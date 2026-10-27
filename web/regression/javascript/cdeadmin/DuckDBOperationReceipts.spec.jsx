import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import DuckDBOperationReceipts from 'sources/Dialogs/DuckDBOperationReceipts';
import {withTheme} from '../fake_theme';
const Component = withTheme(DuckDBOperationReceipts);

it('reads archived native outcomes without opening a session or offering replay', async () => {
  const item = {family: 'database_copy', receipt: {review_id: 'owned-copy', state: 'acknowledged', native_acknowledged: true},
    original_session: {state: 'released'}, archived_read_only: true, transaction_finality_inferred: false};
  const post = jest.fn().mockResolvedValue({receipts: [item], total: 1, offset: 0, limit: 25, more: false});
  render(<Component post={post} databaseTargetId="owned-target" />);
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Load saved DuckDB receipts'}));
  const inspect = await screen.findByRole('button', {name: 'Inspect saved DuckDB receipt owned-copy'});
  expect(post).toHaveBeenLastCalledWith({action: 'duckdb_session_receipts', database_target_id: 'owned-target', request: {operation: 'list', offset: 0, limit: 25}});
  post.mockResolvedValue(item); fireEvent.click(inspect);
  await screen.findByLabelText('Saved DuckDB receipt details');
  expect(post).toHaveBeenLastCalledWith({action: 'duckdb_session_receipts', database_target_id: 'owned-target', request: {operation: 'get', review_id: 'owned-copy'}});
  expect(screen.queryByRole('button', {name: /apply|start|repeat/i})).not.toBeInTheDocument();
});

it('ignores an old archive reply after changing database target', async () => {
  let reply;
  const post = jest.fn(() => new Promise(resolve => {reply = resolve;}));
  const mounted = render(<Component post={post} databaseTargetId="old-target" />);
  fireEvent.click(screen.getByRole('button', {name: 'Load saved DuckDB receipts'}));
  mounted.rerender(<Component post={post} databaseTargetId="new-target" />);
  reply({receipts: [], total: 99, offset: 0, limit: 25, more: false});
  await waitFor(() => expect(screen.queryByText(/Recorded receipts: 99/)).not.toBeInTheDocument());
});
