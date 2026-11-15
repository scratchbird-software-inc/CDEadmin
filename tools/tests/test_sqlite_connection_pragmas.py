"""Descriptor -> original-handle flag controls and actual native SQL effects."""
import sqlite3
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client, SQLiteProvider
from pgadmin.cdeadmin.providers.sqlite.connection_pragmas import action, FLAGS
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft


@pytest.fixture
def native(tmp_path):
    path=tmp_path/'flags.db'
    client=_create_client()
    source=client.open_session({'route':{'database':str(path),'filesystem_root':str(tmp_path)}})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:source)
    try:yield path,client,source,provider
    finally:client.close()


def run(native,operation,**values):
    return SQLiteProvider.native_connection_pragmas_action(native[3],{'operation':operation,**values})


def set_flag(native,name,value):
    before=run(native,'inspect',pragma=name)['effective_value']
    review=run(native,'review',pragma=name,value=value)
    assert review['effective_value']==before
    op=engine_operations('sqlite')['set_connection_pragma_'+name+'@database']
    draft=operation_draft(op,{'value':value,'expected_value':review['expected_value'],'confirmed':True})
    result=run(native,'set_connection_pragma',pragma=name,**draft)
    assert result['effective_value'] is value and result['outcome']=='applied'
    assert not any(result[k]for k in ['file_persisted','future_connection_defaults_changed','commit_requested','rollback_requested','automatic_retry'])
    return result


def test_foreign_keys_native_enforcement_and_pending_transaction_refusal(native):
    source=native[2]
    source.executescript('CREATE TABLE parent(id PRIMARY KEY); CREATE TABLE child(id REFERENCES parent(id))')
    set_flag(native,'foreign_keys',True)
    with pytest.raises(sqlite3.IntegrityError):source.execute('INSERT INTO child VALUES(7)')
    assert source.in_transaction
    before=source.execute('PRAGMA foreign_keys').fetchone()[0]
    assert not run(native,'review',pragma='foreign_keys',value=False)['ready_to_apply']
    with pytest.raises(RelationalClientError,match='caller transaction'):
        run(native,'set_connection_pragma',pragma='foreign_keys',value=False,expected_value=bool(before),confirmed=True)
    assert source.in_transaction and source.execute('PRAGMA foreign_keys').fetchone()[0]==before
    source.rollback()
    set_flag(native,'foreign_keys',False)
    source.execute('INSERT INTO child VALUES(7)')
    assert source.execute('SELECT * FROM child').fetchall()==[(7,)]


def test_query_only_blocks_native_writes_and_can_be_restored_without_settling_pending_work(native):
    source=native[2];source.executescript('CREATE TABLE owned(id); SAVEPOINT caller; INSERT INTO owned VALUES(7)')
    set_flag(native,'query_only',True)
    assert source.execute('SELECT * FROM owned').fetchall()==[(7,)]
    with pytest.raises(sqlite3.OperationalError) as error:source.execute('INSERT INTO owned VALUES(8)')
    assert error.value.sqlite_errorcode==sqlite3.SQLITE_READONLY
    assert source.in_transaction
    set_flag(native,'query_only',False)
    source.execute('INSERT INTO owned VALUES(8)')
    assert source.execute('SELECT * FROM owned').fetchall()==[(7,),(8,)]
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert source.execute('SELECT * FROM owned').fetchall()==[]


def test_recursive_triggers_changes_actual_same_trigger_execution(native):
    source=native[2]
    source.executescript('CREATE TABLE counter(value); INSERT INTO counter VALUES(0); '
        'CREATE TRIGGER bump AFTER UPDATE ON counter WHEN NEW.value<3 '
        'BEGIN UPDATE counter SET value=NEW.value+1; END;')
    set_flag(native,'recursive_triggers',False)
    source.execute('UPDATE counter SET value=1')
    assert source.execute('SELECT value FROM counter').fetchone()==(2,)
    source.rollback()
    set_flag(native,'recursive_triggers',True)
    source.execute('UPDATE counter SET value=1')
    assert source.execute('SELECT value FROM counter').fetchone()==(3,)


def test_read_uncommitted_flag_does_not_claim_dirty_reads_with_private_caches(native):
    source=native[2];source.execute('CREATE TABLE committed(value)');source.commit()
    with closing(sqlite3.connect(native[0])) as peer:
        peer.execute('INSERT INTO committed VALUES(7)')
        set_flag(native,'read_uncommitted',True)
        assert source.execute('SELECT * FROM committed').fetchall()==[]
        set_flag(native,'read_uncommitted',False)
        assert source.execute('SELECT * FROM committed').fetchall()==[]
        peer.rollback()


def test_reverse_unordered_selects_reverses_supported_scan_but_preserves_explicit_order(native):
    source=native[2];source.executescript('CREATE TABLE scan(value); INSERT INTO scan VALUES(1),(2),(3)')
    set_flag(native,'reverse_unordered_selects',False)
    forward=source.execute('SELECT value FROM scan').fetchall()
    set_flag(native,'reverse_unordered_selects',True)
    assert source.execute('SELECT value FROM scan').fetchall()==list(reversed(forward))
    assert source.execute('SELECT value FROM scan ORDER BY value').fetchall()==[(1,),(2,),(3,)]


@pytest.mark.parametrize('name',list(FLAGS))
def test_flag_per_handle_defaults_stale_checks_and_permission(native,name):
    source=native[2]
    before=run(native,'inspect',pragma=name)['effective_value']
    with closing(sqlite3.connect(native[0])) as peer:
        peer_before=peer.execute('PRAGMA '+name).fetchone()[0]
        set_flag(native,name,not before)
        assert peer.execute('PRAGMA '+name).fetchone()[0]==peer_before
        with pytest.raises(RelationalClientError,match='changed'):
            run(native,'set_connection_pragma',pragma=name,value=before,expected_value=before,confirmed=True)
        assert run(native,'inspect',pragma=name)['effective_value'] is not before
    native[3]._require.assert_any_call('administer')
    set_flag(native,name,before)


@pytest.mark.parametrize('values',[{'pragma':'unknown'},{'value':1},{'value':'ON'},{'expected_value':0},{'confirmed':'yes'},{'schema':'temp'}])
def test_invalid_request_never_dispatches_setter(native,values):
    before=run(native,'inspect',pragma='foreign_keys')['effective_value']
    with pytest.raises(RelationalClientError):
        run(native,'set_connection_pragma',**{'pragma':'foreign_keys','value':not before,'expected_value':before,'confirmed':True,**values})
    assert run(native,'inspect',pragma='foreign_keys')['effective_value']==before


def test_read_uncommitted_native_dirty_visibility_requires_actual_shared_cache(tmp_path):
    path=tmp_path/'shared.db'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE TABLE owned(value)');seed.commit()
    client=_create_client()
    source=client.open_session({'route':{'database':str(path),'filesystem_root':str(tmp_path),'uri_cache':'shared'}})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:source)
    selected=(path,client,source,provider)
    try:
        with closing(sqlite3.connect(path.as_uri()+'?cache=shared',uri=True)) as peer:
            peer.execute('INSERT INTO owned VALUES(7)')
            set_flag(selected,'read_uncommitted',False)
            with pytest.raises(sqlite3.OperationalError) as error:source.execute('SELECT * FROM owned').fetchall()
            assert error.value.sqlite_errorcode & 255 == sqlite3.SQLITE_LOCKED
            set_flag(selected,'read_uncommitted',True)
            assert source.execute('SELECT * FROM owned').fetchall()==[(7,)]
            assert peer.in_transaction
            set_flag(selected,'read_uncommitted',False)
            with pytest.raises(sqlite3.OperationalError):source.execute('SELECT * FROM owned').fetchall()
            peer.rollback()
            assert source.execute('SELECT * FROM owned').fetchall()==[]
    finally:client.close()


@pytest.mark.parametrize('name',[n for n in FLAGS if n!='foreign_keys'])
def test_flag_changes_preserve_savepoint_and_are_not_restored_by_rollback(native,name):
    source=native[2];before=run(native,'inspect',pragma=name)['effective_value']
    source.executescript('CREATE TABLE pending(value); SAVEPOINT caller; INSERT INTO pending VALUES(7)')
    result=set_flag(native,name,not before)
    assert result['transaction_open'] and source.execute('SELECT * FROM pending').fetchall()==[(7,)]
    source.execute('ROLLBACK TO caller')
    assert run(native,'inspect',pragma=name)['effective_value'] is not before
    assert source.execute('SELECT * FROM pending').fetchall()==[]
    set_flag(native,name,before)
    source.execute('RELEASE caller')


def test_native_authorizer_is_preserved_and_its_setter_refusal_never_claims_success(native):
    source=native[2];before=run(native,'inspect',pragma='foreign_keys')['effective_value'];calls=[]
    def authorize(code,a,b,*_):
        if code==sqlite3.SQLITE_PRAGMA:
            calls.append((a,b))
            if b is not None:return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    source.set_authorizer(authorize)
    with pytest.raises(RelationalClientError) as error:
        run(native,'set_connection_pragma',pragma='foreign_keys',value=not before,expected_value=before,confirmed=True)
    assert error.value.native_outcome=='unknown_outcome'
    assert run(native,'inspect',pragma='foreign_keys')['effective_value']==before
    assert sum(b is not None for _,b in calls)==1
    assert len(calls)>=3  # Native hook still observes the later getter.


def test_missing_native_getter_is_unavailable_not_a_false_default():
    cursor=Mock();cursor.execute.return_value.fetchone.return_value=None
    source=SimpleNamespace(cursor=lambda:cursor,in_transaction=False)
    with pytest.raises(RelationalClientError) as error:
        action(source,{'operation':'set_connection_pragma','pragma':'foreign_keys','value':True,'expected_value':False,'confirmed':True})
    assert error.value.native_outcome=='not_dispatched'
    cursor.execute.assert_called_once_with('PRAGMA foreign_keys')
    cursor.close.assert_called_once()


def test_failed_native_readback_never_retries_or_reports_applied():
    cursor=Mock();cursor.execute.return_value.fetchone.side_effect=[(0,),(0,)]
    source=SimpleNamespace(cursor=lambda:cursor,in_transaction=False)
    with pytest.raises(RelationalClientError) as error:
        action(source,{'operation':'set_connection_pragma','pragma':'foreign_keys','value':True,'expected_value':False,'confirmed':True})
    assert error.value.native_outcome=='unknown_outcome'
    assert [call.args[0]for call in cursor.execute.call_args_list]==['PRAGMA foreign_keys','PRAGMA foreign_keys=ON','PRAGMA foreign_keys']
    cursor.close.assert_called_once()


def test_busy_closed_and_permission_refusal_do_not_mutate(native):
    before=run(native,'inspect',pragma='foreign_keys')['effective_value']
    native[1]._busy.add(id(native[2]))
    with pytest.raises(RelationalClientError,match='active'):
        run(native,'set_connection_pragma',pragma='foreign_keys',value=not before,expected_value=before,confirmed=True)
    native[1]._busy.remove(id(native[2]))
    assert run(native,'inspect',pragma='foreign_keys')['effective_value']==before
    def permission(name):
        if name=='administer':raise RelationalClientError('permission denied')
    native[3]._require=permission
    with pytest.raises(RelationalClientError,match='permission'):
        run(native,'review',pragma='foreign_keys',value=not before)
    assert run(native,'inspect',pragma='foreign_keys')['effective_value']==before
    native[1].close()
    with pytest.raises(RelationalClientError,match='unavailable'):
        run(native,'inspect',pragma='foreign_keys')


def test_studio_workspace_private_session_binding_and_native_revision(native):
    import threading
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
    calls=[]
    def dispatch(request):
        calls.append(request)
        return SQLiteProvider.native_connection_pragmas_action(native[3],request)
    session=SimpleNamespace(language_profile='sqlite-sql',provider_session={'session_id':'private'},
        provider_isolation_key='owned',native_work_revision=0)
    context=SimpleNamespace(provider_id='org.cdeadmin.sqlite',isolation_key='owned')
    studio=SimpleNamespace(scripts=SimpleNamespace(lock=threading.RLock(),check_execution=Mock()),
        _sessions={'public':session},_operational_session=lambda *_:(session,SimpleNamespace(
            instance=SimpleNamespace(native_connection_pragmas_action=dispatch))))
    bridge=SimpleNamespace(endpoint_service=SimpleNamespace(workspace=lambda *_,**kw:(context,{},None)),
        studio_service=SimpleNamespace(sqlite_connection_pragmas_action=lambda c,s,r,**kw:
            DataStudioService.sqlite_connection_pragmas_action(studio,c,s,r,**kw)))
    def routed(request):
        return ProviderWorkspaceService.language_tool_action(bridge,None,'sqlite_connection_pragmas',
            {'session_id':'public','database_target_id':'registered','request':request})
    before=routed({'operation':'inspect','pragma':'foreign_keys','session_id':'forged','language_profile':'forged','_host_authorized':True,'_host_principal':'forged'})['effective_value']
    assert calls[-1]['session_id']=='private' and calls[-1]['language_profile']=='sqlite-sql'
    assert calls[-1]['_host_authorized']is False and calls[-1]['_host_principal']is None
    assert session.native_work_revision==0
    routed({'operation':'review','pragma':'foreign_keys','value':not before})
    assert session.native_work_revision==0
    routed({'operation':'set_connection_pragma','pragma':'foreign_keys','value':not before,'expected_value':before,'confirmed':True})
    assert session.native_work_revision==1
    assert run(native,'inspect',pragma='foreign_keys')['effective_value'] is not before


@pytest.mark.parametrize('name',list(FLAGS))
def test_disposable_database_alter_refuses_original_connection_flags(native,name):
    before=run(native,'inspect',pragma=name)['effective_value']
    with pytest.raises(RelationalClientError,match='connection-local'):
        native[1].plan_admin_operation({'resource_kind':'database','operation_id':'alter',
            '_provider_route':{'database':str(native[0]),'filesystem_root':str(native[0].parent)},
            'target_resource':{'display_name':'main','display_path':['main']},
            'draft':{name:not before}})
    assert run(native,'inspect',pragma=name)['effective_value']==before


@pytest.mark.parametrize('name',list(FLAGS))
def test_mixed_file_and_connection_policy_refuses_before_any_file_change(native,name):
    source=native[2]
    before=source.execute('PRAGMA journal_mode').fetchone()[0]
    with pytest.raises(RelationalClientError,match='connection-local'):
        native[1].plan_admin_operation({'resource_kind':'database','operation_id':'alter',
            '_provider_route':{'database':str(native[0]),'filesystem_root':str(native[0].parent)},
            'target_resource':{'display_name':'main','display_path':['main']},
            'draft':{'journal_mode':'WAL',name:True}})
    assert source.execute('PRAGMA journal_mode').fetchone()[0]==before
