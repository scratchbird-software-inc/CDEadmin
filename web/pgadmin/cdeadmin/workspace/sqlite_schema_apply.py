"""Durable once-only review and SQLite-owned DDN CREATE application."""

from copy import deepcopy
import json
import os
import re
import stat
import uuid

from .firebird_schema_apply import SchemaApplications, SchemaApplyError
from .firebird_schema_plan import digest
from .sqlite_schema_plan import (FORMAT, CREATABLE, _definition, _quote,
                                 _source, _require_virtual_module, _compile_exact,
                                 _created_owner, _compile_created_child, batch_blockers)
from ..providers.sqlite.provider import _resources
from ..providers.sqlite.driver import uncertain_error


class _PreservationRefused(ValueError):
    """An application invariant failed before COMMIT was dispatched."""


def _validate_dependencies(connection, observed):
    """Prepare retained view/trigger uses without stepping their mutation VMs."""
    # CPython can retain an EXPLAIN program across schema changes. EXPLAIN
    # does not step that program's normal schema-cookie checks. Force a fresh
    # native prepare for this validation, including on retained connections.
    fresh=' /* cdeadmin-native-prepare:'+uuid.uuid4().hex+' */'
    for row in observed.values():
        if row['resource_kind'] == 'view':
            if (row['native'].get('column_observation',{}).get('available') is False or
                    row['native'].get('view_binding_observation',{}).get('available') is False):
                raise _PreservationRefused('SQLite final view columns or native bindings are unavailable')
            connection.execute('EXPLAIN SELECT * FROM "main".' +
                _quote(row['display_name']) + ' LIMIT 0'+fresh).fetchone()
    owners = {row['display_path'][1] for row in observed.values()
        if row['resource_kind'] == 'trigger' and row['display_path'][0] == 'main'}
    for owner in owners:
        target = '"main".' + _quote(owner)
        relation = connection.execute('SELECT type FROM main.sqlite_schema WHERE name=?', (owner,)).fetchone()
        events = {'INSERT', 'UPDATE', 'DELETE'}
        if relation and relation[0] == 'view':
            from .sqlite_replace import trigger_event
            # A view is writable only for events with INSTEAD OF triggers.
            # Prepare those events, rather than inventing unsupported writes.
            events = {trigger_event(row['native']['ddl']) for row in observed.values()
                if row['resource_kind'] == 'trigger' and row['display_path'][:2] == ['main', owner]}
        columns = [row[1] for row in connection.execute(
            'PRAGMA main.table_xinfo(' + _quote(owner) + ')') if not row[6]]
        statements = []
        if 'INSERT' in events: statements.append('INSERT INTO ' + target + ' DEFAULT VALUES')
        if 'DELETE' in events: statements.append('DELETE FROM ' + target)
        if columns and 'UPDATE' in events:
            statements.append('UPDATE ' + target + ' SET ' + ', '.join(
                _quote(name) + '=' + _quote(name) for name in columns))
        for source in statements:
            connection.execute('EXPLAIN ' + source+fresh).fetchone()


class SQLiteSchemaApplications(SchemaApplications):
    def review(self, preview, baseline, desired, owner, binding, database, *, file_identity):
        operations = preview.get('operations')
        if (preview.get('format') != FORMAT or preview.get('ready_for_review') is not True or
                preview.get('application_supported') is not True or
                preview.get('native_grammar_validated') is not True or
                not isinstance(operations, list) or not 1 <= len(operations) <= 32 or
                preview.get('execution_sha256') != digest(operations)):
            raise SchemaApplyError('Only bounded, native-validated SQLite changes can be reviewed')
        if (not isinstance(file_identity, list) or len(file_identity) != 2 or
                any(type(value) is not int or value < 0 for value in file_identity)):
            raise SchemaApplyError('SQLite file identity must be an exact device/inode pair')
        refused=batch_blockers(operations,desired)
        if refused:raise SchemaApplyError(refused[0])
        for operation in operations:
            identity = operation['resource_id']
            if operation.get('operation') == 'fts-configure':
                from .sqlite_fts_settings import plan as configure
                old, wanted = baseline['rows'].get(identity), desired['rows'].get(identity)
                if old is None or wanted is None or configure(old, wanted) != operation:
                    raise SchemaApplyError('SQLite FTS configuration differs from the reviewed design')
                continue
            if operation.get('operation')=='rename-batch':
                from .sqlite_rename import plan as rename_plan
                expected=rename_plan(baseline,desired,baseline,operation.get('renames'),operation.get('fts_rebindings',()))
                if len(operations)!=1 or not expected['ready_for_review'] or expected['operations']!=operations:
                    raise SchemaApplyError('SQLite native rename differs from the reviewed design')
                continue
            if operation.get('operation') == 'replace':
                from .sqlite_replace import plan_replace,validate_view_children
                old, wanted = baseline['rows'].get(identity), desired['rows'].get(identity)
                if old is None or wanted is None:
                    raise SchemaApplyError('SQLite replacements require exact retained views, indexes and triggers')
                if wanted['kind']=='view':
                    try:validate_view_children(wanted,desired)
                    except ValueError as error:raise SchemaApplyError(str(error)) from None
                expected = plan_replace(old, wanted, baseline, probe_name=operation.get('probe_name'))
                if digest(expected) != digest(operation):
                    raise SchemaApplyError('SQLite replacement differs from the reviewed native design')
                continue
            if operation.get('operation') == 'rebuild':
                from .sqlite_rebuild import plan_rebuild
                old, wanted = baseline['rows'].get(identity), desired['rows'].get(identity)
                if old is None or wanted is None:
                    raise SchemaApplyError('SQLite rebuilds require exact retained tables')
                expected = plan_rebuild(old, wanted, baseline, None,
                    temp_name=operation.get('temp_name'),
                    column_renames=operation.get('column_renames'),desired=desired,
                    child_deletions=operation.get('child_deletions',[]))
                if digest(expected) != digest(operation):
                    raise SchemaApplyError('SQLite rebuild stages differ from reviewed design')
                continue
            if operation.get('operation') == 'drop':
                from ..providers.sqlite.provider import _resource_id
                old = baseline['rows'].get(identity)
                if (old is None or old['kind'] not in CREATABLE or
                        old['system'] != 'false' or
                        old['native'].get('system_object') is not False or
                        len(old['path']) != (3 if old['kind'] in {'index', 'trigger'} else 2) or
                        old['path'][0] != 'main' or old['path'][-1] != old['name'] or
                        identity != _resource_id(old['kind'], old['path'][:-1], old['name']) or
                        identity in desired['rows'] or
                        operation.get('baseline_sha256') != digest(_definition(old)) or
                        operation.get('desired_sha256') is not None or
                        operation.get('source') != 'DROP ' +
                            ('TABLE' if old['kind'] in {'fts-table', 'virtual-table'}
                             else old['kind'].upper()) + ' ' +
                            _quote('main') + '.' + _quote(old['name'])):
                    raise SchemaApplyError('SQLite deletion differs from reviewed baseline')
                descendants = {child_id: digest(_definition(child))
                    for child_id, child in baseline['rows'].items()
                    if child_id != identity and child['path'][:len(old['path'])] == old['path']}
                if (operation.get('affected_child_sha256') != descendants or
                        any(child_id in desired['rows'] for child_id in descendants)):
                    raise SchemaApplyError('SQLite deletion children differ from review')
                continue
            row = desired['rows'].get(identity)
            if (operation.get('operation') != ('add-column' if operation.get('kind') == 'column' else 'create') or row is None or
                    identity in baseline['rows'] or
                    operation.get('desired_sha256') != digest(_definition(row)) or
                    operation.get('source') != _source(row)):
                raise SchemaApplyError('SQLite DDL differs from the reviewed native design')
            if row['kind'] == 'column':
                from ..providers.sqlite.provider import _resource_id
                parent = baseline['rows'].get(_resource_id('table', ['main'], row['path'][1]))
                if (parent is None or operation.get('parent_baseline_sha256') !=
                        digest(_definition(parent))):
                    raise SchemaApplyError('SQLite ADD COLUMN parent differs from baseline')
        record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed',
            'created_at': self.clock(), 'expires_at': self.clock() + 300,
            'owner': owner, 'binding': binding, 'database': database,
            'plan': deepcopy(preview), 'baseline': deepcopy(baseline),
            'desired': deepcopy(desired), 'file_identity': file_identity}
        record['review_digest'] = digest(record)
        if len(json.dumps(record, ensure_ascii=False).encode('utf8')) > 4 * 1024 * 1024:
            raise SchemaApplyError('SQLite review exceeds 4 MiB; capture a smaller design')
        with self._store() as store:
            def save(state):
                records = state.setdefault('schema_applications', {})
                for identity in list(records):
                    if records[identity]['state'] == 'reviewed' and records[identity]['expires_at'] < self.clock():
                        del records[identity]
                if len(records) >= 1000:
                    raise SchemaApplyError('SQLite schema receipt capacity reached')
                records[record['review_id']] = record
            store.change(save)
        return self._public(record)


def apply_review(provider, route, record):
    """Execute once on a private SQLite handle; never borrow a query session."""
    if len(record['plan']['operations'])==1 and record['plan']['operations'][0].get('operation')=='rename-batch':
        from .sqlite_rename import apply as apply_rename
        return apply_rename(provider,route,record)
    from ..providers.embedded_route import contained_database
    path = contained_database(route)
    if path == ':memory:' or route.get('read_only') is True:
        return {'state': 'not_dispatched', 'reason': 'Writable registered SQLite file required'}
    try:
        info = os.stat(path)
        if (not stat.S_ISREG(info.st_mode) or
                [info.st_dev, info.st_ino] != record['file_identity']):
            return {'state': 'not_dispatched', 'reason': 'SQLite file identity changed'}
    except OSError:
        return {'state': 'not_dispatched', 'reason': 'SQLite registered file unavailable'}
    connection = provider.client._connect({'route': route})
    dispatched = False
    committed = False
    close_failed = False
    autoincrement_sequences = {}
    try:
        if any(op.get('operation') == 'rebuild' for op in record['plan']['operations']):
            # A retained view may temporarily reference the absent original
            # table between DROP and RENAME. Keep its source names unchanged;
            # prepare all retained bindings again before native COMMIT.
            connection.execute('PRAGMA legacy_alter_table=ON')
            if connection.execute('PRAGMA legacy_alter_table').fetchone() != (1,):
                return {'state': 'not_dispatched', 'reason': 'SQLite owned rename mode unavailable'}
        if any(op.get('operation') == 'rebuild' and op.get('preserve_foreign_keys')
               for op in record['plan']['operations']):
            connection.execute('PRAGMA foreign_keys=OFF')
            if connection.execute('PRAGMA foreign_keys').fetchone() != (0,):
                return {'state': 'not_dispatched',
                    'reason': 'SQLite foreign keys could not be disabled on the owned migration handle'}
        connection.execute('BEGIN IMMEDIATE')
        info = os.stat(path)
        if [info.st_dev, info.st_ino] != record['file_identity']:
            connection.rollback()
            return {'state': 'not_dispatched', 'reason': 'SQLite file identity changed'}
        observed = {row['resource_id']: row for row in _resources(connection, {})
                    if row['native'].get('system_object') is not True}
        baseline = record['baseline']['rows']
        for operation in record['plan']['operations']:
            identity = operation['resource_id']
            if operation['operation'] == 'fts-configure':
                from .sqlite_fts_settings import plan as configure
                old, wanted, now = baseline.get(identity), record['desired']['rows'].get(identity), observed.get(identity)
                current_model = None if now is None else {'resource_id': identity, 'kind': now['resource_kind'],
                    'path': now['display_path'], 'name': now['display_name'], 'system': 'false', 'native': now['native']}
                if (old is None or wanted is None or now is None or
                        digest(_definition(old)) != digest(_definition(current_model)) or configure(old, wanted) != operation):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'Native FTS configuration or reviewed definition changed'}
                continue
            if operation['operation'] == 'replace':
                from .sqlite_replace import dependencies, plan_replace
                modeled = {key:{'resource_id':key,'kind':row['resource_kind'],'path':row['display_path'],
                    'name':row['display_name'],'system':'false','native':row['native']} for key,row in observed.items()}
                old, wanted, now = baseline.get(identity), record['desired']['rows'].get(identity), modeled.get(identity)
                if (old is None or wanted is None or now is None or
                        digest(_definition(old)) != digest(_definition(now)) or
                        dependencies(modeled, identity) != operation['dependency_sha256']):
                    connection.rollback()
                    return {'state':'not_dispatched','reason':'SQLite replacement target or dependency changed'}
                expected = plan_replace(old, wanted, record['baseline'], connection,
                                        probe_name=operation.get('probe_name'))
                if digest(expected) != digest(operation):
                    connection.rollback()
                    return {'state':'not_dispatched','reason':'Reviewed SQLite replacement changed'}
                continue
            if operation['operation'] == 'rebuild':
                from .sqlite_rebuild import plan_rebuild
                old = baseline.get(identity)
                wanted = record['desired']['rows'].get(identity)
                now = observed.get(identity)
                if old is None or wanted is None or now is None:
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite rebuild target changed'}
                current_model = {'resource_id': identity, 'kind': now['resource_kind'],
                    'path': now['display_path'], 'name': now['display_name'],
                    'system': 'true' if now['native'].get('system_object') else 'false',
                    'native': now['native']}
                if (digest(_definition(old)) != digest(_definition(current_model)) or
                        {child_id: digest(row['native'].get('ddl'))
                            for child_id, row in observed.items()
                            if row['resource_kind'] == 'view' or
                            (row['resource_kind'] == 'trigger' and
                             row['display_path'][:2] != old['path'])}
                        != operation.get('dependency_sha256', {}) or
                        any(row['display_name'] == operation['temp_name'] for row in observed.values())):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite rebuild dependency or target changed'}
                expected_children = {child_id: child for child_id, child in baseline.items()
                    if child_id != identity and child['path'][:len(old['path'])] == old['path']}
                current_children = {child_id: child for child_id, child in observed.items()
                    if child_id != identity and child['display_path'][:len(old['path'])] == old['path']}
                if (set(expected_children) != set(current_children) or
                        any(digest(_definition(child)) != digest(_definition({
                            'kind': current_children[child_id]['resource_kind'],
                            'path': current_children[child_id]['display_path'],
                            'name': current_children[child_id]['display_name'],
                            'system': 'true' if current_children[child_id]['native'].get('system_object') else 'false',
                            'native': current_children[child_id]['native']}))
                            for child_id, child in expected_children.items()) or
                        {row['resource_id']: digest({'ddl': row['native'].get('ddl'),
                            'dependencies': row['native'].get('dependencies')})
                            for row in observed.values()
                            if row['resource_kind'] == 'table' and row['resource_id'] != identity and
                            any(dep.get('referenced_table') == old['name']
                                for dep in row['native'].get('dependencies', []))}
                            != operation.get('inbound_sha256', {})):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite rebuild child or foreign key changed'}
                expected = plan_rebuild(old, wanted, record['baseline'], connection,
                    temp_name=operation['temp_name'],
                    column_renames=operation.get('column_renames'),desired=record['desired'],
                    child_deletions=operation.get('child_deletions',[]))
                if digest(expected) != digest(operation):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite rebuild stages changed'}
                if operation.get('preserve_autoincrement'):
                    sequence_rows = connection.execute(
                        'SELECT seq FROM main.sqlite_sequence WHERE name=?',
                        (operation['name'],)).fetchall()
                    if (len(sequence_rows) > 1 or
                            (sequence_rows and
                             (type(sequence_rows[0][0]) is not int or
                              sequence_rows[0][0] < 0))):
                        connection.rollback()
                        return {'state': 'not_dispatched',
                            'reason': 'SQLite AUTOINCREMENT sequence is ambiguous'}
                    autoincrement_sequences[identity] = (
                        sequence_rows[0][0] if sequence_rows else None)
                connection.execute('EXPLAIN ' + operation['stages'][0]).fetchone()
                continue
            if operation['operation'] == 'drop':
                old = baseline.get(identity)
                now = observed.get(identity)
                if (old is None or now is None or
                        digest(_definition(old)) != digest(_definition({
                            'kind': now['resource_kind'], 'path': now['display_path'],
                            'name': now['display_name'],
                            'system': 'true' if now['native'].get('system_object') else 'false',
                            'native': now['native']}))):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite DROP target changed'}
                descendants = {child_id: row for child_id, row in observed.items()
                    if child_id != identity and row['display_path'][:len(old['path'])] == old['path']}
                if (set(descendants) != set(operation['affected_child_sha256']) or
                        any(digest(_definition({'kind': row['resource_kind'],
                            'path': row['display_path'], 'name': row['display_name'],
                            'system': 'true' if row['native'].get('system_object') else 'false',
                            'native': row['native']})) != operation['affected_child_sha256'][child_id]
                            for child_id, row in descendants.items())):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite DROP children changed'}
                if old['kind'] in {'table', 'fts-table', 'virtual-table'} and any(
                        item['native'].get('dependencies') and
                        any(dep.get('referenced_table') == old['name']
                            for dep in item['native']['dependencies'])
                        for other_id, item in observed.items()
                        if other_id != identity and item['resource_kind'] == 'table' and
                        other_id not in {op['resource_id'] for op in record['plan']['operations']}):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite inbound foreign key appeared'}
                if old['kind'] in {'table', 'fts-table', 'virtual-table'} and any(
                        other_id != identity and
                        other_id not in {removed_id
                            for op in record['plan']['operations']
                            for removed_id in [op['resource_id'],
                                *op.get('affected_child_sha256', {})]} and
                        item['resource_kind'] in {'view', 'trigger', 'fts-table', 'virtual-table'}
                        for other_id, item in observed.items()):
                    connection.rollback()
                    return {'state': 'not_dispatched',
                        'reason': 'SQLite dependent view, trigger or virtual table appeared'}
                connection.execute('EXPLAIN ' + operation['source']).fetchone()
                continue
            if identity in observed or identity in baseline:
                connection.rollback()
                return {'state': 'not_dispatched', 'reason': 'SQLite CREATE target changed'}
            row = record['desired']['rows'][identity]
            if (operation['desired_sha256'] != digest(_definition(row)) or
                    operation['source'] != _source(row)):
                connection.rollback()
                return {'state': 'not_dispatched', 'reason': 'Reviewed SQLite DDL changed'}
            try:
                _require_virtual_module(connection, row, operation['source'])
            except ValueError:
                connection.rollback()
                return {'state': 'not_dispatched',
                    'reason': 'SQLite virtual table module availability changed'}
            if row['kind'] in {'index', 'trigger', 'column'}:
                new_owner = _created_owner(row, record['desired'], record['baseline'])
                if new_owner is not None:
                    if not any(item['operation']=='create' and
                               item['resource_id']==new_owner['resource_id']
                               for item in record['plan']['operations']):
                        connection.rollback()
                        return {'state':'not_dispatched','reason':'SQLite new owning relation is not in the reviewed plan'}
                    _compile_created_child(row, operation['source'], new_owner)
                    continue
                from ..providers.sqlite.provider import _resource_id
                parent = _resource_id('table', ['main'], row['path'][1])
                if parent not in baseline and row['kind']=='trigger':parent=_resource_id('view',['main'],row['path'][1])
                old, now = baseline.get(parent), observed.get(parent)
                if old is None or now is None or digest(_definition(old)) != digest(_definition({
                        'kind': now['resource_kind'], 'path': now['display_path'],
                        'name': now['display_name'], 'system': 'true' if now['native'].get('system_object') else 'false',
                        'native': now['native']})):
                    connection.rollback()
                    return {'state': 'not_dispatched', 'reason': 'SQLite owning table changed'}
            _compile_exact(connection, row, operation['source'])
        for operation in record['plan']['operations']:
            dispatched = True
            if operation['operation'] == 'replace':
                for stage in operation['stages']:
                    connection.execute(stage)
            elif operation['operation'] == 'rebuild':
                name = _quote(operation['name'])
                old_count = connection.execute('SELECT count(*) FROM "main".' + name).fetchone()[0]
                for stage in operation['stages']:
                    connection.execute(stage)
                if operation.get('preserve_autoincrement'):
                    high_water = autoincrement_sequences[operation['resource_id']]
                    copied = connection.execute(
                        'SELECT seq FROM main.sqlite_sequence WHERE name=?',
                        (operation['name'],)).fetchone()
                    if copied is not None:
                        high_water = max(high_water or 0, copied[0])
                    connection.execute('DELETE FROM main.sqlite_sequence WHERE name=?',
                                       (operation['name'],))
                    if high_water is not None:
                        connection.execute('INSERT INTO main.sqlite_sequence(name,seq) VALUES (?,?)',
                                           (operation['name'], high_water))
                    observed_sequence = connection.execute(
                        'SELECT seq FROM main.sqlite_sequence WHERE name=?',
                        (operation['name'],)).fetchall()
                    if observed_sequence != ([(high_water,)] if high_water is not None else []):
                        raise _PreservationRefused('SQLite AUTOINCREMENT sequence preservation failed')
                new_count = connection.execute('SELECT count(*) FROM "main".' + name).fetchone()[0]
                if new_count != old_count:
                    raise _PreservationRefused('SQLite rebuild row count differs before commit')
            elif operation['operation'] == 'fts-configure':
                for source in operation['stages']:
                    connection.execute(source)
                from ..providers.sqlite.fts_configuration import capture, identity
                if identity(capture(connection, 'main', operation['name'], operation['module'])) != identity(
                        record['desired']['rows'][operation['resource_id']]['native']['fts_configuration']):
                    raise _PreservationRefused('Native FTS setters differ from the reviewed configuration')
            else:
                connection.execute(operation['source'])
                row=record['desired']['rows'].get(operation['resource_id'])
                if operation['operation']=='create' and row and row['kind']=='fts-table' and row['native'].get('fts_configuration') is not None:
                    from ..providers.sqlite.fts_configuration import statements
                    for source in statements(row['name'],row['native']['fts_configuration']):connection.execute(source)
        if any(operation['operation'] == 'rebuild' for operation in record['plan']['operations']):
            if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise _PreservationRefused('SQLite rebuild batch failed native foreign-key check')
        replacements = [operation for operation in record['plan']['operations'] if operation['operation'] == 'replace']
        if replacements or any(operation['operation'] == 'rebuild' or
                operation['operation'] == 'create' and operation['kind'] in {'view','trigger'}
                for operation in record['plan']['operations']):
            from .sqlite_replace import matches
            actual_objects = {row['resource_id']:row for row in _resources(connection, {})
                              if row['native'].get('system_object') is not True}
            # Validate the complete final schema, including newly created
            # views/triggers and replaced events in a mixed atomic batch.
            _validate_dependencies(connection, actual_objects)
            for operation in replacements:
                actual = actual_objects.get(operation['resource_id'])
                if actual is None or not matches(record['desired']['rows'][operation['resource_id']],
                        {'resource_id':actual['resource_id'],'kind':actual['resource_kind'],'path':actual['display_path'],
                         'name':actual['display_name'],'system':'false','native':actual['native']}):
                    raise _PreservationRefused('SQLite replacement differs from desired native metadata')
            for operation in record['plan']['operations']:
                if operation.get('coordinated_children'):
                    if any(identity in actual_objects for identity in operation.get('child_deletions',[])):
                        raise _PreservationRefused('SQLite rebuilt child deletion differs from review')
                    for identity in operation['target_child_sources']:
                        actual=actual_objects.get(identity)
                        if actual is None or not matches(record['desired']['rows'][identity],
                                {'resource_id':actual['resource_id'],'kind':actual['resource_kind'],'path':actual['display_path'],
                                 'name':actual['display_name'],'system':'false','native':actual['native']}):
                            raise _PreservationRefused('SQLite rebuilt child differs from desired native metadata')
        connection.commit()
        committed = True
    except Exception as error:
        uncertain = not isinstance(error, _PreservationRefused) and uncertain_error(error)
        try:
            if connection.in_transaction:
                connection.rollback()
            if connection.in_transaction:
                raise RuntimeError('SQLite rollback did not end the owned write transaction')
            if not dispatched:
                return {'state': 'not_dispatched', 'error_type': type(error).__name__,
                    'rediscovery_verified': False}
            if not uncertain:
                return {'state': 'rolled_back',
                    'error_type': type(error).__name__, 'rediscovery_verified': False}
        except Exception:
            uncertain = True
        return {'state': 'unknown_outcome' if uncertain else 'not_dispatched',
            'error_type': type(error).__name__, 'rediscovery_verified': False}
    finally:
        try:
            provider.client._discard_failed_session(connection)
        except Exception:
            if not committed:
                raise
            close_failed = True
    if close_failed:
        return {'state': 'unknown_outcome', 'rediscovery_verified': False,
                'error_type': 'SQLiteConnectionReleaseError'}
    try:
        info = os.stat(path)
        if [info.st_dev, info.st_ino] != record['file_identity']:
            return {'state': 'unknown_outcome', 'rediscovery_verified': False,
                    'error_type': 'SQLiteFileIdentityChanged'}
        captured = provider.capture_catalog(route, include_system=True)
        by_id = {row['resource_id']: row for row in captured['resources']}
        def normalized(source):
            # sqlite_schema.sql omits a schema qualifier on the created name.
            return re.sub(r'^(\s*CREATE\s+(?:UNIQUE\s+)?(?:TABLE|VIRTUAL\s+TABLE|VIEW|INDEX|TRIGGER)\s+)"main"\.',
                          r'\1', source.strip().rstrip(';'), count=1, flags=re.I)
        def matches(operation):
            if operation['operation'] == 'replace':
                from .sqlite_replace import matches as replacement_matches
                row = by_id.get(operation['resource_id'])
                return row is not None and replacement_matches(record['desired']['rows'][operation['resource_id']],
                    {'resource_id':row['resource_id'],'kind':row['resource_kind'],'path':row['display_path'],
                     'name':row['display_name'],'system':'true' if row['native'].get('system_object') else 'false','native':row['native']})
            if operation['operation'] == 'rebuild':
                row = by_id.get(operation['resource_id'])
                if row is None or row['resource_kind'] != 'table' or any(
                        item['display_name'] == operation['temp_name'] for item in by_id.values()):
                    return False
                actual = {col['name']: {'type': col.get('data_type', ''),
                    'pk': col.get('primary_key_position', 0),
                    'hidden': col.get('hidden', 0)}
                    for col in row['native'].get('columns', [])}
                expected = {col['name']: {'type': col['type'], 'pk': col['pk'],
                    'hidden': col['hidden']}
                    for col in operation['target_columns']}
                if actual != expected or row['native'].get('ddl') != operation['expected_ddl']:
                    return False
                old = record['baseline']['rows'][operation['resource_id']]
                wanted = record['desired']['rows'][operation['resource_id']] if operation.get('coordinated_children') else old
                def indexed_keys(items):
                    return sorted([{**item,'ddl':normalized(item['ddl']), 'keys': [key for key in item.get('keys', [])
                        if key.get('is_key')]} for item in items if item.get('ddl')],key=lambda item:item['resource_id'])
                def trigger_definitions(items):
                    return sorted([{**item,'ddl':normalized(item['ddl'])} for item in items],key=lambda item:item['resource_id'])
                if (indexed_keys(row['native'].get('indexes', [])) !=
                        indexed_keys(wanted['native'].get('indexes', [])) or
                        trigger_definitions(row['native'].get('triggers',[])) != trigger_definitions(wanted['native'].get('triggers',[]))):
                    return False
                # The fresh catalog connection has already closed. Derive the
                # same native signatures from its captured PRAGMA facts.
                implicit = sorted([(int(item.get('unique', False)), item['origin'],
                    int(item.get('partial', False)), tuple((key['column_id'],
                        key['name'], int(key.get('descending', False)), key['collation'])
                        for key in item['keys'] if key.get('is_key')))
                    for item in row['native'].get('indexes', []) if not item.get('ddl')], key=repr)
                if digest(implicit) != digest(operation['implicit_index_signatures']):
                    return False
                metadata = row['native'].get('catalog_metadata', {})
                if (bool(metadata.get('without_rowid')) != operation['target_without_rowid'] or
                        bool(metadata.get('strict')) != operation['target_strict']):
                    return False
                for child_id in operation['preserved_child_ids']:
                    current = by_id.get(child_id)
                    if current is None:
                        return False
                expected_children = {child_id for child_id, child in record['desired']['rows'].items()
                    if child_id != operation['resource_id'] and
                    child['path'][:len(old['path'])] == old['path']}
                actual_children = {child_id for child_id, child in by_id.items()
                    if child_id != operation['resource_id'] and
                    child['display_path'][:len(old['path'])] == old['path'] and
                    not child['native'].get('system_object')}
                return expected_children == actual_children
            if operation['operation'] == 'drop':
                return all(identity not in by_id for identity in
                    [operation['resource_id'], *operation['affected_child_sha256']])
            row = by_id.get(operation['resource_id'])
            if row is None or row['resource_kind'] != operation['kind']:
                return False
            if operation['operation'] == 'fts-configure':
                actual = {'resource_id': operation['resource_id'], 'kind': row['resource_kind'],
                    'path': row['display_path'], 'name': row['display_name'], 'system': 'false', 'native': row['native']}
                return _definition(actual) == _definition(record['desired']['rows'][operation['resource_id']])
            if operation['kind']=='fts-table':
                from ..providers.sqlite.fts_configuration import identity
                wanted=record['desired']['rows'][operation['resource_id']]['native'].get('fts_configuration')
                if wanted is not None and identity(row['native'].get('fts_configuration'))!=identity(wanted):return False
            if operation['kind'] == 'column':
                actual = row['native'].get('catalog_metadata', {})
                expected = record['desired']['rows'][operation['resource_id']]['native'].get('catalog_metadata', {})
                return all(actual.get(key) == expected.get(key) for key in
                    ('data_type', 'nullable', 'default', 'hidden', 'primary_key_position'))
            return ((row['native'].get('ddl') or '').strip().rstrip(';') ==
                    normalized(operation['source']))
        verified = all(matches(operation) for operation in record['plan']['operations'])
        return {'state': 'committed' if verified else 'unknown_outcome',
            'rediscovery_verified': verified,
            'operations': len(record['plan']['operations'])}
    except Exception as error:
        return {'state': 'unknown_outcome', 'rediscovery_verified': False,
            'error_type': type(error).__name__}
