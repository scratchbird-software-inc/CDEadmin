"""Durable reviewed server-log administration; missing SQL replies never replay."""
from copy import deepcopy
from pathlib import Path
import threading
import time

from ..providers.mysql_family import mysql_log_purge as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError, capture
from ..providers.mysql_family.mysql_clone import rows
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest
from .mysql_monitoring_host import MySQLMonitoringHost


class PurgeJobs(MySQLBinlogJobs):
    native_module = native
    selection_key = 'purge_selection'
    service_attribute = 'mysql_source_log_purge_jobs'
    root_setting = 'CDEADMIN_MYSQL_LOG_PURGE_ROOT'
    root_name = 'mysql-source-log-purge-receipts'
    store_suffix = '.source-log-purge'
    operation = 'mysql_native_binary_log_purge'
    remote_database_mutation = True
    review_warnings = (
        'Permanently removes native binary logs on the selected database server. This does not remove application archives.',
        'Check required backups and replicas before confirmation. Backup/log dependencies and offline replica requirements are not automatically discovered by this action.',
        'Use an exclusive log administration window. Native TO preserves its boundary file; BEFORE uses native file timestamps in UTC. Its displayed files are potential candidates, not an application prediction of timestamp matches.',
        'Cancellation requests native KILL QUERY when the exact private thread/connection/handshake can be confirmed. Removed files are not restored. Unknown replies require reconciliation and never trigger automatic replay.',
    )

    def public(self, record):
        result = super().public(record)
        from .mysql_binlog_service import _public_capture
        if result.get('result', {}).get('after') is not None:
            result['result']['after'] = _public_capture(result['result']['after'])
        if result.get('reconciliation', {}).get('source') is not None:
            result['reconciliation']['source'] = _public_capture(result['reconciliation']['source'])
        result[self.selection_key] = deepcopy(record['source_state'][self.selection_key])
        result['execution_host'] = deepcopy(record['program']['execution_host'])
        result['backup_dependencies_discovered'] = False
        result['native_log_generation_attested'] = False
        return result

    def run(self, record, transport, signal):
        dispatched = False
        try:
            self.update(record, state='active', phase='checking_native_state')
            def boundary():
                nonlocal dispatched
                if DurableCancellation(self, record, signal).is_set():
                    raise InterruptedError('Native log administration cancelled before dispatch')
                self.update(record, phase='native_dispatch', native_may_have_dispatched=True)
                dispatched = True
            result = transport.execute(record, DurableCancellation(self, record, signal), boundary,
                                       lambda value: self.update(record, **value))
            state = 'native_acknowledged' if result['native_acknowledged'] else (
                'native_failed' if result.get('native_error_returned') else 'unknown')
            self.update(record, state=state, result=result, phase='finished', finished_at=time.time())
        except BaseException as error:
            current = self.load(record['job_id'], record['owner'], record['endpoint_id'])
            state = 'native_acknowledged' if current.get('native_acknowledged') is True else (
                'native_failed' if current.get('native_error_returned') is True else
                'unknown' if dispatched else 'cancelled' if signal.is_set() or isinstance(error, InterruptedError) else 'not_dispatched')
            self.update(record, state=state,
                phase='finished', error=native.error_observation(error),
                error_message=str(error) if isinstance(error, BinlogArchiveError) else None,
                finished_at=time.time())
        finally:
            try:
                transport.close()
            finally:
                with self._maps_lock:
                    item = self.workers.get(record['job_id'])
                    if item and item[0] is threading.current_thread():
                        self.workers.pop(record['job_id'], None)

    def reconcile_source(self, record, observed):
        with self._maps_lock:
            known = self.workers.get(record['job_id'])
            if known and known[0].is_alive():
                raise BinlogArchiveError('The native log administration worker is still active')
        if observed['identity'] != record['source']:
            raise BinlogArchiveError('Native reconciliation reached another source or principal')
        after = native.names(observed)
        before = record['source_state']['purge_selection']['before_names']
        self.update(record, reconciliation={'observed_at': time.time(), 'source': observed,
            'absent_before_names': [name for name in before if name not in after],
            'retained_before_names': [name for name in before if name in after],
            'original_acknowledgement_unchanged': True})
        return self.get(record['job_id'], record['owner'], record['endpoint_id'])


def action(service, server, archives, owner, endpoint, context, operation, request, *, jobs_type=PurgeJobs):
    from flask import current_app
    native = jobs_type.native_module
    if not isinstance(request, dict):
        raise BinlogArchiveError('Select a native source log administration request')
    with service._semantic_lock:
        jobs = getattr(service, jobs_type.service_attribute, None)
        if jobs is None:
            root = current_app.config.get(jobs_type.root_setting) or str(Path(service.operation_bus.store.path).parent / jobs_type.root_name)
            jobs = jobs_type(str(archives.path) + jobs_type.store_suffix, root)
            setattr(service, jobs_type.service_attribute, jobs)
            import atexit
            atexit.register(jobs.close)
    if operation == 'list':
        if set(request) - {'offset', 'limit'}:
            raise BinlogArchiveError('Select a native log administration receipt page')
        return jobs.list(owner, endpoint.id, **request)
    if operation in {'status', 'cancel'}:
        if set(request) != {'job_id'}:
            raise BinlogArchiveError('Select one native log administration receipt')
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint.id)
    record = None
    if operation in {'start', 'reconcile'}:
        record = jobs.load(request.get('job_id'), owner, endpoint.id)
        if operation == 'reconcile' and set(request) != {'job_id'}:
            raise BinlogArchiveError('Select one native log administration receipt')
        if operation == 'start' and record['state'] != 'reviewed':
            return jobs.start(request, owner, endpoint.id, {}, None)
        selected = record['options']
    elif operation == 'review':
        if set(request) != {'options'}:
            raise BinlogArchiveError('Review exact native source log options')
        selected = native.options(request['options'])
    elif operation == 'catalog':
        if request:
            raise BinlogArchiveError('Native source log discovery takes no browser route')
        selected = None
    else:
        raise BinlogArchiveError('Native source log action is unavailable')
    worker = monitor = transport = None
    client = None
    try:
        context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
        provider = service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider, MySQLPilotProvider):
            raise BinlogArchiveError('Native MySQL source log administration is unavailable')
        from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
        route = {key: value for key, value in payload['route'].items() if key not in POOL_ARGUMENTS}
        client = provider.client
        monitor = native.private_connection(client, {**route, 'read_timeout': 5, 'write_timeout': 5})
        observed = capture(monitor)
        if operation == 'catalog':
            from .mysql_binlog_service import _public_capture
            return _public_capture(observed)
        if operation == 'reconcile':
            return jobs.reconcile_source(record, observed)
        chosen = native.selection(monitor, observed, selected)
        captured = deepcopy(observed)
        captured['state'][jobs.selection_key] = chosen
        program = native.program(observed)
        configuration = digest({'registration': MySQLMonitoringHost._configuration(server), 'root': str(jobs.root)})
        if operation == 'review':
            return jobs.review(owner, endpoint.id, selected, captured, configuration, program)
        if chosen != record['source_state'][jobs.selection_key]:
            raise BinlogArchiveError('The native log index or boundary changed; prepare a new review')
        worker = native.private_connection(client, {**route, 'read_timeout': selected['timeout_seconds'], 'write_timeout': 5})
        transport = native.Transport(client, worker, monitor, observed, selected)
        worker = monitor = None
        admitted, transport = transport, None
        return jobs.start(request, owner, endpoint.id,
            {'configuration': configuration, 'source': observed['identity'], 'program': program}, admitted)
    except Exception as error:
        from mysql.connector import Error as NativeError
        if isinstance(error, NativeError):
            raise BinlogArchiveError('Native MySQL source log admission failed (' + str(error.errno) + ', ' + str(error.sqlstate) + ')') from None
        raise
    finally:
        if transport is not None:
            transport.close()
        if client is not None:
            for handle in (worker, monitor):
                if handle is not None:
                    client._discard_failed_session(handle)
