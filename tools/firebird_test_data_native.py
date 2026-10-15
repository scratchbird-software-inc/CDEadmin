"""Qualify generated recipes in the caller's uniquely owned native database."""
import json
from pathlib import Path
import subprocess
import shutil


def qualify(connection, client, route):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources, ADMINISTRATION
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError

    statements = [
        'CREATE TABLE GEN_PARENT (ID BIGINT, KIND VARCHAR(8), PRIMARY KEY (ID, KIND))',
        'CREATE TABLE GEN_CHILD (ID INTEGER PRIMARY KEY, REF_ID BIGINT, REF_KIND VARCHAR(8), '
        'FOREIGN KEY (REF_ID, REF_KIND) REFERENCES GEN_PARENT(ID, KIND))',
        'CREATE TABLE GEN_EXISTING (ID INTEGER PRIMARY KEY, REF_ID BIGINT, REF_KIND VARCHAR(8), '
        'FOREIGN KEY (REF_ID, REF_KIND) REFERENCES GEN_PARENT(ID, KIND))',
        'CREATE TABLE GEN_SELF (ID INTEGER, KIND VARCHAR(8), REF_ID INTEGER, REF_KIND VARCHAR(8), '
        'PRIMARY KEY (ID, KIND), FOREIGN KEY (REF_ID, REF_KIND) REFERENCES GEN_SELF(ID, KIND))',
        "INSERT INTO GEN_PARENT VALUES (7, 'existing')",
    ]
    for source in statements:
        with connection.cursor() as cursor:
            cursor.execute(source)
        connection.commit()
    resources = [item for item in _resources(connection, {})
                 if item['resource_kind'] == 'table' and item['display_name'].startswith('GEN_')]
    connection.rollback()
    owned_route = dict(route, transaction_isolation='SNAPSHOT', transaction_access='WRITE',
                       transaction_auto_commit=False, transaction_no_auto_undo=False,
                       transaction_ignore_limbo=False, transaction_lock_timeout=10)
    handle = client.open_session({'route': owned_route})
    catalogs = {}
    try:
        for resource in resources:
            page = client.read_admin_rows({'target_resource': resource, 'limit': 200,
                '_provider_route': owned_route, '_provider_session_handle': handle})
            assert page['complete'] and not page.get('continuation'), page
            catalogs[resource['display_name']] = dict(resource=resource, columns=page['columns'], rows=page['rows'])
        client.control_transaction(handle, 'rollback')
        module = Path(__file__).resolve().parents[1] / 'web/pgadmin/static/js/Dialogs/firebirdTestDataHelpers.js'
        runner = r"""
import {pathToFileURL} from 'node:url';
const m = await import(pathToFileURL(process.argv[1]).href);
const catalogs = JSON.parse((await import('node:fs')).readFileSync(0, 'utf8'));
for (const item of Object.values(catalogs)) item.foreignKeys = m.tableForeignKeys(item.resource);
const constant = value => ({kind:'constant',value});
const sequential = start => ({kind:'sequential',start,step:'1'});
const generated = column => ({kind:'generated',table:'GEN_PARENT',column});
const existing = column => ({kind:'existing',table:'GEN_PARENT',column});
const recipe = {format:'scratchrobin.firebird.test-data@1',seed:42,tables:[
 {table:'GEN_CHILD',count:3,columns:{ID:sequential('1'),REF_ID:generated('ID'),REF_KIND:generated('KIND')}},
 {table:'GEN_PARENT',count:3,columns:{ID:sequential('9007199254740993'),KIND:{kind:'file',values:['A','B','C']}}},
 {table:'GEN_EXISTING',count:2,columns:{ID:sequential('1'),REF_ID:existing('ID'),REF_KIND:existing('KIND')}},
 {table:'GEN_SELF',count:2,columns:{ID:sequential('100'),KIND:constant('root'),REF_ID:constant(null),REF_KIND:constant('absent')}},
]};
const result = m.materializeTestData(recipe,catalogs);
if(JSON.stringify(result)!==JSON.stringify(m.materializeTestData(recipe,catalogs))) throw new Error('Unstable seed');
process.stdout.write(JSON.stringify(result));
"""
        node = shutil.which('node')
        if node is None:
            raise FileNotFoundError('Native Node executable is unavailable')
        generated = subprocess.run([node, '--input-type=module', '-e', runner, str(module)],
                                   input=json.dumps(catalogs), capture_output=True, text=True,
                                   timeout=30, check=True)
        preview = json.loads(generated.stdout)
        assert len(preview['operations']) == 10, preview
        assert preview['order'].index('GEN_PARENT') < preview['order'].index('GEN_CHILD')
        for operation in preview['operations']:
            request = {'resource_kind': 'table', 'operation_id': 'insert',
                '_provider_route': owned_route, 'target_resource': catalogs[operation['table']]['resource'],
                'draft': {'values': operation['values'], 'options': {}}}
            plan = ADMINISTRATION.plan(request)
            result = ADMINISTRATION.apply(client, plan, connection=handle)
            assert result['staged_in_provider_session'] is True and not result['commit_requested'], result
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM GEN_CHILD')
            assert cursor.fetchone() == (0,)
        connection.rollback()
        with handle.cursor() as cursor:
            cursor.execute('SELECT REF_ID, REF_KIND FROM GEN_CHILD ORDER BY ID')
            assert cursor.fetchall() == [(9007199254740993, 'A'), (9007199254740994, 'B'), (9007199254740995, 'C')]
            cursor.execute('SELECT REF_ID, REF_KIND FROM GEN_SELF ORDER BY ID')
            assert cursor.fetchall() == [(None, 'absent'), (None, 'absent')]
        try:
            client.execute(handle, {'source': "INSERT INTO GEN_CHILD VALUES (99, 999, 'missing')"})
        except RelationalClientError:
            pass
        else:
            raise AssertionError('Native FK constraint was not enforced')
        client.control_transaction(handle, 'rollback')
        with connection.cursor() as cursor:
            for table, count in [('GEN_PARENT', 1), ('GEN_CHILD', 0), ('GEN_EXISTING', 0), ('GEN_SELF', 0)]:
                cursor.execute('SELECT COUNT(*) FROM ' + table)
                assert cursor.fetchone() == (count,)
        connection.rollback()
        return {'passed': True, 'rows_staged': 10, 'seed_repeatable': True,
                'exact_bigint_and_file_values': True, 'composite_foreign_keys': True,
                'single_null_segment_native_fk_semantics': True, 'existing_samples': True,
                'constraints_enforced': True, 'independent_visibility': True, 'explicit_rollback_verified': True}
    finally:
        client.close_session(handle)
