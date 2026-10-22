"""Explicit native instance-dump acceptance, independent of restore receipts."""
import hashlib
from pathlib import Path

from ..providers.mysql_family import mysql_instance_acceptance as native
from ..providers.mysql_family import mysql_instance_dumps as dumps
from ..providers.mysql_family import mysql_instance_restores as target_native
from ..providers.mysql_family import mysql_acceptance_lock_owner as lock_owner
from ..providers.mysql_family.mysql_binlog_archives import delegate_credentials, program_identity, rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest
from .mysql_binlog_replay_service import manager as replay_manager
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
    if operation in {'status', 'cancel'} and set(request) == {'job_id'}:
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
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
    client = connection = transport = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider): raise native.BinlogArchiveError('Native MySQL acceptance client is unavailable')
        client = provider.client; route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        connection = client._connect({'route': {**route, 'database': None, 'autocommit': True,
            'read_timeout': selected['timeout_seconds']}})
        target = target_native.capture(connection)
        if operation in {'reconcile', 'acknowledge'}:
            if target['identity'] != record['source']: raise native.BinlogArchiveError('Acceptance reconciliation reached another target or principal')
            observation = {**target, 'native_lock_free': rows(connection, 'SELECT IS_FREE_LOCK(%s) AS free',
                ('cdeadmin:binlog-load:' + target['identity']['server_uuid'],))[0]['free'] == 1,
                'private_server_lock_cleanup': lock_owner.observe(connection, record),
                'scope': 'Current native target state only; independent acceptance is not rerun and earlier results remain unchanged'}
            if operation == 'acknowledge':
                if record.get('recovery_fence_release_confirmed') is not True:
                    raise native.BinlogArchiveError('Private server-lock cleanup must be confirmed before acknowledging this acceptance target')
                return jobs.acknowledge(record, observation, request)
            result = jobs.reconcile(record, observation); result['observation_digest'] = digest(observation); return result
        artifact = dumps.verify(directory, source_identity)
        scopes = native.scopes(directory, artifact)
        if target['identity']['server_uuid'] != selected['target_confirmation'] or target['identity']['server_uuid'] == reference['summary']['source_uuid']:
            raise native.BinlogArchiveError('Confirm a separate native instance acceptance target')
        if scopes['data_requested'] and not target['state']['local_infile']:
            raise native.BinlogArchiveError('Native checksum acceptance requires trusted local_infile on the target')
        workspace = jobs.prepare_scope(owner, endpoint.id)
        program = program_identity(client, route, workspace)
        configuration = digest({'registration': MySQLMonitoringHost._configuration(server), 'root': str(jobs.root),
            'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()})
        if operation == 'review': return jobs.review(owner, endpoint.id, selected,
            {'identity': target['identity'], 'state': {'input_reference': reference, 'target': target, 'scopes': scopes}}, configuration, program)
        transport = InstanceAcceptanceTransport(client, route, delegate_credentials(client, route), connection, directory, source_identity)
        connection = None; admitted = transport; transport = None
        return jobs.start(request, owner, endpoint.id, {'configuration': configuration, 'source': target['identity'], 'program': program}, admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native instance acceptance admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()
