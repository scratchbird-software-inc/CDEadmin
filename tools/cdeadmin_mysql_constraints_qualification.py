"""Qualify native CHECK state and existing-row validation in a disposable database."""
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
    database = 'sr_checks_' + secrets.token_hex(6)
    db = identifier(database)
    proof = {'passed': False, 'checks': []}
    target = {'display_path': [database, 't`é', 'c`é'], 'native': {'constraint_type': 'CHECK'}}
    def execute(state):
        request = {'resource_kind': 'constraint', 'operation_id': 'enforcement',
                   'draft': {'enforcement': state}, 'target_resource': target}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        cursor.execute(statement['source'], statement['parameters'])
        from tools.mysql_task_evidence import record
        record(proof, request)
    try:
        cursor.execute('SELECT VERSION()')
        proof['native_version'] = cursor.fetchone()[0]
        assert proof['native_version'].split('-')[0] == '9.7.0'
        cursor.execute('CREATE DATABASE ' + db)
        table = db + '.' + identifier('t`é')
        cursor.execute('CREATE TABLE ' + table + ' (id INT PRIMARY KEY, CONSTRAINT ' + identifier('c`é') + ' CHECK (id > 0))')
        for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode = mode
            execute('NOT ENFORCED')
            cursor.execute('INSERT INTO ' + table + ' VALUES (-1)')
            try: execute('ENFORCED')
            except mysql.connector.Error as error: assert error.errno == 3819
            else: raise AssertionError('Enabling CHECK did not validate existing rows')
            observed = _resources(connection, {'route': {}}, MYSQL_PROFILE)
            row = next(r for r in observed if r['resource_kind'] == 'constraint' and r['display_path'] == target['display_path'])
            assert row['native']['enforced'] == 'NO'
            assert 'enforcement' in row['native']['administration']['allowed_operations']
            primary = next(r for r in observed if r['resource_kind'] == 'constraint' and r['display_path'] == [database, 't`é', 'PRIMARY'])
            assert 'enforcement' not in primary['native']['administration']['allowed_operations']
            cursor.execute('DELETE FROM ' + table)
            execute('ENFORCED')
            try: cursor.execute('INSERT INTO ' + table + ' VALUES (-1)')
            except mysql.connector.Error as error: assert error.errno == 3819
            else: raise AssertionError('Native enforced CHECK accepted invalid data')
            cursor.execute('INSERT INTO ' + table + ' VALUES (1)')
            cursor.execute('DELETE FROM ' + table)
            proof['checks'].append({'sql_mode': mode, 'disabled_allows_row': True,
                                    'enable_validates_existing_rows': True, 'failed_enable_retains_disabled': True,
                                    'enforced_rejects_invalid_rows': True, 'native_catalog_controls': True})
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
