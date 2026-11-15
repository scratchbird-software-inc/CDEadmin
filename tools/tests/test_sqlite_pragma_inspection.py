"""Native getter value/rowset inspection without accidental action execution."""
import sqlite3
import pytest
from test_sqlite_connection_pragmas import native,run  # noqa: F401
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft


def test_native_scalar_and_object_rowsets_keep_pending_rows_and_quoted_names(native):
    source=native[2];name="exact '); DROP TABLE retained;--"
    source.execute('CREATE TABLE retained(value)')
    source.execute('CREATE TABLE "'+name.replace('"','""')+'"(id INTEGER,value TEXT)')
    source.commit();source.execute('INSERT INTO retained VALUES(7)')
    draft=operation_draft(engine_operations('sqlite')['inspect_value@pragma'],{'schema':'main','object_name':name})
    result=run(native,'inspect_pragma_value',pragma='table_xinfo',**draft)
    assert result['outcome']=='observed' and len(result['rows'])==2
    assert [row[1]for row in result['rows']]==['id','value']
    assert not result['setting_dispatched'] and result['transaction_open']
    assert source.execute('SELECT * FROM retained').fetchall()==[(7,)]
    result=run(native,'inspect_pragma_value',pragma='user_version')
    assert result['rows']==[[0]] and result['native_storage_classes']==[['integer']]
    assert result['management_declared'] and not result['mutation_admission_observed']
    source.rollback();assert source.execute('SELECT * FROM retained').fetchall()==[]


@pytest.mark.parametrize('name',['wal_checkpoint','optimize','shrink_memory','integrity_check','case_sensitive_like','unknown; VACUUM'])
def test_action_or_unknown_names_never_become_getter_dispatch(native,name):
    seen=[];native[2].set_trace_callback(seen.append)
    with pytest.raises(RelationalClientError):run(native,'inspect_pragma_value',pragma=name)
    assert seen==[]


def test_unknown_build_getter_is_unavailable_and_empty_metadata_is_not_a_default(native):
    result=run(native,'inspect_pragma_value',pragma='parser_trace')
    assert result['outcome']=='unavailable' and not result['native_name_present']
    empty=run(native,'inspect_pragma_value',pragma='table_info',object_name='not_a_native_object')
    assert empty['outcome']=='observed' and empty['rows']==[]
    assert not empty['object_existence_inferred'] and not empty['empty_result_default_inferred']


def test_inspection_capabilities_are_declarations_not_runtime_feature_claims(native):
    result=run(native,'pragma_inspection_capabilities')
    assert 'table_info' in result['object_argument_required']
    assert 'wal_checkpoint' in result['non_getter_workflows']
    assert not result['native_name_availability_observed']
