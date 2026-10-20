import {act, fireEvent, render, screen} from '@testing-library/react';
import DuckDBSessionSecrets from '../../../pgadmin/static/js/Dialogs/DuckDBSessionSecrets';

const originalHeight = window.innerHeight;
beforeAll(() => {window.innerHeight = 1800;});
afterAll(() => {window.innerHeight = originalHeight;});

const resources = ['memory', 'local_file'].map(storage => ({resource_id: 'secret:' + storage,
  resource_kind: 'secret', display_name: 'same name', display_path: ['same name'],
  native: {storage, persistent: storage === 'local_file'}}));
const catalog = {objects: [{resource_kind: 'secret', operations: [{operation_id: 'create'}, {operation_id: 'drop'}]},
  {resource_kind: 'table', operations: [{operation_id: 'create'}]}]};

describe('DuckDB original-session secret controls', () => {
  it('offers creation from an empty native catalog and binds every visual request to the original handle', async () => {
    let admin;
    const post = jest.fn(async body => body.action === 'source_catalog' ? {resources: []} : {accepted: true});
    const props = {post, ensureSession: jest.fn(), sessionId: 'owned', databaseTargetId: 'target', catalog,
      onBusyChange: jest.fn(), renderAdministration: value => {admin = value; return <span>Native secret form</span>;}};
    const view = render(<DuckDBSessionSecrets {...props} />);
    fireEvent.click(screen.getByText('Inspect session secrets'));
    await screen.findByText('Native secret form');
    expect(admin.initialOperationId).toBe('create');
    expect(admin.catalog.objects.map(row => row.resource_kind)).toEqual(['secret']);
    const original = admin.post;
    view.rerender(<DuckDBSessionSecrets {...props} disabled onBlocked={() => {}} />);
    expect(admin.post).toBe(original);
    await act(async () => {await original({action: 'visual_admin_apply', request: {
      plan_id: 'review', session_id: 'foreign', database_target_id: 'foreign'}});});
    expect(post).toHaveBeenLastCalledWith({action: 'visual_admin_apply', request: {
      plan_id: 'review', session_id: 'owned', database_target_id: 'target'}});
  });

  it('shows separate same-name storage targets and inspects only an exact current identity', async () => {
    let admin;
    const post = jest.fn(async () => ({resources}));
    render(<DuckDBSessionSecrets post={post} ensureSession={jest.fn()} sessionId="owned" databaseTargetId="target"
      catalog={catalog} onBusyChange={jest.fn()} renderAdministration={value => {admin = value; return <span>Native secret form</span>;}} />);
    fireEvent.click(screen.getByText('Inspect session secrets'));
    await screen.findByText('Native secret form');
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Session secret storage target'}));
    expect(screen.getByRole('option', {name: 'same name / memory / temporary'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', {name: 'same name / local_file / persistent'}));
    expect(admin.selectedResource.resource_id).toBe('secret:local_file');
    expect(admin.resources).toEqual([resources[1]]);
    await act(async () => {expect(await admin.post({action: 'resource_inspect', request: {resource_id: 'secret:local_file'}})).toEqual(resources[1]);});
    post.mockResolvedValueOnce({resources: [resources[0]]});
    await act(async () => {await expect(admin.post({action: 'resource_inspect', request: {resource_id: 'secret:local_file'}})).rejects.toThrow('no longer available');});
  });

  it('discards a stale native catalog and refuses an obsolete mutation callback before dispatch', async () => {
    let reply, admin;
    const post = jest.fn(() => new Promise(resolve => {reply = resolve;}));
    const props = {post, ensureSession: jest.fn(), databaseTargetId: 'target', catalog,
      onBusyChange: jest.fn(), renderAdministration: value => {admin = value; return <span>Native secret form</span>;}};
    const view = render(<DuckDBSessionSecrets {...props} sessionId="old" />);
    fireEvent.click(screen.getByText('Inspect session secrets'));
    view.rerender(<DuckDBSessionSecrets {...props} sessionId="new" />);
    await act(async () => {reply({resources});});
    expect(screen.queryByText('Native secret form')).toBeNull();
    fireEvent.click(screen.getByText('Inspect session secrets'));
    await act(async () => {reply({resources});});
    const obsolete = admin.post;
    view.rerender(<DuckDBSessionSecrets {...props} sessionId="next" />);
    post.mockClear();
    await expect(obsolete({action: 'visual_admin_apply', request: {plan_id: 'old'}})).rejects.toThrow('session changed');
    expect(post).not.toHaveBeenCalled();
  });

  it('blocks reuse on a lost apply reply while retaining read-only receipt access', async () => {
    let admin;
    const onBlocked = jest.fn();
    const post = jest.fn(async body => {
      if (body.action === 'source_catalog') return {resources};
      if (body.action === 'visual_admin_apply') throw new Error('Response lost');
      return {items: [{resource_kind: 'secret', operation_id: 'owned-receipt'}, {resource_kind: 'table'}]};
    });
    const props = {post, ensureSession: jest.fn(), sessionId: 'owned', databaseTargetId: 'target', catalog,
      onBusyChange: jest.fn(), onBlocked, renderAdministration: value => {admin = value; return <span>Native secret form</span>;}};
    const view = render(<DuckDBSessionSecrets {...props} />);
    fireEvent.click(screen.getByText('Inspect session secrets'));
    await screen.findByText('Native secret form');
    await act(async () => {await expect(admin.post({action: 'visual_admin_apply', request: {plan_id: 'retired'}})).rejects.toThrow('Response lost');});
    expect(onBlocked).toHaveBeenCalledTimes(1);
    view.rerender(<DuckDBSessionSecrets {...props} disabled />);
    fireEvent.click(screen.getByText('Read session secret operation receipts'));
    await screen.findByText(/owned-receipt/);
    expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(1);
    expect(screen.queryByText(/"resource_kind": "table"/)).toBeNull();
  });
});
