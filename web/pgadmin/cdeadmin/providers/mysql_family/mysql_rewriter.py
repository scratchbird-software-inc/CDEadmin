"""Native Rewriter table editing and explicit, separate in-memory reload."""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid

OPERATIONS = {
    'inspect_rewrite_rules': 'Inspect native query rewrite rules',
    'create_rewrite_rule': 'Add native query rewrite rule',
    'alter_rewrite_rule': 'Change native query rewrite rule',
    'drop_rewrite_rule': 'Remove native query rewrite rule',
    'reload_rewrite_rules': 'Reload native query rewrite rules',
}
COLUMNS = ('id', 'pattern', 'pattern_database', 'replacement', 'enabled',
           'message', 'pattern_digest', 'normalized_pattern')
EDITABLE = ('pattern', 'pattern_database', 'replacement', 'enabled')
SELECT = 'SELECT ' + ','.join(COLUMNS) + ' FROM query_rewrite.rewrite_rules'
MAX_RULES = 1000
MAX_BYTES = 4 * 1024 * 1024


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native MySQL Rewriter operation')
    uuid = target_uuid(target)
    allowed = {'confirmation'} if operation != 'inspect_rewrite_rules' else set()
    if operation in {'alter_rewrite_rule', 'drop_rewrite_rule'}:
        allowed.add('rule_id')
    if operation in {'create_rewrite_rule', 'alter_rewrite_rule'}:
        allowed.update(EDITABLE)
        allowed.add('pattern_database_mode')
    if operation == 'reload_rewrite_rules':
        allowed.add('all_queries_affected')
    if set(draft) - allowed or operation != 'inspect_rewrite_rules' and draft.get('confirmation') != target['display_name']:
        raise RelationalClientError('Confirm the exact MySQL server and rule options')
    rule_id = None
    if 'rule_id' in allowed:
        text = draft.get('rule_id')
        if not isinstance(text, str) or not re.fullmatch(r'(?:0|-?[1-9][0-9]{0,9})', text) or not -2147483648 <= int(text) <= 2147483647:
            raise RelationalClientError('Select the exact signed 32-bit native rule ID')
        rule_id = int(text)
    values = []
    if operation in {'create_rewrite_rule', 'alter_rewrite_rule'}:
        for name in EDITABLE:
            value = draft.get(name)
            if name == 'enabled':
                if value not in ('YES', 'NO'):
                    raise RelationalClientError('Select native YES or NO for the stored rule')
            elif name == 'pattern_database':
                mode = draft.get('pattern_database_mode', 'VALUE' if value not in (None, '') else 'NULL')
                if mode not in ('VALUE', 'NULL'):
                    raise RelationalClientError('Select native NULL or an exact pattern database value')
                if mode == 'NULL': value = None
                if value is not None and (not isinstance(value, str) or len(value) > 20 or '\0' in value):
                    raise RelationalClientError('Use an optional native pattern database of at most 20 characters')
            elif not isinstance(value, str) or not value or len(value) > 5000 or '\0' in value:
                raise RelationalClientError('Use native pattern and replacement text of 1 to 5000 characters')
            values.append(value)
    if operation == 'reload_rewrite_rules' and draft.get('all_queries_affected') is not True:
        raise RelationalClientError('Confirm that reloading changes native query rewriting for all clients')
    if operation == 'create_rewrite_rule':
        sql = 'INSERT INTO query_rewrite.rewrite_rules (pattern,pattern_database,replacement,enabled) VALUES (%s,%s,%s,%s)'
    elif operation == 'alter_rewrite_rule':
        sql = 'UPDATE query_rewrite.rewrite_rules SET pattern=%s,pattern_database=%s,replacement=%s,enabled=%s WHERE id=%s'
        values.append(rule_id)
    elif operation == 'drop_rewrite_rule':
        sql = 'DELETE FROM query_rewrite.rewrite_rules WHERE id=%s'
        values.append(rule_id)
    elif operation == 'reload_rewrite_rules':
        sql = 'CALL query_rewrite.flush_rewrite_rules()'
    else:
        sql = SELECT + ' ORDER BY id LIMIT 1001'
    return {
        'statements': [{'source': sql, 'parameters': tuple(values)}],
        'mysql_rewriter': {'operation': operation, 'rule_id': rule_id,
                          'draft': dict(draft), 'target': deepcopy(dict(target)), 'server_uuid': uuid},
        'warnings': [
            'Rule edits change the committed native table without invoking a reload. Other administrators and native startup loading can activate stored rules; saving a rule does not establish that it can be loaded.',
            'Reload invokes the native procedure, which commits its own connection and can partially load valid rules while reporting rejected rules. Native per-rule messages and reload status are reported separately.',
            'Review and later observations do not freeze other rule writers or prove which in-memory rule handled any client query. No operation is automatically replayed.',
        ],
    }


def bounded(rows):
    value = [dict(zip(COLUMNS, row)) for row in rows]
    if len(value) > MAX_RULES or len(json.dumps(value, ensure_ascii=False).encode('utf8')) > MAX_BYTES:
        raise RelationalClientError('Native rewrite rules exceed 1000 rows or 4 MiB; no partial review is admitted')
    return value


def observe(cursor):
    cursor.execute("SELECT PLUGIN_NAME,PLUGIN_VERSION,PLUGIN_STATUS,PLUGIN_LIBRARY FROM information_schema.PLUGINS WHERE PLUGIN_NAME='Rewriter'")
    plugin = cursor.fetchone()
    if not plugin or str(plugin[2]).upper() != 'ACTIVE':
        raise RelationalClientError('The native Rewriter plugin must be installed and active')
    cursor.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='query_rewrite' AND TABLE_NAME='rewrite_rules'")
    if cursor.fetchone() != ('InnoDB',):
        raise RelationalClientError('Select the native InnoDB query_rewrite.rewrite_rules table')
    cursor.execute(SELECT + ' ORDER BY id LIMIT 1001')
    rules = bounded(cursor.fetchmany(MAX_RULES + 1))
    cursor.execute('SHOW GLOBAL STATUS WHERE Variable_name IN (%s,%s,%s,%s)',
                   ('Rewriter_number_loaded_rules', 'Rewriter_number_reloads',
                    'Rewriter_number_rewritten_queries', 'Rewriter_reload_error'))
    status = dict(cursor.fetchall())
    # The stored procedure is supplied by the native plugin installer. Retain a
    # digest rather than duplicating a potentially customized routine body.
    cursor.execute('SHOW CREATE PROCEDURE query_rewrite.flush_rewrite_rules')
    routine = cursor.fetchone()
    if not routine or not isinstance(routine[2], str) or not routine[2]:
        raise RelationalClientError('The native Rewriter reload procedure definition must be visible')
    routine_hash = hashlib.sha256(json.dumps(list(routine), ensure_ascii=False, default=str).encode('utf8')).hexdigest()
    return {'plugin': list(plugin), 'reload_procedure_sha256': routine_hash,
            'rules': rules, 'native_status': status,
            'in_memory_rules_enumerated': False, 'complete_stored_rules': True}


def binding(observation, operation, rule_id):
    result = {key: observation[key] for key in ('plugin', 'reload_procedure_sha256')}
    if operation == 'reload_rewrite_rules':
        result['rules'] = observation['rules']
    elif rule_id is not None:
        matches = [row for row in observation['rules'] if row['id'] == rule_id]
        if len(matches) != 1:
            raise RelationalClientError('The selected native rewrite rule no longer exists')
        result['rule'] = matches[0]
    return result


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_rewriter']
    handle = client._connect({'route': payload['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor()
        identity = environment(cursor)
        if identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Native MySQL instance differs from the selected Rewriter server')
        before = observe(cursor)
        intent['review'] = {'execution_identity': identity,
                            'binding': binding(before, intent['operation'], intent['rule_id'])}
        planned['command_preview'].update(native_execution_identity=identity, native_rewriter=before)
        return planned
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Rewriter management requires an independently owned connection')
    compiled = request['provider_payload']['compiled']; intent = compiled['mysql_rewriter']
    checked = deepcopy(compiled); review = checked['mysql_rewriter'].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native Rewriter operation before dispatch')
    handle = client._connect({'route': request['provider_payload']['route']}); cursor = None
    dispatched = acknowledged = commit_requested = commit_acknowledged = False
    operation = intent['operation']; after = None; observation_error = None; native_warnings = []
    inserted_id = None
    try:
        handle.autocommit = True; handle.get_warnings = True; handle.raise_on_warnings = False
        cursor = handle.cursor(); identity = environment(cursor)
        if identity != review['execution_identity']:
            raise RelationalClientError('Native Rewriter execution identity changed since review')
        cursor.execute('SET SESSION innodb_lock_wait_timeout=15')
        cursor.execute('SET SESSION lock_wait_timeout=15')
        before = observe(cursor)
        if operation != 'inspect_rewrite_rules' and binding(before, operation, intent['rule_id']) != review['binding']:
            raise RelationalClientError('Native Rewriter definition or selected rules changed since review')
        editing = operation in {'create_rewrite_rule', 'alter_rewrite_rule', 'drop_rewrite_rule'}
        if editing:
            handle.autocommit = False
            # Open the table in this transaction before verifying its engine.
            # The native metadata lock then prevents a concurrent engine swap.
            cursor.execute('SELECT id FROM query_rewrite.rewrite_rules LIMIT 0')
            cursor.fetchall()
            cursor.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA='query_rewrite' AND TABLE_NAME='rewrite_rules'")
            if cursor.fetchone() != ('InnoDB',):
                raise RelationalClientError('The native rule table engine changed before editing')
            if intent['rule_id'] is not None:
                cursor.execute(SELECT + ' WHERE id=%s FOR UPDATE', (intent['rule_id'],))
                locked = bounded(cursor.fetchall())
                if locked != [review['binding']['rule']]:
                    raise RelationalClientError('The locked native rewrite rule changed since review')
        if operation == 'inspect_rewrite_rules':
            after = before; acknowledged = True
        else:
            statement = compiled['statements'][0]; dispatched = True
            cursor.execute(statement['source'], statement['parameters'])
            if operation == 'create_rewrite_rule': inserted_id = cursor.lastrowid
            # CALL can have an additional empty result set. Drain it before any
            # observer query, retaining errors from the native procedure.
            if cursor.with_rows: cursor.fetchall()
            while cursor.nextset():
                if cursor.with_rows: cursor.fetchall()
            acknowledged = True
            native_warnings = [{'level': level, 'code': code, 'message': message}
                               for level, code, message in (cursor.warnings or ())]
            if editing:
                commit_requested = True; handle.commit(); commit_acknowledged = True
                handle.autocommit = True
            try:
                after = observe(cursor)
            except Exception as error:
                observation_error = {'available': False, 'error_type': type(error).__name__,
                                     'native_error_code': getattr(error, 'errno', None)}
        return {
            'accepted': True, 'native_implicit_commit': operation == 'reload_rewrite_rules',
            'commit_requested': commit_requested, 'rollback_requested': False,
            'staged_in_provider_session': False, 'automatic_retry': False,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'native_warnings': native_warnings,
            'rewriter_observation': {'operation': operation, 'execution_identity': identity,
                                    'native_dispatched': dispatched, 'native_acknowledged': acknowledged,
                                    'native_commit_acknowledged': commit_acknowledged, 'inserted_rule_id': inserted_id,
                                    'stored_table_only': editing, 'reload_requested': operation == 'reload_rewrite_rules',
                                    'before': before, 'after': after, 'later_observation_error': observation_error,
                                    'query_rewrite_effectiveness_asserted': False},
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError('Native MySQL Rewriter operation failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.commit_requested = commit_requested; failure.native_commit_acknowledged = commit_acknowledged
        failure.automatic_retry = False; failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)
