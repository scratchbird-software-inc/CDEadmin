"""Durable protected results for native generated account passwords.

Only authenticated backend code constructs receivers. Public operation receipts
carry references; explicit reveal is separately authorized and never cached.
Reservations survive a lost response and do not authorize DCL replay.
"""
import base64
from contextlib import contextmanager
import hashlib
import hmac
from pathlib import Path
import time
import threading
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..report_scheduler.crypto import WorkerKeyRing
from .models import SecretAccessError, SecretReference
from .secrets import SecretLease


def identity(value):
    try:
        if str(uuid.UUID(value)) == value:
            return value
    except (ValueError, TypeError, AttributeError):
        pass
    raise SecretAccessError('Protected result identity is invalid')


class PasswordResults:
    def __init__(self, root, keys, endpoint, principal, plan_id=None, *, ttl=600, clock=time.time):
        self.endpoint = identity(endpoint)
        if not isinstance(principal, str) or not principal.startswith('user:') or not principal[5:].isdigit():
            raise SecretAccessError('Protected result owner is unavailable')
        if type(ttl) is not int or not 60 <= ttl <= 86400 or not keys.available:
            raise SecretAccessError('Protected result encryption or expiry is unavailable')
        self.principal, self.keys, self.ttl, self.clock = principal, keys, ttl, clock
        self.plan_id = identity(plan_id) if plan_id is not None else None
        self.root = Path(root).resolve() / principal[5:] / endpoint
        generation = hmac.new(keys._keys[keys.active_key_id], (str(self.root) + principal).encode(), hashlib.sha256).hexdigest()
        self.binding_id = str(uuid.uuid5(uuid.UUID(endpoint), keys.active_key_id + generation))

    @contextmanager
    def store(self):
        # Paths contain only server-owned configuration, numeric owner and UUID.
        for directory in (self.root.parent.parent, self.root.parent, self.root):
            if directory.is_symlink():
                raise SecretAccessError('Protected storage cannot contain links')
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_directory(directory)
        lock = self.root / 'results.lock'
        path = self.root / 'results.json'
        if lock.is_symlink() or path.is_symlink():
            raise SecretAccessError('Protected storage cannot contain links')
        try:
            with lock.open('a+b') as stream:
                private_file(lock)
                with exclusive_file_lock(stream.fileno()):
                    store = JsonOperationStore(path)
                    def expire(state):
                        rows = state['provider_audit']
                        for key in list(rows):
                            if rows[key]['expires_at'] <= self.clock():
                                del rows[key]
                    store.change(expire)
                    yield store
        except SecretAccessError:
            raise
        except Exception:
            raise SecretAccessError('Protected result storage is unavailable; do not replay account changes') from None

    def reserve(self, user, host, factors):
        if self.plan_id is None or not factors or len(set(factors)) != len(factors):
            raise SecretAccessError('Protected delivery requires a reviewed operation')
        with self.store() as store:
            def reserve(state):
                rows = state['provider_audit']
                if self.plan_id in rows or len(rows) >= 1024:
                    raise SecretAccessError('Protected result reservation exists or capacity is exhausted')
                rows[self.plan_id] = {'endpoint': self.endpoint, 'principal': self.principal,
                    'plan_id': self.plan_id, 'user': user, 'host': host,
                    'expires_at': self.clock() + self.ttl, 'state': 'reserved',
                    'factors': {str(factor): {'reference_id': str(uuid.uuid4())} for factor in factors}}
                return self.plan_id
            return store.change(reserve)

    def _record(self, state, plan_id):
        row = state['provider_audit'].get(identity(plan_id))
        if row is None or row['endpoint'] != self.endpoint or row['principal'] != self.principal or row['expires_at'] <= self.clock():
            raise SecretAccessError('Protected result is unavailable or expired')
        return row

    def _aad(self, row, factor):
        return {key: row[key] for key in ('endpoint', 'principal', 'plan_id', 'user', 'host', 'expires_at')} | {'factor': str(factor), 'reference_id': row['factors'][str(factor)]['reference_id']}

    def reference(self, reference_id):
        return SecretReference(identity(reference_id), self.endpoint, 'legacy_native', 'password',
            'encrypted_result', 'mysql-generated-password', reference_id, frozenset({'reveal', 'connect'}))

    def publish(self, reservation, factor, lease):
        if reservation != self.plan_id:
            raise SecretAccessError('Protected reservation does not match the operation')
        with self.store() as store:
            def publish(state):
                row = self._record(state, reservation)
                selected = row['factors'].get(str(factor))
                if selected is None or 'envelope' in selected:
                    raise SecretAccessError('Protected factor was not reserved or was already published')
                selected['envelope'] = lease.use(lambda value: self.keys.encrypt(value, self._aad(row, factor)))
                row['state'] = 'published' if all('envelope' in value for value in row['factors'].values()) else 'partially_published'
                return self.reference(selected['reference_id'])
            # The store only accepts JSON values. Return the model after commit.
            reference_id = None
            def save(state):
                nonlocal reference_id
                reference_id = publish(state).reference_id
            store.change(save)
            reference = self.reference(reference_id)
            if hasattr(self, 'secret_service'):
                self.secret_service.register_reference(reference)
            return reference

    def release(self, reservation):
        if reservation is None:
            return
        with self.store() as store:
            def release(state):
                row = self._record(state, reservation)
                if row['state'] == 'reserved':
                    row['state'] = 'no_protected_result'
            store.change(release)

    def recover(self, plan_id):
        with self.store() as store:
            row = self._record(store.read(), plan_id)
            if hasattr(self, 'secret_service'):
                for value in row['factors'].values():
                    if 'envelope' in value:
                        self.secret_service.register_reference(self.reference(value['reference_id']))
            return {key: row[key] for key in ('plan_id', 'user', 'host', 'expires_at', 'state')} | {
                'automatic_retry': False, 'passwords': [
                    {'factor': int(factor), 'secret_reference_id': value['reference_id']}
                    for factor, value in row['factors'].items() if 'envelope' in value]}

    def acquire(self, reference_id):
        identity(reference_id)
        with self.store() as store:
            state = store.read()
            for plan_id in state['provider_audit']:
                row = self._record(state, plan_id)
                for factor, value in row['factors'].items():
                    if value['reference_id'] == reference_id and 'envelope' in value:
                        return SecretLease(self.keys.decrypt(value['envelope'], self._aad(row, factor)))
        raise SecretAccessError('Protected password is unavailable or expired')

    def register(self, reference_id):
        # Validate ownership/expiry before restoring an in-memory reference
        # after application restart. Resolution independently rechecks them.
        with self.acquire(reference_id):
            self.secret_service.register_reference(self.reference(reference_id))


def for_app(app, context, plan_id=None):
    from flask_login import current_user
    from pgadmin.utils.master_password import get_crypt_key
    if not current_user.is_authenticated or not current_user.is_active or context.mode != 'legacy_native' or context.profile_id != 'mysql-native':
        raise SecretAccessError('Protected result scope is unavailable')
    if not {'administer', 'secret_read'} <= context.effective_permissions:
        raise SecretAccessError('Protected result access is not authorized')
    principal = 'user:' + str(current_user.id)
    configured = app.config.get('CDEADMIN_GENERATED_PASSWORD_KEYS')
    if configured:
        keys = WorkerKeyRing(configured, app.config.get('CDEADMIN_GENERATED_PASSWORD_ACTIVE_KEY_ID'))
    else:
        present, key = get_crypt_key()
        if not present or not key:
            raise SecretAccessError('Unlock the master password before generating or revealing passwords')
        if isinstance(key, str):
            key = key.encode('utf8')
        encoded = base64.b64encode(hashlib.sha256(b'cdeadmin-generated-password-v1\x00' + key).digest()).decode('ascii')
        keys = WorkerKeyRing({'master': encoded}, 'master')
    import config
    root = app.config.get('CDEADMIN_GENERATED_PASSWORD_PATH') or str(Path(config.DATA_DIR) / 'protected-password-results')
    results = PasswordResults(root, keys, context.endpoint_id, principal, plan_id,
        ttl=app.config.get('CDEADMIN_GENERATED_PASSWORD_TTL', 600))
    with results.store():
        pass  # Writable durable capacity must be available before account DCL.
    from . import service_for_app
    results.secret_service = service_for_app(app).secrets
    lock = app.extensions.setdefault('cdeadmin_generated_password_lock', threading.RLock())
    with lock:
        if not app.extensions.get('cdeadmin_generated_password_resolver'):
            def resolve(locator, selected_context, purpose, selected_principal):
                selected = for_app(app, selected_context)
                if selected.principal != selected_principal or purpose not in {'reveal', 'connect'}:
                    raise SecretAccessError('Protected result principal or purpose does not match')
                with selected.acquire(locator) as lease:
                    return lease.use(bytes)
            results.secret_service.register_resolver('mysql-generated-password', resolve)
            app.extensions['cdeadmin_generated_password_resolver'] = True
    return results
