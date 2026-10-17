import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import SQLiteSessionFTS from '../../../pgadmin/static/js/Dialogs/SQLiteSessionFTS';

const resource = {resource_id: 'fts:temp:search', resource_kind: 'fts-table', display_path: ['temp', 'search']};
const catalog = {objects: [{resource_kind: 'fts-table', operations: [
  {operation_id: 'create'}, {operation_id: 'fts_flush'}, {operation_id: 'fts_rebuild'}]}]};

describe('SQLite retained-session native FTS controls', () => {
  it('keeps native requests on their own session and target across busy rerenders', async () => {
    const post = jest.fn(async body => body.action === 'source_catalog' ? {resources: [resource]} :
      {provider_result: {native_fts_maintenance: {native_outcome: 'staged'}}});
    let admin;
    const renderAdministration = props => {admin = props; return <span>Native FTS form</span>;};
    const busy = jest.fn();
    const props = {post, ensureSession: jest.fn(), sessionId: 'session-one', databaseTargetId: 'target-one',
      catalog, onBusyChange: busy, renderAdministration};
    const view = render(<SQLiteSessionFTS {...props} onBlocked={() => {}} />);
    fireEvent.click(screen.getByText('Inspect session FTS tables'));
    await screen.findByText('Native FTS form');
    await waitFor(() => expect(screen.getByText('Inspect session FTS tables')).toBeEnabled());
    expect(admin.catalog.objects[0].operations.map(row => row.operation_id)).toEqual(['fts_flush', 'fts_rebuild']);
    const original = admin.post;
    view.rerender(<SQLiteSessionFTS {...props} onBlocked={() => {}} disabled />);
    expect(admin.post).toBe(original);
    await act(async () => {
      const observed = await original({action: 'resource_inspect', request: {resource_id: resource.resource_id}});
      expect(observed).toEqual(resource);
      await original({action: 'visual_admin_apply', request: {plan_id: 'reviewed', session_id: 'foreign', database_target_id: 'foreign'}});
    });
    expect(post).toHaveBeenLastCalledWith({action: 'visual_admin_apply', request: {
      plan_id: 'reviewed', session_id: 'session-one', database_target_id: 'target-one'}});
    expect(busy).toHaveBeenLastCalledWith(false);
  });

  it('discards stale session catalog replies and rejects obsolete mutation callbacks', async () => {
    let reply;
    const post = jest.fn(() => new Promise(resolve => {reply = resolve;}));
    let admin;
    const props = {post, ensureSession: jest.fn(), databaseTargetId: 'target', catalog,
      onBusyChange: jest.fn(), renderAdministration: value => {admin = value; return <span>Native FTS form</span>;}};
    const view = render(<SQLiteSessionFTS {...props} sessionId="old" />);
    fireEvent.click(screen.getByText('Inspect session FTS tables'));
    view.rerender(<SQLiteSessionFTS {...props} sessionId="new" />);
    await act(async () => {reply({resources: [resource]});});
    expect(screen.queryByText('Native FTS form')).toBeNull();
    fireEvent.click(screen.getByText('Inspect session FTS tables'));
    await act(async () => {reply({resources: [resource]});});
    await screen.findByText('Native FTS form');
    const obsolete = admin.post;
    view.rerender(<SQLiteSessionFTS {...props} sessionId="next" />);
    post.mockClear();
    await expect(obsolete({action: 'visual_admin_apply', request: {plan_id: 'old'}})).rejects.toThrow('session changed');
    expect(post).not.toHaveBeenCalled();
  });

  it('blocks query reuse after an observed uncertain native task outcome', async () => {
    const blocked = jest.fn(); let admin;
    const post = jest.fn(async body => body.action === 'source_catalog' ? {resources: [resource]} :
      {provider_result: {native_fts_maintenance: {native_outcome: 'unknown_outcome'}}});
    render(<SQLiteSessionFTS post={post} ensureSession={jest.fn()} sessionId="native" databaseTargetId="target"
      catalog={catalog} onBusyChange={jest.fn()} onBlocked={blocked}
      renderAdministration={value => {admin = value; return <span>Native FTS form</span>;}} />);
    fireEvent.click(screen.getByText('Inspect session FTS tables'));
    await screen.findByText('Native FTS form');
    await act(async () => {await admin.post({action: 'visual_admin_apply', request: {plan_id: 'reviewed'}});});
    expect(blocked).toHaveBeenCalledTimes(1);
    expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(1);
  });

  it('keeps operation receipts readable after a lost apply reply blocks the query', async () => {
    const blocked = jest.fn(); let admin;
    const item = {operation_id: 'owned-operation', operation_kind: 'fts_flush', unknown_outcome: true};
    const post = jest.fn(async body => {
      if (body.action === 'source_catalog') return {resources: [resource]};
      if (body.action === 'visual_admin_apply') throw new Error('Native response lost');
      if (body.action === 'visual_admin_operation_list') return {items: [item]};
      if (body.action === 'visual_admin_operation_refresh') return {...item, provider_observation: {native_outcome: 'staged'}};
      throw new Error('Unexpected request');
    });
    const props = {post, ensureSession: jest.fn(), sessionId: 'native', databaseTargetId: 'target', catalog,
      onBusyChange: jest.fn(), onBlocked: blocked, renderAdministration: value => {admin = value; return <span>Native FTS form</span>;}};
    const view = render(<SQLiteSessionFTS {...props} />);
    fireEvent.click(screen.getByText('Inspect session FTS tables'));
    await screen.findByText('Native FTS form');
    await act(async () => {await expect(admin.post({action: 'visual_admin_apply', request: {plan_id: 'retired'}})).rejects.toThrow('response lost');});
    expect(blocked).toHaveBeenCalledTimes(1);
    view.rerender(<SQLiteSessionFTS {...props} disabled />);
    fireEvent.click(screen.getByText('Read session FTS operation receipts'));
    await screen.findByText('Observe FTS task fts_flush');
    fireEvent.click(screen.getByText('Observe FTS task fts_flush'));
    await waitFor(() => expect(screen.getByText(/"native_outcome": "staged"/)).toBeInTheDocument());
    expect(post.mock.calls.filter(([body]) => body.action === 'visual_admin_apply')).toHaveLength(1);
  });
});
