"""Qualify MariaDB GLOBAL value modes on an owned, disposable 12.2.2 server.

Run from an immutable DDN-refreshed source snapshot. Output belongs in the
owner-designated work area. This does not qualify authenticated HTTP, all
variables, session assignment or ScratchBird history.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import sys
import json
import hashlib

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    W = args.output.resolve()
    W.mkdir(parents=True, exist_ok=True)
    R = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(R), str(R / 'web'), str(R / 'tools')]
    import config
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MARIADB_PROFILE, MARIADB_ADMINISTRATION
    proof = {'complete': False, 'history_testing': 'not run', 'scope': 'Owned MariaDB12.2.2 fixture; actual native variable metadata, production validation/plan/apply and independent GLOBAL read-back. No authenticated HTTP claim.', 'checks': [], 'source_sha256': {p: hashlib.sha256((R / p).read_bytes()).hexdigest() for p in ['web/pgadmin/cdeadmin/providers/relational_admin.py', 'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_variables.py', 'web/pgadmin/cdeadmin/workspace/service.py', 'web/pgadmin/cdeadmin/ui_descriptors/mariadb/operations.json', 'tools/cdeadmin_mariadb_variables_qualification.py']}}
    try:
        with server(W / 'mariadb-variable-fixture') as (route, name, fixture):
            native = _root_connection('mariadb', route['port'])
            native.autocommit = True
            native.cursor().execute('CREATE DATABASE owned_variables')
            route = {**route, 'database': 'owned_variables'}
            route, permissions = provider_access(route)
            client = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace='owned-variable-qualification'))
            try:
                for variable, requested in [('SORT_BUFFER_SIZE', None), ('OPTIMIZER_SWITCH', 'mrr=on'), ('OPTIMIZER_TRACE', 'enabled=on')]:
                    cursor = native.cursor(dictionary=True)
                    cursor.execute('SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,ENUM_VALUE_LIST,GLOBAL_VALUE,DEFAULT_VALUE FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME=?', (variable,))
                    metadata = {k.lower(): v for k, v in cursor.fetchone().items()}
                    cursor.close()
                    if requested is None:
                        requested = str(int(metadata['global_value']) + 1024)
                    target = {'resource_kind': 'system-variable', 'display_name': variable, 'display_path': ['Configuration', variable], 'native': metadata}
                    request = {'resource_kind': 'system-variable', 'operation_id': 'set_global', 'draft': {'value_mode': 'VALUE', 'value': requested}, 'target_resource': target, '_provider_route': route}
                    validation = client.validate_admin_operation(request)
                    assert not validation['errors'], validation
                    planned = client.plan_admin_operation(request)
                    applied = client.apply_admin_operation(planned)
                    assert applied['accepted']
                    cursor = native.cursor()
                    cursor.execute('SELECT @@GLOBAL.' + variable)
                    observed = cursor.fetchone()[0]
                    cursor.close()
                    text = observed.decode() if isinstance(observed, bytes) else str(observed)
                    assert requested in text if '=' in requested else text == requested, (requested, text)
                    proof['checks'].append({'variable': variable, 'native_scope': metadata['variable_scope'], 'native_type': metadata['variable_type'], 'production_apply_acknowledged': True, 'independent_global_value_matches': True})
                for mask in ['0', '1', '2', '3']:
                    cursor = native.cursor(dictionary=True)
                    cursor.execute("SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,ENUM_VALUE_LIST FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME='OPTIMIZER_TRACE'")
                    metadata = {k.lower(): v for k, v in cursor.fetchone().items()}
                    cursor.close()
                    target = {'resource_kind': 'system-variable', 'display_name': 'OPTIMIZER_TRACE', 'display_path': ['Configuration', 'OPTIMIZER_TRACE'], 'native': metadata}
                    request = {'resource_kind': 'system-variable', 'operation_id': 'set_global', 'draft': {'value_mode': 'BITMASK', 'bitmask': mask}, 'target_resource': target, '_provider_route': route}
                    validation = client.validate_admin_operation(request)
                    assert not validation['errors'], validation
                    planned = client.plan_admin_operation(request)
                    applied = client.apply_admin_operation(planned)
                    assert applied['accepted']
                    cursor = native.cursor()
                    cursor.execute('SELECT @@GLOBAL.optimizer_trace')
                    observed = cursor.fetchone()[0]
                    cursor.close()
                    assert observed == 'enabled=' + ('on' if int(mask) & 1 else 'off'), observed
                    proof['checks'].append({'variable': 'OPTIMIZER_TRACE', 'numeric_mask': mask, 'production_apply_acknowledged': True, 'independent_global_value_matches': True})
                request['draft']['bitmask'] = '4'
                assert client.validate_admin_operation(request)['errors']
                proof['numeric_out_of_range_refused'] = True
                from ui_descriptor_roundtrip import engine_operations, operation_draft
                descriptor = engine_operations('mariadb')['set_global@system-variable']
                cursor = native.cursor()
                cursor.execute("SET SESSION optimizer_switch='mrr=off'")
                cursor.close()
                for reset, rows in [(False, [{'flag': 'mrr', 'state': 'on'}]), (False, [{'flag': 'mrr', 'state': 'off'}]), (True, []), (True, [{'flag': 'mrr', 'state': 'on'}]), (False, [{'flag': 'mrr', 'state': 'default'}]), (False, [])]:
                    cursor = native.cursor(dictionary=True)
                    cursor.execute("SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,ENUM_VALUE_LIST,DEFAULT_VALUE FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME='OPTIMIZER_SWITCH'")
                    metadata = {k.lower(): v for k, v in cursor.fetchone().items()}
                    cursor.close()
                    cursor = native.cursor()
                    cursor.execute('SELECT @@GLOBAL.optimizer_switch')
                    before = dict((item.split('=') for item in cursor.fetchone()[0].split(',')))
                    cursor.close()
                    draft = operation_draft(descriptor, {'value_mode': 'FLAGS', 'flags': rows, 'reset_defaults': reset})
                    target = {'resource_kind': 'system-variable', 'display_name': 'OPTIMIZER_SWITCH', 'display_path': ['Configuration', 'OPTIMIZER_SWITCH'], 'native': metadata}
                    request = {'resource_kind': 'system-variable', 'operation_id': 'set_global', 'draft': draft, 'target_resource': target, '_provider_route': route}
                    validation = client.validate_admin_operation(request)
                    assert not validation['errors'], validation
                    planned = client.plan_admin_operation(request)
                    applied = client.apply_admin_operation(planned)
                    assert applied['accepted']
                    cursor = native.cursor()
                    cursor.execute('SELECT @@GLOBAL.optimizer_switch,@@SESSION.optimizer_switch')
                    global_text, session_text = cursor.fetchone()
                    cursor.close()
                    observed = dict((item.split('=') for item in global_text.split(',')))
                    original = dict((item.split('=') for item in session_text.split(',')))
                    defaults = dict((item.split('=') for item in metadata['default_value'].split(',')))
                    expected = dict(defaults if reset else before)
                    for row in rows:
                        expected[row['flag']] = defaults[row['flag']] if row['state'] == 'default' else row['state']
                    assert observed == expected, (observed, expected)
                    assert original['mrr'] == 'off'
                    proof['checks'].append({'variable': 'OPTIMIZER_SWITCH', 'structured_flags': rows, 'reset_defaults': reset, 'descriptor_draft': True, 'production_apply_acknowledged': True, 'independent_global_value_matches': True, 'existing_session_unchanged': True})
                cursor = native.cursor(dictionary=True)
                cursor.execute("SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_SCOPE='SESSION ONLY' AND READ_ONLY='NO' LIMIT 1")
                only = cursor.fetchone()
                cursor.close()
                assert only
                target = {'display_name': only['VARIABLE_NAME'], 'native': {k.lower(): v for k, v in only.items()}}
                errors = MARIADB_ADMINISTRATION._validate_mariadb_system_variable({'value_mode': 'DEFAULT'}, target)
                assert any((e['code'] == 'mariadb_system_variable_not_global' for e in errors))
                proof['session_only_native_scope_refused'] = True
            finally:
                client.close()
                native.close()
        proof['fixture_cleanup'] = json.loads((W / 'mariadb-variable-fixture/fixture.json').read_text())
        assert proof['fixture_cleanup']['owned_server_stopped']
        proof['complete'] = True
    finally:
        (W / 'mariadb-variable-native.json').write_text(json.dumps(proof, indent=2, default=str) + '\n')
    print('MariaDB native variable scope/FLAGSET controls passed', len(proof['checks']))
if __name__ == '__main__':
    main()
