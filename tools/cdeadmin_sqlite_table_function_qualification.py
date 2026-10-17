"""Native result-column fixtures for SQLite table-function completion."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]
import config  # noqa: E402,F401


def qualify(output):
    from tools.cdeadmin_native_editor_gate import provider
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/table_functions.py',
             ROOT / 'web/pgadmin/cdeadmin/providers/sqlite/provider.py', ROOT / 'web/pgadmin/cdeadmin/providers/native_editor.py',
             ROOT / 'web/pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion.js',
             ROOT / 'web/pgadmin/static/js/cdeadmin_ui/editors/nativeScopes.js']
    proof = {'complete': False, 'history_testing': 'not run', 'source_sha256': {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    instance = None
    try:
        assert sqlite3.sqlite_version == '3.53.0'
        path = output / 'native.sqlite'; instance, route = provider('sqlite', {'database': str(path), 'filesystem_root': str(output)})
        opened = instance.open_session({'route': route}); handle = instance._sessions[opened['session_id']].handle
        handle.execute('CREATE TABLE owned(id INTEGER PRIMARY KEY,body TEXT)')
        handle.execute("INSERT INTO owned VALUES(1,'native')")
        handle.execute('CREATE TABLE pending(value INTEGER)'); handle.execute('INSERT INTO pending VALUES(1)'); handle.commit()
        handle.execute('ATTACH DATABASE ? AS "attached.schema"', (str(output / 'attached.sqlite'),))
        handle.execute('BEGIN'); handle.execute('INSERT INTO pending VALUES(2)'); handle.execute('SAVEPOINT retained')
        calls = []
        handle.create_function('sqlite_version', 0, lambda: calls.append('version') or 'overridden')
        handle.create_function('sqlite_source_id', 0, lambda: calls.append('source') or 'overridden')
        quote = lambda name: '"' + name.replace('"', '""') + '"'
        groups = []
        def group(examples, negative=()):
            metadata = instance.complete({'session_id': opened['session_id']})['editor_context']
            assert not calls
            cases = []
            for marked, native_function in examples:
                if native_function:
                    schema, function = native_function[:2] if isinstance(native_function, tuple) else ('main', native_function)
                    names = [row[1] for row in handle.execute('PRAGMA ' + quote(schema) + '.table_xinfo(' + quote(function) + ')')]
                    if isinstance(native_function, tuple) and len(native_function) == 3:
                        # These fixtures are ordinary ROWID tables. Explicit
                        # member completion includes their native pseudo names,
                        # while SELECT * deliberately excludes those names.
                        names += [alias for alias in ('rowid', '_rowid_', 'oid') if alias not in names]
                else:
                    oracle = handle.execute(marked.replace('|', '*')); names = [column[0] for column in oracle.description]
                    assert oracle.fetchall()
                expected = [{'label': name, 'apply': quote(name), 'type': 'property'} for name in names]
                inserted = []
                for option in expected:
                    sql = marked.replace('|', option['apply']); result = handle.execute(sql)
                    assert len(result.description) == 1 and result.fetchall(); inserted.append(sql)
                cases.append({'marked': marked, 'expected': expected, 'native_inserted_sql': inserted})
            for marked in negative:
                try: handle.execute(marked.replace('|', '*'))
                except sqlite3.OperationalError: pass
                else: raise AssertionError('Native name masking did not refuse this function source: ' + marked)
            groups.append({'metadata': metadata, 'cases': cases, 'negative_cases': list(negative)})
        group([
            ("SELECT j.| FROM json_each('{\"snow\":7}') AS j", 'json_each'),
            ("SELECT j.| FROM main.json_tree('{\"snow\":7}') j", 'json_tree'),
            ("SELECT j.| FROM jsonb_each('{\"snow\":7}') j", 'jsonb_each'),
            ("SELECT j.| FROM jsonb_tree('{\"snow\":7}') AS j", 'jsonb_tree'),
            ("SELECT j.| FROM pragma_table_info('owned') AS j", 'pragma_table_info'),
            ("SELECT j.| FROM \"attached.schema\".json_each('{\"snow\":7}') j", 'json_each'),
            ("WITH q AS (SELECT j.* FROM json_each('{\"snow\":7}') j) SELECT q.| FROM q", None),
            ("WITH q AS (SELECT j.key FROM json_each('{\"snow\":7}') j) SELECT q.| FROM q", None),
            ("WITH json_each AS (SELECT id AS local_value FROM owned) SELECT q.| FROM json_each q", None),
        ])
        handle.execute('CREATE TEMP TABLE json_each(owned_temp TEXT)')
        handle.execute("INSERT INTO temp.json_each VALUES('temp')")
        handle.execute('CREATE TABLE json_tree(owned_main TEXT)'); handle.execute("INSERT INTO main.json_tree VALUES('main')")
        handle.execute('CREATE TABLE "attached.schema".pragma_table_info(owned_attached TEXT)')
        group([
            ("SELECT j.| FROM main.json_each('{\"snow\":7}') j", 'json_each'),
            ("SELECT j.| FROM temp.json_tree('{\"snow\":7}') j", ('temp', 'json_tree')),
            ('SELECT j.| FROM temp.json_each j', ('temp', 'json_each', 'rowid-table')),
            ('SELECT j.| FROM main.json_tree j', ('main', 'json_tree', 'rowid-table')),
        ], ["SELECT j.| FROM json_each('{}') j", "SELECT j.| FROM json_tree('{}') j",
            "SELECT j.| FROM pragma_table_info('owned') j"])
        assert handle.in_transaction and handle.execute('SELECT count(*) FROM pending').fetchone() == (2,)
        handle.execute('ROLLBACK TO retained'); handle.rollback()
        assert handle.execute('SELECT count(*) FROM pending').fetchone() == (1,)
        (output / 'native-editor-fixture.json').write_text(json.dumps({'engine': 'sqlite', 'groups': groups}, ensure_ascii=False, indent=2) + '\n')
        proof.update(complete=True, native_cases=sum(len(item['cases']) for item in groups),
            native_inserted_columns=sum(len(case['expected']) for item in groups for case in item['cases']),
            negative_cases=sum(len(item['negative_cases']) for item in groups), caller_work_preserved=True,
            metadata_user_functions_executed=False, native_sqlite_version=sqlite3.sqlite_version)
    finally:
        if instance is not None: instance.client.close()
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--evidence', type=Path, required=True)
    qualify(parser.parse_args().evidence)
