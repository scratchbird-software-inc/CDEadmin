"""Native MariaDB reviewed object replacement, trigger order and sequence continuation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import secrets
from types import SimpleNamespace
from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider, MARIADB_PROFILE, _create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_schema_apply import MariaDBSchemaApplications
from pgadmin.cdeadmin.workspace.mariadb_object_plan import definition


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof={'complete':False,'checks':[]}
    schema='owned_objects_'+secrets.token_hex(8)
    owner=mariadb.connect(**route,autocommit=True,**({'password':password} if password is not None else {}))
    cursor,client=owner.cursor(),None
    try:
        cursor.execute('CREATE DATABASE `'+schema+'`');owner.database=schema
        for source in [
            'CREATE TABLE t(id INT PRIMARY KEY,value VARCHAR(50))',
            'CREATE VIEW v AS SELECT id FROM t',
            'CREATE PROCEDURE p() SELECT 1',
            'CREATE FUNCTION f() RETURNS INT RETURN 1',
            'CREATE PACKAGE pkg PROCEDURE hi(); END',
            'CREATE PACKAGE BODY pkg PROCEDURE hi() BEGIN SELECT 1; END; END',
            'CREATE EVENT ev ON SCHEDULE EVERY 1 DAY DISABLE DO SELECT 1',
            'CREATE SEQUENCE sq START WITH 20 CACHE 0',
            "CREATE TRIGGER tr1 BEFORE INSERT ON t FOR EACH ROW SET NEW.value='first'",
            "CREATE TRIGGER tr2 BEFORE INSERT ON t FOR EACH ROW FOLLOWS tr1 SET NEW.value=CONCAT(NEW.value,' second')",
        ]:cursor.execute(source)
        cursor.execute("SET SESSION sql_mode='ORACLE'")
        cursor.execute('CREATE PACKAGE oracle_pkg AS FUNCTION answer RETURN INT; END')
        cursor.execute('CREATE PACKAGE BODY oracle_pkg AS FUNCTION answer RETURN INT AS BEGIN RETURN 1; END; END')
        cursor.execute('SET SESSION sql_mode=DEFAULT')
        native_route,permissions=provider_access(route,password)
        def require(permission,scope=None):assert permission in {'data_read','administer'} and scope=='resource'
        permissions.require=require
        context=SimpleNamespace(pool_namespace='objects:'+secrets.token_hex(8))
        client=_create_client(MARIADB_PROFILE,permissions,context)
        provider=MariaDBPilotProvider(context,permissions,client)
        selected={**native_route,'database':schema}
        applications=MariaDBSchemaApplications(evidence/'receipts.json')
        def capture():
            native=provider.capture_catalog(selected)
            return build_export(native['resources'],endpoint_id='owned',target_id=schema,
                generation=native['generation'],engine='mariadb',native_model=True)
        def row(document,kind,name):return next(value for value in document['rows'].values() if value['kind']==kind and value['name']==name)
        def change(kind,name,mutate=None,intent=None):
            before=capture();desired=deepcopy(before);target=row(desired,kind,name)
            if mutate is not None:
                original=target['native']['definition'];target['native']['definition']=mutate(original)
                assert original!=target['native']['definition'],'Native fixture mutation did not change '+kind
            if intent is not None:target['native']['mariadb_change']=intent
            preview=plan(before,desired,before);assert preview['ready_for_review'],preview
            preview.update(provider.validate_schema_plan(selected,preview));assert preview['native_grammar_validated'],preview
            receipt=applications.review(preview,before,desired,'owner','binding',schema)
            result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},
                'owner','binding',lambda record:provider.apply_schema_review(selected,record))
            assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
            return result
        change('view','v',lambda source:re.sub(r'\bAS\s+select\b.*','AS SELECT id+1 AS id FROM t',source,flags=re.I|re.S))
        cursor.execute("INSERT INTO t(id) VALUES(1)");cursor.execute('SELECT id FROM v');assert cursor.fetchone()[0]==2
        proof['checks'].append('native_view_alter_preserves_definer_and_changes_query')
        for kind,name in [('procedure','p'),('function','f')]:
            change(kind,name,lambda source:re.sub(r'\b(SELECT|RETURN)\s+1\b',lambda match:match[1]+' 2',source,flags=re.I),
                {'action':'replace','confirmation':name})
            cursor.execute('CALL p()' if kind=='procedure' else 'SELECT f()');assert cursor.fetchone()[0]==2
            while cursor.nextset():pass
        proof['checks'].append('native_procedure_and_function_body_replacement')
        change('package-body','pkg',lambda source:re.sub(r'\bSELECT\s+1\b','SELECT 2',source,flags=re.I),{'action':'replace','confirmation':'pkg'})
        cursor.execute('CALL pkg.hi()');assert cursor.fetchone()[0]==2
        while cursor.nextset():pass
        change('package-body','oracle_pkg',lambda source:re.sub(r'\bRETURN\s+1\b','RETURN 42',source,flags=re.I),
            {'action':'replace','confirmation':'oracle_pkg'})
        cursor.execute('SELECT oracle_pkg.answer()');assert cursor.fetchone()[0]==42
        proof['checks'].append('native_package_body_replacement_retains_declaration_and_oracle_creation_mode')
        change('package-body','pkg',intent={'action':'drop','confirmation':'pkg'})
        assert row(capture(),'package','pkg')
        def spec(source):
            original,match=definition(row(capture(),'package','pkg'),schema)
            return source[:match.end()]+' PROCEDURE replacement(); END'
        change('package','pkg',spec,{'action':'replace','confirmation':'pkg'})
        assert 'replacement' in row(capture(),'package','pkg')['native']['definition']
        proof['checks'].append('native_declaration_replacement_requires_separately_reviewed_body_removal')
        change('trigger','tr1',lambda source:source.replace("'first'","'changed'"),{'action':'replace','confirmation':'tr1'})
        change('trigger','tr2',lambda source:source.replace("' second'","' third'"),{'action':'replace','confirmation':'tr2'})
        cursor.execute('INSERT INTO t(id) VALUES(2)');cursor.execute('SELECT value FROM t WHERE id=2');assert cursor.fetchone()[0]=='changed third'
        triggers=capture()
        assert row(triggers,'trigger','tr1')['native']['trigger_identity']['action_order']==1
        assert row(triggers,'trigger','tr2')['native']['trigger_identity']['action_order']==2
        before=capture();desired=deepcopy(before);inserted=deepcopy(row(before,'trigger','tr2'))
        parent=inserted['native']['navigator_parent_resource_id']
        key='mariadb:'+json.dumps([schema,'trigger',parent,'inserted'],separators=(',',':'))
        inserted.update(resource_id=key,name='inserted',path=[schema,'inserted'])
        inserted['native']['definition']="CREATE TRIGGER inserted BEFORE INSERT ON t FOR EACH ROW SET NEW.value=CONCAT(NEW.value,' inserted')"
        inserted['native']['trigger_identity']['action_order']=2
        desired['rows'][key]=inserted
        preview=plan(before,desired,before);assert preview['ready_for_review'],preview
        preview.update(provider.validate_schema_plan(selected,preview));assert preview['native_grammar_validated'],preview
        receipt=applications.review(preview,before,desired,'owner','binding',schema)
        result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','binding',lambda record:provider.apply_schema_review(selected,record))
        assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
        cursor.execute('INSERT INTO t(id) VALUES(3)');cursor.execute('SELECT value FROM t WHERE id=3');assert cursor.fetchone()[0]=='changed inserted third'
        change('trigger','inserted',intent={'action':'drop','confirmation':'inserted'})
        proof['checks'].append('native_multi_trigger_creation_replacement_and_drop_preserve_precedes_follows_order')
        change('event','ev',lambda source:re.sub(r'\bDO\s+SELECT\s+1\b','DO SELECT 2',source,flags=re.I))
        assert 'SELECT 2' in row(capture(),'event','ev')['native']['definition']
        proof['checks'].append('native_event_alter_retains_complete_schedule_and_time_zone')
        cursor.execute('SELECT NEXT VALUE FOR sq');assert cursor.fetchone()[0]==20
        change('sequence','sq',intent={'action':'alter-options','increment':3,'cache':0})
        cursor.execute('SELECT NEXT VALUE FOR sq');first=cursor.fetchone()[0]
        capture();capture()
        cursor.execute('SELECT NEXT VALUE FOR sq');assert cursor.fetchone()[0]==first+3
        change('sequence','sq',intent={'action':'alter-options','restart':100,'confirmation':'sq'})
        cursor.execute('SELECT NEXT VALUE FOR sq');assert cursor.fetchone()[0]==100
        proof['checks'].append('native_sequence_option_change_and_confirmed_restart_do_not_advance_on_capture')
        change('database',schema,intent={'action':'alter-options','collation':'utf8mb4_bin'})
        cursor.execute('SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=?',(schema,))
        assert cursor.fetchone()[0]=='utf8mb4_bin'
        proof['checks'].append('native_database_collation_alter_excludes_mysql_encryption_grammar')
        proof['complete']=True
    finally:
        if client is not None:client.close()
        cursor.execute('DROP DATABASE IF EXISTS `'+schema+'`');cursor.close();owner.close()
        (evidence/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='mariadb:12.2.2');parser.add_argument('--evidence',type=Path,required=True)
    options=parser.parse_args()
    raise SystemExit(0 if run(options.image,options.evidence,qualify)['complete'] else 1)
