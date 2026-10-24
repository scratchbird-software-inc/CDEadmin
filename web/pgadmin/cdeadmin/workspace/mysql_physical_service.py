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


def source(service, server, *, admitted=None):
    """Admit the actual persistent engine/encryption scope, not a generic dump."""
    captured = host.source(service,server) if admitted is None else host.source(service,server,admitted=admitted)
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    from ..providers.mysql_family.mysql_log_purge import private_connection
    from ..providers.mysql_family.mysql_clone import configure, rows
    route = {key: value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
    client,route=admitted if admitted is not None else (provider.client,route)
    connection = private_connection(client, {**route, 'database':None, 'read_timeout':15})
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
    finally: client._discard_failed_session(connection)


def options(value):
    fields = {'connection', 'workspace', 'executable', 'mysql', 'phase', 'sql_host', 'sql_port',
        'input_job_id', 'parallel', 'memory_bytes', 'timeout_seconds', 'accept_release_candidate'}
    extra = {'mysqld', 'recovery_gtid_mode'} if isinstance(value,dict) and value.get('phase') == 'recover' else set()
    optional = {'recovery_port','recovery_mode','recovery_server_id','recovery_local_infile'} if extra else ({'incremental_job_id'} if isinstance(value,dict) and value.get('phase')=='prepare_redo' else set())
    if not isinstance(value, dict) or not fields | extra <= set(value) or set(value)-fields-extra-optional:
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
    if value['phase'] not in {'backup','incremental','prepare','prepare_redo','copy_back','recover'}:
        raise native.HostError('Select full/incremental backup, redo-only/final preparation, isolated copy-back or managed recovery')
    if extra and value['recovery_gtid_mode'] not in {'OFF','OFF_PERMISSIVE','ON_PERMISSIVE','ON'}:
        raise native.HostError('Select the native recovery GTID mode explicitly')
    if extra:
        port = value.get('recovery_port',0)
        if type(port) is not int or port != 0 and not 1024 <= port <= 65535:
            raise native.HostError('Select no recovery TCP listener or a native loopback port from 1024 through 65535')
        selected['recovery_port'] = port
        local = value.get('recovery_local_infile', False)
        if type(local) is not bool: raise native.HostError('Explicitly select trusted recovery checksum input')
        selected['recovery_local_infile'] = local
        mode=value.get('recovery_mode','read_only')
        if mode not in {'read_only','replay'}:raise native.HostError('Select read-only inspection or writable native replay startup')
        selected['recovery_mode']=mode
        if mode=='replay':
            server_id=value.get('recovery_server_id')
            if not port or type(server_id) is not int or not 1<=server_id<=4294967295:
                raise native.HostError('Writable replay startup requires an explicit loopback TCP port and native server ID')
        elif 'recovery_server_id' in value:raise native.HostError('A recovery server ID applies only to writable replay startup')
    if value['phase']=='prepare_redo':
        selected['incremental_job_id']=identity(value['incremental_job_id']) if value.get('incremental_job_id') is not None else None
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
        'This workflow requires self-contained, uncompressed and unencrypted native backup files. Incrementals require the exact retained native base lineage and contiguous LSNs. Apply them to separate redo-only copies, then finalize preparation before copy-back. External tablespaces, key provisioning and production cutover remain separate.',
        'Managed recovery starts a separate native MySQL9.7.0 data copy under the authenticated SSH OS account with a fresh UUID, private Unix socket and selected loopback TCP listener. Read-only inspection is the default. Explicit replay startup is writable with private ROW binary logging and the selected server ID. Both disable events/replication autostart and automatic upgrades, and end on stop or reviewed lifetime. SQL readiness is distinct from full data recovery acceptance.',
        'Physical files and native output are private to the selected host OS account. Broad source archive protection is acquired before backup dispatch and is retired only by its separate reviewed protection workflow.',
    )

    def public(self, record):
        result = super().public(record)
        result['remote_review'] = deepcopy(record['source_state']['remote_review'])
        result['host_binding'] = deepcopy(record['source_state']['host_binding'])
        result['source_connection_class'] = record['source_state'].get('source_connection_class')
        remote = record.get('remote_observation') or {}
        result['native_process_termination_confirmed'] = remote.get('process_termination_confirmed') is True
        result['file_verification_confirmed'] = bool(not record.get('artifact_removed') and not record.get('artifact_removal') and remote.get('return_code') == 0 and not remote.get('error_type') and
            (remote.get('artifact') or remote.get('restored_files')) and remote.get('process_termination_confirmed') is True and
            remote.get('credential_cleanup_confirmed') is True and remote.get('supervisor_finished') is True)
        result['database_recovery_verified'] = False
        result['recovery_running'] = not record.get('artifact_removed') and remote.get('recovery_running_verified') is True
        result['recovery_sql_startup_observed'] = remote.get('sql_ready_observed') is True
        result['production_cutover_verified'] = False
        result['backup_schedule_id']=record['source_state'].get('backup_schedule_id')
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
        **{key: selected[key] for key in ('mysqld','recovery_gtid_mode','recovery_port','recovery_mode','recovery_server_id','recovery_local_infile','incremental_job_id') if key in selected}}


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
    return provider.client._tool_secrets(route, sealed, allow_recovery_credentials=True)


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
    from .mysql_physical_retention import admission
    jobs,owner,endpoint=manager(service,server)
    if operation.startswith(('retention_schedule_','backup_schedule_','check_schedule_')):
        if not isinstance(request,dict):raise native.HostError('Select a physical schedule request')
        from ..report_scheduler.crypto import WorkerKeyError
        scheduler=service.mysql_check_scheduler if operation.startswith('check_schedule_') else service.mysql_backup_scheduler if operation.startswith('backup_schedule_') else service.mysql_physical_scheduler
        try:
            if operation.endswith('_enable'):
                with admission(jobs):return scheduler.action(server,jobs,owner,endpoint,operation,request)
            return scheduler.action(server,jobs,owner,endpoint,operation,request)
        except WorkerKeyError:raise native.HostError('Physical SSH delegation is unavailable; configure worker keys and review a new policy') from None
    with admission(jobs):return _action(service,server,operation,request)


def _action(service, server, operation, request, *, source_capture=None,database_credentials=None,on_review=None,scheduled_policy_id=None,scheduled_operation=None,authorize=None):
    if not isinstance(request, dict): raise native.HostError('Select a native physical request')
    if operation.startswith('connection_'):
        from .mysql_recovery_connections import action as connection_action
        return connection_action(service, server, operation[11:], request)
    jobs, owner, endpoint = manager(service, server)
    if operation.startswith('retention_batch_'):
        from .mysql_physical_batch_retention import action as batch_action
        return batch_action(service,server,jobs,owner,endpoint,operation,request)
    if operation.startswith('retention_'):
        from .mysql_physical_retention import action as retention_action
        return retention_action(service,server,jobs,owner,endpoint,operation,request)
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
        owning=record['source_state'].get('backup_schedule_id')
        scheduler=(getattr(service,'mysql_check_scheduler',None) if record['source_state'].get('schedule_operation')=='mysql_scheduled_physical_check' else getattr(service,'mysql_backup_scheduler',None))
        if owning and owning!=scheduled_policy_id and operation!='output' and (scheduler is None or scheduler.read(owning)['state']=='enabled'):
            raise native.HostError('Disable the owning backup schedule before changing its native job')
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
        if selected['phase'] in {'backup','incremental'}:
            captured = source_capture() if source_capture is not None else source(service, server)
            if operation == 'start':
                if captured['identity'] != record['source'] or captured['state']['host_binding'] != record['source_state']['host_binding']:
                    raise native.HostError('Native physical source changed after review')
        if selected['phase']!='backup':
            prior = jobs.load(selected['input_job_id'], owner, endpoint.id)
            if (prior.get('artifact_removed') or prior.get('artifact_removal') or prior.get('retention_batch_id') or
                    prior.get('backup_workflow_protected') and prior['source_state'].get('backup_schedule_id')!=scheduled_policy_id or
                    prior['options']['connection'] != selected['connection'] or prior['options']['workspace'] != selected['workspace'] or
                    not jobs.public(prior)['file_verification_confirmed'] or
                    not (prior.get('remote_observation') or {}).get('restored_files' if selected['phase'] == 'recover' else 'artifact')):
                raise native.HostError('Select an observed physical input in this owner/registration and pinned host workspace')
            if selected['phase']=='incremental':
                if captured['identity']!=prior['source'] or captured['state']['host_binding']!=prior['source_state']['host_binding']:
                    raise native.HostError('The incremental source differs from its original base and principal')
            else:
                captured = {'identity': deepcopy(prior['source']), 'state': {key: deepcopy(prior['source_state'][key])
                    for key in ('host_binding', 'source_connection_class') if key in prior['source_state']}}
            if selected.get('incremental_job_id') is not None:
                delta=jobs.load(selected['incremental_job_id'],owner,endpoint.id)
                if (delta['options']['phase']!='incremental' or delta.get('artifact_removed') or delta.get('artifact_removal') or delta.get('retention_batch_id') or
                        delta.get('backup_workflow_protected') or not jobs.public(delta)['file_verification_confirmed'] or
                        delta['source']!=prior['source'] or delta['source_state']['host_binding']!=prior['source_state']['host_binding'] or
                        delta['options']['connection']!=selected['connection'] or delta['options']['workspace']!=selected['workspace']):
                    raise native.HostError('Select a verified incremental in this exact original source and host workspace')
        provisional = {'options': selected, 'source': captured['identity'], 'source_state': {**captured['state'], 'remote_review': {}}, 'job_id': '', 'review_digest': ''}
        observed = transport.request(remote_request(provisional, 'inspect'))
        captured['state']['remote_review'] = observed
        if scheduled_policy_id is not None:captured['state'].update(backup_schedule_id=scheduled_policy_id,schedule_operation=scheduled_operation or 'mysql_scheduled_physical_backup')
        program = {**native.program(), 'execution_host': {**peer, 'kind': 'database-server-ssh-host', 'workspace': selected['workspace']}}
        if operation == 'review':
            value=jobs.review(owner,endpoint.id,selected,captured,configuration,program)
            if on_review is not None:on_review(value)
            if scheduled_policy_id is not None:jobs.update(jobs.load(value['job_id'],owner,endpoint.id),backup_workflow_protected=True)
            return value
        if captured['state'] != record['source_state'] or program != record['program']:
            raise native.HostError('Physical host or input changed after review')
        if selected['phase'] in {'backup','incremental','recover'} and request['delegate_database_credentials'] is not True:
            raise native.HostError('Confirm private database credential delegation to the pinned database SSH host')
        delegated = (database_credentials if database_credentials is not None else delegate(service,server)) if selected['phase'] in {'backup','incremental','recover'} else None
        if authorize is not None:authorize()
        if not claim(jobs, record, owner, endpoint.id, request): return jobs.get(record['job_id'], owner, endpoint.id)
        try:
            if selected['phase'] in {'backup','incremental'}:
                from .mysql_backup_protection import manager as protection
                ticket = protection(service).scoped(owner, endpoint.id).begin(record['source'], 'Incremental physical instance' if selected['phase']=='incremental' else 'Full physical instance',
                    selected['workspace'] + '/' + record['job_id'] + '/artifact', {})
                ticket.update(backup_kind='mysql_native_xtrabackup_incremental' if selected['phase']=='incremental' else 'mysql_native_xtrabackup_full', native_physical_job_id=record['job_id'],
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
