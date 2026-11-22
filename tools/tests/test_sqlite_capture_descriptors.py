"""Typed capture descriptors preserve exact native requests and owned routes."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_sqlite_extensions import native,libraries
from pgadmin.cdeadmin.workspace.sqlite_editor_operations import compile_request,contract,serve


def test_native_capture_descriptor_lifecycle_on_original_handle(native,monkeypatch):
    import config,os
    if 'CDEADMIN_SQLITE_SESSION_LIBRARY' not in os.environ:
        pytest.skip('CDEADMIN_SQLITE_SESSION_LIBRARY requires SQLite 3.53.0+')
    monkeypatch.setattr(config,'CDEADMIN_SQLITE_SESSION_LIBRARY',os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'])
    n=native
    def run(operation,**draft):
        action,request=compile_request('editor_capture_'+operation,draft)
        assert action=='sqlite_native_sessions'
        return n.studio.sqlite_native_session_action(n.context,n.session.session_id,request)
    assert run('inventory')['helper_available']
    n.connection.execute('CREATE TABLE captured(id INTEGER PRIMARY KEY,body TEXT)');n.connection.commit()
    capture=run('open',database='main',estimate_size=True)['capture']['capture_id']
    run('object_config',capture_id=capture,option='estimate_size',value=True)
    run('attach',capture_id=capture,table_name='captured')
    run('configure',capture_id=capture,enabled_mode='ON',indirect_mode='OFF')
    run('table_filter',capture_id=capture,pattern='capt*')
    n.connection.execute("INSERT INTO captured VALUES(9007199254740993,'owned')")
    assert run('status',capture_id=capture)['capture']['capture_id']==capture
    assert n.connection.in_transaction
    assert run('close',capture_id=capture,confirmed=True)['closed']
    assert n.connection.execute('SELECT id FROM captured').fetchall()==[(9007199254740993,)]


def test_typed_apply_review_preserves_all_native_conflict_choices():
    action,request=compile_request('editor_apply_review',dict(source_database_target_id='target',source_job_id='job',path='capture.changeset',conflict_data='replace',include_rebase=True,interactive_conflicts=True))
    assert action=='sqlite_changeset'and request['operation']=='review'
    assert request['options']['conflicts']==dict(data='replace',not_found='abort',conflict='abort',constraint='abort',foreign_key='abort')
    assert request['options']['foreign_keys']and request['options']['include_rebase']and request['options']['interactive_conflicts']
    _,request=compile_request('editor_apply_decide',dict(job_id='job',challenge='A'*32,choice='omit',remember_kind=True))
    assert request==dict(operation='decide',job_id='job',response=dict(challenge='A'*32,choice='omit',remember_kind=True))


@pytest.mark.parametrize('mode',['page','cell','extract'])
def test_typed_inspection_modes_only_forward_native_operands(mode):
    values=dict(input_database_target_id='target',input_kind='capture',input_job_id='job',input_path='capture.changeset')
    if mode!='page':values.update(record_number='9007199254740993',column_index=0,side='new')
    _,request=compile_request('editor_inspection_review_'+mode,values)
    assert request['input']==dict(database_target_id='target',kind='capture',job_id='job',path='capture.changeset')
    assert request['operation']=='inspect_review'and request['options']['mode']==mode
    if mode!='page':assert request['options']['record_number']=='9007199254740993'
    if mode=='extract':assert not {'byte_offset','byte_limit'}&request['options'].keys()


@pytest.mark.parametrize('group,op,expected', [('export','status','status'),('apply','status','status'),('transform','status','transform_status'),('inspection','status','inspect_status'),('diff','status','diff_status'),('upload','status','upload_status')])
def test_fixed_owned_service_routes_preserve_target_and_job(group,op,expected):
    service=Mock();server=SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='sqlite-native',provider_id='org.cdeadmin.sqlite'))
    serve(service,server,dict(database_target_id='target',request=dict(operation_id='editor_'+group+'_'+op,draft=dict(job_id='job'))))
    method=service.sqlite_capture_export if group=='export'else service.sqlite_changeset
    method.assert_called_once_with(server,expected,dict(database_target_id='target',job_id='job'))


@pytest.mark.parametrize('identity,values',[('editor_apply_review',dict(source_database_target_id='target',source_job_id='job',path='capture.changeset',conflict_constraint='replace')),('editor_capture_attach',dict(capture_id='capture',table_mode='EXACT')),('editor_upload_chunk',dict(job_id='job',offset=1,data_base64='AA==',sha256='a'*64)),('editor_transform_review',dict(inputs=[dict(database_target_id='target',kind='capture',job_id='job',path='capture.changeset',host_path='/tmp/x')],transform_operation='invert'))])
def test_untyped_or_unrelated_native_authority_is_refused(identity,values):
    with pytest.raises(ValueError):compile_request(identity,values)
