"""YugabyteDB YSQL extensions.

Checked live on 2025.2.2.2 (66 available on the demo, among them vector,
pg_cron, pg_partman, documentdb, orafce and hll): CREATE EXTENSION name
[WITH SCHEMA s] [VERSION v] [CASCADE]; ALTER EXTENSION UPDATE [TO v], SET
SCHEMA (relocatable extensions only), COMMENT ON EXTENSION; DROP
EXTENSION. Versions are YugabyteDB's own spellings (1.8-yb-1.0), so the
record lists the versions the engine has update paths to.

Field ids match the provider's earlier form (name, schema, version,
cascade).
"""
import re

from ...sdk.relational import RelationalClientError

CREATE_KEYS = {'name', 'schema', 'version', 'cascade', 'comment'}
ALTER_KEYS = {'version', 'schema', 'comment', 'confirmation'}
_VERSION = re.compile(r'[A-Za-z0-9_.+-]{1,64}')


def _blank(value):
    return value is None or value == ''


def _version(admin, value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise RelationalClientError('version is an extension version name')
    return admin._literal(value)


def _comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON EXTENSION {name} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown extension option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    clauses = []
    if not _blank(draft.get('schema')):
        clauses.append('SCHEMA ' + admin._quote(
            admin._identifier(draft['schema'])))
    if not _blank(draft.get('version')):
        clauses.append('VERSION ' + _version(admin, draft['version']))
    if draft.get('cascade'):
        clauses.append('CASCADE')
    source = f'CREATE EXTENSION {name}'
    if clauses:
        source += ' WITH ' + ' '.join(clauses)
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, name, draft['comment']))
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    native = (target or {}).get('native') or {}
    name = admin._quote((target or {}).get('display_name'))
    statements = []
    if not _blank(draft.get('version')) and \
            draft['version'] != native.get('version'):
        targets = native.get('update_versions')
        if isinstance(targets, list) and draft['version'] not in targets:
            available = ', '.join(targets) or 'none'
            raise RelationalClientError(
                f'{native.get("version")} has no update path to '
                f'{draft["version"]}; available: {available}')
        statements.append({'source': (
            f'ALTER EXTENSION {name} UPDATE TO '
            f'{_version(admin, draft["version"])}'), 'parameters': ()})
    if not _blank(draft.get('schema')) and \
            draft['schema'] != native.get('schema'):
        if native.get('relocatable') is False:
            raise RelationalClientError(
                'this extension is not relocatable; it stays in '
                f'{native.get("schema")}')
        statements.append({'source': (
            f'ALTER EXTENSION {name} SET SCHEMA '
            f'{admin._quote(admin._identifier(draft["schema"]))}'),
            'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(field, operation):
    fields = [field('name', 'Extension name', 'text', True),
              field('schema', 'Install schema', 'text'),
              field('version', 'Version', 'text'),
              field('comment', 'Comment', 'text')]
    if operation == 'create':
        fields.append(field('cascade', 'Install dependencies', 'boolean',
                            default=False))
    else:
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.extension.{operation}',
            'title': ('Install YSQL extension' if operation == 'create'
                      else 'Alter YSQL extension'),
            'fields': fields}
