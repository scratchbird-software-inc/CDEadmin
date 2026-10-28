import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import PostgresqlCatalog from 'sources/Dialogs/PostgresqlCatalog';
import {withTheme} from '../fake_theme';
let mockDesigner, mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {mockViewer = props; return <div>Native DDN viewer</div>;},
  DDNDesignerSurface: props => {mockDesigner = props; return <div>Native DDN designer</div>;},
}));
const snapshot = {format: 'ddn-source-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'version ddn-next-1\n// ScratchRobin mapping: scratchrobin.postgresql.catalog\n'}};
const result = {snapshot, views: [{id: 'inventory_1', entry: 'catalog.ddn', label: 'Inventory'}],
  provenance: {warnings: ['Explicit incomplete coverage']}, objects: []};
const Component = withTheme(PostgresqlCatalog);

describe('PostgreSQL native catalog DDN', () => {
  let originalHeight;
  beforeEach(() => {originalHeight = window.innerHeight; window.innerHeight = 1200;});
  afterEach(() => {window.innerHeight = originalHeight;});
  it('binds capture to the selected database and never applies statements', async () => {
    const post = jest.fn().mockResolvedValue(result);
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'postgresql_catalog_export', request: {
      database_target_id: 'postgresql-database:42', include_system: false}});
    expect(screen.getByText('Explicit incomplete coverage')).toBeInTheDocument();
    expect(screen.getByText('SR-F-001381')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /apply/i})).not.toBeInTheDocument();
  });
  it('keeps an authored draft across fresh native capture and compares the draft', async () => {
    const post = jest.fn().mockResolvedValue(result);
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button', {name: 'Edit DDN draft'}));
    const draft = {...snapshot, files: {'catalog.ddn': snapshot.files['catalog.ddn'] + '\n// authored'}};
    act(() => mockDesigner.onReady({snapshot: async () => draft}));
    fireEvent.click(screen.getByRole('button', {name: 'Keep draft'}));
    await waitFor(() => expect(screen.queryByText('Native DDN designer')).not.toBeInTheDocument());
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    post.mockResolvedValue({changes: [], counts: {equal: 1}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Compare with live catalog'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Compare with live catalog'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'postgresql_catalog_compare', request: {
      database_target_id: 'postgresql-database:42', include_system: false, source: JSON.stringify(draft)}}));
  });
  it('opens a plain DDN source file through the paired designer', async () => {
    const post = jest.fn().mockResolvedValue(result);
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    const source = snapshot.files['catalog.ddn'];
    const file = {size: source.length, text: async () => source};
    fireEvent.change(screen.getByLabelText('PostgreSQL catalog DDN file'), {target: {files: [file]}});
    await screen.findByText('An imported or edited document is retained separately from the latest live capture.');
    fireEvent.click(screen.getByRole('button', {name: 'Edit DDN draft'}));
    expect(mockDesigner.snapshot.files['catalog.ddn']).toBe(source);
    expect(mockDesigner.snapshot.format).toBe('ddn-source-workspace@1');
  });

  it('keeps the initial baseline while refreshing and sends a three-way preview', async () => {
    const post = jest.fn().mockResolvedValue(result);
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    const source = snapshot.files['catalog.ddn'] + '\n// desired';
    fireEvent.change(screen.getByLabelText('PostgreSQL catalog DDN file'), {target: {files: [{size: source.length, text: async () => source}]}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
    post.mockResolvedValue({...result, snapshot: {...snapshot, files: {'catalog.ddn': '// newer capture'}}});
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
    post.mockResolvedValue({operations: [{resource_id: 'object', name: 'table', statement: 'COMMENT ON TABLE public.t IS NULL'}], blockers: []});
    fireEvent.click(await screen.findByRole('button', {name: 'Preview native changes'}));
    await screen.findByRole('table', {name: 'PostgreSQL native change preview'});
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_schema_plan', request: {
      database_target_id: 'postgresql-database:42', include_system: false,
      source, baseline: JSON.stringify(snapshot)}});
    expect(screen.queryByRole('button', {name: /apply/i})).not.toBeInTheDocument();
  });

  it('switches to native relational views without replacing the catalog baseline', async () => {
    const diagram = {snapshot: {...snapshot, entry: 'relations.ddn', view: 'relations_1', files: {'relations.ddn': 'native relational source'}},
      views: [{id: 'relations_1', entry: 'relations.ddn', label: 'Relations'}], warnings: []};
    const post = jest.fn().mockResolvedValue({...result, diagram});
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Display'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Relational diagram'}));
    expect(mockViewer.snapshot.entry).toBe('relations.ddn');
    expect(mockViewer.snapshot.view).toBe('relations_1');
    fireEvent.click(screen.getByRole('button', {name: 'Edit DDN draft'}));
    expect(mockDesigner.snapshot.entry).toBe('catalog.ddn');
  });

  it('hands relational native edits to the server and keeps the returned three-way documents', async () => {
    const diagram = {snapshot: {...snapshot, entry: 'relations.ddn', view: 'relations_1', files: {'relations.ddn': 'relations'}},
      views: [{id: 'relations_1', entry: 'relations.ddn', label: 'Relations'}], warnings: []};
    const post = jest.fn().mockResolvedValue({...result, diagram});
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button', {name: 'Edit relational DDN'}));
    expect(mockDesigner.snapshot).toEqual(diagram.snapshot);
    const draft = {...diagram.snapshot, files: {'relations.ddn': 'authored relations'}};
    act(() => mockDesigner.onReady({snapshot: async () => draft}));
    post.mockResolvedValue({baseline: 'original catalog', desired: 'authored catalog'});
    fireEvent.click(screen.getByRole('button', {name: 'Keep draft'}));
    await waitFor(() => expect(screen.queryByText('Native DDN designer')).not.toBeInTheDocument());
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_relational_review', request: {
      database_target_id: 'postgresql-database:42', include_system: false, original: diagram.snapshot, snapshot: draft}});
    post.mockResolvedValue({operations: [], blockers: []});
    fireEvent.click(await screen.findByRole('button', {name: 'Preview native changes'}));
    await screen.findByRole('table', {name: 'PostgreSQL native change preview'});
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_schema_plan', request: {
      database_target_id: 'postgresql-database:42', include_system: false,
      source: 'authored catalog', baseline: 'original catalog'}});
  });

  it('requires a prepared receipt and explicit confirmation and preserves unknown outcomes', async () => {
    const plan = {operations: [{resource_id: 'table', name: 't', statement: 'COMMENT ON TABLE public.t IS NULL'}],
      blockers: [], application_supported: true, execution_sha256: 'execution'};
    const post = jest.fn().mockResolvedValue(result);
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    fireEvent.click(await screen.findByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.change(screen.getByLabelText('PostgreSQL catalog DDN file'), {target: {files: [{size: 5, text: async () => 'draft'}]}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
    post.mockResolvedValue(plan);
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByRole('button', {name: 'Prepare application'});
    const receipt = {review_id: 'review', review_digest: 'digest', state: 'reviewed', plan};
    post.mockResolvedValue(receipt);
    fireEvent.click(screen.getByRole('button', {name: 'Prepare application'}));
    expect(await screen.findByRole('button', {name: 'Apply reviewed changes'})).toBeDisabled();
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_schema_review', request: {
      database_target_id: 'postgresql-database:42', include_system: false,
      baseline: JSON.stringify(snapshot), source: 'draft', execution_sha256: 'execution'}});
    fireEvent.click(screen.getByRole('checkbox', {name: 'Confirm reviewed native changes'}));
    post.mockResolvedValue({...receipt, state: 'unknown_outcome'});
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed changes'}));
    await screen.findByText(/unknown_outcome/);
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_schema_apply', request: {
      database_target_id: 'postgresql-database:42', review_id: 'review', review_digest: 'digest', confirmed: true}});
    expect(screen.queryByRole('button', {name: 'Apply reviewed changes'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Prepare application'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Refresh application receipt'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'postgresql_schema_receipt', request: {
      database_target_id: 'postgresql-database:42', review_id: 'review'}}));
  });

});


it('ignores a source capture that completes after selecting another database', async () => {
  const post=jest.fn().mockResolvedValue(result);
  const {rerender}=render(<Component post={post} databaseTargetId="postgresql-database:42" />);
  fireEvent.click(await screen.findByRole('button',{name:'Capture metadata'}));
  await screen.findByText('Native DDN viewer');
  fireEvent.click(screen.getByRole('button',{name:'Edit DDN draft'}));
  let complete;
  act(()=>mockDesigner.onReady({snapshot:()=>new Promise(resolve=>{complete=resolve;})}));
  fireEvent.click(screen.getByRole('button',{name:'Keep draft'}));
  rerender(<Component post={post} databaseTargetId="postgresql-database:43" />);
  await act(async()=>complete(snapshot));
  expect(screen.queryByText('An imported or edited document is retained separately from the latest live capture.')).toBeNull();
  expect(post).toHaveBeenCalledTimes(1);
});
