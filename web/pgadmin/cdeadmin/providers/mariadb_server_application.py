"""Recompile, revalidate and execute one reviewed server operation exactly once."""
from decimal import Decimal, InvalidOperation
import hashlib

from ..workspace.firebird_schema_plan import digest
from ..workspace.firebird_catalog_export import build_export
from ..workspace.mariadb_server_plan import compile_operation, state
from .mysql_family.mariadb_server_catalog import capture


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
    draft = row['native']['mariadb_change'].get('draft', {})
    if kind == 'role-membership' and action == 'revoke' and draft.get('admin_option_only'):
        return observed is not None and facts.get('admin_option') == 'N'
    if kind == 'privilege' and action == 'revoke' and draft.get('grant_option_only'):
        return observed is None or facts.get('is_grantable') == 'NO'
    if action in {'drop', 'revoke'} or kind == 'replication-channel' and action == 'reset' and draft.get('delete_connection', True):
        return observed is None
    if kind == 'user' and action == 'rename':
        return observed is None and any(item['kind'] == 'user' and
            item['native']['catalog_row'].get('user') == draft['new_user'] and
            item['native']['catalog_row'].get('host') == draft['new_host'] for item in live['rows'].values())
    if kind == 'role' and action == 'set_default':
        matches = [item['native']['catalog_row'] for item in live['rows'].values() if item['kind'] == 'user' and
            item['native']['catalog_row'].get('user') == draft['member_user'] and
            item['native']['catalog_row'].get('host') == draft['member_host']]
        return len(matches) == 1 and matches[0]['default_role'] == (row['native']['catalog_row']['user'] if draft['mode'] == 'SELECTED' else '')
    if observed is None:
        return False
    if kind == 'role-membership':
        return facts.get('admin_option') == ('Y' if draft.get('admin_option') else 'N')
    if kind == 'privilege':
        return facts.get('is_grantable') == ('YES' if draft.get('grant_option') else 'NO')
    if kind == 'system-variable':
        if draft.get('value_mode') == 'DEFAULT':
            return facts.get('default_value') is not None and same(facts.get('global_value'), facts['default_value'])
        return same(facts.get('global_value'), draft['value'])
    if kind == 'server-link' and action == 'alter':
        mapping = {'host':'host','database':'db','username':'username','port':'port','socket':'socket','owner':'owner'}
        return all((same(facts.get(mapping[key]), draft.get(key, 3306)) if key == 'port' else
                    facts.get(mapping[key]) == draft.get(key, ''))
            for key in mapping if draft.get('change_' + key))
    if kind == 'plugin':
        return facts.get('plugin_status') == 'ACTIVE'
    if kind == 'loadable-function' and action == 'create':
        return (facts.get('dl') == draft['library'] and
                facts.get('ret') == {'STRING':0,'REAL':1,'INTEGER':2,'DECIMAL':4}[draft['return_type']] and
                facts.get('type') == ('aggregate' if draft.get('aggregate') else 'function'))
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
        if (plan.get('format') != 'scratchrobin.mariadb.server-plan@1' or
                plan['execution_sha256'] != digest(plan['operations']) or
                operation['desired_sha256'] != digest(row) or
                statement['source'] != operation['source'] or list(statement['parameters']) != operation['parameters']):
            raise ValueError('Reviewed server statement changed')
        if (connection.server_status & 1):
            raise ValueError('Server application requires an independently owned idle connection')
        connection.autocommit = True
        encoding = connection.cursor(); encoding.execute('SET NAMES utf8mb4'); encoding.close()
        cursor = connection.cursor()
        cursor.execute('SELECT VERSION(),@@server_uid')
        identity = cursor.fetchone()
        if identity[0].split('-')[0] != '12.2.2' or identity[1] != plan['server_uid']:
            raise ValueError('Native server application identity changed')
        cursor.execute('SET SESSION lock_wait_timeout=2')
        cursor.execute('SELECT GET_LOCK(%s,2)', (lock,))
        locked = cursor.fetchone()[0] == 1
        if not locked:
            raise ValueError('Server operation lock is unavailable')
        def current():
            acquired = capture(connection)
            return build_export(acquired['resources'], endpoint_id=plan['endpoint_id'],
                target_id='server:' + plan['server_uid'], generation=acquired['generation'],
                include_system=True, refreshed=True, engine='mariadb', native_model=True)
        live = current()
        root = next(item for item in live['rows'].values() if item['kind'] == 'server')
        available = {item['section']: item['available']
                     for item in root['native']['catalog_observations']}
        if not available.get(row['native']['section']):
            raise ValueError('Native catalog section is unavailable before dispatch')
        if row['kind'] == 'user' and operation['operation'] in {'create','alter'} and not available.get('account-lock-state'):
            raise ValueError('Native account-lock state is unavailable before dispatch')
        if row['kind'] == 'privilege' and not available.get('accounts'):
            raise ValueError('Separate native account identities are unavailable before dispatch')
        key = operation['resource_id']
        if digest(state(live['rows'].get(key))) != operation['baseline_sha256']:
            raise ValueError('Native server object changed since review')
        guard_ids = operation['guard_ids']
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
        if row['kind'] == 'user' and operation['operation'] in {'create', 'alter'}:
            account_facts = row['native']['catalog_row']
            cursor.execute("SELECT COALESCE(JSON_VALUE(Priv,'$.account_locked'),'false') IN ('true','1') FROM mysql.global_priv WHERE User=%s AND Host=%s", (account_facts['user'], account_facts['host']))
            locked_state = cursor.fetchone()
            result['rediscovery_verified'] = locked_state is not None and bool(locked_state[0]) == (operation['operation'] == 'create' or not row['native']['mariadb_change']['draft']['active'])
            result['account_state_observation'] = 'native-locked-boolean-only'
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
