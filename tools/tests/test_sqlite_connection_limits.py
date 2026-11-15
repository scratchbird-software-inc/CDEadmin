"""Real original-handle sqlite3_limit administration, with native enforcement."""
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client, SQLiteProvider
from pgadmin.cdeadmin.providers.sqlite.connection_limits import action, LIMITS
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft

CASES = [
    ('length',1024,'SELECT length(?)',('x'*2048,)),
    ('sql_length',80,'SELECT 1 /*'+'x'*100+'*/',()),
    ('column',2,'SELECT 1,2,3',()),
    ('expr_depth',8,'SELECT '+('1 AND ('*12)+'1'+(')'*12),()),
    ('compound_select',2,'SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3',()),
]


@pytest.fixture
def native(tmp_path):
    path=tmp_path/'limits.db'
    client=_create_client()
    source=client.open_session({'route':{'database':str(path),'filesystem_root':str(tmp_path)}})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:source)
    yield path,client,source,provider
    client.close()


def run(native,operation,**values):
    return SQLiteProvider.native_connection_limits_action(native[3],{'operation':operation,**values})


@pytest.mark.parametrize('name,value,sql,parameters',CASES)
def test_descriptor_native_enforcement_and_per_handle_isolation(native,name,value,sql,parameters):
    source=native[2];code=getattr(sqlite3,LIMITS[name]);before=source.getlimit(code)
    review=run(native,'review',limit=name,value=value)
    assert source.getlimit(code)==before and review['ready_to_apply']
    descriptor=engine_operations('sqlite')['set_connection_limit_'+name+'@database']
    draft=operation_draft(descriptor,{'value':value,'expected_value':review['expected_value'],'confirmed':True})
    # The native task contract binds the fixed limit and original-session route.
    result=run(native,'set_connection_limit',limit=name,**draft)
    assert result['effective_value']==source.getlimit(code)==value and result['outcome']=='applied'
    assert not result['file_persisted'] and not result['future_connection_defaults_changed']
    assert not result['commit_requested'] and not result['rollback_requested']
    with pytest.raises(sqlite3.Error):source.execute(sql,parameters).fetchall()
    # A separate native connection retains the default and accepts the request.
    with sqlite3.connect(native[0]) as peer:
        assert peer.getlimit(code)==before
        assert peer.execute(sql,parameters).fetchall()
    run(native,'set_connection_limit',limit=name,value=before,expected_value=value,confirmed=True)
    assert source.execute(sql,parameters).fetchall()
    native[3]._require.assert_any_call('administer')


@pytest.mark.parametrize('name',list(LIMITS))
def test_native_hard_cap_readback_and_stale_compare_refusal(native,name):
    source=native[2];code=getattr(sqlite3,LIMITS[name]);before=source.getlimit(code)
    result=run(native,'set_connection_limit',limit=name,value=2147483647,expected_value=before,confirmed=True)
    effective=source.getlimit(code)
    assert effective==result['effective_value'] and effective<=2147483647
    assert result['outcome']==('applied' if effective==2147483647 else 'native_adjusted')
    with pytest.raises(RelationalClientError,match='changed'):
        run(native,'set_connection_limit',limit=name,value=before,expected_value=effective-1,confirmed=True)
    assert source.getlimit(code)==effective
    run(native,'set_connection_limit',limit=name,value=before,expected_value=effective,confirmed=True)


@pytest.mark.parametrize('name',list(LIMITS))
def test_pending_data_savepoint_rollback_and_authorizer_are_preserved(native,name):
    source=native[2];code=getattr(sqlite3,LIMITS[name]);before=source.getlimit(code)
    source.executescript('CREATE TABLE pending(id); SAVEPOINT caller; INSERT INTO pending VALUES(7)')
    observed=[]
    def authorizer(*args):
        observed.append(args)
        return sqlite3.SQLITE_OK
    source.set_authorizer(authorizer)
    requested=before-1 if before>0 else 1
    result=run(native,'set_connection_limit',limit=name,value=requested,expected_value=before,confirmed=True)
    assert result['transaction_open'] and observed==[]
    assert source.execute('SELECT * FROM pending').fetchall()==[(7,)] and observed
    source.execute('ROLLBACK TO caller')
    assert source.execute('SELECT * FROM pending').fetchall()==[]
    assert source.getlimit(code)==result['effective_value']  # Native state is not rolled back.
    source.execute('RELEASE caller')
    assert run(native,'inspect',limit=name)['effective_value']==result['effective_value']


@pytest.mark.parametrize('values',[{'limit':'unknown'},{'value':True},{'value':-1},{'value':2147483648},
    {'value':1.5},{'expected_value':False},{'confirmed':'true'},{'extra':'not admitted'}])
def test_invalid_control_never_changes_native_limit(native,values):
    before=run(native,'inspect',limit='length')['effective_value']
    with pytest.raises(RelationalClientError):
        run(native,'set_connection_limit',**{'limit':'length','value':1024,'expected_value':before,'confirmed':True,**values})
    assert run(native,'inspect',limit='length')['effective_value']==before


def test_interpreter_capability_refusal_has_no_sql_fallback():
    handle=SimpleNamespace(execute=Mock(side_effect=AssertionError('SQL must not be used')))
    with pytest.raises(RelationalClientError,match='no native limit API'):
        action(handle,SimpleNamespace(),{'operation':'inspect','limit':'length'})
    handle.execute.assert_not_called()


def test_busy_closed_and_permission_denial_do_not_dispatch(native):
    before=run(native,'inspect',limit='length')['effective_value']
    native[1]._busy.add(id(native[2]))
    with pytest.raises(RelationalClientError,match='active'):
        run(native,'set_connection_limit',limit='length',value=1024,expected_value=before,confirmed=True)
    native[1]._busy.remove(id(native[2]))
    assert native[2].getlimit(sqlite3.SQLITE_LIMIT_LENGTH)==before
    def permission(name):
        if name=='administer':raise RelationalClientError('permission denied')
    native[3]._require=permission
    with pytest.raises(RelationalClientError,match='permission'):
        run(native,'review',limit='length',value=1024)
    assert run(native,'inspect',limit='length')['effective_value']==before
    native[1].close()
    with pytest.raises(RelationalClientError,match='unavailable'):
        run(native,'inspect',limit='length')


def test_studio_and_workspace_route_keep_private_handle_and_work_revision(native):
    import threading
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
    provider=native[3];calls=[]
    def dispatch(request):
        calls.append(request)
        return SQLiteProvider.native_connection_limits_action(provider,request)
    session=SimpleNamespace(language_profile='sqlite-sql',provider_session={'session_id':'private'},
        provider_isolation_key='owned',native_work_revision=0)
    context=SimpleNamespace(provider_id='org.cdeadmin.sqlite',isolation_key='owned')
    studio=SimpleNamespace(scripts=SimpleNamespace(lock=threading.RLock(),check_execution=Mock()),
        _sessions={'public':session},_operational_session=lambda *_:(session,SimpleNamespace(
            instance=SimpleNamespace(native_connection_limits_action=dispatch))))
    def call(context,session_id,request):
        return DataStudioService.sqlite_connection_limits_action(studio,context,session_id,request)
    bridge=SimpleNamespace(endpoint_service=SimpleNamespace(workspace=lambda *_,**kw:(context,{},None)),
        studio_service=SimpleNamespace(sqlite_connection_limits_action=call))
    def routed(request):
        return ProviderWorkspaceService.language_tool_action(bridge,None,'sqlite_connection_limits',
            {'session_id':'public','database_target_id':'registered','request':request})
    observed=routed({'operation':'inspect','limit':'length','session_id':'forged','language_profile':'forged'})
    assert calls[-1]['session_id']=='private' and calls[-1]['language_profile']=='sqlite-sql'
    assert session.native_work_revision==0
    routed({'operation':'review','limit':'length','value':1024})
    assert session.native_work_revision==0
    routed({'operation':'set_connection_limit','limit':'length','value':1024,
        'expected_value':observed['effective_value'],'confirmed':True})
    assert session.native_work_revision==1 and native[2].getlimit(sqlite3.SQLITE_LIMIT_LENGTH)==1024


def test_unknown_postcondition_never_reports_applied_or_retries():
    handle=SimpleNamespace(getlimit=Mock(side_effect=[1000,RuntimeError('lost native observation')]),
        setlimit=Mock(return_value=1000),in_transaction=False)
    with pytest.raises(RelationalClientError) as error:
        action(handle,SimpleNamespace(SQLITE_LIMIT_LENGTH=0),{'operation':'set_connection_limit',
            'limit':'length','value':512,'expected_value':1000,'confirmed':True})
    assert error.value.native_outcome=='unknown_outcome'
    handle.setlimit.assert_called_once_with(0,512)


@pytest.mark.parametrize('name',list(LIMITS))
def test_native_zero_value_is_observed_without_guessing_its_semantics(native,name):
    source=native[2];code=getattr(sqlite3,LIMITS[name]);before=source.getlimit(code)
    result=run(native,'set_connection_limit',limit=name,value=0,expected_value=before,confirmed=True)
    assert result['effective_value']==source.getlimit(code)
    assert result['outcome']==('applied' if source.getlimit(code)==0 else 'native_adjusted')
    restored=run(native,'set_connection_limit',limit=name,value=before,expected_value=result['effective_value'],confirmed=True)
    assert restored['effective_value']==before


@pytest.mark.parametrize('name,value,sql,parameters',[
    ('function_arg',2,'SELECT coalesce(NULL,NULL,7)',()),
    ('like_pattern_length',3,"SELECT 'abcde' LIKE 'abcd%'",()),
    ('variable_number',2,'SELECT ?3',(1,2,3)),
])
def test_additional_limit_native_enforcement_and_descriptor(native,name,value,sql,parameters):
    source=native[2];code=getattr(sqlite3,LIMITS[name]);before=source.getlimit(code)
    review=run(native,'review',limit=name,value=value)
    descriptor=engine_operations('sqlite')['set_connection_limit_'+name+'@database']
    draft=operation_draft(descriptor,{'value':value,'expected_value':review['expected_value'],'confirmed':True})
    receipt=run(native,'set_connection_limit',limit=name,**draft)
    assert receipt['effective_value']==source.getlimit(code)==value
    with pytest.raises(sqlite3.Error):source.execute(sql,parameters).fetchall()
    with sqlite3.connect(native[0]) as peer:
        assert peer.getlimit(code)==before and peer.execute(sql,parameters).fetchall()==[(7 if name=='function_arg' else 1 if name=='like_pattern_length' else 3,)]
    run(native,'set_connection_limit',limit=name,value=before,expected_value=value,confirmed=True)
    assert source.execute(sql,parameters).fetchall()


def test_attached_native_limit_preserves_existing_aliases_and_refuses_next_attachment(native):
    source=native[2];name='attached';code=sqlite3.SQLITE_LIMIT_ATTACHED;before=source.getlimit(code)
    source.execute('ATTACH DATABASE ? AS "first 雪"',(':memory:',))
    source.execute('CREATE TABLE "first 雪".retained(value)')
    source.execute('INSERT INTO "first 雪".retained VALUES(7)');source.commit()
    descriptor=engine_operations('sqlite')['set_connection_limit_attached@database']
    draft=operation_draft(descriptor,{'value':1,'expected_value':before,'confirmed':True})
    result=run(native,'set_connection_limit',limit=name,**draft)
    assert result['effective_value']==1
    with pytest.raises(sqlite3.OperationalError,match='attached'):
        source.execute('ATTACH DATABASE ? AS second',(':memory:',))
    assert source.execute('SELECT * FROM "first 雪".retained').fetchall()==[(7,)]
    assert [r[1]for r in source.execute('PRAGMA database_list')]==['main','first 雪']
    result=run(native,'set_connection_limit',limit=name,value=0,expected_value=1,confirmed=True)
    assert result['effective_value']==0 and source.execute('SELECT * FROM "first 雪".retained').fetchall()==[(7,)]
    with sqlite3.connect(native[0]) as peer:
        peer.execute("ATTACH ':memory:' AS one");peer.execute("ATTACH ':memory:' AS two")
        assert peer.getlimit(code)==before
    run(native,'set_connection_limit',limit=name,value=before,expected_value=0,confirmed=True)
    source.execute('ATTACH DATABASE ? AS second',(':memory:',))
    assert [r[1]for r in source.execute('PRAGMA database_list')]==['main','first 雪','second']


def test_trigger_depth_native_failure_preserves_caller_savepoint_and_prior_write(native):
    source=native[2];name='trigger_depth';code=sqlite3.SQLITE_LIMIT_TRIGGER_DEPTH;before=source.getlimit(code)
    source.executescript('CREATE TABLE pending(value); CREATE TABLE origin(value); CREATE TABLE sink(value); '
        'CREATE TRIGGER outer_trigger AFTER INSERT ON origin BEGIN INSERT INTO sink VALUES(NEW.value); END; '
        'CREATE TRIGGER inner_trigger AFTER INSERT ON sink BEGIN SELECT 1; END; '
        'SAVEPOINT caller; INSERT INTO pending VALUES(7);')
    descriptor=engine_operations('sqlite')['set_connection_limit_trigger_depth@database']
    draft=operation_draft(descriptor,{'value':1,'expected_value':before,'confirmed':True})
    result=run(native,'set_connection_limit',limit=name,**draft)
    assert result['effective_value']==1 and result['transaction_open']
    source.execute('SAVEPOINT attempted_insert')
    with pytest.raises(sqlite3.OperationalError,match='recursion'):
        source.execute('INSERT INTO origin VALUES(1)')
    assert source.in_transaction and source.execute('SELECT * FROM pending').fetchall()==[(7,)]
    # Native recursion errors leave these preceding trigger writes pending.
    # Do not fabricate an automatic statement rollback or finalize the caller.
    assert source.execute('SELECT * FROM origin').fetchall()==[(1,)]
    assert source.execute('SELECT * FROM sink').fetchall()==[(1,)]
    source.execute('ROLLBACK TO attempted_insert');source.execute('RELEASE attempted_insert')
    assert source.execute('SELECT * FROM origin').fetchall()==[]
    assert source.execute('SELECT * FROM sink').fetchall()==[]
    assert source.execute('SELECT * FROM pending').fetchall()==[(7,)]
    with sqlite3.connect(native[0]) as peer:
        assert peer.getlimit(code)==before
        peer.execute('SELECT * FROM origin')
    run(native,'set_connection_limit',limit=name,value=before,expected_value=1,confirmed=True)
    source.execute('INSERT INTO origin VALUES(3)')
    assert source.execute('SELECT * FROM sink').fetchall()==[(3,)]
    source.execute('ROLLBACK TO caller');source.execute('RELEASE caller')
    assert source.execute('SELECT * FROM pending').fetchall()==[]
    with sqlite3.connect(native[0]) as peer:
        peer.execute('INSERT INTO origin VALUES(2)')
        assert peer.execute('SELECT * FROM sink').fetchall()==[(2,)]


def test_variable_number_counts_native_slots_not_repeated_occurrences(native):
    source=native[2];before=source.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
    run(native,'set_connection_limit',limit='variable_number',value=2,expected_value=before,confirmed=True)
    assert source.execute('SELECT ?2,?2,?1',(7,9)).fetchone()==(9,9,7)
    with pytest.raises(sqlite3.OperationalError):
        source.execute('SELECT :a,:b,:c',{'a':1,'b':2,'c':3})


def test_like_pattern_length_also_enforces_glob_utf8_bytes(native):
    source=native[2];before=source.getlimit(sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH)
    run(native,'set_connection_limit',limit='like_pattern_length',value=3,expected_value=before,confirmed=True)
    assert source.execute("SELECT 'abc' GLOB 'a*'").fetchone()==(1,)
    with pytest.raises(sqlite3.OperationalError):
        source.execute('SELECT ? GLOB ?',('雪','雪*'))  # Four UTF-8 bytes, two characters.


def test_function_arg_limit_applies_to_vararg_printf_as_well_as_coalesce(native):
    source=native[2];before=source.getlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG)
    run(native,'set_connection_limit',limit='function_arg',value=2,expected_value=before,confirmed=True)
    assert source.execute("SELECT printf('%s','kept')").fetchone()==('kept',)
    with pytest.raises(sqlite3.OperationalError):
        source.execute("SELECT printf('%s%s','too','many')")
