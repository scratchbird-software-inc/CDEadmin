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
                                 _source, _require_virtual_module, _compile_exact)
from ..providers.sqlite.provider import _resources
from ..providers.sqlite.driver import uncertain_error


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
        for operation in operations:
            identity = operation['resource_id']
            if operation.get('operation') == 'rebuild':
                from .sqlite_rebuild import plan_rebuild
                old, wanted = baseline['rows'].get(identity), desired['rows'].get(identity)
                if old is None or wanted is None or len(operations) != 1:
                    raise SchemaApplyError('SQLite rebuild requires one exact retained table')
                expected = plan_rebuild(old, wanted, baseline, None,
                    temp_name=operation.get('temp_name'),
                    column_renames=operation.get('column_renames'))
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
                        any(row['resource_kind'] == 'view' or
                            (row['resource_kind'] == 'trigger' and
                             row['display_path'][:len(old['path'])] != old['path'])
                            for row in observed.values()) or
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
                    column_renames=operation.get('column_renames'))
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
                from ..providers.sqlite.provider import _resource_id
                parent = _resource_id('table', ['main'], row['path'][1])
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
            if operation['operation'] == 'rebuild':
                name = _quote(operation['name'])
                old_count = connection.execute('SELECT count(*) FROM "main".' + name).fetchone()[0]
                for stage in operation['stages']:
                    connection.execute(stage)
                if operation.get('preserve_autoincrement'):
                    high_water = autoincrement_sequences[operation['resource_id']]
                    connection.execute('DELETE FROM main.sqlite_sequence WHERE name=?',
                                       (operation['name'],))
                    if high_water is not None:
                        connection.execute('INSERT INTO main.sqlite_sequence(name,seq) VALUES (?,?)',
                                           (operation['name'], high_water))
                    observed_sequence = connection.execute(
                        'SELECT seq FROM main.sqlite_sequence WHERE name=?',
                        (operation['name'],)).fetchall()
                    if observed_sequence != ([(high_water,)] if high_water is not None else []):
                        raise ValueError('SQLite AUTOINCREMENT sequence preservation failed')
                new_count = connection.execute('SELECT count(*) FROM "main".' + name).fetchone()[0]
                if new_count != old_count:
                    raise ValueError('SQLite rebuild row count differs before commit')
                if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise ValueError('SQLite rebuild failed native foreign-key check')
            else:
                connection.execute(operation['source'])
        connection.commit()
        committed = True
    except Exception as error:
        uncertain = uncertain_error(error)
        try:
            if connection.in_transaction:
                connection.rollback()
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
                def indexed_keys(items):
                    return [{**item, 'keys': [key for key in item.get('keys', [])
                        if key.get('is_key')]} for item in items]
                if (indexed_keys(row['native'].get('indexes', [])) !=
                        indexed_keys(old['native'].get('indexes', [])) or
                        row['native'].get('triggers') != old['native'].get('triggers')):
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
