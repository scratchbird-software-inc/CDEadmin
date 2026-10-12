import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdRecoveryGroup from '../../../pgadmin/static/js/Dialogs/FirebirdRecoveryGroup';

const review = () => ({
  group_id: 'retained-group', review_digest: 'review-digest', state: 'reviewed', decision: 'commit',
  participants: [1, 2].map(n => ({server_name: `Owned ${n}`, database: `/owned/${n}.fdb`,
    transaction_id: `${100 + n}`, state: 'not_dispatched',
    observation: {transaction_id: `${100 + n}`, participants: []}})),
});

async function load(post) {
  render(<FirebirdRecoveryGroup post={post} />);
  fireEvent.change(screen.getByLabelText('Recorded recovery group ID'), {target: {value: 'retained-group'}});
  fireEvent.click(screen.getByRole('button', {name: 'Read recorded status'}));
  await screen.findByLabelText('Confirm participant 1 database');
}

function confirm() {
  for (const n of [1, 2]) {
    fireEvent.change(screen.getByLabelText(`Confirm participant ${n} database`), {target: {value: `/owned/${n}.fdb`}});
    fireEvent.change(screen.getByLabelText(`Confirm participant ${n} transaction ID`), {target: {value: `${100 + n}`}});
  }
  fireEvent.click(screen.getByRole('checkbox'));
}

describe('Coordinated Firebird recovery', () => {
  let height;
  beforeEach(() => { height = window.innerHeight; window.innerHeight = 1200; });
  afterEach(() => { window.innerHeight = height; });
  it('selects only explicit owned routes and preserves large native IDs as text', async () => {
    const post = jest.fn().mockResolvedValueOnce({endpoints: [{server_id: 8, name: 'Owned server',
      targets: [{target_id: 'owned-target', display_name: 'Main', database: '/owned/main.fdb'}]}]})
      .mockResolvedValueOnce(review());
    render(<FirebirdRecoveryGroup post={post} />);
    fireEvent.click(screen.getByRole('button', {name: 'Load owned Firebird endpoints'}));
    await waitFor(() => expect(screen.getByLabelText('Participant 1 endpoint')).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.mouseDown(screen.getByLabelText('Participant 1 endpoint'));
    fireEvent.click(await screen.findByRole('option', {name: 'Owned server'}));
    fireEvent.mouseDown(screen.getByLabelText('Participant 1 database'));
    fireEvent.click(await screen.findByRole('option', {name: 'Main — /owned/main.fdb'}));
    fireEvent.change(screen.getByLabelText('Participant 1 transaction ID'), {target: {value: '9007199254740993'}});
    fireEvent.click(screen.getByRole('button', {name: 'Inspect and review participants'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'firebird_recovery_preview', request: {
      decision: 'rollback', participants: [{server_id: 8, database_target_id: 'owned-target', transaction_id: '9007199254740993'}],
    }}));
  });

  it('requires every exact confirmation and sends one reviewed decision', async () => {
    const post = jest.fn().mockResolvedValueOnce(review()).mockResolvedValueOnce({...review(), state: 'native_calls_returned'});
    await load(post);
    const apply = screen.getByRole('button', {name: 'Apply reviewed recovery decision'});
    expect(apply).toBeDisabled();
    confirm();
    fireEvent.change(screen.getByLabelText('Confirm participant 2 transaction ID'), {target: {value: '101'}});
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirm participant 2 transaction ID'), {target: {value: '102'}});
    fireEvent.click(apply);
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'firebird_recovery_apply', request: {
      group_id: 'retained-group', review_digest: 'review-digest', decision: 'commit', coordinator_reviewed: true,
      confirmations: [{database: '/owned/1.fdb', transaction_id: '101'}, {database: '/owned/2.fdb', transaction_id: '102'}],
    }}));
    await screen.findByText('Recorded workflow state: native_calls_returned');
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('does not resend after a lost response and reads retained uncertainty', async () => {
    const unknown = {...review(), state: 'needs_review'};
    unknown.participants[0].state = 'unknown_outcome';
    const post = jest.fn().mockResolvedValueOnce(review()).mockRejectedValueOnce(new Error('Response lost'))
      .mockResolvedValueOnce(unknown);
    await load(post);
    confirm();
    const apply = screen.getByRole('button', {name: 'Apply reviewed recovery decision'});
    fireEvent.click(apply);
    await screen.findByText('Response lost');
    expect(apply).toBeDisabled();
    fireEvent.click(apply);
    expect(post).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', {name: 'Read recorded status'}));
    await screen.findByText(/This participant has an uncertain outcome/);
    expect(screen.queryByRole('button', {name: 'Apply reviewed recovery decision'})).not.toBeInTheDocument();
    expect(post).toHaveBeenLastCalledWith({action: 'firebird_recovery_status', request: {group_id: 'retained-group'}});
  });
});
