"""Reviewed, observable native FTS3/4/5 index maintenance."""
from copy import deepcopy
import os
import threading
import time
import uuid

from pgadmin.cdeadmin.navigator import resource_native
from pgadmin.cdeadmin.sdk import RelationalClientError
from .fts_configuration import capture, quote
from .modules import declaration, option

OPERATIONS = ('fts_optimize', 'fts_rebuild', 'fts_integrity_check', 'fts_merge',
              'fts_delete_all', 'fts_flush')
TITLES = {'fts_optimize': 'Optimize FTS index', 'fts_rebuild': 'Rebuild FTS index',
          'fts_integrity_check': 'Check FTS integrity', 'fts_merge': 'Merge FTS segments',
          'fts_delete_all': 'Delete all FTS index entries', 'fts_flush': 'Flush session FTS terms'}


def form(operation, field):
    fields = [field('timeout_seconds', 'Native operation timeout (seconds)', 'number', True, default=30)]
    if operation == 'fts_merge':
        fields += [field('pages', 'Merge leaf-page budget (negative FTS5 values start a new merge)', 'number', True, default=128),
                   field('minimum_segments', 'FTS3/4 minimum segments', 'number', False, default=2)]
    if operation == 'fts_integrity_check':
        fields.append(field('external_content', 'Compare FTS5 external content', 'boolean', default=False))
    if operation == 'fts_delete_all':
        fields.append(field('confirmation', 'Exact FTS table name', 'text', True,
                            'Removes index entries from a contentless or external-content FTS5 table. External content rows remain.'))
    return {'form_id': 'fts-table.' + operation, 'title': TITLES[operation], 'fields': fields}


def compile_operation(request):
    operation = request['operation_id']; target = request.get('target_resource') or {}
    native = resource_native(target); path = target.get('display_path')
    ddl = native.get('ddl'); observed = declaration(ddl)
    if (operation not in OPERATIONS or not isinstance(path, list) or len(path) != 2 or
            any(not isinstance(v, str) or not v or '\0' in v for v in path) or
            not observed or observed[1].lower() not in {'fts3', 'fts4', 'fts5'}):
        raise RelationalClientError('Select an observed native FTS table definition')
    module = observed[1].lower(); schema, name = path
    draft = request.get('draft') or {}
    fields = {'timeout_seconds'}
    if operation == 'fts_merge': fields |= {'pages', 'minimum_segments'}
    if operation == 'fts_integrity_check': fields.add('external_content')
    if operation == 'fts_delete_all': fields.add('confirmation')
    if not isinstance(draft, dict) or set(draft) - fields:
        raise RelationalClientError('Unknown FTS maintenance option')
    timeout = draft.get('timeout_seconds', 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 3600:
        raise RelationalClientError('FTS timeout must be above zero and at most 3600 seconds')
    content = option(ddl, 'content') if module == 'fts5' else None
    if operation == 'fts_rebuild' and module == 'fts5' and content == '':
        raise RelationalClientError('SQLite cannot rebuild a contentless FTS5 table')
    if operation == 'fts_delete_all' and (module != 'fts5' or content is None):
        raise RelationalClientError('Delete-all requires contentless or external-content FTS5')
    if operation == 'fts_delete_all' and draft.get('confirmation') != name:
        raise RelationalClientError('FTS deletion confirmation must exactly match the table name')
    external = draft.get('external_content', False)
    if not isinstance(external, bool) or (external and (module != 'fts5' or not content)):
        raise RelationalClientError('External-content comparison requires external-content FTS5')
    command = operation.removeprefix('fts_').replace('_', '-')
    value = None
    if operation == 'fts_integrity_check' and module == 'fts5': value = int(external)
    if operation == 'fts_merge':
        value = draft.get('pages', 128)
        minimum = draft.get('minimum_segments', 2)
        if type(value) is not int or not -2147483648 <= value <= 2147483647:
            raise RelationalClientError('FTS merge pages must be a signed 32-bit integer')
        if module != 'fts5':
            if value < 0 or type(minimum) is not int or not 2 <= minimum <= 2147483647:
                raise RelationalClientError('FTS3/4 merge requires nonnegative pages and at least two segments')
            command += '=' + str(value) + ',' + str(minimum); value = None
    table = quote(schema) + '.' + quote(name)
    if module == 'fts5' and value is not None:
        statement = {'source': 'INSERT INTO ' + table + '(' + quote(name) + ',rank) VALUES(?,?)', 'parameters': (command, value)}
    else:
        statement = {'source': 'INSERT INTO ' + table + '(' + quote(name) + ') VALUES(?)', 'parameters': (command,)}
    literal = "'" + command.replace("'", "''") + "'"
    statement['preview_source'] = statement['source'].replace('VALUES(?,?)', 'VALUES(' + literal + ',' + str(value) + ')').replace('VALUES(?)', 'VALUES(' + literal + ')')
    route = request.get('_provider_route') or {}
    from ..embedded_route import contained_database
    database = contained_database(route)
    identity = None
    if database != ':memory:':
        stat = os.stat(database); identity = [stat.st_dev, stat.st_ino]
    configuration = native.get('fts_configuration')
    if not isinstance(configuration, dict) or configuration.get('available') is not True or configuration.get('restorable') is not True:
        raise RelationalClientError('Capture complete native FTS settings before index maintenance')
    return {'statements': [statement], 'sqlite_fts_maintenance': {
        'reference': str(uuid.uuid4()), 'operation': operation, 'schema': schema, 'name': name,
        'module': module, 'ddl': ddl, 'configuration': deepcopy(configuration),
        'file_identity': identity, 'timeout_seconds': timeout},
        'warnings': ['Native FTS maintenance can read or rewrite the complete index and contend with other writers.',
                     'Retained-session changes remain staged until the caller commits. Flush requires that retained session.',
                     'SQLite interruption can roll back the caller\'s complete write transaction. A lost savepoint blocks session reuse until it is closed.',
                     'Merge budgets count native leaf-page work; callback counts are not completion percentages.']}


def _entries(client):
    if not hasattr(client, '_cde_fts_maintenance'): client._cde_fts_maintenance = {}
    return client._cde_fts_maintenance


def allowed_operations(source, module):
    operations = ['inspect', 'create', 'rename', 'drop', *OPERATIONS]
    try:
        content = option(source, 'content') if module == 'fts5' else None
    except ValueError:
        return ['inspect', 'create', 'rename', 'drop']
    if module != 'fts5' or content is None: operations.remove('fts_delete_all')
    if module == 'fts5' and content == '': operations.remove('fts_rebuild')
    return operations


def observe(client, request, *, cancel=False):
    reference = request['provider_payload']['compiled']['sqlite_fts_maintenance']['reference']
    with client._lock:
        entry = _entries(client).get(reference)
        if entry is None: return {'available': False, 'reference': reference, 'automatic_retry': False}
        if cancel:
            accepted = entry['public']['stage'] not in {'finalizing', 'commit_started', 'complete'}
            if accepted:
                entry['cancel'].set()
                if entry['connection'] is not None: entry['connection'].interrupt()
            return {'cancel_requested': accepted, 'reference': reference, 'automatic_retry': False,
                    'stage': entry['public']['stage']}
        return deepcopy(entry['public'])


def apply(client, request, connection=None):
    payload = request['provider_payload']; compiled = payload['compiled']; spec = compiled['sqlite_fts_maintenance']
    owned = connection is None; reference = spec['reference']; started = False; savepoint = None
    dispatched = False; commit_started = False; old_progress = (None, 0); progress_installed = False
    old_busy = None; progress_interval = 1000; prior_steps = 0; reserved = False
    public = {'reference': reference, 'stage': 'admission', 'operation': spec['operation'],
              'vm_callbacks': 0, 'progress_scope': 'native VM callback observations; no percentage inferred',
              'automatic_retry': False, 'native_outcome': None}
    entry = {'public': public, 'connection': None, 'cancel': threading.Event()}
    def update(**values):
        with client._lock: public.update(values)
    with client._lock:
        entries = _entries(client)
        if reference in entries:
            raise RelationalClientError('This native FTS operation has already been dispatched; inspect its receipt')
        if len(entries) >= 1024:
            expired = next((key for key, item in entries.items() if item['public']['stage'] == 'complete'), None)
            if expired is None: raise RelationalClientError('Native FTS operation capacity is exhausted')
            del entries[expired]
        entries[reference] = entry
    deadline = time.monotonic() + spec['timeout_seconds']
    def checkpoint():
        if entry['cancel'].is_set(): raise RelationalClientError('Native FTS maintenance cancelled')
        if time.monotonic() >= deadline: raise RelationalClientError('Native FTS maintenance timed out')
    def progress():
        nonlocal prior_steps
        public['vm_callbacks'] += 1
        if entry['cancel'].is_set() or time.monotonic() >= deadline: return 1
        prior_steps += progress_interval
        if old_progress[0] and prior_steps >= old_progress[1]:
            prior_steps %= old_progress[1]
            return old_progress[0]()
        return 0
    try:
        if owned and (spec['schema'].lower() != 'main' or spec['operation'] == 'fts_flush'):
            raise RelationalClientError('This FTS operation requires its retained native session')
        connection = connection or client._connect({'route': payload['route']})
        with client._lock:
            client._require_idle(connection); client._busy.add(id(connection)); reserved = True; entry['connection'] = connection
        checkpoint()
        old_busy = connection.execute('PRAGMA busy_timeout').fetchone()[0]
        connection.execute('PRAGMA busy_timeout=' + str(min(old_busy, max(1, int((deadline-time.monotonic())*1000)))))
        if owned:
            connection.execute('BEGIN IMMEDIATE'); started = True
        else:
            if not connection.in_transaction: connection.execute('BEGIN'); started = True
            savepoint = 'cde_fts_' + uuid.uuid4().hex; connection.execute('SAVEPOINT ' + savepoint)
        schema, name = spec['schema'], spec['name']; table = quote(schema) + '.' + quote(name)
        if spec['file_identity'] is not None:
            from ..embedded_route import contained_database
            stat = os.stat(contained_database(payload['route']))
            if [stat.st_dev, stat.st_ino] != spec['file_identity']: raise RelationalClientError('SQLite file identity changed after FTS review')
        row = connection.execute('SELECT sql FROM ' + quote(schema) + '.sqlite_schema WHERE name=? COLLATE NOCASE', (name,)).fetchone()
        before = capture(connection, schema, name, spec['module'])
        if not row or row[0] != spec['ddl'] or before != spec['configuration']:
            raise RelationalClientError('Native FTS definition or settings changed after review')
        old_progress = connection._cdeadmin_progress_handler
        progress_interval = min(old_progress[1], 1000) if old_progress[0] else 1000
        connection.set_progress_handler(progress, progress_interval); progress_installed = True
        update(stage='executing'); dispatched = True
        for statement in compiled['statements']:
            checkpoint(); connection.execute(statement['source'], statement['parameters'])
        checkpoint(); update(stage='verifying')
        if spec['operation'] == 'fts_rebuild' and spec['module'] in {'fts3', 'fts4'}:
            for key, value in before['commands']:
                connection.execute('INSERT INTO ' + table + '(' + quote(name) + ') VALUES(?)', ('automerge=' + str(value),))
        if spec['operation'] != 'fts_integrity_check':
            connection.execute('INSERT INTO ' + table + '(' + quote(name) + ') VALUES(?)', ('integrity-check',))
        if spec['operation'] == 'fts_delete_all':
            vocab = '__cde_fts_' + uuid.uuid4().hex
            connection.execute('CREATE VIRTUAL TABLE temp.' + quote(vocab) + ' USING fts5vocab(' +
                "'" + schema.replace("'", "''") + "','" + name.replace("'", "''") + "','row')")
            try:
                if connection.execute('SELECT count(*) FROM temp.' + quote(vocab)).fetchone()[0]:
                    raise RelationalClientError('Native FTS delete-all left visible index terms')
            finally: connection.execute('DROP TABLE temp.' + quote(vocab))
        after = capture(connection, schema, name, spec['module'])
        if after.get('available') is not True or after.get('restorable') is not True or any(
                dict(after['commands']).get(key) != value for key, value in before['commands']):
            raise RelationalClientError('Native FTS maintenance did not preserve observed settings')
        with client._lock:
            checkpoint(); public['stage'] = 'finalizing'
        if savepoint: connection.execute('RELEASE ' + savepoint); savepoint = None
        if owned:
            with client._lock:
                checkpoint(); public['stage'] = 'commit_started'; commit_started = True
            connection.commit()
        update(native_outcome='committed' if owned else 'staged', configuration=after,
                      native_integrity_verified=True, index_terms_verified_empty=spec['operation'] == 'fts_delete_all')
    except Exception as error:
        rolled_back = False
        try:
            if progress_installed: connection.set_progress_handler(*old_progress); progress_installed = False
            if savepoint:
                connection.execute('ROLLBACK TO ' + savepoint); connection.execute('RELEASE ' + savepoint)
            if started: connection.rollback()
            rolled_back = not commit_started
        except Exception: pass
        update(native_outcome='not_dispatched' if not dispatched else 'rolled_back' if rolled_back else 'unknown_outcome',
                      native_error={'type': type(error).__name__, 'message': str(error),
                                    'code': getattr(error, 'sqlite_errorcode', None), 'name': getattr(error, 'sqlite_errorname', None)},
                      cancellation_requested=entry['cancel'].is_set(), timeout_expired=time.monotonic() >= deadline)
        if not owned and connection is not None and not rolled_back: client._uncertain.add(id(connection))
    finally:
        try:
            if progress_installed: connection.set_progress_handler(*old_progress)
            if old_busy is not None: connection.execute('PRAGMA busy_timeout=' + str(old_busy))
        except Exception:
            update(native_outcome='unknown_outcome'); client._uncertain.add(id(connection))
        with client._lock:
            entry['connection'] = None
            if reserved: client._busy.discard(id(connection))
        if owned and connection is not None:
            try: client._forget_and_close(connection)
            except Exception: update(native_outcome='unknown_outcome', cleanup_failed=True)
        update(stage='complete')
    return {'accepted': public['native_outcome'] in {'committed', 'staged'},
            'native_fts_maintenance': deepcopy(public), 'driver_observation_only': True,
            'staged_in_provider_session': not owned, 'automatic_mutation_retry': False,
            'transaction_finality_interpreted_by_common_code': False}
