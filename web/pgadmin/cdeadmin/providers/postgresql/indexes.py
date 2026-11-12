"""PostgreSQL indexes on the provider tree (M4, 2026-11-11).

CREATE [UNIQUE] INDEX [CONCURRENTLY] name ON [ONLY] table USING method
(columns or expressions with COLLATE, operator class, ASC | DESC and NULLS
FIRST | LAST) [INCLUDE (...)] [NULLS NOT DISTINCT] [WITH (storage
parameters)] [TABLESPACE] [WHERE predicate]; COMMENT ON INDEX; ALTER INDEX
RENAME TO / SET TABLESPACE / SET | RESET (storage parameters); ALTER TABLE
CLUSTER ON; DROP INDEX [CONCURRENTLY]. Every access method the server has
(btree, hash, gist, spgist, gin, brin, ...) is offered: the matrix lists
BRIN and GiST as refusals YugabyteDB has and PostgreSQL must get back. The
column list is fixed once created. REINDEX is already provider-native.
Field ids follow the inherited dialog (``index.ui.js``).

CONCURRENTLY cannot run in a transaction block, so a concurrent create or
drop is exactly one statement in autocommit; the comment follows in an
alter. The alter dialog's initial values come from ``pg_get_indexdef`` read
back through PostgreSQL's own parser.

Owner direction 2026-11-11: every field of the family form is admitted and
compiled. The access-method options the dialog shows as fields
(deduplicate_items, fastupdate, gin_pending_list_limit, pages_per_range,
autosummarize, buffering) are storage parameters; on edit an empty value
resets one. A column row's statistics target becomes ALTER INDEX ... ALTER
COLUMN n SET STATISTICS; extensions the index depends on become ALTER
INDEX ... DEPENDS ON EXTENSION; clustering on create follows the create.
The dialog's booleans for sort order (true = DESC) and NULLs (true =
FIRST) are accepted beside the words.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified,
)
from .policies import expression

_METHOD = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')
_PARAMETER = re.compile(r'[A-Za-z_][A-Za-z0-9_.]{0,62}')
_PARAMETER_VALUE = re.compile(r'[A-Za-z0-9_.-]{1,64}')
_ORDERING = {1: 'ASC', 2: 'DESC'}
_NULLS = {1: 'FIRST', 2: 'LAST'}
# Access-method options the family form shows as fields: name -> kind.
AM_OPTIONS = {'deduplicate_items': 'boolean', 'fastupdate': 'boolean',
              'autosummarize': 'boolean', 'gin_pending_list_limit': 'number',
              'pages_per_range': 'number', 'buffering': 'text'}
FIXED_ONCE_CREATED = ('indisunique', 'indconstraint', 'amname', 'include',
                      'isconcurrent', 'indisonly', 'indnullsnotdistinct')


def _blank(value):
    return value is None or value == '' or value == []


def _render(node):
    from pglast.stream import RawStream
    return RawStream()(node)


def _names(nodes):
    return '.'.join(_identifier(item.sval, 'name') for item in nodes or [])


def facts(native):
    """Current values from pg_get_indexdef; never raises."""
    row = native.get('catalog_row') or {}
    result = {'name': native.get('name') or row.get('relname'),
              'schema': native.get('schema'), 'table': None,
              'amname': None, 'indisunique': False, 'isconcurrent': False,
              'indnullsnotdistinct': False, 'columns': [], 'include': [],
              'indconstraint': None, 'spcname': None,
              'storage_parameters': [], 'description': native.get('comment'),
              'dependsonextensions': list(
                  native.get('depends_on_extensions') or []),
              'definition_parsed': False}
    for option in AM_OPTIONS:
        result[option] = None
    result['fillfactor'] = None
    definition = native.get('definition')
    if not isinstance(definition, str) or not definition.strip():
        return result
    try:
        from pglast import parse_sql
        statement = parse_sql(definition)[0].stmt
        result.update({
            'table': statement.relation.relname,
            'schema': statement.relation.schemaname or result['schema'],
            'amname': statement.accessMethod,
            'indisunique': bool(statement.unique),
            'indnullsnotdistinct': bool(statement.nulls_not_distinct),
            'spcname': statement.tableSpace,
            'indconstraint': _render(statement.whereClause)
            if statement.whereClause is not None else None,
            'include': [item.name for item in
                        statement.indexIncludingParams or []]})
        for item in statement.indexParams or []:
            ordering = getattr(item.ordering, 'value', item.ordering)
            nulls = getattr(item.nulls_ordering, 'value', item.nulls_ordering)
            # pg_get_indexdef omits the defaults; the dialog shows them, so
            # the facts state them: ASC, and NULLS LAST for ASC or FIRST
            # for DESC.
            order = _ORDERING.get(int(ordering or 0)) or 'ASC'
            result['columns'].append({
                'colname': item.name if item.expr is None else _render(
                    item.expr),
                'is_exp': item.expr is not None,
                'collspcname': _names(item.collation) or None,
                'op_class': _names(item.opclass) or None,
                'sort_order': order,
                'nulls': _NULLS.get(int(nulls or 0)) or (
                    'FIRST' if order == 'DESC' else 'LAST')})
        for option in statement.options or []:
            value = option.arg
            text = getattr(value, 'sval', None)
            if text is None:
                text = str(getattr(value, 'ival', None)) if hasattr(
                    value, 'ival') else _render(value)
            result['storage_parameters'].append({'name': option.defname,
                                                 'value': text})
        result['definition_parsed'] = True
    except Exception:
        return result
    for item in result['storage_parameters']:
        name, value = item['name'], item['value']
        if name == 'fillfactor' or AM_OPTIONS.get(name) == 'number':
            result[name] = int(value) if str(value).isdigit() else value
        elif AM_OPTIONS.get(name) == 'boolean':
            result[name] = str(value).lower() in ('on', 'true', 't', '1',
                                                  'yes')
        elif name in AM_OPTIONS:
            result[name] = value
    return result


def _ordering(value, words, label):
    """The dialog's boolean (true = the first word) or a word."""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return words[0] if value else words[1]
    text = str(value).upper()
    if text not in words:
        natural = sorted(words) if 'ASC' in words else list(words)
        raise PostgreSQLNativeAdminError(
            f'{label} is {natural[0]} or {natural[1]}')
    return text


def _shape(columns):
    """Column rows as comparable tuples; statistics are not part of the
    definition and the dialog's booleans equal the words."""
    shaped = []
    for row in columns or []:
        if not isinstance(row, dict):
            raise PostgreSQLNativeAdminError('index columns must be rows')
        # pg_get_indexdef omits the defaults (ASC, and NULLS LAST for ASC
        # or FIRST for DESC); the dialog's unchecked boxes mean the same.
        order = _ordering(row.get('sort_order'), ('DESC', 'ASC'),
                          'sort order') or 'ASC'
        nulls = _ordering(row.get('nulls'), ('FIRST', 'LAST'), 'NULLs') or (
            'FIRST' if order == 'DESC' else 'LAST')
        shaped.append((row.get('colname'), bool(row.get('is_exp')),
                       row.get('collspcname') or None,
                       row.get('op_class') or None, order, nulls))
    return shaped


def _named_parameters(draft):
    """The access-method option fields as storage parameter rows, and the
    names an empty value asks to reset."""
    rows, resets = [], []
    for name in AM_OPTIONS:
        if name not in draft:
            continue
        if _blank(draft[name]):
            resets.append(name)
        else:
            rows.append({'name': name, 'value': draft[name]})
    return rows, resets


def _statistics(qualified, columns):
    statements = []
    for position, row in enumerate(columns or [], 1):
        value = row.get('statistics') if isinstance(row, dict) else None
        if _blank(value):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int) or \
                value < -1:
            raise PostgreSQLNativeAdminError(
                'a statistics target is a whole number, -1 for the default')
        statements.append(f'ALTER INDEX {qualified} ALTER COLUMN {position} '
                          f'SET STATISTICS {value}')
    return statements


def _depends(qualified, draft):
    value = draft.get('dependsonextensions')
    if _blank(value):
        return []
    if not isinstance(value, list):
        raise PostgreSQLNativeAdminError('extensions must be a list')
    statements = []
    for item in value:
        name = item.get('name') if isinstance(item, dict) else item
        statements.append(f'ALTER INDEX {qualified} DEPENDS ON EXTENSION '
                          + _identifier(name, 'extension'))
    return statements


def _column(row):
    if not isinstance(row, dict):
        raise PostgreSQLNativeAdminError('index columns must be rows')
    name = row.get('colname')
    if row.get('is_exp'):
        text = '(' + expression(name, 'index expression') + ')'
    else:
        text = _identifier(name, 'column')
    if not _blank(row.get('collspcname')):
        from .native_admin import _reference
        text += ' COLLATE ' + _reference(row['collspcname'], 'collation')
    if not _blank(row.get('op_class')):
        from .native_admin import _reference
        text += ' ' + _reference(row['op_class'], 'operator class')
    order = _ordering(row.get('sort_order'), ('DESC', 'ASC'), 'sort order')
    if order:
        text += ' ' + order
    nulls = _ordering(row.get('nulls'), ('FIRST', 'LAST'), 'NULLs')
    if nulls:
        text += ' NULLS ' + nulls
    return text


def _parameters(rows):
    parts = []
    for row in rows:
        if not isinstance(row, dict):
            raise PostgreSQLNativeAdminError('storage parameters must be rows')
        name = row.get('name')
        if not isinstance(name, str) or not _PARAMETER.fullmatch(name):
            raise PostgreSQLNativeAdminError(
                'a storage parameter needs a name')
        value = row.get('value')
        if isinstance(value, bool):
            value = 'on' if value else 'off'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str) or not _PARAMETER_VALUE.fullmatch(
                value):
            raise PostgreSQLNativeAdminError(
                f'{name} takes a number, on/off or a plain word')
        parts.append(f'{name}={value}')
    return parts


def _method(value):
    if _blank(value):
        return None
    if not isinstance(value, str) or not _METHOD.fullmatch(value):
        raise PostgreSQLNativeAdminError('access method is a method name')
    return value.lower()


def _create(draft):
    schema = _name(draft.get('schema'), 'schema')
    table = _qualified(schema, draft.get('table'))
    name = _identifier(draft.get('name'), 'name')
    concurrent = _flag(draft, 'isconcurrent')
    columns = draft.get('columns')
    if not isinstance(columns, list) or not columns:
        raise PostgreSQLNativeAdminError(
            'an index needs at least one column or expression')
    text = 'CREATE ' + ('UNIQUE ' if _flag(draft, 'indisunique') else '') \
        + 'INDEX ' + ('CONCURRENTLY ' if concurrent else '') + name
    text += ' ON ' + ('ONLY ' if _flag(draft, 'indisonly') else '') + table
    method = _method(draft.get('amname'))
    if method:
        text += f' USING {method}'
    text += ' (' + ', '.join(_column(row) for row in columns) + ')'
    include = draft.get('include')
    if not _blank(include):
        if not isinstance(include, list):
            raise PostgreSQLNativeAdminError('include columns must be rows')
        text += ' INCLUDE (' + ', '.join(
            _identifier(item.get('colname') if isinstance(item, dict)
                        else item, 'include column') for item in include) + ')'
    if _flag(draft, 'indnullsnotdistinct'):
        text += ' NULLS NOT DISTINCT'
    parameters = list(draft.get('storage_parameters') or [])
    parameters.extend(_named_parameters(draft)[0])
    if not _blank(draft.get('fillfactor')):
        parameters.insert(0, {'name': 'fillfactor',
                              'value': draft['fillfactor']})
    if parameters:
        text += ' WITH (' + ', '.join(_parameters(parameters)) + ')'
    if not _blank(draft.get('spcname')):
        text += ' TABLESPACE ' + _identifier(draft['spcname'], 'tablespace')
    if not _blank(draft.get('indconstraint')):
        text += ' WHERE ' + expression(draft['indconstraint'], 'predicate')
    qualified = _qualified(schema, draft['name'])
    follow_ups = _statistics(qualified, columns) + _depends(qualified, draft)
    if _flag(draft, 'indisclustered') if 'indisclustered' in draft else False:
        follow_ups.append(f'ALTER TABLE {table} CLUSTER ON {name}')
    if not _blank(draft.get('description')):
        comment = _literal(str(draft['description']), 'comment')
        follow_ups.append(f'COMMENT ON INDEX {qualified} IS {comment}')
    if concurrent:
        if follow_ups:
            raise PostgreSQLNativeAdminError(
                'a concurrent build runs alone outside a transaction; set '
                'the comment, statistics, extension dependencies and '
                'clustering with Edit afterwards')
        return {'statement': text, 'read_only': False, 'autocommit': True}
    return {'statement': ';\n'.join([text] + follow_ups), 'read_only': False}


def _alter(native, draft):
    current = native.get('index_facts') or facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    columns = draft.get('columns')
    if not _blank(columns) and _shape(columns) != _shape(current['columns']):
        raise PostgreSQLNativeAdminError(
            'the columns are fixed once created; drop and create the index '
            'to change them')
    for key in FIXED_ONCE_CREATED:
        if key in draft and not _blank(draft[key]) and \
                draft[key] != current.get(key) and not (
                    key == 'include' and [
                        item.get('colname') if isinstance(item, dict)
                        else item for item in draft[key]] == current[key]):
            raise PostgreSQLNativeAdminError(
                f'{key} is fixed once created; drop and create the index to '
                'change it')
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER INDEX {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        name = new_name
        qualified = _qualified(schema, name)
    if not _blank(draft.get('spcname')) and draft['spcname'] != current[
            'spcname']:
        statements.append(f'ALTER INDEX {qualified} SET TABLESPACE '
                          + _identifier(draft['spcname'], 'tablespace'))
    parameters = list(draft.get('storage_parameters') or [])
    named, named_resets = _named_parameters(draft)
    parameters.extend(named)
    held = {item['name']: item['value']
            for item in current['storage_parameters']}
    if not _blank(draft.get('fillfactor')):
        parameters.insert(0, {'name': 'fillfactor',
                              'value': draft['fillfactor']})
    elif 'fillfactor' in draft and 'fillfactor' in held:
        named_resets.insert(0, 'fillfactor')
    wanted = _parameters(parameters)
    changed = [item for item in wanted
               if held.get(item.split('=')[0]) != item.split('=', 1)[1]]
    if changed:
        statements.append(f'ALTER INDEX {qualified} SET ('
                          + ', '.join(changed) + ')')
    resets = draft.get('reset_parameters')
    names = [name for name in named_resets if name in held]
    if not _blank(resets):
        if not isinstance(resets, list):
            raise PostgreSQLNativeAdminError('reset parameters must be rows')
        for item in resets:
            value = item.get('name') if isinstance(item, dict) else item
            if not isinstance(value, str) or not _PARAMETER.fullmatch(value):
                raise PostgreSQLNativeAdminError(
                    'a reset parameter needs a name')
            names.append(value)
    if names:
        statements.append(f'ALTER INDEX {qualified} RESET ('
                          + ', '.join(names) + ')')
    if not _blank(columns):
        statements.extend(_statistics(qualified, columns))
    statements.extend(_depends(qualified, draft))
    if _flag(draft, 'indisclustered'):
        table = current.get('table')
        if not table:
            raise PostgreSQLNativeAdminError(
                'the owning table is unknown; refresh the tree')
        statements.append(f'ALTER TABLE {_qualified(schema, table)} CLUSTER '
                          f'ON {_identifier(name, "name")}')
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        text = 'NULL' if _blank(draft['description']) else _literal(
            str(draft['description']), 'comment')
        statements.append(f'COMMENT ON INDEX {qualified} IS {text}')
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _drop(native, draft):
    current = native.get('index_facts') or facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    qualified = _qualified(current['schema'], name)
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    if _flag(draft, 'concurrently'):
        if _flag(draft, 'cascade'):
            raise PostgreSQLNativeAdminError(
                'DROP INDEX CONCURRENTLY does not take CASCADE')
        return {'statement': f'DROP INDEX CONCURRENTLY {qualified}',
                'read_only': False, 'autocommit': True}
    return {'statement': f'DROP INDEX {qualified}{cascade}',
            'read_only': False}


def compile_operation(operation, native, draft):
    """One exact native text for the index lifecycle."""
    if operation == 'create':
        return _create(draft)
    if operation == 'alter':
        return _alter(native, draft)
    if operation == 'drop':
        return _drop(native, draft)
    raise PostgreSQLNativeAdminError(
        'index inspection stays with the provider tree')


# The family form's field ids (index.form.json) by operation, plus the
# provider's own: the validator admits exactly these.
_FAMILY_FIELDS = {
    'create': ('name', 'schema', 'table', 'indisunique', 'indconstraint',
               'columns', 'description', 'amname', 'include', 'fillfactor',
               'isconcurrent', 'spcname', 'dependsonextensions', 'indisonly',
               'gin_pending_list_limit', 'pages_per_range', 'buffering',
               'deduplicate_items', 'fastupdate', 'autosummarize',
               'indnullsnotdistinct', 'indisclustered', 'storage_parameters'),
    'alter': ('name', 'oid', 'indisunique', 'indconstraint', 'columns',
              'indisvalid', 'indisprimary', 'is_sys_idx', 'description',
              'amname', 'include', 'fillfactor', 'isconcurrent', 'spcname',
              'dependsonextensions', 'indisonly', 'gin_pending_list_limit',
              'pages_per_range', 'buffering', 'deduplicate_items',
              'fastupdate', 'autosummarize', 'indnullsnotdistinct',
              'indisclustered', 'storage_parameters', 'reset_parameters'),
}
_GRIDS = ('columns', 'storage_parameters', 'reset_parameters')
_LISTS = ('include', 'dependsonextensions')
_BOOLEANS = ('indisunique', 'isconcurrent', 'indisonly', 'deduplicate_items',
             'fastupdate', 'autosummarize', 'indnullsnotdistinct',
             'indisclustered', 'indisvalid', 'indisprimary', 'is_sys_idx')
_NUMBERS = ('fillfactor', 'gin_pending_list_limit', 'pages_per_range', 'oid')


def form(operation, field):
    """The validator's view of the index family form: every field id the
    dialog sends, typed loosely; the family form file carries the labels,
    tabs, options and grid columns."""
    if operation == 'drop':
        return {'form_id': 'postgresql-index-drop',
                'form_key': 'native:postgresql:schema:index',
                'title': 'Drop index', 'fields': [
                    field('cascade', 'Drop dependent objects', 'boolean'),
                    field('concurrently', 'Concurrently (runs alone, outside '
                          'a transaction)', 'boolean'),
                    field('confirmation', 'Type the index name to confirm',
                          required=True)],
                'notes': 'Constraint-backed indexes (primary key, unique, '
                         'exclusion) are edited through their constraints.'}
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': ['index_facts', key]} if alter else {}
    fields = []
    for field_id in _FAMILY_FIELDS[operation]:
        label = field_id.replace('_', ' ').capitalize()
        if field_id in _GRIDS:
            fields.append(field(field_id, label, 'grid', columns=[],
                                required=field_id == 'columns' and not alter,
                                **initial(field_id)))
        elif field_id in _LISTS:
            # The dialog sends a list of names; a grid admits any list.
            fields.append(field(field_id, label, 'grid', columns=[],
                                **initial(field_id)))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, label, 'boolean',
                                **initial(field_id)))
        elif field_id in _NUMBERS:
            fields.append(field(field_id, label, 'number',
                                **initial(field_id)))
        elif field_id == 'indconstraint':
            fields.append(field(field_id, 'Constraint (WHERE predicate)',
                                'code', **initial(field_id)))
        else:
            fields.append(field(field_id, label,
                                required=field_id in ('name', 'schema',
                                                      'table') and not alter,
                                **initial(field_id)))
    return {'form_id': f'postgresql-index-{operation}',
            'form_key': 'native:postgresql:schema:index',
            'title': f'{operation.title()} index', 'fields': fields,
            'notes': ('Constraint-backed indexes (primary key, unique, '
                      'exclusion) are edited through their constraints. '
                      'The columns, uniqueness, method, predicate and '
                      'INCLUDE list are fixed once created; the Reset '
                      'storage parameters grid removes an option on edit, '
                      'an unchecked boolean one sets it off.')}
