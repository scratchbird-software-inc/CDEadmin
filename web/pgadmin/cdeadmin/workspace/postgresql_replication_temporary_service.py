"""Authenticated original-backend replication slots without SQL admission."""
import hashlib
import os
from pathlib import Path
import time

from ..operations.store import JsonOperationStore
from ..providers.postgresql.replication_admission import registered
from ..providers.postgresql.replication_temporary_slots import TemporarySlotError, options
from .mysql_binlog_jobs import digest
from .postgresql_monitoring_host import PostgreSQLMonitoringHost
from .postgresql_continuity_service import artifact_context
from .postgresql_replication_temporary_jobs import (
    ReplicationTemporaryResources, ReplicationTemporaryTransport, program,
)
from .postgresql_temporary_slot_service import authorize


def target(value):
    prefix = 'postgresql-replication-database:'
    try:
        if not isinstance(value, str) or not value.startswith(prefix) or len(value) > 1024:
            raise ValueError
        raw = bytes.fromhex(value[len(prefix):])
        database = raw.decode('utf8')
        if not database or '\0' in database or raw.hex() != value[len(prefix):]:
            raise ValueError
    except (ValueError, UnicodeError):
        raise TemporarySlotError('Select the exact registered native replication database identity') from None
    return value


def source_identity(source):
    keys = ('system_identifier', 'timeline', 'server_version', 'authenticated_principal',
            'database', 'database_target_id', 'admission_interface', 'ssh_peer', 'host', 'port')
    result = {key: source[key] for key in keys if key in source}
    target(result.get('database_target_id'))
    if result.get('admission_interface') != 'logical-replication':
        raise TemporarySlotError('Native database replication admission is required')
    result.update(sql_admission_performed=False, slot_catalog_observed=False)
    return result


def manager(service, server, database_target):
    from flask import current_app
    owner, endpoint = authorize(service, server)
    selected = target(database_target)
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise TemporarySlotError('Temporary replication resources require durable application storage')
    key = hashlib.sha256((endpoint + '\0' + selected).encode('utf8')).hexdigest()
    with service._semantic_lock:
        managers = getattr(service, 'postgresql_replication_temporary_resources', None)
        if managers is None:
            managers = service.postgresql_replication_temporary_resources = {}
        jobs = managers.get(key)
        if jobs is None:
            root = current_app.config.get('CDEADMIN_POSTGRESQL_REPLICATION_TEMPORARY_SLOT_ROOT') or str(store.path.parent / 'postgresql-replication-temporary-slots')
            jobs = managers[key] = ReplicationTemporaryResources(
                str(store.path) + '.postgresql-replication-temporary-slots.' + key, Path(root) / key)
            import atexit
            atexit.register(jobs.close)
    return jobs, owner, endpoint


def action(service, server, operation, request):
    from flask import current_app
    owner, endpoint = authorize(service, server)
    if not isinstance(request, dict):
        raise TemporarySlotError('Select a native temporary replication resource request')
    fields = dict(request)
    database_target = fields.pop('database_target_id', None)
    if operation in {'scope', 'review', 'start'}:
        allowed = {'replication_access'}
        if operation == 'review':
            allowed.add('options')
        if operation == 'start':
            allowed.update(('job_id', 'review_digest', 'confirmed'))
        if set(fields) - allowed or not isinstance(fields.get('replication_access', {}), dict):
            raise TemporarySlotError('Select registered replication credentials and exact resource options')
        transport = None
        try:
            if operation == 'start':
                jobs, owner, endpoint = manager(service, server, database_target)
                reviewed = jobs.load(fields.get('job_id'), owner, endpoint)
                if reviewed['state'] != 'reviewed':
                    return jobs.start({key: value for key, value in fields.items() if key != 'replication_access'}, owner, endpoint, {}, None)
                selected = reviewed['options']
            elif operation == 'review':
                selected = fields.get('options')
                if not isinstance(selected, dict) or set(selected) != {'max_lifetime_seconds'}:
                    raise TemporarySlotError('Review the exact replication resource lifetime')
            else:
                selected = None
            if selected is not None:
                lifetime = selected['max_lifetime_seconds']
                limit = current_app.config.get('CDEADMIN_POSTGRESQL_TEMPORARY_SLOT_MAX_LIFETIME_SECONDS')
                if lifetime is not None and (type(lifetime) is not int or not 1 <= lifetime <= 2147483647):
                    raise TemporarySlotError('Select a positive native resource lifetime or no deadline')
                if limit is not None and (type(limit) is not int or limit < 1 or lifetime is None or lifetime > limit):
                    raise TemporarySlotError('Application policy requires a bounded replication resource lifetime')
                from psycopg._capabilities import capabilities
                if not capabilities.has_cancel_safe():
                    raise TemporarySlotError('Replication resource cancellation requires libpq17 or later')
            source, transport = registered(server, fields.get('replication_access', {}), logical=True)
            source = source_identity(source)
            source['provider_isolation_key'] = list(artifact_context(server).isolation_key)
            if database_target is not None and target(database_target) != source['database_target_id']:
                raise TemporarySlotError('The registered replication database changed')
            if operation == 'scope':
                return {'database_target_id': source['database_target_id'], 'source': source,
                        'sql_admission_performed': False}
            jobs, owner, endpoint = manager(service, server, source['database_target_id'])
            configuration = digest({'registration': PostgreSQLMonitoringHost._configuration(server),
                'database_target_id': source['database_target_id'], 'root': str(jobs.root), 'lifetime_limit': limit})
            if operation == 'review':
                return jobs.review(owner, endpoint, selected, {'identity': source, 'state': {}}, configuration, program())
            admitted = transport
            transport = None
            return jobs.start({key: value for key, value in fields.items() if key != 'replication_access'}, owner, endpoint,
                {'source': source, 'configuration': configuration, 'program': program()}, ReplicationTemporaryTransport(admitted))
        finally:
            if transport is not None:
                transport.close()
    jobs, owner, endpoint = manager(service, server, database_target)
    if operation == 'list':
        if set(fields) - {'offset', 'limit'}:
            raise TemporarySlotError('Select a bounded retained replication resource page')
        return jobs.list(owner, endpoint, **fields)
    if operation == 'status':
        if set(fields) != {'job_id'}:
            raise TemporarySlotError('Select one original replication resource')
        return jobs.get(fields['job_id'], owner, endpoint)
    if operation == 'release':
        if set(fields) != {'job_id', 'confirmation'} or fields['confirmation'] != fields['job_id']:
            raise TemporarySlotError('Confirm release of this replication backend and its temporary slots/snapshot')
        return jobs.cancel(fields['job_id'], owner, endpoint)
    resource = jobs.load(fields.get('resource_id'), owner, endpoint)
    commands = jobs.commands(resource)
    remaining = {key: value for key, value in fields.items() if key != 'resource_id'}
    if operation in {'stream_preview', 'stream_reconcile', 'stream_remove', 'copy_preview', 'copy_reconcile', 'copy_remove'}:
        copy = operation.startswith('copy_')
        if copy:
            from . import postgresql_snapshot_copy as stream
        else:
            from . import postgresql_replication_stream as stream
        suffix = operation.split('_', 1)[1]
        allowed = {'job_id', 'offset', 'length' if copy else 'limit'} if suffix == 'preview' else {'job_id', 'confirmation'} if suffix == 'remove' else {'job_id'}
        if set(remaining) - allowed or 'job_id' not in remaining:
            raise TemporarySlotError('Select one owned native replication capture')
        child = commands.load(remaining['job_id'], owner, endpoint)
        if child['options']['operation'] != ('snapshot_copy' if copy else 'logical_stream'):
            raise TemporarySlotError('Select an original-backend capture of this native kind')
        if suffix == 'preview':
            return stream.preview(commands, child, remaining)
        if suffix == 'reconcile':
            return stream.reconcile(commands, child)
        if set(remaining) != {'job_id', 'confirmation'} or remaining['confirmation'] != child['job_id']:
            raise TemporarySlotError('Confirm removal of this owned native replication capture')
        with stream.artifact_lock(commands, child) as current:
            if current.get('artifact_removed'):
                return commands.public(commands.observed(current))
            if stream.commands_running(commands, current):
                raise TemporarySlotError('Wait for the original replication writer to stop')
            with stream.payload(commands, current) as source:
                before = stream.file_identity(os.fstat(source.fileno()))
            path = commands.directory(current) / current['snapshot_copy_artifact' if copy else 'protocol_stream_artifact']['filename']
            if stream.file_identity(path.lstat()) != before:
                raise TemporarySlotError('Native replication bytes changed before removal')
            path.unlink()
            commands.update(current, artifact_removed=True, artifact_removed_at=time.time())
        return commands.public(commands.observed(commands.load(child['job_id'], owner, endpoint)))
    if operation in {'inventory', 'command_review', 'command_start'} and resource['program'] != program():
        raise TemporarySlotError('The retained replication adapter changed; release it before opening another resource')
    if operation in {'command_review', 'command_start'} and resource['source'].get('provider_isolation_key') != list(artifact_context(server).isolation_key):
        raise TemporarySlotError('The retained replication resource belongs to another provider isolation scope')
    if operation == 'inventory':
        if set(remaining) - {'offset', 'limit'}:
            raise TemporarySlotError('Select an acknowledgement page')
        return jobs.queue_catalog(resource['job_id'], owner, endpoint, **remaining)
    if operation == 'command_list':
        if set(remaining) - {'offset', 'limit'}:
            raise TemporarySlotError('Select a native command receipt page')
        return commands.list(owner, endpoint, **remaining)
    if operation in {'command_status', 'command_cancel'}:
        if set(remaining) != {'job_id'}:
            raise TemporarySlotError('Select one native replication command receipt')
        return (commands.public(commands.observed(commands.load(remaining['job_id'], owner, endpoint)))
                if operation == 'command_status' else jobs.cancel_command(resource['job_id'], owner, endpoint, remaining['job_id']))
    if operation == 'command_start':
        return jobs.queue_execute(resource['job_id'], owner, endpoint, remaining)
    if operation == 'command_review':
        if set(remaining) != {'operation', 'options'}:
            raise TemporarySlotError('Review exact native temporary replication options')
        selected = options(remaining['operation'], remaining['options'])
        limit = current_app.config.get('CDEADMIN_POSTGRESQL_CONTINUITY_MAX_RUNTIME_SECONDS')
        if limit is not None and (type(limit) is not int or limit < 1 or selected['timeout_seconds'] is None or selected['timeout_seconds'] > limit):
            raise TemporarySlotError('Application policy requires a bounded replication command deadline')
        return jobs.queue_review(resource['job_id'], owner, endpoint, remaining['operation'], selected)
    raise TemporarySlotError('Temporary replication resource action is unavailable')


def stream_download(service, server, request, *, copy=False):
    from flask import send_file
    if copy:
        from . import postgresql_snapshot_copy as stream
    else:
        from . import postgresql_replication_stream as stream
    if not isinstance(request, dict) or set(request) != {'database_target_id', 'resource_id', 'job_id'}:
        raise TemporarySlotError('Select one owned original-backend native replication capture')
    jobs, owner, endpoint = manager(service, server, request['database_target_id'])
    resource = jobs.load(request['resource_id'], owner, endpoint)
    commands = jobs.commands(resource)
    child = commands.load(request['job_id'], owner, endpoint)
    opened = stream.payload(commands, child)
    source = opened.__enter__()
    artifact = child['snapshot_copy_artifact' if copy else 'protocol_stream_artifact']
    try:
        response = send_file(source, mimetype='application/octet-stream' if copy else 'application/x-ndjson', as_attachment=True,
            download_name=artifact['filename'], conditional=False, max_age=0)
        response.content_length = int(artifact['artifact_bytes'])
        response.direct_passthrough = False
        response.headers.update({'Cache-Control': 'no-store, private', 'X-Content-Type-Options': 'nosniff',
            'X-Content-SHA256': artifact['sha256'],
            'X-Export-Completeness': 'verified-capture' if artifact['state'] == 'verified' else 'incomplete'})
        response.call_on_close(lambda: opened.__exit__(None, None, None))
        return response
    except BaseException:
        opened.__exit__(None, None, None)
        raise
