"""Qualify generated routine/index changes against a disposable native database."""
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
    database = 'sr_objects_' + secrets.token_hex(6)
    db = identifier(database)
    proof = {'passed': False, 'checks': []}
    def execute(kind, operation, name, draft):
        path = [database, 't`é', name] if kind == 'index' else [database, name]
        request = {'resource_kind': kind, 'operation_id': operation, 'draft': draft,
                   'target_resource': {'display_name': name, 'display_path': path},
                   '_provider_route': {'host': options.get('host', 'localhost')}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement = MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        cursor.execute(statement['source'], statement['parameters'])
        from tools.mysql_task_evidence import record
        record(proof, request)
    try:
        cursor.execute('SELECT VERSION()')
        proof['native_version'] = cursor.fetchone()[0]
        assert str(proof['native_version']).split('-')[0] == '9.7.0'
        cursor.execute('CREATE DATABASE ' + db)
        for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode = mode
            table = db + '.' + identifier('t`é')
            cursor.execute('CREATE TABLE ' + table + ' (id INT PRIMARY KEY, v INT, UNIQUE KEY ' + identifier('i`é') + ' (v))')
            cursor.execute('INSERT INTO ' + table + ' VALUES (1,42)')
            cursor.execute('CREATE PROCEDURE ' + db + '.' + identifier('p`é') + '() SELECT 42')
            cursor.execute('CREATE FUNCTION ' + db + '.' + identifier('f`é') + '() RETURNS INT DETERMINISTIC RETURN 42')
            comment = "é'; DROP TABLE t; -- \\"
            for kind, name in (('procedure', 'p`é'), ('function', 'f`é')):
                cursor.execute('SHOW CREATE ' + kind.upper() + ' ' + db + '.' + identifier(name))
                before = cursor.fetchone()[2]
                execute(kind, 'alter', name, {'comment': comment, 'sql_security': 'INVOKER', 'data_access': 'NO SQL'})
                cursor.execute('SELECT SECURITY_TYPE,SQL_DATA_ACCESS,ROUTINE_COMMENT,IS_DETERMINISTIC,ROUTINE_DEFINITION FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s', (database, name))
                facts = cursor.fetchone()
                assert facts[:3] == ('INVOKER', 'NO SQL', comment)
                assert facts[4] == ('SELECT 42' if kind == 'procedure' else 'RETURN 42')
                if kind == 'function': assert facts[3] == 'YES'
                cursor.execute('ALTER ' + kind.upper() + ' ' + db + '.' + identifier(name) + " COMMENT ''")
                cursor.execute('SELECT SECURITY_TYPE,SQL_DATA_ACCESS,ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s', (database, name))
                facts = cursor.fetchone()
                assert facts == ('INVOKER', 'NO SQL', comment), repr(facts)
                execute(kind, 'alter', name, {'comment': 'replacement'})
                cursor.execute('SELECT SECURITY_TYPE,SQL_DATA_ACCESS,ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s', (database, name))
                assert cursor.fetchone() == ('INVOKER', 'NO SQL', 'replacement')
            cursor.execute('SELECT ' + db + '.' + identifier('f`é') + '()')
            assert cursor.fetchone() == (42,)
            execute('index', 'rename', 'i`é', {'new_name': 'renamed`é'})
            execute('index', 'visibility', 'renamed`é', {'visibility': 'INVISIBLE'})
            cursor.execute('SELECT IS_VISIBLE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND INDEX_NAME=%s', (database, 'renamed`é'))
            assert cursor.fetchone() == ('NO',)
            try: cursor.execute('INSERT INTO ' + table + ' VALUES (2,42)')
            except mysql.connector.Error as error: assert error.errno == 1062
            else: raise AssertionError('Invisible unique index stopped enforcing uniqueness')
            observed = _resources(connection, {'route': {}}, MYSQL_PROFILE)
            index = next(row for row in observed if row['resource_kind'] == 'index' and row['display_path'] == [database,'t`é','renamed`é'])
            assert index['native']['is_visible'] == 'NO'
            primary = next(row for row in observed if row['resource_kind'] == 'index' and row['display_path'] == [database,'t`é','PRIMARY'])
            assert not {'rename','visibility'} & set(primary['native']['administration']['allowed_operations'])
            execute('index', 'visibility', 'renamed`é', {'visibility': 'VISIBLE'})
            cursor.execute('SELECT id,v FROM ' + table)
            assert cursor.fetchall() == [(1,42)]
            for kind,name in (('PROCEDURE','p`é'),('FUNCTION','f`é')): cursor.execute('DROP ' + kind + ' ' + db + '.' + identifier(name))
            cursor.execute('DROP TABLE ' + table)
            proof['checks'].append({'sql_mode': mode, 'routine_body_and_determinism_retained': True,
                                    'comment_bound_replaced_and_native_empty_noop_observed': True, 'index_identity_visibility_and_unique_enforcement': True,
                                    'native_catalog_controls': True})
        proof['passed'] = True
    finally:
        cursor.execute('DROP DATABASE IF EXISTS ' + db)
        cursor.close(); connection.close()
        proof['owned_database_removed'] = True
        (output / 'summary.json').write_text(json.dumps(proof, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    qualify(json.loads(args.connection_json.read_text()), args.output_root)
