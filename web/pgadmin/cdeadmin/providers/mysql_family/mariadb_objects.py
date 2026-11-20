"""MariaDB standalone view, procedure, function and trigger create/alter/replace.

Provides reviewed native compilers and owned-connection execution for:
- view: CREATE VIEW, ALTER VIEW, CREATE OR REPLACE VIEW (with ALGORITHM,
  DEFINER, SQL SECURITY, column aliases and WITH [LOCAL|CASCADED] CHECK OPTION)
- procedure & function: CREATE, ALTER (characteristics without body replacement),
  and CREATE OR REPLACE (full signature/IN/OUT/INOUT/body/definer/SQL_MODE
  including sql_mode='ORACLE' PL/SQL routines), observing dependent views and
  mysql.procs_priv routine grants
- trigger: CREATE, ALTER and CREATE OR REPLACE preserving FOLLOWS/PRECEDES
  sibling ordering and stored SQL_MODE, supporting MariaDB 12.0.1+ multi-event
  triggers.
"""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re

from ...data_studio.language_tools import analyze
from ...sdk import RelationalClientError
from ..mysql_view_identity import declared_aliases
from ..mysql_views import _account_part
from .mariadb_catalog import identifier as quote_identifier
from .mariadb_server_diagnostics import environment
from .mysql_engine_diagnostics import observer_route, release
from .mysql_indexes import executable_comment, structural_definition, utf8_length

KEY = 'mariadb_object_change'

VIEW_ALGORITHMS = ('UNDEFINED', 'MERGE', 'TEMPTABLE')
VIEW_SECURITY = ('DEFINER', 'INVOKER')
VIEW_CHECK = ('NONE', 'LOCAL', 'CASCADED')

ROUTINE_ACCESS = ('CONTAINS SQL', 'NO SQL', 'READS SQL DATA', 'MODIFIES SQL DATA')
ROUTINE_ALTER_ACCESS = ('UNCHANGED', *ROUTINE_ACCESS)
ROUTINE_SECURITY = ('DEFINER', 'INVOKER')
ROUTINE_ALTER_SECURITY = ('UNCHANGED', *ROUTINE_SECURITY)

TRIGGER_TIMINGS = ('BEFORE', 'AFTER')
TRIGGER_EVENTS = ('INSERT', 'UPDATE', 'DELETE')
TRIGGER_ORDERS = ('NONE', 'FOLLOWS', 'PRECEDES')


def identifier(value):
    try:
        if isinstance(value, str):
            value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native MariaDB identifier must be nonempty text without NUL') from None


def _text(value, label, maximum=65535):
    if not isinstance(value, str) or '\x00' in value or utf8_length(value) > maximum:
        raise RelationalClientError(f'{label} requires bounded UTF-8 text without NUL')
    return value


def _native_facts(target):
    if not isinstance(target, Mapping):
        return {}
    native = target.get('native')
    if isinstance(native, Mapping):
        return native
    ext = (target.get('extensions') or {}).get('mariadb')
    return ext.get('native') if isinstance(ext, Mapping) and isinstance(ext.get('native'), Mapping) else {}


def _validate_sql_mode(mode_value):
    if mode_value in (None, ''):
        return None
    if not isinstance(mode_value, str) or '\x00' in mode_value or len(mode_value) > 512:
        raise RelationalClientError('SQL mode must be bounded text without NUL')
    tokens = [part.strip().upper() for part in mode_value.split(',') if part.strip()]
    if any(not re.fullmatch(r'[A-Z0-9_]+', token) for token in tokens):
        raise RelationalClientError('SQL mode contains invalid mode flags')
    return ','.join(tokens)


def _safe_type(value):
    text = _text(value, 'Routine type', 4096).strip()
    if not text or any(bad in text for bad in (';', '--', '/*', '*/', '#')):
        raise RelationalClientError('Routine data type contains invalid SQL boundary tokens')
    if text.count('(') != text.count(')'):
        raise RelationalClientError('Routine data type has unbalanced parentheses')
    if not re.match(r'^[A-Za-z][A-Za-z0-9_ ]*(?:\([^)]*\))?[A-Za-z0-9_ ]*$', text):
        raise RelationalClientError('Select a valid MariaDB routine data type')
    return text


def compile_view(operation, draft, target):
    if operation not in {'create', 'alter', 'create_or_replace'} or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a MariaDB view operation')
    draft = deepcopy(dict(draft))
    options = draft.pop('options', {})
    if isinstance(options, Mapping):
        for k, v in options.items():
            draft.setdefault(k, v)
    for alias, canonical in (('query', 'definition'), ('parent', 'database'), ('column_aliases', 'columns')):
        if alias in draft:
            if canonical in draft and draft[canonical] != draft[alias]:
                raise RelationalClientError(f'Conflicting MariaDB view field: {canonical}')
            draft[canonical] = draft.pop(alias)

    allowed = {
        'confirmation', 'definition', 'columns', 'algorithm', 'sql_security',
        'check_option', 'definer_mode', 'definer_user', 'definer_host', 'or_replace',
    }
    if operation == 'create':
        allowed |= {'name', 'database'}
        db_val = draft.get('database')
        if isinstance(db_val, list) and len(db_val) == 1:
            db_val = db_val[0]
        path = [db_val, draft.get('name')] if db_val else [draft.get('name')]
    else:
        if not isinstance(target, Mapping) or target.get('resource_kind') != 'view':
            raise RelationalClientError('Select an existing MariaDB view')
        path = target.get('display_path')
        if not isinstance(path, list) or len(path) != 2:
            raise RelationalClientError('Exact MariaDB database and view identity is required')
        if operation == 'create_or_replace' and draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact MariaDB view name for CREATE OR REPLACE VIEW')
        current = _native_facts(target)
        for option, key in (
            ('definition', 'view_definition'),
            ('columns', 'view_aliases'),
            ('algorithm', 'algorithm'),
            ('sql_security', 'sql_security'),
            ('check_option', 'check_option'),
        ):
            if option not in draft and current.get(key) not in (None, ''):
                draft[option] = current[key]
        if (
            'definer_user' not in draft
            and 'definer_host' not in draft
            and current.get('definer_user') not in (None, '')
            and current.get('definer_host') not in (None, '')
        ):
            draft['definer_user'] = current['definer_user']
            draft['definer_host'] = current['definer_host']

    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB view option: ' + ', '.join(sorted(set(draft) - allowed)))
    if not isinstance(path, list) or not 1 <= len(path) <= 2 or any(not p for p in path):
        raise RelationalClientError('Exact MariaDB view identity is required')

    qualified = '.'.join(identifier(part) for part in path)
    query = draft.get('definition')
    if not isinstance(query, str) or not re.match(r'^\s*(SELECT|WITH|VALUES)\b', query, re.I) or '\x00' in query:
        raise RelationalClientError('MariaDB view query must begin with SELECT, WITH or VALUES')
    parsed = analyze(query, 'mariadb-sql', script=True, settings={'no_backslash_escapes': False})
    if parsed['diagnostics'] or len(parsed['statements']) != 1 or executable_comment(query, ''):
        raise RelationalClientError('MariaDB view definition requires a single lexically complete query')
    clean_query = parsed['statements'][0]['source']

    algorithm = draft.get('algorithm') or 'UNDEFINED'
    security = draft.get('sql_security') or 'DEFINER'
    check = draft.get('check_option') or 'NONE'
    if algorithm not in VIEW_ALGORITHMS or security not in VIEW_SECURITY or check not in VIEW_CHECK:
        raise RelationalClientError('Select valid MariaDB view ALGORITHM, SQL SECURITY and CHECK OPTION values')

    raw_cols = draft.get('columns') or []
    if not isinstance(raw_cols, list) or len(raw_cols) > 4096:
        raise RelationalClientError('View column aliases must be an ordered list')
    cols = [
        row.get('value') if isinstance(row, Mapping) and set(row) <= {'value', '_id'} else row
        for row in raw_cols
    ]
    if any(not isinstance(c, str) or not c for c in cols) or len(set(cols)) != len(cols):
        raise RelationalClientError('View column aliases require distinct nonempty names')

    def_mode = draft.get('definer_mode')
    if def_mode not in (None, '', 'OMIT', 'CURRENT_USER', 'ACCOUNT'):
        raise RelationalClientError('Select OMIT, CURRENT_USER or ACCOUNT for MariaDB definer_mode')
    or_replace = operation == 'create_or_replace' or (operation == 'create' and bool(draft.get('or_replace')))
    verb = 'ALTER' if operation == 'alter' else ('CREATE OR REPLACE' if or_replace else 'CREATE')
    source = f'{verb} ALGORITHM={algorithm}'
    if def_mode == 'CURRENT_USER':
        source += ' DEFINER=CURRENT_USER'
    elif def_mode != 'OMIT' and (draft.get('definer_user') or draft.get('definer_host')):
        source += f" DEFINER={_account_part(draft.get('definer_user'), 80)}@{_account_part(draft.get('definer_host'), 255)}"
    source += f' SQL SECURITY {security} VIEW {qualified}'
    if cols:
        source += ' (' + ', '.join(identifier(c) for c in cols) + ')'
    source += f' AS {clean_query}\n'
    if check != 'NONE':
        source += f'WITH {check} CHECK OPTION'

    return {
        'statements': [{'source': source.strip(), 'parameters': ()}],
        KEY: {
            'kind': 'view',
            'operation': operation,
            'path': [str(p) for p in path],
            'draft': draft,
        },
        'warnings': [
            'MariaDB view DDL commits implicitly on an independently owned connection.',
            'Changing output columns can invalidate dependent views or stored routines at invocation time.',
        ],
    }


def compile_routine(kind, operation, draft, target):
    if kind not in {'procedure', 'function'} or operation not in {'create', 'alter', 'create_or_replace'}:
        raise RelationalClientError('Select a MariaDB stored routine operation')
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Routine properties must be an object')
    draft = deepcopy(dict(draft))
    options = draft.pop('options', {})
    if isinstance(options, Mapping):
        for k, v in options.items():
            draft.setdefault(k, v)
    changes = draft.pop('changes', {})
    if operation == 'alter' and isinstance(changes, Mapping):
        for k, v in changes.items():
            draft.setdefault(k, v)

    if operation == 'alter':
        if not isinstance(target, Mapping) or target.get('resource_kind') != kind:
            raise RelationalClientError(f'Select an existing MariaDB {kind}')
        path = target.get('display_path')
        if not isinstance(path, list) or len(path) != 2:
            raise RelationalClientError(f'Exact MariaDB database and {kind} identity is required')
        allowed = {'sql_security', 'data_access', 'comment', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError(
                f'ALTER {kind.upper()} modifies characteristics only (sql_security, data_access, comment); '
                f'use create_or_replace to replace body or parameters'
            )
        if 'confirmation' in draft and draft['confirmation'] != target.get('display_name'):
            raise RelationalClientError(f'Confirm the exact MariaDB {kind} name')
        clauses = []
        parameters = []
        sec = draft.get('sql_security', 'UNCHANGED')
        acc = draft.get('data_access', 'UNCHANGED')
        if sec not in ROUTINE_ALTER_SECURITY or acc not in ROUTINE_ALTER_ACCESS:
            raise RelationalClientError('Select valid MariaDB routine SQL SECURITY and data access characteristics')
        if sec != 'UNCHANGED':
            clauses.append(f'SQL SECURITY {sec}')
        if acc != 'UNCHANGED':
            clauses.append(acc)
        if 'comment' in draft and draft['comment'] is not None:
            comment = _text(draft['comment'], 'Routine comment', 65535)
            clauses.append('COMMENT %s')
            parameters.append(comment)
        if not clauses:
            raise RelationalClientError('Select at least one MariaDB routine characteristic to alter')
        qualified = '.'.join(identifier(p) for p in path)
        sql = f"ALTER {kind.upper()} {qualified} {' '.join(clauses)}"
        return {
            'statements': [{'source': sql, 'parameters': tuple(parameters)}],
            KEY: {
                'kind': kind,
                'operation': 'alter',
                'path': [str(path[0]), str(path[1])],
                'sql_mode': None,
                'draft': draft,
            },
            'warnings': [
                f'MariaDB ALTER {kind.upper()} updates routine characteristics in place without replacing the routine body or dropping routine grants.',
            ],
        }

    for alias, canonical in (('definition', 'body'), ('parent', 'database')):
        if alias in draft:
            if canonical in draft and draft[canonical] != draft[alias]:
                raise RelationalClientError(f'Conflicting MariaDB routine field: {canonical}')
            draft[canonical] = draft.pop(alias)

    if 'return_parameters' in draft:
        ret_params = draft.pop('return_parameters')
        if ret_params not in (None, [], ()):
            raise RelationalClientError('MariaDB routines use OUT/INOUT parameters or scalar RETURNS, not return_parameters')

    allowed = {
        'name', 'database', 'body', 'parameters', 'returns', 'deterministic',
        'data_access', 'sql_security', 'definer_mode', 'definer_user', 'definer_host', 'comment',
        'if_not_exists', 'or_replace', 'sql_mode', 'aggregate', 'confirmation',
    }
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB routine option: ' + ', '.join(sorted(set(draft) - allowed)))

    if operation == 'create_or_replace':
        if not isinstance(target, Mapping) or target.get('resource_kind') != kind:
            raise RelationalClientError(f'Select an existing MariaDB {kind} to replace')
        path = target.get('display_path')
        if not isinstance(path, list) or len(path) != 2:
            raise RelationalClientError(f'Exact MariaDB database and {kind} identity is required')
        if draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError(f'Confirm the exact MariaDB {kind} name for CREATE OR REPLACE')
        current = _native_facts(target)
        for opt, cur_key in (
            ('body', 'body'),
            ('parameters', 'parameters'),
            ('returns', 'returns'),
            ('sql_data_access', 'data_access'),
            ('security_type', 'sql_security'),
            ('comment', 'comment'),
            ('sql_mode', 'sql_mode'),
        ):
            target_field = cur_key if opt in {'sql_data_access', 'security_type'} else opt
            source_field = opt if opt in {'sql_data_access', 'security_type'} else cur_key
            if target_field not in draft and current.get(source_field) not in (None, ''):
                draft[target_field] = current[source_field]
        if 'deterministic' not in draft:
            cur_det = current.get('deterministic')
            if cur_det in ('DETERMINISTIC', 'NOT DETERMINISTIC'):
                draft['deterministic'] = cur_det
            elif isinstance(cur_det, bool):
                draft['deterministic'] = 'DETERMINISTIC' if cur_det else 'NOT DETERMINISTIC'
    else:
        db_val = draft.get('database')
        if isinstance(db_val, list) and len(db_val) == 1:
            db_val = db_val[0]
        path = [db_val, draft.get('name')] if db_val else [draft.get('name')]
        if any(not p for p in path):
            raise RelationalClientError(f'MariaDB {kind} name is required')

    sql_mode = _validate_sql_mode(draft.get('sql_mode'))
    oracle_mode = sql_mode is not None and 'ORACLE' in sql_mode.split(',')
    qualified = '.'.join(identifier(part) for part in path)

    params = draft.get('parameters') or []
    if not isinstance(params, list) or len(params) > 1024:
        raise RelationalClientError('Routine parameters must be an ordered list')
    declarations = []
    for item in params:
        if not isinstance(item, Mapping) or set(item) - {'name', 'type', 'mode', '_id'}:
            raise RelationalClientError('Routine parameter accepts name, type and mode')
        explicit_mode = item.get('mode')
        p_mode = str(explicit_mode or 'IN').upper()
        if p_mode not in {'IN', 'OUT', 'INOUT'}:
            raise RelationalClientError('Routine parameter mode must be IN, OUT or INOUT')
        if kind == 'function' and p_mode != 'IN' and not oracle_mode:
            raise RelationalClientError('Standard SQL MariaDB functions accept IN parameters only')
        p_name = identifier(item.get('name'))
        p_type = _safe_type(item.get('type'))
        if oracle_mode:
            mode_kw = f' {p_mode}' if (kind == 'procedure' and explicit_mode not in (None, '') or p_mode != 'IN') else ''
            declarations.append(f'{p_name}{mode_kw} {p_type}')
        else:
            prefix_mode = f'{p_mode} ' if (kind == 'procedure' and explicit_mode not in (None, '')) else ''
            declarations.append(f'{prefix_mode}{p_name} {p_type}')

    body = _text(draft.get('body'), 'Routine body', 1024 * 1024).strip()
    if not body:
        raise RelationalClientError('Routine body is required')
    if executable_comment(body, sql_mode or ''):
        raise RelationalClientError('Executable comments are not admitted in structured routine bodies')

    or_replace = operation == 'create_or_replace' or bool(draft.get('or_replace'))
    if_not_exists = bool(draft.get('if_not_exists', False))
    if or_replace and if_not_exists:
        raise RelationalClientError('OR REPLACE and IF NOT EXISTS cannot be combined')

    aggregate = bool(draft.get('aggregate', False))
    if aggregate and kind != 'function':
        raise RelationalClientError('AGGREGATE applies only to MariaDB functions')

    def_mode = draft.get('definer_mode')
    if def_mode not in (None, '', 'OMIT', 'CURRENT_USER', 'ACCOUNT'):
        raise RelationalClientError('Select OMIT, CURRENT_USER or ACCOUNT for MariaDB definer_mode')

    verb = 'CREATE OR REPLACE ' if or_replace else 'CREATE '
    definer_sql = ''
    if def_mode == 'CURRENT_USER':
        definer_sql = 'DEFINER=CURRENT_USER '
    elif def_mode != 'OMIT' and (draft.get('definer_user') or draft.get('definer_host')):
        definer_sql = f"DEFINER={_account_part(draft.get('definer_user'), 80)}@{_account_part(draft.get('definer_host'), 255)} "
    agg_sql = 'AGGREGATE ' if aggregate else ''
    ine_sql = 'IF NOT EXISTS ' if if_not_exists else ''

    det_raw = draft.get('deterministic')
    det_sql = ''
    if det_raw not in (None, ''):
        if not isinstance(det_raw, str) or det_raw not in {'DETERMINISTIC', 'NOT DETERMINISTIC'}:
            raise RelationalClientError('Select DETERMINISTIC or NOT DETERMINISTIC')
        det_sql = f' {det_raw}'

    acc_sql = ''
    if draft.get('data_access') not in (None, ''):
        if draft['data_access'] not in ROUTINE_ACCESS:
            raise RelationalClientError('Select a valid MariaDB SQL data access clause')
        acc_sql = ' ' + draft['data_access']

    sec_sql = ''
    if draft.get('sql_security') not in (None, ''):
        if draft['sql_security'] not in ROUTINE_SECURITY:
            raise RelationalClientError('Select DEFINER or INVOKER SQL security')
        sec_sql = ' SQL SECURITY ' + draft['sql_security']

    parameters = []
    comment_sql = ''
    if draft.get('comment') not in (None, ''):
        comment_text = _text(draft['comment'], 'Routine comment', 65535)
        escaped = comment_text.replace('\\', '\\\\').replace("'", "''")
        comment_sql = f" COMMENT '{escaped}'"

    param_block = f" ({', '.join(declarations)})" if (declarations or not oracle_mode) else ''
    if oracle_mode:
        ret_sql = f" RETURN {_safe_type(draft.get('returns'))}" if kind == 'function' else ''
        header = f'{verb}{definer_sql}{agg_sql}{kind.upper()} {ine_sql}{qualified}{param_block}{ret_sql}{det_sql}{acc_sql}{sec_sql}{comment_sql}'
        connector = ' ' if re.match(r'^(?:AS|IS)\b', body, re.I) else ' AS\n'
        source = f'{header}{connector}{body}'
    else:
        if kind == 'function':
            ret_type = _safe_type(draft.get('returns'))
            ret_sql = f' RETURNS {ret_type}'
        elif draft.get('returns') not in (None, ''):
            raise RelationalClientError('Procedures do not declare a RETURNS scalar type')
        else:
            ret_sql = ''
        header = f'{verb}{definer_sql}{agg_sql}{kind.upper()} {ine_sql}{qualified}{param_block}{ret_sql}{det_sql}{acc_sql}{sec_sql}{comment_sql}'
        source = f'{header} {body}'

    return {
        'statements': [{'source': source, 'parameters': tuple(parameters)}],
        KEY: {
            'kind': kind,
            'operation': operation,
            'path': [str(p) for p in path],
            'sql_mode': sql_mode,
            'draft': draft,
        },
        'warnings': [
            f'MariaDB {verb.strip()} {kind.upper()} commits implicitly on an independently owned connection.',
            *(
                ['CREATE OR REPLACE replaces the stored routine definition and evaluates privileges/dependent callers under the new signature.']
                if or_replace else []
            ),
        ],
    }


def compile_trigger(operation, draft, target):
    if operation not in {'create', 'alter', 'create_or_replace'} or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a MariaDB trigger operation')
    draft = deepcopy(dict(draft))
    options = draft.pop('options', {})
    if isinstance(options, Mapping):
        for k, v in options.items():
            draft.setdefault(k, v)
    changes = draft.pop('changes', {})
    if isinstance(changes, Mapping):
        for k, v in changes.items():
            draft.setdefault(k, v)

    for alias, canonical in (
        ('parent', 'database'),
        ('definition', 'body'),
        ('order_kind', 'order'),
        ('order_trigger', 'other_trigger'),
    ):
        if alias in draft:
            if canonical in draft and draft[canonical] != draft[alias]:
                raise RelationalClientError(f'Conflicting MariaDB trigger field: {canonical}')
            draft[canonical] = draft.pop(alias)

    if 'active' in draft:
        active_val = draft.pop('active')
        if active_val not in (None, True):
            raise RelationalClientError('MariaDB triggers cannot be created in an inactive state')
    if 'position' in draft:
        pos_val = draft.pop('position')
        if pos_val not in (None, 0, ''):
            raise RelationalClientError('MariaDB triggers use FOLLOWS or PRECEDES sibling ordering, not numeric position')

    allowed = {
        'name', 'database', 'table', 'timing', 'event', 'events', 'body',
        'definer_mode', 'definer_user', 'definer_host', 'if_not_exists', 'or_replace',
        'order', 'other_trigger', 'sql_mode', 'confirmation',
    }
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB trigger option: ' + ', '.join(sorted(set(draft) - allowed)))

    replacing = operation in {'alter', 'create_or_replace'}
    preserve_sibling_order = False
    if replacing:
        if not isinstance(target, Mapping) or target.get('resource_kind') != 'trigger':
            raise RelationalClientError('Select an existing MariaDB trigger to replace')
        t_path = target.get('display_path')
        if not isinstance(t_path, list) or len(t_path) not in {2, 3}:
            raise RelationalClientError('Exact MariaDB trigger identity is required')
        if operation == 'create_or_replace' and draft.get('confirmation') != target.get('display_name'):
            raise RelationalClientError('Confirm the exact MariaDB trigger name for CREATE OR REPLACE TRIGGER')
        current = _native_facts(target)
        db_name = str(t_path[0])
        trg_name = str(t_path[-1])
        path = [db_name, trg_name]
        if 'table' not in draft:
            if len(t_path) == 3:
                draft['table'] = [db_name, str(t_path[1])]
            elif isinstance(current.get('table'), list):
                draft['table'] = current['table']
        if 'timing' not in draft and current.get('timing'):
            draft['timing'] = current['timing']
        if 'events' not in draft and 'event' not in draft and current.get('events'):
            draft['events'] = current['events']
        if 'body' not in draft and current.get('body'):
            draft['body'] = current['body']
        if 'sql_mode' not in draft and current.get('sql_mode') is not None:
            draft['sql_mode'] = current['sql_mode']
        if 'order' not in draft:
            preserve_sibling_order = True
    else:
        db_val = draft.get('database')
        if isinstance(db_val, list) and len(db_val) == 1:
            db_val = db_val[0]
        raw_table = draft.get('table')
        table_parts = raw_table.split('.') if isinstance(raw_table, str) else list(raw_table or [])
        if len(table_parts) == 2 and not db_val:
            db_val = table_parts[0]
        path = [db_val, draft.get('name')] if db_val else [draft.get('name')]
        if any(not p for p in path):
            raise RelationalClientError('MariaDB trigger name is required')

    raw_table = draft.get('table')
    table_parts = raw_table.split('.') if isinstance(raw_table, str) else list(raw_table or [])
    if not 1 <= len(table_parts) <= 2 or any(not p for p in table_parts):
        raise RelationalClientError('MariaDB trigger requires an owning table')
    if len(path) == 2 and len(table_parts) == 1:
        table_parts = [path[0], table_parts[0]]
    elif len(path) == 2 and len(table_parts) == 2 and path[0] != table_parts[0]:
        raise RelationalClientError('MariaDB trigger and owning table must belong to the same database')

    timing = str(draft.get('timing') or 'BEFORE').upper()
    if timing not in TRIGGER_TIMINGS:
        raise RelationalClientError('MariaDB trigger timing must be BEFORE or AFTER')

    if 'events' in draft and 'event' in draft:
        raise RelationalClientError('Specify either event or events for a MariaDB trigger')
    events = draft.get('events') if 'events' in draft else ([draft['event']] if 'event' in draft else ['INSERT'])
    if isinstance(events, str):
        events = [events]
    if (
        not isinstance(events, list)
        or not 1 <= len(events) <= 3
        or any(str(ev).upper() not in TRIGGER_EVENTS for ev in events)
        or len({str(ev).upper() for ev in events}) != len(events)
    ):
        raise RelationalClientError('Select 1 to 3 distinct MariaDB trigger events (INSERT, UPDATE, DELETE)')
    events_upper = [str(ev).upper() for ev in events]

    order = str(draft.get('order') or 'NONE').upper()
    if order not in TRIGGER_ORDERS:
        raise RelationalClientError('Select NONE, FOLLOWS or PRECEDES trigger ordering')
    other_trigger = draft.get('other_trigger')
    if order != 'NONE':
        if not isinstance(other_trigger, str) or not other_trigger or other_trigger == path[-1]:
            raise RelationalClientError(f'{order} requires a distinct sibling trigger name')
    elif other_trigger not in (None, ''):
        raise RelationalClientError('Select FOLLOWS or PRECEDES when specifying a sibling trigger')

    body = _text(draft.get('body'), 'Trigger body', 1024 * 1024).strip()
    if not body:
        raise RelationalClientError('Trigger body is required')
    sql_mode = _validate_sql_mode(draft.get('sql_mode'))
    if executable_comment(body, sql_mode or ''):
        raise RelationalClientError('Executable comments are not admitted in structured trigger bodies')

    or_replace = replacing or bool(draft.get('or_replace', False))
    if_not_exists = bool(draft.get('if_not_exists', False))
    if or_replace and if_not_exists:
        raise RelationalClientError('OR REPLACE and IF NOT EXISTS cannot be combined')

    def_mode = draft.get('definer_mode')
    if def_mode not in (None, '', 'OMIT', 'CURRENT_USER', 'ACCOUNT'):
        raise RelationalClientError('Select OMIT, CURRENT_USER or ACCOUNT for MariaDB trigger definer_mode')

    source = _render_trigger_sql(
        or_replace=or_replace,
        if_not_exists=if_not_exists,
        definer_mode=def_mode,
        definer_user=draft.get('definer_user'),
        definer_host=draft.get('definer_host'),
        path=path,
        timing=timing,
        events=events_upper,
        table_parts=table_parts,
        order=order,
        other_trigger=other_trigger,
        body=body,
    )
    return {
        'statements': [{'source': source, 'parameters': ()}],
        KEY: {
            'kind': 'trigger',
            'operation': operation,
            'path': [str(p) for p in path],
            'table': [str(p) for p in table_parts],
            'timing': timing,
            'events': events_upper,
            'order': order,
            'other_trigger': other_trigger,
            'preserve_sibling_order': preserve_sibling_order,
            'sql_mode': sql_mode,
            'or_replace': or_replace,
            'if_not_exists': if_not_exists,
            'definer_mode': def_mode,
            'definer_user': draft.get('definer_user'),
            'definer_host': draft.get('definer_host'),
            'body': body,
            'draft': draft,
        },
        'warnings': [
            'MariaDB trigger DDL commits implicitly on an independently owned connection.',
            *(
                ['CREATE OR REPLACE TRIGGER preserves sibling FOLLOWS/PRECEDES ordering and stored SQL_MODE unless explicitly changed.']
                if replacing else []
            ),
        ],
    }


def _render_trigger_sql(
    *, or_replace, if_not_exists, definer_mode=None, definer_user, definer_host,
    path, timing, events, table_parts, order, other_trigger, body
):
    verb = 'CREATE OR REPLACE ' if or_replace else 'CREATE '
    definer_sql = ''
    if definer_mode == 'CURRENT_USER':
        definer_sql = 'DEFINER=CURRENT_USER '
    elif definer_mode != 'OMIT' and (definer_user or definer_host):
        definer_sql = f'DEFINER={_account_part(definer_user, 80)}@{_account_part(definer_host, 255)} '
    ine_sql = 'IF NOT EXISTS ' if if_not_exists else ''
    qualified = '.'.join(identifier(p) for p in path)
    qualified_table = '.'.join(identifier(p) for p in table_parts)
    event_sql = ' OR '.join(events)
    order_sql = f' {order} {identifier(other_trigger)}' if order != 'NONE' and other_trigger else ''
    return f'{verb}{definer_sql}TRIGGER {ine_sql}{qualified} {timing} {event_sql} ON {qualified_table} FOR EACH ROW{order_sql}\n{body}'


def _observe_object(cursor, intent, env):
    kind = intent['kind']
    path = intent['path']
    db_name, obj_name = path[0], path[1]
    if kind == 'view':
        cursor.execute(
            'SELECT VIEW_DEFINITION, CHECK_OPTION, IS_UPDATABLE, DEFINER, SECURITY_TYPE '
            'FROM information_schema.VIEWS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
            (db_name, obj_name),
        )
        rows = [list(r) for r in cursor.fetchall()]
        cursor.execute(
            'SELECT TABLE_SCHEMA, TABLE_NAME FROM information_schema.VIEWS '
            'WHERE TABLE_SCHEMA = %s AND TABLE_NAME <> %s AND VIEW_DEFINITION LIKE %s '
            'ORDER BY TABLE_NAME LIMIT 50',
            (db_name, obj_name, f'%{obj_name}%'),
        )
        dep_views = [{'database': r[0], 'view': r[1]} for r in cursor.fetchall()]
        return {
            'present': bool(rows),
            'state_sha256': hashlib.sha256(json.dumps(rows, default=str).encode('utf8')).hexdigest(),
            'dependent_views_referencing_name': dep_views,
        }

    if kind in {'procedure', 'function'}:
        cursor.execute(
            'SELECT ROUTINE_TYPE, ROUTINE_DEFINITION, IS_DETERMINISTIC, SQL_DATA_ACCESS, '
            'SECURITY_TYPE, DEFINER, ROUTINE_COMMENT, CAST(SQL_MODE AS CHAR) '
            'FROM information_schema.ROUTINES '
            'WHERE ROUTINE_SCHEMA = %s AND ROUTINE_NAME = %s AND ROUTINE_TYPE = %s',
            (db_name, obj_name, kind.upper()),
        )
        rows = [list(r) for r in cursor.fetchall()]
        grants = []
        try:
            cursor.execute(
                'SELECT Host, User, Proc_priv FROM mysql.procs_priv '
                'WHERE Db = %s AND Routine_name = %s AND Routine_type = %s ORDER BY Host, User',
                (db_name, obj_name, kind.upper()),
            )
            grants = [{'host': str(r[0]), 'user': str(r[1]), 'privileges': str(r[2])} for r in cursor.fetchall()]
        except Exception as exc:
            if getattr(exc, 'errno', None) not in {1044, 1142, 1143, 1227}:
                raise
        dep_views = []
        if kind == 'function':
            cursor.execute(
                'SELECT TABLE_SCHEMA, TABLE_NAME FROM information_schema.VIEWS '
                'WHERE TABLE_SCHEMA = %s AND VIEW_DEFINITION LIKE %s ORDER BY TABLE_NAME LIMIT 50',
                (db_name, f'%{obj_name}%'),
            )
            dep_views = [{'database': r[0], 'view': r[1]} for r in cursor.fetchall()]
        return {
            'present': bool(rows),
            'stored_sql_mode': str(rows[0][7]) if rows and rows[0][7] is not None else None,
            'state_sha256': hashlib.sha256(json.dumps(rows, default=str).encode('utf8')).hexdigest(),
            'routine_grants': grants,
            'dependent_views_referencing_name': dep_views,
        }

    table = intent['table']
    cursor.execute('SHOW CREATE TABLE ' + '.'.join(identifier(p) for p in table))
    t_row = cursor.fetchone()
    if not t_row or len(t_row) < 2 or not isinstance(t_row[1], str):
        raise RelationalClientError('Owning MariaDB table for trigger is unavailable')
    cursor.execute(
        'SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER, '
        'ACTION_STATEMENT, DEFINER, CAST(SQL_MODE AS CHAR) '
        'FROM information_schema.TRIGGERS '
        'WHERE TRIGGER_SCHEMA = %s AND EVENT_OBJECT_SCHEMA = %s AND EVENT_OBJECT_TABLE = %s '
        'ORDER BY ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER, TRIGGER_NAME',
        (db_name, table[0], table[1]),
    )
    t_rows = [list(r) for r in cursor.fetchall()]
    existing = [r for r in t_rows if r[0] == obj_name]
    return {
        'present': bool(existing),
        'stored_sql_mode': str(existing[0][6]) if existing and existing[0][6] is not None else None,
        'table_structure_sha256': structural_definition(t_row[1], env['sql_mode']),
        'state_sha256': hashlib.sha256(json.dumps(t_rows, default=str).encode('utf8')).hexdigest(),
        'ordered_triggers': [
            {'name': r[0], 'timing': r[1], 'event': r[2], 'order': int(r[3])}
            for r in t_rows
        ],
    }


def _resolve_preserved_trigger_details(intent, before):
    """When replacing an existing trigger without explicit order/sql_mode, preserve its sibling anchor and SQL_MODE."""
    if intent['kind'] != 'trigger':
        return
    if intent['sql_mode'] is None and before.get('stored_sql_mode') is not None:
        intent['sql_mode'] = before['stored_sql_mode']
    if not intent.get('preserve_sibling_order'):
        return
    siblings = [
        item for item in before.get('ordered_triggers', [])
        if item['timing'] == intent['timing'] and item['event'] == intent['events'][0]
    ]
    me = next((item for item in siblings if item['name'] == intent['path'][1]), None)
    if me is None or len(siblings) <= 1:
        return
    idx = siblings.index(me)
    if idx > 0:
        intent['order'] = 'FOLLOWS'
        intent['other_trigger'] = siblings[idx - 1]['name']
    else:
        intent['order'] = 'PRECEDES'
        intent['other_trigger'] = siblings[1]['name']


def bind_review(client, planned):
    payload = planned['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        cursor.execute('SELECT DATABASE()')
        (default_db,) = cursor.fetchone()
        if len(intent['path']) == 1:
            if not default_db:
                raise RelationalClientError('Select a default database or qualify the MariaDB object name')
            intent['path'] = [str(default_db), intent['path'][0]]
            if intent['kind'] == 'trigger' and len(intent['table']) == 1:
                intent['table'] = [str(default_db), intent['table'][0]]
        before = _observe_object(cursor, intent, env)
        if intent['operation'] == 'alter' and not before['present']:
            raise RelationalClientError(f"Target MariaDB {intent['kind']} does not exist")
        if intent['kind'] == 'trigger':
            _resolve_preserved_trigger_details(intent, before)
            new_sql = _render_trigger_sql(
                or_replace=intent['or_replace'],
                if_not_exists=intent['if_not_exists'],
                definer_mode=intent.get('definer_mode'),
                definer_user=intent['definer_user'],
                definer_host=intent['definer_host'],
                path=intent['path'],
                timing=intent['timing'],
                events=intent['events'],
                table_parts=intent['table'],
                order=intent['order'],
                other_trigger=intent['other_trigger'],
                body=intent['body'],
            )
            compiled['statements'][0]['source'] = new_sql
            planned['command_preview']['statements'][0]['source'] = new_sql
        elif (
            intent['kind'] in {'procedure', 'function'}
            and intent['operation'] == 'create_or_replace'
            and intent['sql_mode'] is None
            and before.get('stored_sql_mode') is not None
        ):
            intent['sql_mode'] = before['stored_sql_mode']

        intent['review'] = {
            'execution_identity': {**env, 'database': default_db},
            'before': before,
        }
        planned['command_preview'].update(
            native_execution_identity=intent['review']['execution_identity'],
            native_object_observation=before,
            effective_sql_mode=intent.get('sql_mode') if intent.get('sql_mode') is not None else env['sql_mode'],
        )
        return planned
    finally:
        release(client, handle, cursor)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MariaDB object DDL requires an independently owned connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the MariaDB object operation before execution')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        before = _observe_object(cursor, intent, env)
        if (
            env['server_uid'] != review['execution_identity']['server_uid']
            or before['state_sha256'] != review['before']['state_sha256']
            or before.get('table_structure_sha256') != review['before'].get('table_structure_sha256')
        ):
            raise RelationalClientError(f"MariaDB {intent['kind']} or server identity changed since review")

        target_mode = intent.get('sql_mode')
        if target_mode is not None:
            cursor.execute('SET SESSION sql_mode = %s', (target_mode,))

        stmt = compiled['statements'][0]
        params = stmt.get('parameters') or ()
        dispatched = True
        if params:
            cursor.execute(stmt['source'], params)
        else:
            cursor.execute(stmt['source'])
        acknowledged = True
        cursor.execute('SHOW WARNINGS')
        warnings = [
            {'level': str(level), 'code': int(code), 'message': str(msg)}
            for level, code, msg in cursor.fetchall()
        ]
        if target_mode is not None:
            cursor.execute('SET SESSION sql_mode = %s', (env['sql_mode'],))
        after = _observe_object(cursor, intent, env)
        return {
            'accepted': True,
            'native_acknowledged': True,
            'native_implicit_commit': True,
            'commit_requested': False,
            'rollback_requested': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'effective_sql_mode': target_mode if target_mode is not None else env['sql_mode'],
            'native_warnings': warnings,
            'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'object_observation': {
                'kind': intent['kind'],
                'operation': intent['operation'],
                'execution_identity': env,
                'before': before,
                'after': after,
                'dependent_views': [
                    d['view'] for d in after.get('dependent_views_referencing_name', [])
                ],
                'concurrent_external_ddl_fenced': False,
            },
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            f"MariaDB {intent['kind']} {intent['operation']} failed ({type(error).__name__}: {error})"
        )
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        raise failure from None
    finally:
        release(client, handle, cursor)


def enrich_catalog_views_and_program_objects(optional, optional_records, resources, resource_key, add, catalog_failures=None):
    """Enrich MariaDB view, routine and trigger resources with full reopen metadata."""
    for schema_name, view_name, view_def, check_opt, definer, sec_type, is_upd in optional(
        'SELECT TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION, CHECK_OPTION, DEFINER, SECURITY_TYPE, IS_UPDATABLE '
        'FROM information_schema.VIEWS '
        "WHERE TABLE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
        'ORDER BY TABLE_SCHEMA, TABLE_NAME'
    ):
        v_key = resource_key('view', [schema_name], view_name)
        if v_key not in resources:
            continue
        v_native = resources[v_key].setdefault('native', {})
        ddl = v_native.get('ddl') or ''
        v_native.update(
            view_definition=view_def,
            check_option=check_opt,
            definer=definer,
            sql_security=sec_type,
            is_updatable=is_upd,
            view_aliases=declared_aliases(ddl),
        )
        user, sep, host = str(definer or '').rpartition('@')
        if sep:
            v_native.update(definer_user=user, definer_host=host)
        alg = re.match(r'CREATE\s+(?:OR\s+REPLACE\s+)?ALGORITHM\s*=\s*(UNDEFINED|MERGE|TEMPTABLE)\b', ddl, re.I)
        if alg:
            v_native['algorithm'] = alg.group(1).upper()

    for record in optional_records(
        'SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DEFINER, CAST(SQL_MODE AS CHAR) AS SQL_MODE '
        'FROM information_schema.ROUTINES '
        "WHERE ROUTINE_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
        "AND ROUTINE_TYPE IN ('PROCEDURE', 'FUNCTION') ORDER BY 1, 2"
    ):
        kind = str(record['routine_type']).lower()
        r_key = resource_key(kind, [record['routine_schema']], record['routine_name'])
        if r_key not in resources:
            continue
        r_native = resources[r_key].setdefault('native', {})
        definer = record.get('definer') or ''
        user, sep, host = str(definer).rpartition('@')
        r_native.update(
            definer=definer,
            sql_mode=record.get('sql_mode'),
            data_access=r_native.get('sql_data_access'),
            sql_security=r_native.get('security_type'),
            routine_comment=r_native.get('comment'),
            **({'definer_user': user, 'definer_host': host} if sep else {}),
        )

    grouped_triggers = {}
    for record in optional_records(
        'SELECT TRIGGER_SCHEMA, EVENT_OBJECT_SCHEMA, EVENT_OBJECT_TABLE, TRIGGER_NAME, '
        'ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER, ACTION_STATEMENT, DEFINER, CAST(SQL_MODE AS CHAR) AS SQL_MODE '
        'FROM information_schema.TRIGGERS '
        "WHERE TRIGGER_SCHEMA NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
        'ORDER BY TRIGGER_SCHEMA, EVENT_OBJECT_TABLE, ACTION_TIMING, ACTION_ORDER, TRIGGER_NAME'
    ):
        g_key = (record['trigger_schema'], record['event_object_table'], record['trigger_name'])
        entry = grouped_triggers.setdefault(g_key, {'events': [], 'row': record})
        if record['event_manipulation'] not in entry['events']:
            entry['events'].append(record['event_manipulation'])

    for (schema_name, table_name, trg_name), info in grouped_triggers.items():
        row = info['row']
        definer = row.get('definer') or ''
        user, sep, host = str(definer).rpartition('@')
        add('trigger', [schema_name, table_name], trg_name, {
            'timing': row['action_timing'],
            'events': info['events'],
            'position': row['action_order'],
            'body': row['action_statement'],
            'definer': definer,
            'sql_mode': row.get('sql_mode'),
            'table': [row['event_object_schema'], row['event_object_table']],
            **({'definer_user': user, 'definer_host': host} if sep else {}),
        })
