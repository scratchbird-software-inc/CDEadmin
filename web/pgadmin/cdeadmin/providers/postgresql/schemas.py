"""PostgreSQL schema lifecycle on the provider tree (M4, 2026-11-11).

CREATE SCHEMA name [AUTHORIZATION owner]; COMMENT ON SCHEMA; GRANT /
REVOKE ON SCHEMA (USAGE, CREATE); ALTER DEFAULT PRIVILEGES IN SCHEMA for
tables, sequences, functions and types; SECURITY LABEL; ALTER SCHEMA
RENAME TO / OWNER TO; DROP SCHEMA [CASCADE]. Field ids follow the
inherited schema dialog (``schema.ui.js``: name, namespaceowner,
description, nspacl, seclabels); default privileges are one grid keyed by
object type instead of the dialog's four tabs.
"""
from collections.abc import Mapping

from .native_admin import (
    PostgreSQLNativeAdminError, privilege_words,
    _flag, _identifier, _literal, _name,
)

PRIVILEGE_CODES = {'U': 'USAGE', 'C': 'CREATE'}
DEFAULT_PRIVILEGES = {
    'TABLES': ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
               'REFERENCES', 'TRIGGER', 'MAINTAIN'),
    'SEQUENCES': ('USAGE', 'SELECT', 'UPDATE'),
    'FUNCTIONS': ('EXECUTE',),
    'TYPES': ('USAGE',),
}


def _blank(value):
    return value is None or value == ''


def facts(native):
    """The target's current values as the dialog shows them. The owner is
    an OID in the capture, so it is left for the dialog to set."""
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('nspname'),
            'description': native.get('comment'),
            'nspacl': list(row.get('nspacl') or [])}


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _row(value, label):
    if not isinstance(value, Mapping):
        raise PostgreSQLNativeAdminError(f'{label} rows must be objects')
    return value


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return [_row(item, label) for item in value]


def _grant(name, row):
    words = privilege_words(row.get('privileges'), PRIVILEGE_CODES,
                            'schema')
    privileges = 'ALL' if len(words) == len(PRIVILEGE_CODES) else ', '.join(
        words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'GRANT {privileges} ON SCHEMA {name} TO '
            f'{_grantee(row.get("grantee"))}{option}')


def _revoke(name, row):
    return f'REVOKE ALL ON SCHEMA {name} FROM {_grantee(row.get("grantee"))}'


def _object_type(row):
    value = str(row.get('object_type') or '').upper()
    if value not in DEFAULT_PRIVILEGES:
        raise PostgreSQLNativeAdminError(
            'default privileges apply to ' + ', '.join(DEFAULT_PRIVILEGES))
    return value


def _default_grant(name, row):
    object_type = _object_type(row)
    allowed = DEFAULT_PRIVILEGES[object_type]
    value = row.get('privileges')
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',') if part.strip()]
    if not isinstance(value, list) or not value:
        raise PostgreSQLNativeAdminError(
            f'default privileges on {object_type} are among ALL, '
            + ', '.join(allowed))
    words = [str(item).upper() for item in value]
    if words == ['ALL']:
        privileges = 'ALL'
    elif any(word not in allowed for word in words):
        raise PostgreSQLNativeAdminError(
            f'default privileges on {object_type} are among ALL, '
            + ', '.join(allowed))
    else:
        privileges = ', '.join(word for word in allowed if word in words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'ALTER DEFAULT PRIVILEGES IN SCHEMA {name} GRANT {privileges} '
            f'ON {object_type} TO {_grantee(row.get("grantee"))}{option}')


def _default_revoke(name, row):
    return (f'ALTER DEFAULT PRIVILEGES IN SCHEMA {name} REVOKE ALL ON '
            f'{_object_type(row)} FROM {_grantee(row.get("grantee"))}')


def _security_label(name, row):
    provider = _identifier(row.get('provider'), 'security label provider')
    label = row.get('label')
    text = 'NULL' if _blank(label) else _literal(str(label), 'security label')
    return f'SECURITY LABEL FOR {provider} ON SCHEMA {name} IS {text}'


def _comment(name, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON SCHEMA {name} IS {text}'


def _tail(name, draft):
    """Grants, default privileges and labels, shared by create and alter."""
    statements = []
    for row in _rows(draft, 'seclabels', 'security labels'):
        statements.append(_security_label(name, row))
    for row in _rows(draft, 'revoke', 'revoked grantees'):
        statements.append(_revoke(name, row))
    for row in _rows(draft, 'nspacl', 'privileges'):
        statements.append(_grant(name, row))
    for row in _rows(draft, 'default_revoke', 'revoked default privileges'):
        statements.append(_default_revoke(name, row))
    for row in _rows(draft, 'default_privileges', 'default privileges'):
        statements.append(_default_grant(name, row))
    return statements


def _create(draft):
    name = _identifier(draft.get('name'), 'name')
    statement = f'CREATE SCHEMA {name}'
    if not _blank(draft.get('namespaceowner')):
        statement += ' AUTHORIZATION ' + _identifier(
            draft['namespaceowner'], 'owner')
    statements = [statement]
    if not _blank(draft.get('description')):
        statements.append(_comment(name, draft['description']))
    return statements + _tail(name, draft)


def _alter(native, draft):
    current = facts(native)
    name = _identifier(current['name'], 'name')
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != current['name']:
        statements.append(f'ALTER SCHEMA {name} RENAME TO '
                          + _identifier(new_name, 'name'))
        name = _identifier(new_name, 'name')
    if not _blank(draft.get('namespaceowner')):
        statements.append(f'ALTER SCHEMA {name} OWNER TO '
                          + _identifier(draft['namespaceowner'], 'owner'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment(name, draft['description']))
    statements += _tail(name, draft)
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(native, draft):
    name = _name(facts(native)['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP SCHEMA {_identifier(name, "name")}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the schema lifecycle."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'schema inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(operation, field):
    """Dialog fields; ids follow the inherited schema dialog."""
    def grid(name, label, columns, **kw):
        return field(name, label, 'grid', columns=columns, **kw)
    grantee = {'field_id': 'grantee', 'label': 'Grantee', 'control': 'text',
               'required': True}
    with_grant = {'field_id': 'with_grant', 'label': 'With grant option',
                  'control': 'boolean', 'required': False}
    object_type = {'field_id': 'object_type', 'label': 'Object type',
                   'control': 'select', 'required': True, 'options': [
                       {'value': key, 'label': key.title()}
                       for key in DEFAULT_PRIVILEGES]}
    if operation == 'drop':
        fields = [field('cascade', 'Drop everything in the schema (CASCADE)',
                        'boolean'),
                  field('confirmation', 'Type the schema name to confirm',
                        required=True)]
    else:
        alter = operation == 'alter'
        initial = (lambda key: {'initial_value_path': ['schema_facts', key]}) \
            if alter else (lambda key: {})
        fields = [
            field('name', 'Name', required=not alter, **initial('name')),
            field('namespaceowner', 'Owner', help=(
                'AUTHORIZATION on create, OWNER TO on alter; empty keeps '
                'the current owner.')),
            field('description', 'Comment', 'multiline',
                  **initial('description')),
            grid('nspacl', 'Grant privileges', [
                grantee, {'field_id': 'privileges',
                          'label': 'Privileges (U usage, C create)',
                          'control': 'text', 'required': True}, with_grant],
                 help='Rows run GRANT; existing grants stay.'),
            grid('default_privileges', 'Default privileges for new objects', [
                object_type, grantee,
                {'field_id': 'privileges',
                 'label': 'Privileges (keywords, or ALL)',
                 'control': 'text', 'required': True}, with_grant],
                 help='ALTER DEFAULT PRIVILEGES IN SCHEMA ... GRANT'),
            grid('seclabels', 'Security labels', [
                {'field_id': 'provider', 'label': 'Provider',
                 'control': 'text', 'required': True},
                {'field_id': 'label', 'label': 'Security label',
                 'control': 'text', 'required': False}],
                 help="Empty label unsets the provider's label.")]
        if alter:
            fields += [grid('revoke', 'Revoke all privileges from',
                            [grantee]),
                       grid('default_revoke',
                            'Revoke default privileges from',
                            [object_type, grantee])]
    return {'form_id': f'postgresql-schema-{operation}',
            'form_key': 'native:postgresql:database:schema',
            'title': f'{operation.title()} schema', 'fields': fields}
