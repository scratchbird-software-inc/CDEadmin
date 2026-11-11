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
              'definition_parsed': False}
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
            result['columns'].append({
                'colname': item.name if item.expr is None else _render(
                    item.expr),
                'is_exp': item.expr is not None,
                'collspcname': _names(item.collation) or None,
                'op_class': _names(item.opclass) or None,
                'sort_order': _ORDERING.get(int(ordering or 0)),
                'nulls': _NULLS.get(int(nulls or 0))})
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
    return result


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
    order = str(row.get('sort_order') or '').upper()
    if order:
        if order not in ('ASC', 'DESC'):
            raise PostgreSQLNativeAdminError('sort order is ASC or DESC')
        text += ' ' + order
    nulls = str(row.get('nulls') or '').upper()
    if nulls:
        if nulls not in ('FIRST', 'LAST'):
            raise PostgreSQLNativeAdminError('NULLs are FIRST or LAST')
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
    if not _blank(draft.get('fillfactor')):
        parameters.insert(0, {'name': 'fillfactor',
                              'value': draft['fillfactor']})
    if parameters:
        text += ' WITH (' + ', '.join(_parameters(parameters)) + ')'
    if not _blank(draft.get('spcname')):
        text += ' TABLESPACE ' + _identifier(draft['spcname'], 'tablespace')
    if not _blank(draft.get('indconstraint')):
        text += ' WHERE ' + expression(draft['indconstraint'], 'predicate')
    if concurrent:
        if not _blank(draft.get('description')):
            raise PostgreSQLNativeAdminError(
                'a concurrent build runs alone outside a transaction; set '
                'the comment with Alter afterwards')
        return {'statement': text, 'read_only': False, 'autocommit': True}
    statements = [text]
    if not _blank(draft.get('description')):
        qualified = _qualified(schema, draft['name'])
        comment = _literal(str(draft['description']), 'comment')
        statements.append(f'COMMENT ON INDEX {qualified} IS {comment}')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _alter(native, draft):
    current = native.get('index_facts') or facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    columns = draft.get('columns')
    if not _blank(columns) and columns != current['columns']:
        raise PostgreSQLNativeAdminError(
            'the columns are fixed once created; drop and create the index '
            'to change them')
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
    if not _blank(draft.get('fillfactor')):
        parameters.insert(0, {'name': 'fillfactor',
                              'value': draft['fillfactor']})
    held = {item['name']: item['value']
            for item in current['storage_parameters']}
    wanted = _parameters(parameters)
    changed = [item for item in wanted
               if held.get(item.split('=')[0]) != item.split('=', 1)[1]]
    if changed:
        statements.append(f'ALTER INDEX {qualified} SET ('
                          + ', '.join(changed) + ')')
    resets = draft.get('reset_parameters')
    if not _blank(resets):
        if not isinstance(resets, list):
            raise PostgreSQLNativeAdminError('reset parameters must be rows')
        names = []
        for item in resets:
            value = item.get('name') if isinstance(item, dict) else item
            if not isinstance(value, str) or not _PARAMETER.fullmatch(value):
                raise PostgreSQLNativeAdminError(
                    'a reset parameter needs a name')
            names.append(value)
        statements.append(f'ALTER INDEX {qualified} RESET ('
                          + ', '.join(names) + ')')
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


def form(operation, field):
    """Dialog fields; ids follow the inherited index dialog."""
    def column(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    parameter_columns = [column('name', 'Parameter', required=True),
                         column('value', 'Value', required=True)]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('concurrently', 'Concurrently (runs alone, outside '
                        'a transaction)', 'boolean'),
                  field('confirmation', 'Type the index name to confirm',
                        required=True)]
    elif operation == 'create':
        fields = [
            field('name', 'Name', required=True),
            field('schema', 'Schema', required=True),
            field('table', 'Table', required=True),
            field('amname', 'Access method', help=(
                'btree, hash, gist, spgist, gin, brin or another method the '
                'server has; empty for the default.')),
            field('indisunique', 'Unique', 'boolean'),
            field('indnullsnotdistinct', 'NULLs not distinct', 'boolean',
                  help='PostgreSQL 15 and later.'),
            field('isconcurrent', 'Concurrent build', 'boolean', help=(
                'Runs alone outside a transaction; set the comment '
                'afterwards.')),
            field('indisonly', 'Only this table (not partitions)', 'boolean'),
            field('columns', 'Columns/Expressions', 'grid', required=True,
                  columns=[
                      column('colname', 'Column or expression', required=True),
                      column('is_exp', 'Is expression', 'boolean'),
                      column('collspcname', 'Collation'),
                      column('op_class', 'Operator class'),
                      column('sort_order', 'Sort order', 'select', options=[
                          {'value': 'ASC', 'label': 'ASC'},
                          {'value': 'DESC', 'label': 'DESC'}]),
                      column('nulls', 'NULLs', 'select', options=[
                          {'value': 'FIRST', 'label': 'FIRST'},
                          {'value': 'LAST', 'label': 'LAST'}])]),
            field('include', 'Include columns', 'grid', columns=[
                column('colname', 'Column', required=True)]),
            field('fillfactor', 'Fill factor', 'number'),
            field('storage_parameters', 'Storage parameters', 'grid',
                  columns=parameter_columns, help=(
                      'deduplicate_items, fastupdate, '
                      'gin_pending_list_limit, pages_per_range, '
                      'autosummarize, buffering, ...')),
            field('spcname', 'Tablespace'),
            field('indconstraint', 'Constraint (WHERE predicate)', 'code'),
            field('description', 'Comment', 'multiline')]
    else:
        def initial(key):
            return {'initial_value_path': ['index_facts', key]}
        fields = [
            field('name', 'Name', **initial('name')),
            field('columns', 'Columns/Expressions', 'grid', columns=[
                column('colname', 'Column or expression'),
                column('is_exp', 'Is expression', 'boolean'),
                column('collspcname', 'Collation'),
                column('op_class', 'Operator class'),
                column('sort_order', 'Sort order'),
                column('nulls', 'NULLs')],
                  help='Fixed once created.', **initial('columns')),
            field('spcname', 'Tablespace', **initial('spcname')),
            field('fillfactor', 'Fill factor', 'number'),
            field('storage_parameters', 'Set storage parameters', 'grid',
                  columns=parameter_columns,
                  **initial('storage_parameters')),
            field('reset_parameters', 'Reset storage parameters', 'grid',
                  columns=[column('name', 'Parameter', required=True)]),
            field('indisclustered', 'Cluster the table on this index',
                  'boolean', help='Not on a partial or BRIN index.'),
            field('description', 'Comment', 'multiline',
                  **initial('description'))]
    return {'form_id': f'postgresql-index-{operation}',
            'form_key': 'native:postgresql:schema:index',
            'title': f'{operation.title()} index', 'fields': fields,
            'notes': 'Constraint-backed indexes (primary key, unique, '
                     'exclusion) are edited through their constraints.'}
