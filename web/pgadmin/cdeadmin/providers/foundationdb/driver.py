"""Owned FoundationDB transactions and bounded native range delivery."""
import contextvars
import hashlib
from pathlib import Path
import json

from .client import FoundationDBBackend
from ..native_distributed import NativeDistributedError, NativeResult
from ..native_key_value import decode_value
from ..retained_native import RetainedNativeClient


class DatabaseOwner:
    def __init__(self, database):
        self.database = database
        self.transaction = None
        self.state = 'idle'
        self.version = None
        self.error_code = None

    def __getattr__(self, name):
        return getattr(self.database, name)


class FoundationDBDriverBackend(FoundationDBBackend):
    ATOMIC = frozenset(
        ('add',
         'bit_and',
         'bit_or',
         'bit_xor',
         'append_if_fits',
         'max',
         'min',
         'byte_min',
         'byte_max',
         'compare_and_clear',
         'set_versionstamped_key',
         'set_versionstamped_value'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._temporary_owners = contextvars.ContextVar(
            'fdb_owners', default=None)

    def _configure_network(self, route, password):
        # Network options are process-wide, not provider-generation scoped.
        cluster = Path(route['cluster_file']).read_text().strip()
        endpoints = cluster.rsplit('@', 1)[-1].split(',')
        secure = route['tls_mode'] == 'verify-peers'
        if not endpoints or any(x.strip().endswith(':tls') != secure
                                for x in endpoints):
            raise NativeDistributedError(
                'Cluster endpoints disagree with TLS policy')
        files = []
        for field in ('tls_ca_file', 'tls_certificate_file', 'tls_key_file'):
            path = route.get(field)
            files.append(hashlib.sha256(Path(path).read_bytes()).digest()
                         if path else None)
        fingerprint = (tuple(files), hashlib.sha256(
            (password or '').encode()).digest())
        with self._network_lock:
            admitted = getattr(FoundationDBDriverBackend,
                               '_driver_security_fingerprint', None)
            if admitted is not None and admitted != fingerprint:
                raise NativeDistributedError(
                    'FoundationDB TLS changes require a new process')
            super()._configure_network(route, password)
            owner = FoundationDBDriverBackend
            owner._driver_security_fingerprint = fingerprint

    def open_session(self, request):
        with self._network_lock:
            database = super().open_session(request)
            route = self._database_routes.pop(id(database))
            self._databases.remove(database)
            owner = DatabaseOwner(database)
            self._databases.append(owner)
            self._database_routes[id(owner)] = route
            temporary = self._temporary_owners.get()
            if temporary is not None:
                temporary.append(owner)
            return owner

    def _temporary(self, method, request):
        owners = []
        token = self._temporary_owners.set(owners)
        try:
            return method(request)
        finally:
            self._temporary_owners.reset(token)
            for owner in owners:
                self.close_session(owner)

    def list_resources(self, request):
        return self._temporary(super().list_resources, request)

    def apply_admin_operation(self, request):
        return self._temporary(super().apply_admin_operation, request)

    def read_admin_rows(self, request):
        return self._temporary(super().read_admin_rows, request)

    def describe_transaction(self, owner):
        return dict(super().describe_transaction(owner),
                    native_state=owner.state,
                    committed_version=owner.version,
                    automatic_mutation_retry=False,
                    transaction_actions=['begin', 'commit', 'rollback'])

    def control_transaction(self, owner, action):
        tx = owner.transaction
        if action == 'begin':
            if tx is not None:
                raise NativeDistributedError('FoundationDB transaction active')
            owner.transaction = self._transaction(owner)
            owner.state, owner.version = 'active', None
            return
        if tx is None:
            raise NativeDistributedError(
                'FoundationDB transaction unavailable')
        # Detach before a decision: a lost commit response is never replayed.
        owner.transaction = None
        if action == 'commit':
            owner.state = 'commit-unknown'
            try:
                tx.commit().wait()
            except Exception as exc:
                owner.error_code = getattr(exc, 'code', None)
                raise
            owner.version = str(tx.get_committed_version())
            owner.state = 'committed'
        elif action == 'rollback':
            tx.cancel()
            owner.state = 'cancelled-locally'
        else:
            owner.transaction = tx
            raise NativeDistributedError('FoundationDB decision unavailable')

    @staticmethod
    def _page(rows, operation, offset=0, **native):
        return NativeResult('key_value', 'entries', rows,
                            {'fields': ['key', 'value'], 'encoding': 'hex'},
                            dict(operation=operation, row_offset=offset,
                                 encoding='hex', **native))

    def iterate(self, owner, command, parameters):
        if not isinstance(command, dict) or parameters:
            raise NativeDistributedError('FoundationDB requires JSON command')
        if 'snapshot' in command and type(command['snapshot']) is not bool:
            raise NativeDistributedError('FoundationDB snapshot flag invalid')
        operation = command.get('operation')
        if operation in {'begin', 'commit', 'rollback'}:
            self.control_transaction(owner, operation)
            yield self._page([], operation, state=owner.state,
                             committed_version=owner.version)
            return
        if operation not in {'get', 'set', 'clear', 'range', 'clear_range',
                             'atomic', 'read_version'}:
            raise NativeDistributedError('FoundationDB operation unsupported')
        own = owner.transaction is None
        tx = self._transaction(owner) if own else owner.transaction
        mutation = operation in {'set', 'clear', 'clear_range', 'atomic'}
        try:
            if operation in {'range', 'clear_range'}:
                begin, end = decode_value(command, 'begin'), decode_value(
                    command, 'end')
                if begin >= end:
                    raise NativeDistributedError('FoundationDB range invalid')
                if operation == 'clear_range':
                    tx.clear_range(begin, end)
                    rows = []
                else:
                    limit, reverse = command.get('limit', 0), command.get(
                        'reverse', False)
                    if type(limit) is not int or not 0 <= limit <= 1000000000:
                        raise NativeDistributedError(
                            'FoundationDB limit invalid')
                    if type(reverse) is not bool:
                        raise NativeDistributedError(
                            'FoundationDB reverse invalid')
                    reader = tx.snapshot if command.get(
                        'snapshot') is True else tx
                    version = str(tx.get_read_version().wait())
                    rows, size, offset = [], 0, 0
                    for item in reader.get_range(begin, end, limit=limit,
                                                 reverse=reverse):
                        row = {'key': bytes(item.key).hex(),
                               'value': bytes(item.value).hex()}
                        width = len(json.dumps(row).encode())
                        if rows and (
                                len(rows) >= 256 or size + width > 1048576):
                            yield self._page(rows, operation, offset,
                                             read_version=version)
                            offset += len(rows)
                            rows, size = [], 0
                        rows.append(row)
                        size += width
                    yield self._page(
                        rows, operation, offset, read_version=version)
                    return
            elif operation == 'read_version':
                rows = [{'read_version': str(tx.get_read_version().wait())}]
            else:
                key = decode_value(command, 'key')
                if operation == 'get':
                    reader = tx.snapshot if command.get(
                        'snapshot') is True else tx
                    value = reader.get(key).value
                    rows = [{'key': key.hex(), 'value': None if value is None
                             else bytes(value).hex()}]
                else:
                    if operation == 'set':
                        tx.set(key, decode_value(command, 'value'))
                    elif operation == 'clear':
                        tx.clear(key)
                    else:
                        name = command.get('atomic_operation')
                        if name not in self.ATOMIC:
                            raise NativeDistributedError(
                                'Native atomic operation invalid')
                        getattr(tx, name)(key, decode_value(command, 'value'))
                    rows = [{'key': key.hex(), 'staged': not own}]
            if own and mutation:
                owner.state = 'commit-unknown'
                tx.commit().wait()
                owner.version = str(tx.get_committed_version())
                owner.state = 'committed'
                for row in rows:
                    row['accepted'] = True
            yield self._page(rows, operation, committed_version=owner.version)
        except Exception as exc:
            owner.error_code = getattr(exc, 'code', None)
            raise
        finally:
            if own and owner.state != 'commit-unknown':
                tx.cancel()

    def close_session(self, owner, _unknown=False):
        if owner.transaction is not None:
            owner.transaction.cancel()
            owner.transaction = None
        if owner in self._databases:
            self._databases.remove(owner)
        self._database_routes.pop(id(owner), None)
        owner.database = None


class FoundationDBDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

    def describe_transaction(self, session):
        with session.lock:
            if session.active is None:
                session.observation = self.backend.describe_transaction(
                    session.handle)
            return super().describe_transaction(session)

    def describe_result(self, token):
        result = super().describe_result(token)
        if result['payload'].get('error'):
            result['payload']['error']['native_code'] = (
                token.session.handle.error_code)
        return result
