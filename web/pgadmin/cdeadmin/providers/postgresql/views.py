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

Owner direction 2026-11-11: every field of the view family form is
admitted and compiled: privileges (stated, revoked through a grid),
security labels, a materialized view's TOAST tuple target, autovacuum
settings, access method and extension dependencies; the owner, tablespace
and access method are facts.
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
    from . import tables as table_editor  # tables imports _options: lazy
    row = native.get('catalog_row') or {}
    options = _options(row.get('reloptions'))
    fillfactor = options.get('fillfactor')
    autovacuum = {key: value for key, value in options.items()
                  if key in table_editor.AUTOVACUUM}
    toast = {key[6:]: value for key, value in options.items()
             if key.startswith('toast.')
             and key[6:] in table_editor.AUTOVACUUM}

    def number(key):
        value = options.get(key)
        return int(value) if isinstance(value, str) and value.isdigit() \
            else None

    def enabled(settings):
        return {'true': 't', 'false': 'f'}.get(
            str(settings.get('autovacuum_enabled', '')).lower(), 'x')
    return {
        'name': native.get('name') or row.get('relname'),
        'schema': native.get('schema'),
        'owner': native.get('owner') or row.get('owner_name'),
        'definition': (native.get('definition') or '').strip().rstrip(';'),
        'check_option': options.get('check_option', 'no'),
        'security_barrier': options.get('security_barrier',
                                        'false').lower() == 'true',
        'security_invoker': options.get('security_invoker',
                                        'false').lower() == 'true',
        'with_data': bool(row.get('relispopulated', True)),
        'fillfactor': int(fillfactor) if fillfactor and
        fillfactor.isdigit() else None,
        'spcname': native.get('tablespace') or row.get('tablespace_name'),
        'amname': row.get('access_method_name'),
        'toast_tuple_target': number('toast_tuple_target'),
        'autovacuum_enabled': enabled(autovacuum),
        'autovacuum_custom': bool(autovacuum),
        'vacuum_settings': autovacuum,
        'toast_autovacuum_enabled': enabled(toast),
        'toast_autovacuum': bool(toast),
        'toast_vacuum_settings': toast,
        'datacl': list(row.get('relacl') or []),
        'dependsonextensions': list(
            native.get('depends_on_extensions') or []),
        'comment': native.get('comment'),
    }


def _storage_changes(draft, current):
    """(sets, resets) of a materialized view's storage parameters from the
    dialog: fill factor, TOAST tuple target and the autovacuum grids."""
    from . import tables as table_editor
    sets, resets = [], []
    if _flag(draft, 'reset_fillfactor') if 'reset_fillfactor' in draft \
            else False:
        if current is None or current['fillfactor'] is not None:
            resets.append('fillfactor')
    elif not _blank(draft.get('fillfactor')) and (
            current is None or draft['fillfactor'] != current['fillfactor']):
        sets.append(f'fillfactor={_fillfactor(draft["fillfactor"])}')
    if not _blank(draft.get('toast_tuple_target')) and (
            current is None or
            draft['toast_tuple_target'] != current['toast_tuple_target']):
        sets.append('toast_tuple_target='
                    + str(table_editor._number(draft['toast_tuple_target'],
                                               'toast_tuple_target')))
    for prefix, flag, grid, enabled_key, settings_key in (
            ('', 'autovacuum_custom', 'vacuum_table', 'autovacuum_enabled',
             'vacuum_settings'),
            ('toast.', 'toast_autovacuum', 'vacuum_toast',
             'toast_autovacuum_enabled', 'toast_vacuum_settings')):
        held = current[settings_key] if current else {}
        enabled = draft.get(enabled_key)
        if enabled in ('t', 'f') and (current is None or enabled !=
                                      current[enabled_key]):
            sets.append(f'{prefix}autovacuum_enabled='
                        + ('true' if enabled == 't' else 'false'))
        elif enabled == 'x' and current and current[enabled_key] != 'x':
            resets.append(f'{prefix}autovacuum_enabled')
        if flag in draft:
            if _flag(draft, flag):
                for name, value in table_editor._autovacuum_rows(draft,
                                                                 grid):
                    if held.get(name) != value:
                        sets.append(f'{prefix}{name}={value}')
            elif held:
                resets.extend(f'{prefix}{name}' for name in held
                              if name != 'autovacuum_enabled')
    return sets, resets


def _grants(kind, qualified, draft, alter):
    """Grants, revocations, labels and extension dependencies; stated,
    never diffed."""
    from . import tables as table_editor
    statements = []
    if alter:
        for row in table_editor._rows(draft, 'revoke'):
            statements.append(f'REVOKE ALL ON TABLE {qualified} FROM '
                              + table_editor._grantee(row.get('grantee')))
    for row in table_editor._rows(draft, 'datacl'):
        statements.append(table_editor._grant(qualified, row))
    for row in table_editor._rows(draft, 'seclabels'):
        statements.append(table_editor._label(qualified, row).replace(
            ' ON TABLE ', f' ON {_keyword(kind)} ', 1))
    value = draft.get('dependsonextensions')
    if value not in (None, '', []):
        if kind == 'view':
            raise PostgreSQLNativeAdminError(
                'only a materialized view can depend on an extension')
        if not isinstance(value, list):
            raise PostgreSQLNativeAdminError('extensions must be a list')
        for item in value:
            name = item.get('name') if isinstance(item, dict) else item
            statements.append(f'ALTER MATERIALIZED VIEW {qualified} DEPENDS '
                              'ON EXTENSION ' + _identifier(name, 'extension'))
    return statements


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
    # The storage parameters the view will carry: the current ones (on a
    # recreate) under the dialog's changes.
    options = {}
    if current is not None:
        for key, value in (current.get('_reloptions') or {}).items():
            options[key] = value
    sets, resets = _storage_changes(draft, current)
    for item in sets:
        key, _eq, value = item.partition('=')
        options[key] = value
    for key in resets:
        options.pop(key, None)
    if options:
        head += ' WITH (' + ', '.join(f'{key}={value}' for key, value
                                      in options.items()) + ')'
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
    statements.extend(_grants(kind, qualified, draft, False))
    return statements


def _alter(kind, native, draft):
    current = native.get('view_facts') or facts(native)
    current = dict(current, _reloptions=_options(
        (native.get('catalog_row') or {}).get('reloptions')))
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
    if not _blank(draft.get('owner')) and draft['owner'] != current.get(
            'owner'):
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
            if not _blank(draft.get('spcname')) and \
                    draft['spcname'] != current.get('spcname'):
                statements.append(f'ALTER MATERIALIZED VIEW {qualified} SET '
                                  'TABLESPACE ' + _identifier(
                                      draft['spcname'], 'tablespace'))
            if not _blank(draft.get('amname')) and \
                    draft['amname'] != current.get('amname'):
                if current.get('amname') is None:
                    raise PostgreSQLNativeAdminError(
                        'the access method of this view is not known to '
                        'the listing; refresh before changing it')
                statements.append(f'ALTER MATERIALIZED VIEW {qualified} SET '
                                  'ACCESS METHOD ' + _identifier(
                                      draft['amname'], 'access method'))
            # The dialog drops a cleared number, so the reset is a flag.
            sets, resets = _storage_changes(draft, current)
            if sets:
                statements.append(f'ALTER MATERIALIZED VIEW {qualified} SET ('
                                  + ', '.join(sets) + ')')
            if resets:
                statements.append(f'ALTER MATERIALIZED VIEW {qualified} '
                                  'RESET (' + ', '.join(resets) + ')')
    if 'comment' in draft and (draft['comment'] or None) != (
            current['comment'] or None):
        statements.append(_comment(kind, qualified, draft['comment']))
    statements.extend(_grants(kind, qualified, draft, True))
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


# The family form's field ids (view.form.json: the view and materialized
# view variants) plus the provider's reset flag and revoke grid; the
# validator admits exactly these.
_FAMILY_FIELDS = (
    'variant', 'name', 'oid', 'owner', 'schema', 'system_view', 'comment',
    'security_barrier', 'security_invoker', 'check_option', 'with_data',
    'spcname', 'amname', 'fillfactor', 'toast_tuple_target',
    'dependsonextensions', 'vacuum_settings_str', 'definition',
    'autovacuum_custom', 'autovacuum_enabled', 'vacuum_table',
    'toast_autovacuum', 'toast_autovacuum_enabled', 'vacuum_toast', 'acl',
    'datacl', 'seclabels')
_GRIDS = ('vacuum_table', 'vacuum_toast', 'datacl', 'seclabels', 'revoke',
          'dependsonextensions')
_BOOLEANS = ('system_view', 'security_barrier', 'security_invoker',
             'with_data', 'autovacuum_custom', 'toast_autovacuum',
             'reset_fillfactor')
_NUMBERS = ('fillfactor', 'toast_tuple_target')
_TRI = [{'value': 'x', 'label': 'Not set'}, {'value': 't', 'label': 'Yes'},
        {'value': 'f', 'label': 'No'}]


def form(kind, operation, field):
    """The validator's view of the view family form: every field id the
    dialog sends, typed loosely; the family form file carries the labels,
    tabs, options and grid columns."""
    label = 'view' if kind == 'view' else 'materialized view'
    if operation == 'drop':
        return {'form_id': f'postgresql-{kind}-drop',
                'form_key': f'native:postgresql:schema:{kind}',
                'title': f'Drop {label}', 'fields': [
                    field('cascade', 'Drop dependent objects', 'boolean'),
                    field('confirmation', f'Type the {label} name to confirm',
                          required=True)]}
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': ['view_facts', key]} if alter else {}
    fields = []
    for field_id in _FAMILY_FIELDS + (('reset_fillfactor', 'revoke')
                                      if alter else ()):
        title = field_id.replace('_', ' ').capitalize()
        if field_id in _GRIDS:
            fields.append(field(field_id, title, 'grid', columns=[],
                                **initial(field_id)))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, title, 'boolean',
                                **initial(field_id)))
        elif field_id in _NUMBERS:
            fields.append(field(field_id, title, 'number',
                                **initial(field_id)))
        elif field_id == 'check_option':
            fields.append(field(field_id, 'Check options', 'select', options=[
                {'value': item, 'label': item.title()}
                for item in CHECK_OPTIONS], **initial(field_id)))
        elif field_id in ('autovacuum_enabled', 'toast_autovacuum_enabled'):
            fields.append(field(field_id, title, 'select', options=_TRI,
                                **initial(field_id)))
        elif field_id == 'definition':
            fields.append(field(field_id, 'Code', 'code', required=not alter,
                                **initial(field_id)))
        else:
            fields.append(field(field_id, title,
                                required=field_id in ('name', 'schema')
                                and not alter, **initial(field_id)))
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:schema:{kind}',
            'title': f'{operation.title()} {label}', 'fields': fields,
            'notes': ('A changed query runs CREATE OR REPLACE VIEW, or drops '
                      'and recreates a materialized view in one transaction. '
                      'Privileges and labels are stated; the Revoke grid '
                      'removes privileges; the fill factor is reset through '
                      'its flag.')}
