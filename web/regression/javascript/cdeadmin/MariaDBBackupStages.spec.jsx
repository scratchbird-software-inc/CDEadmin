import {fireEvent, render, screen} from '@testing-library/react';
import MariaDBBackupStages from 'sources/Dialogs/MariaDBBackupStages';
import {withTheme} from '../fake_theme';

const Component = withTheme(MariaDBBackupStages);
const reviewed = {review_id: 'stage-1', review_digest: 'digest-1', stage: 'START', state: 'reviewed',
  source: 'SET STATEMENT lock_wait_timeout=5 FOR BACKUP STAGE START', warnings: []};
const acknowledged = {...reviewed, state: 'acknowledged', native_dispatched: true, native_acknowledged: true};
const props = post => ({post, databaseTargetId: 'db-1', sessionId: 'session-1',
  ensureSession: jest.fn().mockResolvedValue('session-1'), onBusyChange: jest.fn(), onBlocked: jest.fn()});
const confirm = () => {
  fireEvent.change(screen.getByRole('textbox', {name: 'Exact native stage confirmation'}), {target: {value: 'START'}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'I reviewed the server-wide backup locks and implicit commit behavior'}));
};

describe('native MariaDB backup stage workflow', () => {
  it('reviews typed native intent and applies the exact stage once', async () => {
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValue(acknowledged);
    render(<Component {...props(post)} />);
    fireEvent.click(screen.getByRole('button', {name: 'Review native backup stage'}));
    await screen.findByLabelText('Reviewed MariaDB backup stage SQL');
    expect(post).toHaveBeenCalledWith({action: 'mariadb_backup_stages', database_target_id: 'db-1', session_id: 'session-1',
      request: {operation: 'review', draft: {stage: 'START', lock_wait_seconds: 5}}});
    expect(screen.getByRole('button', {name: 'Apply reviewed backup stage once'})).toBeDisabled();
    confirm();fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed backup stage once'}));
    await screen.findByText(/Result: acknowledged/);
    expect(post).toHaveBeenLastCalledWith({action: 'mariadb_backup_stages', database_target_id: 'db-1', session_id: 'session-1',
      request: {operation: 'apply', review_id: 'stage-1', review_digest: 'digest-1', confirmation: 'START', confirmed: true}});
    expect(screen.queryByRole('button', {name: 'Apply reviewed backup stage once'})).not.toBeInTheDocument();
  });

  it('polls native execution and leaves cancellation available while the session is busy', async () => {
    const executing = {...reviewed, state: 'executing'};
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce(executing).mockResolvedValue({...reviewed, state: 'cancelled'});
    const properties = props(post);const rendered = render(<Component {...properties} />);
    fireEvent.click(screen.getByRole('button', {name: 'Review native backup stage'}));
    await screen.findByRole('textbox', {name: 'Exact native stage confirmation'});confirm();
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed backup stage once'}));
    await screen.findByText(/Result: executing/);rendered.rerender(<Component {...properties} disabled />);
    fireEvent.click(screen.getByRole('button', {name: 'Cancel active backup stage command'}));
    await screen.findByText(/Result: cancelled/);
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({request: {operation: 'cancel', review_id: 'stage-1'}}));
  });

  it('uses the existing receipt after a lost reply and never retries dispatch', async () => {
    const post = jest.fn().mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new Error('owned native reply lost')).mockResolvedValue(acknowledged);
    render(<Component {...props(post)} />);fireEvent.click(screen.getByRole('button', {name: 'Review native backup stage'}));
    await screen.findByRole('textbox', {name: 'Exact native stage confirmation'});confirm();
    fireEvent.click(screen.getByRole('button', {name: 'Apply reviewed backup stage once'}));
    await screen.findByText('owned native reply lost');
    expect(screen.getByRole('button', {name: 'Apply reviewed backup stage once'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Read backup stage receipt'}));
    await screen.findByText(/Result: acknowledged/);
    expect(post.mock.calls.filter(([value]) => value.request.operation === 'apply')).toHaveLength(1);
  });

  it('clears a review when the original native session changes', async () => {
    const post = jest.fn().mockResolvedValue(reviewed), properties = props(post);
    const rendered = render(<Component {...properties} />);
    fireEvent.click(screen.getByRole('button', {name: 'Review native backup stage'}));
    await screen.findByRole('textbox', {name: 'Exact native stage confirmation'});
    rendered.rerender(<Component {...properties} sessionId="another" />);
    expect(screen.queryByRole('button', {name: 'Apply reviewed backup stage once'})).not.toBeInTheDocument();
    expect(screen.getByText(/native session changed/)).toBeInTheDocument();
  });
});
