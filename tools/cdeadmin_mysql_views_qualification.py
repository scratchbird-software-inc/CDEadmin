"""Qualify structured ordinary views against disposable native MySQL objects."""
import argparse
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _resources
from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier


def qualify(options, output):
    output.mkdir(parents=True, exist_ok=True)
    connection = mysql.connector.connect(**{**options, 'autocommit': True})
    cursor = connection.cursor()
    database = 'sr_views_' + secrets.token_hex(6)
    db = identifier(database)
    proof = {'passed': False, 'checks': []}
    def execute(operation, draft):
        request = {'resource_kind': 'view', 'operation_id': operation, 'draft': draft,
                   'target_resource': {'display_name': 'v`é', 'display_path': [database, 'v`é']}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        cursor.execute(statement['source'], statement['parameters'])
    try:
        cursor.execute('SELECT VERSION(), CURRENT_USER()')
        version, account = cursor.fetchone()
        proof['native_version'] = version
        assert version.split('-')[0] == '9.7.0'
        user, host = account.rsplit('@', 1)
        cursor.execute('CREATE DATABASE ' + db)
        table = db + '.' + identifier('t`é')
        view = db + '.' + identifier('v`é')
        cursor.execute('CREATE TABLE ' + table + ' (id INT PRIMARY KEY, note VARCHAR(100))')
        cursor.execute('INSERT INTO ' + table + " VALUES (1, 'semi;colon')")
        for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode = mode
            desired = {'definition': 'SELECT id,note FROM ' + table + ' WHERE id > 0 -- trailing comment',
                       'columns': ['i`d', 'note'], 'algorithm': 'MERGE', 'sql_security': 'INVOKER',
                       'check_option': 'LOCAL', 'definer_user': user, 'definer_host': host}
            execute('create', {**desired, 'database': database, 'name': 'v`é'})
            cursor.execute('SELECT * FROM ' + view)
            assert cursor.fetchall() == [(1, 'semi;colon')]
            cursor.execute('SELECT CHECK_OPTION,SECURITY_TYPE,DEFINER,IS_UPDATABLE FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (database, 'v`é'))
            assert cursor.fetchone() == ('LOCAL', 'INVOKER', account, 'YES')
            observed = _resources(connection, {'route': {}}, MYSQL_PROFILE)
            selected = next(row for row in observed if row['resource_kind'] == 'view' and row['display_path'] == [database, 'v`é'])
            native = selected['native']
            assert native['algorithm'] == 'MERGE' and native['sql_security'] == 'INVOKER'
            assert native['check_option'] == 'LOCAL' and native['view_columns'] == ['i`d', 'note']
            assert native['definer_user'] == user and native['definer_host'] == host
            assert native['view_definition'] and 'select' in native['view_definition'].lower()
            try: cursor.execute('INSERT INTO ' + view + ' VALUES (-1, \'outside\')')
            except mysql.connector.Error as error: assert error.errno == 1369
            else: raise AssertionError('Native view check option did not reject outside row')
            try: execute('create', {**desired, 'database': database, 'name': 'v`é'})
            except mysql.connector.Error as error: assert error.errno == 1050
            else: raise AssertionError('CREATE silently replaced existing view')
            execute('alter', {**desired, 'definition': 'SELECT id,note FROM ' + table,
                              'algorithm': 'TEMPTABLE', 'sql_security': 'DEFINER', 'check_option': 'NONE'})
            cursor.execute('SHOW CREATE VIEW ' + view)
            definition = cursor.fetchone()[1]
            assert 'ALGORITHM=TEMPTABLE' in definition and 'SQL SECURITY DEFINER' in definition
            cursor.execute('SELECT CHECK_OPTION,IS_UPDATABLE FROM information_schema.VIEWS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', (database, 'v`é'))
            assert cursor.fetchone() == ('NONE', 'NO')
            cursor.execute('SELECT * FROM ' + view)
            assert cursor.fetchall() == [(1, 'semi;colon')]
            cursor.execute('DROP VIEW ' + view)
            proof['checks'].append({'sql_mode': mode, 'exact_column_and_definer_identity': True,
                                    'check_option_enforced': True, 'create_not_replace': True,
                                    'alter_algorithm_security_and_native_updatability': True})
        proof['passed'] = True
    finally:
        cursor.execute('DROP DATABASE IF EXISTS ' + db)
        cursor.close(); connection.close()
        proof['owned_database_removed'] = True
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    qualify(json.loads(args.connection_json.read_text()), args.output_root)
