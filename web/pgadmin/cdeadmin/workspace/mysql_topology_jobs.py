"""Native topology receipts retain replies independently of later observations."""
from .mysql_binlog_jobs import MySQLBinlogJobs
from .mysql_instance_restore_jobs import InstanceRestoreJobs
from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs
from ..providers.mysql_family import mysql_topology as native


class TopologyJobs(InstanceRestoreJobs):
    operation = 'mysql_native_topology'
    review_warnings = (
        'The selected native method can configure instances, change replication or replace member data when clone recovery is selected. Review every selected instance and native option.',
        'Native operations can commit in stages. Cancellation and process exit do not roll back completed changes. An uncertain operation is never automatically repeated.',
        'Native utility replies, independent topology observations and workload readiness are separate results. Advertised member addresses must be reachable from the execution host.',
        'Operations that can use clone recovery acquire conservative archive holds. Inspect and explicitly retire those holds separately from the topology outcome.',
    )

    def public(self, record):
        result = MySQLBinlogJobs.public(self, record)
        result['target'] = result.pop('source')
        result['native_operation_outcome'] = result.pop('native_load_outcome',
            'unknown' if record.get('native_load_may_have_dispatched') else 'not_dispatched')
        result['selected_instances'] = record['source_state']['members']
        result['reviewed_seed'] = record['source_state']['seed']
        result['remote_database_mutation'] = not native.CALLS[record['options']['operation']]['read_only']
        result['workload_readiness_verified'] = False
        result['server_recovery_clearance_required'] = (record['options']['operation'] in native.RECOVERY_CALLS and
            result['native_operation_outcome'] == 'unknown' and not record.get('target_state_acknowledged_at'))
        result['affected_native_instances'] = self.fence_identities(record)
        result['state'] = {'native_load_returned': 'operation_returned',
            'native_returned_unverified': 'operation_returned_observation_unconfirmed'}.get(result['state'], result['state'])
        return result

    @staticmethod
    def fence_identities(record):
        state = record['source_state']
        return sorted({record['source']['server_uuid'],
            *(member['identity']['server_uuid'] for member in state['members'].values()),
            *state['seed'].get('metadata', {}).get('instance_uuids', [])})

    def claim_fence(self, record):
        claimed = []
        try:
            for native_uuid in self.fence_identities(record):
                scoped = {**record, 'source': {**record['source'], 'server_uuid': native_uuid}}
                MySQLBinlogReplayJobs.claim_fence(self, scoped); claimed.append(scoped)
        except BaseException:
            for scoped in claimed: MySQLBinlogReplayJobs.release_fence(self, scoped)
            raise

    def release_fence(self, record):
        if native.CALLS[record['options']['operation']]['read_only']: return
        for native_uuid in self.fence_identities(record):
            MySQLBinlogReplayJobs.release_fence(self, {**record,
                'source': {**record['source'], 'server_uuid': native_uuid}})

    def review(self, owner, endpoint, selected, capture, configuration, program, continuation=None):
        result = super().review(owner, endpoint, selected, capture, configuration, program, continuation)
        record = self.load(result['job_id'], owner, endpoint)
        if native.CALLS[record['options']['operation']]['read_only']:
            self.update(record, remote_database_mutation=False, warnings=[
                'Native inspection uses private utility connections. It does not execute the selected topology changes or verify workload readiness.'])
        elif native.CALLS[record['options']['operation']].get('account'):
            self.update(record, warnings=[
                'Native account setup creates or updates the selected account on the current primary and adds its required native grants. Existing extra grants remain.',
                'Native account and grant changes can commit in stages. Review a native error or uncertain outcome before repeating the operation.',
                'The account state and visible grants were observed for this review. Concurrent administrators can still change them. Client login and replication catch-up require separate observations.'])
        return self.get(record['job_id'], record['owner'], record['endpoint_id'])

    def start(self, request, owner, endpoint, current, transport):
        record = self.load(request.get('job_id') if isinstance(request, dict) else None, owner, endpoint)
        if native.CALLS[record['options']['operation']]['read_only']:
            return MySQLBinlogJobs.start(self, request, owner, endpoint, current, transport)
        return super().start(request, owner, endpoint, current, transport)

    def acknowledge(self, record, observation, request):
        clearance = observation.get('server_recovery_quiescence') or {}
        if record['options']['operation'] in native.RECOVERY_CALLS and not (
                clearance.get('qualified') is True and clearance.get('idle') is True):
            raise native.BinlogArchiveError(
                'Native clone recovery can continue on the server after utility exit. '
                'Independent server-side completion evidence is required before clearing this target; '
                'the uncertain recovery remains protected.')
        return super().acknowledge(record, observation, request)


class TopologyTransport:
    def __init__(self, client, route, credentials, connection, jobs):
        self.client, self.route, self.credentials, self.connection = client, route, credentials, connection
        self.jobs = jobs

    def close(self):
        try:
            if self.credentials is not None:
                owned = self.credentials; self.credentials = None; owned.close()
        finally:
            if self.connection is not None:
                owned = self.connection; self.connection = None; self.client._discard_failed_session(owned)

    def execute(self, record, directory, cancel, progress, boundary):
        if native.capture(self.connection) != record['source_state']['seed']['observation']:
            raise native.BinlogArchiveError('Native topology seed or metadata changed; prepare another review')
        tickets = []
        def protected_boundary():
            if record['options']['operation'] in native.RECOVERY_CALLS:
                tickets.extend(self.jobs.backup_protection.begin_topology(record))
                self.jobs.update(record, archive_backup_protections=[
                    {'endpoint_id': ticket.sink.endpoint, 'backup_id': ticket.backup_id} for ticket in tickets])
            boundary()
        def progress_observation(value):
            if isinstance(value, dict) and 'native_topology_owner' in value:
                self.jobs.update(record, native_topology_owner=value['native_topology_owner'])
            else: progress(value)
        result = native.run(self.client, self.route, self.credentials, record['options'],
            record['source_state']['seed'], record['source_state']['members'], directory, record['program'],
            cancel=cancel, progress=progress_observation, boundary=protected_boundary)
        result['archive_backup_protections'] = []
        for ticket in tickets:
            try:
                value = ticket.update(state='native_topology_reply_observed',
                    native_topology_returned=(result.get('control') or {}).get('native_load_returned') is True,
                    native_backup_acknowledgement_unchanged=True)
            except Exception as error:
                value = {'backup_id': ticket.backup_id, 'state': 'pending_or_unconfirmed', 'error_type': type(error).__name__}
            result['archive_backup_protections'].append({'endpoint_id': ticket.sink.endpoint, **value})
        try:
            result['target_observation'] = native.capture(self.connection)
            result['native_json_observation'] = native.tag_observation(result['target_observation']['metadata'])
        except Exception as error: result['target_observation'] = {'available': False, 'error_type': type(error).__name__}
        if native.CALLS[record['options']['operation']].get('account'):
            try:
                result['account_observation'] = native.accounts.capture(self.connection,
                    native.parse(record['options']['arguments_json'])[0], native.CALLS[record['options']['operation']]['context'])
            except Exception as error: result['account_observation'] = {'available': False, 'error_type': type(error).__name__}
        return result
