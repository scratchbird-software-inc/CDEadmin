"""PostgreSQL views and materialized views on the provider tree (M4,
2026-11-11).

Views: CREATE [OR REPLACE] VIEW WITH (check_option, security_barrier,
security_invoker) AS query, ALTER VIEW RENAME TO / SET SCHEMA / SET | RESET
options, OWNER TO, COMMENT ON VIEW, DROP VIEW. Materialized views: CREATE
MATERIALIZED VIEW [USING method] [WITH (fillfactor)] [TABLESPACE] AS query
WITH [NO] DATA, ALTER MATERIALIZED VIEW RENAME TO / SET SCHEMA / SET
TABLESPACE / SET | RESET (fillfactor), OWNER TO, COMMENT, and a changed
definition as DROP and CREATE in one transaction (as the inherited dialog
does; the data is rebuilt). REFRESH is already provider-native
(``maintenance.py``). Field ids follow the inherited dialogs
(``view.ui.js``, ``mview.ui.js``); WITH CHECK OPTION, which YugabyteDB
refuses, is offered here.

The query is admitted only when PostgreSQL's own parser reads it as exactly
one SELECT (or VALUES / TABLE) statement with no separator or comment.
"""
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified,
)

CHECK_OPTIONS = ('no', 'local', 'cascaded')
VIEW_OPTIONS = ('security_barrier', 'security_invoker')
_ACCESS_METHOD = __import__('re').compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')


def _blank(value):
    return value is None or value == ''


def query(value, label='definition'):
    """One SELECT, admitted by PostgreSQL's own parser."""
    if not isinstance(value, str) or not value.strip():
        raise PostgreSQLNativeAdminError(f'{label} must not be empty')
    value = value.strip().rstrip(';').strip()
    if ';' in value or '--' in value or '/*' in value or '\x00' in value:
        raise PostgreSQLNativeAdminError(f'{label} contains unsafe syntax')
    from pglast import ast, parse_sql
    from pglast.parser import ParseError
    try:
        statements = parse_sql(value)
    except ParseError as exc:
        raise PostgreSQLNativeAdminError(
            f'{label} is not a valid query: {exc}') from None
    if len(statements) != 1 or not isinstance(statements[0].stmt,
                                              ast.SelectStmt):
        raise PostgreSQLNativeAdminError(f'{label} must be one SELECT')
    return value


def _options(reloptions):
    result = {}
    for item in reloptions or []:
        if isinstance(item, str) and '=' in item:
            key, value = item.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def facts(native):
    """Current values of a view or materialized view as the dialogs show
    them."""
    row = native.get('catalog_row') or {}
    options = _options(row.get('reloptions'))
    fillfactor = options.get('fillfactor')
    return {
        'name': native.get('name') or row.get('relname'),
        'schema': native.get('schema'),
        'definition': (native.get('definition') or '').strip().rstrip(';'),
        'check_option': options.get('check_option', 'no'),
        'security_barrier': options.get('security_barrier',
                                        'false').lower() == 'true',
        'security_invoker': options.get('security_invoker',
                                        'false').lower() == 'true',
        'with_data': bool(row.get('relispopulated', True)),
        'fillfactor': int(fillfactor) if fillfactor and
        fillfactor.isdigit() else None,
        'comment': native.get('comment'),
    }


def _keyword(kind):
    return 'VIEW' if kind == 'view' else 'MATERIALIZED VIEW'


def _view_options(draft, current=None):
    """The WITH (...) option values a view would carry after the draft."""
    option = draft.get('check_option')
    if _blank(option):
        option = current['check_option'] if current else 'no'
    option = str(option).lower()
    if option not in CHECK_OPTIONS:
        raise PostgreSQLNativeAdminError(
            'check option is no, local or cascaded')
    values = {'check_option': option}
    for key in VIEW_OPTIONS:
        if draft.get(key) is None:
            values[key] = current[key] if current else False
        else:
            values[key] = _flag(draft, key)
    return values


def _with_clause(values):
    parts = []
    if values['check_option'] != 'no':
        parts.append(f'check_option={values["check_option"]}')
    for key in VIEW_OPTIONS:
        if values[key]:
            parts.append(f'{key}=true')
    return ' WITH (' + ', '.join(parts) + ')' if parts else ''


def _fillfactor(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or \
            not 10 <= value <= 100:
        raise PostgreSQLNativeAdminError('fill factor is 10 to 100')
    return value


def _mview_head(qualified, draft, current=None):
    head = f'CREATE MATERIALIZED VIEW {qualified}'
    method = draft.get('amname')
    if not _blank(method):
        if not isinstance(method, str) or not _ACCESS_METHOD.fullmatch(
                method):
            raise PostgreSQLNativeAdminError(
                'access method is an access method name')
        head += f' USING {_identifier(method, "access method")}'
    fillfactor = draft.get('fillfactor')
    if _blank(fillfactor) and current is not None:
        fillfactor = current['fillfactor']
    if not _blank(fillfactor):
        head += f' WITH (fillfactor={_fillfactor(fillfactor)})'
    if not _blank(draft.get('spcname')):
        head += ' TABLESPACE ' + _identifier(draft['spcname'], 'tablespace')
    return head


def _with_data(draft, current=None):
    value = draft.get('with_data')
    if value is None:
        value = current['with_data'] if current else True
    return ' WITH DATA' if _flag({'with_data': value}, 'with_data') else \
        ' WITH NO DATA'


def _comment(kind, qualified, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON {_keyword(kind)} {qualified} IS {text}'


def _create(kind, draft):
    schema = _name(draft.get('schema'), 'schema')
    qualified = _qualified(schema, draft.get('name'))
    definition = query(draft.get('definition'))
    if kind == 'view':
        options = _with_clause(_view_options(draft))
        statement = f'CREATE VIEW {qualified}{options} AS {definition}'
    else:
        statement = (f'{_mview_head(qualified, draft)} AS {definition}'
                     f'{_with_data(draft)}')
    statements = [statement]
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER TABLE {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    if not _blank(draft.get('comment')):
        statements.append(_comment(kind, qualified, draft['comment']))
    return statements


def _alter(kind, native, draft):
    current = native.get('view_facts') or facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    keyword = _keyword(kind)
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER {keyword} {qualified} RENAME TO '
                          + _identifier(new_name, 'name'))
        name = new_name
        qualified = _qualified(schema, name)
    new_schema = draft.get('schema')
    if not _blank(new_schema) and new_schema != schema:
        statements.append(f'ALTER {keyword} {qualified} SET SCHEMA '
                          + _identifier(new_schema, 'schema'))
        schema = new_schema
        qualified = _qualified(schema, name)
    if not _blank(draft.get('owner')):
        statements.append(f'ALTER TABLE {qualified} OWNER TO '
                          + _identifier(draft['owner'], 'owner'))
    definition = draft.get('definition')
    changed = not _blank(definition) and query(definition) != current[
        'definition']
    if kind == 'view':
        wanted = _view_options(draft, current)
        if changed:
            statements.append(f'CREATE OR REPLACE VIEW {qualified}'
                              f'{_with_clause(wanted)} AS {query(definition)}')
        else:
            sets, resets = [], []
            if wanted['check_option'] != current['check_option']:
                (resets if wanted['check_option'] == 'no' else sets).append(
                    'check_option' if wanted['check_option'] == 'no' else
                    f'check_option={wanted["check_option"]}')
            for key in VIEW_OPTIONS:
                if wanted[key] != current[key]:
                    sets.append(f'{key}={"true" if wanted[key] else "false"}')
            if sets:
                statements.append(f'ALTER VIEW {qualified} SET ('
                                  + ', '.join(sets) + ')')
            if resets:
                statements.append(f'ALTER VIEW {qualified} RESET ('
                                  + ', '.join(resets) + ')')
    else:
        if changed:
            # As the inherited dialog: a materialized view's query cannot be
            # replaced in place; drop and create run in one transaction.
            statements.append(f'DROP MATERIALIZED VIEW {qualified}')
            head = _mview_head(qualified, draft, current)
            statements.append(f'{head} AS {query(definition)}'
                              f'{_with_data(draft, current)}')
        else:
            if not _blank(draft.get('spcname')):
                statements.append(f'ALTER MATERIALIZED VIEW {qualified} SET '
                                  'TABLESPACE ' + _identifier(
                                      draft['spcname'], 'tablespace'))
            # The dialog drops a cleared number, so the reset is a flag.
            if _flag(draft, 'reset_fillfactor'):
                if current['fillfactor'] is not None:
                    statements.append(f'ALTER MATERIALIZED VIEW {qualified} '
                                      'RESET (fillfactor)')
            elif not _blank(draft.get('fillfactor')) and \
                    draft['fillfactor'] != current['fillfactor']:
                statements.append(
                    f'ALTER MATERIALIZED VIEW {qualified} SET '
                    f'(fillfactor={_fillfactor(draft["fillfactor"])})')
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        statements.append(_comment(kind, qualified, draft['comment']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return statements


def _drop(kind, native, draft):
    current = native.get('view_facts') or facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return [f'DROP {_keyword(kind)} '
            f'{_qualified(current["schema"], name)}{cascade}']


def compile_operation(kind, operation, native, draft):
    """One exact native text for a view or materialized view lifecycle."""
    if operation == 'create':
        statements = _create(kind, draft)
    elif operation == 'alter':
        statements = _alter(kind, native, draft)
    elif operation == 'drop':
        statements = _drop(kind, native, draft)
    else:
        raise PostgreSQLNativeAdminError(
            'view inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(kind, operation, field):
    """Dialog fields; ids follow the inherited view dialogs."""
    label = 'view' if kind == 'view' else 'materialized view'
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {label} name to confirm',
                        required=True)]
    else:
        alter = operation == 'alter'

        def initial(key):
            return {'initial_value_path': ['view_facts', key]} if alter \
                else {}
        fields = [field('name', 'Name', required=not alter,
                        **initial('name')),
                  field('schema', 'Schema', required=not alter, **(
                      {'help': 'A different schema runs SET SCHEMA.'}
                      if alter else {}), **initial('schema')),
                  field('owner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO')),
                  field('comment', 'Comment', 'multiline',
                        **initial('comment')),
                  field('definition', 'Code', 'code', required=not alter,
                        help='One SELECT.' + (
                            ' A changed query runs CREATE OR REPLACE VIEW, '
                            'which may add columns at the end but not drop '
                            'or reorder them.'
                            if kind == 'view' and alter else
                            ' A changed query drops and recreates the '
                            'materialized view in one transaction.'
                            if alter else ''), **initial('definition'))]
        if kind == 'view':
            fields += [
                field('check_option', 'Check options', 'select', options=[
                    {'value': 'no', 'label': 'No'},
                    {'value': 'local', 'label': 'Local'},
                    {'value': 'cascaded', 'label': 'Cascaded'}],
                    **({} if alter else {'default': 'no'}),
                    **initial('check_option')),
                field('security_barrier', 'Security barrier', 'boolean',
                      **initial('security_barrier')),
                field('security_invoker', 'Security invoker', 'boolean',
                      help='PostgreSQL 15 and later.',
                      **initial('security_invoker'))]
        else:
            fields += [
                field('with_data', 'With data', 'boolean',
                      **({} if alter else {'default': True}),
                      **initial('with_data')),
                field('spcname', 'Tablespace'),
                field('fillfactor', 'Fill factor', 'number',
                      help='10 to 100.', **initial('fillfactor'))]
            if alter:
                fields.append(field('reset_fillfactor',
                                    'Reset the fill factor', 'boolean'))
            if not alter:
                fields.append(field('amname', 'Access method',
                                    help='USING; empty for the default.'))
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields,
            'notes': 'Privileges and security labels stay with the '
                     'inherited dialog.'}
