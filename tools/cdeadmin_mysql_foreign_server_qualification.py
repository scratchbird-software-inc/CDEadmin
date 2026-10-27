"""Native MySQL foreign-server administration and full global-variable capture."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MYSQL_ADMINISTRATION as adapter, MYSQL_PROFILE, _create_client, _resources)
    from pgadmin.cdeadmin.providers.mysql_family import foreign_servers as foreign
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'history_testing': 'not run', 'full_product_complete': False,
        'checks': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_mysql_foreign_server_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/foreign_servers.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_server_catalog.py']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        with server(output/'fixture') as (route, _name, owned):
            connection = _root_connection('mysql', route['port']);connection.autocommit = True
            cursor = connection.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_foreign')
                name = 'remote : . ` ü'
                for pure in (True, False):
                    for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        selected = {**route, 'use_pure': pure, 'sql_mode': mode}
                        client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                        def observed():
                            return foreign.current(cursor, name)
                        def target():
                            return next(row for row in _resources(connection, {'route': {}}, MYSQL_PROFILE)
                                if row['resource_kind'] == foreign.KIND and row['display_name'] == name)
                        def planned(operation, draft, resource=None):
                            request = {'resource_kind': foreign.KIND, 'operation_id': operation,
                                'draft': draft, 'target_resource': resource, '_provider_route': selected}
                            assert not adapter.validate(request)['errors']
                            return client.plan_admin_operation(request)
                        draft = {'name': name, 'wrapper': 'mysql',
                            'include_host': True, 'host': "host ' \\",
                            'include_database': True, 'database': "database ' ü \\",
                            'include_username': True, 'username': "username ' ü \\",
                            'include_password': True, 'password': "credential ' ü \\",
                            'include_port': True, 'port': '2147483647',
                            'include_socket': True, 'socket': "socket ' ü \\",
                            'include_owner': True, 'owner': "owner ' ü \\"}
                        try:
                            create = planned('create', draft)
                            assert draft['password'] not in json.dumps(create['command_preview'])
                            created = adapter.apply(client, create)
                            after = observed()
                            expected = {'server_name': name, 'wrapper': draft['wrapper'],
                                **{column: draft[key] for key, (_keyword, _label, column) in foreign.OPTIONS.items() if column}}
                            assert after == expected and created['foreign_server_observation']['after'] == expected
                            cursor.execute('SELECT Password FROM mysql.servers WHERE CAST(Server_name AS BINARY)=CAST(%s AS BINARY)', (name,))
                            assert cursor.fetchone() == (draft['password'],)
                            resource = target()
                            assert foreign.normalized(foreign.native(resource)) == after
                            assert draft['password'] not in json.dumps(resource)
                            alter = {'include_host': True, 'host': 'reviewed host', 'confirmation': name}
                            stale = planned('alter', alter, resource)
                            cursor.execute('ALTER SERVER `remote : . `` ü` OPTIONS (PASSWORD %s)', ('external credential',))
                            try:
                                adapter.apply(client, stale)
                            except RelationalClientError as error:
                                assert not error.native_dispatched and not error.native_acknowledged
                            else:
                                raise AssertionError('External credential change was overwritten')
                            changed = adapter.apply(client, planned('alter', alter, target()))
                            assert observed()['host'] == 'reviewed host'
                            cursor.execute('SELECT Password FROM mysql.servers WHERE CAST(Server_name AS BINARY)=CAST(%s AS BINARY)', (name,))
                            assert cursor.fetchone() == ('external credential',)
                            assert 'credential' not in json.dumps(changed)
                            inventory = capture(connection)
                            links = [row for row in inventory['resources'] if row['resource_kind'] == foreign.KIND]
                            assert len(links) == 1 and links[0]['native']['catalog_row']['server_name'] == name
                            cursor.execute('SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_variables ORDER BY VARIABLE_NAME')
                            variables = dict(cursor.fetchall())
                            actual = {row['native']['catalog_row']['variable_name']: row['native']['catalog_row']['global_value']
                                for row in inventory['resources'] if row['resource_kind'] == 'system-variable'}
                            assert actual == variables and len(actual) > 10
                            assert all('variable_source' in row['native']['catalog_row'] for row in inventory['resources'] if row['resource_kind'] == 'system-variable')
                            drop = planned('drop', {'confirmation': name, 'if_exists': True}, target())
                            dropped = adapter.apply(client, drop)
                            assert observed() is None and dropped['foreign_server_observation']['after'] is None
                            assert client._connections == []
                            proof['checks'].append({'use_pure': pure, 'sql_mode': mode,
                                'all_native_attributes_verified': True, 'exact_signed_int_max_port': True,
                                'private_credential_not_exposed': True, 'stale_credential_refused_before_dispatch': True,
                                'partial_alter_preserves_credential': True, 'native_drop_verified': True,
                                'server_foreign_catalog_verified': True, 'all_visible_global_variables_verified': len(actual),
                                'task_sources': {op: value['command_preview']['statements'][0]['source']
                                    for op, value in [('create', create), ('alter', stale), ('drop', drop)]}})
                        finally:
                            client.close()
                cursor.execute("CREATE USER 'sr_foreign_reader'@'%'")
                cursor.execute("GRANT SELECT ON mysql.servers TO 'sr_foreign_reader'@'%'")
                restricted = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                try:
                    request = {'resource_kind': foreign.KIND, 'operation_id': 'create',
                        'draft': {'name': 'denied', 'wrapper': 'mysql', 'include_host': True, 'host': 'localhost'},
                        'target_resource': None, '_provider_route': {**route, 'user': 'sr_foreign_reader'}}
                    try:
                        adapter.apply(restricted, restricted.plan_admin_operation(request))
                    except RelationalClientError as error:
                        assert error.native_dispatched and not error.native_acknowledged and error.errno == 1227
                        proof['restricted_principal_native_refusal'] = {'error_code': error.errno, 'sqlstate': error.sqlstate}
                    else:
                        raise AssertionError('A principal without SUPER created a foreign server')
                    cursor.execute("SELECT COUNT(*) FROM mysql.servers WHERE Server_name='denied'")
                    assert cursor.fetchone() == (0,)
                finally:
                    restricted.close();cursor.execute("DROP USER 'sr_foreign_reader'@'%'")
                proof['native_engine'] = owned;proof['complete'] = True
            finally:
                cursor.close();connection.close()
    except Exception as error:
        proof['failure'] = {'type': type(error).__name__, 'native_error_code': getattr(error, 'errno', None),
            'sqlstate': getattr(error, 'sqlstate', None), 'native_dispatched': getattr(error, 'native_dispatched', None),
            'native_acknowledged': getattr(error, 'native_acknowledged', None)}
        raise
    finally:
        (output/'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    qualify(parser.parse_args().evidence)
