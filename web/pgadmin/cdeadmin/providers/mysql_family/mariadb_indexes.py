"""MariaDB native secondary, FULLTEXT, SPATIAL and VECTOR index administration.

Supports MariaDB 12.2.2 native index creation and alteration:
- FULLTEXT indexes with optional WITH PARSER <parser>
- SPATIAL indexes (optional USING RTREE)
- VECTOR indexes (MHNSW with M=3..200 and DISTANCE=cosine|euclidean)
- Normal/UNIQUE indexes with column prefix lengths, ASC/DESC ordering,
  USING BTREE|HASH, IGNORED / NOT IGNORED visibility, KEY_BLOCK_SIZE, COMMENT,
  ALGORITHM (DEFAULT|INPLACE|COPY|NOCOPY|INSTANT) and LOCK
- Standalone RENAME INDEX, ALTER INDEX ... IGNORED|NOT IGNORED, and composite
  family-editor alter (visibility then rename).
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import re

from ...sdk import RelationalClientError
from .mariadb_catalog import identifier as quote_identifier
from .mariadb_server_diagnostics import environment
from .mysql_engine_diagnostics import observer_route, release
from .mysql_indexes import structural_definition, utf8_length

KEY = 'mariadb_index_change'
KINDS = ('NORMAL', 'FULLTEXT', 'SPATIAL', 'VECTOR')
METHODS = ('DEFAULT', 'BTREE', 'HASH', 'RTREE')
ALGORITHMS = ('DEFAULT', 'INPLACE', 'COPY', 'NOCOPY', 'INSTANT')
LOCKS = ('DEFAULT', 'NONE', 'SHARED', 'EXCLUSIVE')
DISTANCES = ('cosine', 'euclidean')
CREATE_KEYS = {
    'name', 'parent', 'table', 'columns', 'unique', 'index_kind', 'method',
    'key_block_size', 'comment', 'ignored', 'visible', 'parser',
    'vector_m', 'vector_distance', 'algorithm', 'lock',
}
INDEX_OPERATIONS = frozenset({'create', 'alter', 'rename', 'visibility'})


def identifier(value):
    try:
        if isinstance(value, str):
            value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native MariaDB identifier must be nonempty text without NUL') from None


def _table_path(value):
    value = value.split('.') if isinstance(value, str) else value
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 2:
        raise RelationalClientError('Select a MariaDB table identifier path')
    for part in value:
        identifier(part)
    return [str(part) for part in value]


def _resolve_ignored(draft):
    has_ignored = 'ignored' in draft
    has_visible = 'visible' in draft
    has_active = 'active' in draft
    for flag_key in ('ignored', 'visible', 'active'):
        if flag_key in draft and type(draft[flag_key]) is not bool:
            raise RelationalClientError(f'Index {flag_key} flag must be boolean')
    if has_visible and has_active and draft['visible'] != draft['active']:
        raise RelationalClientError('Conflicting MariaDB index visible and active flags')
    effective_visible = draft['visible'] if has_visible else (draft['active'] if has_active else None)
    if has_ignored and effective_visible is not None:
        if draft['ignored'] == effective_visible:
            raise RelationalClientError('Conflicting MariaDB index ignored and visible flags')
        return draft['ignored'], True
    if has_ignored:
        return draft['ignored'], True
    if effective_visible is not None:
        return (not effective_visible), True
    return False, False


def compile_create(draft):
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Select structured MariaDB index properties')
    draft = deepcopy(dict(draft))
    options = draft.pop('options', {})
    if not isinstance(options, Mapping) or set(options) - CREATE_KEYS:
        raise RelationalClientError('Unknown MariaDB index option')
    for key, value in options.items():
        if key in draft and draft[key] != value:
            raise RelationalClientError(f'Conflicting MariaDB index option: {key}')
        draft[key] = value
    if set(draft) - CREATE_KEYS:
        raise RelationalClientError('Unknown MariaDB index property')

    name = draft.get('name')
    if not isinstance(name, str) or name.strip().upper() == 'PRIMARY':
        raise RelationalClientError('Secondary index name is required and cannot be PRIMARY')
    quoted_name = identifier(name)

    table = _table_path(draft.get('table'))
    if draft.get('parent'):
        parent = _table_path(draft['parent'])
        if len(parent) != 1 or (len(table) == 2 and table[0] != parent[0]):
            raise RelationalClientError('Index database and owning table differ')
        if len(table) == 1:
            table = parent + table

    kind = draft.get('index_kind', 'NORMAL')
    unique = draft.get('unique', False)
    method = draft.get('method', 'DEFAULT')
    if kind not in KINDS or type(unique) is not bool or method not in METHODS:
        raise RelationalClientError('Select native MariaDB index kind, uniqueness and method')
    if unique and kind != 'NORMAL':
        raise RelationalClientError(f'{kind} indexes cannot be declared UNIQUE')
    if kind == 'NORMAL' and method == 'RTREE':
        raise RelationalClientError('RTREE index method belongs to SPATIAL indexes')
    if kind == 'SPATIAL' and method not in {'DEFAULT', 'RTREE'}:
        raise RelationalClientError('SPATIAL indexes only accept DEFAULT or RTREE index method')
    if kind in {'FULLTEXT', 'VECTOR'} and method != 'DEFAULT':
        raise RelationalClientError(f'{kind} indexes do not accept a USING index method')

    rows = draft.get('columns')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise RelationalClientError('Select 1 to 64 ordered MariaDB index key parts')
    if kind == 'VECTOR' and len(rows) != 1:
        raise RelationalClientError('MariaDB VECTOR indexes index exactly one VECTOR(N) column')

    parts = []
    for row in rows:
        if isinstance(row, str):
            row = {'name': row}
        elif isinstance(row, Mapping) and set(row) <= {'value', '_id'}:
            row = {'name': row.get('value')}
        if not isinstance(row, Mapping) or set(row) - {'name', 'prefix_length', 'direction', '_id'}:
            raise RelationalClientError('Unknown MariaDB index key-part property')
        col_name = row.get('name')
        if not isinstance(col_name, str) or not col_name:
            raise RelationalClientError('Each MariaDB index key part requires a column name')
        part = identifier(col_name)
        prefix = row.get('prefix_length')
        if prefix not in (None, ''):
            if kind in {'SPATIAL', 'VECTOR'}:
                raise RelationalClientError(f'{kind} indexes do not accept column prefix lengths')
            if type(prefix) is not int or not 1 <= prefix <= 65535:
                raise RelationalClientError('Column prefix length requires an integer from 1 to 65535')
            part += f'({prefix})'
        direction = row.get('direction', 'DEFAULT')
        if direction not in {'DEFAULT', 'ASC', 'DESC'}:
            raise RelationalClientError('Select DEFAULT, ASC or DESC key-part ordering')
        if direction != 'DEFAULT':
            if kind in {'FULLTEXT', 'SPATIAL', 'VECTOR'}:
                raise RelationalClientError(f'{kind} indexes do not accept explicit ASC/DESC key-part direction')
            part += f' {direction}'
        parts.append(part)

    prefix_kw = 'UNIQUE ' if unique else f'{kind} ' if kind != 'NORMAL' else ''
    source = f'CREATE {prefix_kw}INDEX {quoted_name}'
    if method != 'DEFAULT' and not (kind == 'SPATIAL' and method == 'RTREE'):
        source += f' USING {method}'
    source += ' ON ' + '.'.join(identifier(part) for part in table) + ' (' + ', '.join(parts) + ')'

    parameters = []
    parser_name = draft.get('parser')
    if parser_name not in (None, ''):
        if kind != 'FULLTEXT':
            raise RelationalClientError('WITH PARSER is supported only on FULLTEXT indexes')
        source += ' WITH PARSER ' + identifier(parser_name)

    vector_m = draft.get('vector_m')
    if vector_m not in (None, ''):
        if kind != 'VECTOR':
            raise RelationalClientError('M parameter is supported only on VECTOR indexes')
        if type(vector_m) is not int or not 3 <= vector_m <= 200:
            raise RelationalClientError('MariaDB VECTOR M parameter must be an integer between 3 and 200')
        source += f' M={vector_m}'

    vector_distance = draft.get('vector_distance')
    if vector_distance not in (None, ''):
        if kind != 'VECTOR':
            raise RelationalClientError('DISTANCE metric is supported only on VECTOR indexes')
        if not isinstance(vector_distance, str) or vector_distance.lower() not in DISTANCES:
            raise RelationalClientError('MariaDB VECTOR DISTANCE must be cosine or euclidean')
        source += f' DISTANCE={vector_distance.lower()}'

    block = draft.get('key_block_size')
    if block not in (None, ''):
        if kind == 'VECTOR':
            raise RelationalClientError('VECTOR indexes do not accept KEY_BLOCK_SIZE')
        if not isinstance(block, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', block) or int(block) > 2**64 - 1:
            raise RelationalClientError('KEY_BLOCK_SIZE requires unsigned decimal text')
        source += f' KEY_BLOCK_SIZE={block}'

    if draft.get('comment') not in (None, ''):
        comment = draft['comment']
        if not isinstance(comment, str) or '\x00' in comment or utf8_length(comment) > 65536:
            raise RelationalClientError('Index comment requires bounded UTF-8 text without NUL')
        source += ' COMMENT %s'
        parameters.append(comment)

    ignored, explicit_visibility = _resolve_ignored(draft)
    if explicit_visibility:
        source += ' IGNORED' if ignored else ' NOT IGNORED'

    for key, allowed_values in (('algorithm', ALGORITHMS), ('lock', LOCKS)):
        if key in draft and draft[key] not in (None, '', 'DEFAULT'):
            if draft[key] not in allowed_values:
                raise RelationalClientError(f'Select a supported MariaDB index {key.upper()} option')
            source += f' {key.upper()}={draft[key]}'
        elif key in draft and draft[key] not in allowed_values and draft[key] not in (None, ''):
            raise RelationalClientError(f'Select a supported MariaDB index {key.upper()} option')

    return {
        'statements': [{'source': source, 'parameters': tuple(parameters)}],
        KEY: {
            'operation': 'create',
            'draft': draft,
            'table': table,
            'index_name': name,
            'target_index_name': name,
        },
        'warnings': [
            'MariaDB index DDL performs an implicit commit and executes on an independently owned connection.',
            'Review binds server_uid and owning-table structure SHA-256; never automatically retried.',
        ],
    }


def compile_change(operation, draft, target):
    if operation not in {'rename', 'visibility', 'alter'} or not isinstance(draft, Mapping) or not isinstance(target, Mapping):
        raise RelationalClientError('Select a MariaDB index and change operation')
    path = target.get('display_path')
    if not isinstance(path, list) or len(path) != 3 or target.get('resource_kind') != 'index':
        raise RelationalClientError('Exact MariaDB database, table and index identity is required')
    if str(path[2]).upper() == 'PRIMARY':
        raise RelationalClientError('PRIMARY KEY cannot be renamed or marked IGNORED')

    draft = deepcopy(dict(draft))
    qualified_table = '.'.join(identifier(part) for part in path[:2])
    current_name = str(path[2])
    final_name = current_name
    statements = []

    if operation == 'rename':
        if set(draft) - {'new_name', 'confirmation'}:
            raise RelationalClientError('Unknown MariaDB index rename option')
        if 'confirmation' in draft and draft['confirmation'] != target.get('display_name'):
            raise RelationalClientError('Confirm the exact MariaDB index name')
        new_name = draft.get('new_name')
        if not isinstance(new_name, str) or not new_name or new_name.strip().upper() == 'PRIMARY' or new_name == current_name:
            raise RelationalClientError('Supply a distinct non-PRIMARY index name')
        statements.append({
            'source': f'ALTER TABLE {qualified_table} RENAME INDEX {identifier(current_name)} TO {identifier(new_name)}',
            'parameters': (),
        })
        final_name = new_name
    elif operation == 'visibility':
        if set(draft) - {'visibility', 'ignored', 'confirmation'}:
            raise RelationalClientError('Unknown MariaDB index visibility option')
        if 'confirmation' in draft and draft['confirmation'] != target.get('display_name'):
            raise RelationalClientError('Confirm the exact MariaDB index name')
        if 'visibility' in draft:
            vis = draft['visibility']
            if vis not in {'IGNORED', 'NOT IGNORED'}:
                raise RelationalClientError('Select MariaDB IGNORED or NOT IGNORED index visibility')
        elif 'ignored' in draft and type(draft['ignored']) is bool:
            vis = 'IGNORED' if draft['ignored'] else 'NOT IGNORED'
        else:
            raise RelationalClientError('Select MariaDB IGNORED or NOT IGNORED index visibility')
        statements.append({
            'source': f'ALTER TABLE {qualified_table} ALTER INDEX {identifier(current_name)} {vis}',
            'parameters': (),
        })
    else:
        if set(draft) - {'new_name', 'ignored', 'visible', 'active', 'confirmation'}:
            raise RelationalClientError('Unknown MariaDB index alter option')
        ignored, explicit_vis = _resolve_ignored(draft)
        if explicit_vis:
            vis = 'IGNORED' if ignored else 'NOT IGNORED'
            statements.append({
                'source': f'ALTER TABLE {qualified_table} ALTER INDEX {identifier(current_name)} {vis}',
                'parameters': (),
            })
        if 'new_name' in draft and draft['new_name'] not in (None, '', current_name):
            new_name = draft['new_name']
            if not isinstance(new_name, str) or new_name.strip().upper() == 'PRIMARY':
                raise RelationalClientError('Supply a valid non-PRIMARY index name')
            statements.append({
                'source': f'ALTER TABLE {qualified_table} RENAME INDEX {identifier(current_name)} TO {identifier(new_name)}',
                'parameters': (),
            })
            final_name = new_name
        if not statements:
            raise RelationalClientError('Select an index visibility or rename change')

    return {
        'statements': statements,
        KEY: {
            'operation': operation,
            'draft': draft,
            'table': [str(path[0]), str(path[1])],
            'index_name': current_name,
            'target_index_name': final_name,
            'target_display_path': [str(part) for part in path],
            'target_display_name': target.get('display_name'),
        },
        'warnings': [
            'MariaDB ALTER TABLE index operations perform an implicit commit on an owned connection.',
        ],
    }


def _observe(cursor, table, index_name, sql_mode):
    cursor.execute('SHOW CREATE TABLE ' + '.'.join(identifier(part) for part in table))
    row = cursor.fetchone()
    if not row or len(row) < 2 or not isinstance(row[1], str):
        raise RelationalClientError('Native MariaDB owning-table definition is unavailable')
    cursor.execute(
        'SELECT SEQ_IN_INDEX, COLUMN_NAME, SUB_PART, COLLATION, INDEX_TYPE, IGNORED, INDEX_COMMENT '
        'FROM information_schema.STATISTICS '
        'WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND INDEX_NAME = ? '
        'ORDER BY SEQ_IN_INDEX',
        (table[0], table[1], index_name),
    )
    parts = [list(item) for item in cursor.fetchall()]
    return {
        'table_definition': row[1],
        'table_structure_sha256': structural_definition(row[1], sql_mode),
        'key_parts': parts,
    }


def _public(observed):
    return {k: v for k, v in observed.items() if k != 'table_definition'}


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        cursor.execute('SELECT DATABASE()')
        (default_db,) = cursor.fetchone()
        if len(intent['table']) == 1:
            if not default_db:
                raise RelationalClientError('Select a default database or a qualified MariaDB table')
            intent['table'] = [str(default_db), intent['table'][0]]
        before = _observe(cursor, intent['table'], intent['index_name'], env['sql_mode'])
        if intent['operation'] != 'create' and not before['key_parts']:
            raise RelationalClientError('Target MariaDB index is absent on the owning table')
        intent['review'] = {
            'execution_identity': {**env, 'database': default_db},
            'before': _public(before),
        }
        planned['command_preview'].update(
            native_execution_identity=intent['review']['execution_identity'],
            native_index_observation=_public(before),
        )
        return planned
    finally:
        release(client, handle, cursor)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MariaDB index DDL requires an independently owned connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the MariaDB index operation before execution')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        cursor.execute('SELECT DATABASE()')
        (default_db,) = cursor.fetchone()
        current_identity = {**env, 'database': default_db}
        before = _observe(cursor, intent['table'], intent['index_name'], env['sql_mode'])
        if (
            current_identity['server_uid'] != review['execution_identity']['server_uid']
            or before['table_structure_sha256'] != review['before']['table_structure_sha256']
            or before['key_parts'] != review['before']['key_parts']
        ):
            raise RelationalClientError('MariaDB server identity or owning table changed since review')

        dispatched = True
        for statement in compiled['statements']:
            params = statement.get('parameters') or ()
            if params:
                cursor.execute(statement['source'], params)
            else:
                cursor.execute(statement['source'])
        acknowledged = True
        cursor.execute('SHOW WARNINGS')
        warnings = [
            {'level': str(level), 'code': int(code), 'message': str(msg)}
            for level, code, msg in cursor.fetchall()
        ]
        after = _observe(cursor, intent['table'], intent['target_index_name'], env['sql_mode'])
        return {
            'accepted': True,
            'native_acknowledged': True,
            'native_implicit_commit': True,
            'commit_requested': False,
            'rollback_requested': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'native_warnings': warnings,
            'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'index_observation': {
                'native_acknowledged': True,
                'execution_identity': current_identity,
                'before': _public(before),
                'after': _public(after),
                'concurrent_external_ddl_fenced': False,
            },
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            f'MariaDB index operation failed ({type(error).__name__}: {error})'
        )
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        raise failure from None
    finally:
        release(client, handle, cursor)


def extract_ddl_index_options(table_ddl):
    """Extract VECTOR M/DISTANCE and FULLTEXT WITH PARSER clauses per index from SHOW CREATE TABLE."""
    if not isinstance(table_ddl, str) or not table_ddl:
        return {}
    extracted = {}
    for line in table_ddl.splitlines():
        stripped = line.strip().rstrip(',')
        vec = re.match(
            r'^VECTOR\s+(?:KEY|INDEX)\s+`((?:``|[^`])+)`\s*\([^)]*\)(.*)$',
            stripped,
            re.I,
        )
        if vec:
            idx_name = vec.group(1).replace('``', '`')
            tail = vec.group(2)
            opts = {'index_kind': 'VECTOR'}
            m_match = re.search(r'(?:`M`|\bM)\s*=\s*(\d+)', tail, re.I)
            if m_match:
                opts['vector_m'] = int(m_match.group(1))
            d_match = re.search(r'(?:`DISTANCE`|\bDISTANCE)\s*=\s*([A-Za-z]+)', tail, re.I)
            if d_match:
                opts['vector_distance'] = d_match.group(1).lower()
            extracted[idx_name] = opts
            continue
        ft = re.match(
            r'^FULLTEXT\s+(?:KEY|INDEX)\s+`((?:``|[^`])+)`\s*\([^)]*\)(.*)$',
            stripped,
            re.I,
        )
        if ft:
            idx_name = ft.group(1).replace('``', '`')
            tail = ft.group(2)
            p_match = re.search(r'\bWITH\s+PARSER\s+(?:`((?:``|[^`])+)`|([A-Za-z0-9_]+))', tail, re.I)
            if p_match:
                parser = (p_match.group(1).replace('``', '`') if p_match.group(1) else p_match.group(2))
                extracted[idx_name] = {'parser': parser}
    return extracted


def enrich_catalog_indexes(optional_records, resources, resource_key, add):
    """Enrich MariaDB index resources with statistics, IGNORED state and VECTOR/FULLTEXT options."""
    grouped = {}
    for record in optional_records(
        'SELECT TABLE_SCHEMA, TABLE_NAME, NON_UNIQUE, INDEX_NAME, SEQ_IN_INDEX, '
        'COLUMN_NAME, COLLATION, SUB_PART, INDEX_TYPE, INDEX_COMMENT, IGNORED '
        'FROM information_schema.STATISTICS '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX'
    ):
        key = (record['table_schema'], record['table_name'], record['index_name'])
        grouped.setdefault(key, []).append(record)

    ddl_cache = {}
    for (database, table, name), parts in grouped.items():
        if (database, table) not in ddl_cache:
            tbl_res = resources.get(resource_key('table', [database], table), {})
            ddl_cache[(database, table)] = extract_ddl_index_options(
                tbl_res.get('native', {}).get('ddl')
            )
        extra_opts = ddl_cache[(database, table)].get(name, {})
        first = parts[0]
        raw_type = str(first.get('index_type') or '').upper()
        ignored_raw = first.get('ignored')
        is_ignored = None if ignored_raw is None else str(ignored_raw).upper() == 'YES'
        index_kind = extra_opts.get(
            'index_kind',
            {
                'FULLTEXT': 'FULLTEXT',
                'SPATIAL': 'SPATIAL',
                'RTREE': 'SPATIAL',
                'VECTOR': 'VECTOR',
            }.get(raw_type, 'NORMAL'),
        )
        method = raw_type if (
            (index_kind == 'NORMAL' and raw_type in {'BTREE', 'HASH'})
            or (index_kind == 'SPATIAL' and raw_type == 'RTREE')
        ) else 'DEFAULT'
        native = {
            **{k: v for k, v in first.items() if k not in {'table_schema', 'table_name'}},
            **extra_opts,
            'key_parts': parts,
            'ignored': is_ignored,
            'visible': None if is_ignored is None else (not is_ignored),
            'visibility': None if is_ignored is None else ('IGNORED' if is_ignored else 'NOT IGNORED'),
            'unique': int(first.get('non_unique') or 0) == 0,
            'index_kind': index_kind,
            'method': method,
            'definition_parts': [
                {
                    'name': row['column_name'],
                    **({'prefix_length': int(row['sub_part'])} if row.get('sub_part') is not None else {}),
                    'direction': {'A': 'ASC', 'D': 'DESC'}.get(row.get('collation'), 'DEFAULT'),
                }
                for row in parts
                if row.get('column_name') is not None
            ],
            'administration': {
                'allowed_operations': (
                    ['inspect', 'drop']
                    if str(name).upper() == 'PRIMARY'
                    else ['inspect', 'alter', 'rename', 'visibility', 'drop']
                ),
            },
        }
        add('index', [database, table], name, native)
