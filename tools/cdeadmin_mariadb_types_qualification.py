"""Native SQL type spelling/parameter and mode qualification; owned fixture only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


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
    from pgadmin.cdeadmin.providers.mysql_family.mariadb_types import candidates, routine_candidates
    from pgadmin.cdeadmin.providers.native_editor import metadata
    paths = ['tools/cdeadmin_mariadb_types_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_types.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_installed.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py']
    proof = {'complete': False, 'checks': [], 'parameter_checks': [], 'oracle_refusals': [], 'non_column_type_refusals': [], 'history_testing': 'not run',
        'scope': 'Owned MariaDB12.2.2 CREATE TEMPORARY TABLE/type read-back, '
                 'mode refusals and actual native editor metadata; no HTTP/cell codec claim.',
        'source_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(work / 'mariadb-types-fixture') as (route, _name, _fixture):
            connection = _root_connection('mariadb', route['port'])
            connection.autocommit = True
            try:
                cursor = connection.cursor()
                cursor.execute('CREATE DATABASE owned_types')
                cursor.execute('USE owned_types')
                cursor.execute("SELECT PLUGIN_NAME,PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_TYPE='DATA TYPE'")
                plugins = cursor.fetchall()
                proof['type_plugins'] = plugins
                for mode in ['', 'ORACLE']:
                    cursor.execute('SET SESSION sql_mode=?', (mode,))
                    cursor.execute('SELECT VERSION(),@@sql_mode')
                    version, observed_mode = cursor.fetchone()
                    rows, observations = candidates(version, observed_mode, plugins)
                    assert rows
                    native_context = metadata(connection, 'mariadb')
                    native_types = {row['display_name']: row for row in native_context['resources'] if row['resource_kind'] == 'type'}
                    assert set(native_types) == {row['name'] for row in rows}
                    assert all(row['native_type_keyword'] and row['native_type_syntax'] for row in native_types.values())
                    for row in rows:
                        cursor.execute('CREATE TEMPORARY TABLE owned_type_probe (value ' + row['syntax']['example_sql'] + ')')
                        cursor.execute('SHOW FULL COLUMNS FROM owned_type_probe')
                        columns = cursor.fetchall()
                        assert len(columns) == 1 and columns[0][0] == 'value'
                        cursor.execute('DROP TEMPORARY TABLE owned_type_probe')
                        proof['checks'].append({'mode': mode or 'default', 'name': row['name'],
                            'type_clause': row['syntax']['example_sql'],
                            'native_column_type': columns[0][1], 'native_ddl_and_metadata_passed': True})
                    for row in rows:
                        required = row['syntax']['parameter_requirement'] == 'required'
                        try:
                            cursor.execute('CREATE TEMPORARY TABLE owned_type_probe (value ' + row['name'] + ')')
                        except Exception as error:
                            import mariadb
                            assert required and isinstance(error, mariadb.Error), (row['name'], error)
                            assert type(getattr(error, 'errno', None)) is int and not str(getattr(error, 'sqlstate', '')).startswith('08')
                            proof['parameter_checks'].append({'mode': mode or 'default',
                                'name': row['name'], 'parameters_required': True,
                                'native_refusal_code': error.errno})
                        else:
                            cursor.execute('DROP TEMPORARY TABLE owned_type_probe')
                            assert not required, row['name'] + ' accepted without required parameters'
                            proof['parameter_checks'].append({'mode': mode or 'default',
                                'name': row['name'], 'parameters_required': False,
                                'native_omitted_parameters_accepted': True})
                    for item in routine_candidates(version, plugins):
                        if (item['required_sql_mode']=='oracle') != (mode=='ORACLE'):
                            continue
                        cursor.execute(item['example_sql'])
                        proof.setdefault('routine_declarations',[]).append({'name':item['name'],'mode':mode or 'default','native_execution_passed':True})
                    for name, status in plugins:
                        if name.upper() not in {'ASSOCIATIVE_ARRAY', 'SYS_REFCURSOR'} or status != 'ACTIVE':
                            continue
                        try:
                            cursor.execute('CREATE TEMPORARY TABLE owned_type_probe (value ' + name + ')')
                        except Exception as error:
                            import mariadb
                            assert isinstance(error, mariadb.Error) and type(error.errno) is int
                            proof['non_column_type_refusals'].append({'mode': mode or 'default',
                                'name': name, 'native_error_code': error.errno})
                        else:
                            raise AssertionError('Routine-local type unexpectedly accepted as column: ' + name)
                    if not mode:
                        for clause in ['NUMBER(10,2)', 'VARCHAR2(16)', 'RAW(16)', 'CLOB']:
                            try:
                                cursor.execute('CREATE TEMPORARY TABLE owned_type_probe (value ' + clause + ')')
                            except Exception as error:
                                assert getattr(error, 'errno', None) in {1064, 4161}, getattr(error, 'errno', None)
                                proof['oracle_refusals'].append({'clause': clause, 'native_error_code': error.errno})
                            else:
                                raise AssertionError('Oracle-only type admitted without Oracle mode: ' + clause)
                cursor.close()
            finally:
                connection.close()
        proof['fixture_cleanup'] = json.loads((work / 'mariadb-types-fixture/fixture.json').read_text())
        assert proof['fixture_cleanup']['owned_server_stopped']
        proof['complete'] = True
    finally:
        (work / 'mariadb-types-native.json').write_text(json.dumps(proof, indent=2, default=str) + '\n')
    print('MariaDB native SQL type checks passed', len(proof['checks']))


if __name__ == '__main__':
    main()
