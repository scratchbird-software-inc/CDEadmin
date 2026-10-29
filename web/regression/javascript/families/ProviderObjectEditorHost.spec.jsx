import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import {
  OperationDialog, ProviderObjectEditorHost, makePost, recordFromResource,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from './familyFixtures';

beforeEach(() => {
  window.innerHeight = 1200;
});

function fakeApi(bundle, resource) {
  const calls = [];
  return {
    calls,
    get: jest.fn(async () => ({data: {success: 1, data: bundle}})),
    post: jest.fn(async (_url, payload) => {
      calls.push(payload);
      switch(payload.action) {
      case 'resource_inspect': return {data: {success: 1, data: resource}};
      case 'visual_admin_validate': return {data: {success: 1, data: {valid: true, errors: []}}};
      case 'visual_admin_plan': return {data: {success: 1, data: {plan_id: 'plan-1', plan_digest: 'digest-1', state: 'ready',
        execution_available: true, confirmation_required: false,
        command_preview: {statements: [{source: 'ALTER TABLE orders ADD note VARCHAR(20)'}], driver_operation: 'execute'}}}};
      case 'visual_admin_apply': return {data: {success: 1, data: {provider_result: {committed: true}}}};
      default: return {data: {success: 0, errormsg: `unexpected ${payload.action}`}};
      }
    }),
  };
}

const resource = {
  resource_id: 'tbl-orders', resource_kind: 'table', display_name: 'ORDERS', display_path: ['ORDERS'],
  extensions: {firebird: {native: {name: 'ORDERS', table_type: 'PERSISTENT', sql_security: 'DEFINER'}},
    cdeadmin: {database_target_id: 'db-1'}},
};

describe('ProviderObjectEditorHost', () => {
  it('loads the bundle, inspects the resource, previews the provider plan and applies it', async () => {
    const bundle = loadEngineBundle('firebird');
    const api = fakeApi(bundle, resource);
    const onApplied = jest.fn();
    render(<Theme><ProviderObjectEditorHost api={api} endpointUrl="/browser/server/cde_workspace/1/2" engine="firebird"
      version="5.0.4" resourceId="tbl-orders" resourceKind="table" databaseTargetId="db-1" mode="alter"
      displayName="ORDERS" onClose={() => {}} onApplied={onApplied} /></Theme>);
    await screen.findByRole('dialog', {name: /Edit table — ORDERS/});
    expect(api.get).toHaveBeenCalledWith('/cdeadmin/api/ui/descriptors/firebird?version=5.0.4');
    expect(api.calls[0]).toMatchObject({action: 'resource_inspect', request: {resource_id: 'tbl-orders', database_target_id: 'db-1'}});
    // The record pre-fills the General tab from the resource's native block.
    expect(screen.getByLabelText(/^Name/)).toHaveValue('ORDERS');
    // Edit a field, then the SQL tab shows the provider plan.
    fireEvent.change(screen.getByLabelText(/^Name/), {target: {value: 'ORDERS2'}});
    const tablist = screen.getByRole('tablist', {name: 'Table tabs'});
    fireEvent.click(within(tablist).getByRole('tab', {name: 'SQL'}));
    await waitFor(() => expect(screen.getByRole('tabpanel', {name: 'SQL'}).textContent).toContain('ALTER TABLE orders ADD note'));
    const planCall = api.calls.find((call) => call.action === 'visual_admin_plan');
    expect(planCall.request).toMatchObject({resource_kind: 'table', operation_id: 'alter', database_target_id: 'db-1',
      target_resource: {resource_id: 'tbl-orders'}, draft: {name: 'ORDERS2'}});
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(api.calls.at(-1)).toMatchObject({action: 'visual_admin_apply',
      request: {plan_id: 'plan-1', plan_digest: 'digest-1', confirmed: true}});
    expect(screen.getByText('Applied.')).toBeInTheDocument();
  });

  it('explains when the engine declares no editor for the kind', async () => {
    const bundle = loadEngineBundle('sqlite');
    const api = fakeApi(bundle, resource);
    render(<Theme><ProviderObjectEditorHost api={api} endpointUrl="/x" engine="sqlite" resourceId="r" resourceKind="pragma"
      mode="alter" onClose={() => {}} /></Theme>);
    await screen.findByText(/No pragma editor is declared for sqlite yet/);
  });

  it('surfaces provider validation errors instead of planning', async () => {
    const bundle = loadEngineBundle('firebird');
    const api = fakeApi(bundle, resource);
    api.post.mockImplementation(async (_url, payload) => payload.action === 'resource_inspect' ?
      {data: {success: 1, data: resource}} :
      payload.action === 'visual_admin_validate' ?
        {data: {success: 1, data: {valid: false, errors: [{field_id: 'name', message: 'Name is reserved'}]}}} :
        {data: {success: 0, errormsg: 'should not plan'}});
    render(<Theme><ProviderObjectEditorHost api={api} endpointUrl="/x" engine="firebird" resourceId="tbl-orders"
      resourceKind="table" mode="alter" onClose={() => {}} /></Theme>);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText(/^Name/), {target: {value: 'BAD'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview SQL'}));
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toContain('Name is reserved'));
  });
});

describe('record and transport helpers', () => {
  it('flattens native values and scopes database requests', async () => {
    expect(recordFromResource(resource)).toMatchObject({name: 'ORDERS', table_type: 'PERSISTENT', resource_id: 'tbl-orders'});
    const api = {post: jest.fn(async () => ({data: {success: 1, data: {ok: 1}}}))};
    const post = makePost(api, '/endpoint', 'db-9');
    await post({action: 'visual_admin_plan', request: {draft: {}}});
    expect(api.post).toHaveBeenCalledWith('/endpoint', {action: 'visual_admin_plan', request: {draft: {}, database_target_id: 'db-9'}});
    await post({action: 'resource_page', request: {database_target_id: 'explicit'}});
    expect(api.post.mock.calls[1][1].request.database_target_id).toBe('explicit');
    api.post.mockResolvedValueOnce({data: {success: 0, errormsg: 'nope'}});
    await expect(post({action: 'visual_admin_apply', request: {}})).rejects.toThrow('nope');
  });
});

describe('OperationDialog', () => {
  const operation = {
    operation_id: 'sweep_database', resource_kind: 'database', title: 'Sweep database', tier: 3,
    menu: {category: 'maintenance'}, status: 'draft', confirmation: 'confirm', execution_host: true, produces_log: true,
    fields: [
      {field_id: 'wait', label: 'Wait for completion', control: 'boolean', default: true},
      {field_id: 'note', label: 'Note', control: 'text', group: 'Audit'},
    ],
  };
  it('plans, shows the native preview and runs with a receipt', async () => {
    const plan = jest.fn(async () => ({plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true,
      command_preview: 'gfix -sweep employee.fdb'}));
    const apply = jest.fn(async () => ({provider_result: 'Sweep complete: 12 pages'}));
    render(<Theme><OperationDialog open operation={operation} targetName="employee" plan={plan} apply={apply}
      onClose={() => {}} /></Theme>);
    expect(screen.getByRole('dialog', {name: 'Sweep database — employee'})).toBeInTheDocument();
    expect(screen.getByLabelText('Execution host')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', {name: 'Wait for completion'})).toBeChecked();
    fireEvent.click(screen.getByRole('button', {name: 'Preview'}));
    await waitFor(() => expect(plan).toHaveBeenCalledWith({draft: {wait: true}, execution_host: 'local'}));
    await waitFor(() => expect(screen.getByRole('dialog').textContent).toContain('gfix -sweep employee.fdb'));
    fireEvent.click(screen.getByRole('button', {name: 'Run'}));
    await waitFor(() => expect(apply).toHaveBeenCalled());
    await screen.findByText('Completed.');
    expect(screen.getByRole('dialog').textContent).toContain('Sweep complete: 12 pages');
  });
  it('requires the typed object name for destructive operations', async () => {
    const destructive = {...operation, operation_id: 'drop', title: 'Drop', confirmation: 'typed_name', tier: 2, execution_host: false};
    render(<Theme><OperationDialog open operation={destructive} targetName="employee" plan={async () => ({plan_id: 'p', plan_digest: 'd', state: 'ready'})}
      apply={async () => ({})} onClose={() => {}} /></Theme>);
    expect(screen.getByRole('button', {name: 'Preview and run'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Type employee to confirm/), {target: {value: 'employee'}});
    expect(screen.getByRole('button', {name: 'Preview and run'})).toBeEnabled();
  });
});

describe('OperationDialog with a confirm-type operation carrying a typed confirmation field', () => {
  it('sends the repeated value as the draft confirmation (Firebird limbo and shadow tasks)', async () => {
    const {loadEngineBundle: load} = require('./familyFixtures');
    const operation = load('firebird').kinds.database.operations.find((op) => op.operation_id === 'commit_limbo_local');
    expect(operation.confirmation).toBe('confirm');
    const plan = jest.fn(async () => ({plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true}));
    render(<Theme><OperationDialog open operation={operation} targetName="employee" plan={plan}
      apply={async () => ({})} onClose={() => {}} /></Theme>);
    fireEvent.change(screen.getByLabelText(/^Local transaction ID/), {target: {value: '42'}});
    fireEvent.change(screen.getByLabelText(/^Repeat the transaction ID/), {target: {value: '42'}});
    fireEvent.change(screen.getByLabelText(/^Confirm database filename or alias/), {target: {value: 'employee'}});
    fireEvent.click(screen.getByRole('checkbox', {name: /Coordinator and participant states reviewed/}));
    fireEvent.click(screen.getByRole('button', {name: 'Preview'}));
    await waitFor(() => expect(plan).toHaveBeenCalled());
    expect(plan.mock.calls[0][0].draft).toMatchObject({transaction_id: '42', confirmation: '42', database_confirmation: 'employee',
      coordinator_reviewed: true});
  });
});

describe('recordFromResource with record_children', () => {
  const {recordFromResource, isChildOf} = require('../../../pgadmin/static/js/cdeadmin_ui/objects/ProviderObjectEditorHost');
  it('folds child resources into the declared grid fields', () => {
    const table = {resource_id: 'table:db:t', resource_kind: 'table', display_name: 't', display_path: ['db', 't'], native: {table_type: 'BASE TABLE'}};
    const resources = [
      table,
      {resource_id: 'column:db:t:id', resource_kind: 'column', display_name: 'id', display_path: ['db', 't', 'id'],
        native: {details: ['int', 'NO', null], navigator_parent_resource_id: 'table:db:t'}},
      {resource_id: 'column:db:u:id', resource_kind: 'column', display_name: 'id', display_path: ['db', 'u', 'id'],
        native: {details: ['int', 'NO', null], navigator_parent_resource_id: 'table:db:u'}},
      {resource_id: 'constraint:db:t:pk', resource_kind: 'constraint', display_name: 'PRIMARY', display_path: ['db', 't', 'PRIMARY'],
        native: {details: ['PRIMARY KEY'], navigator_parent_resource_id: 'table:db:t'}},
    ];
    const form = {record_children: {columns: {resource_kind: 'column'}, primary_key: {resource_kind: 'constraint'}}};
    const record = recordFromResource(table, {form, resources});
    expect(record.columns).toEqual([{name: 'id', details: ['int', 'NO', null], navigator_parent_resource_id: 'table:db:t'}]);
    expect(record.primary_key.map((row) => row.name)).toEqual(['PRIMARY']);
    expect(record.parent).toBe('db');
    expect(isChildOf(resources[2], table)).toBe(false);
  });
});
