import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import Component from '../../../pgadmin/static/js/Dialogs/MariaDBSchemaChanges';
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/data/PagedDataGrid', () => function NativeGrid() {return <div>Native plan grid</div>;});

it('requires fresh native validation, reviewed digest and maintenance confirmation before apply', async () => {
  const post = jest.fn().mockResolvedValueOnce({ready_for_review: true, native_grammar_validated: true, execution_sha256: 'displayed', operations: []})
    .mockResolvedValueOnce({review_id: 'owned-review', review_digest: 'reviewed', state: 'reviewed'})
    .mockResolvedValueOnce({review_id: 'owned-review', state: 'committed'});
  const mounted = render(<Component post={post} databaseTargetId="owned-target" baseline="captured" source="desired" />);
  expect(screen.getByRole('button', {name: 'Apply reviewed change'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: 'Preview and validate native changes'}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Prepare reviewed change'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Prepare reviewed change'}));
  await waitFor(() => expect(screen.getByRole('checkbox', {name: 'Confirm reviewed native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('checkbox', {name: 'Confirm reviewed native changes'}));
  expect(screen.getByRole('button', {name: 'Apply reviewed change'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', {name: 'Exclusive DDL maintenance window confirmed'}));
  fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed change'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'mariadb_schema_apply', request: {
    database_target_id: 'owned-target', review_id: 'owned-review', review_digest: 'reviewed', confirmed: true, maintenance_window_confirmed: true}}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Apply reviewed change'})).toBeDisabled());
  mounted.rerender(<Component post={post} databaseTargetId="other-target" baseline="other" source="desired" />);
  expect(screen.getByRole('button', {name: 'Prepare reviewed change'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Read receipt'})).toBeDisabled();
});
