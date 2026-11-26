"""PostgreSQL object privileges: GRANT and REVOKE on existing objects (Decision 21).

Parameter privileges (``parameter_acl``) and privileges on objects created later
(``default_privileges``) have their own kinds; this module is the third and most
common case, the ACL of one existing object, or of every object of a family in a
schema. Every identifier is quoted and every privilege word comes from a fixed list
per object family, so a draft can never reach the statement as free text.

The effect is read back inside the same transaction: ``observation_statement`` reads
the object's ACL after the statement (a NULL ACL is shown as the object family's
default, since NULL means the owner holds everything, not that nobody holds anything).
"""
import re

from .native_admin import PostgreSQLNativeAdminError, _identifier, _literal, _name, _flag

COLUMN_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')

# object type -> (privileges, acldefault code, qualified by schema, columns allowed, minimum privilege versions)
OBJECTS = {
    'TABLE': (('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN'), 'r', True),
    'SEQUENCE': (('USAGE', 'SELECT', 'UPDATE'), 's', True),
    'DATABASE': (('CREATE', 'CONNECT', 'TEMPORARY'), 'd', False),
    'DOMAIN': (('USAGE',), 'T', True),
    'FOREIGN DATA WRAPPER': (('USAGE',), 'F', False),
    'FOREIGN SERVER': (('USAGE',), 'S', False),
    'FUNCTION': (('EXECUTE',), 'f', True),
    'PROCEDURE': (('EXECUTE',), 'f', True),
    'ROUTINE': (('EXECUTE',), 'f', True),
    'LANGUAGE': (('USAGE',), 'l', False),
    'LARGE OBJECT': (('SELECT', 'UPDATE'), 'L', False),
    'SCHEMA': (('USAGE', 'CREATE'), 'n', False),
    'TABLESPACE': (('CREATE',), 't', False),
    'TYPE': (('USAGE',), 'T', True),
}
# ALL ... IN SCHEMA: the family each covers, and the privilege list of that family.
BULK = {
    'ALL TABLES IN SCHEMA': 'TABLE', 'ALL SEQUENCES IN SCHEMA': 'SEQUENCE',
    'ALL FUNCTIONS IN SCHEMA': 'FUNCTION', 'ALL PROCEDURES IN SCHEMA': 'PROCEDURE',
    'ALL ROUTINES IN SCHEMA': 'ROUTINE',
}
OBJECT_TYPES = tuple(OBJECTS) + tuple(BULK)
ALL_PRIVILEGES = 'ALL'
OPERATIONS = ('grant', 'revoke')


def _grid(draft, key, field, limit=100):
    rows = draft.get(key)
    if not isinstance(rows, list) or not 1 <= len(rows) <= limit or any(
            not isinstance(row, dict) or set(row) - {field, 'columns', '_id'} for row in rows):
        raise PostgreSQLNativeAdminError(f'{key} must be a bounded typed grid')
    return rows


def _grantees(draft):
    rows = _grid(draft, 'grantees', 'role')
    names = [_name(row.get('role'), 'role') for row in rows]
    if len(set(names)) != len(names):
        raise PostgreSQLNativeAdminError('Grantees must be distinct')
    # PUBLIC is the keyword; a role literally named public must be quoted by the caller's choice
    # of spelling, so only the exact upper-case word selects the keyword.
    return ', '.join('PUBLIC' if name == 'PUBLIC' else _identifier(name, 'role') for name in names)


def _column_list(value):
    if value in (None, '', []):
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',')]
    if not isinstance(value, list) or not value or any(not isinstance(part, str) or not part for part in value):
        raise PostgreSQLNativeAdminError('Columns must be a list of column names')
    if len(set(value)) != len(value):
        raise PostgreSQLNativeAdminError('Columns must be distinct')
    return [_identifier(part, 'column') for part in value]


def _privileges(draft, allowed, columns_allowed):
    rows = _grid(draft, 'privileges', 'privilege')
    words, parts = [], []
    for row in rows:
        word = row.get('privilege')
        columns = _column_list(row.get('columns'))
        if not isinstance(word, str) or not (word == ALL_PRIVILEGES or word in allowed):
            raise PostgreSQLNativeAdminError('Privileges must match the object family, or be ALL alone')
        if columns and not (columns_allowed and (word == ALL_PRIVILEGES or word in COLUMN_PRIVILEGES)):
            raise PostgreSQLNativeAdminError('Only SELECT, INSERT, UPDATE and REFERENCES on a table take a column list')
        words.append(word)
        parts.append(('ALL PRIVILEGES' if word == ALL_PRIVILEGES else word) + (' (' + ', '.join(columns) + ')' if columns else ''))
    if len(set(words)) != len(words):
        raise PostgreSQLNativeAdminError('Privileges must be distinct')
    if ALL_PRIVILEGES in words and len(words) != 1:
        raise PostgreSQLNativeAdminError('ALL must be the only privilege')
    return words, parts


def _object_reference(object_type, draft):
    """The ON clause's object, fully quoted, and the catalog identity used to read the ACL back."""
    code = OBJECTS[object_type][1]
    qualified = OBJECTS[object_type][2]
    name = _name(draft.get('object'), 'object')
    if object_type == 'LARGE OBJECT':
        if not name.isdigit() or not 1 <= int(name) <= 2 ** 32 - 1:
            raise PostgreSQLNativeAdminError('A large object is identified by its numeric OID')
        return name, ("SELECT 'oid' AS catalog, m.oid::text AS identity, m.lomacl AS acl, "
                      f"pg_catalog.acldefault('{code}', m.lomowner) AS default_acl FROM pg_catalog.pg_largeobject_metadata m "
                      f'WHERE m.oid = {int(name)}')
    if qualified:
        schema = _name(draft.get('schema'), 'schema')
        reference = _identifier(schema, 'schema') + '.' + _identifier(name, 'object')
    else:
        reference = _identifier(name, 'object')
        schema = None
    if object_type in ('FUNCTION', 'PROCEDURE', 'ROUTINE'):
        arguments = _arguments(draft.get('arguments'))
        if arguments:
            reference += '(' + arguments + ')'
    return reference, _observe(object_type, code, schema, name, _arguments(draft.get('arguments')))


_ARGUMENT_TYPES = re.compile(r'[A-Za-z0-9_ ,."$\[\]]+')


def _arguments(value):
    """A plain list of argument types (identity arguments), or None. Only name characters,
    spaces, commas, dots, array brackets and balanced double quotes are accepted."""
    if value in (None, ''):
        return None
    if (not isinstance(value, str) or len(value) > 500 or _ARGUMENT_TYPES.fullmatch(value) is None
            or value.count('"') % 2):
        raise PostgreSQLNativeAdminError('Argument types must be a plain type list such as integer, text')
    return value


def _observe(object_type, code, schema, name, arguments):
    lit = lambda value, label: _literal(value, label)  # noqa: E731
    if object_type in ('TABLE', 'SEQUENCE'):
        return ("SELECT 'pg_class' AS catalog, c.oid::text AS identity, c.relacl AS acl, "
                f"pg_catalog.acldefault('{code}', c.relowner) AS default_acl, "
                "(SELECT COALESCE(jsonb_agg(jsonb_build_object('column', a.attname, 'acl', a.attacl::text) ORDER BY a.attnum), '[]'::jsonb) "
                "FROM pg_catalog.pg_attribute a WHERE a.attrelid = c.oid AND a.attacl IS NOT NULL AND NOT a.attisdropped) AS column_acls "
                "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = {lit(schema, 'schema')} AND c.relname = {lit(name, 'object')}")
    if object_type in ('DOMAIN', 'TYPE'):
        return ("SELECT 'pg_type' AS catalog, t.oid::text AS identity, t.typacl AS acl, "
                f"pg_catalog.acldefault('{code}', t.typowner) AS default_acl FROM pg_catalog.pg_type t "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
                f"WHERE n.nspname = {lit(schema, 'schema')} AND t.typname = {lit(name, 'object')}")
    if object_type in ('FUNCTION', 'PROCEDURE', 'ROUTINE'):
        where = f"n.nspname = {lit(schema, 'schema')} AND p.proname = {lit(name, 'object')}"
        if arguments not in (None, ''):
            signature = _quote_part(schema) + '.' + _quote_part(name) + '(' + arguments + ')'
            where = f"p.oid = {_literal(signature, 'function')}::pg_catalog.regprocedure"
        return ("SELECT 'pg_proc' AS catalog, p.oid::text AS identity, p.proacl AS acl, "
                f"pg_catalog.acldefault('{code}', p.proowner) AS default_acl FROM pg_catalog.pg_proc p "
                f"JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE {where}")
    simple = {
        'DATABASE': ('pg_database', 'datname', 'datacl', 'datdba'),
        'SCHEMA': ('pg_namespace', 'nspname', 'nspacl', 'nspowner'),
        'TABLESPACE': ('pg_tablespace', 'spcname', 'spcacl', 'spcowner'),
        'LANGUAGE': ('pg_language', 'lanname', 'lanacl', 'lanowner'),
        'FOREIGN DATA WRAPPER': ('pg_foreign_data_wrapper', 'fdwname', 'fdwacl', 'fdwowner'),
        'FOREIGN SERVER': ('pg_foreign_server', 'srvname', 'srvacl', 'srvowner'),
    }[object_type]
    table, name_column, acl_column, owner_column = simple
    return (f"SELECT '{table}' AS catalog, o.oid::text AS identity, o.{acl_column} AS acl, "
            f"pg_catalog.acldefault('{code}', o.{owner_column}) AS default_acl "
            f"FROM pg_catalog.{table} o WHERE o.{name_column} = {lit(name, 'object')}")


def _quote_part(name):
    return '"' + name.replace('"', '""') + '"'


def compile_operation(operation, native, draft):
    if operation == 'inspect':
        raise PostgreSQLNativeAdminError('Object privileges are read from each object, not inspected here')
    if operation not in OPERATIONS:
        raise PostgreSQLNativeAdminError('Select privilege grant or revoke')
    object_type = draft.get('object_type')
    if not isinstance(object_type, str) or object_type not in OBJECT_TYPES:
        raise PostgreSQLNativeAdminError('Select a native object family')
    bulk = BULK.get(object_type)
    family = bulk or object_type
    allowed = OBJECTS[family][0]
    words, parts = _privileges(draft, allowed, columns_allowed=(family == 'TABLE' and not bulk))
    who = _grantees(draft)
    if bulk:
        schemas = _grid(draft, 'schemas', 'schema', limit=100)
        names = [_name(row.get('schema'), 'schema') for row in schemas]
        if len(set(names)) != len(names):
            raise PostgreSQLNativeAdminError('Schemas must be distinct')
        target = ', '.join(_identifier(name, 'schema') for name in names)
        observation = None
    else:
        target, observation = _object_reference(object_type, draft)
    on = object_type + ' ' + target
    if operation == 'grant':
        if _flag(draft, 'grant_option_only') or _flag(draft, 'cascade'):
            raise PostgreSQLNativeAdminError('Grant-option-only and CASCADE belong to revoke')
        statement = 'GRANT ' + ', '.join(parts) + ' ON ' + on + ' TO ' + who + (' WITH GRANT OPTION' if _flag(draft, 'with_grant') else '')
    else:
        if _flag(draft, 'with_grant'):
            raise PostgreSQLNativeAdminError('WITH GRANT OPTION belongs to grant')
        statement = ('REVOKE ' + ('GRANT OPTION FOR ' if _flag(draft, 'grant_option_only') else '') + ', '.join(parts)
                     + ' ON ' + on + ' FROM ' + who + (' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'))
    result = {'statement': statement, 'read_only': False}
    if observation:
        result['observation_statement'] = observation
    if 'MAINTAIN' in words:
        result['minimum_server_version'] = 170000
    return result


def form(operation, field):
    privileges = sorted({word for words, _code, _q in OBJECTS.values() for word in words})
    fields = [
        field('object_type', 'Object', 'select', required=True, options=[{'value': v, 'label': v.title()} for v in OBJECT_TYPES]),
        field('schema', 'Schema'),
        field('object', 'Name', help='A large object is its numeric OID.'),
        field('arguments', 'Argument types', help='Functions and procedures only; empty when the name is unique.'),
        field('schemas', 'Schemas', 'grid', columns=[field('schema', 'Schema', required=True)]),
        field('privileges', 'Privileges', 'grid', required=True, columns=[
            field('privilege', 'Privilege', 'select', required=True,
                  options=[{'value': 'ALL', 'label': 'ALL'}] + [{'value': v, 'label': v} for v in privileges]),
            field('columns', 'Columns')]),
        field('grantees', 'Grantees', 'grid', required=True, columns=[field('role', 'Role or PUBLIC', required=True)]),
    ]
    if operation == 'grant':
        fields.append(field('with_grant', 'With grant option', 'boolean'))
    else:
        fields += [field('grant_option_only', 'Revoke grant option only', 'boolean'),
                   field('cascade', 'Cascade dependent grants', 'boolean')]
    return {'form_id': 'postgresql-privileges-' + operation, 'form_key': 'native:postgresql:database:privilege',
            'title': operation.title() + ' privileges', 'fields': fields}


# --- reading ACLs back for the listing ---------------------------------------------------------------

#: resource kind -> the raw catalog column holding its ACL
ACL_COLUMNS = {
    'table': 'relacl', 'partitioned-table': 'relacl', 'foreign-table': 'relacl', 'view': 'relacl',
    'materialized-view': 'relacl', 'sequence': 'relacl', 'function': 'proacl', 'procedure': 'proacl',
    'schema': 'nspacl', 'type': 'typacl', 'domain': 'typacl', 'database': 'datacl', 'language': 'lanacl',
    'foreign-data-wrapper': 'fdwacl', 'foreign-server': 'srvacl', 'tablespace': 'spcacl',
}
#: resource kind -> the object family its default ACL follows
DEFAULT_FAMILY = {
    'table': 'TABLE', 'partitioned-table': 'TABLE', 'foreign-table': 'TABLE', 'view': 'TABLE',
    'materialized-view': 'TABLE', 'sequence': 'SEQUENCE', 'function': 'FUNCTION', 'procedure': 'FUNCTION',
    'schema': 'SCHEMA', 'type': 'TYPE', 'domain': 'TYPE', 'database': 'DATABASE', 'language': 'LANGUAGE',
    'foreign-data-wrapper': 'FOREIGN DATA WRAPPER', 'foreign-server': 'FOREIGN SERVER', 'tablespace': 'TABLESPACE',
}
#: what PUBLIC holds on a new object of the family (PostgreSQL's built-in defaults)
PUBLIC_DEFAULTS = {
    'FUNCTION': ('EXECUTE',), 'TYPE': ('USAGE',), 'LANGUAGE': ('USAGE',), 'DATABASE': ('CONNECT', 'TEMPORARY'),
}
OWNER_KEYS = ('owner_name', 'owner', 'relowner', 'nspowner', 'typowner', 'datdba', 'funcowner', 'proowner')


def _owner_name(native, raw):
    for source in (raw, native):
        for key in OWNER_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value and not value.isdigit():
                return value
    return '(owner)'


def default_acl(kind, native, raw, version=0):
    """The rows of the family's default ACL for an object whose ACL is NULL: the owner holds every
    privilege with grant option, and PUBLIC what the family grants by default."""
    family = DEFAULT_FAMILY[kind]
    words = [word for word in OBJECTS[family][0] if word != 'MAINTAIN' or version >= 170000]
    owner = _owner_name(native, raw)
    rows = [{'grantee': owner, 'grantee_kind': 'role', 'grantor': owner, 'privilege': word,
             'grant_option': True, 'with_grant': True} for word in words]
    rows += [{'grantee': 'PUBLIC', 'grantee_kind': 'special', 'grantor': owner, 'privilege': word,
              'grant_option': False, 'with_grant': False} for word in PUBLIC_DEFAULTS.get(family, ())]
    return rows


def apply_default_acl(kind, native, raw, version=0):
    """Replace an empty privilege list by the default ACL when the object's ACL is NULL, and say so.
    ``[]`` from a NULL ACL would read as 'nobody holds anything', which is false."""
    column = ACL_COLUMNS.get(kind)
    if column is None or column not in raw or raw[column] is not None:
        native['privileges_default'] = False
        return
    native['privileges'] = default_acl(kind, native, raw, version)
    native['privileges_default'] = True
