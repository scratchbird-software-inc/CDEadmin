"""PostgreSQL extension lifecycle on the provider tree (M4, 2026-11-11).

CREATE EXTENSION name [SCHEMA s] [VERSION v] [CASCADE]; ALTER EXTENSION
UPDATE TO v and SET SCHEMA s (relocatable extensions only); COMMENT ON
EXTENSION; DROP EXTENSION [CASCADE]. Compiled from the dialog's draft and
the captured ``pg_extension`` row, as the inherited extension dialog and
templates do (``extension.ui.js``, ``extensions/sql``); field ids follow
that dialog.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
)

_VERSION = re.compile(r'[A-Za-z0-9_.+-]{1,64}')


def _blank(value):
    return value is None or value == ''


def _version(value):
    # Versions are identifiers to PostgreSQL (CREATE EXTENSION ... VERSION
    # "1.0"); the inherited template quotes them the same way.
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise PostgreSQLNativeAdminError(
            'version is an extension version name')
    return _identifier(value, 'version')


def facts(native):
    """The target's current values as the dialog shows them."""
    row = native.get('catalog_row') or {}
    return {
        'name': native.get('name') or row.get('extname'),
        'schema': native.get('schema'),
        'version': row.get('extversion'),
        'relocatable': bool(row.get('extrelocatable', False)),
        'comment': native.get('comment'),
    }


def _comment(name, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON EXTENSION {name} IS {text}'


def _create(draft):
    name = _identifier(draft.get('name'), 'name')
    clauses = []
    if not _blank(draft.get('schema')):
        clauses.append('SCHEMA ' + _identifier(draft['schema'], 'schema'))
    if not _blank(draft.get('version')):
        clauses.append('VERSION ' + _version(draft['version']))
    if _flag(draft, 'cascade'):
        clauses.append('CASCADE')
    statement = f'CREATE EXTENSION {name}'
    if clauses:
        statement += ' WITH ' + ' '.join(clauses)
    statements = [statement]
    if not _blank(draft.get('comment')):
        statements.append(_comment(name, draft['comment']))
    return statements


def _alter(native, draft):
    current = facts(native)
    name = _identifier(current['name'], 'name')
    statements = []
    if not _blank(draft.get('version')) and \
            draft['version'] != current['version']:
        statements.append(
            f'ALTER EXTENSION {name} UPDATE TO {_version(draft["version"])}')
    if not _blank(draft.get('schema')) and \
            draft['schema'] != current['schema']:
        if not current['relocatable']:
            raise PostgreSQLNativeAdminError(
                'this extension is not relocatable; it stays in '
                f'{current["schema"]}')
        statements.append(f'ALTER EXTENSION {name} SET SCHEMA '
                          + _identifier(draft['schema'], 'schema'))
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        statements.append(_comment(name, draft['comment']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(native, draft):
    name = _name(facts(native)['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP EXTENSION {_identifier(name, "name")}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the extension lifecycle."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'extension inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(operation, field):
    """Dialog fields; ids follow the inherited extension dialog."""
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation',
                        'Type the extension name to confirm', required=True)]
    elif operation == 'create':
        fields = [field('name', 'Name', required=True, help=(
                      'An available extension (pg_available_extensions).')),
                  field('schema', 'Schema', help='WITH SCHEMA'),
                  field('version', 'Version', help='WITH VERSION'),
                  field('cascade', 'Install required extensions too (CASCADE)',
                        'boolean'),
                  field('comment', 'Comment')]
    else:
        fields = [field('schema', 'Schema', help=(
                      'SET SCHEMA; relocatable extensions only.'),
                        initial_value_path=['extension_facts', 'schema']),
                  field('version', 'Version', help='UPDATE TO',
                        initial_value_path=['extension_facts', 'version']),
                  field('comment', 'Comment',
                        initial_value_path=['extension_facts', 'comment'])]
    return {'form_id': f'postgresql-extension-{operation}',
            'form_key': 'native:postgresql:database:extension',
            'title': f'{operation.title()} extension', 'fields': fields}
