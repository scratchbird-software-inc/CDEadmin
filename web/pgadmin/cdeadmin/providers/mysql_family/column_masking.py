"""Native MySQL column policy references, distinct from policy-component state."""
from collections.abc import Mapping
from copy import deepcopy
import json

from ...sdk import RelationalClientError
from .mysql_catalog import identifier, _value
from .spatial_reference_systems import identity

OPERATIONS = frozenset({'set_masking_policy', 'drop_masking_policy'})


def policy_clauses(source, mode):
    from ...workspace.mysql_table_clauses import table_layout
    from ...workspace.mysql_relational_fields import tokens
    from ...workspace.mysql_schema_plan import name
    found = {}
    for clause in table_layout(source, mode)['clauses']:
        parsed = tokens(clause, mode)
        if not parsed or parsed[0][0] != 'quoted':
            continue
        column = name(parsed[0][1])
        policy = None;preserved = [];index = 0
        while index < len(parsed):
            kind, value, _start, _end = parsed[index]
            if kind == 'word' and value.upper() == 'MASKING':
                if (policy is not None or index + 2 >= len(parsed) or
                        parsed[index+1][0] != 'word' or parsed[index+1][1].upper() != 'POLICY' or
                        parsed[index+2][0] != 'quoted'):
                    raise ValueError('Ambiguous native column masking policy')
                policy = name(parsed[index+2][1]);index += 3
            else:
                preserved.append((kind, value));index += 1
        if column in found:
            raise ValueError('Ambiguous native column declaration')
        found[column] = {'name': policy, 'column_tokens_without_policy': preserved}
    return found


def policy_clause(source, column, mode):
    found = policy_clauses(source, mode)
    if column not in found:
        raise ValueError('Exact native masked-column declaration is unavailable')
    return found[column]


def address(path):
    parts = ['column', *path]
    return ('mysql-resource:' + json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
        if any(':' in part for part in parts) else ':'.join(parts))


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping) or not isinstance(target, Mapping):
        raise RelationalClientError('Select a native MySQL column masking operation')
    allowed = {'confirmation', 'policy_name'} if operation == 'set_masking_policy' else {'confirmation'}
    path = target.get('display_path')
    if (set(draft) - allowed or target.get('resource_kind') != 'column' or
            not isinstance(path, list) or len(path) != 3 or
            any(not isinstance(value, str) or not value or '\x00' in value for value in path) or
            target.get('display_name') != path[-1] or target.get('resource_id') != address(path) or
            draft.get('confirmation') != path[-1]):
        raise RelationalClientError('Confirm the exact native MySQL column resource address')
    source = 'ALTER TABLE ' + '.'.join(identifier(value) for value in path[:2]) + ' ALTER COLUMN ' + identifier(path[-1])
    if operation == 'set_masking_policy':
        policy = draft.get('policy_name')
        if not isinstance(policy, str) or not policy or '\x00' in policy or len(policy) > 64:
            raise RelationalClientError('Select an exact native masking policy name of 1 to 64 characters')
        source += ' SET MASKING POLICY ' + identifier(policy)
    else:
        source += ' DROP MASKING POLICY'
    return {'statements': [{'source': source, 'parameters': ()}],
        'mysql_column_masking': {'operation': operation, 'draft': dict(draft), 'target': deepcopy(dict(target))},
        'warnings': ['Working masking and policy administration require the post-beta Enterprise object_policy component; its implementation is absent from the pinned Community source. Community MySQL stores the column reference and can refuse reads while that component is unavailable.',
            'This DDL uses an independent connection and never decides an interactive session transaction.']}


def observe(cursor, path, mode):
    cursor.execute('SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s', tuple(path))
    names = [str(column[0]).lower() for column in cursor.description];row = cursor.fetchone()
    if not row:
        raise RelationalClientError('The native MySQL column no longer exists')
    facts = {key: _value(value) for key, value in zip(names, row)}
    cursor.execute('SHOW CREATE TABLE ' + '.'.join(identifier(value) for value in path[:2]))
    row = cursor.fetchone()
    if not row or row[0] != path[1]:
        raise RelationalClientError('Exact native MySQL table definition is unavailable')
    try:
        policy = policy_clause(row[1], path[-1], mode)
    except ValueError as error:
        raise RelationalClientError(str(error)) from None
    if bool(policy['name']) != ('MASKING POLICY' in str(facts.get('extra', '')).upper()):
        raise RelationalClientError('Native masking declaration and column facts disagree')
    return {'column': facts, 'masking_policy': policy['name'],
        'column_tokens_without_policy': policy['column_tokens_without_policy']}


def environment(cursor):
    observed = identity(cursor)
    cursor.execute('SELECT @@sql_mode');observed['sql_mode'] = cursor.fetchone()[0]
    cursor.execute('SET SESSION sql_quote_show_create=1')
    return observed


def lookup(cursor, name):
    if name is None:
        return {'state': 'not_referenced'}
    try:
        cursor.execute('SHOW CREATE MASKING POLICY ' + identifier(name))
        row = cursor.fetchone()
        return {'state': 'observed', 'native_columns': [str(column[0]) for column in cursor.description],
            'native_definition': [_value(value) for value in row]}
    except Exception as error:
        code = getattr(error, 'errno', None)
        if (not isinstance(code, int) or 2000 <= code < 3000 or
                str(getattr(error, 'sqlstate', '')).startswith('08')):
            raise
        return {'state': 'component_unavailable' if code == 6561 else 'permission_denied' if code == 1227 else 'native_refusal',
            'native_error_code': code, 'sqlstate': getattr(error, 'sqlstate', None)}


def bind_review(client, planned):
    payload = planned['provider_payload'];intent = payload['compiled']['mysql_column_masking']
    handle = client._connect({'route': payload['route']});cursor = None
    try:
        cursor = handle.cursor();observed = environment(cursor)
        baseline = observe(cursor, intent['target']['display_path'], observed['sql_mode'])
        definition = lookup(cursor, intent['draft'].get('policy_name', baseline['masking_policy']))
        intent['review'] = {'execution_identity': observed, 'baseline': baseline}
        planned['command_preview'].update(native_execution_identity=observed,
            native_column_context=deepcopy(baseline), masking_policy_definition=definition)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def preserved(before, after):
    def extra(value):return ' '.join(value.replace('MASKING POLICY', '').split())
    return (before['column_tokens_without_policy'] == after['column_tokens_without_policy'] and
        {key:value for key,value in before['column'].items() if key != 'extra'} ==
        {key:value for key,value in after['column'].items() if key != 'extra'} and
        extra(before['column'].get('extra', '')) == extra(after['column'].get('extra', '')))


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Column masking DDL requires an independently owned connection')
    payload = request['provider_payload'];compiled = payload['compiled'];intent = compiled['mysql_column_masking']
    checked = deepcopy(compiled);review = checked['mysql_column_masking'].pop('review', None)
    if compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('The reviewed native column masking operation changed')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the native MySQL column and principal before dispatch')
    handle = client._connect({'route': payload['route']});cursor = None;dispatched = acknowledged = False
    try:
        handle.autocommit = True;handle.get_warnings = True;handle.raise_on_warnings = False;cursor = handle.cursor()
        observed = environment(cursor);path = intent['target']['display_path']
        before = observe(cursor, path, observed['sql_mode'])
        if observed != review['execution_identity'] or before != review['baseline']:
            raise RelationalClientError('Native column, masking reference or execution identity changed since review')
        dispatched = True;cursor.execute(compiled['statements'][0]['source']);acknowledged = True
        warnings = [{'level':level,'code':code,'message':message} for level,code,message in (cursor.warnings or ())]
        after = observe(cursor, path, observed['sql_mode'])
        expected = intent['draft'].get('policy_name') if intent['operation'] == 'set_masking_policy' else None
        verified = after['masking_policy'] == expected and preserved(before, after)
        return {'accepted': True, 'commit_requested': False, 'rollback_requested': False,
            'staged_in_provider_session': False, 'native_implicit_commit': True,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'native_warnings': warnings, 'column_masking_observation': {'native_acknowledged': True,
                'rediscovery_verified': verified, 'before': before, 'after': after,
                'policy_definition': lookup(cursor, expected), 'execution_identity': observed},
            'automatic_retry': False}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MySQL column masking operation failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched;failure.native_acknowledged = acknowledged
        failure.errno = getattr(error, 'errno', None);failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if isinstance(failure.errno, int) else ()
        failure.automatic_retry = False
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
