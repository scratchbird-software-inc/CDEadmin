"""PostgreSQL casts, collations and procedural languages on the provider
tree (M5, 2026-11-11).

Casts: CREATE CAST (source AS target) WITH FUNCTION f(args) | WITHOUT
FUNCTION | WITH INOUT [AS ASSIGNMENT | AS IMPLICIT], COMMENT ON CAST, DROP
CAST; a cast has no alter on the preserved surface (its comment is set at
creation), so the provider offers none either.
Collations: CREATE COLLATION schema.name (LOCALE | LC_COLLATE + LC_CTYPE,
PROVIDER, DETERMINISTIC, RULES, VERSION) or FROM another collation, owner,
comment; ALTER COLLATION RENAME TO / OWNER TO / SET SCHEMA / REFRESH
VERSION, COMMENT; a changed locale is drop and create, as the inherited
dialog does. Languages: CREATE [TRUSTED] [PROCEDURAL] LANGUAGE with HANDLER,
INLINE and VALIDATOR, or from the server's template, owner, comment; ALTER
LANGUAGE RENAME TO / OWNER TO, COMMENT; DROP LANGUAGE. Nondeterministic
collations, which YugabyteDB refuses, are offered here. Field ids follow
the inherited dialogs (``cast.ui.js``, ``collation.ui.js``,
``language.ui.js``).
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference, _type_list, _type_reference,
)

CAST_CONTEXTS = {'e': 'explicit', 'a': 'assignment', 'i': 'implicit'}
CAST_METHODS = {'f': 'function', 'b': 'binary', 'i': 'inout'}
PROVIDERS = {'i': 'icu', 'c': 'libc', 'b': 'builtin', 'd': 'default'}
_LOCALE = re.compile(r'[A-Za-z0-9_.@=;:/ -]{1,128}')
_VERSION = re.compile(r'[A-Za-z0-9_.+-]{1,64}')
_CAST_IDENTITY = re.compile(r'^\((.+) AS (.+)\)$')


def _blank(value):
    return value is None or value == ''


def _comment(keyword, target, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON {keyword} {target} IS {text}'


def _function_signature(value, label):
    """``schema.function(type, ...)`` for WITH FUNCTION."""
    if not isinstance(value, str) or '(' not in value or not value.strip(
    ).endswith(')'):
        raise PostgreSQLNativeAdminError(
            f'{label} is written name(argument types)')
    name, _, rest = value.strip().partition('(')
    arguments = [item.strip() for item in rest[:-1].split(',')
                 if item.strip()]
    return _reference(name.strip(), label) + _type_list(arguments, label)


# -- casts --------------------------------------------------------------------

def cast_facts(native):
    row = native.get('catalog_row') or {}
    identity = native.get('sql_identity') or ''
    match = _CAST_IDENTITY.match(identity)
    source, target = (match.group(1), match.group(2)) if match else (
        None, None)
    return {'name': native.get('name') or identity, 'srctyp': source,
            'trgtyp': target,
            'castcontext': CAST_CONTEXTS.get(row.get('castcontext'),
                                             'explicit'),
            'castmethod': CAST_METHODS.get(row.get('castmethod'),
                                           'function'),
            'description': native.get('comment')}


def _cast_target(current=None, draft=None):
    source = (draft or {}).get('srctyp') if current is None else current[
        'srctyp']
    target = (draft or {}).get('trgtyp') if current is None else current[
        'trgtyp']
    return (f'({_type_reference(source, "source type")} AS '
            f'{_type_reference(target, "target type")})')


def _cast_create(draft):
    target = _cast_target(draft=draft)
    method = str(draft.get('castmethod') or 'function').lower()
    if method == 'function':
        text = f'CREATE CAST {target} WITH FUNCTION ' + _function_signature(
            draft.get('proname'), 'function')
    elif method == 'binary':
        text = f'CREATE CAST {target} WITHOUT FUNCTION'
    elif method == 'inout':
        text = f'CREATE CAST {target} WITH INOUT'
    else:
        raise PostgreSQLNativeAdminError(
            'cast method is function, binary or inout')
    context = str(draft.get('castcontext') or 'explicit').lower()
    if context not in CAST_CONTEXTS.values():
        raise PostgreSQLNativeAdminError(
            'context is explicit, assignment or implicit')
    if context != 'explicit':
        text += f' AS {context.upper()}'
    statements = [text]
    if not _blank(draft.get('description')):
        statements.append(_comment('CAST', target, draft['description']))
    return statements


def _cast_alter(native, draft):
    raise PostgreSQLNativeAdminError(
        'a cast has no alter; drop and create it for another function, '
        'context or comment')


def _cast_drop(native, draft):
    current = native.get('cast_facts') or cast_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP CAST {_cast_target(current)}{cascade}']


# -- collations ---------------------------------------------------------------

def collation_facts(native):
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('collname'),
            'schema': native.get('schema'),
            'provider': PROVIDERS.get(row.get('collprovider'), 'libc'),
            'locale': row.get('colllocale'),
            'lc_collate': row.get('collcollate'),
            'lc_type': row.get('collctype'),
            'is_deterministic': bool(row.get('collisdeterministic', True)),
            'rules': row.get('collicurules'),
            'version': row.get('collversion'),
            'description': native.get('comment')}


def _locale(value, label):
    if not isinstance(value, str) or not _LOCALE.fullmatch(value):
        raise PostgreSQLNativeAdminError(f'{label} is a locale name')
    return _literal(value, label)


def _collation_options(draft):
    options = []
    copied = draft.get('copy_collation')
    if not _blank(copied):
        return ' FROM ' + _reference(copied, 'copied collation')
    locale = draft.get('locale')
    if not _blank(locale):
        options.append('LOCALE = ' + _locale(locale, 'locale'))
    elif not _blank(draft.get('lc_collate')) or not _blank(
            draft.get('lc_type')):
        if _blank(draft.get('lc_collate')) or _blank(draft.get('lc_type')):
            raise PostgreSQLNativeAdminError(
                'LC_COLLATE and LC_CTYPE go together')
        options.append('LC_COLLATE = ' + _locale(draft['lc_collate'],
                                                 'LC_COLLATE'))
        options.append('LC_CTYPE = ' + _locale(draft['lc_type'], 'LC_CTYPE'))
    else:
        raise PostgreSQLNativeAdminError(
            'a collation needs a locale, LC_COLLATE with LC_CTYPE, or a '
            'collation to copy')
    provider = str(draft.get('provider') or '').lower()
    if provider:
        if provider not in ('icu', 'libc', 'builtin'):
            raise PostgreSQLNativeAdminError(
                'provider is icu, libc or builtin')
        options.append(f'PROVIDER = {provider}')
    if draft.get('is_deterministic') is not None:
        options.append('DETERMINISTIC = ' + (
            'true' if _flag(draft, 'is_deterministic') else 'false'))
    if not _blank(draft.get('rules')):
        options.append('RULES = ' + _literal(str(draft['rules']), 'rules'))
    if not _blank(draft.get('version')):
        if not isinstance(draft['version'], str) or not _VERSION.fullmatch(
                draft['version']):
            raise PostgreSQLNativeAdminError('version is a version name')
        options.append('VERSION = ' + _literal(draft['version'], 'version'))
    return ' (' + ', '.join(options) + ')'


def _collation_create(draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    statements = [f'CREATE COLLATION {qualified}'
                  + _collation_options(draft)]
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER COLLATION {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('COLLATION', qualified,
                                   draft['description']))
    return statements


def _collation_alter(native, draft):
    current = native.get('collation_facts') or collation_facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    redefined = any(not _blank(draft.get(key)) and draft[key] != current.get(
        key) for key in ('locale', 'lc_collate', 'lc_type')) or not _blank(
        draft.get('copy_collation'))
    if redefined:
        # As the inherited dialog: a collation's locale cannot change in
        # place; drop and create run in one transaction.
        statements.append(f'DROP COLLATION {qualified}')
        statements.append(f'CREATE COLLATION {qualified}'
                          + _collation_options({**current, **{
                              key: value for key, value in draft.items()
                              if value is not None}}))
    if _flag(draft, 'refresh_version'):
        statements.append(f'ALTER COLLATION {qualified} REFRESH VERSION')
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER COLLATION {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('COLLATION', qualified,
                                   draft['description']))
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER COLLATION {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        qualified = _qualified(schema, new_name)
    new_schema = draft.get('schema')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER COLLATION {qualified} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _collation_drop(native, draft):
    current = native.get('collation_facts') or collation_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP COLLATION {_qualified(current["schema"], name)}{cascade}']


# -- languages ----------------------------------------------------------------

def language_facts(native):
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('lanname'),
            'trusted': bool(row.get('lanpltrusted', False)),
            'is_procedural': bool(row.get('lanispl', False)),
            'description': native.get('comment')}


def _language_create(draft):
    name = _identifier(draft.get('name'), 'name')
    if _flag(draft, 'is_template'):
        # The server's pg_pltemplate-style built-in template (plpgsql,
        # plperl, ...) supplies the handlers.
        text = f'CREATE LANGUAGE {name}'
    else:
        text = 'CREATE ' + ('TRUSTED ' if _flag(draft, 'trusted') else '') \
            + f'PROCEDURAL LANGUAGE {name} HANDLER ' + _reference(
                draft.get('lanproc'), 'handler function')
        if not _blank(draft.get('laninl')):
            text += ' INLINE ' + _reference(draft['laninl'],
                                            'inline function')
        if not _blank(draft.get('lanval')):
            text += ' VALIDATOR ' + _reference(draft['lanval'],
                                               'validator function')
    statements = [text]
    if not _blank(draft.get('lanowner')):
        statements.append(f'ALTER LANGUAGE {name} OWNER TO '
                          + _identifier(draft['lanowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('LANGUAGE', name, draft['description']))
    return statements


def _language_alter(native, draft):
    current = native.get('language_facts') or language_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    statements = []
    if not _blank(draft.get('lanowner')):
        statements.append(f'ALTER LANGUAGE {quoted} OWNER TO '
                          + _identifier(draft['lanowner'], 'owner'))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('LANGUAGE', quoted, draft['description']))
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER LANGUAGE {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
    if not statements:
        raise PostgreSQLNativeAdminError(
            'nothing to change; handlers and trust are fixed once created')
    return statements


def _language_drop(native, draft):
    current = native.get('language_facts') or language_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP LANGUAGE {_identifier(name, "name")}{cascade}']


# -- dispatch -----------------------------------------------------------------

_COMPILERS = {
    'cast': (_cast_create, _cast_alter, _cast_drop),
    'collation': (_collation_create, _collation_alter, _collation_drop),
    'language': (_language_create, _language_alter, _language_drop),
}
FACTS = {'cast': ('cast_facts', cast_facts),
         'collation': ('collation_facts', collation_facts),
         'language': ('language_facts', language_facts)}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a cast, collation or language."""
    create, alter, drop = _COMPILERS[kind]
    if operation == 'create':
        statements = create(draft)
    elif operation == 'alter':
        statements = alter(native, draft)
    elif operation == 'drop':
        statements = drop(native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            f'{kind} inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- forms --------------------------------------------------------------------

def form(kind, operation, field):
    """Dialog fields; ids follow the inherited dialogs."""
    facts_key = FACTS[kind][0]
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': [facts_key, key]} if alter else {}
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {kind} name to confirm',
                        required=True)]
    elif kind == 'cast':
        if alter:
            raise PostgreSQLNativeAdminError('a cast has no alter')
        else:
            fields = [
                field('srctyp', 'Source type', required=True),
                field('trgtyp', 'Target type', required=True),
                field('castmethod', 'Method', 'select', options=[
                    {'value': 'function', 'label': 'With function'},
                    {'value': 'binary', 'label': 'Binary coercible '
                                                 '(without function)'},
                    {'value': 'inout', 'label': 'With I/O conversion '
                                                '(INOUT)'}],
                    default='function'),
                field('proname', 'Function', help=(
                    'schema.function(argument types)')),
                field('castcontext', 'Context', 'select', options=[
                    {'value': 'explicit', 'label': 'Explicit'},
                    {'value': 'assignment', 'label': 'Assignment'},
                    {'value': 'implicit', 'label': 'Implicit'}],
                    default='explicit'),
                field('description', 'Comment', 'multiline')]
    elif kind == 'collation':
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('schema', 'Schema', required=not alter, **(
                      {'help': 'A different schema runs SET SCHEMA.'}
                      if alter else {}), **initial('schema')),
                  field('owner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO')),
                  field('copy_collation', 'Copy collation', help=(
                      'FROM an existing collation; other definition fields '
                      'are then ignored.')),
                  field('provider', 'Provider', 'select', options=[
                      {'value': 'icu', 'label': 'icu'},
                      {'value': 'libc', 'label': 'libc'},
                      {'value': 'builtin', 'label': 'builtin'}],
                      **initial('provider')),
                  field('locale', 'Locale', **initial('locale')),
                  field('lc_collate', 'LC_COLLATE', **initial('lc_collate')),
                  field('lc_type', 'LC_CTYPE', **initial('lc_type')),
                  field('is_deterministic', 'Deterministic', 'boolean',
                        **({} if alter else {'default': True}),
                        **initial('is_deterministic')),
                  field('rules', 'Rules', help='ICU rules.',
                        **initial('rules')),
                  field('version', 'Version', **initial('version')),
                  field('description', 'Comment', 'multiline',
                        **initial('description'))]
        if alter:
            fields.append(field('refresh_version', 'Refresh version',
                                'boolean'))
    else:
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('lanowner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO'))]
        if not alter:
            fields += [
                field('is_template', 'From the server template', 'boolean',
                      help='CREATE LANGUAGE name alone, for languages the '
                           'server knows (plpgsql, plperl, plpython3u, '
                           'pltcl).'),
                field('trusted', 'Trusted', 'boolean'),
                field('lanproc', 'Handler function',
                      help='Required unless from the template.'),
                field('laninl', 'Inline function'),
                field('lanval', 'Validator function')]
        fields.append(field('description', 'Comment', 'multiline',
                            **initial('description')))
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:database:{kind}',
            'title': f'{operation.title()} {kind}', 'fields': fields,
            'notes': 'A changed collation locale drops and recreates the '
                     'collation; a language\'s handlers and trust are fixed '
                     'once created; privileges stay with the inherited '
                     'dialog.'}
