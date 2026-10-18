import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import DuckDBAttachment from 'sources/Dialogs/DuckDBAttachment';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBAttachment);

const review = {review_id: 'review-1', review_digest: 'digest-1', action: 'attach', alias: 'analytics',
  state: 'reviewed', session_scope_id: 'native-session-1', source: 'ATTACH ...', warnings: []};
const acknowledged = {...review, state: 'acknowledged', native_dispatched: true,
  native_acknowledged: true, rediscovery_verified: true};
const enter = () => {
  fireEvent.change(screen.getByRole('textbox', {name: 'Native catalog alias'}), {target: {value: 'analytics'}});
  fireEvent.change(screen.getByRole('textbox', {name: 'Absolute DuckDB file path'}), {target: {value: '/owned/analytics.duckdb'}});
};
const confirm = () => {
  fireEvent.change(screen.getByRole('textbox', {name: 'Exact reviewed catalog alias'}), {target: {value: 'analytics'}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'I reviewed the native catalog and file effects'}));
};
const properties = post => ({post, databaseTargetId: 'file-1', sessionId: 'query-1',
  ensureSession: jest.fn().mockResolvedValue('query-1'), onBusyChange: jest.fn(), onBlocked: jest.fn()});

describe('DuckDB original-session attachment workflow', () => {
  it('requires exact confirmation and applies through the original retained session', async () => {
    const post = jest.fn().mockResolvedValueOnce(review).mockResolvedValueOnce(acknowledged);
    render(<Component {...properties(post)} />);
    expect(screen.getByText('SR-F-010007')).toBeInTheDocument();
    enter();fireEvent.click(screen.getByRole('button', {name: 'Review native attachment'}));
    await screen.findByRole('textbox', {name: 'Exact reviewed catalog alias'});
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_attachments', database_target_id: 'file-1', session_id: 'query-1',
      request: {operation: 'review', draft: {action: 'attach', alias: 'analytics', path: '/owned/analytics.duckdb',
        read_only: true, conflict: 'ERROR', create_if_missing: false}}});
    expect(screen.getByRole('button', {name: 'Apply reviewed attachment once'})).toBeDisabled();
    confirm();fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed attachment once'}));
    await screen.findByLabelText('DuckDB attachment receipt');
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_attachments', database_target_id: 'file-1', session_id: 'query-1',
      request: {operation: 'apply', review_id: 'review-1', review_digest: 'digest-1', confirmation: 'analytics', confirmed: true}});
    expect(screen.queryByRole('button', {name: 'Apply reviewed attachment once'})).not.toBeInTheDocument();
  });

  it('requires receipt inspection after a lost apply reply and never resends a mutation', async () => {
    const post = jest.fn().mockResolvedValueOnce(review).mockRejectedValueOnce(new Error('native reply lost')).mockResolvedValueOnce(acknowledged);
    render(<Component {...properties(post)} />);enter();fireEvent.click(screen.getByRole('button', {name: 'Review native attachment'}));
    await screen.findByRole('textbox', {name: 'Exact reviewed catalog alias'});confirm();
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed attachment once'}));await screen.findByText('native reply lost');
    expect(screen.getByRole('button', {name: 'Apply reviewed attachment once'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Review native attachment'})).toBeDisabled();
    expect(screen.getByRole('textbox', {name: 'Native catalog alias'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Read attachment receipt'}));await screen.findByLabelText('DuckDB attachment receipt');
    expect(post.mock.calls.filter(([request]) => request.request.operation === 'apply')).toHaveLength(1);
    expect(post.mock.calls[2][0].request).toEqual({operation: 'receipt', review_id: 'review-1'});
  });

  it('does not send a stale review after the selected database changes while opening a session', async () => {
    let opened;const opening = new Promise(resolve => {opened = resolve;});
    const post = jest.fn();const props = {...properties(post), sessionId: null, ensureSession: jest.fn(() => opening)};
    const rendered = render(<Component {...props} />);enter();fireEvent.click(screen.getByRole('button', {name: 'Review native attachment'}));
    await waitFor(() => expect(props.ensureSession).toHaveBeenCalled());
    rendered.rerender(<Component {...props} databaseTargetId="file-2" />);
    await act(async () => opened('old-session'));
    expect(post).not.toHaveBeenCalled();
  });

  it('keeps an uncertain session blocked while allowing its stored receipt to be read', async () => {
    const unknown = {...review, state: 'unknown_outcome', native_dispatched: true, native_acknowledged: false,
      rediscovery_verified: false, session_reuse_blocked: true};
    const post = jest.fn().mockResolvedValueOnce(review).mockResolvedValueOnce(unknown).mockResolvedValueOnce(unknown);
    const props = properties(post);render(<Component {...props} />);enter();fireEvent.click(screen.getByRole('button', {name: 'Review native attachment'}));
    await screen.findByRole('textbox', {name: 'Exact reviewed catalog alias'});confirm();fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed attachment once'}));
    await screen.findByLabelText('DuckDB attachment receipt');expect(props.onBlocked).toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Review native attachment'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Read attachment receipt'}));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(post.mock.calls.filter(([request]) => request.request.operation === 'apply')).toHaveLength(1);
  });
});
