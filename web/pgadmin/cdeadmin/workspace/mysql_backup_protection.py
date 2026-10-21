"""Durable holds for managed native dumps; holds do not prove recoverability."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import socket
import threading
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .mysql_binlog_jobs import digest, identity


class Registry:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    @contextmanager
    def store(self, owner, endpoint):
        if type(owner) is not int or owner <= 0:
            raise BinlogArchiveError('Native backup protection owner is unavailable')
        endpoint = identity(endpoint)
        directory = self.root / str(owner)
        for path in (self.root, directory):
            path.mkdir(parents=True, exist_ok=True, mode=0o700); private_directory(path)
        path = directory / (endpoint + '.json')
        with self.lock, (directory / (endpoint + '.lock')).open('a+b') as lock:
            private_file(Path(lock.name))
            with exclusive_file_lock(lock.fileno()):
                yield JsonOperationStore(path)

    @staticmethod
    def records(store):
        return store.read().get('mysql_backup_protection', {})

    def scoped(self, owner, endpoint):
        return Sink(self, owner, identity(endpoint))

    def list(self, owner, endpoint, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise BinlogArchiveError('Select a native backup protection page')
        with self.store(owner, endpoint) as store:
            rows = sorted(self.records(store).values(), key=lambda row: (row['created_at'], row['backup_id']), reverse=True)
        return {'backups': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
                'scope': 'managed_graphical_dumps_for_this_owner_and_registration',
                'dependency_resolution': 'conservative_source_hold; not a verified recovery chain',
                'external_backups_discovered': False, 'native_log_generation_attested': False}

    def protections(self, owner, endpoint):
        with self.store(owner, endpoint) as store:
            return [deepcopy(row) for row in self.records(store).values() if row['state'] != 'retired']

    @staticmethod
    def protected(record, references):
        return any(row['state'] != 'native_dump_returned' or
                   row['source']['server_uuid'] == record['source']['server_uuid'] for row in references)

    @contextmanager
    def guard(self, owner, endpoint, record):
        # The same lock admits a new backup intent and archive removal. A new
        # intent cannot appear between this check and its file deletion.
        with self.store(owner, endpoint) as store:
            refs = [row for row in self.records(store).values() if row['state'] != 'retired']
            if not record.get('artifact_removed') and self.protected(record, refs):
                raise BinlogArchiveError('Managed backup protection retains this archive; inspect and explicitly retire its backup holds before removal')
            yield

    def review_retire(self, owner, endpoint, backup_id):
        with self.store(owner, endpoint) as store:
            record = self.records(store).get(identity(backup_id))
            if record is None or record['state'] == 'retired':
                raise BinlogArchiveError('Select an active managed backup protection')
            review = {'backup_id': backup_id, 'snapshot': digest(record), 'expires_at': time.time() + 300,
                      'review_id': str(uuid.uuid4()), 'owner': owner, 'endpoint_id': endpoint}
            review['review_digest'] = digest(review)
            store.change(lambda state: state.setdefault('mysql_backup_retire_reviews', {}).update({review['review_id']: review}))
        return {key: value for key, value in review.items() if key not in {'owner', 'endpoint_id'}} | {
            'backup': record, 'warning': 'Retire this backup from archive protection and recovery planning. Backup files remain. Required archives can then be removed. No database recovery is established.'}

    def retire(self, owner, endpoint, request):
        if not isinstance(request, dict) or set(request) != {'review_id', 'review_digest', 'confirmed'} or request['confirmed'] is not True:
            raise BinlogArchiveError('Confirm the exact backup protection retirement review')
        with self.store(owner, endpoint) as store:
            state = store.read(); review = state.get('mysql_backup_retire_reviews', {}).get(identity(request['review_id']))
            if review is None or review['review_digest'] != request['review_digest']:
                raise BinlogArchiveError('Native backup retirement review is unavailable')
            record = state.get('mysql_backup_protection', {}).get(review['backup_id'])
            if record is None:
                raise BinlogArchiveError('Native backup protection is unavailable')
            if record['state'] == 'retired' and record.get('retirement_review_id') == review['review_id']:
                return record
            if review['expires_at'] < time.time() or digest(record) != review['snapshot']:
                raise BinlogArchiveError('Native backup protection changed; prepare a new retirement review')
            def change(candidate):
                row = candidate['mysql_backup_protection'][record['backup_id']]
                row.update(state='retired', retired_at=time.time(), retirement_review_id=review['review_id'],
                           backup_files_removed=False, automatic_native_retry=False)
            store.change(change)
            return self.records(store)[record['backup_id']]


class Sink:
    def __init__(self, registry, owner, endpoint):
        self.registry, self.owner, self.endpoint = registry, owner, endpoint

    def begin(self, source, database, path, options):
        backup_id = str(uuid.uuid4())
        record = {'backup_id': backup_id, 'source': deepcopy(source), 'database': database,
                  'artifact_path': path, 'created_at': time.time(), 'state': 'pending_native_reply',
                  'execution_host': socket.gethostname(), 'native_log_generation_attested': False,
                  'database_recovery_verified': False, 'automatic_native_retry': False}
        with self.registry.store(self.owner, self.endpoint) as store:
            store.change(lambda state: state.setdefault('mysql_backup_protection', {}).update({backup_id: record}))
        return Ticket(self, backup_id)


class Ticket:
    def __init__(self, sink, backup_id):
        self.sink, self.backup_id = sink, backup_id

    def update(self, **values):
        with self.sink.registry.store(self.sink.owner, self.sink.endpoint) as store:
            def change(state):
                record = state['mysql_backup_protection'][self.backup_id]
                if record['state'] == 'retired':
                    raise BinlogArchiveError('The pending backup hold was retired; inspect the returned dump separately')
                record.update(deepcopy(values), updated_at=time.time())
            store.change(change)
            return Registry.records(store)[self.backup_id]

    def unconfirmed(self):
        return self.update(state='unconfirmed_native_reply')

    def completed(self, top, done, result):
        with self.sink.registry.store(self.sink.owner, self.sink.endpoint) as store:
            record = Registry.records(store)[self.backup_id]
        if record['state'] == 'retired':
            return {**record, 'native_dump_acknowledged_after_retirement': True}
        source = top.get('source', {})
        if (source.get('sysvars', {}).get('server_uuid') != record['source']['server_uuid'] or
                top.get('serverVersion') != record['source']['version'] or top.get('origin') != 'dumpSchemas' or
                top.get('schemas') != [record['database']] or not isinstance(done.get('end'), str)):
            raise BinlogArchiveError('Native dump source metadata differs from its protection intent')
        boundary = source.get('binlog', {})
        boundary = {key: str(boundary[key]) for key in ('file', 'position', 'gtidExecuted') if key in boundary}
        files = result['artifact_manifest']
        return self.update(state='native_dump_returned', native_completed_at=time.time(),
            native_dump_completion_acknowledged=True,
            native_boundary=boundary, native_consistent=top.get('consistent') is True,
            native_gtid_snapshot_inconsistent=top.get('gtidExecutedInconsistent') is True,
            artifact_manifest_digest=digest(files), artifact_file_count=len(files),
            artifact_total_bytes=str(result['artifact_total_bytes']))


def manager(service):
    from flask import current_app
    with service._semantic_lock:
        registry = getattr(service, 'mysql_backup_protection', None)
        if registry is None:
            if not isinstance(getattr(service.operation_bus, 'store', None), JsonOperationStore):
                raise BinlogArchiveError('Managed backup protection requires durable application storage')
            path = Path(service.operation_bus.store.path).parent / 'mysql-backup-protection'
            root = current_app.config.get('CDEADMIN_MYSQL_BACKUP_PROTECTION_ROOT') or path
            registry = service.mysql_backup_protection = Registry(root)
        return registry


@contextmanager
def capture_scope(service, context, owner):
    if context.profile_id != 'mysql-native':
        yield
        return
    from ..providers.mysql_family.mysql_backup_events import observe
    class DeferredSink:
        def begin(self, *args):
            return manager(service).scoped(owner, context.endpoint_id).begin(*args)
    with observe(DeferredSink()):
        yield


def action(service, owner, endpoint, operation, request):
    registry = manager(service)
    if operation == 'list' and isinstance(request, dict) and not set(request) - {'offset', 'limit'}:
        return registry.list(owner, endpoint, **request)
    if operation == 'review_retire' and isinstance(request, dict) and set(request) == {'backup_id'}:
        return registry.review_retire(owner, endpoint, request['backup_id'])
    if operation == 'retire':
        return registry.retire(owner, endpoint, request)
    raise BinlogArchiveError('Select a managed native backup protection action')
