"""Complete-table column permutation using native POSITION operations."""
from collections.abc import Mapping

from ...sdk.relational import RelationalClientError
from .character_metadata import identifier
from .columns import integer


def compile_operation(draft, target):
    if not isinstance(draft, Mapping) or set(draft) != {'column_order'}:
        raise RelationalClientError('Column ordering requires exactly one complete column list')
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select an inspected native table')
    native = target.get('native') or target.get('extensions', {}).get('firebird', {}).get('native', {})
    if (native.get('system_object') or str(native.get('relation_type')) not in {'0', '2', '4', '5'}):
        raise RelationalClientError('Column ordering requires a user-defined Firebird table')
    name = target.get('display_name')
    identifier(name)
    if target.get('display_path', [name]) != [name]:
        raise RelationalClientError('Native table name/path disagree')
    relation_id = integer(native.get('relation_id'), 0, 32767, 'Native relation ID')
    columns = native.get('columns')
    if not isinstance(columns, list) or not columns:
        raise RelationalClientError('Complete inspected column metadata is required')
    before = []
    for position, item in enumerate(columns):
        if not isinstance(item, Mapping):
            raise RelationalClientError('Invalid inspected column metadata')
        identifier(item.get('name'))
        if int(integer(item.get('position'), 0, 32766, 'Native column position')) != position:
            raise RelationalClientError('Inspected column positions must be complete and ordered')
        before.append(item['name'])
    desired = draft['column_order']
    if (not isinstance(desired, list) or not all(isinstance(item, str) for item in desired) or
            len(desired) != len(before) or len(set(before)) != len(before) or
            len(set(desired)) != len(desired) or set(desired) != set(before)):
        raise RelationalClientError('The new order must contain every inspected column exactly once')
    remaining = list(before)
    statements = []
    for position, column in enumerate(desired):
        if remaining[position] != column:
            remaining.remove(column)
            remaining.insert(position, column)
            statements.append({'source': 'ALTER TABLE ' + identifier(name) + ' ALTER COLUMN ' +
                identifier(column) + ' POSITION ' + str(position + 1), 'parameters': ()})
    if not statements:
        raise RelationalClientError('The column order has not changed')
    return {'statements': statements, 'firebird_column_order': {
        'table': name, 'relation_id': relation_id, 'before': before, 'after': list(desired)}}


def verify(cursor, guard):
    cursor.execute('SELECT R.RDB$RELATION_ID, COALESCE(R.RDB$SYSTEM_FLAG, 0), '
        'R.RDB$RELATION_TYPE, TRIM(TRAILING FROM F.RDB$FIELD_NAME), F.RDB$FIELD_POSITION '
        'FROM RDB$RELATIONS R JOIN RDB$RELATION_FIELDS F ON '
        'F.RDB$RELATION_NAME = R.RDB$RELATION_NAME WHERE R.RDB$RELATION_NAME = ? '
        'ORDER BY F.RDB$FIELD_POSITION', (guard['table'],))
    rows = cursor.fetchall()
    if (not rows or any(str(row[0]) != guard['relation_id'] or row[1] != 0 or
            str(row[2]) not in {'0', '2', '4', '5'} or row[4] != position
            for position, row in enumerate(rows)) or
            [row[3] for row in rows] != guard['before']):
        raise RelationalClientError('Table identity or column order changed; refresh and preview again')


def form(field):
    return {'form_id': 'firebird.table.reorder_columns', 'title': 'Reorder columns',
        'fields': [{**field('column_order', 'Column order', 'json', True,
            'Move existing columns into the desired order. Preview shows native POSITION statements.', []),
            'initial_value_path': ['column_order'], 'json_type': 'array',
            'array_editor': {'item_kind': 'string', 'fixed_items': True}}]}
