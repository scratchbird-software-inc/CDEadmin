"""Qualify installed MySQL plugin/runtime-function metadata and DDN boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True, exist_ok=False); app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, _create_client, _resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.providers.mysql_family.installed_catalog import PLUGINS, PLUGIN_COLUMNS, FUNCTIONS
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.security import SecretLease
    from cdeadmin_mysql_online_ddl_qualification import registration
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/'+n for n in
             ['provider.py','installed_catalog.py','mysql_server_catalog.py']]
    paths += ['web/pgadmin/cdeadmin/workspace/mysql_server_plan.py', str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'application': [],
             'history_testing': 'ScratchBird history not run', 'full_native_inventory_complete': False,
             'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output/'fixture', keyring=True) as (route, _container, owned):
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc'); q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute("INSTALL PLUGIN keyring_udf SONAME 'keyring_udf.so'")
                q.execute("CREATE FUNCTION keyring_key_type_fetch RETURNS STRING SONAME 'keyring_udf.so'")
                q.execute("INSTALL COMPONENT 'file://component_mysqlbackup'")
                q.execute('SELECT @@server_uuid'); server_uuid = q.fetchone()[0]
                def records(source):
                    q.execute(source); columns = [row[0].lower() for row in q.description]
                    return [dict(zip(columns, row)) for row in q.fetchall()]
                expected_plugins = {row['plugin_name']: row for row in records(PLUGINS)}
                expected_functions = {row['udf_name']: row for row in records(FUNCTIONS)}
                assert expected_functions['keyring_key_type_fetch']['udf_library'] == 'keyring_udf.so'
                assert any(row['udf_library'] is None for row in expected_functions.values())
                names = [key.lower() for key in PLUGIN_COLUMNS]
                def compare_explorer(rows):
                    rows = [{**row, 'native': row.get('native') or row.get('extensions', {}).get('mysql', {}).get('native')} for row in rows]
                    actual = {row['display_name']: row for row in rows if row['resource_kind'] == 'plugin'}
                    assert set(actual) == set(expected_plugins)
                    for name, record in actual.items():
                        assert {key: record['native'][key] for key in names} == expected_plugins[name]
                        assert record['native']['definition']['plugin_description'] == expected_plugins[name]['plugin_description']
                        assert record['native']['library'] == expected_plugins[name]['plugin_library']
                    functions = {row['display_name']: row for row in rows if row['resource_kind'] == 'loadable-function'}
                    assert set(functions) == set(expected_functions)
                    assert functions['keyring_key_type_fetch']['native']['administration']['allowed_operations'] == ['inspect','drop']
                    for name, facts in expected_functions.items():
                        actual = functions[name]['native']
                        assert {key: actual[key] for key in facts if key != 'udf_usage_count'} == {key: value for key, value in facts.items() if key != 'udf_usage_count'}
                        assert type(actual['udf_usage_count']) is int and actual['udf_usage_count'] >= 0
                        if facts['udf_library'] is None:
                            assert actual['administration']['allowed_operations'] == ['inspect']
                def compare_ddn(snapshot):
                    parsed = read_catalog(json.dumps(snapshot), engine='mysql')
                    plugins = {row['native']['catalog_row']['plugin_name']: row['native']['catalog_row']
                               for row in parsed['rows'].values() if row['kind'] == 'plugin'}
                    assert plugins == expected_plugins
                    functions = {row['native']['catalog_row']['udf_name']: row['native']['catalog_row']
                                 for row in parsed['rows'].values() if row['kind'] == 'loadable-function'}
                    assert set(functions) == set(expected_functions)
                    assert all(facts['udf_library'] == expected_functions[name]['udf_library'] for name,facts in functions.items())
                    return parsed
                for pure in (True, False):
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    selected = {**route, 'database': 'sr_osc', 'use_pure': pure, 'autocommit': True}
                    try:
                        oracle.autocommit = False; q.execute('SAVEPOINT catalog_guard'); q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                        handle = client._connect({'route': selected})
                        native_class = type(handle).__name__
                        assert native_class == ('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection')
                        try:
                            compare_explorer(_resources(handle, {'route': selected}, MYSQL_PROFILE))
                            captured = capture(handle)
                        finally: client._forget_and_close(handle)
                        q.execute('SELECT ROW_COUNT()'); assert q.fetchone() == (1,)
                        q.execute('ROLLBACK TO SAVEPOINT catalog_guard'); oracle.rollback(); oracle.autocommit = True
                        exported = build_export(captured['resources'], endpoint_id='owned', target_id='server:'+server_uuid,
                                                generation=captured['generation'], engine='mysql')
                        compare_ddn(exported['snapshot'])
                        q.execute("SELECT CAST('catalog-warning' AS UNSIGNED)"); q.fetchall()
                        q.execute('SHOW WARNINGS'); warning = q.fetchall(); assert warning
                        handle = client._connect({'route': selected})
                        try: capture(handle)
                        finally: client._forget_and_close(handle)
                        q.execute('SHOW WARNINGS'); assert q.fetchall() == warning
                        proof['interfaces'].append({'use_pure': pure, 'native_connection_class': native_class,
                            'complete': True, 'all_eleven_plugin_fields': True, 'runtime_functions_captured': True,
                            'native_null_library_and_registration_distinguished': True,
                            'native_metadata_survives_ddn': True, 'original_diagnostics_and_savepoint_preserved': True})
                    finally: client.close()
                password = secrets.token_urlsafe(24); q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                for pure in (True, False):
                    sid, target, post = registration(app, route, password, not pure)
                    page = post('resource_page', {}); rows = list(page['items'])
                    while page.get('next_cursor'):
                        page = post('resource_page', {'continuation': page['next_cursor'], 'generation': page['generation']})
                        rows.extend(page['items'])
                    # Resource pages are navigator DTOs. Native facts arrive
                    # through authenticated, generation-bound inspection.
                    relevant = [row for row in rows if row['resource_kind'] in {'plugin','loadable-function'}]
                    inspected = []
                    for row in relevant:
                        detail = post('resource_inspect', {'resource_id': row['resource_id'], 'generation': page['generation']})
                        inspected.append(detail)
                    compare_explorer(inspected)
                    from flask import url_for
                    from pgadmin.model import User, Server
                    with app.test_request_context('/'):
                        saved = Server.query.get(sid); uid = User.query.first().id
                        endpoint = url_for('NODE-server.cde_workspace_id', gid=saved.servergroup_id, sid=sid)
                    browser = app.test_client()
                    with browser.session_transaction() as session: session['_user_id'], session['_fresh'] = str(uid), True
                    q.execute("SELECT CAST('api-warning' AS UNSIGNED)"); q.fetchall()
                    q.execute('SHOW WARNINGS'); warning = q.fetchall()
                    response = browser.post(endpoint, json={'action': 'mysql_server_catalog', 'request': {}})
                    data = response.get_json(); assert response.status_code == 200 and data.get('success'), data
                    assert response.headers['Cache-Control'] == 'no-store'
                    compare_ddn(data['data']['snapshot'])
                    q.execute('SHOW WARNINGS'); assert q.fetchall() == warning
                    proof['application'].append({'use_pure': pure, 'complete': True,
                        'generation_bound_resource_inspection': True, 'authenticated_server_ddn': True,
                        'native_field_values_preserved': True, 'original_diagnostics_preserved': True})
                reader_password = secrets.token_urlsafe(24)
                q.execute('CREATE USER `catalog_reader`@`%` IDENTIFIED BY %s', (reader_password,))
                q.execute('GRANT SELECT ON sr_osc.* TO `catalog_reader`@`%`')
                denied = []
                for pure in (True, False):
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=lambda *_: SecretLease(reader_password.encode())), SimpleNamespace())
                    handle = client._connect({'route': {**route, 'database': 'sr_osc', 'user': 'catalog_reader', 'use_pure': pure,
                        'autocommit': True, 'credential_reference_id': 'owned-reader', 'principal_reference': 'owned-operator'}})
                    try:
                        captured = capture(handle)
                        observation = next(row for row in captured['observations'] if row['section'] == 'runtime-functions')
                        assert not observation['available'] and observation['error_code'] == 1142
                        denied.append({'use_pure': pure, 'runtime_functions_explicitly_denied': True})
                    finally: client._forget_and_close(handle); client.close()
                proof.update(complete=True, denied=denied, plugin_count=len(expected_plugins), runtime_function_count=len(expected_functions))
            finally: q.close(); oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned['owned_server_stopped'])
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True)
    result = qualify(parser.parse_args().output)
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
