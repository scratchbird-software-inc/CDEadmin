"""View query planning preserves native columns and never recreates a view."""
from ..providers.firebird.character_metadata import identifier
from ..providers.firebird.views import catalog_columns
from ..providers.firebird.packages import source
from ..providers.firebird_expressions import index_expression

FIELDS = {'definition', 'description', 'columns'}
DERIVED = {'view_columns', 'column_order', 'view_columns_unavailable_reason', 'metadata_warnings'}


def model(row):
    native = row['native']
    if str(native.get('relation_type')) != '1':
        raise ValueError('View planning requires native relation type 1')
    definition = source(native.get('definition'), 'View query')
    # Reject script separators outside native quotes/comments. Preparation still
    # owns SELECT/CTE grammar, check options and all type/dependency semantics.
    definition = index_expression(definition, 'View query')
    ordered = catalog_columns(native.get('columns'))
    return {'definition': definition,
            'columns': [{'name': item['name'], 'position': item['position']} for item in ordered]}


def statements(before, after):
    if before is not None and before['columns'] != after['columns']:
        raise ValueError('View output renames require explicit identity mapping')
    if before is not None and before['definition'] == after['definition']:
        return []
    names = ', '.join(identifier(item['name']) for item in after['columns'])
    return [('CREATE' if before is None else 'ALTER') + ' VIEW ' + identifier(after['name']) +
            ' (' + names + ') AS\n' + after['definition'] + '\n']


def dependencies(current):
    # A proposed query can reference objects absent from the old dependency
    # list. Guard every visible native object rather than guessing SQL names.
    kinds = {'table', 'view', 'column', 'domain', 'sequence', 'procedure',
             'function', 'external-function', 'package', 'exception', 'collation',
             'character-set', 'index', 'constraint', 'trigger', 'role'}
    return sorted(identity for identity, row in current['rows'].items() if row['kind'] in kinds)
