"""Reviewed native physical artifacts on an independently authenticated DB host."""
from copy import deepcopy
import time

from ..providers.mysql_family import mysql_physical_transport as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import MySQLBinlogJobs, digest, identity, review_digest
from . import mysql_host_service as host
from .mysql_monitoring_host import MySQLMonitoringHost


def source(service, server):
    """Admit the actual persistent engine/encryption scope, not a generic dump."""
    captured = host.source(service, server)
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    from ..providers.mysql_family.mysql_log_purge import private_connection
    from ..providers.mysql_family.mysql_clone import configure, rows
    route = {key: value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
    connection = private_connection(provider.client, {**route, 'database':None, 'read_timeout':15})
    try:
        configure(connection)
        engines = rows(connection, "SELECT ENGINE AS engine,COUNT(*) AS objects FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys') AND TABLE_TYPE='BASE TABLE' GROUP BY ENGINE ORDER BY ENGINE")
        unsupported = [row['engine'] for row in engines if row['engine'] not in {'InnoDB','MyISAM','CSV'}]
        if unsupported:
            raise native.HostError('This physical backend has not admitted these persistent storage engines: ' + ', '.join(str(item) for item in unsupported))
        encrypted = rows(connection, "SELECT COUNT(*) AS encrypted FROM information_schema.INNODB_TABLESPACES WHERE ENCRYPTION='Y'")[0]['encrypted']
        if encrypted:
            raise native.HostError('Encrypted tablespaces require separately admitted native keyring provisioning for physical recovery')
        captured['state']['storage_engine_counts'] = engines
        captured['state']['encrypted_tablespaces'] = encrypted
        return captured
    finally: provider.client._discard_failed_session(connection)


def options(value):
    fields = {'connection', 'workspace', 'executable', 'mysql', 'phase', 'sql_host', 'sql_port',
        'input_job_id', 'parallel', 'memory_bytes', 'timeout_seconds', 'accept_release_candidate'}
    extra = {'mysqld', 'recovery_gtid_mode'} if isinstance(value,dict) and value.get('phase') == 'recover' else set()
    if not isinstance(value, dict) or set(value) != fields | extra:
        raise native.HostError('Select the complete native physical host and operation options')
    selected = deepcopy(value); selected['connection'] = native.ssh.public_route(value['connection'])
    if selected['connection']['platform'] != 'posix' or value['accept_release_candidate'] is not True:
        raise native.HostError('Confirm the admitted Linux XtraBackup9.7.1-rc1 release candidate explicitly')
    for key in ('workspace', 'executable', 'mysql', *(['mysqld'] if extra else [])):
        if not isinstance(value[key], str) or not value[key] or '\x00' in value[key] or len(value[key]) > 4096:
            raise native.HostError('Select bounded absolute paths on the authenticated database host')
    if value['sql_host'] not in {'127.0.0.1', '::1', 'localhost'} or type(value['sql_port']) is not int or not 1 <= value['sql_port'] <= 65535:
        raise native.HostError('Select the source loopback TCP address on its authenticated database host')
    for key, low, high in [('parallel', 1, 64), ('memory_bytes', 64 * 1024 * 1024, 16 * 1024**3), ('timeout_seconds', 1, 604800)]:
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise native.HostError('Select bounded native physical ' + key)
    if value['phase'] not in {'backup', 'prepare', 'copy_back', 'recover'}:
        raise native.HostError('Select backup, prepare, isolated copy-back or managed recovery')
    if extra and value['recovery_gtid_mode'] not in {'OFF','OFF_PERMISSIVE','ON_PERMISSIVE','ON'}:
        raise native.HostError('Select the native recovery GTID mode explicitly')
    if value['phase'] == 'backup':
        if value['input_job_id'] is not None:
            raise native.HostError('A full physical backup has no prior input')
    else:
        selected['input_job_id'] = identity(value['input_job_id'])
    return selected


class PhysicalJobs(MySQLBinlogJobs):
    operation = 'mysql_native_physical_backup'
    review_warnings = (
        'The admitted backend is upstream XtraBackup9.7.1-rc1, a release candidate. Its original native replies, verified files and recovery acceptance are separate facts.',
        'Full backups take native backup/read locks and copy complete supported instance files. Prepare mutates a separate private copy. Copy-back creates only a new isolated job data directory; it never overwrites the live data directory or starts a database.',
        'Native processes run under an independent supervisor on the authenticated database SSH host. Closing the viewer or losing a reply does not cancel or roll back native work. An original unknown dispatch is never automatically repeated.',
        'This full-artifact workflow requires self-contained, uncompressed and unencrypted native backup files. External tablespaces, encryption key provisioning, incrementals, post-replay acceptance and production cutover retain separate implementation/acceptance gates.',
        'Managed recovery starts a separate native MySQL9.7.0 data copy under the authenticated SSH OS account, with a fresh native UUID, private Unix socket only, super_read_only, events/replication autostart disabled and no automatic upgrades. It ends on explicit stop or its reviewed lifetime. SQL readiness is distinct from full data recovery acceptance.',
        'Physical files and native output are private to the selected host OS account. Broad source archive protection is acquired before backup dispatch and is retired only by its separate reviewed protection workflow.',
    )

    def public(self, record):
        result = super().public(record)
        result['remote_review'] = deepcopy(record['source_state']['remote_review'])
        result['host_binding'] = deepcopy(record['source_state']['host_binding'])
        result['source_connection_class'] = record['source_state'].get('source_connection_class')
        remote = record.get('remote_observation') or {}
        result['file_verification_confirmed'] = bool(remote.get('return_code') == 0 and not remote.get('error_type') and
            (remote.get('artifact') or remote.get('restored_files')) and remote.get('process_termination_confirmed') is True and
            remote.get('credential_cleanup_confirmed') is True and remote.get('supervisor_finished') is True)
        result['database_recovery_verified'] = False
        result['recovery_running'] = remote.get('recovery_running_verified') is True
        result['recovery_sql_startup_observed'] = remote.get('sql_ready_observed') is True
        result['production_cutover_verified'] = False
        return result


def manager(service, server):
    _base, owner, endpoint = host.manager(service, server)
    context = service.endpoint_service._context(endpoint, ())
    if 'backup_admin' not in service.endpoint_service.provider_registry.admitted_permissions(context):
        raise native.HostError('Native physical artifacts require backup administration permission')
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_physical_jobs', None)
        if jobs is None:
            from flask import current_app
            path = service.operation_bus.store.path
            root = current_app.config.get('CDEADMIN_MYSQL_PHYSICAL_ROOT') or str(path.parent / 'mysql-physical-receipts')
            jobs = service.mysql_physical_jobs = PhysicalJobs(str(path) + '.mysql-physical', root)
    return jobs, owner, endpoint


def remote_request(record, action):
    selected = record['options']
    return {'schema': 'cdeadmin.mysql-physical.v1', 'action': action,
        **{key: deepcopy(selected[key]) for key in ('workspace', 'executable', 'mysql', 'phase', 'sql_host', 'sql_port',
            'input_job_id', 'parallel', 'memory_bytes', 'timeout_seconds')},
        'binding': deepcopy(record['source_state']['host_binding']), 'source_identity': deepcopy(record['source']),
        'reviewed': deepcopy(record['source_state']['remote_review']),
        'job_id': record['job_id'], 'input_digest': record['review_digest'],
        **{key: selected[key] for key in ('mysqld','recovery_gtid_mode') if key in selected}}


def delegate(service, server):
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, MySQLPilotProvider):
        raise native.HostError('Native MySQL backup credential delegation is unavailable')
    route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
    if route.get('ssl_verify_identity') or route.get('ssl_verify_cert') or route.get('ssl_ca'):
        raise native.HostError('Registered TLS verification requires separately admitted host-side certificate paths; it cannot be lowered for physical backup')
    def sealed(values):
        if len(values) > 1:
            raise native.HostError('This physical backend has not admitted native multiple-factor credential delegation')
        return {'user': route.get('user') or route.get('username'), 'password': values[0] if values else ''}
    return provider.client._tool_secrets(route, sealed)


def claim(jobs, record, owner, endpoint, request):
    with jobs.store(record['job_id']) as store:
        def change(state):
            current = jobs.record(state, record['job_id'], owner, endpoint)
            if request.get('confirmed') is not True or request.get('review_digest') != current['review_digest'] or review_digest(current) != current['review_digest']:
                raise native.HostError('Confirm the exact original physical review')
            if current['state'] != 'reviewed': return False
            if time.time() > current['expires_at']: raise native.HostError('Physical review expired; review its current inputs again')
            current.update(state='dispatching', native_may_have_dispatched=True, started_at=time.time())
            return True
        return store.change(change)


def action(service, server, operation, request):
    if not isinstance(request, dict): raise native.HostError('Select a native physical request')
    jobs, owner, endpoint = manager(service, server)
    if operation == 'peer' and set(request) == {'host', 'port'}:
        return native.ssh.probe(request['host'], request['port'])
    if operation == 'list' and not set(request) - {'offset', 'limit'}:
        return jobs.list(owner, endpoint.id, **request)
    if operation == 'status' and set(request) == {'job_id'}:
        return jobs.get(request['job_id'], owner, endpoint.id)
    if operation == 'review' and set(request) == {'options', 'credentials'}:
        selected = options(request['options']); record = None
    elif operation in {'start', 'reconcile', 'cancel', 'output'}:
        fields = {'job_id', 'credentials'} | ({'review_digest', 'confirmed', 'delegate_database_credentials'} if operation == 'start' else set())
        if set(request) != fields: raise native.HostError('Select the exact physical job and private SSH authentication')
        record = jobs.load(request['job_id'], owner, endpoint.id); selected = record['options']
        if operation == 'start' and record['state'] != 'reviewed':
            if request['confirmed'] is not True or request['review_digest'] != record['review_digest']:
                raise native.HostError('Confirm the exact original physical review')
            return jobs.get(record['job_id'], owner, endpoint.id)
        if operation == 'cancel' and record['state'] == 'reviewed':
            jobs.update(record, state='cancelled', native_may_have_dispatched=False, process_termination_confirmed=True)
            return jobs.get(record['job_id'], owner, endpoint.id)
    else:
        raise native.HostError('Native physical action is unavailable')
    configuration = digest(MySQLMonitoringHost._configuration(server))
    if record and (record['configuration'] != configuration or
            any(record['program'].get(key) != value for key, value in native.program().items())):
        raise native.HostError('Physical registration or host adapter changed; preserve the original receipt and review new work separately')
    transport = native.Transport(selected['connection'], host.credentials(request['credentials']))
    try:
        peer = transport.connect()
        if operation in {'reconcile', 'cancel', 'output'}:
            remote = transport.request(remote_request(record, 'status' if operation == 'reconcile' else operation))
            if operation == 'output': return remote
            if remote.get('input_digest') != record['review_digest']:
                raise native.HostError('Original remote physical receipt is unavailable or differs from this reviewed job')
            values = {'remote_observation': remote, 'observed_at': time.time(),
                'original_dispatch_reply_unchanged': True}
            if remote.get('supervisor_control_unavailable'):
                values['state'] = 'unknown'
            if record['state'] != 'unknown' and remote.get('supervisor_finished') is True and remote.get('state') in {'native_returned', 'not_dispatched'}:
                values['state'] = 'native_returned' if remote.get('return_code') == 0 else 'native_failed' if remote.get('native_reply_observed') else 'not_dispatched'
            jobs.update(record, **values)
            return jobs.get(record['job_id'], owner, endpoint.id)
        if selected['phase'] == 'backup':
            captured = source(service, server)
            if operation == 'start':
                if captured['identity'] != record['source'] or captured['state']['host_binding'] != record['source_state']['host_binding']:
                    raise native.HostError('Native physical source changed after review')
        else:
            prior = jobs.load(selected['input_job_id'], owner, endpoint.id)
            if (prior['options']['connection'] != selected['connection'] or prior['options']['workspace'] != selected['workspace'] or
                    not jobs.public(prior)['file_verification_confirmed'] or
                    not (prior.get('remote_observation') or {}).get('restored_files' if selected['phase'] == 'recover' else 'artifact')):
                raise native.HostError('Select an observed physical input in this owner/registration and pinned host workspace')
            captured = {'identity': deepcopy(prior['source']), 'state': {key: deepcopy(prior['source_state'][key])
                for key in ('host_binding', 'source_connection_class') if key in prior['source_state']}}
        provisional = {'options': selected, 'source': captured['identity'], 'source_state': {**captured['state'], 'remote_review': {}}, 'job_id': '', 'review_digest': ''}
        observed = transport.request(remote_request(provisional, 'inspect'))
        captured['state']['remote_review'] = observed
        program = {**native.program(), 'execution_host': {**peer, 'kind': 'database-server-ssh-host', 'workspace': selected['workspace']}}
        if operation == 'review':
            return jobs.review(owner, endpoint.id, selected, captured, configuration, program)
        if captured['state'] != record['source_state'] or program != record['program']:
            raise native.HostError('Physical host or input changed after review')
        if selected['phase'] in {'backup','recover'} and request['delegate_database_credentials'] is not True:
            raise native.HostError('Confirm private database credential delegation to the pinned database SSH host')
        delegated = delegate(service, server) if selected['phase'] in {'backup','recover'} else None
        if not claim(jobs, record, owner, endpoint.id, request): return jobs.get(record['job_id'], owner, endpoint.id)
        try:
            if selected['phase'] == 'backup':
                from .mysql_backup_protection import manager as protection
                ticket = protection(service).scoped(owner, endpoint.id).begin(record['source'], 'Full physical instance',
                    selected['workspace'] + '/' + record['job_id'] + '/artifact', {})
                ticket.update(backup_kind='mysql_native_xtrabackup_full', native_physical_job_id=record['job_id'],
                    execution_host=program['execution_host'])
                jobs.update(record, backup_protection_id=ticket.backup_id)
            payload = remote_request(record, 'start'); payload['database_credentials'] = delegated
            remote = transport.request(payload)
            jobs.update(record, state='remote_running', dispatch_reply=remote, original_dispatch_reply_observed=True)
        except BaseException as error:
            jobs.update(record, state='unknown', dispatch_error_type=type(error).__name__)
            raise
        return jobs.get(record['job_id'], owner, endpoint.id)
    finally: transport.close()
