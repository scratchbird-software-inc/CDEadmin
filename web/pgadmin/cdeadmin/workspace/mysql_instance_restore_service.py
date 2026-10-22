"""Owned instance backup inputs and separately authorized native load targets."""
from copy import deepcopy
import hashlib
from pathlib import Path

from ..providers.mysql_family import mysql_instance_restores as native
from ..providers.mysql_family import mysql_instance_dumps as dumps
from ..providers.mysql_family.mysql_binlog_archives import delegate_credentials, program_identity, rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest, identity
from .mysql_binlog_replay_service import manager as replay_manager, source_server
from .mysql_instance_backup_service import manager as backup_manager
from .mysql_instance_restore_jobs import InstanceRestoreJobs, InstanceRestoreTransport
from .mysql_monitoring_host import MySQLMonitoringHost


def manager(service, server):
    from flask import current_app
    replays, owner, endpoint = replay_manager(service, server)
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_instance_restore_jobs', None)
        if jobs is None:
            store = service.operation_bus.store
            root = current_app.config.get('CDEADMIN_MYSQL_INSTANCE_RESTORE_ROOT') or str(store.path.parent / 'mysql-instance-restores')
            jobs = service.mysql_instance_restore_jobs = InstanceRestoreJobs(str(store.path) + '.mysql-instance-restores', root)
            import atexit
            atexit.register(jobs.close)
        jobs.replay_jobs = replays
    return jobs, owner, endpoint


def input_reference(service, owner, request):
    source = source_server(owner, request['source_server_id'])
    jobs, _owner, endpoint, _context = backup_manager(service, source)
    record = jobs.load(identity(request['backup_job_id']), owner, endpoint.id)
    artifact = (record.get('result') or {}).get('artifact')
    if (record['state'] not in {'completed', 'artifact_verified'} or record.get('artifact_removed') or
            record.get('artifact_removal') or record.get('native_process_termination_confirmed') is not True or artifact is None):
        raise native.BinlogArchiveError('Select a retained verified instance backup whose native writer stopped')
    if digest(dumps.verify(jobs.directory(record) / 'archive', record['source'])) != digest(artifact):
        raise native.BinlogArchiveError('Native instance backup files differ from their verified receipt')
    reference = {'server_id': source.id, 'endpoint_id': endpoint.id, 'job_id': record['job_id'],
        'artifact_digest': digest(artifact), 'summary': {key: deepcopy(artifact[key]) for key in
            ('format', 'source_uuid', 'schemas', 'users', 'native_boundary', 'native_consistent', 'native_checksums_included')}}
    return reference, jobs.directory(record) / 'archive', record['source']


def action(service, server, operation, request):
    from mysql.connector import Error as NativeError
    if not isinstance(request, dict): raise native.BinlogArchiveError('Select a native instance restore request')
    jobs, owner, endpoint = manager(service, server)
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation == 'sources':
        from .mysql_binlog_replay_service import action as replay_action
        return replay_action(service, server, 'sources', request)
    if operation == 'backups' and not set(request) - {'source_server_id', 'offset', 'limit'} and 'source_server_id' in request:
        source = source_server(owner, request['source_server_id'])
        backups, _owner, source_endpoint, _context = backup_manager(service, source)
        return backups.list(owner, source_endpoint.id, request.get('offset', 0), request.get('limit', 25))
    if operation in {'status', 'cancel'} and set(request) == {'job_id'}:
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    if operation == 'review' and set(request) == {'source_server_id', 'backup_job_id', 'options'}:
        reference, directory, source_identity = input_reference(service, owner, request)
        selected = None
    elif operation == 'start':
        record = jobs.load(request.get('job_id'), owner, endpoint.id)
        if record['state'] != 'reviewed': return jobs.start(request, owner, endpoint.id, {}, None)
        selected = record['options']; original = record['source_state']['input_reference']
        reference, directory, source_identity = input_reference(service, owner,
            {'source_server_id': original['server_id'], 'backup_job_id': original['job_id']})
        if reference != original: raise native.BinlogArchiveError('Instance restore input reference changed')
    elif operation == 'inspect' and not request:
        selected = record = reference = None
    elif operation in {'reconcile', 'acknowledge'} and set(request) == ({'job_id'} if operation == 'reconcile' else {'job_id', 'target_confirmation', 'observation_digest'}):
        record = jobs.load(request['job_id'], owner, endpoint.id); selected = record['options']; reference = record['source_state']['input_reference']
    else: raise native.BinlogArchiveError('Select a native instance restore action')
    client = connection = transport = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider): raise native.BinlogArchiveError('Native MySQL restore client is unavailable')
        client = provider.client; route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        connection = client._connect({'route': {**route, 'database': None, 'autocommit': True, 'read_timeout': 15}})
        target = native.capture(connection)
        if operation == 'inspect': return {**target, 'native_mutation_dispatched': False}
        if operation in {'reconcile', 'acknowledge'}:
            if target['identity'] != record['source']: raise native.BinlogArchiveError('Instance reconciliation reached another target or principal')
            observed = {**target, 'native_lock_free': rows(connection, 'SELECT IS_FREE_LOCK(%s) AS free',
                ('cdeadmin:binlog-load:' + target['identity']['server_uuid'],))[0]['free'] == 1,
                'scope': 'Current native identity, schema names and GTIDs; not restored-data/definition equality or attribution of concurrent changes'}
            if operation == 'acknowledge': return jobs.acknowledge(record, observed, request)
            result = jobs.reconcile(record, observed); result['observation_digest'] = digest(observed); return result
        workspace = jobs.prepare_scope(owner, endpoint.id)
        if selected is None: selected = native.options(request['options'], {**route, 'tool_workspace': str(workspace)})
        target = native.admission(connection, reference['summary'], selected)
        program = program_identity(client, route, workspace)
        configuration = digest({'registration': MySQLMonitoringHost._configuration(server), 'root': str(jobs.root),
            'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()})
        if operation == 'review': return jobs.review(owner, endpoint.id, selected,
            {'identity': target['identity'], 'state': {'input_reference': reference, 'target': target}}, configuration, program)
        transport = InstanceRestoreTransport(client, route, delegate_credentials(client, route), connection, directory, source_identity)
        connection = None; admitted = transport; transport = None
        return jobs.start(request, owner, endpoint.id, {'configuration': configuration, 'source': target['identity'], 'program': program}, admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native instance restore admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()
