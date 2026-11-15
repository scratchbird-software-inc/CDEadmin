"""Native ordered B-tree expression/partial index construction."""
from ...sdk import RelationalClientError
from .expressions import expression


def create(adapter, request):
    draft = request['draft']; options = draft.get('options') or {}
    if set(options) - {'parent','table','columns','unique','terms','predicate'}:
        raise RelationalClientError('Unknown native SQLite index option')
    terms = options.get('terms'); columns = options.get('columns')
    if terms is not None and not isinstance(terms, list):
        raise RelationalClientError('Index terms must be an ordered list')
    if terms and columns:
        raise RelationalClientError('Select terms or legacy columns, not both')
    if type(options.get('unique', False)) is not bool:
        raise RelationalClientError('Unique must be Boolean')
    parts = []
    if terms:
        if len(terms) > 64:
            raise RelationalClientError('At most 64 index terms are admitted')
        for term in terms:
            if not isinstance(term, dict) or set(term) - {'kind','value','collation','order','_id'}:
                raise RelationalClientError('Select typed native index terms')
            if term.get('kind') == 'column':
                part = adapter._quote(adapter._identifier(term.get('value')))
            elif term.get('kind') == 'expression':
                part = '(' + expression(term.get('value')) + ')'
            else:
                raise RelationalClientError('Choose column or expression')
            if term.get('collation') not in (None, ''):
                part += ' COLLATE ' + adapter._quote(adapter._identifier(term['collation']))
            order = term.get('order', 'ASC')
            if order not in ('ASC','DESC'):
                raise RelationalClientError('Choose native ASC or DESC order')
            parts.append(part + ' ' + order)
        definition = ', '.join(parts)
    else:
        definition = adapter._identifier_list(columns)
    table = adapter._option_path(options, 'table')
    if len(table) > 2:
        raise RelationalClientError('SQLite index requires schema and table names')
    parent = adapter._path_value(options.get('parent') or 'main')
    schema = table[0] if len(table) == 2 else parent[0]
    ascii_lower = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
    if len(parent) != 1 or options.get('parent') and parent[0].translate(ascii_lower) != schema.translate(ascii_lower):
        raise RelationalClientError('SQLite index and table must share their exact schema')
    source = ('CREATE ' + ('UNIQUE ' if options.get('unique') else '') + 'INDEX ' +
        adapter._qualified((schema, adapter._identifier(draft['name']))) +
        ' ON ' + adapter._quote(table[-1]) + ' (' + definition + ')')
    if options.get('predicate') not in (None, ''):
        source += ' WHERE (' + expression(options['predicate']) + ')'
    return [{'source': source, 'parameters': ()}]
