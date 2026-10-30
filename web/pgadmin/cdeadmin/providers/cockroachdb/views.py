"""CockroachDB views and materialized views.

Checked live on 26.1.3: CREATE VIEW [(columns)] AS, CREATE OR REPLACE VIEW
(adding columns at the end; dropping one is refused by the engine), ALTER
VIEW / ALTER MATERIALIZED VIEW ... RENAME TO, CREATE MATERIALIZED VIEW ...
[WITH NO DATA], REFRESH. Refused: COMMENT ON VIEW or MATERIALIZED VIEW (and
COMMENT ON TABLE for either), CREATE OR REPLACE MATERIALIZED VIEW, and
temporary views unless the session opts in. A materialized view's query
cannot change in place.
"""
from ...sdk.relational import RelationalClientError

CREATE_KEYS = {'name', 'parent', 'query', 'column_names', 'with_data'}
ALTER_KEYS = {'name', 'query', 'column_names', 'confirmation'}


def _query(admin, draft):
    return admin._query_body(draft.get('query', draft.get('definition')))


def _columns(admin, draft):
    names = draft.get('column_names') or []
    return f' ({admin._identifier_list(names)})' if names else ''


def create(admin, kind, draft):
    unknown = set(draft) - CREATE_KEYS - {'definition'}
    if unknown:
        raise RelationalClientError(
            'unknown view option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    if kind == 'view':
        if 'with_data' in draft and draft['with_data'] is not None:
            raise RelationalClientError('only a materialized view has data')
        source = f'CREATE VIEW {name}{_columns(admin, draft)} AS ' + \
            _query(admin, draft)
    else:
        source = (f'CREATE MATERIALIZED VIEW {name}'
                  f'{_columns(admin, draft)} AS {_query(admin, draft)}')
        if draft.get('with_data') is False:
            source += ' WITH NO DATA'
    return [{'source': source, 'parameters': ()}]


def alter(admin, kind, draft, target):
    unknown = set(draft) - ALTER_KEYS - {'definition'}
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    path = admin._target_path(target)
    name = admin._qualified(path)
    native = (target or {}).get('native') or {}
    statements = []
    query = draft.get('query', draft.get('definition'))
    if query in (None, ''):
        query = native.get('query')
    names = draft.get('column_names', native.get('column_names'))
    if query != native.get('query') or names != native.get('column_names'):
        if kind != 'view':
            raise RelationalClientError(
                "a materialized view's query and columns cannot change in "
                'place; drop and create it')
        # The column list always goes with the replacement: CockroachDB
        # refuses one that would rename an existing column.
        statements.append({'source': (
            f'CREATE OR REPLACE VIEW {name}'
            f'{_columns(admin, {"column_names": names})} AS '
            f'{admin._query_body(query)}'), 'parameters': ()})
    if draft.get('name') not in (None, '', path[-1]):
        keyword = 'VIEW' if kind == 'view' else 'MATERIALIZED VIEW'
        statements.append({'source': (
            f'ALTER {keyword} {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(base, field, kind, operation):
    """The shared view forms; alter is name and (for a view) query."""
    if operation == 'create':
        if kind == 'materialized-view' and not any(
                item['field_id'] == 'with_data' for item in base['fields']):
            base['fields'].append(field(
                'with_data', 'Populate now', 'boolean', False,
                'Off: WITH NO DATA; REFRESH fills it later.', True))
        return base
    fields = [{**field('name', 'Name', 'text', True),
               'initial_value_path': ['name']}]
    if kind == 'view':
        fields.append({**field('query', 'View query', 'code', True,
                               'CREATE OR REPLACE VIEW: existing columns '
                               'keep their names; new ones go last.'),
                       'initial_value_path': ['query']})
    return {'form_id': f'cockroachdb.{kind}.alter',
            'title': f'Alter CockroachDB {kind.replace("-", " ")}',
            'fields': fields}
