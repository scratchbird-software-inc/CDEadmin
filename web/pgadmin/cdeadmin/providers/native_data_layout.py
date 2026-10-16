"""Exact native relation layouts for typed DDN capture and reviewed imports."""
import hashlib
import json
import os
import re


def quote(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('Native identifier is invalid')
    return '"' + value.replace('"', '""') + '"'


def duckdb_generated(source):
    """Read generated-column markers from DuckDB's native CREATE serialization."""
    import duckdb
    encoded = source.encode('utf8')
    tokens = duckdb.tokenize(source)
    words = []
    for index, (offset, kind) in enumerate(tokens):
        end = tokens[index + 1][0] if index + 1 < len(tokens) else len(encoded)
        word = encoded[offset:end].decode('utf8').strip()
        if kind == duckdb.token_type.comment: continue
        words.append((kind, word))
    sections, current, depth = [], [], 0
    for kind, word in words:
        if word == '(':
            depth += 1
            if depth == 1: continue
        if word == ')':
            depth -= 1
            if depth == 0:
                sections.append(current); break
        if depth == 1 and word == ',': sections.append(current); current = []
        elif depth: current.append((kind, word))
    result = set()
    for section in sections:
        if not section or section[0][0] != duckdb.token_type.identifier: continue
        name = section[0][1]
        if name.startswith('"') and name.endswith('"'): name = name[1:-1].replace('""', '"')
        keywords = [word.lower() for kind, word in section[1:] if kind == duckdb.token_type.keyword]
        if any(keywords[index:index + 3] == ['generated', 'always', 'as'] for index in range(len(keywords))): result.add(name)
    return result


def inspect_relation(connection, engine, resource_id, route):
    if engine not in {'postgresql', 'duckdb', 'sqlite'}:
        raise ValueError('An exact native data engine is required')
    columns = []
    if engine == 'postgresql':
        match = re.fullmatch(r'postgresql:pg_class:([1-9][0-9]{0,9})', resource_id or '')
        if not match or int(match[1]) > 4294967295: raise ValueError('Select an exact PostgreSQL relation')
        oid = int(match[1])
        from psycopg import Cursor
        from psycopg.rows import tuple_row
        cursor = Cursor(connection, row_factory=tuple_row)
        try:
            cursor.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()')
            database = cursor.fetchone()[0]
            if database != route['database_id']: raise ValueError('Native database identity changed')
            cursor.execute('SELECT n.nspname,c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=%s', (oid,))
            row = cursor.fetchone()
            if not row or row[2] not in {'r', 'p', 'v', 'm', 'f'}: raise ValueError('Native relation is unavailable')
            schema, name, kind, row_security, force_security = row
            cursor.execute('''SELECT a.attnum,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod),a.atttypid,a.atttypmod,
                a.attnotnull,a.attidentity,a.attgenerated,a.attcollation,pg_catalog.pg_get_expr(d.adbin,d.adrelid)
                FROM pg_catalog.pg_attribute a LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', (oid,))
            for ordinal, label, native_type, type_oid, modifier, not_null, identity, generated, collation, default in cursor.fetchall():
                columns.append({'native_name': label, 'native_type': native_type, 'ordinal_position': ordinal,
                    'generated': bool(generated), 'identity': identity, 'type_oid': type_oid, 'type_modifier': modifier,
                    'nullable': not not_null, 'collation_oid': collation, 'default': default})
            definition = {'row_security': row_security, 'force_row_security': force_security, 'columns': columns}
        finally: cursor.close()
        database_identity = {'database_oid': database}
        version = connection.info.server_version
        version = str(version // 10000) + '.' + str(version % 10000)
        path = [schema, name]
    else:
        prefix = engine + ':'
        if not isinstance(resource_id, str) or not resource_id.startswith(prefix): raise ValueError('Select an exact native relation')
        parts = json.loads(resource_id[len(prefix):])
        count = 4 if engine == 'duckdb' else 3
        if not isinstance(parts, list) or len(parts) != count or any(not isinstance(part, str) or not part or '\0' in part for part in parts):
            raise ValueError('Invalid native relation identity')
        if resource_id != prefix + json.dumps(parts, ensure_ascii=False, separators=(',', ':')):
            raise ValueError('Noncanonical native relation identity')
        kind, *path = parts
        from .embedded_route import contained_database
        filename = contained_database(route)
        info = os.stat(filename)
        database_identity = {'registered_file': [info.st_dev, info.st_ino]}
        if engine == 'sqlite':
            schema, name = path
            row = connection.execute('SELECT type,sql FROM ' + quote(schema) + '.sqlite_schema WHERE name=?', (name,)).fetchone()
            if not row or row[0] not in {'table', 'view'}: raise ValueError('Native relation is unavailable')
            definition = row[1]
            actual_kind = 'view' if row[0] == 'view' else 'fts-table' if re.search(r'\bUSING\s+fts\d?\b', definition or '', re.I) else 'virtual-table' if re.match(r'^\s*CREATE\s+VIRTUAL\s+TABLE', definition or '', re.I) else 'table'
            if actual_kind != kind: raise ValueError('Native relation kind changed')
            for ordinal, label, native_type, not_null, default, primary, hidden in connection.execute('PRAGMA ' + quote(schema) + '.table_xinfo(' + quote(name) + ')'):
                if hidden == 1: continue  # SELECT * excludes virtual hidden columns.
                columns.append({'native_name': label, 'native_type': native_type, 'ordinal_position': ordinal,
                    'generated': hidden in {2, 3}, 'identity': '', 'nullable': not bool(not_null),
                    'default': default, 'primary_key_position': primary, 'hidden': hidden})
            version = connection.execute('SELECT sqlite_version()').fetchone()[0]
        else:
            database, schema, name = path
            if kind not in {'table', 'view'}: raise ValueError('Select a native DuckDB table or view')
            function = 'duckdb_tables()' if kind == 'table' else 'duckdb_views()'
            label = 'table_name' if kind == 'table' else 'view_name'
            row = connection.execute('SELECT sql FROM ' + function + ' WHERE database_name=? AND schema_name=? AND ' + label + '=? AND NOT internal', path).fetchone()
            if row is None: raise ValueError('Native relation is unavailable')
            definition = row[0]
            generated = duckdb_generated(definition) if kind == 'table' else set()
            for label, ordinal, default, nullable, native_type in connection.execute('SELECT column_name,column_index,column_default,is_nullable,data_type FROM duckdb_columns() WHERE database_name=? AND schema_name=? AND table_name=? ORDER BY column_index', path).fetchall():
                columns.append({'native_name': label, 'native_type': native_type, 'ordinal_position': ordinal,
                    'generated': label in generated, 'identity': '', 'nullable': nullable, 'default': default})
            version = connection.execute('SELECT version()').fetchone()[0].lstrip('v')
    if not 1 <= len(columns) <= 256: raise ValueError('Native data layout needs 1–256 columns')
    return {'engine_id': engine, 'resource_id': resource_id, 'path': path, 'kind': kind, 'native_version': version,
            'database_identity': database_identity, 'native_columns': columns,
            'definition_sha256': hashlib.sha256(json.dumps(definition, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
