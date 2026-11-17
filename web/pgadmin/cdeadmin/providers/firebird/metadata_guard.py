"""Reviewed native catalog records, checked inside the executing snapshot.

A DB_KEY alone is not a persistent object identity. Pair it with the native
record's creating/updating transaction and database GUID/file identity. The
executing snapshot spans this check and the DDL. A concurrent replacement
conflicts when DDL rewrites/deletes the checked catalog record; native table
DROP is explicitly qualified. This is not a general lock on other catalog
rows, such as grants, nor an external/security-database identity protocol.
"""
from collections.abc import Mapping

from ...sdk import RelationalClientError


CATALOGS = {
    'database': ('RDB$DATABASE', None),
    'shadow': ('RDB$FILES', 'RDB$SHADOW_NUMBER'),
    'table': ('RDB$RELATIONS', 'RDB$RELATION_NAME'),
    'view': ('RDB$RELATIONS', 'RDB$RELATION_NAME'),
    'index': ('RDB$INDICES', 'RDB$INDEX_NAME'),
    'constraint': ('RDB$RELATION_CONSTRAINTS', 'RDB$CONSTRAINT_NAME'),
    'sequence': ('RDB$GENERATORS', 'RDB$GENERATOR_NAME'),
    'domain': ('RDB$FIELDS', 'RDB$FIELD_NAME'),
    'trigger': ('RDB$TRIGGERS', 'RDB$TRIGGER_NAME'),
    'procedure': ('RDB$PROCEDURES', 'RDB$PROCEDURE_NAME'),
    'function': ('RDB$FUNCTIONS', 'RDB$FUNCTION_NAME'),
    'external-function': ('RDB$FUNCTIONS', 'RDB$FUNCTION_NAME'),
    'package': ('RDB$PACKAGES', 'RDB$PACKAGE_NAME'),
    'exception': ('RDB$EXCEPTIONS', 'RDB$EXCEPTION_NAME'),
    'role': ('RDB$ROLES', 'RDB$ROLE_NAME'),
    'collation': ('RDB$COLLATIONS', 'RDB$COLLATION_NAME'),
    'character-set': ('RDB$CHARACTER_SETS', 'RDB$CHARACTER_SET_NAME'),
    'blob-filter': ('RDB$FILTERS', 'RDB$FUNCTION_NAME'),
    'authentication-mapping': ('RDB$AUTH_MAPPING', 'RDB$MAP_NAME'),
    'column': ('RDB$RELATION_FIELDS', 'RDB$FIELD_NAME'),
    'publication': ('RDB$PUBLICATIONS', 'RDB$PUBLICATION_NAME'),
}
NON_EXISTING_TARGET = frozenset({'inspect', 'create', 'insert', 'update', 'delete'})


def selection(request, administration):
    kind = request.get('resource_kind')
    if (kind not in CATALOGS or request.get('operation_id') in NON_EXISTING_TARGET
            or not isinstance(request.get('target_resource'), Mapping)):
        return None
    path = ([request['_provider_route']['database']] if kind == 'database'
            else administration._target_path(request['target_resource']))
    return {'resource_kind': kind, 'path': list(path)}


def _refused(message):
    error = RelationalClientError(message)
    error.code = 'FIREBIRD_STALE_NATIVE_TARGET'
    error.rejected = error.nothing_changed = True
    error.native_dispatched = error.automatic_retry = False
    return error


def _record(cursor, table, predicates, values, multiple=False):
    # Tables/columns are private constants; object names remain parameters.
    cursor.execute('SELECT X.RDB$DB_KEY, X.RDB$RECORD_VERSION FROM ' + table +
                   ' X WHERE ' + ' AND '.join(predicates), tuple(values))
    rows = cursor.fetchall()
    if not rows or not multiple and len(rows) != 1:
        raise _refused('Native target is absent or ambiguous; refresh and review again')
    result = []
    for key, version in rows:
        if (not isinstance(key, (bytes, bytearray, memoryview)) or len(key) != 8
                or type(version) is not int or version < 0):
            raise _refused('Native catalog record identity is unavailable; no mutation dispatched')
        result.append({'record_key_hex': bytes(key).hex(), 'record_transaction': str(version)})
    return sorted(result, key=lambda item: item['record_key_hex']) if multiple else result[0]


def observe(connection, selected):
    import firebird.driver as native
    kind, path = selected['resource_kind'], selected['path']
    if kind not in CATALOGS or not isinstance(path, list) or not path:
        raise _refused('Native target binding is invalid')
    table, name_field = CATALOGS[kind]
    predicates, values = (['X.' + name_field + ' = ?'], [path[-1]]) if name_field else (['1 = 1'], [])
    if kind == 'shadow':
        from .shadows import numeric, MAX_NUMBER
        values = [int(numeric(path[-1], 'Shadow number', 1, MAX_NUMBER))]
    if kind == 'column':
        if len(path) != 2:
            raise _refused('A column requires its exact parent relation')
        predicates.append('X.RDB$RELATION_NAME = ?'); values.append(path[0])
    if kind in {'constraint', 'index', 'trigger'} and len(path) == 2:
        predicates.append('X.RDB$RELATION_NAME = ?'); values.append(path[0])
    if kind in {'procedure', 'function'}:
        if len(path) == 2:
            predicates.append('X.RDB$PACKAGE_NAME = ?'); values.append(path[0])
        elif len(path) == 1:
            predicates.append('X.RDB$PACKAGE_NAME IS NULL')
        else:
            raise _refused('Native routine package identity is invalid')
    guid = connection.info.get_info(native.DbInfoCode.DB_GUID)
    file_id = connection.info.get_info(native.DbInfoCode.DB_FILE_ID)
    if not isinstance(guid, str) or not guid or not isinstance(file_id, str) or not file_id:
        raise _refused('Native database GUID/file identity is unavailable')
    cursor = connection.cursor()
    try:
        record = _record(cursor, table, predicates, values, multiple=kind == 'shadow')
        parent = None
        if kind in {'column', 'constraint', 'index', 'trigger'} and len(path) == 2:
            parent = _record(cursor, 'RDB$RELATIONS', ['X.RDB$RELATION_NAME = ?'], [path[0]])
        elif kind in {'procedure', 'function'} and len(path) == 2:
            parent = _record(cursor, 'RDB$PACKAGES', ['X.RDB$PACKAGE_NAME = ?'], [path[0]])
        return {'schema': 'scratchrobin.firebird.native-target@1',
                **selected, 'database_guid': guid, 'database_file_id': file_id,
                'record': record, 'parent': parent}
    finally:
        cursor.close()


def verify(connection, expected):
    import firebird.driver as native
    try:
        # The query starts only an idle original transaction. It never ends
        # an existing transaction or changes its isolation.
        actual = observe(connection, {'resource_kind': expected['resource_kind'],
                                      'path': expected['path']})
        if connection.main_transaction.info.isolation != native.Isolation.SNAPSHOT:
            raise _refused('Reviewed metadata changes require a native SNAPSHOT transaction; use an independently reviewed operation')
        if actual != expected:
            raise _refused('Native object changed since review; refresh and review again')
    except (KeyError, TypeError):
        raise _refused('Native target binding is incomplete; refresh and review again') from None
