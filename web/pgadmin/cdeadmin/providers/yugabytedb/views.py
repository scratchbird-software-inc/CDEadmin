"""YugabyteDB YSQL views and materialized views.

Checked live on 2025.2.2.2: CREATE [RECURSIVE] VIEW (columns) WITH
(security_barrier, security_invoker), CREATE OR REPLACE VIEW, ALTER VIEW
RENAME COLUMN / SET (options) / RENAME TO, COMMENT ON VIEW; CREATE
MATERIALIZED VIEW (columns) [TABLESPACE] AS ... [WITH NO DATA], ALTER
MATERIALIZED VIEW RENAME TO / SET TABLESPACE, COMMENT ON MATERIALIZED
VIEW, REFRESH [CONCURRENTLY] (concurrently needs a unique index, as in
PostgreSQL). Refused: WITH CHECK OPTION.

Field ids match the CockroachDB view form (name, parent, query,
column_names, with_data); YSQL adds options, recursion, tablespace and
comments.
"""
from ...sdk.relational import RelationalClientError

OPTIONS = ('security_barrier', 'security_invoker')
CREATE_KEYS = {'name', 'parent', 'query', 'definition', 'column_names',
               'with_data', 'recursive', 'tablespace', 'comment', *OPTIONS}
ALTER_KEYS = {'name', 'query', 'definition', 'column_names', 'tablespace',
              'comment', 'confirmation', *OPTIONS}


def _blank(value):
    return value is None or value == ''


def _keyword(kind):
    return 'VIEW' if kind == 'view' else 'MATERIALIZED VIEW'


def _comment(admin, kind, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {_keyword(kind)} {name} IS {text}',
            'parameters': ()}


def _names(admin, value):
    return admin._identifier_list(value) if value else ''


def _options(draft, native=None):
    chosen = []
    for key in OPTIONS:
        if key in draft and draft[key] is not None and (
                native is None or bool(draft[key]) != bool(
                    native.get(key, False))):
            chosen.append(f'{key} = {"true" if draft[key] else "false"}')
    return chosen


def create(admin, kind, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown view option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    query = admin._query_body(draft.get('query', draft.get('definition')))
    columns = _names(admin, draft.get('column_names'))
    if kind == 'view':
        if draft.get('with_data') is not None or not _blank(
                draft.get('tablespace')):
            raise RelationalClientError(
                'only a materialized view has data or a tablespace')
        recursive = bool(draft.get('recursive'))
        if recursive and not columns:
            raise RelationalClientError('a recursive view needs column names')
        source = (f'CREATE {"RECURSIVE " if recursive else ""}VIEW {name}'
                  f'{f" ({columns})" if columns else ""}')
        options = _options(draft)
        if options:
            source += ' WITH (' + ', '.join(options) + ')'
        source += f' AS {query}'
    else:
        if draft.get('recursive') or _options(draft):
            raise RelationalClientError(
                'a materialized view takes no recursion or view options')
        source = (f'CREATE MATERIALIZED VIEW {name}'
                  f'{f" ({columns})" if columns else ""}')
        if not _blank(draft.get('tablespace')):
            source += f' TABLESPACE {admin._quote(draft["tablespace"])}'
        source += f' AS {query}'
        if draft.get('with_data') is False:
            source += ' WITH NO DATA'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, kind, name, draft['comment']))
    return statements


def alter(admin, kind, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    statements = []
    held = list(native.get('column_names') or [])
    names = draft.get('column_names', held)
    query = draft.get('query', draft.get('definition'))
    if _blank(query):
        query = native.get('query')
    if kind != 'view':
        if query != native.get('query') or names != held:
            raise RelationalClientError(
                "a materialized view's query and columns cannot change in "
                'place; drop and create it')
    else:
        # Existing columns renamed in place first, by position.
        for old, new in zip(held, names):
            if old != new:
                statements.append({'source': (
                    f'ALTER VIEW {name} RENAME COLUMN {admin._quote(old)} '
                    f'TO {admin._quote(new)}'), 'parameters': ()})
        if query != native.get('query') or len(names) != len(held):
            columns = _names(admin, names)
            statements.append({'source': (
                f'CREATE OR REPLACE VIEW {name}'
                f'{f" ({columns})" if columns else ""} AS '
                f'{admin._query_body(query)}'), 'parameters': ()})
        options = _options(draft, native)
        if options:
            statements.append({'source': (
                f'ALTER VIEW {name} SET (' + ', '.join(options) + ')'),
                'parameters': ()})
    if kind != 'view' and 'tablespace' in draft and (
            draft['tablespace'] or None) != (native.get('tablespace') or None):
        statements.append({'source': (
            f'ALTER MATERIALIZED VIEW {name} SET TABLESPACE ' +
            admin._quote(draft['tablespace'] or 'pg_default')),
            'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, kind, name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER {_keyword(kind)} {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(base, field, kind, operation):
    if operation == 'create':
        base['fields'] += [field('comment', 'Comment', 'text')]
        if kind == 'view':
            base['fields'] += [
                field('recursive', 'Recursive', 'boolean', False,
                      default=False),
                field('security_barrier', 'Security barrier', 'boolean',
                      False, default=False),
                field('security_invoker', 'Security invoker', 'boolean',
                      False, default=False)]
        else:
            base['fields'] += [field('tablespace', 'Tablespace', 'text')]
            if not any(item['field_id'] == 'with_data'
                       for item in base['fields']):
                base['fields'].append(field('with_data', 'Populate now',
                                            'boolean', False, default=True))
        return base
    fields = [field('name', 'Name', 'text', True)]
    if kind == 'view':
        fields += [field('query', 'View query', 'code', True),
                   field('security_barrier', 'Security barrier', 'boolean'),
                   field('security_invoker', 'Security invoker', 'boolean')]
    else:
        fields.append(field('tablespace', 'Tablespace', 'text'))
    fields.append(field('comment', 'Comment', 'text'))
    for item in fields:
        item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.{kind}.alter',
            'title': f'Alter YSQL {kind.replace("-", " ")}',
            'fields': fields}
