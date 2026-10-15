"""Native recipe SQL effects and rollback on an owned MariaDB 12.2.2 fixture."""
import argparse
import json
import secrets
from pathlib import Path
from types import SimpleNamespace
from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider, MARIADB_PROFILE, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mariadb_test_data import generate, template, FORMAT


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    schema = 'owned_recipe_' + secrets.token_hex(8)
    owner = mariadb.connect(**route, autocommit=True, **({'password': password} if password is not None else {}))
    cursor, client, writer = owner.cursor(), None, None
    try:
        cursor.execute(f'CREATE DATABASE `{schema}`');owner.database = schema
        cursor.execute('CREATE TABLE parent (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, amount DECIMAL(65,30), doc JSON, embedding VECTOR(2), calc INT AS (JSON_VALID(doc)) VIRTUAL) ENGINE=InnoDB')
        cursor.execute('CREATE TABLE child (id BIGINT UNSIGNED, payload VARBINARY(20), FOREIGN KEY (id) REFERENCES parent(id)) ENGINE=InnoDB')
        native_route, permissions = provider_access(route, password)
        def require(permission_id, scope=None):
            assert (permission_id, scope) == ('data_read', 'resource')
        permissions.require = require
        context = SimpleNamespace(pool_namespace='recipe:' + secrets.token_hex(8))
        client = _create_client(MARIADB_PROFILE, permissions, context)
        provider = MariaDBPilotProvider(context, permissions, client)
        captured = provider.capture_catalog({**native_route, 'database': schema})
        model = build_export(captured['resources'], endpoint_id='owned', target_id=schema,
            generation=captured['generation'], engine='mariadb', native_model=True)
        tables = template(model)['tables'];ids = {row['name']:row['resource_id'] for row in tables}
        assert not next(col for row in tables if row['name']=='parent' for col in row['columns'] if col['name']=='calc')['insertable']
        recipe = {'format': FORMAT, 'scope': {'endpoint_id':'owned', 'database_target_id':schema}, 'seed': 42,
            'tables': [{'table':ids['child'], 'count':2, 'columns':{'id':{'kind':'returned','table':ids['parent'],'column':'id'},
                'payload':{'kind':'constant','value':{'type':'binary','value':'AP8='}}}},
                {'table':ids['parent'],'count':2,'columns':{'id':{'kind':'default'},
                'amount':{'kind':'constant','value':{'type':'decimal','value':'12345678901234567890123456789012345.123456789012345678901234567890'}},
                'doc':{'kind':'constant','value':{'type':'json','value':'{"n":9007199254740993}'}},
                'embedding':{'kind':'constant','value':{'type':'vector','value':'[1,2]'}}}}]}
        result = generate(model, recipe)
        assert not result['executed'] and result['rows']==4
        cursor.execute('SELECT COUNT(*) FROM parent');assert cursor.fetchone()[0]==0
        proof['checks'].append('native_catalog_generated_columns_and_generation_does_not_write')
        writer = mariadb.connect(**route, database=schema, autocommit=False, **({'password': password} if password is not None else {}))
        with writer.cursor() as execution:
            for statement in result['source'].split(';'):
                if statement.strip():execution.execute(statement)
            execution.execute('SELECT CAST(amount AS CHAR),doc,VEC_ToText(embedding),calc FROM parent ORDER BY id')
            rows=execution.fetchall();assert len(rows)==2
            for amount,doc,vector,calculated in rows:
                assert amount=='12345678901234567890123456789012345.123456789012345678901234567890'
                assert json.loads(doc)['n']==9007199254740993 and json.loads(vector)==[1,2] and calculated==1
            execution.execute('SELECT COUNT(*) FROM child JOIN parent USING(id) WHERE payload=X\'00ff\'')
            assert execution.fetchone()[0]==2
        assert writer.server_status & 1
        cursor.execute('SELECT COUNT(*) FROM parent');assert cursor.fetchone()[0]==0
        proof['checks'].append('native_json_vector_decimal_binary_returned_parent_keys_inside_user_transaction')
        writer.rollback()
        cursor.execute('SELECT COUNT(*) FROM parent');assert cursor.fetchone()[0]==0
        cursor.execute('SELECT COUNT(*) FROM child');assert cursor.fetchone()[0]==0
        proof['checks'].append('caller_owned_native_rollback_removes_transactional_fixture_rows')
        (evidence/'generated.sql').write_text(result['source'])
        proof['complete']=True
    finally:
        if writer is not None:writer.rollback();writer.close()
        if client is not None:client.close()
        cursor.execute(f'DROP DATABASE IF EXISTS `{schema}`');cursor.close();owner.close()
        (evidence/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='mariadb:12.2.2');parser.add_argument('--evidence',type=Path,required=True)
    options=parser.parse_args();result=run(options.image,options.evidence,qualify)
    raise SystemExit(0 if result['complete'] else 1)
