"""Typed descriptor controls translated to bounded native module options."""
from collections.abc import Mapping
from pgadmin.cdeadmin.sdk import RelationalClientError


def normalize(draft):
    draft = dict(draft)
    if draft.get('constraints'):
        raise RelationalClientError('Virtual module constraints belong to its native constructor')
    draft.pop('constraints', None)
    if 'options' in draft and not isinstance(draft['options'], Mapping):
        raise RelationalClientError('create options must be an object')
    options = dict(draft.get('options') or {})
    if 'module_options' in draft and 'module_options' in options and draft['module_options'] != options['module_options']:
        raise RelationalClientError('Conflicting SQLite module_options')
    legacy = draft.pop('module_options', options.get('module_options', {}))
    if not isinstance(legacy, Mapping):
        raise RelationalClientError('module_options must be an object')
    native = dict(legacy)
    def put(key, value):
        if key in native and native[key] != value:
            raise RelationalClientError('Conflicting SQLite module option: ' + key)
        native[key] = value
    for field, key in {'auxiliary_columns':'auxiliary_columns', 'source_table':'table',
                       'source_database':'database', 'vocabulary_mode':'mode',
                       'csv_data':'data', 'csv_schema':'schema',
                       'csv_columns_count':'columns_count', 'csv_header':'header',
                       'spellfix_vocab_table':'vocab_table', 'fuzzer_rules_table':'rules_table',
                       'vtab_namespace_tag':'namespace_tag', 'vtab_read_only_mode':'read_only_mode',
                       'vtab_with_shadow':'with_shadow'}.items():
        value = draft.pop(field, None)
        if value not in (None, '', []):
            put(key, value)
    name = draft.pop('tokenizer_name', None)
    args = draft.pop('tokenizer_arguments', [])
    if args and not name:
        raise RelationalClientError('Tokenizer arguments require a tokenizer name')
    if name:
        put('tokenizer', {'name':name, 'arguments':args})
    for key in ('matchinfo','compress','uncompress','order','languageid','content_rowid','detail'):
        value = draft.pop('fts_' + key, None)
        if value not in (None, '', 'DEFAULT'):
            put(key, value)
    for field, key in (('prefix_lengths','prefix'), ('notindexed_columns','notindexed')):
        value = draft.pop(field, None)
        if value not in (None, []):
            if key == 'prefix' and isinstance(value, list):
                value = [int(v) if isinstance(v, str) and v.isascii() and v.isdecimal() and len(v) <= 9 else v for v in value]
            put(key, value)
    mode = draft.pop('content_mode', 'INTERNAL')
    table = draft.pop('content_table', None)
    if mode == 'EXTERNAL':
        if not isinstance(table, str) or not table:
            raise RelationalClientError('External content requires its table name')
        put('content', table)
    elif mode == 'CONTENTLESS':
        if table:
            raise RelationalClientError('Contentless tables cannot specify a content table')
        put('content', '')
    elif mode != 'INTERNAL' or table:
        raise RelationalClientError('Invalid FTS content mode/table combination')
    for key in ('columnsize','contentless_delete','contentless_unindexed','tokendata','locale'):
        value = draft.pop('fts_' + key, None)
        if value not in (None, 'DEFAULT'):
            if value not in ('0', '1', 0, 1):
                raise RelationalClientError(key + ' requires 0 or 1')
            put(key, int(value))
    module = draft.get('module', options.get('module'))
    columns = draft.get('columns', options.get('columns'))
    if isinstance(columns, list):
        converted = []
        for col in columns:
            if isinstance(col, Mapping):
                if set(col) - {'name','unindexed','_id'}:
                    raise RelationalClientError('Unknown SQLite module column control')
                if module != 'fts5':
                    if col.get('unindexed', False) is not False:
                        raise RelationalClientError('UNINDEXED column control requires FTS5')
                    col = col.get('name')
                else:
                    col = {k:v for k,v in col.items() if k != '_id'}
            converted.append(col)
        if 'columns' in draft:
            draft['columns'] = converted
        else:
            options['columns'] = converted
    options['module_options'] = native
    draft['options'] = options
    return draft


# SQLite release notes: 3.43.0, 3.45.0, 3.47.0.
MINIMUM = {'contentless_delete':(3,43,0), 'tokendata':(3,45,0),
           'locale':(3,47,0), 'contentless_unindexed':(3,47,0)}


def runtime_gate(request, version):
    if request.get('resource_kind') not in {'fts-table','virtual-table'} or request.get('operation_id') != 'create':
        return
    draft = normalize(request.get('draft') or {})
    options = draft['options']['module_options']
    runtime = tuple(int(v) for v in version.split('.')[:3])
    for key, minimum in MINIMUM.items():
        if key in options and runtime < minimum:
            raise RelationalClientError(key + ' requires SQLite ' + '.'.join(map(str, minimum)))
