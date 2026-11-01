"""YugabyteDB YSQL foreign servers, user mappings and foreign tables.

Checked live on 2025.2.2.2 with postgres_fdw (2026-11-01): CREATE SERVER
... [TYPE] [VERSION] FOREIGN DATA WRAPPER w OPTIONS (...); ALTER SERVER
OPTIONS (ADD | SET | DROP), VERSION, RENAME TO, OWNER TO; COMMENT ON
SERVER; CREATE / ALTER / DROP USER MAPPING FOR role | PUBLIC SERVER s
OPTIONS (...); CREATE FOREIGN TABLE s.t (columns) SERVER srv OPTIONS
(...); ALTER FOREIGN TABLE ADD / DROP / RENAME COLUMN, OPTIONS, RENAME TO,
SET SCHEMA; COMMENT ON FOREIGN TABLE.

A user mapping's password is a secret: it is not taken as an option here
(the form records the gap), so it never travels as plain text. The
wrapper's own extension (CREATE EXTENSION postgres_fdw) is installed with the
extension editor first.
"""
import re

from ...sdk.relational import RelationalClientError
from .tables import column_definition

_OPTION = re.compile(r'[a-z_][a-z0-9_]{0,62}')
_SECRET_OPTIONS = {'password', 'passfile', 'sslpassword', 'sslkey'}
_IGNORED = {'variant', 'confirmation', 'cascade'}


def _blank(value):
    return value is None or value == '' or value == []


def _known(draft, keys, kind):
    unknown = set(draft) - keys - _IGNORED
    if unknown:
        raise RelationalClientError(
            f'unknown {kind} option: ' + ', '.join(sorted(unknown)))


def _comment(admin, target, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {target} IS {text}', 'parameters': ()}


def options(value):
    """{name: value} from grid rows; secrets are refused."""
    result = {}
    for item in value or []:
        if not isinstance(item, dict):
            raise RelationalClientError('options are name and value rows')
        name, text = item.get('name'), item.get('value')
        if not isinstance(name, str) or not _OPTION.fullmatch(name):
            raise RelationalClientError('an option name is lower case')
        if name in _SECRET_OPTIONS:
            raise RelationalClientError(
                f'{name} is a secret and is not taken as an option here')
        if name in result:
            raise RelationalClientError(f'option {name} repeats')
        result[name] = '' if text is None else str(text)
    return result


def stored_options(value):
    """{name: value} from a catalog options array (name=value)."""
    result = {}
    for entry in value or []:
        name, _, text = str(entry).partition('=')
        result[name] = text
    return result


def _option_list(admin, values):
    return ', '.join(f'{name} {admin._literal(text)}'
                     for name, text in values.items())


def _option_changes(admin, wanted, held):
    changes = [f'DROP {name}' for name in held if name not in wanted]
    for name, text in wanted.items():
        if name not in held:
            changes.append(f'ADD {name} {admin._literal(text)}')
        elif held[name] != text:
            changes.append(f'SET {name} {admin._literal(text)}')
    return ', '.join(changes)


# Foreign servers ------------------------------------------------------------

SERVER_KEYS = {'name', 'wrapper', 'server_type', 'version', 'options',
               'owner', 'comment'}


def create_server(admin, draft):
    _known(draft, SERVER_KEYS, 'foreign server')
    name = admin._quote(admin._identifier(draft.get('name')))
    source = f'CREATE SERVER {name}'
    if not _blank(draft.get('server_type')):
        source += ' TYPE ' + admin._literal(str(draft['server_type']))
    if not _blank(draft.get('version')):
        source += ' VERSION ' + admin._literal(str(draft['version']))
    source += (' FOREIGN DATA WRAPPER ' +
               admin._quote(admin._identifier(draft.get('wrapper'))))
    values = options(draft.get('options'))
    if values:
        source += f' OPTIONS ({_option_list(admin, values)})'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, f'SERVER {name}', draft['comment']))
    return statements


def alter_server(admin, draft, target):
    _known(draft, SERVER_KEYS, 'foreign server')
    native = (target or {}).get('native') or {}
    current = (target or {}).get('display_name')
    name = admin._quote(current)
    for key in ('wrapper', 'server_type'):
        if not _blank(draft.get(key)) and draft[key] != native.get(key):
            raise RelationalClientError(
                f'a foreign server cannot change its {key.replace("_", " ")}')
    statements = []
    if 'options' in draft:
        changes = _option_changes(admin, options(draft['options']),
                                  native.get('option_values') or {})
        if changes:
            statements.append({'source': (
                f'ALTER SERVER {name} OPTIONS ({changes})'),
                'parameters': ()})
    if not _blank(draft.get('version')) and draft['version'] != native.get(
            'version'):
        statements.append({'source': (
            f'ALTER SERVER {name} VERSION '
            f'{admin._literal(str(draft["version"]))}'), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, f'SERVER {name}', draft['comment']))
    if not _blank(draft.get('owner')) and draft['owner'] != native.get(
            'owner'):
        statements.append({'source': (
            f'ALTER SERVER {name} OWNER TO '
            f'{admin._quote(admin._identifier(draft["owner"]))}'),
            'parameters': ()})
    if not _blank(draft.get('name')) and draft['name'] != current:
        statements.append({'source': (
            f'ALTER SERVER {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop_server(admin, draft, target):
    name = admin._quote((target or {}).get('display_name'))
    return [{'source': f'DROP SERVER {name}' + (
        ' CASCADE' if (draft or {}).get('cascade') else ''),
        'parameters': ()}]


# User mappings --------------------------------------------------------------

MAPPING_KEYS = {'user', 'server', 'options'}


def _mapping_user(admin, value):
    if isinstance(value, str) and value.upper() == 'PUBLIC':
        return 'PUBLIC'
    return admin._quote(admin._identifier(value))


def create_mapping(admin, draft):
    _known(draft, MAPPING_KEYS, 'user mapping')
    user = _mapping_user(admin, draft.get('user'))
    server = admin._quote(admin._identifier(draft.get('server')))
    source = f'CREATE USER MAPPING FOR {user} SERVER {server}'
    values = options(draft.get('options'))
    if values:
        source += f' OPTIONS ({_option_list(admin, values)})'
    return [{'source': source, 'parameters': ()}]


def _mapping_target(admin, target):
    path = (target or {}).get('display_path') or []
    if len(path) != 2:
        raise RelationalClientError('the user mapping target is invalid')
    return (f'FOR {_mapping_user(admin, path[1])} SERVER '
            f'{admin._quote(path[0])}')


def alter_mapping(admin, draft, target):
    _known(draft, MAPPING_KEYS, 'user mapping')
    native = (target or {}).get('native') or {}
    path = (target or {}).get('display_path') or []
    for key, index in (('server', 0), ('user', 1)):
        if not _blank(draft.get(key)) and len(path) == 2 and (
                str(draft[key]).lower() != str(path[index]).lower()):
            raise RelationalClientError(
                f'a user mapping cannot change its {key}; create another')
    changes = _option_changes(admin, options(draft.get('options')),
                              native.get('option_values') or {})
    if not changes:
        raise RelationalClientError('nothing to change')
    return [{'source': (f'ALTER USER MAPPING {_mapping_target(admin, target)}'
                        f' OPTIONS ({changes})'), 'parameters': ()}]


def drop_mapping(admin, _draft, target):
    return [{'source': f'DROP USER MAPPING {_mapping_target(admin, target)}',
             'parameters': ()}]


# Foreign tables -------------------------------------------------------------

TABLE_KEYS = {'name', 'parent', 'columns', 'server', 'options', 'comment',
              'add_columns', 'drop_columns', 'rename_columns'}
_NOT_FOREIGN = ('primary_key', 'unique', 'identity')


def _column(admin, item):
    if not isinstance(item, dict):
        raise RelationalClientError('a column is a grid row')
    if any(item.get(key) for key in _NOT_FOREIGN):
        raise RelationalClientError(
            'a foreign table column has no primary key, unique or identity')
    return column_definition(admin, {key: value for key, value in
                                     item.items() if key not in _NOT_FOREIGN})


def create_table(admin, draft):
    _known(draft, TABLE_KEYS - {'add_columns', 'drop_columns',
                                'rename_columns'}, 'foreign table')
    name = admin._quote(admin._identifier(draft.get('name')))
    if not _blank(draft.get('parent')):
        name = admin._quote(admin._identifier(draft['parent'])) + '.' + name
    columns = [_column(admin, item) for item in draft.get('columns') or []]
    source = (f'CREATE FOREIGN TABLE {name} ({", ".join(columns)}) SERVER '
              f'{admin._quote(admin._identifier(draft.get("server")))}')
    values = options(draft.get('options'))
    if values:
        source += f' OPTIONS ({_option_list(admin, values)})'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, f'FOREIGN TABLE {name}',
                                   draft['comment']))
    return statements


def alter_table(admin, draft, target):
    _known(draft, TABLE_KEYS, 'foreign table')
    native = (target or {}).get('native') or {}
    path = (target or {}).get('display_path') or []
    if len(path) != 2:
        raise RelationalClientError('the foreign table target is invalid')
    table = f'{admin._quote(path[0])}.{admin._quote(path[1])}'
    if not _blank(draft.get('server')) and draft['server'] != native.get(
            'server'):
        raise RelationalClientError(
            'a foreign table cannot move to another server; create another')
    prefix = f'ALTER FOREIGN TABLE {table}'
    statements = [{'source': f'{prefix} DROP COLUMN {admin._quote(name)}',
                   'parameters': ()}
                  for name in draft.get('drop_columns') or []]
    statements += [{'source': (
        f'{prefix} RENAME COLUMN {admin._quote(item["from"])} TO '
        f'{admin._quote(item["to"])}'), 'parameters': ()}
        for item in draft.get('rename_columns') or []]
    statements += [{'source': f'{prefix} ADD COLUMN {_column(admin, item)}',
                    'parameters': ()}
                   for item in draft.get('add_columns') or []]
    if 'options' in draft:
        changes = _option_changes(admin, options(draft['options']),
                                  native.get('option_values') or {})
        if changes:
            statements.append({'source': f'{prefix} OPTIONS ({changes})',
                               'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, f'FOREIGN TABLE {table}',
                                   draft['comment']))
    if not _blank(draft.get('name')) and draft['name'] != path[1]:
        statements.append({'source': (
            f'{prefix} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
        table = f'{admin._quote(path[0])}.{admin._quote(draft["name"])}'
    if not _blank(draft.get('parent')) and draft['parent'] != path[0]:
        statements.append({'source': (
            f'ALTER FOREIGN TABLE {table} SET SCHEMA '
            f'{admin._quote(admin._identifier(draft["parent"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


BUILDERS = {
    'foreign-server': {'create': lambda admin, draft, _t: create_server(
        admin, draft), 'alter': alter_server, 'drop': drop_server},
    'user-mapping': {'create': lambda admin, draft, _t: create_mapping(
        admin, draft), 'alter': alter_mapping, 'drop': drop_mapping},
    'foreign-table': {'create': lambda admin, draft, _t: create_table(
        admin, draft), 'alter': alter_table},
}


def compile_request(admin, kind, operation, draft, target):
    return BUILDERS[kind][operation](admin, draft, target)


def _grid(values):
    return [{'name': name, 'value': text} for name, text in values.items()]


def resources(cursor, generation, resource, optional_rows, excluded):
    values = []
    for name, wrapper, server_type, version, stored, owner, comment in \
            optional_rows(
                cursor,
                'SELECT s.srvname, w.fdwname, s.srvtype, s.srvversion, '
                "s.srvoptions, r.rolname, obj_description(s.oid, "
                "'pg_foreign_server') FROM pg_catalog.pg_foreign_server s "
                'JOIN pg_catalog.pg_foreign_data_wrapper w '
                'ON w.oid = s.srvfdw '
                'JOIN pg_catalog.pg_roles r ON r.oid = s.srvowner '
                'ORDER BY 1'):
        held = stored_options(stored)
        values.append(resource('foreign-server', [], name, generation, {
            'wrapper': str(wrapper),
            'server_type': None if server_type is None else str(server_type),
            'version': None if version is None else str(version),
            'option_values': held, 'options': _grid(held),
            'owner': str(owner),
            'comment': None if comment is None else str(comment),
        }))
    for server, user, stored in optional_rows(
        cursor,
        'SELECT srvname, usename, umoptions FROM pg_catalog.pg_user_mappings '
        'ORDER BY 1, 2',
    ):
        held = stored_options(stored)
        values.append(resource('user-mapping', [server], user, generation, {
            'server': str(server), 'user': str(user),
            'option_values': held, 'options': _grid(held),
        }))
    for schema, name, server, stored, comment in optional_rows(
        cursor,
        'SELECT n.nspname, c.relname, s.srvname, t.ftoptions, '
        "obj_description(c.oid, 'pg_class') "
        'FROM pg_catalog.pg_foreign_table t '
        'JOIN pg_catalog.pg_class c ON c.oid = t.ftrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
        'JOIN pg_catalog.pg_foreign_server s ON s.oid = t.ftserver '
        f'WHERE n.nspname NOT IN {excluded} ORDER BY 1, 2',
    ):
        held = stored_options(stored)
        values.append(resource('foreign-table', [schema], name, generation, {
            'server': str(server), 'option_values': held,
            'options': _grid(held), 'table_type': 'FOREIGN',
            'comment': None if comment is None else str(comment),
        }))
    return values


def form(field, kind, operation):
    fields = {
        'foreign-server': lambda: [
            field('name', 'Name', 'text', True),
            field('wrapper', 'Foreign data wrapper', 'text', True),
            field('server_type', 'Type', 'text'),
            field('version', 'Version', 'text'),
            field('options', 'Options', 'json', False, default=[]),
            field('owner', 'Owner', 'text'),
            field('comment', 'Comment', 'text')],
        'user-mapping': lambda: [
            field('user', 'User', 'text', True),
            field('server', 'Server', 'text', True),
            field('options', 'Options', 'json', False, default=[])],
        'foreign-table': lambda: [
            field('name', 'Name', 'text', True),
            field('parent', 'Schema', 'text'),
            field('columns', 'Columns', 'json', True),
            field('server', 'Server', 'text', True),
            field('options', 'Options', 'json', False, default=[]),
            field('comment', 'Comment', 'text')],
    }[kind]()
    if operation == 'alter':
        for item in fields:
            item.pop('default', None)
            item['required'] = False
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.{kind}.{operation}',
            'title': f'{operation.title()} {kind.replace("-", " ")}',
            'fields': fields}
