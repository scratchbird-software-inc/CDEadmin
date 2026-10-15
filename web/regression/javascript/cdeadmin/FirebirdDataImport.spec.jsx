import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {TextDecoder} from 'util';
import {Buffer} from 'buffer';
import FirebirdDataImport from 'sources/Dialogs/FirebirdDataImport';
import {withTheme} from '../fake_theme';

const preview = {source_sha256: 'file-digest', order: ['T'], counts: {T: 1},
  operations: [{table: 'T', row: 0, values: {ID: 42}, override_identity: true}],
  catalogs: {T: {resource: {resource_id: 'native-table', resource_kind: 'table', display_name: 'T'}}},
  external_prerequisites: [], identity_requirements: [{table: 'T', columns: ['ID']}]};
const Component = withTheme(FirebirdDataImport);

describe('Firebird data archive import', () => {
  let decoder;
  beforeEach(() => {decoder = global.TextDecoder; global.TextDecoder = TextDecoder;});
  afterEach(() => {global.TextDecoder = decoder;});
  const read = async () => {
    fireEvent.change(screen.getByLabelText('Firebird data archive file'), {target: {files: [
      {name: 'owned.json', size: 2, arrayBuffer: async () => Buffer.from('{}')},
    ]}});
    await screen.findByText('owned.json');
  };
  it('requires review and confirmation, then stages exact identities without committing', async () => {
    const calls = [];
    const post = jest.fn(async request => {
      calls.push(request);
      if(request.action === 'firebird_data_import_plan') return preview;
      if(request.action === 'open_session') return {session_id: 'owned-import'};
      if(request.action === 'visual_admin_validate') return {valid: true};
      if(request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
      if(request.action === 'visual_admin_apply') return {provider_result: {staged_in_provider_session: true}};
      return request.action === 'close_session' ? {session_id: request.session_id, provider_closed: true} :
        {provider_payload: {state: 'idle', in_transaction: false, attachment_live: true}};
    });
    const refresh = jest.fn();
    const view = render(<Component post={post} generation="g" databaseTargetId="target" onCatalogRefresh={refresh} />);
    await read(); expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Preview data import'}));
    await screen.findByText(/preserve ID with OVERRIDING/);
    expect(screen.getByRole('button', {name: 'Stage imported rows'})).toBeDisabled();
    expect(calls.some(item => item.action === 'open_session')).toBe(false);
    fireEvent.click(screen.getByLabelText('I authorize importing these rows into the selected database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage imported rows'}));
    await screen.findByText('1 rows confirmed staged. staged');
    expect(calls.find(item => item.action === 'open_session').session_purpose).toBe('firebird-data-import');
    expect(calls.find(item => item.action === 'visual_admin_plan').request.draft).toEqual({values: {ID: 42}, options: {}, override_identity: true});
    expect(calls.some(item => item.action === 'transaction_action')).toBe(false);
    fireEvent.click(screen.getByRole('button', {name: 'Roll back imported rows'}));
    await waitFor(() => expect(calls.some(item => item.transaction_action === 'rollback' && item.session_id === 'owned-import')).toBe(true));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2));
    expect(calls.some(item => item.transaction_action === 'commit')).toBe(false);
    view.unmount();
    await waitFor(() => expect(calls.some(item => item.action === 'close_session' && item.session_id === 'owned-import')).toBe(true));
  });
  it('does not replay a row after a lost staging response', async () => {
    const post = jest.fn(async request => {
      if(request.action === 'firebird_data_import_plan') return preview;
      if(request.action === 'open_session') return {session_id: 'owned-import'};
      if(request.action === 'visual_admin_validate') return {valid: true};
      if(request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
      if(request.action === 'visual_admin_apply') throw new Error('response lost');
      return {};
    });
    render(<Component post={post} generation="g" databaseTargetId="target" />);
    await read(); fireEvent.click(screen.getByRole('button', {name: 'Preview data import'}));
    await screen.findByText(/preserve ID with OVERRIDING/);
    fireEvent.click(screen.getByLabelText('I authorize importing these rows into the selected database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage imported rows'}));
    await screen.findByText(/Do not retry this preview/);
    expect(screen.getByRole('button', {name: 'Stage imported rows'})).toBeDisabled();
    expect(post.mock.calls.filter(([item]) => item.action === 'visual_admin_apply')).toHaveLength(1);
    expect(post.mock.calls.some(([item]) => item.action === 'transaction_action')).toBe(false);
  });
  it('releases the owned session after an in-flight row settles on unmount', async () => {
    let settle;
    let closes = 0;
    const post = jest.fn(async request => {
      if(request.action === 'firebird_data_import_plan') return preview;
      if(request.action === 'open_session') return {session_id: 'owned-import'};
      if(request.action === 'visual_admin_validate') return {valid: true};
      if(request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
      if(request.action === 'visual_admin_apply') return new Promise(resolve => {settle = resolve;});
      if(request.action === 'close_session' && ++closes === 1) throw new Error('native operation busy');
      return {};
    });
    const view = render(<Component post={post} generation="g" databaseTargetId="target" />);
    await read(); fireEvent.click(screen.getByRole('button', {name: 'Preview data import'}));
    await screen.findByText(/preserve ID with OVERRIDING/);
    fireEvent.click(screen.getByLabelText('I authorize importing these rows into the selected database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage imported rows'}));
    await waitFor(() => expect(settle).toBeDefined());
    view.unmount();
    await act(async () => {settle({provider_result: {staged_in_provider_session: true}});});
    await waitFor(() => expect(closes).toBe(2));
    expect(post.mock.calls.filter(([item]) => item.action === 'visual_admin_apply')).toHaveLength(1);
    expect(post.mock.calls.some(([item]) => item.action === 'transaction_action')).toBe(false);
  });
  it('binds explicit ordering to review and offers allocation handoff only after a transaction decision', async () => {
    const allocation = {resource_id: 'column:T:ID', resource_kind: 'column', display_name: 'ID', display_path: ['T', 'ID']};
    const post = jest.fn(async request => {
      if(request.action === 'firebird_data_import_plan') return {...preview, allocation_targets: [allocation]};
      if(request.action === 'open_session') return {session_id: 'owned-import'};
      if(request.action === 'visual_admin_validate') return {valid: true};
      if(request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
      if(request.action === 'visual_admin_apply') return {provider_result: {staged_in_provider_session: true}};
      return request.action === 'close_session' ? {session_id: request.session_id, provider_closed: true} :
        {provider_payload: {state: 'idle', in_transaction: false, attachment_live: true}};
    });
    const open = jest.fn();
    render(<Component post={post} generation="g" databaseTargetId="target" onOpenAllocation={open} />);
    await read();
    fireEvent.change(screen.getByLabelText('Explicit row order (optional JSON)'), {target: {value: '[{"table":"T","row":0}]'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview data import'}));
    await screen.findByText(/preserve ID with OVERRIDING/);
    expect(post.mock.calls[0][0].request.row_order).toEqual([{table: 'T', row: 0}]);
    fireEvent.click(screen.getByLabelText('I authorize importing these rows into the selected database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage imported rows'}));
    await screen.findByText('1 rows confirmed staged. staged');
    expect(screen.queryByRole('button', {name: 'Review allocation: T / ID'})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Commit imported rows'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Review allocation: T / ID'}));
    await waitFor(() => expect(open).toHaveBeenCalledWith(allocation));
  });

  it('keeps unresolved native finalization pending and withholds allocation handoffs', async () => {
    const post = jest.fn(async request => {
      if(request.action === 'firebird_data_import_plan') return {...preview, allocation_targets: [{resource_id: 'column:T:ID', display_path: ['T', 'ID']}]};
      if(request.action === 'open_session') return {session_id: 'owned-import'};
      if(request.action === 'visual_admin_validate') return {valid: true};
      if(request.action === 'visual_admin_plan') return {state: 'ready', execution_available: true, plan_id: 'p', plan_digest: 'd'};
      if(request.action === 'visual_admin_apply') return {provider_result: {staged_in_provider_session: true}};
      return {provider_payload: {state: 'unknown', attachment_live: true}};
    });
    render(<Component post={post} generation="g" databaseTargetId="target" onOpenAllocation={jest.fn()} />);
    await read(); fireEvent.click(screen.getByRole('button', {name: 'Preview data import'}));
    await screen.findByText(/preserve ID with OVERRIDING/);
    fireEvent.click(screen.getByLabelText('I authorize importing these rows into the selected database'));
    fireEvent.click(screen.getByRole('button', {name: 'Stage imported rows'}));
    await screen.findByText('1 rows confirmed staged. staged');
    fireEvent.click(screen.getByRole('button', {name: 'Commit imported rows'}));
    expect(await screen.findByText(/Native transaction remains active or unavailable/)).toBeVisible();
    expect(screen.getByLabelText('Firebird data archive file')).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Roll back imported rows'})).not.toBeDisabled();
    expect(screen.queryByText('Review allocation: T / ID')).toBeNull();
    expect(post.mock.calls.filter(([request]) => request.transaction_action === 'commit')).toHaveLength(1);
    expect(post.mock.calls.filter(([request]) => request.action === 'visual_admin_apply')).toHaveLength(1);
  });

});
