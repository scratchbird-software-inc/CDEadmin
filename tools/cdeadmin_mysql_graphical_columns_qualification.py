"""Qualify DDN field additions through native PREPARE, reviewed apply and rediscovery."""
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
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
from pgadmin.cdeadmin.workspace.mysql_erd import build_diagram
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options, output):
    output.mkdir(parents=True, exist_ok=True)
    connection = mysql.connector.connect(**{**options, 'autocommit': True})
    cursor = connection.cursor()
    database = 'sr_graph_' + secrets.token_hex(6)
    reader = None
    proof = {'passed': False, 'checks': []}
    applications = MySQLSchemaApplications(output / 'receipts.json')
    try:
        cursor.execute('CREATE DATABASE ' + identifier(database) + ' CHARACTER SET utf8mb4')
        connection.database = database
        reader = mysql.connector.connect(**{**options, 'database': database, 'autocommit': True})
        for mode in ('', 'NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode = mode
            cursor.execute("CREATE TABLE t (id INT PRIMARY KEY, note VARCHAR(80) DEFAULT 'semi;comma,)', computed INT GENERATED ALWAYS AS ((id+1)) STORED) ENGINE=InnoDB")
            cursor.execute('INSERT INTO t(id) VALUES (42)')
            captured = capture(connection, database)
            catalog = build_export(captured['resources'], endpoint_id='ep', target_id='target', generation=captured['generation'], engine='mysql')
            exported = read_catalog(json.dumps(catalog['snapshot']), engine='mysql')
            original = build_diagram(captured['resources'], {'endpoint_id': 'ep', 'database_target_id': 'target'})['snapshot']
            desired = deepcopy(original)
            field = 'field new_column "n`é" {uid:"new-owned-field";datatype:"varchar(40)";nullable:true;description:"owner comment";}'
            source = desired['files'][desired['entry']]
            assert source.count('fields {') == 1
            desired['files'][desired['entry']] = source.replace('fields {', 'fields {' + field, 1)
            try: handoff(catalog['snapshot'], original, desired, engine='mysql')
            except ValueError: pass
            else: raise AssertionError('Unknown graphical field was admitted without explicit option')
            prepared = handoff(catalog['snapshot'], original, desired, engine='mysql', allow_new_columns=True)
            before, after = [read_catalog(prepared[key], engine='mysql') for key in ('baseline', 'desired')]
            preview = plan(before, after, exported)
            assert preview['ready_for_review'] and len(preview['operations']) == 1
            assert 'ADD COLUMN `n``é` varchar(40) NULL COMMENT' in preview['operations'][0]['source']
            preview.update(validate(reader, preview))
            assert preview['native_grammar_validated']
            receipt = applications.review(preview, before, after, 'owner', 'binding', 'target')
            request = {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}
            result = applications.apply(request, 'owner', 'binding', lambda record: apply_review(reader, record))
            assert result['state'] == 'committed' and result['outcome']['rediscovery_verified']
            assert applications.apply(request, 'owner', 'binding', lambda _: (_ for _ in ()).throw(AssertionError('replayed'))) == result
            cursor.execute('SELECT id,note,computed,`n``é` FROM t')
            assert cursor.fetchone() == (42, 'semi;comma,)', 43, None)
            cursor.execute("SELECT COLUMN_COMMENT FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='t' AND COLUMN_NAME=%s", (database, 'n`é'))
            assert cursor.fetchone() == ('owner comment',)
            cursor.execute('DROP TABLE t')
            proof['checks'].append({'sql_mode': mode, 'explicit_admission_required': True,
                'native_prepare_and_reviewed_add': True, 'rediscovery': True,
                'defaults_generated_values_and_existing_data_preserved': True, 'receipt_not_replayed': True})
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
