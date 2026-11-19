"""Reviewed native catalog records, checked inside the executing snapshot.

A DB_KEY alone is not a persistent object identity. Pair it with the native
record's creating/updating transaction and database GUID/file identity. The
executing snapshot spans this check and the DDL. A concurrent replacement
conflicts when DDL rewrites/deletes the checked catalog record; native table
DROP is explicitly qualified.

Security-database virtual projections (SEC$USERS, SEC$USER_ATTRIBUTES and
SEC$GLOBAL_AUTH_MAPPING) do not expose RDB$RECORD_VERSION or password hashes;
for those targets, observe/verify binds non-secret projected state by SHA-256
and marks record_version_available=False explicitly rather than claiming an
external security-database transaction lock.
"""
from collections.abc import Mapping
import hashlib
import json

from pgadmin.cdeadmin.navigator import resource_native
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
SEC_CATALOGS = frozenset({'user', 'global-authentication-mapping'})
PRIVILEGE_OBJECT_KINDS = {
    'TABLE': 'table',
    'VIEW': 'view',
    'PROCEDURE': 'procedure',
    'FUNCTION': 'function',
    'PACKAGE': 'package',
    'SEQUENCE': 'sequence',
    'GENERATOR': 'sequence',
    'DOMAIN': 'domain',
    'EXCEPTION': 'exception',
}
NON_EXISTING_TARGET = frozenset({'inspect', 'create', 'insert', 'update', 'delete'})


def selection(request, administration):
    kind = request.get('resource_kind')
    operation = request.get('operation_id')
    if operation in NON_EXISTING_TARGET:
        return None
    target = request.get('target_resource')
    draft = request.get('draft') if isinstance(request.get('draft'), Mapping) else {}
    if kind == 'privilege' and operation in {'grant', 'revoke'}:
        if isinstance(target, Mapping) and target.get('resource_kind') == 'privilege':
            info = resource_native(target)
            if (info.get('catalog_source') != 'SEC$DB_CREATORS'
                    and info.get('grantee') and info.get('privilege')):
                return {
                    'resource_kind': 'privilege',
                    'path': [str(target.get('display_name') or info['grantee'])],
                    'privilege_key': {
                        'grantee': str(info['grantee']).rstrip(' '),
                        'relation_name': (
                            '' if info.get('object_name') == 'database'
                            else str(info.get('object_name') or '').rstrip(' ')
                        ),
                        'field_name': str(info.get('field') or '').rstrip(' '),
                        'privilege': str(info['privilege']).strip(),
                        'grantor': str(info.get('grantor') or '').rstrip(' '),
                        'user_type': int(info['user_type']),
                        'object_type': int(info['object_type']),
                    },
                }
            return None
        if draft.get('privilege_scope', 'object') == 'object':
            obj_kind = PRIVILEGE_OBJECT_KINDS.get(draft.get('object_type'))
            obj_name = draft.get('object_name')
            if obj_kind and isinstance(obj_name, str) and obj_name:
                return {'resource_kind': obj_kind, 'path': [obj_name]}
        return None
    if not isinstance(target, Mapping):
        return None
    if (operation == 'create_or_alter' and 'name' in draft
            and draft.get('name') != target.get('display_name')):
        return None
    if kind in SEC_CATALOGS:
        path = list(administration._target_path(target))
        if kind == 'user':
            plugin = resource_native(target).get('plugin') or draft.get('plugin')
            result = {'resource_kind': 'user', 'path': path}
            if isinstance(plugin, str) and plugin:
                result['plugin'] = plugin
            return result
        return {'resource_kind': kind, 'path': path}
    if kind not in CATALOGS:
        return None
    path = ([request['_provider_route']['database']] if kind == 'database'
            else administration._target_path(target))
    return {'resource_kind': kind, 'path': list(path)}


def _refused(message):
    error = RelationalClientError(message)
    error.code = 'FIREBIRD_STALE_NATIVE_TARGET'
    error.rejected = error.nothing_changed = True
    error.native_dispatched = error.automatic_retry = False
    return error


def _materialize(value):
    if callable(getattr(value, 'read', None)):
        reader = value
        try:
            value = reader.read()
        finally:
            reader.close()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'bytes_hex': bytes(value).hex()}
    return value


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


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


def _observe_sec(cursor, selected):
    kind = selected['resource_kind']
    name = selected['path'][-1]
    if kind == 'user':
        plugin = selected.get('plugin')
        predicates = ['TRIM(TRAILING FROM SEC$USER_NAME) = ?']
        params = [name]
        if isinstance(plugin, str) and plugin:
            predicates.append('TRIM(TRAILING FROM SEC$PLUGIN) = ?')
            params.append(plugin)
        cursor.execute(
            'SELECT TRIM(TRAILING FROM SEC$USER_NAME), '
            'TRIM(TRAILING FROM SEC$PLUGIN), SEC$FIRST_NAME, SEC$MIDDLE_NAME, '
            'SEC$LAST_NAME, SEC$ACTIVE, SEC$ADMIN, SEC$DESCRIPTION '
            'FROM SEC$USERS WHERE ' + ' AND '.join(predicates),
            tuple(params),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise _refused('Native user target is absent or ambiguous; refresh and review again')
        materialized = [_materialize(col) for col in rows[0]]
        resolved_user, resolved_plugin = materialized[0], materialized[1]
        cursor.execute(
            'SELECT TRIM(TRAILING FROM SEC$KEY), SEC$VALUE '
            'FROM SEC$USER_ATTRIBUTES '
            'WHERE TRIM(TRAILING FROM SEC$USER_NAME) = ? '
            'AND TRIM(TRAILING FROM SEC$PLUGIN) = ? ORDER BY 1, 2',
            (resolved_user, resolved_plugin),
        )
        attrs = [[_materialize(k), _materialize(v)] for k, v in cursor.fetchall()]
        return {
            'identity_authority': 'SEC$USERS+SEC$USER_ATTRIBUTES',
            'plugin': resolved_plugin,
            'record_version_available': False,
            'projection_sha256': _digest({'user': materialized, 'attributes': attrs}),
        }
    if kind == 'global-authentication-mapping':
        cursor.execute(
            'SELECT TRIM(TRAILING FROM SEC$MAP_NAME), '
            'TRIM(TRAILING FROM SEC$MAP_USING), '
            'TRIM(TRAILING FROM SEC$MAP_PLUGIN), '
            'TRIM(TRAILING FROM SEC$MAP_DB), '
            'TRIM(TRAILING FROM SEC$MAP_FROM_TYPE), SEC$MAP_FROM, '
            'SEC$MAP_TO_TYPE, TRIM(TRAILING FROM SEC$MAP_TO), SEC$DESCRIPTION '
            'FROM SEC$GLOBAL_AUTH_MAPPING '
            'WHERE TRIM(TRAILING FROM SEC$MAP_NAME) = ?',
            (name,),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise _refused(
                'Native global mapping target is absent or ambiguous; refresh and review again'
            )
        materialized = [_materialize(col) for col in rows[0]]
        return {
            'identity_authority': 'SEC$GLOBAL_AUTH_MAPPING',
            'record_version_available': False,
            'projection_sha256': _digest({'mapping': materialized}),
        }
    raise _refused('Native security target binding is invalid')


def _observe_privilege(cursor, selected):
    pk = selected.get('privilege_key')
    if not isinstance(pk, Mapping):
        raise _refused('Native privilege target binding is incomplete')
    predicates = [
        'TRIM(TRAILING FROM X.RDB$USER) = ?',
        'TRIM(TRAILING FROM X.RDB$PRIVILEGE) = ?',
        'TRIM(TRAILING FROM X.RDB$GRANTOR) = ?',
        'X.RDB$USER_TYPE = ?',
        'X.RDB$OBJECT_TYPE = ?',
    ]
    values = [
        pk['grantee'], pk['privilege'], pk['grantor'],
        int(pk['user_type']), int(pk['object_type']),
    ]
    if pk.get('relation_name'):
        predicates.append('TRIM(TRAILING FROM X.RDB$RELATION_NAME) = ?')
        values.append(pk['relation_name'])
    else:
        predicates.append(
            "(X.RDB$RELATION_NAME IS NULL OR TRIM(TRAILING FROM X.RDB$RELATION_NAME) = '')"
        )
    if not (pk['privilege'] == 'M' and int(pk['object_type']) == 13):
        predicates.append("COALESCE(TRIM(TRAILING FROM X.RDB$FIELD_NAME), '') = ?")
        values.append(pk.get('field_name') or '')
    return _record(cursor, 'RDB$USER_PRIVILEGES', predicates, values, multiple=True)


def observe(connection, selected):
    import firebird.driver as native
    kind, path = selected.get('resource_kind'), selected.get('path')
    if (kind not in CATALOGS and kind not in SEC_CATALOGS and kind != 'privilege'
            or not isinstance(path, list) or not path):
        raise _refused('Native target binding is invalid')
    guid = connection.info.get_info(native.DbInfoCode.DB_GUID)
    file_id = connection.info.get_info(native.DbInfoCode.DB_FILE_ID)
    if not isinstance(guid, str) or not guid or not isinstance(file_id, str) or not file_id:
        raise _refused('Native database GUID/file identity is unavailable')
    cursor = connection.cursor()
    try:
        if kind in SEC_CATALOGS:
            record = _observe_sec(cursor, selected)
            return {
                'schema': 'scratchrobin.firebird.native-target@1',
                **selected, 'database_guid': guid, 'database_file_id': file_id,
                'record': record, 'parent': None,
            }
        if kind == 'privilege':
            record = _observe_privilege(cursor, selected)
            return {
                'schema': 'scratchrobin.firebird.native-target@1',
                **selected, 'database_guid': guid, 'database_file_id': file_id,
                'record': record, 'parent': None,
            }
        table, name_field = CATALOGS[kind]
        predicates, values = (
            (['X.' + name_field + ' = ?'], [path[-1]]) if name_field else (['1 = 1'], [])
        )
        if kind == 'shadow':
            from .shadows import numeric, MAX_NUMBER
            values = [int(numeric(path[-1], 'Shadow number', 1, MAX_NUMBER))]
        if kind == 'column':
            if len(path) != 2:
                raise _refused('A column requires its exact parent relation')
            predicates.append('X.RDB$RELATION_NAME = ?')
            values.append(path[0])
        if kind in {'constraint', 'index', 'trigger'} and len(path) == 2:
            predicates.append('X.RDB$RELATION_NAME = ?')
            values.append(path[0])
        if kind in {'procedure', 'function'}:
            if len(path) == 2:
                predicates.append('X.RDB$PACKAGE_NAME = ?')
                values.append(path[0])
            elif len(path) == 1:
                predicates.append('X.RDB$PACKAGE_NAME IS NULL')
            else:
                raise _refused('Native routine package identity is invalid')
        record = _record(cursor, table, predicates, values, multiple=kind == 'shadow')
        parent = None
        if kind in {'column', 'constraint', 'index', 'trigger'} and len(path) == 2:
            parent = _record(cursor, 'RDB$RELATIONS', ['X.RDB$RELATION_NAME = ?'], [path[0]])
        elif kind in {'procedure', 'function'} and len(path) == 2:
            parent = _record(cursor, 'RDB$PACKAGES', ['X.RDB$PACKAGE_NAME = ?'], [path[0]])
        return {
            'schema': 'scratchrobin.firebird.native-target@1',
            **selected, 'database_guid': guid, 'database_file_id': file_id,
            'record': record, 'parent': parent,
        }
    finally:
        cursor.close()


def verify(connection, expected):
    import firebird.driver as native
    try:
        # The query starts only an idle original transaction. It never ends
        # an existing transaction or changes its isolation.
        selector = {
            key: expected[key]
            for key in ('resource_kind', 'path', 'plugin', 'privilege_key')
            if key in expected
        }
        if not selector.get('resource_kind') or not selector.get('path'):
            raise KeyError('selector')
        actual = observe(connection, selector)
        if connection.main_transaction.info.isolation != native.Isolation.SNAPSHOT:
            raise _refused(
                'Reviewed metadata changes require a native SNAPSHOT transaction; '
                'use an independently reviewed operation'
            )
        if actual != expected:
            raise _refused('Native object changed since review; refresh and review again')
    except (KeyError, TypeError):
        raise _refused('Native target binding is incomplete; refresh and review again') from None
