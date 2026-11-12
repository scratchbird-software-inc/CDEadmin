"""PostgreSQL text search configurations, dictionaries, parsers and
templates on the provider tree (M5, 2026-11-11).

CREATE TEXT SEARCH CONFIGURATION (PARSER = p | COPY = c) with ADD | ALTER
| DROP MAPPING FOR token WITH dictionaries, owner, comment, rename, SET
SCHEMA; CREATE TEXT SEARCH DICTIONARY (TEMPLATE = t, option = 'value', ...)
with options set or dropped in place, owner, comment, rename, SET SCHEMA
(the template is fixed); CREATE TEXT SEARCH PARSER (START, GETTOKEN, END,
LEXTYPES, HEADLINE) and CREATE TEXT SEARCH TEMPLATE (INIT, LEXIZE) with
comment, rename and SET SCHEMA, where a changed function is drop and
create, as the inherited dialogs do. Field ids follow the inherited
dialogs. The capture holds a configuration's mappings and a dictionary's
template as OIDs, so mapping and option changes are explicit rows.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference,
)

_TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')
_OPTION = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')
KEYWORDS = {'text-search-configuration': 'CONFIGURATION',
            'text-search-dictionary': 'DICTIONARY',
            'text-search-parser': 'PARSER',
            'text-search-template': 'TEMPLATE'}
_PARSER_FUNCTIONS = (('prsstart', 'START'), ('prstoken', 'GETTOKEN'),
                     ('prsend', 'END'), ('prslextype', 'LEXTYPES'),
                     ('prsheadline', 'HEADLINE'))
_TEMPLATE_FUNCTIONS = (('tmplinit', 'INIT'), ('tmpllexize', 'LEXIZE'))


def _blank(value):
    return value is None or value == '' or value == []


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _comment(keyword, qualified, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON TEXT SEARCH {keyword} {qualified} IS {text}'


# -- facts --------------------------------------------------------------------

def facts(kind, native):
    row = native.get('catalog_row') or {}
    result = {'name': native.get('name'), 'schema': native.get('schema'),
              'description': native.get('comment')}
    if kind == 'text-search-dictionary':
        result['dictinitoption'] = row.get('dictinitoption')
    elif kind == 'text-search-parser':
        for key, _ in _PARSER_FUNCTIONS:
            value = row.get(key)
            result[key] = None if value in (None, '-') else value
    elif kind == 'text-search-template':
        for key, _ in _TEMPLATE_FUNCTIONS:
            value = row.get(key)
            result[key] = None if value in (None, '-') else value
    else:
        result['mapping_count'] = len(
            (native.get('children') or {}).get('pg_ts_config_map') or [])
    return result


# -- shared alter tail: owner, comment, rename, schema ------------------------

def _tail(keyword, qualified, schema, name, current, draft, *,
          owner_key='owner'):
    statements = []
    if owner_key and not _blank(draft.get(owner_key)):
        statements.append(f'ALTER TEXT SEARCH {keyword} {qualified} OWNER TO '
                          + _identifier(draft[owner_key], 'owner'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment(keyword, qualified, draft['description']))
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER TEXT SEARCH {keyword} {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        qualified = _qualified(schema, new_name)
    new_schema = draft.get('schema')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER TEXT SEARCH {keyword} {qualified} '
                          'SET SCHEMA ' + _identifier(new_schema, 'schema'))
    return statements


# -- configurations -----------------------------------------------------------

def _mapping(row, action):
    token = row.get('token')
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise PostgreSQLNativeAdminError('a mapping needs a token type name')
    if action == 'DROP':
        return f'DROP MAPPING FOR {token}'
    dictionaries = row.get('dictname')
    if isinstance(dictionaries, str):
        dictionaries = [item.strip() for item in dictionaries.split(',')
                        if item.strip()]
    if not isinstance(dictionaries, list) or not dictionaries:
        raise PostgreSQLNativeAdminError(
            f'the {token} mapping needs at least one dictionary')
    return f'{action} MAPPING FOR {token} WITH ' + ', '.join(
        _reference(item, 'dictionary') for item in dictionaries)


def _configuration_create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    copied, parser = draft.get('copy_config'), draft.get('prsname')
    if not _blank(copied) and not _blank(parser):
        raise PostgreSQLNativeAdminError(
            'a configuration copies another or names a parser, not both')
    if not _blank(copied):
        option = 'COPY = ' + _reference(copied, 'copied configuration')
    elif not _blank(parser):
        option = 'PARSER = ' + _reference(parser, 'parser')
    else:
        raise PostgreSQLNativeAdminError(
            'a configuration needs a parser or a configuration to copy')
    statements = [f'CREATE TEXT SEARCH CONFIGURATION {qualified} ({option})']
    for row in _rows(draft, 'tokens', 'mappings'):
        statements.append(f'ALTER TEXT SEARCH CONFIGURATION {qualified} '
                          + _mapping(row, 'ADD'))
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER TEXT SEARCH CONFIGURATION {qualified} '
                          'OWNER TO ' + _identifier(draft['owner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('CONFIGURATION', qualified,
                                   draft['description']))
    return statements


def _configuration_alter(native, draft):
    current = native.get('text_search_facts') or facts(
        'text-search-configuration', native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    for key, action in (('add_mappings', 'ADD'), ('alter_mappings', 'ALTER'),
                        ('drop_mappings', 'DROP')):
        for row in _rows(draft, key, key.replace('_', ' ')):
            statements.append(f'ALTER TEXT SEARCH CONFIGURATION {qualified} '
                              + _mapping(row, action))
    statements += _tail('CONFIGURATION', qualified, schema, name, current,
                        draft)
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


# -- dictionaries -------------------------------------------------------------

def _option(row, *, value_required=True):
    option = row.get('option')
    if not isinstance(option, str) or not _OPTION.fullmatch(option):
        raise PostgreSQLNativeAdminError('an option needs a name')
    if not value_required:
        return option
    value = row.get('value')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise PostgreSQLNativeAdminError(f'option {option} needs a value')
    return f'{option} = {_literal(value, option)}'


def _dictionary_create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    parts = ['TEMPLATE = ' + _reference(draft.get('template'), 'template')]
    parts += [_option(row) for row in _rows(draft, 'options', 'options')]
    statements = [f'CREATE TEXT SEARCH DICTIONARY {qualified} ('
                  + ', '.join(parts) + ')']
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER TEXT SEARCH DICTIONARY {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('DICTIONARY', qualified,
                                   draft['description']))
    return statements


def _dictionary_alter(native, draft):
    current = native.get('text_search_facts') or facts(
        'text-search-dictionary', native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    if not _blank(draft.get('template')):
        raise PostgreSQLNativeAdminError(
            'the template is fixed once created; drop and create the '
            'dictionary to change it')
    statements = []
    parts = [_option(row) for row in _rows(draft, 'set_options',
                                           'set options')]
    parts += [_option(row, value_required=False)
              for row in _rows(draft, 'drop_options', 'dropped options')]
    if parts:
        statements.append(f'ALTER TEXT SEARCH DICTIONARY {qualified} ('
                          + ', '.join(parts) + ')')
    statements += _tail('DICTIONARY', qualified, schema, name, current, draft)
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


# -- parsers and templates ----------------------------------------------------

def _function_definition(draft, current, functions, required):
    parts = []
    for key, keyword in functions:
        value = draft.get(key)
        if _blank(value) and current is not None:
            value = current.get(key)
        if _blank(value) or value == '-':
            if key in required:
                raise PostgreSQLNativeAdminError(f'{keyword} is required')
            continue
        parts.append(f'{keyword} = ' + _reference(value, keyword))
    return '(' + ', '.join(parts) + ')'


def _parser_create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    statements = [f'CREATE TEXT SEARCH PARSER {qualified} '
                  + _function_definition(draft, None, _PARSER_FUNCTIONS, {
                      'prsstart', 'prstoken', 'prsend', 'prslextype'})]
    if not _blank(draft.get('description')):
        statements.append(_comment('PARSER', qualified, draft['description']))
    return statements


def _template_create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    statements = [f'CREATE TEXT SEARCH TEMPLATE {qualified} '
                  + _function_definition(draft, None, _TEMPLATE_FUNCTIONS,
                                         {'tmpllexize'})]
    if not _blank(draft.get('description')):
        statements.append(_comment('TEMPLATE', qualified,
                                   draft['description']))
    return statements


def _functions_alter(kind, native, draft):
    keyword = KEYWORDS[kind]
    functions = _PARSER_FUNCTIONS if kind == 'text-search-parser' else \
        _TEMPLATE_FUNCTIONS
    required = {'prsstart', 'prstoken', 'prsend', 'prslextype'} if kind == \
        'text-search-parser' else {'tmpllexize'}
    current = native.get('text_search_facts') or facts(kind, native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    changed = any(not _blank(draft.get(key)) and draft[key] != current.get(key)
                  for key, _ in functions)
    if changed:
        # As the inherited dialog: functions cannot change in place.
        statements.append(f'DROP TEXT SEARCH {keyword} {qualified}')
        statements.append(f'CREATE TEXT SEARCH {keyword} {qualified} '
                          + _function_definition(draft, current, functions,
                                                 required))
    statements += _tail(keyword, qualified, schema, name, current, draft,
                        owner_key=None)
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


# -- drop and dispatch --------------------------------------------------------

def _drop(kind, native, draft):
    current = native.get('text_search_facts') or facts(kind, native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP TEXT SEARCH {KEYWORDS[kind]} '
            f'{_qualified(current["schema"], name)}{cascade}']


_CREATE = {'text-search-configuration': _configuration_create,
           'text-search-dictionary': _dictionary_create,
           'text-search-parser': _parser_create,
           'text-search-template': _template_create}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a text search object."""
    if operation == 'create':
        statements = _CREATE[kind](draft)
    elif operation == 'alter':
        if kind == 'text-search-configuration':
            statements = _configuration_alter(native, draft)
        elif kind == 'text-search-dictionary':
            statements = _dictionary_alter(native, draft)
        else:
            statements = _functions_alter(kind, native, draft)
    elif operation == 'drop':
        statements = _drop(kind, native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'text search inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

def _column(field_id, label, control='text', required=False, **extra):
    return {'field_id': field_id, 'label': label, 'control': control,
            'required': required, **extra}


def form(kind, operation, field):
    """Dialog fields; ids follow the inherited dialogs."""
    label = 'text search ' + KEYWORDS[kind].lower()
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': ['text_search_facts', key]} if alter \
            else {}
    mapping_columns = [_column('token', 'Token', required=True),
                       _column('dictname', 'Dictionaries (comma-separated)',
                               required=True)]
    option_columns = [_column('option', 'Option', required=True),
                      _column('value', 'Value', required=True)]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {label} name to confirm',
                        required=True)]
    else:
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('schema', 'Schema', required=not alter, **(
                      {'help': 'A different schema runs SET SCHEMA.'}
                      if alter else {}), **initial('schema'))]
        if kind in ('text-search-configuration', 'text-search-dictionary'):
            fields.append(field('owner', 'Owner', help=(
                'Empty keeps the owner.' if alter else 'OWNER TO')))
        if kind == 'text-search-configuration':
            if alter:
                fields += [field('add_mappings', 'Add mappings', 'grid',
                                 columns=mapping_columns),
                           field('alter_mappings', 'Alter mappings', 'grid',
                                 columns=mapping_columns),
                           field('drop_mappings', 'Drop mappings', 'grid',
                                 columns=[mapping_columns[0]])]
            else:
                fields += [field('prsname', 'Parser', help='PARSER ='),
                           field('copy_config', 'Copy config', help=(
                               'COPY = an existing configuration.')),
                           field('tokens', 'Mappings', 'grid',
                                 columns=mapping_columns)]
        elif kind == 'text-search-dictionary':
            if alter:
                fields += [field('set_options', 'Set options', 'grid',
                                 columns=option_columns),
                           field('drop_options', 'Drop options', 'grid',
                                 columns=[option_columns[0]])]
            else:
                fields += [field('template', 'Template', required=True),
                           field('options', 'Options', 'grid',
                                 columns=option_columns)]
        elif kind == 'text-search-parser':
            fields += [field(key, label_, required=(not alter and key !=
                                                     'prsheadline'),
                             help=('Changing a function drops and recreates '
                                   'the parser.' if alter else ''),
                             **initial(key))
                       for key, label_ in (
                           ('prsstart', 'Start function'),
                           ('prstoken', 'Get next token function'),
                           ('prsend', 'End function'),
                           ('prslextype', 'Lextypes function'),
                           ('prsheadline', 'Headline function'))]
        else:
            fields += [field('tmplinit', 'Init function', help=(
                           'Changing a function drops and recreates the '
                           'template.' if alter else ''),
                           **initial('tmplinit')),
                       field('tmpllexize', 'Lexize function',
                             required=not alter, **initial('tmpllexize'))]
        fields.append(field('description', 'Comment', 'multiline',
                            **initial('description')))
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields}
