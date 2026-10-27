"""Explicit native instance-dump acceptance, independent of restore receipts."""
import hashlib
from copy import deepcopy
from pathlib import Path

from ..providers.mysql_family import mysql_instance_acceptance as native
from ..providers.mysql_family import mysql_instance_dumps as dumps
from ..providers.mysql_family import mysql_instance_restores as target_native
from ..providers.mysql_family import mysql_acceptance_lock_owner as lock_owner
from ..providers.mysql_family.mysql_binlog_archives import delegate_credentials, program_identity, rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest
from .mysql_binlog_replay_service import manager as replay_manager, principal_sessions, principal_work, release_observed_reservation
from .mysql_instance_restore_service import input_reference
from .mysql_instance_acceptance_jobs import InstanceAcceptanceJobs, InstanceAcceptanceTransport
from .mysql_monitoring_host import MySQLMonitoringHost


def manager(service, server):
    from flask import current_app
    replays, owner, endpoint = replay_manager(service, server)
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_instance_acceptance_jobs', None)
        if jobs is None:
            store = service.operation_bus.store
            root = current_app.config.get('CDEADMIN_MYSQL_INSTANCE_ACCEPTANCE_ROOT') or str(store.path.parent / 'mysql-instance-acceptance')
            jobs = service.mysql_instance_acceptance_jobs = InstanceAcceptanceJobs(str(store.path) + '.mysql-instance-acceptance', root)
            import atexit
            atexit.register(jobs.close)
        jobs.replay_jobs = replays
    return jobs, owner, endpoint


def action(service, server, operation, request):
    from mysql.connector import Error as NativeError
    if not isinstance(request, dict): raise native.BinlogArchiveError('Select an independent instance acceptance request')
    jobs, owner, endpoint = manager(service, server)
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status', 'cancel', 'observe_utilities'} and set(request) == {'job_id'}:
        if operation == 'status': return jobs.get(request['job_id'], owner, endpoint.id)
        record = jobs.load(request['job_id'], owner, endpoint.id)
        if operation == 'cancel': jobs.cancel(request['job_id'], owner, endpoint.id)
        else: jobs.inspect_utilities(record)
        return release_observed_reservation(jobs, jobs.load(record['job_id'], owner, endpoint.id))
    if operation == 'review' and set(request) == {'source_server_id', 'backup_job_id', 'options'}:
        reference, directory, source_identity = input_reference(service, owner, request)
        selected = native.options(request['options'])
    elif operation == 'start':
        record = jobs.load(request.get('job_id'), owner, endpoint.id)
        if record['state'] != 'reviewed': return jobs.start(request, owner, endpoint.id, {}, None)
        selected = record['options']; original = record['source_state']['input_reference']
        reference, directory, source_identity = input_reference(service, owner,
            {'source_server_id': original['server_id'], 'backup_job_id': original['job_id']})
        if reference != original: raise native.BinlogArchiveError('Independent acceptance input reference changed')
    elif operation in {'reconcile', 'acknowledge'} and set(request) == ({'job_id'} if operation == 'reconcile' else {'job_id', 'target_confirmation', 'observation_digest'}):
        record = jobs.load(request['job_id'], owner, endpoint.id); selected = record['options']
    else: raise native.BinlogArchiveError('Select an independent instance acceptance action')
    client = connection = transport = utility = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider): raise native.BinlogArchiveError('Native MySQL acceptance client is unavailable')
        client = provider.client; route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        binding = route.get('mysql_recovery_binding')
        if operation == 'start' and record['source_state'].get('recovery_binding') != binding:
            raise native.BinlogArchiveError('Recovery binding changed after acceptance review')
        if binding and operation in {'review', 'start'}:
            from ..providers.mysql_family.mysql_recovery_bridge import admit_replay_utility
            utility = admit_replay_utility(route, family='acceptance'); route = utility.route
        connection = client._connect({'route': {**route, 'database': None, 'autocommit': True,
            'read_timeout': selected['timeout_seconds']}})
        target = target_native.capture(connection)
        if operation in {'reconcile', 'acknowledge'}:
            if target['identity'] != record['source']: raise native.BinlogArchiveError('Acceptance reconciliation reached another target or principal')
            if operation == 'reconcile':
                jobs.observe_utility(record)
                record = jobs.load(record['job_id'], owner, endpoint.id)
            observation = {**target, 'native_lock_free': rows(connection, 'SELECT IS_FREE_LOCK(%s) AS free',
                ('cdeadmin:binlog-load:' + target['identity']['server_uuid'],))[0]['free'] == 1,
                'private_server_lock_cleanup': lock_owner.observe(connection, record),
                'scope': 'Current native target state only; independent acceptance is not rerun and earlier results remain unchanged'}
            if record['source_state'].get('recovery_binding'):
                observation.update(principal_work(connection, record['source_state'].get('native_login')))
            release_observed_reservation(jobs, jobs.load(record['job_id'], owner, endpoint.id))
            if operation == 'acknowledge':
                if record.get('recovery_fence_release_confirmed') is not True:
                    raise native.BinlogArchiveError('Private server-lock cleanup must be confirmed before acknowledging this acceptance target')
                return jobs.acknowledge(record, observation, request)
            result = jobs.reconcile(record, observation); result['observation_digest'] = digest(observation); return result
        artifact = dumps.verify(directory, source_identity)
        scopes = native.scopes(directory, artifact)
        recovery = None
        if binding:
            from .mysql_recovery_connections import marker
            from .mysql_physical_service import manager as physical_manager
            original = marker(server)
            if original is None or original['binding'] != binding: raise native.BinlogArchiveError('Recovery registration differs from its original binding')
            physical, _, _ = physical_manager(service, server)
            base = physical.load(original['source_job_id'], owner, original['source_endpoint_id'])
            if base['options']['phase'] != 'recover' or base['source']['server_uuid'] != reference['summary']['source_uuid']:
                raise native.BinlogArchiveError('Select an expected native dump from this physical recovery source')
            recovery = {'job_id': base['job_id'], 'endpoint_id': base['endpoint_id'], 'review_digest': base['review_digest'],
                'copy_back_job_id': base['options']['input_job_id'], 'source_uuid': base['source']['server_uuid'],
                'recovery_mode': binding['recovery_mode'], 'expected_boundary': artifact['native_boundary'],
                'scope': 'Selected expected dump surfaces on the original managed recovery instance; production cutover is separate'}
            if operation == 'start' and record['source_state'].get('physical_recovery') != recovery:
                raise native.BinlogArchiveError('Physical recovery acceptance reference changed after review')
        if target['identity']['server_uuid'] != selected['target_confirmation'] or target['identity']['server_uuid'] == reference['summary']['source_uuid']:
            raise native.BinlogArchiveError('Confirm a separate native instance acceptance target')
        if scopes['data_requested'] and not target['state']['local_infile']:
            raise native.BinlogArchiveError('Native checksum acceptance requires trusted local_infile on the target')
        workspace = jobs.prepare_scope(owner, endpoint.id)
        program = program_identity(client, route, workspace)
        configuration = digest({'registration': MySQLMonitoringHost._configuration(server), 'root': str(jobs.root),
            'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
            'system_state_adapter_sha256':hashlib.sha256(Path(native.system_state.__file__).read_bytes()).hexdigest()})
        if operation == 'review': return jobs.review(owner, endpoint.id, selected,
            {'identity': target['identity'], 'state': {'input_reference': reference, 'target': target, 'scopes': scopes,
                **({'recovery_binding': deepcopy(binding), 'native_login': principal_sessions(connection)[1], 'physical_recovery': recovery} if binding else {})}}, configuration, program)
        transport = InstanceAcceptanceTransport(client, route, delegate_credentials(client, route), connection, directory, source_identity)
        connection = None; transport.recovery_utility = utility; utility = None
        admitted = transport; transport = None
        return jobs.start(request, owner, endpoint.id, {'configuration': configuration, 'source': target['identity'], 'program': program}, admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native instance acceptance admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()
        if utility is not None: utility.close()
