import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import SQLiteCatalog from 'sources/Dialogs/SQLiteCatalog';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: () => <div>SQLite DDN viewer</div>,
}));
jest.mock('sources/Dialogs/FirebirdCatalogDesigner', () => () => null);
jest.mock('sources/Dialogs/FirebirdERD', () => ({onReview}) => <button onClick={() => onReview(globalThis.__review)}>Mock diagram review</button>);

const Component = withTheme(SQLiteCatalog);
const snapshot = {format: 'ddn-source-workspace@1', entry: 'catalog.ddn',
  view: 'inventory_1', files: {'catalog.ddn': 'native facts'}};

it('generates an untyped and computed column design from properties before native review', async () => {
  const generated={...snapshot,files:{'catalog.ddn':'native typed additions'}};
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'owned-id',kind:'table',name:'owned',path:['main','owned']}],provenance:{objects:1,coverage:'partial'}})
    .mockResolvedValueOnce({snapshot:generated})
    .mockResolvedValueOnce({operations:[],blockers:[],conflicts:[],application_supported:false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native column additions'));
  fireEvent.change(screen.getByRole('textbox',{name:'Column 1 name'}),{target:{value:'untyped:雪'}});
  fireEvent.click(screen.getByRole('button',{name:'Add another native column'}));
  fireEvent.change(screen.getByRole('textbox',{name:'Column 2 name'}),{target:{value:'computed'}});
  fireEvent.change(screen.getByRole('textbox',{name:'Column 2 generated expression'}),{target:{value:'id * 2'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate column design'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview native changes'})).toBeEnabled());
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_column_design',request:{database_target_id:'file-1',
    baseline:JSON.stringify(snapshot),resource_id:'owned-id',columns:[
      {name:'untyped:雪',data_type:'',nullable:true,constraint_names:{}},
      {name:'computed',data_type:'',nullable:true,generated:{expression:'id * 2',storage:'virtual'},constraint_names:{}}]}});
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await screen.findByText(/Native preview only/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_plan',request:{database_target_id:'file-1',
    baseline:JSON.stringify(snapshot),desired:JSON.stringify(generated,null,2),deletions:[],rebuilds:[],column_renames:[]}});
});

it('discards a late generated column design after changing database scope', async () => {
  let finish;
  const pending=new Promise(resolve=>{finish=resolve;});
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'owned-id',kind:'table',name:'owned',path:['main','owned']}],provenance:{objects:1,coverage:'partial'}})
    .mockReturnValueOnce(pending);
  const view=render(<Component post={post} databaseTargetId="first-file" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native column additions'));
  fireEvent.change(screen.getByRole('textbox',{name:'Column 1 name'}),{target:{value:'private'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate column design'}));
  view.rerender(<Component post={post} databaseTargetId="second-file" />);
  finish({snapshot});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview native changes'})).toBeDisabled());
  expect(screen.queryByText('Native column additions')).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(2);
});

it('shows exact appended-column stages and the native atomic refusal receipt', async () => {
  const stages=['ALTER TABLE "main"."owned" ADD COLUMN untyped',
    'ALTER TABLE "main"."owned" ADD COLUMN computed AS (id * 2) STORED'];
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[],provenance:{objects:0,coverage:'partial'}})
    .mockResolvedValueOnce({operations:[{operation:'append-columns',resource_id:'owned',name:'owned',stages}],
      blockers:[],conflicts:[],application_supported:true,execution_sha256:'native-plan',
      warnings:['Native existing-row checks run during atomic apply.']})
    .mockResolvedValueOnce({review_id:'columns',review_digest:'reviewed',state:'reviewed'})
    .mockResolvedValueOnce({review_id:'columns',state:'rolled_back',outcome:{rediscovery_verified:false,
      native_error:'cannot add a STORED column',native_error_name:'SQLITE_ERROR'}});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  const file=new File([JSON.stringify(snapshot)],'desired.json',{type:'application/json'});
  file.text=jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'),{target:{files:[file]}});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  fireEvent.click(await screen.findByText('Exact native migration statements'));
  const exact=screen.getByText(/ALTER TABLE/,{selector:'pre'});
  expect(exact).toBeVisible();expect(exact).toHaveTextContent(stages[0]);expect(exact).toHaveTextContent(stages[1]);
  expect(screen.getByText('Native existing-row checks run during atomic apply.')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Prepare native change review'}));await screen.findByText(/Native receipt columns: reviewed/);
  const apply=screen.getByRole('button',{name:'Apply reviewed change'});expect(apply).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Confirm this reviewed SQLite change'}));fireEvent.click(apply);
  await screen.findByText(/Native receipt columns: rolled_back/);
  expect(screen.getByLabelText('SQLite native outcome')).toHaveTextContent('cannot add a STORED column (SQLITE_ERROR)');
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_apply',request:{database_target_id:'file-1',
    review_id:'columns',review_digest:'reviewed',confirmed:true}});
  expect(screen.queryByRole('button',{name:'Apply reviewed change'})).not.toBeInTheDocument();
});

it('generates an FTS settings design for native preview and existing review controls', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot, views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'fts', kind: 'fts-table', name: 'search', path: ['main', 'search'],
      fts_configuration: {restorable: true, module: 'fts5', commands: [['automerge', 4]]}}], provenance: {objects: 1, coverage: 'partial'}})
    .mockResolvedValueOnce({snapshot: {...snapshot, files: {'catalog.ddn': 'native desired settings'}}})
    .mockResolvedValueOnce({operations: [{operation: 'fts-configure', resource_id: 'fts', name: 'search', source: 'native setters'}], blockers: [], conflicts: [], application_supported: true});
  render(<Component post={post} databaseTargetId="file" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'})); await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native FTS configuration'));
  fireEvent.change(screen.getByRole('textbox', {name: 'Native FTS settings (JSON)'}), {target: {value: '{"automerge":"8","rank":"bm25(2.0)"}'}});
  fireEvent.click(screen.getByRole('button', {name: 'Generate FTS settings design'}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_fts_configuration_design', request: {
    database_target_id: 'file', baseline: JSON.stringify(snapshot), resource_id: 'fts', settings: {automerge: '8', rank: 'bm25(2.0)'}}});
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByRole('button', {name: 'Prepare native change review'});
  expect(post.mock.calls[2][0].request).toMatchObject({database_target_id: 'file', deletions: [], rebuilds: [], column_renames: []});
});

it('requires the selected external-content index identity in rename generation and review', async () => {
  const renames=[{kind:'table',table:'owner',to:'renamed'}],fts_rebindings=['search-id'];
  const post=jest.fn().mockResolvedValueOnce({snapshot,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[{resource_id:'owner-id',kind:'table',name:'owner',path:['main','owner']},
      {resource_id:'search-id',kind:'fts-table',name:'search',path:['main','search'],external_content:'owner'}],provenance:{objects:2,coverage:'partial'}})
    .mockResolvedValueOnce({snapshot,renames,fts_rebindings})
    .mockResolvedValueOnce({operations:[{operation:'rename-batch',resource_id:'rename',name:'Rename',source:'native reviewed statements'}],blockers:[],conflicts:[],application_supported:true,execution_sha256:'reviewed'})
    .mockResolvedValueOnce({review_id:'native',state:'reviewed'});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByText('Native table and column renames'));
  fireEvent.change(screen.getByRole('combobox',{name:'Native rename table'}).parentElement.querySelector('input'),{target:{value:'owner'}});
  fireEvent.change(screen.getByRole('textbox',{name:'New native name'}),{target:{value:'renamed'}});
  fireEvent.click(screen.getByRole('checkbox',{name:'Rebuild external-content FTS search from owner'}));
  fireEvent.click(screen.getByRole('button',{name:'Generate native rename design'}));await screen.findByText(/The generated rename intent is included/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_rename_design',request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),renames,fts_rebindings}});
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));await screen.findByText('Exact native rename statements and settings');
  fireEvent.click(screen.getByRole('button',{name:'Prepare native change review'}));await screen.findByText(/Native receipt native: reviewed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_review',request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),desired:JSON.stringify(snapshot,null,2),execution_sha256:'reviewed',deletions:[],rebuilds:[],column_renames:[],renames,fts_rebindings}});
});

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

it('turns diagram rename arguments into a native rename design before preview', async () => {
  const generated={...snapshot,files:{'catalog.ddn':'rewritten after native rename'}};
  const diagram={snapshot:{...snapshot,view:'relations_1'},views:[{id:'relations_1',label:'Relations',entry:'catalog.ddn'}]};
  const renames=[{kind:'column',table:'child',from:'note',to:'remark'},{kind:'table',table:'child',to:'kid'}];
  globalThis.__review={baseline:JSON.stringify(snapshot),desired:JSON.stringify(snapshot),renames};
  const post=jest.fn().mockResolvedValueOnce({snapshot,diagram,views:[{id:'inventory_1',label:'Inventory',entry:'catalog.ddn'}],
    objects:[],provenance:{objects:1,coverage:'partial'}})
    .mockResolvedValueOnce({snapshot:generated,renames,fts_rebindings:[]})
    .mockResolvedValueOnce({operations:[],blockers:[],conflicts:[],application_supported:false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('SQLite DDN viewer');
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'Display'}));
  fireEvent.click(await screen.findByRole('option',{name:'Relations'}));
  console.error.mockClear();  // jsdom has no layout: MUI popover size warning
  fireEvent.click(await screen.findByText('Mock diagram review'));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_rename_design',
    request:{database_target_id:'file-1',baseline:JSON.stringify(snapshot),renames}}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'sqlite_schema_plan',request:{database_target_id:'file-1',
    baseline:JSON.stringify(snapshot),desired:expect.any(String),deletions:[],rebuilds:[],column_renames:[],renames,}}));
});
