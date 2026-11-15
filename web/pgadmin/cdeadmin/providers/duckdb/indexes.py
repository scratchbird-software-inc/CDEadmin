"""Typed ordered native ART index terms; parse expressions without execution."""
from ...sdk.relational import RelationalClientError


def compile_create(adapter, request):
    import duckdb
    draft = request['draft']
    options = draft.get('options') or {}
    if not isinstance(options, dict):
        raise RelationalClientError('Native index options must be an object')
    if set(options) - {'parent', 'table', 'columns', 'terms', 'unique', 'method', 'index_options'}:
        raise RelationalClientError('Unknown DuckDB index option')
    if duckdb.__version__ != '1.5.2':
        raise RelationalClientError('Native index terms need the qualified DuckDB 1.5.2 parser')
    if options.get('method', 'ART') != 'ART':
        raise RelationalClientError('Extension index methods need their qualified native adapter')
    extra = options.get('index_options', {})
    if not isinstance(extra, dict) or extra:
        raise RelationalClientError('ART creation has no admitted WITH options; ignored options are not support')
    if type(options.get('unique', False)) is not bool:
        raise RelationalClientError('Unique index requires a Boolean choice')
    terms = options.get('terms')
    columns = options.get('columns')
    if terms is not None and not isinstance(terms, list):
        raise RelationalClientError('Index terms must be an ordered list')
    if terms and columns:
        raise RelationalClientError('Choose ordered terms or legacy columns, not both')
    if terms:
        if len(terms) > 64:
            raise RelationalClientError('Index term policy permits at most 64 entries')
        expressions = []
        for term in terms:
            if not isinstance(term, dict) or set(term) - {'kind', 'value', '_id'}:
                raise RelationalClientError('Select typed column or expression terms')
            value = term.get('value')
            if term.get('kind') == 'column':
                expressions.append(adapter._quote(adapter._identifier(value)))
            elif term.get('kind') == 'expression':
                if not isinstance(value, str) or not value.strip() or len(value.encode()) > 65536 or '\x00' in value:
                    raise RelationalClientError('Choose a bounded native index expression')
                try:
                    expression = str(duckdb.SQLExpression(value))
                except Exception:
                    raise RelationalClientError('Index term requires one native SQL expression') from None
                expressions.append('(' + expression + ')')
            else:
                raise RelationalClientError('Choose column or expression for each index term')
        definition = ', '.join(expressions)
    else:
        definition = adapter._identifier_list(columns)
    table = adapter._qualified(adapter._option_path(options, 'table'))
    source = ('CREATE ' + ('UNIQUE ' if options.get('unique') else '') +
        'INDEX ' + adapter._quote(adapter._identifier(draft['name'])) +
        ' ON ' + table + ' USING ART (' + definition + ')')
    parsed = duckdb.extract_statements(source)
    if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.CREATE:
        raise RelationalClientError('Exactly one native index creation statement is required')
    return [{'source': source, 'parameters': ()}]
