"""Qualify unloaded MySQL component settings and durable reset receipts."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output):
    import config  # noqa: F401
    import mysql.connector
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.providers.mysql_server_application import apply_operation
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
    from pgadmin.cdeadmin.workspace.mysql_server_apply import MySQLServerApplications

    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    paths = ['tools/cdeadmin_mysql_persisted_variables_qualification.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/system_variables.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/mysql_server_catalog.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
             'web/pgadmin/cdeadmin/providers/mysql_server_application.py',
             'web/pgadmin/cdeadmin/workspace/mysql_server_plan.py',
             'web/pgadmin/cdeadmin/workspace/mysql_server_apply.py']
    proof = {'complete': False, 'full_product_complete': False,
             'history_testing': 'not run', 'checks': [],
             'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output / 'fixture') as (route, _name, owned):
            observer = _root_connection('mysql', route['port'])
            observer.autocommit = True
            cursor = observer.cursor()
            try:
                for pure in (True, False):
                    for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        connection = mysql.connector.connect(**{**route, 'use_pure': pure})
                        connection.autocommit = True
                        selected = connection.cursor()
                        try:
                            selected.execute('SET SESSION sql_mode=%s', (mode,))
                            selected.execute("INSTALL COMPONENT 'file://component_validate_password'")
                            selected.execute('SET PERSIST_ONLY `validate_password.length` = 12')
                            selected.execute("UNINSTALL COMPONENT 'file://component_validate_password'")
                            selected.execute("SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='validate_password.length'")
                            assert selected.fetchone() == ('12',)
                            selected.execute("SELECT VARIABLE_VALUE FROM performance_schema.global_variables WHERE VARIABLE_NAME='validate_password.length'")
                            assert selected.fetchone() is None

                            def current():
                                acquired = capture(connection)
                                return build_export(acquired['resources'], endpoint_id='owned',
                                    target_id='server:' + acquired['server_uuid'], generation=acquired['generation'],
                                    include_system=True, refreshed=True, engine='mysql', native_model=True)

                            baseline = current()
                            row = next(item for item in baseline['rows'].values() if item['kind'] == 'system-variable' and item['name'] == 'validate_password.length')
                            facts = row['native']['catalog_row']
                            assert facts['global_present'] == 0 and facts['persisted_present'] == 1
                            assert facts['global_value'] is None and facts['persisted_value'] is None and facts['persisted_value_redacted'] == 1
                            native = next(item for item in _resources(connection, {'route': {}}, MYSQL_PROFILE)
                                if item['resource_kind'] == 'system-variable' and item['display_name'] == row['name'])['native']
                            assert native['persisted_present'] == 1 and native['persisted_value_redacted'] == 1 and native['persisted_value'] is None
                            desired = deepcopy(baseline)
                            desired['rows'][row['resource_id']]['native']['mysql_change'] = {
                                'action': 'reset_persist', 'draft': {}, 'confirmation': row['name']}
                            preview = plan(baseline, desired, baseline)
                            preview['endpoint_id'] = 'owned'
                            assert preview['ready_for_review'] and len(preview['operations']) == 1, preview
                            store_path = output / ('receipts-' + str(pure) + '-' + str(bool(mode)) + '.json')
                            store = MySQLServerApplications(store_path)
                            review = store.review(preview, baseline, desired, 1, 'owned')
                            request = {'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True}
                            calls = []
                            def execute(record, operation):
                                calls.append(operation['source'])
                                return apply_operation(connection, record, operation)
                            applied = store.apply(request, 1, 'owned', execute)
                            assert applied['state'] == 'acknowledged', applied
                            outcome = applied['statement_outcomes'][0]['outcome']
                            assert outcome['rediscovery_verified'] and outcome['native_observation'] is None
                            assert outcome['reviewed_value_scope'].startswith('identity-and-presence')
                            selected.execute("SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='validate_password.length'")
                            assert selected.fetchone() is None
                            assert not any(item['kind'] == 'system-variable' and item['name'] == row['name'] for item in current()['rows'].values())
                            restarted = MySQLServerApplications(store_path)
                            assert restarted.apply(request, 1, 'owned', execute)['state'] == 'acknowledged'
                            assert len(calls) == 1
                            proof['checks'].append({'use_pure': pure, 'sql_mode': mode,
                                'native_persisted_only_discovery_verified': True,
                                'navigator_and_ddn_preserve_identity_and_redact_value': True,
                                'durable_reset_and_authoritative_disappearance_verified': True,
                                'restart_duplicate_did_not_redispatch': True})
                        finally:
                            selected.close()
                            connection.close()
                cursor.execute("CREATE USER 'sr_variable_observer'@'%'")
                for table in ('global_variables', 'persisted_variables', 'variables_info'):
                    cursor.execute("GRANT SELECT ON performance_schema." + table + " TO 'sr_variable_observer'@'%'")
                cursor.execute("INSTALL COMPONENT 'file://component_validate_password'")
                cursor.execute('SET PERSIST_ONLY `validate_password.length`=12')
                cursor.execute("UNINSTALL COMPONENT 'file://component_validate_password'")
                restricted = mysql.connector.connect(**{**route, 'user': 'sr_variable_observer'})
                try:
                    acquired = capture(restricted)
                    resource = next(item for item in acquired['resources'] if item['resource_kind'] == 'system-variable' and item['display_name'] == 'validate_password.length')
                    assert resource['native']['catalog_row']['persisted_value_redacted'] == 1
                    assert resource['native']['catalog_row']['persisted_value'] is None
                    assert any(item['section'] == 'accounts' and not item['available'] for item in acquired['observations'])
                finally:
                    restricted.close()
                cursor.execute("REVOKE SELECT ON performance_schema.persisted_variables FROM 'sr_variable_observer'@'%'")
                restricted = mysql.connector.connect(**{**route, 'user': 'sr_variable_observer'})
                try:
                    acquired = capture(restricted)
                    # This native Performance Schema table uses a world-read
                    # ACL. Revoking an explicit SELECT grant does not hide it.
                    assert next(item for item in acquired['observations'] if item['section'] == 'system-variables')['available'] is True
                    resource = next(item for item in acquired['resources'] if item['resource_kind'] == 'system-variable' and item['display_name'] == 'validate_password.length')
                    assert resource['native']['catalog_row']['persisted_value_redacted'] == 1
                    denied = restricted.cursor()
                    try:
                        denied.execute('RESET PERSIST `validate_password.length`')
                    except mysql.connector.Error as error:
                        assert error.errno == 1227 and error.sqlstate == '42000'
                    else:
                        raise AssertionError('Restricted native reset unexpectedly succeeded')
                    finally:
                        denied.close()
                finally:
                    restricted.close()
                cursor.execute("SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='validate_password.length'")
                assert cursor.fetchone() == ('12',)
                cursor.execute('RESET PERSIST `validate_password.length`')
                proof['restricted_catalog_and_permission_denial_verified'] = True
                proof['native_engine'] = owned
                proof['complete'] = True
            finally:
                cursor.close()
                observer.close()
    finally:
        (output / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    qualify(parser.parse_args().evidence)
