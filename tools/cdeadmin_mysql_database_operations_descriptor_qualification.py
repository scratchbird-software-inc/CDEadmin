"""Owned native/API qualification of typed database maintenance and dump inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep qualification evidence outside source')
    output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from cdeadmin_mysql_online_ddl_qualification import registration
    from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft
    declarations = engine_operations('mysql')
    paths = ['web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
             'web/pgadmin/cdeadmin/providers/mysql_descriptor_contract.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/database_inputs.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
             'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
             'web/pgadmin/cdeadmin/visual_admin/portfolio_catalog.json',
             str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'interfaces': [], 'actual_operation_dialog_qualified': False,
             'history_testing': 'ScratchBird history not run',
             'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned = None
    try:
        with server(output/'fixture') as (route, _container, owned):
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc CHARACTER SET utf8mb4')
                q.execute('CREATE DATABASE sr_descriptor_guard')
                q.execute('CREATE TABLE sr_descriptor_guard.pending(id INT PRIMARY KEY)')
                q.execute('CREATE TABLE sr_osc.repairable(id INT PRIMARY KEY, v VARCHAR(30)) ENGINE=MyISAM')
                q.execute("INSERT INTO sr_osc.repairable VALUES(1,'preserved')")
                q.execute('CREATE TABLE sr_osc.payload(id BIGINT UNSIGNED PRIMARY KEY, body TEXT, bytes BLOB)')
                q.execute('INSERT INTO sr_osc.payload VALUES(%s,%s,%s)', (2**64-1, 'native 😀 雪', b'\x00\xff'))
                q.execute('CREATE TABLE sr_osc.parts(id INT PRIMARY KEY) PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN(10),PARTITION p1 VALUES LESS THAN MAXVALUE)')
                q.execute('INSERT INTO sr_osc.parts VALUES(0),(1),(10)')
                definitions = {'i': 'BIGINT', 'u': 'BIGINT UNSIGNED', 'd': 'DOUBLE', 'n': 'DECIMAL(20,3)',
                               's': 'VARCHAR(20)', 'dt': 'DATE', 'tm': 'TIME(6)', 'ts': 'DATETIME(6)',
                               'e': "ENUM('a','b')", 'st': "SET('a','b')"}
                q.execute('CREATE TABLE sr_osc.histograms('+','.join(k+' '+v for k,v in definitions.items())+')')
                q.execute('INSERT INTO sr_osc.histograms VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                          (-(2**63), 2**64-1, .125, '1.125', '雪', '2026-10-26', '01:02:03.123456', '2026-10-26 01:02:03.123456', 'a', 'a,b'))
                q.execute('INSERT INTO sr_osc.histograms(i) VALUES(0),(1),(2),(3),(4),(5)')
                q.execute('CREATE TABLE sr_osc.empty_hist(v INT)')
                password = 'LF\nquote"slash\\雪-'+secrets.token_urlsafe(24)
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                for pure in (True, False):
                    _, _, post = registration(app, {**route, 'tool_workspace': str(output)}, password, not pure)
                    target = {'resource_kind': 'database', 'resource_id': 'database:sr_osc', 'display_name': 'sr_osc', 'display_path': ['sr_osc']}
                    operations = []
                    def run(operation, values=None, guard=True):
                        declaration = declarations[operation+'@database']
                        ui = operation_draft(declaration, values, 'sr_osc')
                        draft = backend_draft({'tabs': [{'fields': declaration['fields']}]}, ui)
                        request = {'resource_kind': 'database', 'operation_id': operation, 'target_resource': target, 'draft': draft}
                        if guard:
                            oracle.autocommit = False
                            q.execute('SAVEPOINT descriptor_guard')
                            q.execute('INSERT INTO sr_descriptor_guard.pending VALUES(1)')
                        try:
                            checked = post('visual_admin_validate', request); assert checked['valid'], checked['errors']
                            planned = post('visual_admin_plan', request); assert planned['state'] == 'ready' and planned['execution_available']
                            apply = {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True}
                            result = post('visual_admin_apply', apply); assert result['provider_result']['accepted']
                            replay = post.raw('visual_admin_apply', apply)
                            assert replay.status_code != 200 or not replay.get_json().get('success')
                            if guard:
                                q.execute('SELECT ROW_COUNT()'); assert q.fetchone() == (1,)
                                q.execute('ROLLBACK TO SAVEPOINT descriptor_guard')
                            operations.append(operation)
                            print('API', operation, 'use_pure='+str(pure), flush=True)
                            return result
                        finally:
                            if guard:
                                oracle.rollback(); oracle.autocommit = True
                    for operation, values in [
                        ('analyze_tables', {'tables': [{'value': 'repairable'}], 'no_write_to_binlog': True}),
                        ('check_tables', {'tables': ['repairable'], 'check_options': ['QUICK']}),
                        ('optimize_tables', {'tables': ['repairable'], 'no_write_to_binlog': True}),
                        ('repair_tables', {'tables': ['repairable'], 'repair_options': ['QUICK'], 'no_write_to_binlog': True}),
                        ('checksum_tables', {'tables': ['repairable'], 'checksum_type': 'EXTENDED'})]:
                        run(operation, values)
                    native_types = []
                    histogram_shapes = []
                    for column in [*definitions, 'v']:
                        table = 'empty_hist' if column == 'v' else 'histograms'
                        base = {'tables': [table], 'histogram_action': 'UPDATE', 'histogram_columns': [column], 'histogram_buckets': 2}
                        run('analyze_tables', base)
                        q.execute("SELECT histogram FROM information_schema.column_statistics WHERE schema_name='sr_osc' AND table_name=%s AND column_name=%s", (table, column))
                        document = q.fetchone()[0]
                        if isinstance(document, str): document = json.loads(document)
                        text = lambda value: value if isinstance(value, str) else json.dumps(value)
                        rows = [({'lower': text(row[0]), 'frequency': row[1]} if len(row) == 2 else
                                 {'lower': text(row[0]), 'upper': text(row[1]), 'frequency': row[2], 'distinct': str(row[3])})
                                for row in document['buckets']]
                        run('analyze_tables', {**base, 'histogram_source': 'IMPORT',
                            'histogram_type': document['histogram-type'], 'histogram_data_type': document['data-type'],
                            'histogram_sampling': document['sampling-rate'], 'histogram_nulls': document['null-values'],
                            'histogram_collation': document['collation-id'], 'histogram_specified': document['number-of-buckets-specified'],
                            'histogram_import_auto': document['auto-update'], 'histogram_bucket_rows': rows})
                        q.execute("SELECT histogram FROM information_schema.column_statistics WHERE schema_name='sr_osc' AND table_name=%s AND column_name=%s", (table, column))
                        observed = q.fetchone()[0]
                        if isinstance(observed, str): observed = json.loads(observed)
                        assert observed['buckets'] == document['buckets']
                        native_types.append(document['data-type'])
                        histogram_shapes.append('empty' if not rows else document['histogram-type'])
                    run('analyze_tables', {**base, 'histogram_action': 'DROP'})
                    q.execute('SELECT * FROM sr_osc.repairable'); assert q.fetchall() == [(1, 'preserved')]
                    dump = 'full-'+str(pure)
                    run('backup_logical', {'path': dump, 'threads': 2, 'show_progress': False}, guard=False)
                    q.execute("UPDATE sr_osc.payload SET body='after dump'")
                    restored = run('restore_logical', {'path': dump, 'drop_existing_objects': True, 'reset_progress': True,
                        'enable_local_infile': True, 'show_progress': False, 'threads': 2}, guard=False)
                    observation = restored['provider_result']['driver_observation']
                    assert observation['restore_postcondition']['schema_postcondition_passed']
                    verified = run('verify_logical', {'path': dump, 'enable_local_infile': True, 'threads': 2}, guard=False)
                    assert verified['provider_result']['driver_observation']['data_recovery_verified']
                    q.execute('SELECT CAST(id AS CHAR), body, HEX(bytes) FROM sr_osc.payload')
                    assert q.fetchall() == [(str(2**64-1), 'native 😀 雪', '00FF')]
                    q.execute('SELECT @@GLOBAL.local_infile'); assert q.fetchone() == (0,)
                    subset = 'subset-'+str(pure)
                    run('backup_logical', {'path': subset, 'threads': 2, 'checksum': False, 'show_progress': False,
                        'set_include_tables': True, 'include_tables': [{'value': 'sr_osc.parts'}],
                        'set_partitions': True, 'partitions': [{'table': 'sr_osc.parts', 'partitions': [{'value': 'p0'}]}],
                        'set_where': True, 'where': [{'table': 'sr_osc.parts', 'condition': 'id > 0'}]}, guard=False)
                    # Restore a typed filtered dump into an independently named
                    # schema, inspect the data, then remove only this fixture.
                    name = 'sr_subset_'+str(pure)
                    q.execute('CREATE DATABASE '+name)
                    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE
                    from pgadmin.cdeadmin.security import SecretLease
                    from types import SimpleNamespace
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=lambda *_: SecretLease(password.encode())), SimpleNamespace())
                    try:
                        client.run_database_operation(None, {**route, 'database': name, 'tool_workspace': str(output), 'use_pure': pure,
                            'credential_reference_id': 'owned', 'principal_reference': 'owned-operator'}, 'restore_logical', {'path': subset, 'confirmation': name,
                            'schema': name, 'reset_progress': True, 'enable_local_infile': True, 'show_progress': False})
                    finally: client.close()
                    q.execute('SELECT id FROM '+name+'.parts'); assert q.fetchall() == [(1,)]
                    q.execute('DROP DATABASE '+name)
                    proof['interfaces'].append({'use_pure': pure, 'complete': True, 'operations': sorted(set(operations)),
                        'native_histogram_types': sorted(native_types), 'exact_uint64_unicode_blob_restored': True,
                        'native_histogram_shapes': sorted(set(histogram_shapes)),
                        'native_data_checksum_verified': True, 'filtered_partition_dump_data_verified': True,
                        'maintenance_diagnostics_and_savepoint_preserved': True, 'consumed_plans_refused': True})
                proof['complete'] = True
            finally: q.close(); oracle.close()
    finally:
        proof['owned_server_stopped'] = bool(owned and owned['owned_server_stopped'])
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True)
    result = qualify(parser.parse_args().output)
    print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
