"""Durable holds for managed native backups; holds do not prove recoverability."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import socket
import threading
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..operations.models import OperationBusError
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
        # Registrations can name the same native instance. One owner-wide lock
        # makes new holds and archive deletion atomic across those aliases.
        with self.lock, (directory / '.protection.lock').open('a+b') as lock:
            private_file(Path(lock.name))
            with exclusive_file_lock(lock.fileno()):
                yield JsonOperationStore(path)

    @staticmethod
    def records(store):
        return store.read().get('mysql_backup_protection', {})

    def scoped(self, owner, endpoint):
        return Sink(self, owner, identity(endpoint))

    def list(self, owner, endpoint, offset=0, limit=25, all_registrations=False):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100 or type(all_registrations) is not bool:
            raise BinlogArchiveError('Select a native backup protection page')
        with self.store(owner, endpoint) as store:
            records = ([{**deepcopy(row), 'protection_endpoint_id': scope}
                        for scope, state in self._scoped_states(owner)
                        for row in state.get('mysql_backup_protection', {}).values()]
                       if all_registrations else self.records(store).values())
            rows = sorted(records, key=lambda row: (row['created_at'], row['backup_id']), reverse=True)
        return {'backups': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
                'scope': 'managed_native_dumps_and_clones_for_this_owner' + ('_all_registrations' if all_registrations else '_and_registration'),
                'dependency_resolution': 'conservative_source_hold; not a verified recovery chain',
                'external_backups_discovered': False, 'native_log_generation_attested': False}

    def protections(self, owner, endpoint):
        with self.store(owner, endpoint):
            return self._protections(owner, endpoint)

    def _scoped_states(self, owner):
        """Read while holding the owner lock; never skip an unreadable scope."""
        for path in sorted((self.root / str(owner)).glob('*.json')):
            scope = identity(path.stem)
            if path.is_symlink() or not path.is_file():
                raise BinlogArchiveError('Native backup protection storage identity changed')
            try:
                state = JsonOperationStore(path).read()
            except OperationBusError:
                raise BinlogArchiveError('An owner registration backup protection store is unavailable; archive removal is refused') from None
            yield scope, state

    def _protections(self, owner, endpoint):
        references = []
        for scope, state in self._scoped_states(owner):
            for row in state.get('mysql_backup_protection', {}).values():
                if row['state'] != 'retired':
                    references.append({**deepcopy(row), 'same_registration': scope == endpoint,
                                       'protection_endpoint_id': scope})
            for row in state.get('mysql_recovery_chains', {}).values():
                if row['state'] == 'active':
                    references.append({**deepcopy(row), 'protection_kind': 'recovery_chain',
                                       'protection_endpoint_id': scope})
        return references

    @staticmethod
    def protected(record, references):
        for row in references:
            if record.get('operation') == 'mysql_full_instance_logical_backup':
                if (row.get('protection_kind') == 'recovery_chain' and row.get('backup_instance_job_id') == record.get('job_id') or
                        row.get('protection_kind') != 'recovery_chain' and row.get('native_instance_job_id') == record.get('job_id')):
                    return True
                continue
            if row.get('protection_kind') == 'recovery_chain':
                if any(item['job_id'] == record.get('job_id') and
                       item['operation'] == record.get('operation') and
                       item['endpoint_id'] == record.get('endpoint_id')
                       for item in row['archives']):
                    return True
            elif row['source']['server_uuid'] == record['source']['server_uuid'] or (
                    row.get('same_registration', True) and
                    row['state'] not in {'native_dump_returned', 'native_clone_returned'}):
                return True
        return False

    def begin_clone(self, owner, endpoint, clone):
        """Persist known-registration holds before admitting native SQL.

        Remote CLONE does not attest its protocol source UUID. Both the reviewed
        donor and recipient registrations retain all their archives, including
        after a returned native statement. A partial write leaves a conservative
        hold and never authorizes native dispatch.
        """
        donor = clone.get('donor')
        scopes = [(endpoint, clone['source'], 'recipient' if donor else 'local')]
        if donor:
            scopes.append((donor['endpoint_id'], donor['native_identity'], 'registered_donor'))
        tickets = []
        for scope, source, role in scopes:
            backup_id = identity(clone['job_id'])
            expected = {'backup_id': backup_id, 'backup_kind': 'mysql_native_physical_clone',
                'native_clone_job_id': backup_id, 'clone_role': role,
                'source': {name: deepcopy(source[name]) for name in ('server_uuid', 'version', 'authenticated_principal', 'active_role') if name in source},
                'database': 'InnoDB instance clone', 'artifact_path': clone['options']['destination'],
                'native_protocol_source_uuid_attested': donor is None,
                'execution_host': deepcopy(clone['execution_host'])}
            with self.store(owner, scope) as store:
                previous = self.records(store).get(backup_id)
                if previous is not None:
                    if any(previous.get(key) != value for key, value in expected.items()):
                        raise BinlogArchiveError('Native clone protection differs from its admitted job')
                    if previous['state'] == 'retired':
                        raise BinlogArchiveError('This native clone protection was retired; prepare a new clone')
                else:
                    value = {**expected, 'created_at': time.time(), 'state': 'pending_native_reply',
                        'native_log_generation_attested': False, 'database_recovery_verified': False,
                        'native_clone_completion_acknowledged': False, 'automatic_native_retry': False}
                    store.change(lambda state: state.setdefault('mysql_backup_protection', {}).update({backup_id: value}))
            tickets.append(Ticket(self.scoped(owner, scope), backup_id))
        return tickets

    @contextmanager
    def guard(self, owner, endpoint, record):
        # The same lock admits a new backup intent and archive removal. A new
        # intent cannot appear between this check and its file deletion.
        with self.store(owner, endpoint) as store:
            refs = self._protections(owner, endpoint)
            if not record.get('artifact_removed') and self.protected(record, refs):
                raise BinlogArchiveError('Managed backup protection retains this archive; inspect and explicitly retire its backup or recovery-chain holds before removal')
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
        if options.get('_instance_scope') is True:
            record.update(backup_kind='mysql_native_logical_instance',
                          native_instance_options=deepcopy(options['native_options']),
                          native_instance_job_id=identity(options['_instance_job_id']))
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

    def clone_returned(self, outcome, observed):
        with self.sink.registry.store(self.sink.owner, self.sink.endpoint) as store:
            record = Registry.records(store)[self.backup_id]
        if record['state'] == 'retired':
            return {**record, 'native_clone_acknowledged_after_retirement': outcome.get('acknowledged') is True}
        acknowledged = outcome.get('acknowledged') is True
        known_source = record['native_protocol_source_uuid_attested']
        status = (observed or {}).get('status') if (observed or {}).get('job_correlated') else None
        boundary = {name: status[name] for name in ('binlog_file', 'binlog_position', 'gtid_executed_prefix',
            'gtid_executed_length', 'gtid_executed_sha256', 'gtid_executed_truncated') if name in (status or {})}
        return self.update(state=('native_clone_returned' if known_source else 'native_clone_returned_unattested_source')
            if acknowledged else 'unconfirmed_native_reply', native_completed_at=time.time(),
            native_clone_completion_acknowledged=acknowledged, native_boundary=boundary,
            native_boundary_observed=status is not None, native_clone_observation_correlated=status is not None,
            native_backup_acknowledgement_unchanged=True)

    def completed(self, top, done, result, *, acknowledged=True):
        with self.sink.registry.store(self.sink.owner, self.sink.endpoint) as store:
            record = Registry.records(store)[self.backup_id]
        if record['state'] == 'retired':
            return {**record, 'native_dump_acknowledged_after_retirement': acknowledged}
        source = top.get('source', {})
        instance = record.get('backup_kind') == 'mysql_native_logical_instance'
        scope_matches = (top.get('origin') == 'dumpInstance' and isinstance(top.get('schemas'), list)
                         if instance else top.get('origin') == 'dumpSchemas' and top.get('schemas') == [record['database']])
        version_matches = (str(top.get('serverVersion')).split('-')[0] == str(record['source'].get('version')).split('-')[0]
                           if instance else top.get('serverVersion') == record['source']['version'])
        if (source.get('sysvars', {}).get('server_uuid') != record['source']['server_uuid'] or
                not version_matches or not scope_matches or not isinstance(done.get('end'), str)):
            raise BinlogArchiveError('Native dump source metadata differs from its protection intent')
        boundary = source.get('binlog', {})
        boundary = {key: str(boundary[key]) for key in ('file', 'position', 'gtidExecuted') if key in boundary}
        files = result['artifact_manifest']
        known_ack = record.get('native_dump_completion_acknowledged') is True or acknowledged is True
        return self.update(state='native_dump_returned' if known_ack else 'native_dump_artifact_verified', native_completed_at=time.time(),
            native_dump_completion_acknowledged=known_ack, native_artifact_completion_observed=True,
            native_boundary=boundary, native_consistent=top.get('consistent') is True,
            native_gtid_snapshot_inconsistent=top.get('gtidExecutedInconsistent') is True,
            artifact_manifest_digest=digest(files), artifact_file_count=len(files),
            artifact_total_bytes=str(result['artifact_total_bytes']),
            **({'native_schemas': deepcopy(top['schemas']), 'native_users': deepcopy(top.get('users'))} if instance else {}))


def finish_clone(tickets, outcome, observed):
    """Bookkeeping cannot replace a native acknowledgement or cause replay."""
    results = []
    for ticket in tickets:
        try:
            result = ticket.clone_returned(outcome, observed)
        except Exception as error:
            result = {'backup_id': ticket.backup_id, 'state': 'pending_or_unconfirmed',
                      'error_type': type(error).__name__, 'native_backup_acknowledgement_unchanged': True}
        results.append({'endpoint_id': ticket.sink.endpoint, **result})
    return results


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
    if operation == 'list' and isinstance(request, dict) and not set(request) - {'offset', 'limit', 'all_registrations'}:
        return registry.list(owner, endpoint, **request)
    if operation == 'review_retire' and isinstance(request, dict) and set(request) in ({'backup_id'}, {'backup_id', 'protection_endpoint_id'}):
        scope = identity(request.get('protection_endpoint_id', endpoint))
        return {**registry.review_retire(owner, scope, request['backup_id']), 'protection_endpoint_id': scope}
    if operation == 'retire' and isinstance(request, dict):
        selected = dict(request); scope = identity(selected.pop('protection_endpoint_id', endpoint))
        return registry.retire(owner, scope, selected)
    raise BinlogArchiveError('Select a managed native backup protection action')
