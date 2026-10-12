"""Qualify durable MySQL multi-table outcomes and a lost native acknowledgement."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture, identifier
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options, output):
    output.mkdir(parents=True, exist_ok=True)
    connection = mysql.connector.connect(**{**options, 'autocommit': True})
    cursor = connection.cursor()
    database = 'sr_batch_' + secrets.token_hex(6)
    reader = None
    proof = {'passed': False, 'checks': []}
    applications = MySQLSchemaApplications(output / 'receipts.json')
    try:
        cursor.execute('CREATE DATABASE ' + identifier(database) + ' CHARACTER SET utf8mb4')
        connection.database = database
        reader = mysql.connector.connect(**{**options, 'database': database, 'autocommit': True})
        for lost in (False, True):
            for name in ('a', 'b', 'c'):
                cursor.execute('CREATE TABLE ' + identifier(name) + ' (id INT PRIMARY KEY, note VARCHAR(80))')
                cursor.execute('INSERT INTO ' + identifier(name) + " VALUES (42,'retained')")
            captured = capture(connection, database)
            before = build_export(captured['resources'], endpoint_id='ep', target_id='target', generation=captured['generation'], engine='mysql', native_model=True)
            desired = deepcopy(before)
            for row in desired['rows'].values():
                if row['kind'] == 'table':
                    row['native']['definition'] = row['native']['definition'].replace('varchar(80)', 'varchar(120)')
            preview = plan(before, desired, before)
            assert preview['ready_for_review'] and len(preview['operations']) == 3
            preview.update(validate(reader, preview))
            assert preview['native_grammar_validated']
            receipt = applications.review(preview, before, desired, 'owner', 'binding', 'target')
            request = {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}
            class CursorProxy:
                def __init__(self, native): self.native = native
                def execute(self, source):
                    result = self.native.execute(source)
                    if source.startswith('ALTER TABLE'): raise OSError('fixture loses native success acknowledgement')
                    return result
                def __getattr__(self, key): return getattr(self.native, key)
            class ConnectionProxy:
                def __init__(self, native): object.__setattr__(self, 'native', native)
                def cursor(self): return CursorProxy(self.native.cursor())
                def __getattr__(self, key): return getattr(self.native, key)
                def __setattr__(self, key, value): setattr(self.native, key, value)
            calls = []
            def execute(record):
                name = record['plan']['operations'][0]['name']
                calls.append(name)
                return apply_review(ConnectionProxy(reader) if lost and name == 'b' else reader, record)
            result = applications.apply(request, 'owner', 'binding', execute)
            assert calls == (['a', 'b'] if lost else ['a', 'b', 'c'])
            assert result['state'] == ('unknown_outcome' if lost else 'committed')
            assert [entry['state'] for entry in result['statement_outcomes']] == (
                ['committed', 'unknown_outcome', 'not_dispatched'] if lost else ['committed'] * 3)
            restarted = MySQLSchemaApplications(output / 'receipts.json')
            assert restarted.apply(request, 'owner', 'binding', lambda _: (_ for _ in ()).throw(AssertionError('replay'))) == result
            cursor.execute("SELECT TABLE_NAME,COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND COLUMN_NAME='note' ORDER BY TABLE_NAME", (database,))
            assert cursor.fetchall() == [('a', 'varchar(120)'), ('b', 'varchar(120)'), ('c', 'varchar(80)' if lost else 'varchar(120)')]
            for name in ('a', 'b', 'c'):
                cursor.execute('SELECT id,note FROM ' + identifier(name))
                assert cursor.fetchall() == [(42, 'retained')]
                cursor.execute('DROP TABLE ' + identifier(name))
            proof['checks'].append({'lost_second_acknowledgement': lost,
                'native_effects_match_retained_statement_outcomes': True, 'remaining_not_dispatched': lost,
                'restart_and_repeat_do_not_replay': True, 'existing_data_preserved': True})
        proof['passed'] = True
    finally:
        if reader is not None: reader.close()
        cursor.execute('DROP DATABASE IF EXISTS ' + identifier(database))
        cursor.close(); connection.close()
        proof['owned_database_removed'] = True
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    qualify(json.loads(args.connection_json.read_text()), args.output_root)
