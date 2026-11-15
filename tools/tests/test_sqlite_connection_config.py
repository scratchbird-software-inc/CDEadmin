"""Typed db_config contracts on real original SQLite handles."""
from contextlib import closing
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_sqlite_connection_pragmas import native  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.connection_config import CONFIGS, DANGEROUS, action
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft


def run(native, operation, **values):
    return SQLiteProvider.native_connection_config_action(native[3], {'operation':operation, **values})


def apply(native,name,value):
    review=run(native,'review',config=name,value=value)
    values={'value':value,'expected_value':review['expected_value'],'confirmed':True}
    if name in DANGEROUS:values['dangerous_change_confirmed']=True
    draft=operation_draft(engine_operations('sqlite')['set_connection_config_'+name+'@database'],values)
    return run(native,'set_connection_config',config=name,**draft)


@pytest.mark.parametrize('name',CONFIGS)
def test_native_config_descriptor_roundtrip_peer_and_transaction_isolation(native,name):
    source=native[2];code=getattr(sqlite3,CONFIGS[name])
    before=run(native,'inspect',config=name)['effective_value']
    source.executescript('CREATE TABLE pending(value); SAVEPOINT caller; INSERT INTO pending VALUES(7)')
    with closing(sqlite3.connect(native[0])) as peer:
        peer_before=peer.getconfig(code)
        result=apply(native,name,not before)
        assert result['effective_value'] is source.getconfig(code) is not before
        assert peer.getconfig(code) is peer_before
        assert result['transaction_open']
        assert not any(result[k] for k in ['commit_requested','rollback_requested','file_persisted','future_connection_defaults_changed','automatic_retry'])
        with pytest.raises(RelationalClientError,match='changed'):
            run(native,'set_connection_config',config=name,value=before,expected_value=before,confirmed=True,dangerous_change_confirmed=True)
        # Restore reset_database before any VACUUM (the test never runs one).
        apply(native,name,before)
        assert source.in_transaction
        source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
        assert source.execute('SELECT * FROM pending').fetchall()==[]
    native[3]._require.assert_any_call('administer')


@pytest.mark.parametrize('name',DANGEROUS)
def test_dangerous_policies_require_separate_acknowledgement(native,name):
    apply(native,name,False)
    with pytest.raises(RelationalClientError,match='Confirm'):
        run(native,'set_connection_config',config=name,value=True,expected_value=False,confirmed=True)
    assert run(native,'inspect',config=name)['effective_value'] is False


@pytest.mark.parametrize('bad',[1,0,'on',None,[],{}])
def test_boolean_config_refuses_coercion(native,bad):
    with pytest.raises(RelationalClientError):run(native,'review',config='defensive',value=bad)


def test_native_config_effects_and_rollback_persistence(native):
    source=native[2]
    source.executescript('CREATE TABLE target(value); CREATE TABLE log(value); CREATE TRIGGER seen AFTER INSERT ON target BEGIN INSERT INTO log VALUES(new.value); END; CREATE VIEW shown AS SELECT * FROM target;')
    apply(native,'enable_trigger',False)
    source.execute('INSERT INTO target VALUES(7)')
    assert source.execute('SELECT * FROM log').fetchall()==[]
    source.rollback()
    assert run(native,'inspect',config='enable_trigger')['effective_value'] is False
    apply(native,'enable_trigger',True)
    source.execute('INSERT INTO target VALUES(8)')
    assert source.execute('SELECT * FROM log').fetchall()==[(8,)]
    source.rollback()
    apply(native,'enable_view',False)
    with pytest.raises(sqlite3.OperationalError):source.execute('SELECT * FROM shown').fetchall()
    apply(native,'enable_view',True)
    assert source.execute('SELECT * FROM shown').fetchall()==[]
    apply(native,'dqs_dml',False)
    with pytest.raises(sqlite3.OperationalError):source.execute('SELECT "not_an_identifier"').fetchall()
    apply(native,'dqs_dml',True)
    assert source.execute('SELECT "not_an_identifier"').fetchone()==('not_an_identifier',)


def test_config_build_gate_and_unknown_postcondition():
    with pytest.raises(RelationalClientError,match='unavailable'):
        action(SimpleNamespace(),SimpleNamespace(),{'operation':'inspect','config':'defensive'})
    connection=SimpleNamespace(getconfig=Mock(side_effect=[False,False]),setconfig=Mock(),in_transaction=False)
    with pytest.raises(RelationalClientError) as error:
        action(connection,sqlite3,{'operation':'set_connection_config','config':'defensive','value':True,'expected_value':False,'confirmed':True})
    assert error.value.native_outcome=='unknown_outcome'
    connection.setconfig.assert_called_once()


def test_native_config_preserves_authorizer_progress_and_trace_ownership(native):
    source=native[2];events=[];progress=[];trace=[]
    def authorizer(*args):
        events.append(args[0]);return sqlite3.SQLITE_OK
    def tick():progress.append(1);return 0
    source.set_authorizer(authorizer);source.set_progress_handler(tick,1);source.set_trace_callback(trace.append)
    for name in CONFIGS:
        before=run(native,'inspect',config=name)['effective_value'];apply(native,name,not before);apply(native,name,before)
    assert source._cdeadmin_authorizer is authorizer
    assert source._cdeadmin_progress_handler==(tick,1)
    assert source._cdeadmin_trace_callback==trace.append
    assert source.execute('SELECT 7').fetchone()==(7,)
    assert events and progress and trace


def test_native_reset_database_arms_vacuum_only_after_explicit_owned_dispatch(native):
    source=native[2];source.executescript('CREATE TABLE erased(value);INSERT INTO erased VALUES(7);')
    original=native[0].read_bytes()
    apply(native,'reset_database',True)
    assert native[0].read_bytes()==original
    # Explicit test-owned native dispatch, never performed by the policy setter.
    source.execute('VACUUM')
    apply(native,'reset_database',False)
    assert source.execute("SELECT name FROM sqlite_schema WHERE name='erased'").fetchall()==[]


def test_native_config_permission_busy_and_closed_guards(native):
    native[1]._busy.add(id(native[2]))
    with pytest.raises(RelationalClientError,match='active'):run(native,'review',config='defensive',value=True)
    native[1]._busy.remove(id(native[2]))
    def permission(name):
        if name=='administer':raise RelationalClientError('permission denied')
    native[3]._require=permission
    with pytest.raises(RelationalClientError,match='permission'):run(native,'review',config='defensive',value=True)
    native[1].close()
    with pytest.raises(RelationalClientError,match='unavailable'):run(native,'inspect',config='defensive')


def test_config_private_binding_and_native_revision(native):
    import threading
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
    calls=[]
    def dispatch(request):
        calls.append(request);return SQLiteProvider.native_connection_config_action(native[3],request)
    session=SimpleNamespace(language_profile='sqlite-sql',provider_session={'session_id':'private'},provider_isolation_key='owned',native_work_revision=0)
    context=SimpleNamespace(provider_id='org.cdeadmin.sqlite',isolation_key='owned')
    studio=SimpleNamespace(scripts=SimpleNamespace(lock=__import__('threading').RLock(),check_execution=Mock()),_sessions={'public':session},_operational_session=lambda *_:(session,SimpleNamespace(instance=SimpleNamespace(native_connection_config_action=dispatch))))
    bridge=SimpleNamespace(endpoint_service=SimpleNamespace(workspace=lambda *_,**kw:(context,{},None)),studio_service=SimpleNamespace(sqlite_connection_config_action=lambda c,s,r:DataStudioService.sqlite_connection_config_action(studio,c,s,r)))
    def routed(request):
        return ProviderWorkspaceService.language_tool_action(bridge,None,'sqlite_connection_config',{'session_id':'public','database_target_id':'registered','request':request})
    before=routed({'operation':'inspect','config':'defensive','session_id':'forged','language_profile':'forged'})['effective_value']
    assert calls[-1]['session_id']=='private' and session.native_work_revision==0
    routed({'operation':'review','config':'defensive','value':not before})
    assert session.native_work_revision==0
    routed({'operation':'set_connection_config','config':'defensive','value':not before,'expected_value':before,'confirmed':True})
    assert session.native_work_revision==1 and run(native,'inspect',config='defensive')['effective_value'] is not before
