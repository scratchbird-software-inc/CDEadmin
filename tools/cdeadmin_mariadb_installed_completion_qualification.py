"""Owned MariaDB installed-metadata lifecycle and restricted-reader qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


UDF_SOURCE = '''#include <mysql.h>
my_bool sr_completion_udf_init(UDF_INIT *state, UDF_ARGS *args, char *message) {
  return args->arg_count != 0;
}
long long sr_completion_udf(UDF_INIT *state, UDF_ARGS *args, char *is_null, char *error) {
  return 42;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / 'web'), str(root / 'tools')]
    import config  # noqa: F401
    from tools.mariadb_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MARIADB_PROFILE
    from pgadmin.cdeadmin.providers.native_editor import NativeEditorProvider
    paths = ['tools/cdeadmin_mariadb_installed_completion_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_installed.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_completion.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py']
    proof = {'complete': False, 'checks': [], 'history_testing': 'not run',
        'scope': 'Owned MariaDB12.2.2 production completion: dynamic plugin variable and UDF '
                 'registration lifecycle, ACTIVE function plugins, restricted reader and diagnostics. No HTTP claim.',
        'source_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}}
    try:
        fixture = work / 'mariadb-installed-fixture'
        fixture.mkdir(parents=True, exist_ok=True)
        code = fixture / 'sr_completion_udf.c'
        library = fixture / 'sr_completion_udf.so'
        code.write_text(UDF_SOURCE)
        subprocess.run(['cc', '-shared', '-fPIC', '-I/usr/include/mariadb', str(code), '-o', str(library)], check=True, env={**os.environ, 'TMPDIR': str(fixture)})
        proof['owned_udf_library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
        with server(fixture) as (route, name, _fixture):
            native = _root_connection('mariadb', route['port'])
            native.autocommit = True
            clients = []
            try:
                cursor = native.cursor()
                cursor.execute('CREATE DATABASE owned_installed')
                cursor.execute('SELECT @@plugin_dir')
                plugin_dir = cursor.fetchone()[0]
                subprocess.run(['docker', 'cp', str(library), name + ':' + plugin_dir + '/sr_completion_udf.so'], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                route = {**route, 'database': 'owned_installed'}
                def connect(settings):
                    settings = dict(settings)
                    password = settings.pop('password', None)
                    settings, permissions = provider_access(settings, password=password)
                    client = _create_client(MARIADB_PROFILE, permissions,
                        SimpleNamespace(pool_namespace='owned-installed-' + str(len(clients))))
                    clients.append(client)
                    source = client.open_session({'route': settings})
                    provider = SimpleNamespace(client=client, profile=MARIADB_PROFILE,
                        _editor_session=lambda request: source)
                    return client, source, provider
                client, source, provider = connect(route)
                def observe():
                    return NativeEditorProvider.complete(provider, {})['editor_context']
                def dynamic(result):
                    return {row['display_name'].upper(): row for row in result['resources']
                        if row['resource_kind'] == 'system-variable'}
                before = observe()
                assert not any(row['display_name'] == 'sr_completion_udf' for row in before['resources'])
                baseline = set(dynamic(before))
                available_libraries = subprocess.run(['docker', 'exec', name, 'ls', plugin_dir],
                    check=True, capture_output=True, text=True).stdout.splitlines()
                assert 'server_audit.so' in available_libraries, available_libraries
                proof['dynamic_variable_plugin_dependency'] = 'server_audit.so; observed in owned plugin directory'
                cursor.execute("INSTALL SONAME 'server_audit'")
                installed = observe()
                added = set(dynamic(installed)) - baseline
                assert added and all(name.startswith('SERVER_AUDIT_') for name in added), added
                for name in added:
                    assert dynamic(installed)[name]['native_variable']['metadata_origin'] == 'information_schema.SYSTEM_VARIABLES'
                proof['checks'].append({'dynamic_plugin_variables_added': sorted(added)})
                cursor.execute("CREATE FUNCTION sr_completion_udf RETURNS INTEGER SONAME 'sr_completion_udf.so'")
                registered = observe()
                udf = next(row for row in registered['resources'] if row['display_name'] == 'sr_completion_udf')
                assert udf['native_function']['origin'] == 'mysql.func'
                assert udf['native_function']['return_type'] == 'INT_RESULT'
                assert not udf['native_function']['invocation_verified']
                cursor.execute('SELECT sr_completion_udf()')
                assert cursor.fetchone() == (42,)
                proof['checks'].append({'owned_udf_registration_observed': True,
                    'independent_owned_udf_invocation_returned_42': True,
                    'completion_did_not_claim_invocation': True})
                active = [row for row in registered['resources'] if row.get('native_function', {}).get('origin') == 'information_schema.PLUGINS']
                assert active and all(row['native_function']['plugin_status'] == 'ACTIVE' for row in active)
                proof['checks'].append({'active_function_plugin_names': sorted(row['display_name'] for row in active)})
                cursor.execute('DROP FUNCTION sr_completion_udf')
                cursor.execute("UNINSTALL SONAME 'server_audit'")
                removed = observe()
                assert not (set(dynamic(removed)) & added)
                assert not any(row['display_name'] == 'sr_completion_udf' for row in removed['resources'])
                proof['checks'].append({'removed_plugin_variables_and_udf_absent': True})
                cursor.execute("CREATE USER 'sr_completion_reader'@'%' IDENTIFIED BY 'owned-fixture-only'")
                cursor.execute("GRANT SELECT ON owned_installed.* TO 'sr_completion_reader'@'%'")
                _reader, reader_source, reader_provider = connect({**route,
                    'user': 'sr_completion_reader', 'password': 'owned-fixture-only'})
                reader_cursor = reader_source.cursor()
                reader_cursor.execute('SELECT 1/0')
                assert reader_cursor.fetchone() == (None,)
                reader_cursor.execute('SHOW WARNINGS')
                warnings = reader_cursor.fetchall()
                assert warnings and warnings[0][1] == 1365
                denied = NativeEditorProvider.complete(reader_provider, {})['editor_context']
                reader_cursor.execute('SHOW WARNINGS')
                assert reader_cursor.fetchall() == warnings
                reader_cursor.close()
                observation = next(row for row in denied['observations'] if row['section'] == 'native-loadable-functions')
                assert not observation['available'] and observation['error_code'] == 1142
                assert dynamic(denied) and not denied['complete']
                proof['checks'].append({'native_mysql_func_denial_code': 1142,
                    'public_variable_metadata_preserved': True, 'source_warning_preserved': True,
                    'incomplete_scope_reported': True})
                cursor.close()
            finally:
                for client in reversed(clients):
                    client.close()
                native.close()
        proof['fixture_cleanup'] = json.loads((fixture / 'fixture.json').read_text())
        assert proof['fixture_cleanup']['owned_server_stopped']
        proof['complete'] = True
    finally:
        (work / 'mariadb-installed-native.json').write_text(json.dumps(proof, indent=2, default=str) + '\n')
    print('MariaDB installed completion checks passed', len(proof['checks']))


if __name__ == '__main__':
    main()
