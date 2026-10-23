import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import SQLNotebook from 'sources/cdeadmin_ui/projects/SQLNotebook';
import {NOTEBOOK_TYPE, newNotebook, portableNotebook, rebindNotebook, retainedSnapshot,
  notebookRequest, sameScope, validateNotebook} from 'sources/cdeadmin_ui/projects/SQLNotebookModel';

const scope = {engine: 'mysql', endpoint_id: 'native-endpoint', database_target_id: 'database'};
const content = {...newNotebook(scope), cells: [
  {id: 'n', kind: 'note', source: '<script>inert note</script>'},
  {id: 'q', kind: 'sql', source: 'SELECT id, token FROM evidence', snapshot: null}]};
const asset = {asset_id: 'investigation', name: 'Evidence', asset_type: NOTEBOOK_TYPE,
  version: 2, access: 'owner', content};
const client = access => ({listProjects: jest.fn().mockResolvedValue([{project_id: 'p', name: 'Investigations', access}]),
  project: jest.fn().mockResolvedValue({access, assets: [asset]}),
  asset: jest.fn().mockResolvedValue({...asset, access}), revisions: jest.fn().mockResolvedValue([{version: 2}, {version: 1}]),
  saveAsset: jest.fn().mockResolvedValue({...asset, version: 3}), setMember: jest.fn().mockResolvedValue({})});
const Component = withTheme(SQLNotebook);
const originalHeight = window.innerHeight;
beforeAll(() => {window.innerHeight = 1800;});
afterAll(() => {window.innerHeight = originalHeight;});
async function choose(label, value) {
  fireEvent.mouseDown(screen.getByLabelText(label));
  fireEvent.click(await screen.findByRole('option', {name: value}));
}
describe('SQL notebook', () => {
  it('opens a saved asset without execution and keeps viewer permissions', async () => {
    const api = client('viewer'), run = jest.fn();
    render(<Component client={api} initialProjectId="p" initialAssetId="investigation" scope={scope} onRun={run} />);
    expect(await screen.findByText('Loaded revision 2. No SQL executed.')).toBeInTheDocument();
    expect(run).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Notebook note')).toHaveValue('<script>inert note</script>');
    expect(screen.getByRole('button', {name: 'Save notebook revision'})).toBeDisabled();
    expect(api.saveAsset).not.toHaveBeenCalled();
  });
  it('requires explicit Run and does not save transient results; edited SQL invalidates the snapshot', async () => {
    const api = client('owner'), run = jest.fn(), load = jest.fn();
    const rendered = {view_model: {columns: [{name: 'id'}, {name: 'token'}], rows: [{id: '9007199254740993', token: 'private-value'}]}, page: {source_count: 1}};
    render(<Component client={api} initialProjectId="p" initialAssetId="investigation" scope={scope}
      onRun={run} onLoad={load} rendered={rendered} executedSource={content.cells[1].source} />);
    await screen.findByText('Loaded revision 2. No SQL executed.');
    await choose('Notebook cell', /^2\. sql:/);
    expect(run).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Load cell in SQL editor'}));
    expect(load).toHaveBeenCalledWith(content.cells[1].source); expect(run).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Run selected SQL cell'}));
    expect(run).toHaveBeenCalledTimes(1);
    await choose('Snapshot id', 'Retain value');
    fireEvent.click(screen.getByRole('button', {name: 'Retain reviewed page snapshot'}));
    const retained = await screen.findByLabelText('Retained notebook snapshot');
    expect(retained).toHaveTextContent('9007199254740993');
    expect(retained).toHaveTextContent('[REDACTED]'); expect(retained).not.toHaveTextContent('private-value');
    expect(api.saveAsset).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Notebook SQL cell'), {target: {value: 'SELECT changed'}});
    expect(screen.queryByLabelText('Retained notebook snapshot')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Save notebook revision'}));
    await waitFor(() => expect(api.saveAsset).toHaveBeenCalledWith('p', 'investigation', expect.objectContaining({expected_version: 2,
      content: expect.objectContaining({cells: expect.arrayContaining([expect.objectContaining({source: 'SELECT changed', snapshot: null})])})})));
  });
  it('refuses cross-target execution until explicit rebinding clears old snapshots', async () => {
    const api = client('owner'), run = jest.fn();
    render(<Component client={api} initialProjectId="p" initialAssetId="investigation"
      scope={{...scope, database_target_id: 'other'}} onRun={run} />);
    await screen.findByText('Loaded revision 2. No SQL executed.');
    await choose('Notebook cell', /^2\. sql:/);
    expect(screen.getByRole('button', {name: 'Run selected SQL cell'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Bind to this SQL editor (clear snapshots)'}));
    expect(run).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Run selected SQL cell'})).toBeEnabled();
  });
  it('preserves edits on a concurrent save failure and blocks sharing an unsaved draft', async () => {
    const api = client('owner'); api.saveAsset.mockRejectedValue(new Error('asset version has changed'));
    render(<Component client={api} initialProjectId="p" initialAssetId="investigation" />);
    await screen.findByText('Loaded revision 2. No SQL executed.');
    fireEvent.change(screen.getByLabelText('Notebook note'), {target: {value: 'Retain my edit'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save notebook revision'}));
    await screen.findByText('asset version has changed');
    expect(screen.getByLabelText('Notebook note')).toHaveValue('Retain my edit');
    expect(screen.getByRole('button', {name: 'Export shareable notebook'})).toBeDisabled();
  });
  it('loads an earlier revision as a draft that must be saved before sharing', async () => {
    const api = client('owner');
    render(<Component client={api} initialProjectId="p" initialAssetId="investigation" />);
    await screen.findByText('Loaded revision 2. No SQL executed.');
    await choose('Notebook revision', 'v1');
    fireEvent.click(screen.getByRole('button', {name: 'Reload notebook'}));
    await screen.findByText('Loaded revision 1 as a draft; next save checks current revision 2.');
    expect(screen.getByRole('button', {name: 'Export shareable notebook'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Save notebook revision'}));
    await waitFor(() => expect(api.saveAsset).toHaveBeenCalledWith('p', 'investigation', expect.objectContaining({expected_version: 2})));
  });
});
describe('portable result retention', () => {
  it('compares scoped identities independent of JSON key order and keeps asset paths distinct', () => {
    expect(sameScope(scope, {database_target_id: scope.database_target_id, endpoint_id: scope.endpoint_id, engine: 'mysql'})).toBe(true);
    expect(notebookRequest(content, 'one', 0, 'one').path).not.toEqual(notebookRequest(content, 'two', 0, 'two').path);
  });
  it('excludes omitted values, redacts selected columns and removes binding on export', () => {
    const rendered = {view_model: {columns: [{name: 'id'}, {name: 'token'}, {name: 'omitted'}],
      rows: Array.from({length: 101}, () => ({id: '18446744073709551615', token: 'private', omitted: 'do-not-retain'}))}, page: {next_cursor: 'private-cursor'}};
    const snapshot = retainedSnapshot(rendered, content.cells[1].source, scope, {0: 'retain', 1: 'redact'});
    expect(snapshot.rows).toHaveLength(100); expect(snapshot.limited).toBe(true);
    const value = {...content, cells: [content.cells[0], {...content.cells[1], snapshot}]};
    const portable = portableNotebook(value);
    expect(portable.scope).toBeNull(); expect(portable.cells[1].snapshot.scope).toBeNull();
    const encoded = JSON.stringify(portable);
    for(const secret of ['private', 'do-not-retain', 'native-endpoint', 'private-cursor']) expect(encoded).not.toContain(secret);
    expect(rebindNotebook(portable, scope).cells[1].snapshot).toBeNull();
  });
  it('refuses credential text, automatic execution fields and mismatched result provenance', () => {
    expect(() => validateNotebook({...content, auto_execute: true})).toThrow('fields');
    expect(() => validateNotebook({...content, cells: [{id: 'n', kind: 'note', source: 'mysql://user:secret@host/db'}]})).toThrow('credential');
    const snapshot = retainedSnapshot({view_model: {columns: [{name: 'id'}], rows: [{id: '1'}]}}, 'SELECT other', scope, {0: 'retain'});
    expect(() => validateNotebook({...content, cells: [{...content.cells[1], snapshot}]})).toThrow('differs');
  });
});
