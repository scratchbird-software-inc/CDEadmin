import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLPhysicalBackupSchedule from 'sources/Dialogs/MySQLPhysicalBackupSchedule';
import {withTheme} from '../fake_theme';
const Component = withTheme(MySQLPhysicalBackupSchedule);
const physical = {phase: 'backup', input_job_id: null, accept_release_candidate: true, connection: {host: 'pinned-source'}, workspace: '/private'};
const reviewed = {job_id: 'exact-backup-policy', review_digest: 'original-backup-digest', state: 'reviewed', ssh_delegation_present: false};
const renderPolicy = post => render(<Component post={post} physical={physical} credentials={{private_key: 'transient-SSH'}} busy={false} onBusy={jest.fn()} />);
const confirmation = () => {
  fireEvent.change(screen.getByLabelText('Exact recurring backup policy UUID'), {target: {value: reviewed.job_id}});
  fireEvent.click(screen.getByLabelText('I confirm this exact recurring native backup policy.'));
};

it('requires exact policy and joint SSH/SQL delegation before enabling future backups', async () => {
  const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce({...reviewed, state: 'enabled', ssh_delegation_present: true});
  renderPolicy(post); expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Review recurring physical backup policy'}));
  await screen.findByLabelText('Recurring physical backup policy receipt');
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_backup_schedule_review', request: {options: {physical, drill: null, interval_seconds: 86400, expires_after_days: 30}, credentials: {private_key: 'transient-SSH'}}});
  confirmation(); expect(screen.getByRole('button', {name: 'Enable reviewed recurring backup policy'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Delegate SSH and the registered SQL password encrypted for this expiring backup policy.'));
  fireEvent.click(screen.getByRole('button', {name: 'Enable reviewed recurring backup policy'}));
  await waitFor(() => expect(screen.getByLabelText('Recurring physical backup policy receipt')).toHaveTextContent('enabled'));
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_backup_schedule_enable', request: {job_id: reviewed.job_id, review_digest: reviewed.review_digest, confirmed: true, schedule_confirmation: reviewed.job_id,
    delegate_ssh_credentials: true, delegate_database_credentials: true, credentials: {private_key: 'transient-SSH'}}});
  expect(screen.getByLabelText('Recurring physical backup policy receipt')).not.toHaveTextContent('transient-SSH');
  expect(screen.getByRole('button', {name: 'Disable recurring backup policy'})).toBeDisabled();
});

it('reviews isolated native startup separately and invalidates a changed pipeline', async () => {
  const post = jest.fn().mockResolvedValue(reviewed); renderPolicy(post);
  fireEvent.click(screen.getByLabelText('Run an isolated native startup drill after each backup'));
  expect(screen.getByLabelText('Startup drill mysqld')).toHaveValue('/usr/sbin/mysqld');
  fireEvent.click(screen.getByRole('button', {name: 'Review recurring physical backup policy'}));
  await screen.findByLabelText('Recurring physical backup policy receipt');
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({request: expect.objectContaining({options: expect.objectContaining({drill: {mysqld: '/usr/sbin/mysqld', gtid_mode: 'ON', timeout_seconds: 300}})})}));
  fireEvent.change(screen.getByLabelText('Startup drill lifetime seconds'), {target: {value: '120'}});
  expect(screen.queryByLabelText('Recurring physical backup policy receipt')).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});

it('loads interrupted occurrences without retry and releases protection only through an explicit confirmed action', async () => {
  const policy = {...reviewed, state: 'attention_required'};
  const unknown = {job_id: 'original-occurrence', state: 'interrupted', startup_drill_outcome: 'not_observed', database_recovery_verified: false};
  const post = jest.fn().mockResolvedValueOnce({jobs: [policy]}).mockResolvedValueOnce(policy).mockResolvedValueOnce({jobs: [unknown]}).mockResolvedValueOnce(unknown)
    .mockResolvedValueOnce({...unknown, protection_released: true});
  renderPolicy(post); fireEvent.click(screen.getByRole('button', {name: 'Load recurring physical backup policies'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Inspect recurring backup policy ' + reviewed.job_id}));
  fireEvent.click(await screen.findByRole('button', {name: 'Load native backup occurrences'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Inspect native backup occurrence original-occurrence'}));
  await screen.findByLabelText('Native backup occurrence receipt');
  expect(post).toHaveBeenCalledTimes(4);
  expect(screen.getByRole('button', {name: 'Request due recurring backup'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Reconcile native ends and release workflow protection'})).toBeDisabled();
  confirmation(); fireEvent.click(screen.getByRole('button', {name: 'Reconcile native ends and release workflow protection'}));
  await waitFor(() => expect(screen.getByLabelText('Native backup occurrence receipt')).toHaveTextContent('protection_released'));
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_backup_schedule_release', request: {job_id: reviewed.job_id, occurrence_id: 'original-occurrence', confirmed: true, schedule_confirmation: reviewed.job_id, credentials: {private_key: 'transient-SSH'}}});
  expect(screen.getByLabelText('Native backup occurrence receipt')).toHaveTextContent('interrupted');
});
