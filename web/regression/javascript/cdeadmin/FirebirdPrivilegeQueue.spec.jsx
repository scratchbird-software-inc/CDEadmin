import {fireEvent, render, screen, waitFor, act} from '@testing-library/react';
import FirebirdPrivilegeQueue, {executePrivilegeQueue} from 'sources/Dialogs/FirebirdPrivilegeQueue';
import {withTheme} from '../fake_theme';

const item = (id) => ({title: 'Grant', target: {display_name: 'T'}, databaseTargetId: 'database-a',
  plan: {plan_id: id, plan_digest: 'digest-' + id, command_preview: {statements: [{source: 'GRANT SELECT ON T TO U'}]}}});
const accepted = {provider_result: {accepted: true, staged_in_provider_session: true}};

describe('Firebird privilege statement queue', () => {
  it('submits original database-bound plans in order and retains native staging receipts', async () => {
    const post = jest.fn().mockResolvedValue(accepted);
    const results = await executePrivilegeQueue([item('a'), item('b')], post, () => true);
    expect(post.mock.calls.map(([request]) => request.request)).toEqual([
      {plan_id: 'a', plan_digest: 'digest-a', confirmed: true, database_target_id: 'database-a'},
      {plan_id: 'b', plan_digest: 'digest-b', confirmed: true, database_target_id: 'database-a'},
    ]);
    expect(results.map((entry) => entry.result)).toEqual([accepted, accepted]);
  });
  it('never retries a lost response and records remaining items as unattempted', async () => {
    const post = jest.fn().mockResolvedValueOnce(accepted).mockRejectedValueOnce(new Error('connection lost'));
    const results = await executePrivilegeQueue([item('a'), item('b'), item('c')], post, () => true);
    expect(post).toHaveBeenCalledTimes(2);
    expect(results.map((entry) => entry.status)).toEqual([
      'provider-response-recorded', 'unknown-or-failed', 'not-attempted']);
  });
  it('stops on an unaccepted native result or connection change', async () => {
    const post = jest.fn().mockResolvedValue({provider_result: {accepted: false}});
    await executePrivilegeQueue([item('a'), item('b')], post, () => true);
    expect(post).toHaveBeenCalledTimes(1);
    const current = jest.fn().mockReturnValueOnce(true).mockReturnValue(false);
    post.mockReset().mockResolvedValue(accepted);
    const results = await executePrivilegeQueue([item('a'), item('b')], post, current);
    expect(results[1].status).toBe('not-attempted');
    expect(post).toHaveBeenCalledTimes(1);
  });
  const Component = withTheme(FirebirdPrivilegeQueue);
  it('requires confirmation, consumes a preview and retires the list before dispatch', async () => {
    let resolve;
    const post = jest.fn(() => new Promise((done) => {resolve = done;}));
    const consumePlan = jest.fn(), beginExecution = jest.fn(() => true), endExecution = jest.fn();
    const props = {post, candidate: item('a'), consumePlan, beginExecution, endExecution};
    const {rerender} = render(<Component {...props} />);
    expect(screen.getByText('SR-F-001373')).toBeVisible();
    fireEvent.click(screen.getByText('Add to statement list'));
    expect(consumePlan).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Execute all statements')).toBeDisabled();
    rerender(<Component {...props} candidate={null} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Execute all statements'));
    expect(screen.queryByText('Execute all statements')).toBeNull();
    expect(post).toHaveBeenCalledTimes(1);
    await act(async () => resolve(accepted));
    await waitFor(() => expect(endExecution).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('Privilege queue receipts')).toHaveTextContent('staged_in_provider_session');
  });
  it('invalidates confirmation after removing an item and discards plans on endpoint change', () => {
    const props = {post: jest.fn(), candidate: item('a'), consumePlan: jest.fn(),
      beginExecution: jest.fn(), endExecution: jest.fn()};
    const {rerender} = render(<Component {...props} />);
    fireEvent.click(screen.getByText('Add to statement list'));
    rerender(<Component {...props} candidate={item('b')} />);
    fireEvent.click(screen.getByText('Add to statement list'));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Remove statement 1'));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    rerender(<Component {...props} candidate={null} post={jest.fn()} />);
    expect(screen.queryByText('Execute all statements')).toBeNull();
  });
  it('does not display a late old-connection receipt in a new connection context', async () => {
    let resolve;
    const props = {post: jest.fn(() => new Promise(done => {resolve = done;})), candidate: item('a'),
      consumePlan: jest.fn(), beginExecution: () => true, endExecution: jest.fn()};
    const {rerender} = render(<Component {...props} />);
    fireEvent.click(screen.getByText('Add to statement list'));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Execute all statements'));
    rerender(<Component {...props} candidate={null} post={jest.fn()} />);
    await act(async () => resolve(accepted));
    expect(screen.queryByLabelText('Privilege queue receipts')).toBeNull();
  });

});
