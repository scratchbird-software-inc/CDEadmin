"""Original-session FLAGSET native effects and refusal contracts."""
import os,json
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.mariadb_flagsets import action
from pgadmin.cdeadmin.providers.mysql_family.mariadb_variables import flagset_bitmask,validate_flagset
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations,operation_draft

SETTINGS=json.loads(os.environ.get('CDEADMIN_MARIADB_FLAGS_TEST') or 'null')


@pytest.mark.parametrize('size',[65,128])
def test_oversized_native_metadata_never_becomes_an_unbounded_numeric_mask(size):
    options=','.join(['flag_'+str(i) for i in range(size-1)]+['default'])
    with pytest.raises(ValueError):flagset_bitmask('0',options)
    # The textual native grammar is not truncated at a fabricated bit position.
    validate_flagset('flag_'+str(size-2)+'=on',options)


def test_session_flagset_requires_explicit_diagnostics_ack_before_any_cursor():
    handle=Mock()
    with pytest.raises(RelationalClientError,match='diagnostics'):
        action(handle,{'operation':'inspect','variable':'optimizer_switch'})
    handle.cursor.assert_not_called()


@pytest.mark.parametrize('bad',['sql_mode','OPTIMIZER_SWITCH',123,{},None])
def test_session_flagset_never_accepts_an_arbitrary_variable(bad):
    with pytest.raises(RelationalClientError):
        action(Mock(),{'operation':'inspect','variable':bad,'diagnostics_change_confirmed':True})


@pytest.fixture
def native():
    if SETTINGS is None:pytest.skip('CDEADMIN_MARIADB_FLAGS_TEST is not set')
    import mariadb
    connection=mariadb.connect(**SETTINGS)
    try:yield connection
    finally:connection.close()


def run(handle,operation,variable='optimizer_trace',**values):
    return action(handle,{'operation':operation,'variable':variable,'diagnostics_change_confirmed':True,**values})


def apply(handle,variable,values):
    review=run(handle,'review',variable,**values)
    op=engine_operations('mariadb')['set_session_'+variable+'_flags@system-variable']
    draft=operation_draft(op,{**values,'expected_value':review['expected_value'],'confirmed':True,'diagnostics_change_confirmed':True})
    result=run(handle,'set_session_flags',variable,**draft)
    assert result['outcome']=='native_acknowledged_with_readback'
    assert not any(result[key]for key in ['commit_requested','rollback_requested','future_connection_defaults_changed','global_value_changed','automatic_retry','native_diagnostics_preserved'])
    return result


@pytest.mark.parametrize('variable',['optimizer_switch','optimizer_trace'])
def test_native_session_flags_preserve_pending_rows_peer_global_and_rollback_semantics(native,variable):
    import mariadb
    native.autocommit=True
    cur=native.cursor();cur.execute('CREATE TABLE IF NOT EXISTS pending(value INTEGER) ENGINE=InnoDB')
    cur.execute('DELETE FROM pending');cur.execute('START TRANSACTION');cur.execute('INSERT INTO pending VALUES(7)')
    with closing(mariadb.connect(**SETTINGS)) as peer:
        peer_cur=peer.cursor();peer_cur.execute('SELECT @@GLOBAL.'+variable+',@@SESSION.'+variable);global_before,peer_before=peer_cur.fetchone()
        flag='mrr' if variable=='optimizer_switch' else 'enabled'
        for state in ['on','off','default']:
            result=apply(native,variable,{'value_mode':'FLAGS','flags':[{'flag':flag,'state':state}],'reset_defaults':False})
            observed=dict(part.split('=')for part in result['effective_value'].split(','))
            if state!='default':assert observed[flag]==state
            cur.execute('SELECT * FROM pending');assert cur.fetchall()==[(7,)]
            peer_cur.execute('SELECT @@GLOBAL.'+variable+',@@SESSION.'+variable);assert peer_cur.fetchone()==(global_before,peer_before)
        for values in [{'value_mode':'VALUE','value':flag+'=on'},{'value_mode':'DEFAULT'},{'value_mode':'FLAGS','flags':[],'reset_defaults':True}]:
            apply(native,variable,values)
        result=apply(native,variable,{'value_mode':'VALUE','value':flag+'=off'})
        native.rollback()
        assert run(native,'inspect',variable)['effective_value']==result['effective_value']
        cur.execute('SELECT * FROM pending');assert cur.fetchall()==[]
        peer_cur.close()
    cur.close()


@pytest.mark.parametrize('mask',['0','1','2','3'])
def test_native_session_exact_numeric_masks_and_stale_refusal(native,mask):
    result=apply(native,'optimizer_trace',{'value_mode':'BITMASK','bitmask':mask})
    assert result['effective_value']=='enabled='+('on' if int(mask)&1 else 'off')
    with pytest.raises(RelationalClientError,match='changed'):
        run(native,'set_session_flags',value_mode='DEFAULT',expected_value='not the native value',confirmed=True)
    assert run(native,'inspect')['effective_value']==result['effective_value']


def test_unknown_native_outcome_keeps_private_binding_and_never_returns_success():
    import threading
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    calls=[]
    def dispatch(request):
        calls.append(request)
        failure=RelationalClientError('unconfirmed native setting');failure.native_outcome='unknown_outcome';raise failure
    session=SimpleNamespace(language_profile='mariadb-sql',provider_session={'session_id':'private'},provider_isolation_key='owned',native_work_revision=0)
    context=SimpleNamespace(provider_id='org.cdeadmin.mariadb',isolation_key='owned')
    service=SimpleNamespace(scripts=SimpleNamespace(lock=threading.RLock(),check_execution=Mock()),
        _sessions={'public':session},_operational_session=lambda *_:(session,SimpleNamespace(instance=SimpleNamespace(native_session_flagsets_action=dispatch))))
    result=DataStudioService.mariadb_session_flagsets_action(service,context,'public',{'operation':'set_session_flags','session_id':'forged','language_profile':'forged'})
    assert calls[0]['session_id']=='private' and calls[0]['language_profile']=='mariadb-sql'
    assert result['outcome']=='unknown_outcome' and not result['accepted'] and not result['automatic_retry']
    assert result['close_session_required'] and not result['effective_value_observed']


def test_native_provider_original_handle_lifecycle_permissions_and_uncertain_refusal(native):
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client,MARIADB_PROFILE,MariaDBPilotProvider
    route,permissions=provider_access({**SETTINGS,'ssl':False,'ssl_verify_cert':False})
    client=_create_client(MARIADB_PROFILE,permissions,SimpleNamespace(pool_namespace='owned-session-flags'))
    handle=client.open_session({'route':route})
    provider=SimpleNamespace(client=client,_require=Mock(),_editor_session=lambda request:handle)
    def routed(operation,**values):
        return MariaDBPilotProvider.native_session_flagsets_action(provider,
            {'operation':operation,'variable':'optimizer_switch','diagnostics_change_confirmed':True,
             'session_id':'owned','language_profile':'mariadb-sql',**values})
    try:
        before=routed('inspect')['effective_value']
        result=routed('set_session_flags',value_mode='FLAGS',flags=[{'flag':'mrr','state':'on'}],reset_defaults=False,expected_value=before,confirmed=True)
        assert 'mrr=on' in result['effective_value']
        provider._require.assert_any_call('execute');provider._require.assert_any_call('administer')
        before=routed('inspect')['effective_value']
        with pytest.raises(RelationalClientError) as failure:
            routed('set_session_flags',value_mode='BITMASK',bitmask='0',expected_value=before,confirmed=True)
        assert failure.value.native_outcome=='unknown_outcome'
        assert id(handle) in client._uncertain_sessions
        with pytest.raises(RelationalClientError):routed('inspect')
    finally:client.close()


def test_native_restricted_account_can_set_session_but_cannot_set_global(native):
    import mariadb,uuid
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client,MARIADB_PROFILE,MARIADB_ADMINISTRATION
    name='sr_flags_'+uuid.uuid4().hex[:16]
    cur=native.cursor();cur.execute("CREATE USER '"+name+"'@'%' IDENTIFIED BY 'owned-flags-test'")
    cur.execute('GRANT SELECT ON `'+SETTINGS['database']+"`.* TO '"+name+"'@'%'")
    credentials={**SETTINGS,'user':name,'password':'owned-flags-test'}
    try:
        cur.execute('SELECT @@GLOBAL.optimizer_trace');global_before=cur.fetchone()[0]
        with closing(mariadb.connect(**credentials)) as restricted:
            result=apply(restricted,'optimizer_trace',{'value_mode':'FLAGS','flags':[{'flag':'enabled','state':'on'}]})
            assert 'enabled=on' in result['effective_value']
        route,permissions=provider_access({**credentials,'ssl':False,'ssl_verify_cert':False})
        client=_create_client(MARIADB_PROFILE,permissions,SimpleNamespace(pool_namespace=name))
        cur.execute("SELECT VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,ENUM_VALUE_LIST FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME='OPTIMIZER_TRACE'")
        scope,kind,readonly,options=cur.fetchone()
        request={'resource_kind':'system-variable','operation_id':'set_global','_provider_route':route,
            'target_resource':{'resource_kind':'system-variable','display_name':'optimizer_trace','display_path':['Configuration','optimizer_trace'],
                'native':{'read_only':readonly,'variable_scope':scope,'variable_type':kind,'enum_value_list':options}},
            'draft':{'value_mode':'FLAGS','flags':[{'flag':'enabled','state':'on'}],'reset_defaults':False}}
        try:
            planned=MARIADB_ADMINISTRATION.plan(request)
            with pytest.raises(RelationalClientError):MARIADB_ADMINISTRATION.apply(client,planned)
        finally:client.close()
        cur.execute('SELECT @@GLOBAL.optimizer_trace');assert cur.fetchone()[0]==global_before
    finally:
        cur.execute("DROP USER '"+name+"'@'%'");cur.close()
