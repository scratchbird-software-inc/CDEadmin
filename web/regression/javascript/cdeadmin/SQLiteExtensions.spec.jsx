import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import SQLiteExtensions from 'sources/Dialogs/SQLiteExtensions';
import {withTheme} from '../fake_theme';

const Component = withTheme(SQLiteExtensions);
const review = {review_id: 'owned-review', state: 'reviewed', extension: {id: 'native', sha256: 'a'.repeat(64)}};

it('reviews the approved identity and loads only after explicit confirmation', async () => {
  const loaded = {...review, state: 'loaded'};
  const post = jest.fn().mockResolvedValueOnce({loader_available: true, execution_host: 'application-host', extensions: [review.extension]})
    .mockResolvedValueOnce(review).mockResolvedValueOnce(loaded).mockResolvedValueOnce(loaded);
  render(<Component post={post} ensureSession={jest.fn()} sessionId="query-session" databaseTargetId="file" onBusyChange={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect approved extensions'}));
  await screen.findByText(/Execution host: application-host/);
  fireEvent.click(screen.getByRole('button', {name: 'Review native library'}));
  await screen.findByText('Extension receipt owned-review: reviewed');
  expect(screen.getByRole('button', {name: 'Load native library'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', {name: 'Load native library'}));
  await screen.findByText('Extension receipt owned-review: loaded');
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_extensions', session_id: 'query-session', database_target_id: 'file',
    request: {operation: 'load', review_id: 'owned-review', confirmed: true}});
  expect(screen.queryByRole('button', {name: 'Load native library'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Read extension receipt'}));
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_extensions', session_id: 'query-session', database_target_id: 'file',
    request: {operation: 'receipt', review_id: 'owned-review'}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Read extension receipt'})).toBeEnabled());
});

it('preserves review identity after lost load response so receipt can be read', async () => {
  const blocked = jest.fn();
  const post = jest.fn().mockResolvedValueOnce({loader_available: true, extensions: [review.extension]})
    .mockResolvedValueOnce(review).mockRejectedValueOnce(new Error('Lost native response'))
    .mockResolvedValueOnce({...review, state: 'unknown_outcome'});
  render(<Component post={post} ensureSession={jest.fn()} sessionId="session" databaseTargetId="file" onBusyChange={jest.fn()} onBlocked={blocked} />);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect approved extensions'}));
  await screen.findByRole('button', {name: 'Review native library'});
  fireEvent.click(screen.getByRole('button', {name: 'Review native library'}));
  await screen.findByText('Extension receipt owned-review: reviewed');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', {name: 'Load native library'}));
  await screen.findByText('Lost native response');
  fireEvent.click(screen.getByRole('button', {name: 'Read extension receipt'}));
  await screen.findByText('Extension receipt owned-review: unknown_outcome');
  expect(blocked).toHaveBeenCalledTimes(1);
  expect(post.mock.calls.filter(([request]) => request.request.operation === 'load')).toHaveLength(1);
});
