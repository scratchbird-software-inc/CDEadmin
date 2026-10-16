"""Qualify native MySQL resource-group plans without exposing credentials."""
import argparse
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import config  # noqa: F401 - initialize application before providers
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION


def qualify(connection_options, output):
    output.mkdir(parents=True, exist_ok=True)
    connection = mysql.connector.connect(**{**connection_options, 'autocommit': True})
    recipient = mysql.connector.connect(**{**connection_options, 'autocommit': True})
    cursor, assigned = connection.cursor(), recipient.cursor()
    name = 'sr_group_' + secrets.token_hex(6) + '`é'
    proof = {'passed': False, 'statements': {}, 'checks': []}
    created = False
    def execute(operation, draft):
        request = {'resource_kind': 'resource-group', 'operation_id': operation,
                   'target_resource': {'resource_kind': 'resource-group', 'display_name': name},
                   'draft': draft, '_provider_route': {'host': connection_options.get('host', 'localhost')}}
        errors = MYSQL_ADMINISTRATION.validate(request)['errors']
        assert not errors, errors
        source = MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source']
        cursor.execute(source)
        from tools.mysql_task_evidence import record
        record(proof, request)
        proof['statements'].setdefault(operation, source)
    try:
        cursor.execute('SELECT VERSION()')
        assert str(cursor.fetchone()[0]).split('-')[0] == '9.7.0'
        assigned.execute('SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=CONNECTION_ID()')
        thread = assigned.fetchone()[0]
        for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode = mode
            execute('create', {'name': name, 'resource_type': 'USER', 'priority': 0, 'enabled': True})
            created = True
            execute('assign', {'thread_ids': [thread]})
            cursor.execute('SELECT RESOURCE_GROUP FROM performance_schema.threads WHERE THREAD_ID=%s', (thread,))
            assert cursor.fetchone()[0] == name
            execute('alter', {'state': 'DISABLE', 'force': True})
            cursor.execute('SELECT RESOURCE_GROUP_ENABLED FROM information_schema.RESOURCE_GROUPS WHERE RESOURCE_GROUP_NAME=%s', (name,))
            assert cursor.fetchone()[0] == 0
            cursor.execute('SELECT RESOURCE_GROUP FROM performance_schema.threads WHERE THREAD_ID=%s', (thread,))
            assert cursor.fetchone()[0] == 'USR_default'
            execute('alter', {'state': 'ENABLE', 'priority': 0})
            execute('drop', {'force': True})
            created = False
            cursor.execute('SELECT COUNT(*) FROM information_schema.RESOURCE_GROUPS WHERE RESOURCE_GROUP_NAME=%s', (name,))
            assert cursor.fetchone()[0] == 0
        proof.update(passed=True, checks=['native generated create/alter/assign/drop plans',
            'exact quoted Unicode resource-group identity', 'default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES',
            'independent native thread assignment', 'FORCE disable moves assigned thread to USR_default',
            'native enabled-state rediscovery', 'native group absence after drop'])
    finally:
        if created:
            cursor.execute('DROP RESOURCE GROUP `' + name.replace('`', '``') + '` FORCE')
        cursor.close()
        assigned.close()
        connection.close()
        recipient.close()
        proof['temporary_resource_group_removed'] = True
        (output / 'summary.json').write_text(json.dumps(proof, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path)
    options = parser.parse_args()
    qualify(json.loads(options.connection_json.read_text()), options.output_root)
