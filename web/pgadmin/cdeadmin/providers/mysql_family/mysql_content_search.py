"""Native, bounded MySQL value search; private observers and logical identities."""
from datetime import date, datetime, time as day_time, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from .mysql_catalog import identifier
from .mysql_monitoring import MySQLMonitor

TEXT = {'char', 'varchar', 'tinytext', 'text', 'mediumtext', 'longtext', 'enum', 'set'}
NUMERIC = {'tinyint', 'smallint', 'mediumint', 'int', 'bigint', 'decimal', 'float', 'double', 'year', 'bit'}
BINARY = {'binary', 'varbinary', 'tinyblob', 'blob', 'mediumblob', 'longblob'}
TEMPORAL = {'date', 'datetime', 'timestamp', 'time'}
MODES = {'text_exact', 'text_prefix', 'text_contains', 'numeric_equal', 'binary_exact', 'binary_contains', 'is_null'}
EXACT = 'CAST(TABLE_SCHEMA AS BINARY)=CAST(%s AS BINARY) AND CAST(TABLE_NAME AS BINARY)=CAST(%s AS BINARY)'


class SearchError(ValueError):
    pass


def name(value):
    if not isinstance(value, str) or not value or len(value) > 64 or '\0' in value:
        raise SearchError('Select an exact native database, table or column name')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), default=display).encode('utf8')).hexdigest()


def display(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'hex': bytes(value).hex(), 'bytes': len(value)}
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date, day_time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    raise SearchError('A native search value has an unsupported representation')


class Observer:
    def __init__(self, permissions, route):
        selected = dict(route)
        selected.pop('init_command', None)
        selected.update(get_warnings=False, raise_on_warnings=False)
        self.monitor = MySQLMonitor(permissions, selected, scope='server')
        try:
            self.monitor._open()
            self.connection = self.monitor._connection
            self.connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
            self.query("SET SESSION time_zone='+00:00',lock_wait_timeout=3,max_execution_time=3000,explain_json_format_version=1")
            self.identity = self.query('SELECT @@server_uuid AS server_uuid,VERSION() AS version,'
                'CURRENT_USER() AS account,CURRENT_ROLE() AS active_role,CONNECTION_ID() AS connection_id,'
                'PS_CURRENT_THREAD_ID() AS thread_id')[0]
            if self.identity['version'].split('-')[0] != '9.7.0':
                raise SearchError('Content search requires the selected native MySQL 9.7.0 profile')
        except BaseException:
            self.close()
            raise

    def query(self, sql, params=None, *, limit=4097):
        with self.connection.cursor(dictionary=True) as cursor:
            cursor.execute(sql, params)
            self.warning_count = cursor.warning_count
            if cursor.description is None:
                return []
            result = cursor.fetchmany(limit)
            if cursor.fetchone() is not None:
                raise SearchError('The native search observation exceeded its declared bound')
            self.warning_count = cursor.warning_count or 0
            return result

    def begin(self):
        self.connection.start_transaction(isolation_level='REPEATABLE READ', readonly=True)

    def rollback(self):
        self.connection.rollback()

    def close(self):
        try: self.monitor.close()
        finally: self.connection = None


def databases(observer, offset=0):
    page(offset)
    rows = observer.query('SELECT SCHEMA_NAME AS name FROM information_schema.SCHEMATA '
        'ORDER BY CAST(SCHEMA_NAME AS BINARY) LIMIT 101 OFFSET ' + str(offset), limit=101)
    return {'rows': rows[:100], 'next_offset': offset+100 if len(rows)>100 else None,
            'visibility': 'native permission-filtered schemas; invisible schemas are unknown'}


def page(offset):
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise SearchError('Select a bounded native catalog page')


def tables(observer, schema, offset=0):
    name(schema); page(offset)
    rows = observer.query('SELECT TABLE_NAME AS name,TABLE_TYPE AS kind,ENGINE AS engine '
        'FROM information_schema.TABLES WHERE CAST(TABLE_SCHEMA AS BINARY)=CAST(%s AS BINARY) '
        'ORDER BY CAST(TABLE_NAME AS BINARY) LIMIT 101 OFFSET ' + str(offset), (schema,), limit=101)
    return {'schema_name': schema, 'rows': rows[:100], 'next_offset': offset+100 if len(rows)>100 else None,
        'visibility': 'native permission-filtered persistent tables; views and session temporary tables are not searched'}


def describe(observer, schema, table):
    name(schema); name(table)
    base = observer.query('SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE,ENGINE,TABLE_COLLATION,CREATE_TIME '
        'FROM information_schema.TABLES WHERE ' + EXACT + ' LIMIT 2', (schema, table), limit=2)
    if len(base) != 1:
        raise SearchError('The exact table is invisible, absent or ambiguous')
    if base[0]['TABLE_TYPE'] != 'BASE TABLE':
        raise SearchError('Content search admits persistent native base tables')
    columns = observer.query('SELECT COLUMN_NAME,ORDINAL_POSITION,DATA_TYPE,LEFT(COLUMN_TYPE,256) AS COLUMN_TYPE,'
        'SHA2(COLUMN_TYPE,256) AS COLUMN_TYPE_SHA256,IS_NULLABLE,'
        'CHARACTER_SET_NAME,COLLATION_NAME,NUMERIC_PRECISION,NUMERIC_SCALE,EXTRA,'
        'SHA2(GENERATION_EXPRESSION,256) AS GENERATION_EXPRESSION_SHA256,PRIVILEGES '
        'FROM information_schema.COLUMNS WHERE ' + EXACT + ' ORDER BY ORDINAL_POSITION LIMIT 4097', (schema, table))
    if not columns or len(columns)>4096:
        raise SearchError('Native column metadata is empty or exceeds 4096 columns')
    indexes = observer.query('SELECT INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,SHA2(EXPRESSION,256) AS EXPRESSION,IS_VISIBLE '
        'FROM information_schema.STATISTICS WHERE ' + EXACT + ' ORDER BY INDEX_NAME,SEQ_IN_INDEX LIMIT 1025',
        (schema, table), limit=1025)
    if len(indexes)>1024:
        raise SearchError('Native index metadata exceeds the search observation bound')
    # PRIVILEGES describes admission, not table structure. Recheck it natively
    # when dispatching and navigating; do not turn a grant change into a DDL ID.
    structural = [{k: v for k, v in c.items() if k != 'PRIVILEGES'} for c in columns]
    source = {'table': base[0], 'columns': structural, 'indexes': indexes,
        'identity': {k:observer.identity[k] for k in ('server_uuid','account','active_role')}}
    by_name = {c['COLUMN_NAME']: c for c in columns}
    candidates = {}
    for item in indexes:
        candidates.setdefault(item['INDEX_NAME'], []).append(item)
    key = []
    for index_name in sorted(candidates, key=lambda n: (n != 'PRIMARY', n)):
        parts = candidates[index_name]
        if all(not p['NON_UNIQUE'] and p['SUB_PART'] is None and p['EXPRESSION'] is None and
            p['COLUMN_NAME'] in by_name and by_name[p['COLUMN_NAME']]['IS_NULLABLE']=='NO' and
            'select' in by_name[p['COLUMN_NAME']]['PRIVILEGES'].split(',') for p in parts):
            key = [p['COLUMN_NAME'] for p in parts]; break
    return {'schema_name': schema, 'table_name': table, 'engine': base[0]['ENGINE'], 'server_uuid':observer.identity['server_uuid'],
        'fingerprint': digest(source), 'columns': columns, 'indexes': indexes, 'key': key,
        'identity_basis': 'native server UUID, exact names and structural metadata; not an immutable native object ID'}


def options(request):
    if not isinstance(request, dict) or set(request)-{'mode','value','indexed_only','limit','seconds'}:
        raise SearchError('Select native search rules and explicit bounds')
    mode = request.get('mode')
    if mode not in MODES or type(request.get('indexed_only', False)) is not bool:
        raise SearchError('Select a supported native value comparison')
    limit, seconds = request.get('limit', 200), request.get('seconds', 30)
    if type(limit) is not int or not 1<=limit<=500 or type(seconds) is not int or not 1<=seconds<=60:
        raise SearchError('Search bounds are 1–500 matches and 1–60 seconds')
    value = request.get('value', '')
    if not isinstance(value, str) or len(value.encode('utf8'))>4096:
        raise SearchError('Search values are bounded to 4096 UTF-8 bytes')
    if mode.startswith('binary_'):
        if len(value)%2 or not re.fullmatch('[0-9a-fA-F]*', value):
            raise SearchError('Binary search requires exact pairs of hexadecimal digits')
        value = bytes.fromhex(value)
    elif mode == 'numeric_equal':
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,4})?', value):
            raise SearchError('Numeric search requires a finite decimal or exponent value')
        try:
            value = Decimal(value)
            if not value.is_finite() or abs(value.adjusted())>4000:
                raise ValueError()
            sign, digits, exponent = value.as_tuple()
            digits = list(digits)
            while digits and digits[-1]==0:
                digits.pop(); exponent += 1
            value = Decimal((sign,tuple(digits),exponent)) if digits else Decimal(0)
        except (InvalidOperation, ValueError):
            raise SearchError('The numeric search value is outside its native admission bound') from None
    return {'mode': mode, 'value': value, 'indexed_only': request.get('indexed_only', False), 'limit': limit, 'seconds': seconds}


def predicate(column, selected):
    field, kind, mode, value = identifier(column['COLUMN_NAME']), column['DATA_TYPE'], selected['mode'], selected['value']
    if mode == 'is_null':
        return field+' IS NULL', ()
    if mode.startswith('text_'):
        if kind not in TEXT | TEMPORAL | {'json'}:
            return None
        expression = field if kind in TEXT else 'CAST('+field+' AS CHAR CHARACTER SET utf8mb4)'
        if mode == 'text_exact':
            return expression+'=%s', (value,)
        # Explicit ESCAPE works under NO_BACKSLASH_ESCAPES too. Input %/_/!
        # are literal data; no application regex or wildcard grammar is added.
        escaped = value.replace('!', '!!').replace('%', '!%').replace('_', '!_')
        return expression+" LIKE %s ESCAPE '!'", ((('%' if mode=='text_contains' else '')+escaped+'%'),)
    if mode.startswith('binary_'):
        if kind not in BINARY:
            return None
        # Bound ASCII hex avoids connector text-protocol byte literals being
        # interpreted as invalid connection-charset text before comparison.
        return ((field+'=UNHEX(%s)', (value.hex(),)) if mode=='binary_exact' else
            ('LOCATE(UNHEX(%s),'+field+')>0', (value.hex(),)))
    if kind not in NUMERIC:
        return None
    if kind in {'float', 'double'}:
        return field+'=CAST(%s AS DOUBLE)', (str(value),)
    digits = value.as_tuple()
    scale = max(0, -digits.exponent)
    integer = max(0, len(digits.digits)+digits.exponent)
    if scale>30 or integer+scale>65:
        return None  # No lossy coercion to a different exact numeric value.
    expression, parameter = decimal_parameter(value)
    return field+'='+expression, (parameter,)


def decimal_parameter(value):
    # Connector/Python emits Decimal.__str__ in its text protocol. Exponents
    # would become approximate SQL literals. Bind fixed text and explicitly
    # recover its exact native DECIMAL type instead.
    scale = max(0, -value.as_tuple().exponent)
    return 'CAST(%s AS DECIMAL(65,'+str(scale)+'))', format(value, 'f')


def preview(column):
    field = identifier(column['COLUMN_NAME'])
    if column['DATA_TYPE']=='bit':
        return 'CAST(CAST('+field+' AS UNSIGNED) AS CHAR)'
    if column['DATA_TYPE']=='vector':
        return 'LEFT(VECTOR_TO_STRING('+field+'),256)'
    if column['DATA_TYPE'] in {'geometry','point','linestring','polygon','multipoint','multilinestring','multipolygon','geometrycollection'}:
        return 'HEX(LEFT(ST_AsWKB('+field+'),256))'
    if column['DATA_TYPE'] in TEXT | TEMPORAL | {'json'}:
        return 'LEFT(CONVERT('+field+' USING utf8mb4),256)'
    if column['DATA_TYPE'] in NUMERIC:
        return 'CAST('+field+' AS CHAR)'
    return 'HEX(LEFT(CAST('+field+' AS BINARY),256))'


def indexed_plan(observer, sql, parameters):
    result = observer.query('EXPLAIN FORMAT=JSON '+sql, parameters, limit=1)
    if len(result)!=1:
        return False
    plan = json.loads(next(iter(result[0].values())))
    tables_seen = []
    def walk(value):
        if isinstance(value, dict):
            if 'table_name' in value:
                tables_seen.append(value)
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(plan)
    return bool(tables_seen) and all(t.get('access_type') in
        {'const','eq_ref','ref','ref_or_null','range','index_merge','fulltext'} and t.get('key') for t in tables_seen)
