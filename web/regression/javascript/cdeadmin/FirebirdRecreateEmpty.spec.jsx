import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {DatabaseTargetWorkspace} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';

function mount(outcome, initialMode='recreate_empty', approvedCreationRoot='/owned') {
  const forms = Object.fromEntries(['create', 'drop'].map(operation => [operation, {
    form_id: operation, title: operation + ' native database', supported: true,
    fields: operation === 'create' ? [{field_id: 'database_path', label: 'Database path', control: 'text'}] : [],
  }]));
  const post = jest.fn(async payload => {
    if (payload.action === 'visual_admin_validate') return {valid: true};
    if (payload.action === 'visual_admin_plan') return {
      plan_id: 'drop-plan', plan_digest: 'digest', state: 'ready', execution_available: true,
    };
    if (outcome instanceof Error) throw outcome;
    return outcome?.database_targets ? {...outcome, database_targets: {
      ...outcome.database_targets, forms: {form_set_id: 'firebird', lifecycle_resource_kind: 'database', forms},
    }} : outcome;
  });
  const onRecreateEmpty = jest.fn();
  const onTargetCatalogChanged = jest.fn();
  render(<DatabaseTargetWorkspace initialCatalog={{forms: {
    form_set_id: 'firebird', lifecycle_resource_kind: 'database', forms,
  }, targets: [{target_id: 'old', database: '/owned/original.fdb'}]}}
  visualCatalog={{objects: [{resource_kind: 'database', operations:
    ['create', 'drop'].map(operation_id => ({operation_id, confirmation_required: true}))}]}}
  resources={[]} post={post} setError={jest.fn()} initialMode={initialMode}
  initialTargetId="old" focused onRecreateEmpty={onRecreateEmpty} approvedCreationRoot={approvedCreationRoot} onTargetCatalogChanged={onTargetCatalogChanged}
  initialCreatePath={initialMode === 'create' ? '/owned/original.fdb' : ''} />);
  return {post, onRecreateEmpty, onTargetCatalogChanged};
}

async function drop() {
  fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
  await screen.findByRole('checkbox');
  expect(screen.getByRole('button', {name: 'drop native database'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  await act(async () => {
    fireEvent.click(screen.getByRole('button', {name: 'drop native database'}));
  });
}
const success = {workspace_follow_up: [{action: 'remove_dropped_database_registration', state: 'complete'}], database_targets: {targets: []}, provider_result: {driver_observation: {driver_returned: true},
  dropped_endpoint_database_target: {target_id: 'old'}}};

describe('Firebird recreate empty', () => {
  it('requires a durable server creation root before destructive work', () => {
    const {post} = mount({}, 'recreate_empty', '');
    expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText(/Configure an approved database creation root/)).toBeInTheDocument();
  });
  it('requires native success and another explicit action before opening creation', async () => {
    const {post, onRecreateEmpty, onTargetCatalogChanged} = mount(success);
    await drop();
    const next = await screen.findByRole('button', {name: 'Review creation of empty database'});
    expect(onRecreateEmpty).not.toHaveBeenCalled();
    expect(onTargetCatalogChanged).toHaveBeenCalledWith(expect.objectContaining(success.database_targets));
    expect(post.mock.calls.map(([payload]) => payload.action)).toEqual([
      'visual_admin_validate', 'visual_admin_plan', 'visual_admin_apply']);
    expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled();
    fireEvent.click(next);
    expect(onRecreateEmpty).toHaveBeenCalledWith('/owned/original.fdb');
  });
  it.each([
    new Error('Response lost'), {},
    {...success, database_targets: undefined},
    {...success, workspace_follow_up: []},
    {...success, database_targets: {targets: [{target_id: 'old'}]}},
    {...success, provider_result: {...success.provider_result, dropped_endpoint_database_target: {target_id: 'different'}}},
    {...success, workspace_follow_up: [{state: 'failed', action: 'delete', message: 'Registration cleanup failed'}]},
  ])('does not continue or replay on missing proof or failed cleanup %#', async outcome => {
    const {post, onRecreateEmpty} = mount(outcome);
    await drop();
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', {name: 'Review creation of empty database'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'drop native database'})).toBeDisabled();
    expect(onRecreateEmpty).not.toHaveBeenCalled();
    if (!(outcome instanceof Error) && !outcome?.provider_result?.driver_observation?.driver_returned) {
      expect(screen.getByText(/Native drop completion is unconfirmed/)).toBeInTheDocument();
    }
  });
  it('prefills the new filename without submitting creation', async () => {
    const {post} = mount({}, 'create');
    await waitFor(() => expect(screen.getByRole('textbox', {name: 'Database path'})).toHaveValue('/owned/original.fdb'));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText(/creation failure does not restore the original/)).toBeInTheDocument();
  });
});
