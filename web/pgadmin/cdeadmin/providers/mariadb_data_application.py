"""Native transaction ownership and exact postimages for reviewed DDN imports."""
from decimal import Decimal
import json
import time

from ..workspace.firebird_schema_plan import digest
from ..workspace.mariadb_data_import import bound, plan_digest
from .mysql_family.mariadb_catalog import identifier
from .mysql_family.mariadb_data_capture import native_layout
from .mysql_family.mariadb_values import value as wire_value, Cursor


def identity(cursor, plan):
    cursor.execute('SELECT VERSION(),@@server_uid,DATABASE()')
    actual = cursor.fetchone()
    if (actual is None or actual[0].split('-')[0] != '12.2.2' or
            actual[1] != plan['server_uid'] or actual[2] != plan['database']):
        raise ValueError('Native import server/database identity changed')


def equal(expected, actual, column):
    if isinstance(expected, dict) and expected.get('encoding') == 'base64':
        return isinstance(actual, dict) and all(expected.get(key) == actual.get(key) for key in ('data', 'byte_length'))
    datatype = column['column_type'].split('(')[0].lower()
    if expected is not None and actual is not None and datatype in {'decimal', 'numeric', 'float', 'double'}:
        return Decimal(str(expected)) == Decimal(str(actual))
    if expected is not None and actual is not None and datatype == 'json':
        return json.loads(expected, parse_float=Decimal) == json.loads(actual, parse_float=Decimal)
    return expected == actual


def verify(connection, plan):
    columns = {column['column_name']: column for column in plan['native_columns']}
    with connection.cursor() as cursor:
        identity(cursor, plan)
        cursor.execute('SET SESSION time_zone=%s', ('+00:00',))
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION", (plan['database'], plan['table']))
        keys = [row[0] for row in cursor.fetchall()]
    if plan.get('system_versioned'):
        # MariaDB appends its generated system-time endpoint to the physical
        # primary key. Current rows share the native open-ended boundary. The
        # current-row SELECT below must still observe exactly one match.
        keys = [name for name in keys if name in plan['columns']]
    if not keys or not set(keys) <= set(plan['columns']):
        return {'verified': False, 'reason': 'Exact row re-read requires an explicit source-valued primary key', 'rows': 0}
    indexes = [plan['columns'].index(name) for name in keys]
    address = identifier(plan['database']) + '.' + identifier(plan['table'])
    checked = 0
    with Cursor(connection).native as cursor:
        cursor.cdeadmin_exact_temporals = True
        for row in plan['rows']:
            expressions, parameters = [], []
            for name, index in zip(keys, indexes):
                expression, values = bound(row[index], columns[name])
                expressions.append(identifier(name) + '=' + expression)
                parameters.extend(values)
            selected = [
                'CAST(' + identifier(name) + ' AS BINARY)' if isinstance(cell, dict) and 'native_charset' in cell else identifier(name)
                for name, cell in zip(plan['columns'], row)]
            cursor.execute('SELECT ' + ','.join(selected) + ' FROM ' + address + ' WHERE ' + ' AND '.join(expressions) + ' LIMIT 2', parameters)
            native = cursor.fetchall()
            if len(native) != 1:
                raise ValueError('An imported native row is absent or ambiguous')
            observed = [wire_value(cell) for cell, column in zip(native[0], cursor.description)]
            if any(not equal(cell, result, columns[name]) for name, cell, result in zip(plan['columns'], row, observed)):
                raise ValueError('Native import would change an exact source value')
            checked += 1
    return {'verified': True, 'rows': checked, 'method': 'native-primary-key-postimages'}


def apply_import(connection, record):
    plan = record['plan']
    cursor = None
    begun = dispatched = committing = acknowledged = False
    count = 0
    result = {'state': 'not_dispatched', 'automatic_retry': False, 'acknowledged_rows': 0,
              'rollback_undoes_target_rows': plan.get('storage_engine') == 'InnoDB',
              'native_side_effects_may_survive_rollback': True}
    try:
        if (plan.get('format') != 'scratchrobin.mariadb.data-import-plan@1' or
                plan.get('execution_sha256') != plan_digest(plan) or
                plan.get('row_count') != len(plan.get('rows', [])) or not plan.get('ready_for_review')):
            raise ValueError('Native data review changed')
        if (connection.server_status & 1):
            raise ValueError('Import requires an independently owned idle connection')
        connection.autocommit = True
        cursor_charset = connection.cursor(); cursor_charset.execute('SET NAMES utf8mb4'); cursor_charset.close()
        cursor = connection.cursor()
        identity(cursor, plan)
        cursor.execute('SET SESSION lock_wait_timeout=2')
        cursor.execute('SET SESSION sql_quote_show_create=1')
        cursor.execute('SET SESSION sql_mode=%s', (plan['catalog_sql_mode'],))
        cursor.execute('START TRANSACTION')
        begun = True
        address = identifier(plan['database']) + '.' + identifier(plan['table'])
        # Acquire the table metadata lock before checking columns/definition.
        cursor.execute('SELECT ' + ','.join(identifier(name) for name in plan['columns']) + ' FROM ' + address + ' WHERE 1=0')
        cursor.fetchall()
        if native_layout(cursor, plan['database'], plan['table']) != plan['native_columns']:
            raise ValueError('Destination native column layout changed since review')
        cursor.execute('SHOW CREATE TABLE ' + address)
        definition = cursor.fetchone()
        if not definition or digest(definition[1]) != plan['native_definition_sha256']:
            raise ValueError('Destination native definition changed since review')
        cursor.execute('SET SESSION sql_mode=%s', (plan['sql_mode'],))
        cursor.execute('SET SESSION time_zone=%s', ('+00:00',))
        columns = {column['column_name']: column for column in plan['native_columns']}
        prefix = 'INSERT INTO ' + address + '(' + ','.join(identifier(name) for name in plan['columns']) + ') VALUES('
        started = time.monotonic()
        for row in plan['rows']:
            if time.monotonic() - started > 60:
                raise ValueError('Native import exceeded its 60 second dispatch budget')
            expressions, parameters = [], []
            for name, cell in zip(plan['columns'], row):
                expression, values = bound(cell, columns[name])
                expressions.append(expression)
                parameters.extend(values)
            dispatched = True
            cursor.execute(prefix + ','.join(expressions) + ')', parameters)
            if cursor.rowcount != 1:
                raise ValueError('Native import acknowledgement did not describe one inserted row')
            count += 1
        result['transaction_postimages'] = verify(connection, plan)
        committing = True
        connection.commit()
        acknowledged = True
        begun = False
        result.update(state='committed', acknowledged_rows=count, commit_acknowledged=True)
    except Exception as error:
        rollback_acknowledged = False
        if begun:
            try:
                connection.rollback()
                rollback_acknowledged = True
            except Exception:
                pass
        result.update(state='committed' if acknowledged else 'unknown_outcome' if committing else
                      'rolled_back' if dispatched and rollback_acknowledged and plan.get('storage_engine') == 'InnoDB' else
                      'partial_nontransactional' if dispatched and rollback_acknowledged else
                      'unknown_outcome' if dispatched else 'not_dispatched',
                      acknowledged_rows=count, rollback_acknowledged=rollback_acknowledged,
                      error_type=type(error).__name__, error_code=getattr(error, 'errno', None))
        if not dispatched and isinstance(error, ValueError):
            result['rejection_reason'] = str(error)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
    return result
