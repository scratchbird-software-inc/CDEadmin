import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {VisualAdministration} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import catalog from '../../../pgadmin/cdeadmin/visual_admin/portfolio_catalog.json';

describe('compact Firebird native task forms', () => {
  it('retains every visible option, submits native values and invalidates a changed plan', async () => {
    const post = jest.fn(async ({action}) => action === 'visual_admin_validate' ?
      {valid: true} : {plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true});
    render(<VisualAdministration focused resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="database" initialOperationId="backup_logical"
      catalog={{objects: [{resource_kind: 'database', operations: [{
        operation_id: 'backup_logical', title: 'Backup', target_required: false,
        form_id: 'firebird_backup_logical', form: {...catalog.forms.firebird_backup_logical,
          fields: [...catalog.forms.firebird_backup_logical.fields,
            {field_id: 'future_native', label: 'Future native setting', control: 'text'}]},
      }]}]}} />);
    expect(screen.getByRole('group', {name: 'Additional native options'})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Backup filename on the Firebird server/), {target: {value: 'backup.fbk'}});
    fireEvent.click(screen.getByRole('checkbox', {name: 'Metadata only'}));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Compressed backup'}));
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeEnabled());
    const draft = post.mock.calls.find(([body]) => body.action === 'visual_admin_plan')[0].request.draft;
    expect(draft.backup_flags).toEqual(['METADATA_ONLY', 'ZIP']);
    fireEvent.click(screen.getByRole('checkbox', {name: 'Metadata only'}));
    expect(screen.getByRole('button', {name: 'Apply provider plan'})).toBeDisabled();
  });
  it('requires password confirmation without adding a provider field', async () => {
    const post = jest.fn(async ({action}) => action === 'visual_admin_validate' ?
      {valid: true} : {plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true});
    render(<VisualAdministration focused resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="user" initialOperationId="create"
      catalog={{engine_id: 'firebird', objects: [{resource_kind: 'user', operations: [{
        operation_id: 'create', title: 'Create user', target_required: false,
        form_id: 'create', form: {fields: [
          {field_id: 'password', label: 'New password', control: 'password'},
        ]},
      }]}]}} />);
    fireEvent.change(screen.getByLabelText('New password'), {target: {value: 'test-password'}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled());
    fireEvent.change(screen.getByLabelText('Confirm New password'), {target: {value: 'different'}});
    expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirm New password'), {target: {value: 'test-password'}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Validate and preview'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Validate and preview'}));
    await waitFor(() => expect(post.mock.calls.some(([body]) => body.action === 'visual_admin_plan')).toBe(true));
    expect(post.mock.calls.find(([body]) => body.action === 'visual_admin_plan')[0].request.draft)
      .toEqual({password: 'test-password'});
  });
  it('uses mutually exclusive native shutdown choices', async () => {
    const post = jest.fn(async () => ({valid: true}));
    render(<VisualAdministration focused resources={[]} post={post} setError={jest.fn()}
      initialResourceKind="database" initialOperationId="shutdown_database"
      catalog={{objects: [{resource_kind: 'database', operations: [{
        operation_id: 'shutdown_database', title: 'Shutdown', target_required: false,
        form_id: 'firebird_shutdown_database', form: catalog.forms.firebird_shutdown_database,
      }]}]}} />);
    expect(screen.getByRole('radio', {name: 'Full shutdown'})).toBeChecked();
    fireEvent.click(screen.getByRole('radio', {name: 'Single-user maintenance'}));
    expect(screen.getByRole('radio', {name: 'Full shutdown'})).not.toBeChecked();
    expect(screen.getByRole('radio', {name: 'Single-user maintenance'})).toBeChecked();
  });
});
