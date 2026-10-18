"""Registered native MySQL/MariaDB continuous receiver admission and receipts."""
import socket
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
    if operation == 'list':
        if set(request)-{'offset','limit'}: raise BinlogArchiveError('Invalid native receiver receipt page')
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status','cancel'}:
        if set(request) != {'job_id'}: raise BinlogArchiveError('Select one owned native receiver')
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    adapter = native.adapter(family)
    if operation == 'review':
        if set(request) != {'options'}: raise BinlogArchiveError('Review exact native receiver options')
        selected = native.options(family, request['options'])
    elif operation == 'start':
        reviewed = jobs.load(request.get('job_id'), owner, endpoint.id)
        if reviewed['state'] != 'reviewed': return jobs.start(request, owner, endpoint.id, {}, None)
        selected = reviewed['options']
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
            program = program_identity(adapter, client, route, jobs.prepare_scope(owner, endpoint.id))
            runtime_limit = current_app.config.get('CDEADMIN_' + family.upper() + '_CONTINUOUS_BINLOG_MAX_RUNTIME_SECONDS')
            if runtime_limit is not None and (type(runtime_limit) is not int or not 1 <= runtime_limit <= 2147483647 or
                    selected['timeout_seconds'] is None or selected['timeout_seconds'] > runtime_limit):
                raise BinlogArchiveError('Application policy requires a bounded native receiver duration')
            configuration = digest({'registration': MySQLMonitoringHost._configuration(server),
                'collector_root': str(jobs.root), 'archive_root': str(archives.root), 'runtime_limit': runtime_limit})
            if operation == 'review': return jobs.review(owner, endpoint.id, selected, captured, configuration, program)
            transport = native.ReceiverTransport(family, client, route, adapter.delegate_credentials(client, route), connection, archives)
            connection = None
            admitted = transport; transport = None
            return jobs.start(request, owner, endpoint.id, {'source': captured['identity'], 'configuration': configuration, 'program': program}, admitted)
        except NativeError as error:
            raise BinlogArchiveError('Native receiver admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
    finally:
        if connection is not None: client._discard_failed_session(connection)
        if transport is not None: transport.close()
