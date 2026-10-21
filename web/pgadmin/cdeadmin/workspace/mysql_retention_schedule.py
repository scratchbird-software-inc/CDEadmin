"""Revocable local archive retention with durable, non-replaying occurrences."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
import threading
import time

from ..operations.fileio import private_directory, private_file
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .continuous_binlog_tails import file_claim
from .mysql_binlog_jobs import ACTIVE, MySQLBinlogJobs, digest, identity, review_digest
from . import mysql_archive_retention as retention


class ScheduleJobs(MySQLBinlogJobs):
    operation = 'mysql_scheduled_archive_retention'
    review_warnings = (
        'Authorize future scans of this exact native source, principal and role, including new archives. Each occurrence removes at most100 eligible archives on the recorded application host and retains receipts.',
        'Protect all archives required by base backups or recovery targets. Age/count rules do not discover backup dependencies or prove recovery coverage. Native server logs are unchanged.',
        'The policy expires and can be disabled. Changed registration, application adapter or execution host suspends it. Interrupted occurrences require explicit reconciliation and a new policy review; they never restart automatically.',
    )

    def public(self, record):
        return {**super().public(record), 'automatic_future_scans': record['state'] == 'enabled',
            'automatic_occurrence_retry': False, 'backup_dependencies_discovered': False}


def selected(value):
    if not isinstance(value, dict) or set(value) != {'policy', 'interval_seconds', 'expires_after_days'}:
        raise BinlogArchiveError('Select an archive policy, scan interval and expiry')
    retention.policy(value['policy'])
    if type(value['interval_seconds']) is not int or not 60 <= value['interval_seconds'] <= 31536000:
        raise BinlogArchiveError('Select a scan interval between60 seconds and one year')
    if type(value['expires_after_days']) is not int or not 1 <= value['expires_after_days'] <= 365:
        raise BinlogArchiveError('Select a policy lifetime between1 and365 days')
    return deepcopy(value)


def program(archives):
    current = retention.binding(archives)
    return {**current['program'], 'archive_configuration': current['configuration'],
        'archive_kind': current['source'], 'scheduler_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class ScheduledTransport(retention.RetentionTransport):
    def __init__(self, host, grant, archives):
        super().__init__(archives)
        self.host, self.grant = host, grant

    def execute(self, record, directory, cancel, progress):
        removed = []
        for item in record['continuation']['archives']:
            if cancel.is_set():
                raise InterruptedError('Scheduled retention cancelled')
            self.host.require(self.grant, record['job_id'])
            # Recheck the minimum count and protections at each dispatch;
            # a concurrent manual removal must not lower the retained floor.
            current, _counts, _cutoff, _total = retention.candidates(self.archives, record['owner'], record['endpoint_id'],
                record['options'], native_source=self.grant['source'])
            if item['job_id'] not in {row['job_id'] for row in current}:
                raise BinlogArchiveError('Scheduled retention eligibility changed; review the interrupted occurrence')
            progress({'removed_job_ids': list(removed), 'current_job_id': item['job_id']})
            retention.remove(self.archives, item['job_id'], record['owner'], record['endpoint_id'], item['job_id'],
                expected=item, retention_id=record['job_id'])
            removed.append(item['job_id'])
            progress({'removed_job_ids': list(removed), 'current_job_id': None})
        return {'removed_job_ids': removed, 'scheduled_policy_id': self.grant['job_id'],
            'receipts_removed': False, 'remote_database_mutation': False, 'database_recovery_verified': False}


class ScheduleHost:
    def __init__(self, app, service):
        self.app, self.service = app, service
        store = service.operation_bus.store
        root = app.config.get('CDEADMIN_MYSQL_RETENTION_SCHEDULE_ROOT') or str(store.path.parent / 'mysql-retention-schedules')
        self.jobs = ScheduleJobs(str(store.path) + '.mysql-retention-schedules', root)
        self.enabled = self.jobs.root / 'enabled'
        self.stop = threading.Event(); self.lock = threading.RLock(); self.thread = None
        self.poll_seconds = app.config.get('CDEADMIN_MYSQL_RETENTION_POLL_SECONDS', 5)
        if type(self.poll_seconds) not in {int, float} or not .1 <= self.poll_seconds <= 60:
            raise BinlogArchiveError('Invalid archive retention scheduler polling interval')

    def marker(self, job_id):
        return self.enabled / identity(job_id)

    def authority(self, grant):
        from pgadmin.model import Server, User
        from .mysql_monitoring_host import MySQLMonitoringHost
        if User.query.filter_by(id=grant['owner'], active=True).first() is None:
            raise BinlogArchiveError('The archive policy owner is unavailable')
        server = Server.query.filter_by(id=grant['continuation']['server_id'], user_id=grant['owner']).first()
        if server is None or server.endpoint_profile is None or server.endpoint_profile.id != grant['endpoint_id']:
            raise BinlogArchiveError('The archive policy registration is unavailable')
        from .mysql_binlog_service import manager as shell_manager
        from .mysql_raw_binlog_service import manager as raw_manager
        kind = grant['continuation']['archive_kind']
        if kind not in {'shell', 'raw'}:
            raise BinlogArchiveError('The archive policy kind changed')
        archives, _owner, _endpoint, _context = (raw_manager if kind == 'raw' else shell_manager)(self.service, server)
        if (grant['configuration'] != MySQLMonitoringHost._configuration(server) or
                grant['program'] != program(archives) or
                Path(grant['execution_host']['filesystem_scope']) != self.jobs.scope(grant['owner'], grant['endpoint_id'])):
            raise BinlogArchiveError('Archive policy registration, adapter or execution host changed')
        return archives

    def require(self, grant, occurrence=None):
        with self.app.app_context():
            current = self.jobs.load(grant['job_id'], grant['owner'], grant['endpoint_id'])
            if (current['state'] != 'enabled' or current.get('valid_until', 0) <= time.time() or
                    review_digest(current) != current['review_digest'] or
                    occurrence is not None and current.get('last_occurrence_id') != occurrence or self.stop.is_set()):
                raise BinlogArchiveError('The scheduled archive policy is inactive, expired or changed')
            return self.authority(current)

    def start(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            if not self.enabled.exists():
                return
            self.stop.clear()
            self.thread = threading.Thread(target=self.loop, daemon=True, name='mysql-archive-retention-scheduler')
            self.thread.start()

    def close(self):
        self.stop.set()
        with self.lock: thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        stopped = not (thread and thread.is_alive())
        for value in vars(self.service).copy().values():
            if isinstance(value, retention.RetentionJobs):
                stopped = value.close() and stopped
        return stopped

    def loop(self):
        while not self.stop.wait(self.poll_seconds):
            try:
                retention.directory_identity(self.enabled)
                for entry in self.enabled.iterdir():
                    if self.stop.is_set():
                        break
                    try:
                        identity(entry.name)
                        try:
                            info = entry.lstat()
                        except FileNotFoundError:
                            # A concurrent disable removes only this marker;
                            # its durable policy/occurrence receipts remain.
                            continue
                        if not stat.S_ISREG(info.st_mode) or info.st_size or getattr(info, 'st_file_attributes', 0) & 0x400:
                            raise BinlogArchiveError('The archive schedule index changed')
                        self.tick(entry.name)
                    except Exception as error:
                        self.app.logger.error('Archive retention schedule requires attention: %s (%s)', entry.name, type(error).__name__)
            except Exception:
                self.app.logger.error('Archive retention schedule index is unavailable')

    def read(self, job_id):
        with self.jobs.store(job_id) as store:
            records = store.read().get('mysql_binlog_jobs', {})
            grant = records.get(job_id)
            if grant is None:
                raise BinlogArchiveError('The archive schedule receipt is unavailable')
            return self.jobs.record({'mysql_binlog_jobs': records}, job_id, grant['owner'], grant['endpoint_id'])

    def tick(self, job_id, *, force=False):
        grant = self.read(job_id)
        try:
            # Every web process can observe due policies; this claim chooses
            # one creator. The durable occurrence is bound before dispatch.
            with file_claim(self.jobs.directory(grant)):
                grant = self.read(job_id)
                if grant['state'] == 'preparing':
                    self.jobs.update(grant, state='attention_required', automatic_retry=False,
                        error_message='The previous policy scan was interrupted; review a new policy', suspended_at=time.time())
                    return self.jobs.get(job_id, grant['owner'], grant['endpoint_id'])
                if grant['state'] != 'enabled':
                    return self.jobs.public(grant)
                try:
                    archives = self.require(grant)
                    jobs = retention.manager(self.service, archives)
                    previous = grant.get('last_occurrence_id')
                    if previous:
                        receipt = jobs.get(previous, grant['owner'], grant['endpoint_id'])
                        if receipt['state'] in ACTIVE:
                            return self.jobs.public(grant)
                        if receipt['state'] != 'completed':
                            raise BinlogArchiveError('The previous occurrence is unresolved; reconcile it and review a new policy')
                    if not force and grant.get('next_scan_at', 0) > time.time():
                        return self.jobs.public(grant)
                    self.jobs.update(grant, state='preparing', scan_started_at=time.time(),
                        next_scan_at=time.time() + grant['options']['interval_seconds'])
                    plan = retention.prepare(jobs, archives, grant['owner'], grant['endpoint_id'], grant['options']['policy'],
                        native_source=grant['source'], scheduled_policy_id=grant['job_id'])
                    # Do not overwrite a concurrent revocation after hashing.
                    with self.jobs.store(job_id) as store:
                        def publish(state):
                            current = self.jobs.record(state, job_id, grant['owner'], grant['endpoint_id'])
                            if current['state'] != 'preparing':
                                raise BinlogArchiveError('The scheduled archive policy changed while preparing')
                            current.update(state='enabled', last_scan_at=time.time(), last_scan_empty=plan is None)
                            if plan is not None:
                                current['last_occurrence_id'] = plan['job_id']
                        store.change(publish)
                    if plan is not None:
                        self.require(grant, plan['job_id'])
                        jobs.start({'job_id': plan['job_id'], 'review_digest': plan['review_digest'], 'confirmed': True},
                            grant['owner'], grant['endpoint_id'], retention.binding(archives), ScheduledTransport(self, grant, archives))
                except Exception as error:
                    with self.jobs.store(job_id) as store:
                        def suspend(state):
                            current = self.jobs.record(state, job_id, grant['owner'], grant['endpoint_id'])
                            if current['state'] in {'enabled', 'preparing'}:
                                current.update(state='attention_required', error_type=type(error).__name__,
                                    error_message=str(error) if isinstance(error, BinlogArchiveError) else 'Scheduled retention could not complete',
                                    suspended_at=time.time(), automatic_retry=False)
                        store.change(suspend)
                return self.jobs.get(job_id, grant['owner'], grant['endpoint_id'])
        except BinlogArchiveError as error:
            if str(error).startswith('Another operation'):
                return self.jobs.get(job_id, grant['owner'], grant['endpoint_id'])
            raise

    def action(self, server, archives, owner, endpoint, operation, request):
        if operation == 'retention_schedule_review':
            if set(request) != {'anchor_job_id', 'options'}:
                raise BinlogArchiveError('Review a policy for one retained native source archive')
            options = selected(request['options'])
            anchor = archives.load(request['anchor_job_id'], owner, endpoint)
            if (anchor['state'] not in retention.RETAINED or anchor.get('artifact_removed') or anchor.get('artifact_removal') or
                    anchor.get('native_process_termination_confirmed') is not True or not anchor.get('result', {}).get('artifact')):
                raise BinlogArchiveError('Select a retained verified source archive')
            from .mysql_monitoring_host import MySQLMonitoringHost
            return self.jobs.review(owner, endpoint, options, {'identity': anchor['source'], 'state': {}},
                MySQLMonitoringHost._configuration(server), program(archives),
                {'anchor_job_id': anchor['job_id'], 'server_id': server.id,
                 'archive_kind': 'raw' if archives.operation == 'mysql_closed_raw_binary_log_archive' else 'shell'})
        if operation == 'retention_schedule_list':
            if set(request) - {'offset', 'limit'}:
                raise BinlogArchiveError('Select one schedule receipt page')
            offset, limit = request.get('offset', 0), request.get('limit', 25)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise BinlogArchiveError('Invalid archive policy page')
            rows, total, unavailable, scanned = [], 0, [], 0
            kind = 'raw' if archives.operation == 'mysql_closed_raw_binary_log_archive' else 'shell'
            while True:
                page = self.jobs.list(owner, endpoint, offset=scanned, limit=100)
                unavailable.extend(page['unavailable_job_ids'])
                for row in page['jobs']:
                    if row['continuation']['archive_kind'] == kind:
                        if offset <= total < offset + limit:
                            rows.append(row)
                        total += 1
                if not page['more']:
                    break
                scanned += 100
            return {'jobs': rows, 'total': total, 'offset': offset, 'limit': limit, 'more': total > offset + limit,
                'unavailable_job_ids': unavailable}
        if operation == 'retention_schedule_status':
            if set(request) != {'job_id'}:
                raise BinlogArchiveError('Select one archive policy')
            result = self.jobs.get(request['job_id'], owner, endpoint)
            if result['continuation']['archive_kind'] != ('raw' if archives.operation == 'mysql_closed_raw_binary_log_archive' else 'shell'):
                raise BinlogArchiveError('Select the matching archive policy kind')
            if result.get('last_occurrence_id'):
                result['last_occurrence'] = retention.manager(self.service, archives).get(result['last_occurrence_id'], owner, endpoint)
            return result
        if operation not in {'retention_schedule_enable', 'retention_schedule_disable', 'retention_schedule_scan'}:
            raise BinlogArchiveError('The archive scheduling action is unavailable')
        fields = {'job_id', 'confirmed'} | ({'review_digest'} if operation == 'retention_schedule_enable' else set())
        if set(request) != fields or request.get('confirmed') is not True:
            raise BinlogArchiveError('Confirm this exact archive policy action')
        grant = self.jobs.load(request['job_id'], owner, endpoint)
        if grant['continuation']['archive_kind'] != ('raw' if archives.operation == 'mysql_closed_raw_binary_log_archive' else 'shell'):
            raise BinlogArchiveError('Select the matching archive policy kind')
        if operation == 'retention_schedule_scan':
            if grant['state'] != 'enabled':
                raise BinlogArchiveError('Select an enabled archive policy')
            return self.tick(grant['job_id'], force=True)
        if operation == 'retention_schedule_disable':
            with self.jobs.store(grant['job_id']) as store:
                def disable(state):
                    current = self.jobs.record(state, grant['job_id'], owner, endpoint)
                    current.update(state='disabled', disabled_at=time.time())
                store.change(disable)
            self.marker(grant['job_id']).unlink(missing_ok=True)
            if grant.get('last_occurrence_id'):
                retention.manager(self.service, archives).cancel(grant['last_occurrence_id'], owner, endpoint)
            return self.jobs.get(grant['job_id'], owner, endpoint)
        self.authority(grant)
        self.enabled.mkdir(parents=True, exist_ok=True, mode=0o700); private_directory(self.enabled)
        retention.directory_identity(self.enabled)
        with self.jobs.store(grant['job_id']) as store:
            def enable(state):
                current = self.jobs.record(state, grant['job_id'], owner, endpoint)
                if current['review_digest'] != request['review_digest'] or review_digest(current) != current['review_digest']:
                    raise BinlogArchiveError('The archive policy review changed')
                if current['state'] != 'reviewed':
                    return
                if time.time() > current['expires_at']:
                    raise BinlogArchiveError('The archive policy review expired')
                marker = self.marker(current['job_id'])
                if marker.exists() or marker.is_symlink():
                    info = marker.lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_size or getattr(info, 'st_file_attributes', 0) & 0x400 or marker.resolve() != marker:
                        raise BinlogArchiveError('The archive schedule marker changed')
                else:
                    with marker.open('xb') as stream:
                        private_file(marker); stream.flush(); os.fsync(stream.fileno())
                if os.name != 'nt':
                    descriptor = os.open(self.enabled, os.O_RDONLY | os.O_DIRECTORY)
                    try: os.fsync(descriptor)
                    finally: os.close(descriptor)
                current.update(state='enabled', enabled_at=time.time(), next_scan_at=time.time(),
                    valid_until=time.time() + current['options']['expires_after_days'] * 86400)
            store.change(enable)
        self.start()
        return self.jobs.get(grant['job_id'], owner, endpoint)


def init_app(app, service):
    from ..operations.store import JsonOperationStore
    if not isinstance(getattr(service.operation_bus, 'store', None), JsonOperationStore):
        return
    import atexit
    host = ScheduleHost(app, service)
    service.mysql_retention_scheduler = host
    app.register_before_app_start(host.start)
    atexit.register(host.close)
