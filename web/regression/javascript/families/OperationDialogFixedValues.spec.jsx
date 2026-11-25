import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import {OperationDialog} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from './familyFixtures';

describe('OperationDialog fixedValues', () => {
  const grant = loadEngineBundle('firebird').kinds.privilege.operations.find((op) => op.operation_id === 'grant');
  const plan = jest.fn(async () => ({plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true}));
  const fixedValues = {privilege_scope: 'object', object_type: 'TABLE', object_name: 'ORDERS'};
  // A fixed value may also be a list (the privileges being granted from a grid row).
  const withPrivileges = {...fixedValues, privileges: ['SELECT']};

  beforeEach(() => plan.mockClear());

  it('does not show a fixed field and never lets the user edit it', () => {
    render(<Theme><OperationDialog open operation={grant} targetName="ORDERS" fixedValues={fixedValues}
      plan={plan} apply={async () => ({})} onClose={() => {}} /></Theme>);
    expect(screen.queryByLabelText(/Exact object name/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Privilege scope/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Grantee name/)).toBeInTheDocument();
  });

  it('sends the fixed values with the draft, and none of the hidden scopes defaults', async () => {
    render(<Theme><OperationDialog open operation={grant} targetName="ORDERS" fixedValues={withPrivileges}
      plan={plan} apply={async () => ({})} onClose={() => {}} /></Theme>);
    fireEvent.change(screen.getByLabelText(/Grantee name/), {target: {value: 'APP_USER'}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Preview'}));
    await waitFor(() => expect(plan).toHaveBeenCalled());
    const {draft} = plan.mock.calls[0][0];
    expect(draft).toMatchObject({privilege_scope: 'object', object_type: 'TABLE', object_name: 'ORDERS', privileges: ['SELECT'],
      principal: 'APP_USER', principal_kind: 'USER'});
    // ddl_class defaults to TABLE but only applies to the ddl_class scope; the
    // provider refuses a draft that mixes scopes.
    expect(draft).not.toHaveProperty('ddl_class');
    expect(draft).not.toHaveProperty('database_privileges');
  });

  it('is unchanged when no values are fixed', async () => {
    render(<Theme><OperationDialog open operation={grant} targetName="x" plan={plan}
      apply={async () => ({})} onClose={() => {}} /></Theme>);
    expect(screen.getByLabelText(/Exact object name/)).toBeInTheDocument();
  });
});
