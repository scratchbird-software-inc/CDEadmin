"""Recompile, revalidate and execute one reviewed server operation exactly once."""
from decimal import Decimal, InvalidOperation
import hashlib

from ..workspace.firebird_schema_plan import digest
from ..workspace.firebird_catalog_export import build_export
from ..workspace.mysql_server_plan import compile_operation, state
from .mysql_family.mysql_server_catalog import capture


def same(left, right):
    def scalar(value):
        text = str(value).upper()
        if text in {'TRUE', 'ON', 'YES'}:
            return Decimal(1)
        if text in {'FALSE', 'OFF', 'NO'}:
            return Decimal(0)
        try:
            return Decimal(text)
        except InvalidOperation:
            return text
    return scalar(left) == scalar(right)


def effect(row, operation, live):
    action, kind = operation['operation'], row['kind']
    observed = live['rows'].get(row['resource_id'])
    facts = observed['native']['catalog_row'] if observed else {}
    draft = row['native']['mysql_change'].get('draft', {})
    if action in {'drop', 'revoke'} or kind == 'replication-channel' and action == 'reset' and draft.get('delete_connection', True):
        return observed is None
    if kind == 'user' and action == 'rename':
        return observed is None and any(item['kind'] == 'user' and
            item['native']['catalog_row'].get('user') == draft['new_user'] and
            item['native']['catalog_row'].get('host') == draft['new_host'] for item in live['rows'].values())
    if observed is None:
        if kind == 'tablespace' and action == 'rename':
            return any(item['kind'] == 'tablespace' and item['native']['catalog_row'].get('name') == draft['new_name'] for item in live['rows'].values())
        if kind == 'default-role' and draft.get('mode') == 'NONE':
            old = row['native']['catalog_row']
            return not any(item['kind'] == 'default-role' and all(item['native']['catalog_row'][key] == old[key] for key in ('user', 'host')) for item in live['rows'].values())
        return False
    if kind == 'user':
        return facts.get('account_locked') == ('Y' if action == 'create' or not draft.get('active', False) else 'N')
    if kind == 'role-membership':
        return facts.get('with_admin_option') == ('Y' if draft.get('admin_option') else 'N')
    if kind == 'privilege':
        return facts.get('is_grantable') == ('YES' if draft.get('grant_option') else 'NO')
    if kind == 'system-variable':
        if action == 'reset_persist':
            return facts.get('persisted_value') is None
        if draft.get('value_mode', 'VALUE') == 'DEFAULT':
            return True  # Native DEFAULT acknowledgement, without guessing its value.
        keys = ['global_value'] if action == 'set_global' else ['persisted_value'] if action == 'set_persist_only' else ['global_value', 'persisted_value']
        return all(same(facts.get(key), draft['value']) for key in keys)
    if kind == 'resource-group':
        return (action == 'create' and same(facts.get('resource_group_enabled'), draft.get('enabled', True)) or
                action == 'alter' and ('state' not in draft or same(facts.get('resource_group_enabled'), draft['state'] == 'ENABLE')))
    if kind == 'tablespace' and action == 'alter':
        change = draft.get('change')
        if change in {'ENCRYPTION', 'AUTOEXTEND_SIZE'}:
            return same(facts.get(change.lower()), draft[change.lower()])
        if change in {'ACTIVE', 'INACTIVE'}:
            return facts.get('state') == ('active' if change == 'ACTIVE' else 'inactive') or change == 'INACTIVE' and facts.get('state') == 'empty'
    if kind == 'plugin':
        return facts.get('plugin_status') == 'ACTIVE'
    return bool(facts)


def apply_operation(connection, record, operation):
    dispatched = acknowledged = False
    result = {'state': 'not_dispatched', 'rediscovery_verified': False, 'automatic_retry': False,
              'concurrent_external_administration_fenced': False, 'durability': 'native-operation-specific'}
    cursor = None
    locked = False
    lock = 'sr-server:' + hashlib.sha256(operation['resource_id'].encode()).hexdigest()[:54]
    try:
        plan = record['plan']
        row = record['desired']['rows'][operation['resource_id']]
        statement = compile_operation(row)
        if (plan.get('format') != 'scratchrobin.mysql.server-plan@1' or
                plan['execution_sha256'] != digest(plan['operations']) or
                operation['desired_sha256'] != digest(row) or
                statement['source'] != operation['source'] or list(statement['parameters']) != operation['parameters']):
            raise ValueError('Reviewed server statement changed')
        if connection.in_transaction:
            raise ValueError('Server application requires an independently owned idle connection')
        connection.autocommit = True
        connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
        cursor = connection.cursor()
        cursor.execute('SELECT VERSION(),@@server_uuid')
        identity = cursor.fetchone()
        if identity[0].split('-')[0] != '9.7.0' or identity[1] != plan['server_uuid']:
            raise ValueError('Native server application identity changed')
        cursor.execute('SET SESSION lock_wait_timeout=2')
        cursor.execute('SELECT GET_LOCK(%s,2)', (lock,))
        locked = cursor.fetchone()[0] == 1
        if not locked:
            raise ValueError('Server operation lock is unavailable')
        def current():
            acquired = capture(connection)
            return build_export(acquired['resources'], endpoint_id=plan['endpoint_id'],
                target_id='server:' + plan['server_uuid'], generation=acquired['generation'],
                include_system=True, refreshed=True, engine='mysql', native_model=True)
        live = current()
        root = next(item for item in live['rows'].values() if item['kind'] == 'server')
        available = {item['section']: item['available']
                     for item in root['native']['catalog_observations']}
        if not available.get(row['native']['section']):
            raise ValueError('Native catalog section is unavailable before dispatch')
        if row['kind'] == 'privilege' and not available.get('accounts'):
            raise ValueError('Separate native account identities are unavailable before dispatch')
        key = operation['resource_id']
        if digest(state(live['rows'].get(key))) != operation['baseline_sha256']:
            raise ValueError('Native server object changed since review')
        guard_ids = operation['guard_ids']
        if row['kind'] == 'default-role':
            old = row['native']['catalog_row']
            guard_ids = [uid for uid, item in live['rows'].items() if item['kind'] == 'default-role' and
                         all(item['native']['catalog_row'][name] == old[name] for name in ('user', 'host'))]
        if digest({uid: state(live['rows'][uid]) for uid in guard_ids if uid in live['rows']}) != operation['guard_sha256']:
            raise ValueError('Native server object sibling set changed since review')
        dispatched = True
        cursor.execute(statement['source'], statement['parameters'] or None)
        if cursor.description:
            cursor.fetchall()
        acknowledged = True
        result['state'] = 'acknowledged'
        observed = current()
        result['rediscovery_verified'] = effect(row, operation, observed)
        result['native_observation'] = state(observed['rows'].get(key))
    except Exception as error:
        native_refusal = (isinstance(getattr(error, 'errno', None), int) and error.errno >= 1000 and
                          not 2000 <= error.errno < 3000 and isinstance(getattr(error, 'sqlstate', None), str))
        result.update(state='acknowledged' if acknowledged else 'refused' if dispatched and native_refusal else
                      'unknown_outcome' if dispatched else 'not_dispatched', error_type=type(error).__name__,
                      error_code=getattr(error, 'errno', None))
        if not dispatched and isinstance(error, ValueError):
            result['rejection_reason'] = str(error)
    finally:
        if cursor is not None:
            if locked:
                try:
                    cursor.execute('SELECT RELEASE_LOCK(%s)', (lock,))
                    cursor.fetchone()
                except Exception:
                    pass
            try:
                cursor.close()
            except Exception:
                pass
    return result
