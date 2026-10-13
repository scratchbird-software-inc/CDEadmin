"""MariaDB native definitions preserve object targets and explicit replacements."""
from copy import deepcopy
import pytest
from tools.tests.test_mariadb_sql_export import model
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_object_plan import compile_object


def row(document, kind): return next(value for value in document['rows'].values() if value['kind']==kind)


def test_view_alter_preserves_native_definer_query_and_exact_target():
    before=model();desired=deepcopy(before)
    view=row(desired,'view');view['native']['definition']=view['native']['definition'].replace('AS SELECT','AS SELECT DISTINCT')
    preview=plan(before,desired,before)
    assert preview['ready_for_review'] and preview['operations'][0]['source'].startswith('ALTER VIEW `demo`.`v` AS SELECT DISTINCT')
    view['native']['definition']=view['native']['definition'].replace('`v`','`other`',1)
    assert plan(before,desired,before)['blockers']


def test_package_body_replacement_is_distinct_and_declaration_cannot_erase_body_implicitly():
    before=model();desired=deepcopy(before)
    body=row(desired,'package-body');body['native']['definition']=body['native']['definition'].replace('SELECT 1','SELECT 2')
    assert plan(before,desired,before)['blockers']
    body['native']['mariadb_change']={'action':'replace','confirmation':'pkg'}
    preview=plan(before,desired,before)
    assert preview['ready_for_review'] and preview['operations'][0]['source'].startswith('CREATE OR REPLACE PACKAGE BODY `demo`.`pkg`')
    spec=row(desired,'package');spec['native']['definition']+=';'
    spec['native']['mariadb_change']={'action':'replace','confirmation':'pkg'}
    assert any('existing body' in item['reason'] for item in plan(before,desired,before)['blockers'])


def test_sequence_option_changes_do_not_infer_restart_from_configuration_capture():
    before=model();desired=deepcopy(before);seq=row(desired,'sequence')
    seq['native']['mariadb_change']={'action':'alter-options','increment':3,'cache':20,'cycle':False}
    preview=plan(before,desired,before)
    source=preview['operations'][0]['source']
    assert preview['ready_for_review'] and source=='ALTER SEQUENCE `demo`.`seq` INCREMENT BY 3 CACHE 20 NOCYCLE'
    seq['native']['mariadb_change']['restart']=100
    assert plan(before,desired,before)['blockers']
    seq['native']['mariadb_change']['confirmation']='seq'
    assert 'RESTART WITH 100' in plan(before,desired,before)['operations'][0]['source']
    seq['native']['mariadb_change']['cache']=True
    assert plan(before,desired,before)['blockers']


def test_database_options_exclude_mysql_encryption_grammar_and_database_drop():
    before=model();desired=deepcopy(before);database=row(desired,'database')
    database['native']['mariadb_change']={'action':'alter-options','collation':'utf8mb4_bin'}
    assert plan(before,desired,before)['operations'][0]['source']=='ALTER DATABASE `demo` DEFAULT COLLATE `utf8mb4_bin`'
    database['native']['mariadb_change']['encryption']='Y'
    assert plan(before,desired,before)['blockers']
    database['native']['mariadb_change']={'action':'drop','confirmation':'demo'}
    assert plan(before,desired,before)['blockers']


def test_trigger_sibling_compilation_preserves_native_server_uid_and_parent_identity():
    import json
    before=model();owner=row(before,'table')
    for position,name in [(1,'tr1'),(2,'tr2')]:
        key='mariadb:'+json.dumps(['demo','trigger',owner['resource_id'],name],separators=(',',':'))
        native={'database':'demo','system_object':False,'navigator_parent_resource_id':owner['resource_id'],
            'definition':'CREATE TRIGGER '+name+' BEFORE INSERT ON a FOR EACH ROW SET NEW.id=1',
            'definition_context':deepcopy(owner['native']['definition_context']),
            'trigger_identity':{'database':'demo','table':'a','timing':'BEFORE','event':'INSERT','action_order':position}}
        before['rows'][key]={'resource_id':key,'kind':'trigger','name':name,'path':['demo',name],'system':'false','native':native}
    desired=deepcopy(before);trigger=next(value for value in desired['rows'].values() if value['name']=='tr1')
    trigger['native']['definition']=trigger['native']['definition'].replace('NEW.id=1','NEW.id=2')
    trigger['native']['mariadb_change']={'action':'replace','confirmation':'tr1'}
    preview=plan(before,desired,before)
    assert preview['ready_for_review'] and preview['server_uid']=='native'
    assert 'FOR EACH ROW PRECEDES `tr2` SET NEW.id=2' in preview['operations'][0]['source']
    assert len(preview['operations'][0]['trigger_order_baseline'])==2
