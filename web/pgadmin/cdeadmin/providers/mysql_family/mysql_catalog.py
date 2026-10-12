"""Bounded, privilege-aware MySQL catalog capture on an owned attachment.

MySQL information_schema reads are observational, not an atomic DDL snapshot.
Never borrow an interactive transaction or promote a filtered catalog to full
coverage. This module does not execute imported definitions.
"""
from datetime import date, datetime, time
from decimal import Decimal
import json
import uuid

MAX_FACTS = 20000
MAX_BYTES = 8 * 1024 * 1024
DENIED = {1044, 1142, 1143, 1227, 1370}
SYSTEM = {'information_schema', 'mysql', 'performance_schema', 'sys'}


def identifier(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Invalid MySQL identifier')
    return '`' + value.replace('`', '``') + '`'


def _value(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        return {'decimal': str(value)}
    if isinstance(value, (datetime, date, time)):
        return {'temporal': value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'hex': bytes(value).hex()}
    if type(value) is float:
        # json.dumps below rejects NaN/infinity rather than silently changing it.
        return value
    raise ValueError('Unsupported native MySQL catalog value')


def capture(connection, database, *, include_system=False):
    if type(include_system) is not bool or not isinstance(database, str) or not database:
        raise ValueError('Select an explicit MySQL database')
    if connection.in_transaction:
        raise ValueError('Catalog capture requires its own idle connection')
    resources, observations = [], []
    facts = size = 0

    def account(value):
        nonlocal facts, size
        facts += 1
        size += len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf8'))
        if facts > MAX_FACTS or size > MAX_BYTES:
            raise ValueError('Native catalog exceeds the 20,000-fact / 8 MiB capture limit')

    def read(source, parameters=None):
        cursor = connection.cursor(buffered=False)
        try:
            cursor.execute(source, parameters)
            names = [str(column[0]).lower() for column in cursor.description or ()]
            while True:
                rows = cursor.fetchmany(128)
                if not rows:
                    break
                for row in rows:
                    value = {key: _value(item) for key, item in zip(names, row)}
                    account(value)
                    yield value
        finally:
            cursor.close()

    def section(name, source, parameters=None):
        try:
            values = list(read(source, parameters))
        except Exception as error:
            if getattr(error, 'errno', None) not in DENIED:
                raise
            observations.append({'section': name, 'available': False,
                'error_code': error.errno, 'sqlstate': getattr(error, 'sqlstate', None)})
            return []
        observations.append({'section': name, 'available': True, 'rows': len(values)})
        return values

    def add(kind, name, row, parent=None):
        # JSON tuple addresses avoid collisions for names containing separators.
        address = 'mysql:' + json.dumps([database, kind, parent, name], ensure_ascii=False, separators=(',', ':'))
        native = {'system_object': database in SYSTEM, 'database': database,
                  'catalog_row': row}
        if parent:
            native['navigator_parent_resource_id'] = parent
        item = {'resource_id': address, 'resource_kind': kind, 'display_name': name,
                'display_path': [database] + ([] if kind == 'database' else [name]), 'native': native}
        account(item)
        resources.append(item)
        return item

    identity = list(read('SELECT DATABASE() AS database_name, VERSION() AS version, '
                         '@@server_uuid AS server_uuid, @@lower_case_table_names AS lower_case_table_names, '
                         '@@sql_mode AS sql_mode'))
    if len(identity) != 1 or identity[0]['database_name'] != database:
        raise ValueError('Selected MySQL database identity changed')
    if identity[0]['version'].split('-')[0] != '9.7.0':
        raise ValueError('Catalog capture requires native MySQL 9.7.0')
    if database in SYSTEM and not include_system:
        raise ValueError('System database capture requires explicit system-object inclusion')
    root = add('database', database, identity[0])
    quoted_database = identifier(database)
    schemas = section('SCHEMATA', 'SELECT * FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (database,))
    root['native']['schema_rows'] = schemas
    definition = section('SHOW CREATE DATABASE', 'SHOW CREATE DATABASE ' + quoted_database)
    if definition:
        root['native']['definition'] = definition[0].get('create database')

    tables = section('TABLES', 'SELECT * FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME', (database,))
    relations = {}
    for row in tables:
        name, table_type = row['table_name'], row['table_type']
        show_kind = 'VIEW' if table_type == 'VIEW' else 'TABLE'
        values = section('SHOW CREATE ' + name,
                         'SHOW CREATE ' + show_kind + ' ' + quoted_database + '.' + identifier(name))
        ddl = next((value for key, value in (values[0].items() if values else ()) if key.startswith('create ')), None)
        kind = 'view' if table_type == 'VIEW' else 'table'
        # Native materialized views may be catalogued as VIEW. Use the server's
        # own DDL header, not a substring in comments/defaults/query literals.
        if isinstance(ddl, str):
            import re
            if re.match(r'^CREATE\s+(?:(?:ALGORITHM=\S+|DEFINER=\S+|SQL SECURITY \w+)\s+)*MATERIALIZED\s+VIEW\b', ddl, re.I):
                kind = 'materialized-view'
        item = add(kind, name, row, root['resource_id'])
        item['native']['definition'] = ddl
        item['native']['definition_available'] = bool(ddl)
        relations[name] = item

    for catalog in ('COLUMNS', 'STATISTICS', 'TABLE_CONSTRAINTS', 'KEY_COLUMN_USAGE',
                    'REFERENTIAL_CONSTRAINTS', 'CHECK_CONSTRAINTS', 'PARTITIONS', 'VIEWS'):
        schema_column = 'CONSTRAINT_SCHEMA' if catalog in {'REFERENTIAL_CONSTRAINTS', 'CHECK_CONSTRAINTS'} else 'TABLE_SCHEMA'
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + schema_column + '=%s', (database,))
        for row in values:
            parent = relations.get(row.get('table_name'))
            if parent is not None:
                parent['native'].setdefault('children', {}).setdefault(catalog, []).append(row)
            else:
                root['native'].setdefault('unattached_facts', {}).setdefault(catalog, []).append(row)

    specs = (('ROUTINES', 'ROUTINE_SCHEMA', 'routine_name'),
             ('TRIGGERS', 'TRIGGER_SCHEMA', 'trigger_name'),
             ('EVENTS', 'EVENT_SCHEMA', 'event_name'))
    for catalog, schema_column, name_column in specs:
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + schema_column + '=%s', (database,))
        for row in values:
            kind = row['routine_type'].lower() if catalog == 'ROUTINES' else 'trigger' if catalog == 'TRIGGERS' else 'event'
            name = row[name_column]
            owner = relations.get(row.get('event_object_table'))
            item = add(kind, name, row, (owner or root)['resource_id'])
            definitions = section('SHOW CREATE ' + kind + ' ' + name,
                'SHOW CREATE ' + kind.upper() + ' ' + quoted_database + '.' + identifier(name))
            ddl = next((value for key, value in (definitions[0].items() if definitions else ())
                        if key.startswith('create ') or key == 'sql original statement'), None)
            item['native']['definition'] = ddl
            item['native']['definition_available'] = bool(ddl)
            if ddl is None:
                observations.append({'section': kind + ':' + name, 'available': False,
                                     'reason': 'Native definition withheld or unavailable'})
    for catalog in ('SCHEMA_PRIVILEGES', 'TABLE_PRIVILEGES', 'COLUMN_PRIVILEGES'):
        column = 'TABLE_SCHEMA'
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + column + '=%s', (database,))
        root['native'].setdefault('visible_privileges', {})[catalog] = values
    root['native'].update(catalog_observations=observations, coverage_complete=False,
        isolation='observational information_schema / SHOW CREATE; concurrent DDL may change metadata',
        catalog_warnings=['Privilege-filtered visible metadata; full coverage is not asserted.',
            'Concurrent DDL is not fenced; this capture is not an atomic schema snapshot.',
            'Rows, account secrets, replication state and server-global configuration are excluded.'])
    account(root['native'])
    return {'resources': resources, 'generation': str(uuid.uuid4()),
            'database_name': database, 'observations': observations, 'complete': False}
