"""Bounded, privilege-aware MariaDB catalog capture on an owned attachment.

MariaDB information_schema reads are observational, not an atomic DDL snapshot.
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
        raise ValueError('Invalid MariaDB identifier')
    return '`' + value.replace('`', '``') + '`'


def _value(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, (set, frozenset)) and all(isinstance(item, str) for item in value):
        return {'set': sorted(value)}
    if isinstance(value, Decimal):
        return {'decimal': str(value)}
    if isinstance(value, (datetime, date, time)):
        return {'temporal': value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'hex': bytes(value).hex()}
    if type(value) is float:
        # json.dumps below rejects NaN/infinity rather than silently changing it.
        return value
    raise ValueError('Unsupported native MariaDB catalog value')


def capture(connection, database, *, include_system=False):
    if type(include_system) is not bool or not isinstance(database, str) or not database:
        raise ValueError('Select an explicit MariaDB database')
    if (type(connection.server_status) is not int or connection.server_status & 1 or
            connection.autocommit is not True):
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
        # information_schema does not promise row order without ORDER BY.
        # Keep exact facts, including ordinal fields, in deterministic order.
        values.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False))
        observations.append({'section': name, 'available': True, 'rows': len(values)})
        return values

    def add(kind, name, row, parent=None):
        # JSON tuple addresses avoid collisions for names containing separators.
        address = 'mariadb:' + json.dumps([database, kind, parent, name], ensure_ascii=False, separators=(',', ':'))
        native = {'system_object': database in SYSTEM, 'database': database,
                  'catalog_row': row}
        if parent:
            native['navigator_parent_resource_id'] = parent
        item = {'resource_id': address, 'resource_kind': kind, 'display_name': name,
                'display_path': [database] + ([] if kind == 'database' else [name]), 'native': native}
        account(item)
        resources.append(item)
        return item

    quote_policy = connection.cursor(buffered=False)
    try:
        quote_policy.execute('SET SESSION sql_quote_show_create=1', None)
    finally:
        quote_policy.close()

    identity = list(read('SELECT DATABASE() AS database_name, VERSION() AS version, '
                         '@@server_uid AS server_uid, @@lower_case_table_names AS lower_case_table_names, '
                         '@@sql_mode AS sql_mode, @@character_set_client AS character_set_client, '
                         '@@collation_connection AS collation_connection, @@time_zone AS time_zone'))
    if len(identity) != 1 or identity[0]['database_name'] != database:
        raise ValueError('Selected MariaDB database identity changed')
    if identity[0]['version'].split('-')[0] != '12.2.2':
        raise ValueError('Catalog capture requires native MariaDB 12.2.2')
    if database in SYSTEM and not include_system:
        raise ValueError('System database capture requires explicit system-object inclusion')
    mode = identity[0].get('sql_mode')
    if not isinstance(mode, str):
        raise ValueError('Native MariaDB SQL mode observation is unavailable')
    hidden_options = {'NO_TABLE_OPTIONS', 'NO_FIELD_OPTIONS', 'NO_KEY_OPTIONS',
        'ORACLE', 'DB2', 'MAXDB', 'MSSQL', 'POSTGRESQL'}
    modes = [flag.strip() for flag in mode.split(',') if flag.strip()]
    retrieval_mode = ','.join(flag for flag in modes if flag not in hidden_options)
    if retrieval_mode != mode:
        policy = connection.cursor(buffered=False)
        try:
            policy.execute('SET SESSION sql_mode=?', (retrieval_mode,))
        finally:
            policy.close()
    capture_context = {key: identity[0].get(key) for key in
        ('character_set_client', 'collation_connection', 'time_zone')}
    capture_context['sql_mode'] = retrieval_mode
    root = add('database', database, identity[0])
    root['native']['definition_context'] = dict(capture_context)

    quoted_database = identifier(database)
    schemas = section('SCHEMATA', 'SELECT * FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=?', (database,))
    root['native']['schema_rows'] = schemas
    definition = section('SHOW CREATE DATABASE', 'SHOW CREATE DATABASE ' + quoted_database)
    if definition:
        root['native']['definition'] = definition[0].get('create database')

    tables = section('TABLES', 'SELECT * FROM information_schema.TABLES WHERE TABLE_SCHEMA=? ORDER BY TABLE_NAME', (database,))
    relations = {}
    for row in tables:
        name, table_type = row['table_name'], row['table_type']
        show_kind = 'VIEW' if table_type == 'VIEW' else 'SEQUENCE' if table_type == 'SEQUENCE' else 'TABLE'
        values = section('SHOW CREATE ' + name,
                         'SHOW CREATE ' + show_kind + ' ' + quoted_database + '.' + identifier(name))
        ddl = next((value for key, value in (values[0].items() if values else ()) if key.startswith('create ')), None)
        kind = 'view' if table_type == 'VIEW' else 'sequence' if table_type == 'SEQUENCE' else 'table'
        item = add(kind, name, row, root['resource_id'])
        item['native']['definition'] = ddl
        item['native']['definition_context'] = {**capture_context, **{key: value for key, value in (values[0].items() if values else ())
            if key in {'sql_mode', 'character_set_client', 'collation_connection', 'database collation', 'time_zone'}}}
        item['native']['definition_available'] = bool(ddl)
        if not ddl:
            observations.append({'section': kind + ':' + name, 'available': False,
                'reason': 'Native definition withheld or unavailable'})
        relations[name] = item

    for catalog in ('COLUMNS', 'STATISTICS', 'TABLE_CONSTRAINTS', 'KEY_COLUMN_USAGE',
                    'REFERENTIAL_CONSTRAINTS', 'CHECK_CONSTRAINTS', 'PARTITIONS', 'VIEWS', 'PERIODS', 'KEY_PERIOD_USAGE'):
        schema_column = ('CONSTRAINT_SCHEMA' if catalog in {'REFERENTIAL_CONSTRAINTS', 'CHECK_CONSTRAINTS'} else
                         'TABLE_SCHEMA')
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + schema_column + '=?', (database,))
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
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + schema_column + '=?', (database,))
        for row in values:
            kind = row['routine_type'].lower().replace(' ', '-') if catalog == 'ROUTINES' else 'trigger' if catalog == 'TRIGGERS' else 'event'
            name = row[name_column]
            owner = relations.get(row.get('event_object_table'))
            item = add(kind, name, row, (owner or root)['resource_id'])
            definitions = section('SHOW CREATE ' + kind + ' ' + name,
                'SHOW CREATE ' + kind.upper().replace('-', ' ') + ' ' + quoted_database + '.' + identifier(name))
            ddl = next((value for key, value in (definitions[0].items() if definitions else ())
                        if key.startswith('create ') or key == 'sql original statement'), None)
            item['native']['definition'] = ddl
            item['native']['definition_context'] = {**capture_context, **{key: value for key, value in (definitions[0].items() if definitions else ())
                if key in {'sql_mode', 'character_set_client', 'collation_connection', 'database collation', 'time_zone'}}}
            if kind == 'trigger':
                item['native']['trigger_identity']={'database':row.get('event_object_schema'),
                    'table':row.get('event_object_table'),'timing':row.get('action_timing'),
                    'event':row.get('event_manipulation'),'action_order':row.get('action_order')}
            item['native']['definition_available'] = bool(ddl)
            if ddl is None:
                observations.append({'section': kind + ':' + name, 'available': False,
                                     'reason': 'Native definition withheld or unavailable'})
    parameters = section('PARAMETERS',
        'SELECT * FROM information_schema.PARAMETERS WHERE SPECIFIC_SCHEMA=?', (database,))
    for item in resources:
        if item['resource_kind'] in {'procedure', 'function', 'package', 'package-body'}:
            item['native']['parameters'] = [row for row in parameters
                if row['specific_name'] == item['display_name'] and
                   row.get('routine_type', '').lower().replace(' ', '-') == item['resource_kind']]
    for catalog in ('SCHEMA_PRIVILEGES', 'TABLE_PRIVILEGES', 'COLUMN_PRIVILEGES'):
        column = 'TABLE_SCHEMA'
        values = section(catalog, 'SELECT * FROM information_schema.' + catalog + ' WHERE ' + column + '=?', (database,))
        root['native'].setdefault('visible_privileges', {})[catalog] = values
    root['native'].update(catalog_observations=observations, coverage_complete=False,
        isolation='observational information_schema / SHOW CREATE; concurrent DDL may change metadata',
        catalog_warnings=['Privilege-filtered visible metadata; full coverage is not asserted.',
            'Concurrent DDL is not fenced; this capture is not an atomic schema snapshot.',
            'Rows, account secrets, replication state and server-global configuration are excluded.'])
    account(root['native'])
    return {'resources': resources, 'generation': str(uuid.uuid4()),
            'database_name': database, 'observations': observations, 'complete': False}


SYSTEM_SCHEMAS = "('information_schema', 'mysql', 'performance_schema', 'sys')"


def program_object_natives(optional_records, add):
    """Enrich MariaDB triggers, routines and events with the definition facts
    the family editor pre-fills (body, parameters, schedule). Additive: every
    key here is new; the ``details`` list the base inventory records stays."""
    for record in optional_records(
            'SELECT TRIGGER_SCHEMA, EVENT_OBJECT_SCHEMA, EVENT_OBJECT_TABLE, TRIGGER_NAME, ACTION_TIMING, '
            'EVENT_MANIPULATION, ACTION_ORDER, ACTION_STATEMENT FROM information_schema.TRIGGERS '
            f'WHERE TRIGGER_SCHEMA NOT IN {SYSTEM_SCHEMAS} ORDER BY 1, 3, 7, 4'):
        add('trigger', [record['trigger_schema'], record['event_object_table']], record['trigger_name'], {
            'timing': record['action_timing'], 'events': [record['event_manipulation']],
            'position': record['action_order'], 'body': record['action_statement'],
            'table': [record['event_object_schema'], record['event_object_table']]})
    parameters = {}
    for record in optional_records(
            'SELECT SPECIFIC_SCHEMA, SPECIFIC_NAME, ROUTINE_TYPE, ORDINAL_POSITION, PARAMETER_MODE, PARAMETER_NAME, '
            f'DTD_IDENTIFIER FROM information_schema.PARAMETERS WHERE SPECIFIC_SCHEMA NOT IN {SYSTEM_SCHEMAS} '
            'ORDER BY 1, 2, 4'):
        key = (record['specific_schema'], record['specific_name'], str(record['routine_type']).lower())
        entry = parameters.setdefault(key, {'parameters': [], 'returns': None})
        if record['ordinal_position'] == 0:
            entry['returns'] = record['dtd_identifier']
            continue
        entry['parameters'].append({'name': record['parameter_name'], 'type': record['dtd_identifier'],
                                    'mode': record['parameter_mode']})
    for record in optional_records(
            'SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DTD_IDENTIFIER, ROUTINE_DEFINITION, IS_DETERMINISTIC, '
            f'SQL_DATA_ACCESS, SECURITY_TYPE, ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA NOT IN {SYSTEM_SCHEMAS} '
            "AND ROUTINE_TYPE IN ('PROCEDURE', 'FUNCTION') ORDER BY 1, 2"):
        kind = str(record['routine_type']).lower()
        signature = parameters.get((record['routine_schema'], record['routine_name'], kind), {})
        add(kind, [record['routine_schema']], record['routine_name'], {
            'body': record['routine_definition'], 'parameters': signature.get('parameters', []),
            'returns': signature.get('returns') or record['dtd_identifier'],
            'deterministic': str(record['is_deterministic']).upper() == 'YES',
            'sql_data_access': record['sql_data_access'], 'security_type': record['security_type'],
            'comment': record['routine_comment']})
    for record in optional_records(
            'SELECT EVENT_SCHEMA, EVENT_NAME, EVENT_TYPE, EXECUTE_AT, INTERVAL_VALUE, INTERVAL_FIELD, STARTS, ENDS, '
            f'STATUS, ON_COMPLETION, EVENT_DEFINITION FROM information_schema.EVENTS WHERE EVENT_SCHEMA NOT IN {SYSTEM_SCHEMAS} '
            'ORDER BY 1, 2'):
        if str(record['event_type']).upper() == 'ONE TIME':
            schedule = f"AT '{record['execute_at']}'"
        else:
            schedule = f"EVERY {record['interval_value']} {record['interval_field']}"
            if record.get('starts'):
                schedule += f" STARTS '{record['starts']}'"
            if record.get('ends'):
                schedule += f" ENDS '{record['ends']}'"
        add('event', [record['event_schema']], record['event_name'], {
            'schedule': schedule, 'preserve': str(record['on_completion']).upper() == 'PRESERVE',
            'enabled': str(record['status']).upper() == 'ENABLED', 'body': record['event_definition']})
