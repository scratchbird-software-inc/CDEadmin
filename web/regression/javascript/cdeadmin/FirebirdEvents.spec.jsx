import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdEvents from 'sources/Dialogs/FirebirdEvents';
import {withTheme} from '../fake_theme';

describe('Firebird event subscriptions', () => {
  const Component = withTheme(FirebirdEvents);
  it('binds every action to the database and waits for confirmed cleanup before reconnect', async () => {
    const listening = {subscription_id: 's', state: 'listening', counts: {EV: '9007199254740993'}, cleanup_confirmed: false};
    const post = jest.fn().mockResolvedValueOnce(listening).mockResolvedValue({...listening, state: 'stopped', cleanup_confirmed: true});
    const {unmount} = render(<Component post={post} databaseTargetId="db" />);
    fireEvent.change(screen.getByLabelText('Event names (one per line)'), {target: {value: 'EV'}});
    fireEvent.click(screen.getByText('Subscribe / reconnect'));
    expect(await screen.findByText('EV: 9007199254740993')).toBeVisible();
    expect(screen.getByText('Subscribe / reconnect')).toBeDisabled();
    fireEvent.click(screen.getByText('Unsubscribe'));
    expect(await screen.findByText('Attachment release: confirmed')).toBeVisible();
    expect(screen.getByText('Subscribe / reconnect')).not.toBeDisabled();
    expect(post.mock.calls[0][0]).toEqual({action: 'firebird_events', request: {action: 'start', database_target_id: 'db', names: ['EV']}});
    expect(post.mock.calls[1][0].request).toEqual({action: 'stop', database_target_id: 'db', subscription_id: 's'});
    unmount();
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  });
  it('does not fabricate a subscription after lost start delivery', async () => {
    const post = jest.fn().mockRejectedValue(new Error('secret native text'));
    render(<Component post={post} databaseTargetId="db" />);
    fireEvent.change(screen.getByLabelText('Event names (one per line)'), {target: {value: 'EV'}});
    fireEvent.click(screen.getByText('Subscribe / reconnect'));
    expect(await screen.findByText(/lost start response expires/)).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Subscribe / reconnect')).toBeDisabled();
    expect(screen.queryByText('secret native text')).toBeNull();
  });
  it.each(['start', 'poll'])('releases a late %s on its original database after retarget', async action => {
    let complete;
    const pending = new Promise(resolve => {complete = resolve;});
    const listening = {subscription_id: 'old-subscription', state: 'listening', counts: {EV: '7'}, cleanup_confirmed: false};
    const post = jest.fn(payload => {
      if (payload.request.action === action) return pending;
      if (payload.request.action === 'start') return Promise.resolve(listening);
      return Promise.resolve({...listening, state: 'stopped', cleanup_confirmed: true});
    });
    const nextPost = jest.fn();
    const {rerender} = render(<Component post={post} databaseTargetId="original" />);
    fireEvent.change(screen.getByLabelText('Event names (one per line)'), {target: {value: 'EV'}});
    fireEvent.click(screen.getByText('Subscribe / reconnect'));
    if (action === 'poll') {
      await screen.findByText('EV: 7');
      fireEvent.click(screen.getByText('Refresh event counts'));
    }
    rerender(<Component post={nextPost} databaseTargetId="replacement" />);
    expect(screen.getByLabelText('Event names (one per line)')).toHaveValue('');
    await act(async () => {complete(listening);});
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'firebird_events', request: {
      action: 'stop', database_target_id: 'original', subscription_id: 'old-subscription'}}));
    expect(nextPost).not.toHaveBeenCalled();
    expect(screen.queryByText('EV: 7')).not.toBeInTheDocument();
    expect(screen.queryByText(/Subscription old-subscription/)).not.toBeInTheDocument();
  });
  it('does not let a late file read overwrite a replacement database', async () => {
    let complete;
    const file = {size: 2, arrayBuffer: () => new Promise(resolve => {complete = resolve;})};
    const post = jest.fn(), {rerender} = render(<Component post={post} databaseTargetId="original" />);
    fireEvent.change(screen.getByLabelText('Event names file'), {target: {files: [file]}});
    rerender(<Component post={post} databaseTargetId="replacement" />);
    await act(async () => {complete(new TextEncoder().encode('EV').buffer);});
    expect(screen.getByLabelText('Event names (one per line)')).toHaveValue('');
    expect(post).not.toHaveBeenCalled();
  });

});
