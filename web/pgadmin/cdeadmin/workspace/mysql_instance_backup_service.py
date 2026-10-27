"""Registered native full-instance backup admission and offline file receipts."""
from pathlib import Path
import hashlib

from ..providers.mysql_family import mysql_instance_dumps as native
from ..providers.mysql_family.mysql_binlog_archives import program_identity, delegate_credentials
from ..providers.mysql_family.mysql_clone import rows
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import digest
from .mysql_binlog_service import manager as archive_manager
from .mysql_instance_backup_jobs import InstanceBackupJobs, InstanceBackupTransport
from .mysql_monitoring_host import MySQLMonitoringHost


def manager(service, server):
    from flask import current_app
    archives, owner, endpoint, context = archive_manager(service, server)
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_instance_backup_jobs', None)
        if jobs is None:
            store = service.operation_bus.store
            root = current_app.config.get('CDEADMIN_MYSQL_INSTANCE_BACKUP_ROOT') or str(store.path.parent / 'mysql-instance-backups')
            jobs = service.mysql_instance_backup_jobs = InstanceBackupJobs(str(store.path) + '.mysql-instance-backups', root)
            import atexit
            atexit.register(jobs.close)
        jobs.backup_protection = archives.backup_protection
    return jobs, owner, endpoint, context


def action(service, server, operation, request):
    from mysql.connector import Error as NativeError
    if not isinstance(request, dict):
        raise native.BinlogArchiveError('Select a native instance backup request')
    jobs, owner, endpoint, context = manager(service, server)
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status', 'cancel', 'reconcile', 'cleanup_script'} and set(request) == {'job_id'}:
        return {'status': jobs.get, 'cancel': jobs.cancel, 'reconcile': jobs.reconcile, 'cleanup_script': jobs.cleanup_script}[operation](request['job_id'], owner, endpoint.id)
    if operation == 'files' and not set(request) - {'job_id', 'offset', 'limit'} and 'job_id' in request:
        return jobs.files(request['job_id'], owner, endpoint.id, request.get('offset', 0), request.get('limit', 100))
    if operation in {'remove_artifact', 'removal_reconcile', 'pin'}:
        from .mysql_archive_retention import action as retention_action
        return retention_action(service, jobs, owner, endpoint.id, operation, request)
    if operation == 'start':
        reviewed = jobs.load(request.get('job_id'), owner, endpoint.id)
        if reviewed['state'] != 'reviewed':
            return jobs.start(request, owner, endpoint.id, {}, None)
        selected = reviewed['options']
    elif operation=='observe_source_locks' and set(request)=={'job_id'}:
        record=jobs.load(request['job_id'],owner,endpoint.id);selected=record['options']
    elif operation == 'review' and set(request) == {'options'}:
        selected = None
    else:
        raise native.BinlogArchiveError('Select a native instance backup action')
    connection = transport = None; client = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider):
            raise native.BinlogArchiveError('Native MySQL instance backup client is unavailable')
        client = provider.client; route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        workspace = jobs.prepare_scope(owner, endpoint.id)
        if selected is None:
            selected = native.options(request['options'], {**route, 'tool_workspace': str(workspace)})
        connection = client._connect({'route': {**route, 'database': None, 'autocommit': True}})
        source = rows(connection, 'SELECT VERSION() AS version,@@server_uuid AS server_uuid,'
            'CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role')[0]
        if source['version'].split('-')[0] != '9.7.0':
            raise native.BinlogArchiveError('Select native MySQL9.7.0 for an instance backup')
        if operation=='observe_source_locks':
            if source!=record['source']:raise native.BinlogArchiveError('Source lock observation reached another server or principal')
            from ..providers.mysql_family import mysql_acceptance_lock_owner as locks
            observation=locks.observe(connection,record)
            jobs.update(record,source_lock_cleanup_observation={**observation,'original_native_reply_unchanged':True,'automatic_retry':False})
            return jobs.get(record['job_id'],owner,endpoint.id)
        program = program_identity(client, route, workspace)
        configuration = digest({'registration': MySQLMonitoringHost._configuration(server), 'root': str(jobs.root),
            'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
            'system_state_adapter_sha256':hashlib.sha256(Path(native.system_state.__file__).read_bytes()).hexdigest()})
        if operation == 'review':
            return jobs.review(owner, endpoint.id, selected, {'identity': source, 'state': {}}, configuration, program)
        transport = InstanceBackupTransport(client, route, delegate_credentials(client, route), jobs.backup_protection.scoped(owner, endpoint.id))
        if selected.get('system_state_tables'):
            transport.system_connection=connection;connection=None
        admitted = transport; transport = None
        return jobs.start(request, owner, endpoint.id, {'configuration': configuration, 'source': source, 'program': program}, admitted)
    except NativeError as error:
        raise native.BinlogArchiveError('Native instance backup admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None:
            client._discard_failed_session(connection)
        if transport is not None:
            transport.close()
