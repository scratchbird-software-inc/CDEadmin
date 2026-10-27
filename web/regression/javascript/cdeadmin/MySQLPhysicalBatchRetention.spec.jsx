import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLPhysicalBatchRetention from 'sources/Dialogs/MySQLPhysicalBatchRetention';
import {withTheme} from '../fake_theme';
const Component = withTheme(MySQLPhysicalBatchRetention);
const reviewed = {job_id: 'exact-batch', review_digest: 'original-digest', state: 'reviewed',
  plan: {job_ids: ['leaf', 'parent'], retained_full_backup_ids: ['latest']}, items: []};
const confirmation = () => {
  fireEvent.change(screen.getByLabelText('Exact physical retention batch UUID'), {target: {value: 'exact-batch'}});
  fireEvent.click(screen.getByLabelText('I confirm this exact physical retention batch.'));
};
const renderBatch = post => render(<Component post={post} credentials={{private_key: 'ephemeral-key'}} scopeJobId="source-job" busy={false} onBusy={jest.fn()} onChanged={jest.fn()} />);

it('requires the exact reviewed batch and executes its fixed steps without exposing SSH secrets', async () => {
  const post = jest.fn().mockResolvedValueOnce(reviewed).mockResolvedValueOnce({...reviewed, state: 'paused', next_index: 1}).mockResolvedValueOnce({...reviewed, state: 'completed', next_index: 2});
  renderBatch(post); expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Review physical retention policy'}));
  await screen.findByLabelText('Physical retention batch receipt');
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_retention_batch_review', request: {scope_job_id: 'source-job', policy: {retention_days: 30, keep_latest: 2}, credentials: {private_key: 'ephemeral-key'}}});
  expect(screen.getByLabelText('Physical retention batch receipt')).not.toHaveTextContent('ephemeral-key');
  expect(screen.getByRole('button', {name: 'Run reviewed physical retention batch'})).toBeDisabled();
  confirmation(); fireEvent.click(screen.getByRole('button', {name: 'Run reviewed physical retention batch'}));
  await waitFor(() => expect(screen.getByLabelText('Physical retention batch receipt')).toHaveTextContent('completed'));
  expect(post.mock.calls.filter(([value]) => value.action.endsWith('_advance'))).toHaveLength(2);
  expect(post.mock.calls[1][0].request).toEqual({job_id: 'exact-batch', review_digest: 'original-digest', batch_confirmation: 'exact-batch', confirmed: true, credentials: {private_key: 'ephemeral-key'}});
});

it('requires independent inspection and renewed confirmation after an uncertain step', async () => {
  const post = jest.fn().mockResolvedValueOnce(reviewed).mockRejectedValueOnce(new Error('Lost original host reply'))
    .mockResolvedValueOnce({...reviewed, state: 'interrupted', needs_observation: false}).mockResolvedValueOnce({...reviewed, state: 'completed'});
  renderBatch(post); fireEvent.click(screen.getByRole('button', {name: 'Review physical retention policy'}));
  await screen.findByLabelText('Physical retention batch receipt'); confirmation();
  fireEvent.click(screen.getByRole('button', {name: 'Run reviewed physical retention batch'}));
  await screen.findByText('Lost original host reply');
  expect(screen.getByRole('button', {name: 'Run reviewed physical retention batch'})).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect current physical batch step'}));
  await waitFor(() => expect(screen.getByLabelText('Physical retention batch receipt')).toHaveTextContent('interrupted'));
  expect(post).toHaveBeenCalledTimes(3);
  expect(screen.getByRole('button', {name: 'Resume original physical batch step'})).toBeDisabled();
  confirmation(); fireEvent.click(screen.getByRole('button', {name: 'Resume original physical batch step'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action: 'mysql_physical_retention_batch_resume'})));
});

it('pauses after the admitted step and never dispatches the next job', async () => {
  let resolveStep;
  const post = jest.fn().mockResolvedValueOnce(reviewed).mockImplementationOnce(() => new Promise(resolve => {resolveStep = resolve;}));
  renderBatch(post); fireEvent.click(screen.getByRole('button', {name: 'Review physical retention policy'}));
  await screen.findByLabelText('Physical retention batch receipt'); confirmation();
  fireEvent.click(screen.getByRole('button', {name: 'Run reviewed physical retention batch'}));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Pause after current physical removal'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Pause after current physical removal'}));
  resolveStep({...reviewed, state: 'paused', next_index: 1});
  await waitFor(() => expect(screen.getByLabelText('Physical retention batch receipt')).toHaveTextContent('paused'));
  expect(post).toHaveBeenCalledTimes(2);
  expect(screen.getByLabelText('Exact physical retention batch UUID')).toHaveValue('');
});

it('loads persisted batches without dispatch and invalidates unused reviews explicitly', async () => {
  const post = jest.fn().mockResolvedValueOnce({jobs: [reviewed], more: false}).mockResolvedValueOnce(reviewed).mockResolvedValueOnce({...reviewed, state: 'cancelled'});
  renderBatch(post); fireEvent.click(screen.getByRole('button', {name: 'Load physical retention batches'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Inspect physical retention batch exact-batch'}));
  await screen.findByLabelText('Physical retention batch receipt');
  expect(post).toHaveBeenCalledTimes(2);
  confirmation(); fireEvent.click(screen.getByRole('button', {name: 'Invalidate unused physical batch reviews'}));
  await waitFor(() => expect(screen.getByLabelText('Physical retention batch receipt')).toHaveTextContent('cancelled'));
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action: 'mysql_physical_retention_batch_cancel'}));
});

const reviewedSchedule = {job_id: 'exact-schedule', review_digest: 'schedule-digest', state: 'reviewed', ssh_delegation_present: false};
const confirmSchedule = () => {
  fireEvent.change(screen.getByLabelText('Exact physical retention schedule UUID'), {target: {value: 'exact-schedule'}});
  fireEvent.click(screen.getByLabelText('I confirm this exact physical retention schedule.'));
};
it('delegates scheduled SSH access only after exact policy confirmation and a separate delegation choice', async () => {
  const post = jest.fn().mockResolvedValueOnce(reviewedSchedule).mockResolvedValueOnce({...reviewedSchedule, state: 'enabled', ssh_delegation_present: true});
  renderBatch(post); fireEvent.click(screen.getByRole('button', {name: 'Review physical retention schedule'}));
  await screen.findByLabelText('Physical retention schedule receipt');
  expect(post).toHaveBeenCalledTimes(1);
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_retention_schedule_review', request: {scope_job_id: 'source-job', options: {policy: {retention_days: 30, keep_latest: 2}, interval_seconds: 3600, expires_after_days: 30}, credentials: {private_key: 'ephemeral-key'}}});
  confirmSchedule(); expect(screen.getByRole('button', {name: 'Enable reviewed physical retention schedule'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Delegate SSH authentication encrypted for this expiring physical policy.'));
  fireEvent.click(screen.getByRole('button', {name: 'Enable reviewed physical retention schedule'}));
  await waitFor(() => expect(screen.getByLabelText('Physical retention schedule receipt')).toHaveTextContent('enabled'));
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_retention_schedule_enable', request: {job_id: 'exact-schedule', review_digest: 'schedule-digest', confirmed: true, schedule_confirmation: 'exact-schedule', delegate_ssh_credentials: true, credentials: {private_key: 'ephemeral-key'}}});
  expect(screen.getByLabelText('Physical retention schedule receipt')).not.toHaveTextContent('ephemeral-key');
  expect(screen.getByRole('button', {name: 'Disable physical retention schedule'})).toBeDisabled();
});

it('loads a persisted policy without scanning and requires fresh confirmation before disabling it', async () => {
  const enabled = {...reviewedSchedule, state: 'enabled', ssh_delegation_present: true};
  const post = jest.fn().mockResolvedValueOnce({jobs: [enabled]}).mockResolvedValueOnce(enabled).mockResolvedValueOnce({...enabled, state: 'disabled', ssh_delegation_present: false});
  renderBatch(post); fireEvent.click(screen.getByRole('button', {name: 'Load physical retention schedules'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Inspect physical retention schedule exact-schedule'}));
  await screen.findByLabelText('Physical retention schedule receipt'); expect(post).toHaveBeenCalledTimes(2);
  confirmSchedule(); fireEvent.click(screen.getByRole('button', {name: 'Disable physical retention schedule'}));
  await waitFor(() => expect(screen.getByLabelText('Physical retention schedule receipt')).toHaveTextContent('disabled'));
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_retention_schedule_disable', request: {job_id: 'exact-schedule', confirmed: true, schedule_confirmation: 'exact-schedule'}});
});

it('invalidates a schedule review when its age/count policy changes', async () => {
  const post = jest.fn().mockResolvedValue(reviewedSchedule); renderBatch(post);
  fireEvent.click(screen.getByRole('button', {name: 'Review physical retention schedule'}));
  await screen.findByLabelText('Physical retention schedule receipt');
  fireEvent.change(screen.getByLabelText('Minimum full-backup chains'), {target: {value: '3'}});
  expect(screen.queryByLabelText('Physical retention schedule receipt')).not.toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});
