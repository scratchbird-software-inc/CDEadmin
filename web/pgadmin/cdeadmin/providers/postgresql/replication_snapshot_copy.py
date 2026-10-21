"""Native relation discovery and COPY identity in an owned decoding snapshot."""
from .temporary_slots import TemporarySlotError


def options(operation, value):
    if operation == 'snapshot_tables':
        if set(value) - {'offset', 'limit', 'schema'}:
            raise TemporarySlotError('Select a bounded native snapshot relation page')
        offset, limit = value.get('offset', 0), value.get('limit', 25)
        if type(offset) is not int or not 0 <= offset <= 9223372036854775807 or type(limit) is not int or not 1 <= limit <= 100:
            raise TemporarySlotError('Select a bounded native snapshot relation page')
        schema = value.get('schema')
        if schema is not None:
            try:
                valid = isinstance(schema, str) and 1 <= len(schema.encode('utf8')) <= 63 and '\0' not in schema
            except UnicodeError:
                valid = False
            if not valid:
                raise TemporarySlotError('Select an exact native snapshot schema name or all schemas')
        return {'offset': offset, 'limit': limit, 'schema': schema}
    if operation not in {'snapshot_copy', 'snapshot_inspect'} or set(value) - (
            {'relation_oid'} if operation == 'snapshot_inspect' else {'relation_oid', 'include_descendants', 'format', 'copy_options'}):
        raise TemporarySlotError('Select an exact original-snapshot relation copy')
    oid = value.get('relation_oid')
    if (not isinstance(oid, str) or not oid.isascii() or not oid.isdecimal() or
            not 1 <= len(oid) <= 10 or not 1 <= int(oid) <= 4294967295 or str(int(oid)) != oid):
        raise TemporarySlotError('Select an exact native snapshot relation OID')
    if operation == 'snapshot_inspect':
        return {'relation_oid': oid}
    descendants = value.get('include_descendants', True)
    if type(descendants) is not bool:
        raise TemporarySlotError('Select native descendant inclusion explicitly')
    format = value.get('format', 'binary')
    if not isinstance(format, str) or format not in {'binary', 'text', 'csv'}:
        raise TemporarySlotError('Select a native COPY output format')
    selected = value.get('copy_options', {})
    allowed = {'delimiter', 'null_string', 'header', 'quote', 'escape', 'force_quote', 'encoding'}
    if not isinstance(selected, dict) or set(selected) - allowed:
        raise TemporarySlotError('Select exact native COPY TO options')
    result = {}
    for key, item in selected.items():
        if item is None:
            continue
        if key == 'header':
            valid = type(item) is bool
        elif key == 'force_quote':
            names = item if isinstance(item, list) else []
            try:
                valid = item == 'all' or isinstance(item, list) and 1 <= len(item) <= 65535 and all(
                    isinstance(name, str) and 1 <= len(name.encode('utf8')) <= 63 and '\0' not in name for name in names)
            except UnicodeError:
                valid = False
        else:
            try:
                valid = isinstance(item, str) and '\0' not in item and len(item.encode('utf8')) <= 1048576
            except UnicodeError:
                valid = False
        if not valid:
            raise TemporarySlotError('Native COPY options require exact typed native values')
        result[key] = item
    return {'relation_oid': oid, 'include_descendants': descendants, 'format': format, 'copy_options': result}


def text(value):
    if isinstance(value, bytes):
        try:
            return value.decode('utf8')
        except UnicodeError:
            raise TemporarySlotError('This native snapshot identity is not representable as UTF8') from None
    return value


def catalog(cursor, selected):
    cursor.execute("""SELECT c.oid::pg_catalog.text,n.nspname,c.relname,c.relkind,
        pg_catalog.has_table_privilege(c.oid,'SELECT'),pg_catalog.row_security_active(c.oid)
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p','m','v','f') AND (%s::pg_catalog.text IS NULL OR n.nspname::pg_catalog.text COLLATE pg_catalog."C"=%s::pg_catalog.text COLLATE pg_catalog."C")
        ORDER BY c.oid LIMIT %s OFFSET %s""", (selected['schema'], selected['schema'], selected['limit'] + 1, selected['offset']))
    rows = cursor.fetchall()
    return {'relations': [dict(zip(('relation_oid', 'schema', 'name', 'native_kind', 'can_select', 'row_security_active'),
            map(text, row))) for row in rows[:selected['limit']]],
            'offset': selected['offset'], 'limit': selected['limit'], 'schema': selected['schema'], 'more': len(rows) > selected['limit'],
            'observation_source': 'original-native-snapshot-transaction', 'current_catalog_after_snapshot_observed': False}


def relation(connection, selected):
    from psycopg import ClientCursor
    from psycopg.rows import tuple_row
    with ClientCursor(connection, row_factory=tuple_row) as cursor:
        cursor.execute("""SELECT c.oid::pg_catalog.text,n.nspname,c.relname,c.relkind,
            pg_catalog.row_security_active(c.oid),pg_catalog.has_table_privilege(c.oid,'SELECT')
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE c.oid=%s::pg_catalog.oid AND c.relkind IN ('r','p','m','v','f')""", (selected['relation_oid'],))
        row = cursor.fetchone()
        if row is None or text(row[0]) != selected['relation_oid']:
            raise TemporarySlotError('The selected relation is absent from the original native snapshot catalog')
        result = dict(zip(('relation_oid', 'schema', 'name', 'native_kind', 'row_security_active', 'can_select'), map(text, row)))
        cursor.execute("""WITH RECURSIVE native_types AS (
            SELECT a.attnum,a.attname,a.atttypid,a.atttypmod,a.attcollation,
                a.attnotnull,a.attgenerated,a.attidentity,t.oid AS wire_type_oid,
                a.atttypmod AS wire_type_modifier,t.typtype,t.typbasetype,t.typtypmod
            FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_type t ON t.oid=a.atttypid
            WHERE a.attrelid=%s::pg_catalog.oid AND a.attnum>0 AND NOT a.attisdropped
            UNION ALL
            SELECT n.attnum,n.attname,n.atttypid,n.atttypmod,n.attcollation,
                n.attnotnull,n.attgenerated,n.attidentity,t.oid,
                n.typtypmod,
                t.typtype,t.typbasetype,t.typtypmod
            FROM native_types n JOIN pg_catalog.pg_type t ON t.oid=n.typbasetype
            WHERE n.typtype='d'
        ) SELECT attnum,attname,atttypid::pg_catalog.text,atttypmod,attcollation::pg_catalog.text,
            attnotnull,attgenerated,attidentity,wire_type_oid::pg_catalog.text,wire_type_modifier
            FROM native_types WHERE typtype<>'d' ORDER BY attnum""", (selected['relation_oid'],))
        result['columns'] = [dict(zip(('ordinal', 'name', 'type_oid', 'type_modifier', 'collation_oid',
            'not_null', 'generated', 'identity', 'wire_type_oid', 'wire_type_modifier'), map(text, column))) for column in cursor.fetchall()]
    result['row_scope'] = 'native-authorized-SELECT-in-original-snapshot'
    if result['native_kind'] == 'f':
        result['remote_snapshot_synchronization_observed'] = False
    return result


def qualified(source):
    from psycopg import sql
    return sql.Identifier(source['schema'], source['name'])


def lock_and_verify(cursor, source):
    from psycopg import sql
    identity = qualified(source)
    # regclass input resolves the currently locked name through native name
    # lookup. A transaction's old pg_class snapshot cannot prove current reuse.
    rendered = identity.as_string(cursor.connection)
    def verify_identity():
        cursor.execute('SELECT %s::pg_catalog.regclass::pg_catalog.oid::pg_catalog.text,pg_catalog.row_security_active(%s::pg_catalog.regclass)', (rendered, rendered))
        oid, row_security = cursor.fetchone()
        if text(oid) != source['relation_oid'] or row_security != source['row_security_active']:
            raise TemporarySlotError('The locked native relation or row-security scope changed after review')
    if source['native_kind'] in {'r', 'p', 'v'}:
        cursor.execute(sql.SQL('LOCK TABLE ONLY {} IN ACCESS SHARE MODE').format(identity))
    # Native LOCK TABLE rejects materialized/foreign relations. A zero-row
    # SELECT obtains their native AccessShareLock without exporting rows;
    # compare the current name before planning and after that lock is held.
    verify_identity()
    columns = sql.SQL(', ').join(sql.Identifier(column['name']) for column in source['columns']) if source['columns'] else sql.SQL('*')
    scope = sql.SQL('') if source['include_descendants'] else sql.SQL('ONLY ')
    query = sql.SQL('SELECT {} FROM {}{}').format(columns, scope, identity)
    cursor.execute(query + sql.SQL(' LIMIT 0'))
    observed = [(text(column.name), str(column.type_code), cursor.pgresult.fmod(index))
                for index, column in enumerate(cursor.description or ())]
    expected = [(column['name'], column['wire_type_oid'], column['wire_type_modifier']) for column in source['columns']]
    if observed != expected:
        raise TemporarySlotError('The native COPY column identities changed after review')
    verify_identity()
    clauses = [sql.SQL('FORMAT {}').format(sql.SQL(source['copy_format']))]
    for key, value in source['copy_options'].items():
        if key == 'force_quote':
            value = sql.SQL('*') if value == 'all' else sql.SQL('({})').format(
                sql.SQL(', ').join(sql.Identifier(name) for name in value))
            clauses.append(sql.SQL('FORCE_QUOTE {}').format(value))
        elif key == 'header':
            clauses.append(sql.SQL('HEADER {}').format(sql.SQL('true' if value else 'false')))
        else:
            clauses.append(sql.SQL('{} {}').format(sql.SQL({'null_string': 'NULL'}.get(key, key.upper())), sql.Literal(value)))
    return sql.SQL('COPY ({}) TO STDOUT ({})').format(query, sql.SQL(', ').join(clauses))
