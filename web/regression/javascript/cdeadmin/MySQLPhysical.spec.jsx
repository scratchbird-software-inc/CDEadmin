import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLPhysical from 'sources/Dialogs/MySQLPhysical';
import {withTheme} from '../fake_theme';
const Component = withTheme(MySQLPhysical);
const connection = {host: 'host', port: 22, username: 'operator', host_key: 'pinned', authentication: 'private_key', platform: 'posix', python: '/usr/bin/python3'};
const review = {job_id: 'physical-job', review_digest: 'exact', state: 'reviewed', warnings: ['Native RC1 scope'],
  source: {server_uuid: 'native-source'}, remote_review: {}, options: {connection, phase: 'backup',
    workspace: '/private', executable: '/usr/bin/xtrabackup', mysql: '/usr/bin/mysql', sql_host: '127.0.0.1', sql_port: 3306,
    input_job_id: null, parallel: 2, memory_bytes: 268435456, timeout_seconds: 3600, accept_release_candidate: true}};

it('requires release and execution confirmations and keeps SSH secrets out of public review', async () => {
  const post = jest.fn().mockResolvedValue(review); render(<Component post={post} />);
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name: 'Review native physical job'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Physical SSH private key'), {target: {value: 'owned-private-key'}});
  fireEvent.click(screen.getByLabelText('I accept this pinned XtraBackup release candidate for this physical operation.'));
  fireEvent.click(screen.getByRole('button', {name: 'Review native physical job'}));
  await screen.findByLabelText('Native physical review');
  expect(screen.getByLabelText('Native physical review')).not.toHaveTextContent('owned-private-key');
  expect(screen.getByRole('button', {name: 'Start reviewed physical job'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I confirm this exact reviewed physical operation.'));
  expect(screen.getByRole('button', {name: 'Start reviewed physical job'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Delegate the registered database password privately to the pinned SSH host.'));
  post.mockResolvedValue({...review, state: 'unknown'});
  fireEvent.click(screen.getByRole('button', {name: 'Start reviewed physical job'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_start', request: {
    job_id: 'physical-job', review_digest: 'exact', confirmed: true, delegate_database_credentials: true,
    credentials: {private_key: 'owned-private-key'}}}));
  expect(await screen.findByLabelText('Native physical receipt')).not.toHaveTextContent('owned-private-key');
});

it('loads uncertain receipts and observes them without executing again', async () => {
  const unknown = {...review, state: 'unknown', file_verification_confirmed: false};
  const post = jest.fn().mockResolvedValue({jobs: [unknown], offset: 0, limit: 25, more: false});
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button', {name: 'Load physical jobs'}));
  await screen.findByRole('table', {name: 'Native physical jobs'});
  post.mockResolvedValue(unknown);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect physical job physical-job'}));
  await screen.findByLabelText('Native physical receipt');
  fireEvent.change(screen.getByLabelText('Physical SSH private key'), {target: {value: 'renewed-private-key'}});
  post.mockResolvedValue({...unknown, file_verification_confirmed: true, remote_observation: {artifact: {prepared: false}, process_termination_confirmed: true}});
  fireEvent.click(screen.getByRole('button', {name: 'Observe remote physical job'}));
  expect(await screen.findByRole('button', {name: 'Use backup for separate prepare'})).toBeEnabled();
  expect(post.mock.calls.filter(([value]) => value.action === 'mysql_physical_start')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', {name: 'Use backup for separate prepare'}));
  expect(screen.getByLabelText('Physical input job ID')).toHaveValue('physical-job');
});

it('invalidates a review when its native host or input changes', async () => {
  const post = jest.fn().mockResolvedValue(review); render(<Component post={post} />);
  fireEvent.click(screen.getByLabelText('I accept this pinned XtraBackup release candidate for this physical operation.'));
  fireEvent.click(screen.getByRole('button', {name: 'Review native physical job'}));
  await screen.findByLabelText('Native physical review');
  fireEvent.change(screen.getByLabelText('XtraBackup executable'), {target: {value: '/changed/xtrabackup'}});
  expect(screen.queryByLabelText('Native physical review')).not.toBeInTheDocument();
  expect(post.mock.calls.filter(([value]) => value.action === 'mysql_physical_start')).toHaveLength(0);
});

it('derives recovery from verified copy-back and separately confirms native startup and credential delegation', async () => {
  const copied = {...review, state: 'native_returned', options: {...review.options, phase: 'copy_back'}, file_verification_confirmed: true,
    remote_observation: {restored_files: {database_started: false}, process_termination_confirmed: true}};
  const post = jest.fn().mockResolvedValue({jobs: [copied], offset: 0, limit: 25, more: false});
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button', {name: 'Load physical jobs'}));
  await screen.findByRole('table', {name: 'Native physical jobs'});
  post.mockResolvedValue(copied);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect physical job physical-job'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Use copy-back for managed recovery'}));
  expect(screen.getByLabelText('Recovery mysqld executable')).toHaveValue('/usr/sbin/mysqld');
  const recoveryReview = {...review, options: {...review.options, phase: 'recover', input_job_id: 'physical-job', mysqld: '/usr/sbin/mysqld', recovery_gtid_mode: 'ON', recovery_port: 3307}};
  post.mockResolvedValue(recoveryReview);
  fireEvent.click(screen.getByRole('button', {name: 'Review native physical job'}));
  await screen.findByLabelText('Native physical review');
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action: 'mysql_physical_review', request: expect.objectContaining({options: recoveryReview.options})}));
  fireEvent.click(screen.getByLabelText('I confirm this exact reviewed physical operation.'));
  expect(screen.getByRole('button', {name: 'Start reviewed physical job'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Delegate the registered database password privately to the pinned SSH host.'));
  post.mockResolvedValue({...recoveryReview, state: 'remote_running', recovery_running: true, recovery_sql_startup_observed: true,
    remote_observation: {runtime_process_live: true}});
  fireEvent.click(screen.getByRole('button', {name: 'Start reviewed physical job'}));
  expect(await screen.findByRole('button', {name: 'Stop managed recovery instance'})).toBeEnabled();
  expect(screen.getByText(/SQL startup readiness: observed/)).toBeVisible();
});

it('reviews a separate recovery connection and requires both confirmations before registering it', async () => {
  const recovered = {...review, state: 'unknown', options: {...review.options, phase: 'recover', recovery_port: 3307}};
  const post = jest.fn().mockResolvedValue({jobs: [recovered], offset: 0, limit: 25, more: false});
  const registered = jest.fn(); render(<Component post={post} onTargetRegistered={registered} />);
  fireEvent.click(screen.getByRole('button', {name: 'Load physical jobs'}));
  await screen.findByRole('table', {name: 'Native physical jobs'});
  post.mockResolvedValue(recovered);
  fireEvent.click(screen.getByRole('button', {name: 'Inspect physical job physical-job'}));
  await screen.findByLabelText('Native physical receipt');
  fireEvent.change(screen.getByLabelText('Physical SSH private key'), {target: {value: 'private-recovery-key'}});
  const ticket = {job_id: 'connection-review', review_digest: 'connection-exact', state: 'reviewed'};
  post.mockResolvedValue(ticket);
  fireEvent.click(screen.getByRole('button', {name: 'Review recovery connection'}));
  await screen.findByLabelText('Native recovery connection review');
  expect(screen.getByRole('button', {name: 'Attach reviewed recovery connection'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I confirm this separate recovery connection registration.'));
  expect(screen.getByRole('button', {name: 'Attach reviewed recovery connection'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Use the registered database credential for this recovery registration.'));
  const result = {server_id: 42, transport_attached: true}; post.mockResolvedValue({...ticket, result});
  fireEvent.click(screen.getByRole('button', {name: 'Attach reviewed recovery connection'}));
  await waitFor(() => expect(registered).toHaveBeenCalledWith(result));
  expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_connection_connect', request: {
    review_id: ticket.job_id, review_digest: ticket.review_digest, confirmed: true, delegate_database_credentials: true,
    credentials: {private_key: 'private-recovery-key'},
  }});
  expect(screen.getByLabelText('Native recovery connection receipt')).not.toHaveTextContent('private-recovery-key');
  post.mockResolvedValue({...result, transport_attached: false});
  fireEvent.click(screen.getByRole('button', {name: 'Detach recovery transport'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'mysql_physical_connection_detach', request: {server_id: 42}}));
});
