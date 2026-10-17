"""Observe native eponymous tables without executing their result-producing VM."""
from functools import lru_cache
import sqlite3

# Native3.53 builtin module registrations, including modules registered only
# when their names are resolved. Availability and columns are native facts.
BUILTINS = ('json_each', 'json_tree', 'jsonb_each', 'jsonb_tree', 'carray',
            'dbstat', 'sqlite_dbpage', 'sqlite_stmt', 'fts3tokenize')
FOLD = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def quote(name):
    return '"' + name.replace('"', '""') + '"'


@lru_cache(maxsize=1)
def native_runtime():
    probe = sqlite3.connect(':memory:')
    try:
        return sqlite3.sqlite_version, probe.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally:
        probe.close()


@lru_cache(maxsize=1)
def inventory():
    probe = sqlite3.connect(':memory:')
    try:
        names = set(BUILTINS)
        names.update('pragma_' + row[0] for row in probe.execute('PRAGMA pragma_list'))
        observed = []
        for name in sorted(names):
            try:
                columns = list(probe.execute('PRAGMA main.table_xinfo(' + quote(name) + ')'))
            except sqlite3.Error:
                continue
            if columns:
                observed.append(name)
        return tuple(observed)
    finally:
        probe.close()


def discover(cursor, schemas, relations):
    """Respect live authorization and name masking on the original connection.

    table_xinfo resolves and connects a virtual table, but does not call its
    xFilter or run the wrapped PRAGMA. A same-named real relation masks the
    eponymous table in that schema and is never relabeled as a native function.
    """
    masked = {(schema.translate(FOLD), name.translate(FOLD)) for schema, name in relations}
    result = []
    for name in inventory():
        scopes = []
        for schema in schemas:
            if (schema.translate(FOLD), name.translate(FOLD)) in masked:
                scopes.append({'schema': schema, 'available': False, 'masked_by_relation': True})
                continue
            try:
                cursor.execute('PRAGMA ' + quote(schema) + '.table_xinfo(' + quote(name) + ')')
                columns = cursor.fetchall()
            except sqlite3.Error as error:
                code = getattr(error, 'sqlite_errorcode', None)
                if type(code) is not int or code & 255 not in {sqlite3.SQLITE_ERROR, sqlite3.SQLITE_AUTH}:
                    raise
                scopes.append({'schema': schema, 'available': False, 'native_error_code': code,
                               'native_error_name': getattr(error, 'sqlite_errorname', None)})
            else:
                scopes.append({'schema': schema, 'available': bool(columns),
                    'columns': [{'ordinal_position': row[0], 'name': row[1], 'data_type': row[2],
                                 'nullable': not bool(row[3]), 'default': row[4],
                                 'primary_key_position': row[5], 'hidden': row[6]} for row in columns]})
        result.append({'name': name, 'scopes': scopes,
            'available': any(scope['available'] for scope in scopes),
            'observation_complete': all(scope['available'] or scope.get('masked_by_relation') for scope in scopes),
            'authority': 'native table_xinfo; result-producing virtual-table VM and wrapped PRAGMA not executed',
            'unqualified_available': bool(scopes) and all(scope['available'] for scope in scopes)})
    return result
