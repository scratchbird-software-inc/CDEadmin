"""Descriptor -> provider -> original native configuration signatures/effects."""
import os,sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client,SQLiteProvider
from pgadmin.cdeadmin.providers.sqlite.extended_config import BOOLEANS
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft

pytestmark=pytest.mark.skipif(not os.environ.get('CDEADMIN_SQLITE_CONFIG_LIBRARY'),reason='Native configuration helper not selected')


@pytest.fixture
def native(tmp_path):
    client=_create_client();source=client.open_session({'route':{'database':str(tmp_path/'owned.db'),'filesystem_root':str(tmp_path),'cached_statements':0}})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:source)
    try:yield source,provider,tmp_path
    finally:client.close()


def call(native,operation,name,revision=0,**values):
    return SQLiteProvider.native_connection_config_action(native[1],{'operation':operation,'config':name,'session_id':'owned','language_profile':'sqlite-sql','_native_work_revision':revision,**values})


def apply(native,name,value,revision=0,receipt=None):
    review=receipt or call(native,'review',name,revision,value=value)
    fields={'value':value,'confirmed':True}
    if name!='lookaside':fields['expected_value']=review['expected_value']
    if name in {'main_dbname','lookaside'}:
        fields['review_id']=review['review_id']
        fields['schema_alias_change_confirmed'if name=='main_dbname'else'native_allocation_change_confirmed']=True
    draft=operation_draft(engine_operations('sqlite')['set_connection_config_'+name+'@database'],fields)
    return call(native,'set_connection_config',name,revision,**draft)


@pytest.mark.parametrize('name',BOOLEANS)
def test_native_boolean_read_write_availability_and_original_transaction(native,name):
    source=native[0];available=source._cdeadmin_config_api.module.boolean(source._cdeadmin_config_api.capsule,name,-1)[0]==0
    if not available:
        with pytest.raises(RelationalClientError,match='absent'):call(native,'inspect',name)
        return
    source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    before=call(native,'inspect',name)['effective_value']
    result=apply(native,name,not before)
    assert result['accepted'] and result['effective_value']is not before and result['outcome']=='applied'
    assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert call(native,'inspect',name)['effective_value']is not before
    assert not any(result[k]for k in ['commit_requested','rollback_requested','file_persisted','future_connection_defaults_changed','automatic_retry'])


def test_native_actual_comment_parser_and_scan_order(native):
    source=native[0]
    if sqlite3.sqlite_version_info<(3,49,0):
        with pytest.raises(RelationalClientError):call(native,'inspect','enable_comments')
    else:
        apply(native,'enable_comments',False)
        with pytest.raises(sqlite3.OperationalError):source.execute('SELECT /* disabled */ 1')
        apply(native,'enable_comments',True)
        assert source.execute('SELECT /* enabled */ 1').fetchone()==(1,)
    if sqlite3.sqlite_version_info>=(3,42,0):
        source.executescript('CREATE TABLE owned(value);INSERT INTO owned VALUES(1),(2),(3)')
        apply(native,'reverse_scanorder',True)
        assert source.execute('SELECT value FROM owned').fetchall()==[(3,),(2,),(1,)]
        assert source.execute('SELECT value FROM owned ORDER BY value').fetchall()==[(1,),(2,),(3,)]


def test_native_attach_creation_and_write_policy(native):
    source,_,root=native
    if sqlite3.sqlite_version_info<(3,49,0):
        with pytest.raises(RelationalClientError):call(native,'inspect','enable_attach_create')
        return
    path=root/'attached.db'
    apply(native,'enable_attach_create',False)
    with pytest.raises(sqlite3.OperationalError):source.execute('ATTACH DATABASE ? AS blocked',(str(path),))
    assert not path.exists()
    apply(native,'enable_attach_create',True)
    source.execute('ATTACH DATABASE ? AS owned',(str(path),));source.execute('CREATE TABLE owned.data(value)');source.execute('DETACH DATABASE owned')
    apply(native,'enable_attach_write',False)
    source.execute('ATTACH DATABASE ? AS owned',(str(path),))
    with pytest.raises(sqlite3.OperationalError):source.execute('INSERT INTO owned.data VALUES(7)')
    source.rollback();source.execute('DETACH DATABASE owned')
    apply(native,'enable_attach_write',True)
    source.execute('ATTACH DATABASE ? AS owned',(str(path),));source.execute('INSERT INTO owned.data VALUES(7)')
    assert source.execute('SELECT * FROM owned.data').fetchall()==[(7,)]


def test_native_main_alias_typed_review_cas_invalidation_and_one_use(native):
    source=native[0];source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    value='Alias 雪 "quote"'
    review=call(native,'review','main_dbname',value=value)
    with pytest.raises(RelationalClientError):apply(native,'main_dbname',value,revision=1,receipt=review)
    result=apply(native,'main_dbname',value,receipt=review)
    assert result['effective_value']==value and result['invalidate_catalog_references']
    assert source.execute('PRAGMA database_list').fetchone()[1]==value
    assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    with pytest.raises(RelationalClientError):apply(native,'main_dbname',value,receipt=review)
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert source.execute('PRAGMA database_list').fetchone()[1]==value
    with pytest.raises(RelationalClientError):call(native,'review','main_dbname',value='TEMP')
    source.execute('ATTACH DATABASE ? AS Attached',(str(native[2]/'peer.db'),))
    with pytest.raises(RelationalClientError):call(native,'review','main_dbname',value='aTTACHED')


def test_native_lookaside_success_has_no_invented_geometry_and_busy_is_known_refusal(native):
    source=native[0]
    grid=[{'slot_size':128,'slot_count':128}]
    review=call(native,'review','lookaside',value=grid)
    assert review['ready_to_apply'] and review['before_value']is None and not review['before_configuration_observed']
    with pytest.raises(RelationalClientError):apply(native,'lookaside',grid,revision=1,receipt=review)
    result=apply(native,'lookaside',grid,receipt=review)
    assert result['accepted'] and result['outcome']=='native_acknowledged_geometry_unobserved'
    assert result['effective_value']is None and not result['allocation_geometry_observed']
    with pytest.raises(RelationalClientError):apply(native,'lookaside',grid,receipt=review)
    source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    review=call(native,'review','lookaside',value=grid)
    assert not review['ready_to_apply'] and review['native_usage']['used_slots']>0
    result=apply(native,'lookaside',grid,receipt=review)
    assert not result['accepted'] and result['outcome']=='native_refused' and result['native_result_code']==sqlite3.SQLITE_BUSY
    assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    assert id(source)not in native[1].client._uncertain


@pytest.mark.parametrize('value',[None,[],[{},{}],{'slot_size':True,'slot_count':1},[{'slot_size':9,'slot_count':1}],[{'slot_size':65536,'slot_count':1}],[{'slot_size':128,'slot_count':2147483648}],[{'slot_size':128,'slot_count':1000000}]])
def test_lookaside_typed_geometry_refusals(native,value):
    with pytest.raises(RelationalClientError):call(native,'review','lookaside',value=value)


def test_missing_native_bridge_and_private_source_guards_are_not_silently_reopened(native):
    source,provider,_=native;api=source._cdeadmin_config_api
    source._cdeadmin_config_api=None
    try:
        with pytest.raises(RelationalClientError,match='original handle'):call(native,'inspect','lookaside')
    finally:source._cdeadmin_config_api=api
    provider.client._busy.add(id(source))
    try:
        with pytest.raises(RelationalClientError):call(native,'review','main_dbname',value='renamed')
    finally:provider.client._busy.discard(id(source))
    provider._require=Mock(side_effect=PermissionError('denied'))
    with pytest.raises(PermissionError):call(native,'review','lookaside',value=[{'slot_size':128,'slot_count':1}])


def test_native_fp_digits_exact_integer_signature_and_actual_text_conversion(native):
    source=native[0];bridge=source._cdeadmin_config_api
    if bridge.module.integer(bridge.capsule,0)[0]!=0:
        with pytest.raises(RelationalClientError,match='absent'):call(native,'inspect','fp_digits')
        return
    for bad in [True,'17',2,24,None]:
        with pytest.raises(RelationalClientError):call(native,'review','fp_digits',value=bad)
    source.executescript('CREATE TABLE owned(value);SAVEPOINT caller;INSERT INTO owned VALUES(7)')
    apply(native,'fp_digits',3)
    low=source.execute('SELECT CAST(? AS TEXT),?',(1.2345678901234567,1.2345678901234567)).fetchone()
    apply(native,'fp_digits',23)
    high=source.execute('SELECT CAST(? AS TEXT),?',(1.2345678901234567,1.2345678901234567)).fetchone()
    assert low[0]!=high[0] and low[1]==high[1]==1.2345678901234567
    assert source.in_transaction and source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert call(native,'inspect','fp_digits')['effective_value']==23


def test_capability_observation_does_not_prepare_sql_or_occupy_lookaside(native):
    source=native[0];trace=[];source.set_trace_callback(trace.append)
    result=SQLiteProvider.native_connection_config_action(native[1],{'operation':'capabilities'})
    assert len(result['configurations'])==24 and result['original_sql_commands_sent']==0 and not result['setter_dispatched']
    assert trace==[]
    rows={row['config']:row for row in result['configurations']}
    assert rows['enable_fkey']['available_observed']
    assert rows['main_dbname']['signature_admitted'] and not rows['main_dbname']['current_configuration_observed']
    review=call(native,'review','lookaside',value=[{'slot_size':128,'slot_count':128}])
    assert review['native_usage']['used_slots']==0 and review['ready_to_apply']
