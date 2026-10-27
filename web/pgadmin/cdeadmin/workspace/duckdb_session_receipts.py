"""Durable observations of original-session DuckDB work; never replay authority."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import threading
import time
import uuid

import psutil

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..security.redaction import redact


FAMILIES = frozenset({'attachments', 'extensions', 'database_copy'})


def identity(value):
    try:
        valid=isinstance(value,str) and str(uuid.UUID(value))==value
    except ValueError:
        valid=False
    if not valid:
        raise ValueError('Select an exact native operation receipt identity')
    return value


class DuckDBSessionReceipts:
    def __init__(self, path, owner, endpoint, target):
        if type(owner) is not int or owner <= 0 or not isinstance(target, str) or not target or len(target) > 512:
            raise ValueError('Select an owned DuckDB receipt scope')
        identity(endpoint)
        self.binding = (str(Path(path).resolve()), owner, endpoint, target)
        self.root = Path(path).resolve() / str(owner) / endpoint / hashlib.sha256(target.encode('utf8')).hexdigest()
        self.lock = threading.RLock()
        self.process = [os.getpid(), psutil.Process().create_time()]

    @contextmanager
    def store(self, kind, key):
        identity(key)
        directory = self.root / kind
        with self.lock:
            for path in (self.root.parent.parent.parent, self.root.parent.parent, self.root.parent, self.root, directory):
                linked=path.is_symlink()
                if path.exists():linked=linked or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)
                if linked:
                    raise ValueError('Native receipt directories cannot contain links or reparse points')
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
                private_directory(path)
            path = directory / (key + '.json')
            if path.is_symlink() or Path(str(path) + '.lock').is_symlink():
                raise ValueError('Native receipt files cannot be symbolic links')
            descriptor = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
            try:
                with exclusive_file_lock(descriptor):
                    yield JsonOperationStore(path)
            finally:
                os.close(descriptor)

    def bind(self, context):
        scope = identity(context['session_scope_id'])
        with self.store('sessions', scope) as store:
            def create(state):
                state.setdefault('duckdb_session_observation', {
                    'session_scope_id': scope, 'original_catalog': {
                        'name':context['origin'][0],'oid':str(context['origin'][1]),'path':context['origin'][2]},
                    'state': 'open', 'process_identity': self.process,
                    'opened_observed_at': time.time(), 'transaction_finality_inferred': False})
            store.change(create)
        return BoundDuckDBReceipts(self, scope)

    def publish(self, family, record):
        if family not in FAMILIES:
            raise ValueError('Unknown native DuckDB receipt family')
        receipt = identity(record['review_id'])
        identity(record['session_scope_id'])
        with self.store('records', receipt) as store:
            def update(state):
                prior = state.get('duckdb_session_receipt')
                if prior and (prior['family'] != family or prior['receipt']['session_scope_id'] != record['session_scope_id']):
                    raise ValueError('Native receipt identity changed')
                state['duckdb_session_receipt'] = {
                    'family': family, 'receipt': redact(record),
                    'created_at': prior['created_at'] if prior else time.time(),
                    'recorded_at': time.time(), 'revision': prior['revision'] + 1 if prior else 1}
            store.change(update)

    def session(self, scope, state, observation=None):
        with self.store('sessions', scope) as store:
            def update(candidate):
                value = candidate.get('duckdb_session_observation')
                if not value:
                    raise ValueError('Original native receipt session is unavailable')
                value.update(state=state, release_observation=redact(observation or {}), observed_at=time.time())
            store.change(update)

    def get(self, receipt):
        with self.store('records', receipt) as store:
            record = store.read().get('duckdb_session_receipt')
        if not record:
            raise ValueError('Native receipt is unavailable for this owner, endpoint and database target')
        with self.store('sessions', record['receipt']['session_scope_id']) as store:
            session = store.read().get('duckdb_session_observation')
        if not session:
            raise ValueError('Original native receipt session observation is unavailable')
        if session['state'] != 'released':
            try:
                alive = psutil.Process(session['process_identity'][0]).create_time() == session['process_identity'][1]
            except psutil.Error:
                alive = False
            if not alive:
                session['state'] = 'owner_unavailable'
        result = deepcopy(record)
        result.update(original_session=session, archived_read_only=True, automatic_retry=False,
            transaction_finality_inferred=False,live_session_observed=False,
            outcome_observation=('unknown' if session['state']=='owner_unavailable' else 'unresolved') if
                record['receipt'].get('state') in {'reviewing','applying','unknown_outcome'} else 'last_persisted_observation')
        return result

    def recent(self, *, offset=0, limit=25):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Select a bounded native receipt page')
        root = self.root / 'records'
        paths = sorted(root.glob('*.json'), key=lambda value: (value.stat().st_mtime_ns, value.name), reverse=True)
        records=[]
        for path in paths[offset:offset+limit]:
            item=self.get(path.stem)
            item['receipt']={key:value for key,value in item['receipt'].items() if key in {
                'review_id','session_scope_id','state','phase','action','native_dispatched','native_acknowledged',
                'rediscovery_verified','source_catalog','destination_catalog','extension_name','alias'}}
            records.append(item)
        return {'receipts': records,
            'offset': offset, 'limit': limit, 'total': len(paths), 'more': offset + limit < len(paths),
            'archived_read_only': True, 'transaction_finality_inferred': False}


class BoundDuckDBReceipts:
    def __init__(self, archive, scope):
        self.archive, self.scope = archive, scope
        self.binding = archive.binding

    def publish(self, family, record):
        if record['session_scope_id'] != self.scope:
            raise ValueError('Original native receipt session changed')
        self.archive.publish(family, record)

    def release(self, state, observation=None):
        self.archive.session(self.scope, state, observation)


def for_workspace(service,server,context,target):
    if context.provider_id!='org.cdeadmin.duckdb' or context.profile_id!='duckdb-native':
        raise ValueError('Select a native DuckDB receipt workspace')
    store=getattr(service.operation_bus,'store',None)
    if not isinstance(store,JsonOperationStore):
        raise ValueError('Native DuckDB operations require durable application receipt storage')
    return DuckDBSessionReceipts(str(store.path)+'.duckdb-session-receipts',
        service._principal_id(server),context.endpoint_id,target)


def action(archive,request):
    if not isinstance(request,dict):raise ValueError('Select an archived native DuckDB receipt')
    if request.get('operation')=='list' and not set(request)-{'operation','offset','limit'}:
        return archive.recent(**{key:value for key,value in request.items() if key!='operation'})
    if request.get('operation')=='get' and set(request)=={'operation','review_id'}:
        return archive.get(request['review_id'])
    raise ValueError('Archived native DuckDB receipts support read-only list and get')
