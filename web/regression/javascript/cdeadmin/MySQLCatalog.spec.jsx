import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLCatalog from 'sources/Dialogs/MySQLCatalog';
import {withTheme} from '../fake_theme';
let mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {mockViewer = props; return <div>Native DDN viewer</div>;},
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => function MockGrid(props) {return <div aria-label={props['aria-label']}>{props.rows.length} changes</div>;});
const Component = withTheme(MySQLCatalog);

const capture = {snapshot: {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'native metadata'}},
  views: [{id: 'inventory_1', label: 'Native inventory', entry: 'catalog.ddn'}],
  provenance: {warnings: ['Visibility is partial']}};

describe('MySQL native catalog form', () => {
  it('binds capture to its database and presents DDN without engine-specific substitution', async () => {
    const post = jest.fn().mockResolvedValue(capture);
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'mysql_catalog_export', request: {
      database_target_id: 'mysql-owned-target', include_system: false}});
    expect(mockViewer.snapshot.files).toEqual(capture.snapshot.files);
    expect(mockViewer.presentation).toBe(true);
    expect(screen.getByText('Visibility is partial')).toBeVisible();
    expect(screen.getByText('SR-F-001393')).toBeVisible();
  });

  it('does not show a late response from a previously selected database', async () => {
    let finish;
    const post = jest.fn().mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<Component post={post} databaseTargetId="old-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    mounted.rerender(<Component post={post} databaseTargetId="new-target" />);
    await act(async () => {finish(capture);});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Capture metadata'})).toBeEnabled());
    expect(screen.queryByText('Native DDN viewer')).not.toBeInTheDocument();
  });

  it('generates native SQL from the complete capture without executing or using only its displayed view', async () => {
    const metadata = {script: 'CREATE TABLE native_table(id int);', script_available: true,
      blockers: [], prerequisites: [], warnings: ['Observational export only']};
    const post = jest.fn().mockResolvedValueOnce(capture).mockResolvedValueOnce(metadata);
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button', {name: 'Generate native SQL'}));
    const script = await screen.findByRole('textbox', {name: 'Native MySQL metadata script'});
    expect(script).toHaveValue(metadata.script);
    expect(script).toHaveAttribute('readonly');
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_sql_export', request: {
      database_target_id: 'mysql-owned-target', source: JSON.stringify(capture.snapshot)}});
    expect(screen.getByRole('button', {name: 'Download native SQL'})).toBeEnabled();
    expect(post).toHaveBeenCalledTimes(2);
  });


  it('acquires data only after explicit relation/mode/budget selection and shows static DDN coverage', async () => {
    const captured = {...capture, objects: [{resource_id: 'native-table', kind: 'table', name: 'Exact values'}]};
    const data = {snapshot: {format: 'ddn-workspace@1', entry: 'result-1.ddn', view: 'result_1',
      files: {'result-1.ddn': 'static exact data'}}, views: [{id: 'result_1', label: 'Data page 1', entry: 'result-1.ddn'}],
    warnings: ['Explicit sample coverage']};
    const post = jest.fn().mockResolvedValueOnce(captured).mockResolvedValueOnce(data);
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Data row budget'}), {target: {value: '3'}});
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected data'}));
    await screen.findByText('Explicit sample coverage');
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_data_capture', request: {
      database_target_id: 'mysql-owned-target', resource_id: 'native-table', mode: 'sample', row_limit: 3}});
    expect(mockViewer.snapshot.files).toEqual(data.snapshot.files);
    expect(screen.getByText('SR-F-001399')).toBeVisible();
  });

});

describe('MySQL three-way native metadata preview', () => {
  it('binds saved baseline and desired DDN to fresh native review without applying', async () => {
    const preview={operations: [{kind:'table',source: 'ALTER TABLE `demo`.`native` ADD COLUMN `value` int'}], ready_for_review: true,
      blockers: [], conflicts: [], ignored: [], executed: false};
    const post=jest.fn().mockResolvedValueOnce(capture).mockResolvedValueOnce(preview).mockResolvedValueOnce({
      ...preview, native_grammar_validated: true, native_validation: [{index: 0, accepted: true}]});
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
    await screen.findByRole('textbox', {name: 'Native MySQL change preview'});
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_schema_plan', request: {
      database_target_id: 'mysql-owned-target', baseline: JSON.stringify(capture.snapshot), source: JSON.stringify(capture.snapshot)}});
    fireEvent.click(screen.getByRole('button', {name: 'Validate native changes'}));
    await screen.findByText('Native PREPARE accepted the change statements; none were executed.');
    expect(post.mock.calls.every(([request]) => ['mysql_catalog_export','mysql_schema_plan','mysql_schema_validate'].includes(request.action))).toBe(true);
    expect(screen.getByText('SR-F-001402')).toBeVisible();
    expect(screen.getByRole('button', {name: 'Apply reviewed change'})).toBeDisabled();
  });
});

describe('MySQL reviewed schema controls', () => {
  it.each([['table','alter'],['table','create'],['table','drop'],['view','alter'],['view','create'],['view','drop'],['library','create'],['library','alter'],['library','drop']])('requires native validation, receipt and confirmation for %s %s, then shows the native outcome', async (kind,operationId) => {
    const snapshot={view:'inventory_1',entry:'native.ddn',files:{'native.ddn':'native'}};
    const operation={kind,operation:operationId,source:operationId === 'create' ? 'CREATE TABLE `db`.`t` (`extra` int)' : operationId === 'drop' ? 'DROP TABLE `db`.`t`' : 'ALTER TABLE `db`.`t` ADD COLUMN `extra` int'};
    const preview={ready_for_review:true,native_grammar_validated:false,execution_sha256:'digest',operations:[operation],warnings:kind==='view'?['External DDL is not fenced']:[]};
    const receipt={review_id:'receipt',review_digest:'review-digest',state:'reviewed'};
    const post=jest.fn().mockImplementation(async ({action}) => {
      if(action==='mysql_catalog_export') return {snapshot,views:[{id:'inventory_1',entry:'native.ddn'}],objects:[]};
      if(action==='mysql_schema_plan') return preview;
      if(action==='mysql_schema_validate') return {...preview,native_grammar_validated:true,native_validation:[{accepted:true}]};
      if(action==='mysql_schema_review') return receipt;
      return {...receipt,state:'committed',outcome:{rediscovery_verified:true,native_definition:'CREATE TABLE `t` (`extra` int)',desired_definition_exact_match:false}};
    });
    render(<Component post={post} databaseTargetId="db-target" />);
    fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
    await screen.findByRole('textbox',{name:'Native MySQL change preview'});
    if(kind==='view') expect(screen.getByText('External DDL is not fenced')).toBeVisible();
    expect(screen.getByRole('button',{name:'Prepare reviewed change'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button',{name:'Validate native changes'}));
    await screen.findByText('Native PREPARE accepted the change statements; none were executed.');
    fireEvent.click(screen.getByRole('button',{name:'Prepare reviewed change'}));
    await screen.findByText(/Schema receipt receipt: reviewed/);
    expect(screen.getByRole('button',{name:'Apply reviewed change'})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox',{name:'Confirm reviewed native DDL and implicit commit'}));
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed change'}));
    await screen.findByText(/Schema receipt receipt: committed/);
    expect(post).toHaveBeenLastCalledWith({action:'mysql_schema_apply',request:{database_target_id:'db-target',review_id:'receipt',review_digest:'review-digest',confirmed:true}});
    expect(screen.getByRole('button',{name:'Apply reviewed change'})).toBeDisabled();
    expect(screen.getByRole('textbox',{name:'Rediscovered native definition'})).toHaveValue('CREATE TABLE `t` (`extra` int)');
    expect(screen.getByText(/Native SHOW CREATE differs/)).toBeInTheDocument();
  });
});


describe('MySQL native encoded download', () => {
  it('downloads the original bytes while displaying a documentary Unicode preview', async () => {
    const metadata={script_available:true,script:null,script_preview:'SELECT \'é€\';',encoded_script:{data_base64:'6YA='}};
    const post=jest.fn().mockResolvedValueOnce(capture).mockResolvedValueOnce(metadata);
    const create=jest.fn().mockReturnValue('blob:native');
    const previous=URL.createObjectURL; URL.createObjectURL=create;
    const revoke=URL.revokeObjectURL; URL.revokeObjectURL=jest.fn();
    jest.useFakeTimers();
    const click=jest.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(() => {});
    try {
      render(<Component post={post} databaseTargetId="mysql-owned-target" />);
      fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));await screen.findByText('Native DDN viewer');
      fireEvent.click(screen.getByRole('button',{name:'Generate native SQL'}));
      expect(await screen.findByRole('textbox',{name:'Native MySQL metadata script'})).toHaveValue(metadata.script_preview);
      fireEvent.click(screen.getByRole('button',{name:'Download native SQL'}));
      const blob=create.mock.calls[0][0];expect(blob.type).toBe('application/octet-stream');expect(blob.size).toBe(2);
      expect(screen.getByText(/mysql --binary-mode/)).toBeVisible();expect(click).toHaveBeenCalledTimes(1);
    } finally {jest.runOnlyPendingTimers();jest.useRealTimers();URL.createObjectURL=previous;URL.revokeObjectURL=revoke;click.mockRestore();}
  });
});

it('keeps parent previews disabled until the relational handoff installs its reviewed documents', async () => {
  let finish;
  const diagram={snapshot:{format:'ddn-workspace@1',entry:'relations.ddn',view:'relations_1',files:{'relations.ddn':'native relations'}},views:[]};
  const post=jest.fn().mockImplementation(request => {
    if(request.action==='mysql_catalog_export') return Promise.resolve({...capture,diagram});
    if(request.action==='mysql_relational_review') return new Promise(resolve => {finish=resolve;});
    return Promise.resolve({operations:[],blockers:[],conflicts:[],ignored:[]});
  });
  render(<Component post={post} databaseTargetId="mysql-target" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));
  await screen.findByText('Native tables, views, columns and foreign keys. Diagram edits do not alter the database. Save a design revision or download it to retain changes. Native application requires schema reconciliation and explicit review.');
  // The suite's fixed 800px offsetHeight needs a matching menu viewport.
  const viewport=window.innerHeight;
  try {
    window.innerHeight=1200;
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Display'}));
    fireEvent.click(screen.getByRole('option',{name:'Relations'}));
  } finally {window.innerHeight=viewport;}
  fireEvent.click(screen.getByRole('button',{name:'Review relational metadata changes'}));
  expect(screen.getByRole('button',{name:'Preview native changes'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Capture metadata'})).toBeDisabled();
  await act(async () => {finish({baseline:'reviewed baseline',desired:'reviewed desired'});});
  await waitFor(() => expect(screen.getByRole('button',{name:'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_schema_plan',request:{database_target_id:'mysql-target',baseline:'reviewed baseline',source:'reviewed desired'}}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Capture metadata'})).toBeEnabled());
});


it('retains ordered native outcomes for a multi-table receipt and disables replay', async () => {
  const operations=['a','b'].map(name => ({kind:'table',operation:'alter',resource_id:name,source:`ALTER TABLE \`db\`.\`${name}\` ADD COLUMN extra int`}));
  const preview={ready_for_review:true,operations};
  const entries=[{index:0,resource_id:'a',state:'committed'},{index:1,resource_id:'b',state:'unknown_outcome'}];
  const receipt={review_id:'batch',review_digest:'sealed',state:'reviewed',statement_outcomes:entries.map(row => ({...row,state:'not_dispatched'}))};
  const post=jest.fn().mockImplementation(async ({action}) => {
    if(action==='mysql_catalog_export') return capture;
    if(action==='mysql_schema_plan') return preview;
    if(action==='mysql_schema_validate') return {...preview,native_grammar_validated:true,native_validation:operations.map((_,index) => ({index,accepted:true}))};
    if(action==='mysql_schema_review') return receipt;
    return {...receipt,state:'unknown_outcome',statement_outcomes:entries,outcome:{rediscovery_verified:false}};
  });
  render(<Component post={post} databaseTargetId="batch-target" />);
  fireEvent.click(screen.getByRole('button',{name:'Capture metadata'}));
  await screen.findByText('Native DDN viewer');
  fireEvent.click(screen.getByRole('button',{name:'Preview native changes'}));
  await screen.findByRole('textbox',{name:'Native MySQL change preview'});
  fireEvent.click(screen.getByRole('button',{name:'Validate native changes'}));
  await screen.findByText('Native PREPARE accepted the change statements; none were executed.');
  fireEvent.click(screen.getByRole('button',{name:'Prepare reviewed change'}));
  await screen.findByText(/Schema receipt batch: reviewed/);
  expect(screen.getByLabelText('MySQL migration statement outcomes')).toHaveTextContent('2 changes');
  fireEvent.click(screen.getByRole('checkbox',{name:'Confirm reviewed native DDL and implicit commit'}));
  fireEvent.click(screen.getByRole('button',{name:'Apply reviewed change'}));
  await screen.findByText(/Schema receipt batch: unknown_outcome/);
  expect(screen.getByRole('button',{name:'Apply reviewed change'})).toBeDisabled();
  expect(post.mock.calls.filter(([request]) => request.action==='mysql_schema_apply')).toHaveLength(1);
});
