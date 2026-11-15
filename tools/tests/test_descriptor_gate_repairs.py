"""Typed descriptor repairs preserve native field values and declared tool ownership."""
import json
from pathlib import Path
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService
from pgadmin.cdeadmin.workspace.service import database_workspace_tool_tabs, sql_builder_declaration
from ui_descriptor_roundtrip import operation_draft

ROOT=Path(__file__).resolve().parents[2]


def test_registration_references_are_registered_unique_and_persistent():
    registry=json.loads((ROOT/'web/pgadmin/static/js/cdeadmin_ui/navigation/formReferences.json').read_text())['forms']
    service=UIDescriptorService()
    refs=[]
    for engine in ['apache_ignite','cassandra','clickhouse','foundationdb','influxdb','milvus','mongodb','neo4j','opensearch','redis','tikv']:
        form=service.engine(engine)['forms']['server']
        assert form['form_reference']==registry[f'descriptor-form:{engine}:server']['reference']
        refs.append(form['form_reference'])
    assert len(set(refs))==11


def test_postgresql_partition_comments_remain_exact_multiline_strings():
    service=UIDescriptorService()
    operations=[x for x in service.engine('postgresql')['operations']if x['operation_id']=='create-partition']
    assert len(operations)==2
    for op in operations:
        field=next(x for x in op['fields']if x['field_id']=='description')
        assert field['control']=='code' and field['language']=='text'
        assert operation_draft(op,{'description':"owner's note\nsecond line"})['description']=="owner's note\nsecond line"


def test_workspace_tabs_follow_declarations_without_cross_engine_tool_leakage():
    service=UIDescriptorService()
    for engine in service.engine_ids():
        bundle=service.engine(engine)
        expected=sorted({t['arguments']['tab']for t in bundle.get('tools',[])
            if t.get('scope')=='database'and t.get('handler')=='open_workspace'and t.get('arguments',{}).get('tab')})
        for profile in bundle['capabilities']['profiles']:
            endpoint={'identity':{'profile_id':profile}}
            assert database_workspace_tool_tabs(endpoint)==expected
            assert sql_builder_declaration(endpoint)==(bundle['capabilities'].get('sql_builder')or None)
    pg=database_workspace_tool_tabs({'identity':{'profile_id':'postgresql-native'}})
    assert 'postgresql-test-data'in pg and 'postgresql-large-object-files'in pg
    for endpoint in [None,{}, {'identity':{'profile_id':'unregistered'}},{'identity':{'profile_id':'sqlite-native'}}]:
        tabs=database_workspace_tool_tabs(endpoint)
        assert 'postgresql-test-data'not in tabs and 'postgresql-large-object-files'not in tabs
