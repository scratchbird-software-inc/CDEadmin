"""Registered native MySQL/MariaDB continuous receiver admission and receipts."""
import socket
import stat
import time

from ..providers.mysql_family import continuous_binlog as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest
from .mysql_monitoring_host import MySQLMonitoringHost


class ReceiverJobs(MySQLBinlogJobs):
    operation = 'native_continuous_raw_binary_logs'
    review_warnings = (
        'A long-lived native utility reads this source through the application host. Active files stay private; only independently verified closed-log snapshots enter the existing archive/replay workspace.',
        'Choose a receiver server ID unique among clients and replicas on this source. A conflicting native replication ID can disconnect another receiver; the source does not expose every unregistered client ID.',
        'Stopping or losing this receiver does not restart it automatically. Published archives remain independent; an unclosed private file is not a complete archive or proof of a recoverable transaction.',)

    def restart_checkpoint(self,job_id,owner,endpoint,archives):
        from ..operations.native_writers import inspect,NativeWriterError
        record=self.load(job_id,owner,endpoint)
        result=record.get('result') or {}
        if (record['state'] not in {'cancelled','captured'} or
                record.get('native_process_termination_confirmed') is not True or not result.get('next_file')):
            raise BinlogArchiveError('Restart requires a clean stopped receiver with a durable next-log checkpoint')
        with self._maps_lock:known=self.workers.get(job_id)
        if known is not None and known[0].is_alive():raise BinlogArchiveError('The local receiver worker is still stopping')
        try:
            candidates,_absent=inspect(self.writer_scopes(record,archives),
                hostname=record['program']['execution_host'].get('hostname'),started_at=record.get('started_at',record['created_at']))
            if candidates:raise NativeWriterError('Reconcile remaining native receiver writers before reviewing a restart')
        except NativeWriterError as error:raise BinlogArchiveError(str(error)) from None
        return record,result['next_file']

    def writer_scopes(self,record,archives):
        from ..operations.native_writers import NativeWriterError
        from .mysql_binlog_jobs import identity
        parent=self.directory(record);children=[]
        if (record.get('continuation') or {}).get('writer_scope_index')==1:
            index=parent/'snapshots'
            if index.is_symlink() or index.exists() and (index.resolve()!=index or getattr(index.lstat(),'st_file_attributes',0)&0x400):
                raise NativeWriterError('Native receiver snapshot index cannot contain links or reparse points')
            if index.is_dir():
                for entry in index.iterdir():
                    if entry.name.startswith('.'):continue
                    identity(entry.name);info=entry.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_size or getattr(info,'st_file_attributes',0)&0x400:
                        raise NativeWriterError('Native receiver snapshot index entry is invalid')
                    children.append(archives.load(entry.name,record['owner'],record['endpoint_id']))
        else:
            # Phase-84 receipts predate the dedicated parent index. Inspect
            # their existing owner/endpoint archive index once for compatibility.
            index=archives.scope(record['owner'],record['endpoint_id'])/'index'
            if index.is_dir():
                for entry in index.iterdir():
                    if entry.name.startswith('.'):continue
                    child=archives.load(entry.name.split('_',1)[-1],record['owner'],record['endpoint_id'])
                    if (child.get('continuation') or {}).get('continuous_receiver_job_id')==record['job_id']:children.append(child)
        allowed={record['program']['executable_sha256']:'native-binlog-receiver'}
        scopes=[{'directory':parent,'executables':allowed}]
        for child in children:
            if ((child.get('continuation') or {}).get('continuous_receiver_job_id')!=record['job_id'] or
                    child['source']!=record['source'] or child['program']!=record['program']):
                raise NativeWriterError('Native receiver snapshot ownership or executable identity differs')
            directory=archives.directory(child)
            if directory.is_dir():scopes.append({'directory':directory,'executables':{record['program']['executable_sha256']:'native-binlog-parser'}})
        return scopes

    def reconcile_writer(self,request,owner,endpoint,archives):
        from ..operations.native_writers import inspect,stop,NativeWriterError
        if set(request)!={'job_id','confirmed'} or request['confirmed'] is not True:
            raise BinlogArchiveError('Confirm stopping reviewed native utilities in one receiver and its owned snapshot workspaces')
        record=self.load(request['job_id'],owner,endpoint)
        if self.get(record['job_id'],owner,endpoint)['state'] not in {'unknown','failed','cancelled','captured'}:
            raise BinlogArchiveError('Cancel the active receiver before reconciling its writers')
        with self._maps_lock:known=self.workers.get(record['job_id'])
        if known is not None and known[0].is_alive():raise BinlogArchiveError('The local receiver worker is still stopping')
        try:
            scopes=self.writer_scopes(record,archives)
            hostname=record['program']['execution_host'].get('hostname')
            observation=record.get('tool_observation') or (record.get('result') or {}).get('receiver_observation') or {}
            observation=observation.get('process_observation',observation)
            progress=record.get('progress') or {}
            expected=[{'pid':progress.get('pid',observation.get('pid')),
                       'process_create_time':progress.get('process_create_time',observation.get('process_create_time'))}]
            arguments={'hostname':hostname,'started_at':record.get('started_at',record['created_at']),'expected':expected}
            candidates,absent=inspect(scopes,**arguments)
            if not candidates and (record.get('writer_reconciliation') or {}).get('process_scope_stopped') is True:
                return self.get(record['job_id'],owner,endpoint)
            stopped=stop(candidates)
            remaining,_absent=inspect(scopes,**arguments)
            if remaining:raise NativeWriterError('A reviewed native utility is still using an owned receiver workspace')
        except NativeWriterError as error:raise BinlogArchiveError(str(error)) from None
        self.update(record,state=record['state'] if record['state'] in {'unknown','failed','cancelled','captured'} else 'unknown',
            writer_reconciliation={'process_scope_stopped':True,'hostname':hostname,'processes':stopped,
                'recorded_process_ids_absent':absent,'scope':'reviewed receiver and its linked native snapshot parser workspaces',
                'artifact_verified':False,'remote_finality_inferred':False,'observed_at':time.time()},automatic_retry=False)
        return self.get(record['job_id'],owner,endpoint)

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal)
        try:
            self.update(record, state='active')
            result = transport.execute(record, self.directory(record), cancel,
                lambda event: self.update(record, progress=event))
            observed = result['receiver_observation']['process_observation']
            self.update(record, state='cancelled' if signal.is_set() or observed.get('cancel_requested') else
                'failed' if not result['native_operation_returned'] else 'captured',
                result=result, native_process_termination_confirmed=observed.get('cleanup_confirmed') is True,
                finished_at=time.time(), automatic_retry=False)
        except BaseException as error:
            observation = getattr(error, 'observation', None) or getattr(error, 'process_observation', None) or {}
            stopped = observation.get('process_observation', observation).get('cleanup_confirmed')
            self.update(record, state='unknown' if stopped is False else 'failed' if getattr(error,'publication_failed',False) else 'cancelled' if signal.is_set() else 'failed',
                error_type=type(error).__name__, error_message=str(error) if isinstance(error, BinlogArchiveError) else None,
                tool_observation={key: value for key, value in observation.items() if key not in {'stdout', 'stderr'}},
                native_process_termination_confirmed=stopped, finished_at=time.time(), automatic_retry=False)
        finally:
            try: transport.close()
            finally:
                import threading
                with self._maps_lock:
                    known = self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread(): self.workers.pop(record['job_id'], None)


def manager(service, server, family):
    from flask import current_app
    if family == 'mysql':
        from .mysql_raw_binlog_service import manager as archive_manager
        archives, owner, endpoint, context = archive_manager(service, server)
    elif family == 'mariadb':
        from .mysql_binlog_service import manager as archive_manager
        archives, owner, endpoint, context = archive_manager(service, server, family)
    else: raise BinlogArchiveError('Select a native receiver family')
    with service._semantic_lock:
        attribute = family + '_continuous_binlog_jobs'
        jobs = getattr(service, attribute, None)
        if jobs is None:
            store = service.operation_bus.store
            root = current_app.config.get('CDEADMIN_' + family.upper() + '_CONTINUOUS_BINLOG_ROOT') or str(store.path.parent/(family+'-continuous-binlogs'))
            jobs = ReceiverJobs(str(store.path)+'.'+family+'-continuous-binlogs', root)
            setattr(service, attribute, jobs)
            import atexit
            atexit.register(jobs.close)
    return jobs, archives, owner, endpoint, context


def program_identity(native_adapter, client, route, scope):
    result = native_adapter.program_identity(client, route, scope)
    return {**result, 'execution_host': {**result['execution_host'], 'hostname': socket.gethostname()}}


def action(service, server, operation, request, family):
    from flask import current_app
    if not isinstance(request, dict): raise BinlogArchiveError('Select a native continuous receiver request')
    jobs, archives, owner, endpoint, _context = manager(service, server, family)
    if operation in {'cleanup_catalog','cleanup_review','cleanup_start','cleanup_status','cleanup_cancel','cleanup_list'}:
        from .continuous_binlog_cleanup import action as cleanup_action
        return cleanup_action(service,server,operation,request,family,(jobs,archives,owner,endpoint,_context))
    if operation in {'tail_catalog','tail_review','tail_start'}:
        from .continuous_binlog_tails import action as tail_action
        return tail_action(service,server,operation,request,family,(jobs,archives,owner,endpoint,_context))
    if operation == 'list':
        if set(request)-{'offset','limit'}: raise BinlogArchiveError('Invalid native receiver receipt page')
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status','cancel'}:
        if set(request) != {'job_id'}: raise BinlogArchiveError('Select one owned native receiver')
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    if operation=='reconcile_writer':return jobs.reconcile_writer(request,owner,endpoint.id,archives)
    adapter = native.adapter(family)
    previous=None
    if operation == 'review':
        if set(request) not in ({'options'},{'options','resume_job_id'}): raise BinlogArchiveError('Review exact native receiver options')
        selected = native.options(family, request['options'])
        if 'resume_job_id' in request:
            previous,checkpoint=jobs.restart_checkpoint(request['resume_job_id'],owner,endpoint.id,archives)
            if selected['start_file']!=checkpoint:raise BinlogArchiveError('Restart from the stopped receiver\'s exact next native log')
    elif operation == 'start':
        reviewed = jobs.load(request.get('job_id'), owner, endpoint.id)
        if reviewed['state'] != 'reviewed': return jobs.start(request, owner, endpoint.id, {}, None)
        selected = reviewed['options']
        previous_id=(reviewed.get('continuation') or {}).get('previous_receiver_job_id')
        if previous_id:
            previous,checkpoint=jobs.restart_checkpoint(previous_id,owner,endpoint.id,archives)
            if selected['start_file']!=checkpoint:raise BinlogArchiveError('The stopped receiver checkpoint changed; prepare a new review')
    elif operation == 'catalog':
        if request: raise BinlogArchiveError('Native receiver catalog takes no browser route')
        selected = None
    else: raise BinlogArchiveError('Native receiver action is unavailable')
    client = connection = transport = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        from ..providers.mysql_family.provider import MySQLPilotProvider, MariaDBPilotProvider
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider if family == 'mysql' else MariaDBPilotProvider):
            raise BinlogArchiveError('Native receiver client family is unavailable')
        client = provider.client
        if family == 'mysql':
            from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
            from mysql.connector import Error as NativeError
        else:
            from ..providers.mysql_family.mariadb_connections import POOL_ARGUMENTS
            from mariadb import Error as NativeError
        route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        try:
            connection = client._connect({'route': {**route, 'read_timeout': 5, 'write_timeout': 15}})
            captured = adapter.capture(connection)
            if operation == 'catalog': return captured
            native.admit(captured, selected)
            if previous is not None and previous['source']!=captured['identity']:
                raise BinlogArchiveError('The stopped receiver belongs to a different native source identity')
            program = program_identity(adapter, client, route, jobs.prepare_scope(owner, endpoint.id))
            runtime_limit = current_app.config.get('CDEADMIN_' + family.upper() + '_CONTINUOUS_BINLOG_MAX_RUNTIME_SECONDS')
            if runtime_limit is not None and (type(runtime_limit) is not int or not 1 <= runtime_limit <= 2147483647 or
                    selected['timeout_seconds'] is None or selected['timeout_seconds'] > runtime_limit):
                raise BinlogArchiveError('Application policy requires a bounded native receiver duration')
            configuration = digest({'registration': MySQLMonitoringHost._configuration(server),
                'collector_root': str(jobs.root), 'archive_root': str(archives.root), 'runtime_limit': runtime_limit})
            if operation == 'review': return jobs.review(owner, endpoint.id, selected, captured, configuration, program,
                continuation={'writer_scope_index':1,**({'previous_receiver_job_id':previous['job_id']} if previous else {})})
            transport = native.ReceiverTransport(family, client, route, adapter.delegate_credentials(client, route), connection, archives)
            connection = None
            admitted = transport; transport = None
            return jobs.start(request, owner, endpoint.id, {'source': captured['identity'], 'configuration': configuration, 'program': program}, admitted)
        except NativeError as error:
            raise BinlogArchiveError('Native receiver admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()
