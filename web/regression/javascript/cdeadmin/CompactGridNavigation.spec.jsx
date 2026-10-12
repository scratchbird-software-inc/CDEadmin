import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {StructuredDataGrid} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import PagedDataGrid from '../../../pgadmin/static/js/cdeadmin_ui/data/PagedDataGrid';

const table = {resource_id: 'table:T', resource_kind: 'table', display_name: 'T'};
const catalog = {objects: [{resource_kind: 'table', operations: ['insert', 'update', 'delete'].map(
  operation_id => ({operation_id, execution_available: true}))}]};
const rowPage = (value, continuation=null) => ({editable: true,
  columns: [{name: 'name', editable: true}],
  rows: [{values: {name: value}, identity_token: value}], continuation});
function fixture(pages) {
  const calls = [];
  const post = jest.fn(async request => {
    calls.push(request);
    if (request.action === 'open_session') return {session_id: 'owner'};
    if (request.action === 'visual_admin_rows') return pages.shift();
    if (request.action === 'visual_admin_validate') return {valid: true};
    if (request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
    if (request.action === 'visual_admin_apply') return {provider_result: {staged_in_provider_session: true}};
    return {};
  });
  const setError = jest.fn();
  render(<StructuredDataGrid catalog={catalog} resources={[table]} post={post}
    setError={setError} languageProfile="firebird-sql" databaseTargetId="db" />);
  return {post, calls, setError};
}
async function load() {
  fireEvent.click(screen.getByRole('button', {name: 'Load rows'}));
  await waitFor(() => expect(screen.getByRole('combobox', {name: 'Grid mode'})).not.toHaveAttribute('aria-disabled', 'true'));
}
async function edit() {
  fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Grid mode'}));
  fireEvent.click(screen.getByRole('option', {name: 'Edit'}));
}

describe('compact provider grid ownership and navigation', () => {
  let originalHeight;
  beforeEach(() => {originalHeight = window.innerHeight; window.innerHeight = 1200;});
  afterEach(() => {window.innerHeight = originalHeight;});
  it('caches backward pages without replaying native continuations', async () => {
    const {post, calls} = fixture([rowPage('one', 'next'), rowPage('two')]);
    await load();
    expect(screen.queryByRole('textbox', {name: 'name value'})).toBeNull();
    expect(screen.getByRole('button', {name: /Last page/})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Next page'}));
    expect(await screen.findByText('two')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'First page'}));
    expect(screen.getByText('one')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
    expect(screen.getByText('two')).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(3);
    expect(calls[2].request).toMatchObject({continuation: 'next', session_id: 'owner', database_target_id: 'db'});
  });
  it('caps retrieval and closes the cursor without deciding the transaction', async () => {
    const {calls} = fixture([rowPage('one', 'next')]);
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Maximum rows retrieved'}), {target: {value: '1'}});
    await load();
    expect(screen.getByText('Retrieval limit reached')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Next page'})).toBeDisabled();
    expect(calls[1].request.limit).toBe(1);
    expect(calls.map(call => call.action)).toEqual(['open_session', 'visual_admin_rows', 'visual_admin_rows_cancel']);
  });
  it('keeps the native batch size stable and clips a partial final page', async () => {
    const batch = (start, continuation) => ({...rowPage('unused', continuation),
      rows: Array.from({length: 25}, (_, index) => ({values: {name: `row-${start + index}`}, identity_token: `${start + index}`}))});
    const {calls} = fixture([batch(0, 'second'), batch(25, 'third')]);
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Rows per page'}));
    fireEvent.click(screen.getByRole('option', {name: '25'}));
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Maximum rows retrieved'}), {target: {value: '45'}});
    await load();
    fireEvent.click(screen.getByRole('button', {name: 'Next page'}));
    await screen.findByText('45 rows retained');
    expect(screen.getByText('5 excess rows from the final native batch discarded')).toBeInTheDocument();
    expect(calls.filter(call => call.action === 'visual_admin_rows').map(call => call.request.limit)).toEqual([25, 25]);
    expect(calls.at(-1)).toMatchObject({action: 'visual_admin_rows_cancel', request: {continuation: 'third'}});
    expect(screen.getByRole('button', {name: 'Next page'})).toBeDisabled();
  });
  it('blocks navigation and finalization with drafts, then stages and commits explicitly', async () => {
    const {calls} = fixture([rowPage('one', 'next'), rowPage('changed'), rowPage('committed')]);
    await load(); await edit();
    fireEvent.change(screen.getByRole('textbox', {name: 'name value'}), {target: {value: 'changed'}});
    expect(screen.getByRole('button', {name: 'Next page'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Load rows'})).toBeDisabled();
    expect(screen.getByRole('combobox', {name: 'Grid mode'})).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('textbox', {name: 'name new value'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Commit changes'})).not.toBeDisabled());
    expect(calls.some(call => call.action === 'transaction_action')).toBe(false);
    fireEvent.click(screen.getByRole('button', {name: 'Commit changes'}));
    await waitFor(() => expect(calls.find(call => call.action === 'transaction_action')).toMatchObject({
      session_id: 'owner', database_target_id: 'db', transaction_action: 'commit',
    }));
  });
  it('automatically commits saved edits and disables manual transaction buttons', async () => {
    const {calls} = fixture([rowPage('one'), rowPage('changed')]);
    fireEvent.click(screen.getByRole('checkbox', {name: 'Autocommit'}));
    await load(); await edit();
    expect(screen.getByRole('button', {name: 'Commit changes'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Rollback changes'})).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', {name: 'name value'}), {target: {value: 'changed'}});
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(screen.getByRole('checkbox', {name: 'Autocommit'})).not.toBeDisabled());
    expect(calls.map(call => call.action)).toEqual(['open_session', 'visual_admin_rows',
      'visual_admin_validate', 'visual_admin_plan', 'visual_admin_apply', 'transaction_action', 'visual_admin_rows']);
    expect(calls[0].session_purpose).toBe('firebird-row-grid');
    expect(calls[5]).toMatchObject({transaction_action: 'commit', session_id: 'owner'});
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).toBeChecked();
    expect(screen.getByRole('button', {name: 'Commit changes'})).toBeDisabled();
  });
  it('retains an unresolved automatic commit without replaying the saved mutation', async () => {
    const {post, calls, setError} = fixture([rowPage('one')]);
    fireEvent.click(screen.getByRole('checkbox', {name: 'Autocommit'}));
    await load(); await edit();
    fireEvent.change(screen.getByRole('textbox', {name: 'name value'}), {target: {value: 'changed'}});
    const original = post.getMockImplementation();
    post.mockImplementation(request => request.action === 'transaction_action' ?
      Promise.reject(new Error('Commit outcome unknown')) : original(request));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Commit outcome unknown'));
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).not.toBeChecked();
    expect(screen.getByRole('checkbox', {name: 'Autocommit'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Commit changes'})).not.toBeDisabled();
    expect(screen.getByRole('button', {name: 'Save'})).toBeDisabled();
    expect(calls.filter(call => call.action === 'visual_admin_apply')).toHaveLength(1);
  });
  it('pages finite read-only results independently of native execution', () => {
    const rows = Array.from({length: 205}, (_, id) => ({id, name: `row-${id}`}));
    render(<PagedDataGrid readOnly rows={rows} columns={[{key: 'name', name: 'Name'}]} rowKeyGetter={row => row.id} />);
    fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
    expect(screen.getByText('row-200')).toBeInTheDocument();
    expect(screen.queryByText('row-0')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'First page'}));
    expect(screen.getByText('row-0')).toBeInTheDocument();
  });
});
