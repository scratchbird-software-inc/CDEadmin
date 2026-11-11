"""PostgreSQL foreign data wrappers, foreign servers and user mappings on
the provider tree (M5, 2026-11-11).

CREATE FOREIGN DATA WRAPPER name [HANDLER f] [VALIDATOR f] [OPTIONS (...)],
ALTER FOREIGN DATA WRAPPER RENAME TO / OWNER TO / HANDLER | NO HANDLER /
VALIDATOR | NO VALIDATOR / OPTIONS (ADD | SET | DROP ...), COMMENT, DROP;
CREATE SERVER name [TYPE] [VERSION] FOREIGN DATA WRAPPER w [OPTIONS],
ALTER SERVER RENAME TO / OWNER TO / VERSION / OPTIONS, COMMENT, DROP (a
changed wrapper or type is refused: drop and create); CREATE | ALTER | DROP
USER MAPPING FOR role | PUBLIC | CURRENT_USER SERVER s [OPTIONS]. Field
ids follow the inherited dialogs.

The capture redacts wrapper, server and mapping options, so the dialogs
take option changes as explicit add, set and drop rows rather than a diff.
Options that carry a credential (password, passfile, sslpassword, sslkey)
are refused here and stay with the inherited dialog, so a plan never shows
a secret; the same rule as role passwords.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _reference,
)

_OPTION = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,62}')
SECRET_OPTIONS = frozenset({'password', 'passfile', 'sslpassword', 'sslkey',
                            'sslcert', 'gssencmode_password'})
_MAPPING_IDENTITY = re.compile(r'^(.+) on server (.+)$')


def _blank(value):
    return value is None or value == '' or value == []


def _comment(keyword, name, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON {keyword} {name} IS {text}'


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _option_name(value):
    if not isinstance(value, str) or not _OPTION.fullmatch(value):
        raise PostgreSQLNativeAdminError('an option needs a name')
    if value.lower() in SECRET_OPTIONS:
        raise PostgreSQLNativeAdminError(
            f'the {value} option carries a credential; set it from the '
            'inherited dialog so the plan never shows it')
    return _identifier(value, 'option')


def _option_pairs(rows, action=''):
    parts = []
    for row in rows:
        name = _option_name(row.get('name'))
        value = row.get('value')
        if not isinstance(value, str):
            raise PostgreSQLNativeAdminError(
                f'option {row.get("name")} needs a text value')
        parts.append(f'{action}{name} {_literal(value, "option value")}')
    return parts


def _option_changes(draft):
    """OPTIONS (ADD ..., SET ..., DROP ...) from the three grids."""
    parts = _option_pairs(_rows(draft, 'add_options', 'added options'),
                          'ADD ')
    parts += _option_pairs(_rows(draft, 'set_options', 'set options'),
                           'SET ')
    parts += ['DROP ' + _option_name(row.get('name'))
              for row in _rows(draft, 'drop_options', 'dropped options')]
    return ' OPTIONS (' + ', '.join(parts) + ')' if parts else ''


# -- facts --------------------------------------------------------------------

def wrapper_facts(native):
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('fdwname'),
            'description': native.get('comment')}


def server_facts(native, wrappers=None):
    row = native.get('catalog_row') or {}
    try:
        wrapper = int(row.get('srvfdw') or 0)
    except (TypeError, ValueError):
        wrapper = 0
    return {'name': native.get('name') or row.get('srvname'),
            'fdwname': (wrappers or {}).get(wrapper),
            'fsrvtype': row.get('srvtype'),
            'fsrvversion': row.get('srvversion'),
            'description': native.get('comment')}


def mapping_facts(native):
    identity = native.get('sql_identity') or ''
    match = _MAPPING_IDENTITY.match(identity)
    user, server = (match.group(1), match.group(2)) if match else (
        None, None)
    return {'name': user, 'server': server,
            'display_name': native.get('name') or identity}


# -- wrappers -----------------------------------------------------------------

def _wrapper_create(draft):
    name = _identifier(draft.get('name'), 'name')
    text = f'CREATE FOREIGN DATA WRAPPER {name}'
    if not _blank(draft.get('fdwhan')):
        text += ' HANDLER ' + _reference(draft['fdwhan'], 'handler')
    if not _blank(draft.get('fdwvalue')):
        text += ' VALIDATOR ' + _reference(draft['fdwvalue'], 'validator')
    options = _option_pairs(_rows(draft, 'fdwoptions', 'options'))
    if options:
        text += ' OPTIONS (' + ', '.join(options) + ')'
    statements = [text]
    if not _blank(draft.get('fdwowner')):
        statements.append(f'ALTER FOREIGN DATA WRAPPER {name} OWNER TO '
                          + _identifier(draft['fdwowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('FOREIGN DATA WRAPPER', name,
                                   draft['description']))
    return statements


def _wrapper_alter(native, draft):
    current = native.get('wrapper_facts') or wrapper_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER FOREIGN DATA WRAPPER {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    if not _blank(draft.get('fdwowner')):
        statements.append(f'ALTER FOREIGN DATA WRAPPER {quoted} OWNER TO '
                          + _identifier(draft['fdwowner'], 'owner'))
    clauses = []
    if _flag(draft, 'no_handler'):
        clauses.append('NO HANDLER')
    elif not _blank(draft.get('fdwhan')):
        clauses.append('HANDLER ' + _reference(draft['fdwhan'], 'handler'))
    if _flag(draft, 'no_validator'):
        clauses.append('NO VALIDATOR')
    elif not _blank(draft.get('fdwvalue')):
        clauses.append('VALIDATOR ' + _reference(draft['fdwvalue'],
                                                 'validator'))
    options = _option_changes(draft)
    if clauses or options:
        statements.append(f'ALTER FOREIGN DATA WRAPPER {quoted}'
                          + (' ' + ' '.join(clauses) if clauses else '')
                          + options)
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('FOREIGN DATA WRAPPER', quoted,
                                   draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _wrapper_drop(native, draft):
    current = native.get('wrapper_facts') or wrapper_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP FOREIGN DATA WRAPPER {_identifier(name, "name")}{cascade}']


# -- servers ------------------------------------------------------------------

def _server_create(draft):
    name = _identifier(draft.get('name'), 'name')
    text = f'CREATE SERVER {name}'
    if not _blank(draft.get('fsrvtype')):
        text += ' TYPE ' + _literal(str(draft['fsrvtype']), 'type')
    if not _blank(draft.get('fsrvversion')):
        text += ' VERSION ' + _literal(str(draft['fsrvversion']), 'version')
    text += ' FOREIGN DATA WRAPPER ' + _identifier(draft.get('fdwname'),
                                                   'foreign data wrapper')
    options = _option_pairs(_rows(draft, 'fsrvoptions', 'options'))
    if options:
        text += ' OPTIONS (' + ', '.join(options) + ')'
    statements = [text]
    if not _blank(draft.get('fsrvowner')):
        statements.append(f'ALTER SERVER {name} OWNER TO '
                          + _identifier(draft['fsrvowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('SERVER', name, draft['description']))
    return statements


def _server_alter(native, draft):
    current = native.get('server_facts') or server_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    for key in ('fdwname', 'fsrvtype'):
        if not _blank(draft.get(key)) and draft[key] != current.get(key):
            raise PostgreSQLNativeAdminError(
                'the wrapper and type are fixed once created; drop and '
                'create the server to change them')
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER SERVER {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    if not _blank(draft.get('fsrvowner')):
        statements.append(f'ALTER SERVER {quoted} OWNER TO '
                          + _identifier(draft['fsrvowner'], 'owner'))
    version = draft.get('fsrvversion')
    clauses = []
    if not _blank(version) and version != current.get('fsrvversion'):
        clauses.append('VERSION ' + _literal(str(version), 'version'))
    options = _option_changes(draft)
    if clauses or options:
        statements.append(f'ALTER SERVER {quoted}'
                          + (' ' + ' '.join(clauses) if clauses else '')
                          + options)
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('SERVER', quoted, draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _server_drop(native, draft):
    current = native.get('server_facts') or server_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP SERVER {_identifier(name, "name")}{cascade}']


# -- user mappings ------------------------------------------------------------

def _mapping_user(value):
    value = _name(value, 'user')
    if value.upper() in ('PUBLIC', 'CURRENT_USER', 'CURRENT_ROLE', 'USER'):
        return value.upper()
    return _identifier(value, 'user')


def _mapping_create(draft):
    text = (f'CREATE USER MAPPING FOR {_mapping_user(draft.get("name"))} '
            f'SERVER {_identifier(draft.get("server"), "server")}')
    options = _option_pairs(_rows(draft, 'umoptions', 'options'))
    if options:
        text += ' OPTIONS (' + ', '.join(options) + ')'
    return [text]


def _mapping_alter(native, draft):
    current = native.get('mapping_facts') or mapping_facts(native)
    options = _option_changes(draft)
    if not options:
        raise PostgreSQLNativeAdminError(
            'nothing to change; a user mapping changes through its options')
    return [f'ALTER USER MAPPING FOR {_mapping_user(current["name"])} SERVER '
            f'{_identifier(current["server"], "server")}{options}']


def _mapping_drop(native, draft):
    current = native.get('mapping_facts') or mapping_facts(native)
    display = current.get('display_name') or ''
    if _name(draft.get('confirmation'), 'confirmation') not in (
            display, current.get('name')):
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    return [f'DROP USER MAPPING FOR {_mapping_user(current["name"])} SERVER '
            f'{_identifier(current["server"], "server")}']


# -- dispatch -----------------------------------------------------------------

_COMPILERS = {
    'foreign-data-wrapper': (_wrapper_create, _wrapper_alter, _wrapper_drop),
    'foreign-server': (_server_create, _server_alter, _server_drop),
    'user-mapping': (_mapping_create, _mapping_alter, _mapping_drop),
}
FACTS = {'foreign-data-wrapper': ('wrapper_facts', wrapper_facts),
         'foreign-server': ('server_facts', server_facts),
         'user-mapping': ('mapping_facts', mapping_facts)}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a wrapper, server or mapping."""
    create, alter, drop = _COMPILERS[kind]
    if operation == 'create':
        statements = create(draft)
    elif operation == 'alter':
        statements = alter(native, draft)
    elif operation == 'drop':
        statements = drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            f'{kind} inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

_OPTION_COLUMNS = [{'field_id': 'name', 'label': 'Option', 'control': 'text',
                    'required': True},
                   {'field_id': 'value', 'label': 'Value', 'control': 'text',
                    'required': True}]
_DROP_COLUMNS = [{'field_id': 'name', 'label': 'Option', 'control': 'text',
                  'required': True}]
_SECRET_NOTE = ('Credential options (password, passfile, sslpassword, '
                'sslkey) stay with the inherited dialog.')


def _option_fields(field, alter):
    if alter:
        return [field('add_options', 'Add options', 'grid',
                      columns=_OPTION_COLUMNS, help=_SECRET_NOTE),
                field('set_options', 'Set options', 'grid',
                      columns=_OPTION_COLUMNS),
                field('drop_options', 'Drop options', 'grid',
                      columns=_DROP_COLUMNS)]
    return []


def form(kind, operation, field):
    """Dialog fields; ids follow the inherited dialogs."""
    facts_key = FACTS[kind][0]
    alter = operation == 'alter'
    label = {'foreign-data-wrapper': 'foreign data wrapper',
             'foreign-server': 'foreign server',
             'user-mapping': 'user mapping'}[kind]

    def initial(key):
        return {'initial_value_path': [facts_key, key]} if alter else {}
    if operation == 'drop':
        fields = [field('confirmation', f'Type the {label} name to confirm',
                        required=True)]
        if kind != 'user-mapping':
            fields.insert(0, field('cascade', 'Drop dependent objects',
                                   'boolean'))
    elif kind == 'foreign-data-wrapper':
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('fdwowner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO')),
                  field('fdwhan', 'Handler', help='schema.function'),
                  field('fdwvalue', 'Validator', help='schema.function')]
        if alter:
            fields += [field('no_handler', 'Remove the handler', 'boolean'),
                       field('no_validator', 'Remove the validator',
                             'boolean')]
        else:
            fields.append(field('fdwoptions', 'Options', 'grid',
                                columns=_OPTION_COLUMNS, help=_SECRET_NOTE))
        fields += _option_fields(field, alter)
        fields.append(field('description', 'Comment', 'multiline',
                            **initial('description')))
    elif kind == 'foreign-server':
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('fdwname', 'Foreign data wrapper', required=not alter,
                        **({'help': 'Fixed once created.'} if alter else {}),
                        **initial('fdwname')),
                  field('fsrvowner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO')),
                  field('fsrvtype', 'Type', **(
                      {'help': 'Fixed once created.'} if alter else {}),
                      **initial('fsrvtype')),
                  field('fsrvversion', 'Version', **initial('fsrvversion'))]
        if not alter:
            fields.append(field('fsrvoptions', 'Options', 'grid',
                                columns=_OPTION_COLUMNS, help=_SECRET_NOTE))
        fields += _option_fields(field, alter)
        fields.append(field('description', 'Comment', 'multiline',
                            **initial('description')))
    else:
        if alter:
            fields = _option_fields(field, True)
        else:
            fields = [field('name', 'User', required=True, help=(
                          'A role, PUBLIC or CURRENT_USER.')),
                      field('server', 'Foreign server', required=True),
                      field('umoptions', 'Options', 'grid',
                            columns=_OPTION_COLUMNS, help=_SECRET_NOTE)]
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:database:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields,
            'notes': _SECRET_NOTE + ' Privileges stay with the inherited '
                     'dialog.'}
