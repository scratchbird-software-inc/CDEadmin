import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import SQLiteCatalog from 'sources/Dialogs/SQLiteCatalog';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: () => <div>SQLite DDN viewer</div>,
}));
jest.mock('sources/Dialogs/FirebirdCatalogDesigner', () => () => null);

const Component = withTheme(SQLiteCatalog);
const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn',
  view: 'inventory_1', files: {'catalog.ddn': 'native facts'}};

it('offers an observed FTS table for native table rename generation', async () => {
  const renames=[{kind:'table',table:'search:雪',to:'renamed:雪'}];
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'fts',kind:'fts-table',name:'search:雪',path:['main','search:雪']}],provenance:{objects:1,coverage:'partial'}})
    .mockResolvedValueOnce({snapshot,renames});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native table and column renames'));
  fireEvent.change(screen.getByRole('combobox',{name:'Native rename table'}).parentElement.querySelector('input'),{target:{value:'search:雪'}});
  fireEvent.change(screen.getByRole('textbox',{name:'New native name'}),{target:{value:'renamed:雪'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate native rename design'}));
  await screen.findByText(/The generated rename intent is included/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_rename_design',request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),renames}});
});

it('generates a native rename design and carries exact intent into its preview', async () => {
  const renames=[{kind:'column',table:'owned',from:'old_note',to:'new:雪'}];
  const generated={...snapshot,files:{'catalog.ddn':'native rewritten facts'}};
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'parent',kind:'table',name:'owned',path:['main','owned']},
      {resource_id:'column',kind:'column',name:'old_note',path:['main','owned','old_note']}],provenance:{objects:2,coverage:'partial'}})
    .mockResolvedValueOnce({snapshot:generated,renames})
    .mockResolvedValueOnce({operations:[],blockers:[],conflicts:[],application_supported:false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native table and column renames'));
  fireEvent.change(screen.getByRole('combobox',{name:'Native rename kind'}).parentElement.querySelector('input'),{target:{value:'column'}});
  fireEvent.change(screen.getByRole('combobox',{name:'Native rename table'}).parentElement.querySelector('input'),{target:{value:'owned'}});
  fireEvent.change(screen.getByRole('combobox',{name:'Native rename column'}).parentElement.querySelector('input'),{target:{value:'old_note'}});
  fireEvent.change(screen.getByRole('textbox',{name:'New native name'}),{target:{value:'new:雪'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate native rename design'}));
  await screen.findByText(/The generated rename intent is included/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_rename_design',request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),renames}});
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_plan',request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),desired:JSON.stringify(generated,null,2),deletions:[],rebuilds:[],column_renames:[],renames}});
});

it('previews a SQLite native design from its captured baseline', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [], provenance: {objects: 0, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [],
      application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const input = screen.getByLabelText('SQLite catalog DDN file');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(input, {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot), deletions: [], rebuilds: [], column_renames: []}});
});

it('exports only a selected SQLite user table as reviewable SQL', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', path: ['main', 'owned']}],
    provenance: {objects: 1, coverage: 'partial'}})
    .mockResolvedValueOnce({source: 'INSERT INTO "main"."owned" VALUES (1);', rows: 1});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByRole('button', {name: 'Export table as native SQL'}));
  await screen.findByText(/1 SQLite rows exported as SQL/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_data_script', request: {
    database_target_id: 'file-1', resource_id: 'table-1'}});
  expect(screen.getByRole('textbox', {name: 'SQLite native data SQL'}).value).toContain('INSERT INTO');
});

it('sends an explicit deletion identity with the SQLite DDN preview', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', name: 'owned', path: ['main', 'owned']}],
    provenance: {objects: 1, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [], application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'), {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByText('Explicit native deletions (0)'));
  fireEvent.click(screen.getByRole('checkbox', {name: 'Delete SQLite table owned'}));
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot),
    deletions: ['table-1'], rebuilds: [], column_renames: []}});
});

it('sends a reviewed column rename mapping with its selected table rebuild', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', name: 'owned', path: ['main', 'owned']},
      {resource_id: 'column-1', kind: 'column', name: 'old_note', path: ['main', 'owned', 'old_note']}],
    provenance: {objects: 2, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [], application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'), {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByText('Table rebuilds (0)'));
  fireEvent.click(screen.getByRole('checkbox', {name: 'Rebuild SQLite table owned'}));
  fireEvent.click(screen.getByText('Retained column renames (0)'));
  fireEvent.click(screen.getByRole('button', {name: 'Map column rename'}));
  fireEvent.change(screen.getByRole('combobox', {name: 'Existing column'})
    .parentElement.querySelector('input'), {target: {value: 'old_note'}});
  fireEvent.change(screen.getByRole('textbox', {name: 'Desired column name'}),
    {target: {value: 'new_note'}});
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot),
    deletions: [], rebuilds: ['table-1'], column_renames: [
      {table: 'table-1', from: 'old_note', to: 'new_note'}]}});
});

it('selects related tables for one coordinated native rebuild review', async () => {
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'parent',kind:'table',name:'parent',path:['main','parent']},
      {resource_id:'child',kind:'table',name:'child',path:['main','child']}],provenance:{objects:2,coverage:'partial'}})
    .mockResolvedValueOnce({operations:[],blockers:[],conflicts:[],application_supported:false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const file=new File([JSON.stringify(snapshot)],'desired.json',{type:'application/json'});
  file.text=jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'),{target:{files:[file]}});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByText('Table rebuilds (0)'));
  fireEvent.click(screen.getByRole('checkbox',{name:'Rebuild SQLite table parent'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Rebuild SQLite table child'}));
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_plan',request:{database_target_id:'file-1',
    baseline:JSON.stringify(snapshot),desired:JSON.stringify(snapshot),deletions:[],rebuilds:['parent','child'],column_renames:[]}});
});
