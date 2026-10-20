import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import DuckDBDatabaseCopy from 'sources/Dialogs/DuckDBDatabaseCopy';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBDatabaseCopy);
const reviewed = {review_id: 'copy-1', review_digest: 'digest-1', session_scope_id: 'original-1',
  state: 'reviewed', phase: 'finished', source_catalog: 'source . " é', destination_catalog: 'target . " é',
  source: 'COPY FROM DATABASE "source . "" é" TO "target . "" é" (SCHEMA);', warnings: []};
const acknowledged = {...reviewed, state: 'acknowledged', native_dispatched: true,
  native_acknowledged: true, rediscovery_verified: true};
const props = post => ({post, databaseTargetId: 'registered-1', sessionId: 'session-1',
  ensureSession: jest.fn().mockResolvedValue('session-1'), onBusyChange: jest.fn(), onBlocked: jest.fn()});
const enter = () => {
  fireEvent.change(screen.getByRole('textbox', {name: 'Copy source catalog'}), {target: {value: reviewed.source_catalog}});
  fireEvent.change(screen.getByRole('textbox', {name: 'Copy destination catalog'}), {target: {value: reviewed.destination_catalog}});
};
const confirm = () => {
  fireEvent.change(screen.getByRole('textbox', {name: 'Exact copy destination confirmation'}), {target: {value: reviewed.destination_catalog}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'I reviewed the native database copy and its transaction effects'}));
};

describe('native DuckDB database copy', () => {
  it('previews typed catalog intent and applies the exact review once', async () => {
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce(acknowledged).mockResolvedValue(acknowledged);
    render(<Component {...props(post)} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByLabelText('Reviewed DuckDB database copy SQL');
    expect(post).toHaveBeenCalledWith({action: 'duckdb_database_copy', database_target_id: 'registered-1', session_id: 'session-1',
      request: {operation: 'review', draft: {source_catalog: reviewed.source_catalog, destination_catalog: reviewed.destination_catalog, mode: 'ALL'}}});
    expect(screen.getByRole('button', {name: 'Apply reviewed database copy once'})).toBeDisabled();
    confirm();fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed database copy once'}));
    await waitFor(() => expect(screen.queryByRole('button', {name: 'Apply reviewed database copy once'})).not.toBeInTheDocument());
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_database_copy', database_target_id: 'registered-1', session_id: 'session-1',
      request: {operation: 'apply', review_id: 'copy-1', review_digest: 'digest-1', confirmation: reviewed.destination_catalog, confirmed: true}});
    fireEvent.click(screen.getByRole('button', {name: 'Read database copy receipt'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith(expect.objectContaining({request: {operation: 'receipt', review_id: 'copy-1'}})));
  });

  it('polls review and copy progress while preserving the original review identity', async () => {
    let dispatched = false;
    const post = jest.fn().mockImplementation(async payload => {
      if(payload.request.operation === 'review') return {...reviewed, state: 'reviewing', phase: 'reading_source'};
      if(payload.request.operation === 'apply') {dispatched = true;return {...reviewed, state: 'applying', phase: 'copying_data'};}
      return dispatched ? acknowledged : reviewed;
    });
    const properties = props(post);render(<Component {...properties} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByText(/Phase: reading_source/);
    await screen.findByRole('textbox', {name: 'Exact copy destination confirmation'});
    confirm();fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed database copy once'}));
    await screen.findByText(/Phase: copying_data/);
    await screen.findByText(/Native database copy: acknowledged/);
    expect(post.mock.calls.filter(([value]) => value.request.operation === 'apply')).toHaveLength(1);
    expect(properties.onBusyChange).toHaveBeenCalledWith(true);
    expect(properties.onBusyChange).toHaveBeenLastCalledWith(false);
  });

  it('recovers a lost apply response by receipt without offering another apply', async () => {
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new Error('owned lost reply')).mockResolvedValue(acknowledged);
    render(<Component {...props(post)} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByRole('textbox', {name: 'Exact copy destination confirmation'});confirm();
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed database copy once'}));
    await screen.findByText('owned lost reply');
    expect(screen.getByRole('button', {name: 'Apply reviewed database copy once'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Review native database copy'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Read database copy receipt'}));
    await screen.findByText(/Native database copy: acknowledged/);
    expect(post.mock.calls.filter(([value]) => value.request.operation === 'apply')).toHaveLength(1);
  });

  it('allows cancelling an active review while mutation controls are blocked', async () => {
    const post = jest.fn().mockResolvedValueOnce({...reviewed, state: 'reviewing', phase: 'reading_source'})
      .mockResolvedValue({...reviewed, state: 'cancelled'});
    const properties = props(post);const rendered = render(<Component {...properties} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByText(/Phase: reading_source/);rendered.rerender(<Component {...properties} disabled />);
    fireEvent.click(screen.getByRole('button', {name: 'Cancel active database copy'}));
    await screen.findByText(/Native database copy: cancelled/);
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({request: {operation: 'cancel', review_id: 'copy-1'}}));
  });

  it('ignores responses from another target and clears a review on session replacement', async () => {
    let resolve;
    const post = jest.fn().mockImplementationOnce(() => new Promise(done => {resolve = done;})).mockResolvedValue(reviewed);
    const properties = props(post);const rendered = render(<Component {...properties} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await waitFor(() => expect(resolve).toBeDefined());
    rendered.rerender(<Component {...properties} databaseTargetId="another" />);
    await act(async () => resolve(reviewed));
    expect(screen.queryByLabelText('Reviewed DuckDB database copy SQL')).not.toBeInTheDocument();
    enter();fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByRole('textbox', {name: 'Exact copy destination confirmation'});
    rendered.rerender(<Component {...properties} databaseTargetId="another" sessionId="replacement" />);
    expect(screen.queryByRole('button', {name: 'Apply reviewed database copy once'})).not.toBeInTheDocument();
    expect(screen.getByText(/original copy session closed or changed/)).toBeInTheDocument();
  });

  it('keeps final receipts readable when native uncertainty blocks the session', async () => {
    const value = {...acknowledged, state: 'unknown_outcome', rediscovery_verified: false, session_reuse_blocked: true};
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValue(value);
    const properties = props(post);render(<Component {...properties} />);enter();
    fireEvent.click(screen.getByRole('button', {name: 'Review native database copy'}));
    await screen.findByRole('textbox', {name: 'Exact copy destination confirmation'});confirm();
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed database copy once'}));
    await screen.findByText(/Native database copy: unknown_outcome/);
    expect(properties.onBlocked).toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Review native database copy'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Read database copy receipt'})).toBeEnabled();
  });
});
