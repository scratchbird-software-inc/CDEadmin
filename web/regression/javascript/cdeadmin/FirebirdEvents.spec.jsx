import {fireEvent, render, screen, waitFor} from '@testing-library/react';
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
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  });
  it('does not fabricate a subscription after lost start delivery', async () => {
    const post = jest.fn().mockRejectedValue(new Error('secret native text'));
    render(<Component post={post} databaseTargetId="db" />);
    fireEvent.change(screen.getByLabelText('Event names (one per line)'), {target: {value: 'EV'}});
    fireEvent.click(screen.getByText('Subscribe / reconnect'));
    expect(await screen.findByText(/lost start response expires/)).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('secret native text')).toBeNull();
  });
});
