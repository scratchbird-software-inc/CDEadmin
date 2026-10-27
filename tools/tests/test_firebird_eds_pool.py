"""Process controls must preserve native acknowledgement and caller ownership."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import threading

import pytest

from pgadmin.cdeadmin.providers.firebird import eds_pool
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.workspace.firebird_eds_pool_receipts import EDSPoolReceipts
from tools.tests.test_firebird_query_limits import client_fixture


ROW=(42,'SYSDBA   ','NONE   ','/owned/native.fdb',123,'32','7200','0','0')


@pytest.fixture
def owned(tmp_path):
    client,handle,cursor=client_fixture()
    cursor.description=None
    handle.main_transaction.is_active.return_value=True
    archive=EDSPoolReceipts(tmp_path/'receipts.json',1,'endpoint','registered-database')
    with patch.object(eds_pool,'observe',return_value=eds_pool.metadata(ROW)):
        yield SimpleNamespace(client=client,handle=handle,cursor=cursor,archive=archive)


def call(owned,operation,**fields):
    return eds_pool.action(owned.client,owned.handle,'original',{'operation':operation,**fields},owned.archive)


def review(owned):return call(owned,'review',draft={'action':'set_size','value':31})


def apply(owned,record,**changes):
    return call(owned,'apply',review_id=record['review_id'],review_digest=record['review_digest'],
        confirmed=True,confirmation=record['native_before']['server_process_id'],**changes)


@pytest.mark.parametrize('draft',[
    None,[],{}, {'action':[]},{'action':'clear_database','value':'owned'},
    {'action':'set_size','value':True},{'action':'set_size','value':-1},{'action':'set_size','value':1001},
    {'action':'set_size','value':'32'},{'action':'set_size','value':32,'source':'DROP DATABASE'},
    {'action':'set_lifetime','value':0,'unit':'SECOND'}, {'action':'set_lifetime','value':65536,'unit':'SECOND'},
    {'action':'set_lifetime','value':25,'unit':'HOUR'},{'action':'set_lifetime','value':1441,'unit':'MINUTE'},
    {'action':'set_lifetime','value':1,'unit':[]},{'action':'set_lifetime','value':1,'unit':'SECOND; DROP DATABASE'},
    {'action':'clear_oldest','value':1}])
def test_only_implemented_native_options_can_produce_sql(draft):
    with pytest.raises(ValueError):eds_pool.compile_operation(draft)


@pytest.mark.parametrize('draft,source,expected',[
    ({'action':'set_size','value':0},'SET SIZE 0',{'size':'0'}),
    ({'action':'set_size','value':1000},'SET SIZE 1000',{'size':'1000'}),
    ({'action':'set_lifetime','value':65535,'unit':'SECOND'},'SET LIFETIME 65535 SECOND',{'lifetime_seconds':'65535'}),
    ({'action':'set_lifetime','value':24,'unit':'HOUR'},'SET LIFETIME 24 HOUR',{'lifetime_seconds':'86400'}),
    ({'action':'set_lifetime','value':1440,'unit':'MINUTE'},'SET LIFETIME 1440 MINUTE',{'lifetime_seconds':'86400'}),
    ({'action':'clear_all'},'CLEAR ALL',{}),({'action':'clear_oldest'},'CLEAR OLDEST',{})])
def test_native_bounds_and_units_are_preserved(draft,source,expected):
    assert eds_pool.compile_operation(draft)==('ALTER EXTERNAL CONNECTIONS POOL '+source,expected)


def test_native_facts_are_exact_and_not_file_configuration():
    value=eds_pool.metadata(ROW)
    assert value['effective_principal']=='SYSDBA' and value['attachment_id']=='42'
    assert value['server_process_id']=='123' and value['size']=='32'
    assert value['scope']=='attachment-engine-process'
    assert not value['transactional'] and not value['configuration_file_updated']
    assert not value['clear_database_implemented']
    with pytest.raises(RelationalClientError):eds_pool.metadata(ROW[:-1])
    with pytest.raises(RelationalClientError):eds_pool.metadata((*ROW[:5],None,*ROW[6:]))


@pytest.mark.parametrize('available',[False,True])
def test_catalog_preserves_available_process_facts_or_explicit_unavailability(available):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources
    cursor=Mock();current=[]
    def execute(source,*_):
        nonlocal current
        current=[ROW] if source==eds_pool.SQL and available else []
    cursor.execute.side_effect=execute;cursor.fetchall.side_effect=lambda:current
    resources=_resources(SimpleNamespace(cursor=lambda:cursor,info=SimpleNamespace()),{})
    for kind in ('database','server'):
        row=next(value for value in resources if value['resource_kind']==kind)
        facts=row['native']['external_connection_pool']
        assert facts['available'] is available
        if available:assert facts['server_process_id']=='123' and facts['size']=='32'
        else:assert 'size' not in facts and 'idle_count' not in facts


def test_observation_releases_only_owned_read_transaction(owned):
    manager=owned.handle.transaction_manager.return_value
    manager.cursor.return_value.fetchone.return_value=ROW
    # Use the real function outside the fixture's observation replacement.
    assert OBSERVE(owned.client,owned.handle)['size']=='32'
    manager.rollback.assert_called_once_with();manager.close.assert_called_once_with()
    owned.handle.main_transaction.rollback.assert_not_called()
    owned.handle.commit.assert_not_called();owned.handle.rollback.assert_not_called()


OBSERVE=eds_pool.observe


def test_observation_cleanup_failure_blocks_attachment(owned):
    manager=owned.handle.transaction_manager.return_value
    manager.cursor.return_value.fetchone.return_value=ROW
    manager.close.side_effect=RuntimeError('PRIVATE connection cleanup')
    with pytest.raises(RelationalClientError,match='close this session'):
        OBSERVE(owned.client,owned.handle)
    assert owned.client._state(owned.handle).result_cleanup_failed


def test_durable_claim_precedes_dispatch_and_repeated_apply_never_replays(owned):
    record=review(owned);entered=threading.Event();release=threading.Event()
    original=owned.cursor.execute.side_effect
    def execute(*args):
        saved=owned.archive.get(record['review_id'])
        assert saved['native_dispatch_admitted'] and saved['state']=='unknown_outcome'
        entered.set();assert release.wait(3)
        if original:return original(*args)
    owned.cursor.execute.side_effect=execute
    try:
        assert apply(owned,record)['native_operation_running']
        assert entered.wait(3)
        # Receipt access remains possible while native dispatch owns the handle.
        assert call(owned,'receipt',review_id=record['review_id'])['native_operation_running']
    finally:release.set()
    task=owned.client._eds_pool_reviews[record['review_id']]['token'];task.worker.join(3)
    observed=call(owned,'receipt',review_id=record['review_id'])
    assert observed['native_acknowledged'] and observed['state']=='acknowledged'
    assert observed['caller_transaction_active_after']
    assert observed['requested_settings_observed'] is False  # Concurrent native observation, not invented success.
    apply(owned,record)
    owned.cursor.execute.assert_called_once_with(record['source'])
    owned.handle.commit.assert_not_called();owned.handle.rollback.assert_not_called()
    restored=EDSPoolReceipts(owned.archive.path,*owned.archive.binding)
    owned.client._forget_connection(owned.handle)
    assert restored.get(record['review_id'])['native_acknowledged']
    assert not restored.get(record['review_id'])['transaction_finality_inferred']


def test_stale_native_settings_and_process_refuse_before_claim(owned):
    record=review(owned)
    for key in ('server_process_id','attachment_id','size','effective_principal','role','database'):
        changed={**record['native_before'],key:'different'}
        with patch.object(eds_pool,'observe',return_value=changed),pytest.raises(ValueError,match='changed'):
            apply(owned,record)
    assert owned.archive.get(record['review_id'])['state']=='reviewed'
    owned.cursor.execute.assert_not_called()


def test_confirmation_session_adapter_and_owner_are_bound(owned):
    record=review(owned)
    base={'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
        'confirmed':True,'confirmation':'123'}
    for changes in ({'confirmed':False},{'confirmation':123},{'review_digest':'changed'}):
        with pytest.raises(ValueError):eds_pool.action(owned.client,owned.handle,'original',{**base,**changes},owned.archive)
    with pytest.raises(ValueError):eds_pool.action(owned.client,owned.handle,'another',base,owned.archive)
    with patch.object(eds_pool,'identity',return_value={}),pytest.raises(ValueError):apply(owned,record)
    for owner,endpoint,target in ((2,'endpoint','registered-database'),(1,'other','registered-database'),(1,'endpoint','other')):
        with pytest.raises(ValueError):EDSPoolReceipts(owned.archive.path,owner,endpoint,target).get(record['review_id'])
    owned.cursor.execute.assert_not_called()


def test_lost_claim_receipt_and_storage_failure_never_authorize_replay(owned):
    record=review(owned)
    with patch.object(owned.archive,'claim',side_effect=OSError('Owned disk unavailable')),pytest.raises(OSError):apply(owned,record)
    owned.cursor.execute.assert_not_called()
    assert owned.archive.claim(record['review_id'],record['review_digest'])
    assert apply(owned,record)['state']=='unknown_outcome'
    owned.cursor.execute.assert_not_called()


@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_native_acknowledgement_is_retained_even_when_cursor_cleanup_fails(owned,cleanup_fails):
    record=review(owned)
    if cleanup_fails:owned.cursor.close.side_effect=RuntimeError('PRIVATE cleanup')
    apply(owned,record);task=owned.client._eds_pool_reviews[record['review_id']]['token'];task.worker.join(3)
    receipt=call(owned,'receipt',review_id=record['review_id'])
    assert receipt['native_acknowledged'] and receipt['session_reuse_blocked'] is cleanup_fails
    assert receipt['last_native_phase']=='session_release'


def test_native_privilege_error_does_not_claim_zero_effect_or_retry(owned):
    error=RuntimeError('PRIVATE native privilege');error.gds_codes=(335544352,)
    owned.cursor.execute.side_effect=error
    record=review(owned);apply(owned,record)
    owned.client._eds_pool_reviews[record['review_id']]['token'].worker.join(3)
    receipt=call(owned,'receipt',review_id=record['review_id'])
    assert receipt['state']=='unknown_outcome' and not receipt['native_acknowledged']
    assert receipt['native_status_codes']==[335544352] and not receipt['automatic_retry']
    apply(owned,record);assert owned.cursor.execute.call_count==1


def test_observer_failures_never_strand_worker_or_erase_durable_unknown(owned):
    record=review(owned)
    with patch.object(owned.archive,'update',side_effect=OSError('Receipt write unavailable')):
        apply(owned,record);task=owned.client._eds_pool_reviews[record['review_id']]['token'];task.worker.join(3)
    receipt=call(owned,'receipt',review_id=record['review_id'])
    assert task.done and not receipt['native_operation_running'] and receipt['receipt_persistence_failed']
    assert receipt['state']=='unknown_outcome'
    apply(owned,record);assert owned.cursor.execute.call_count==1


def test_completed_poll_reads_receipt_after_worker_release_callback(owned):
    record=review(owned);executing=threading.Event();finish_sql=threading.Event()
    releasing=threading.Event();finish_release=threading.Event();polling=threading.Event()
    original_update=owned.archive.update;original_describe=owned.client.describe_result
    def execute(*_):executing.set();assert finish_sql.wait(3)
    def update(key,**changes):
        if changes.get('last_native_phase')=='session_release':
            releasing.set();assert finish_release.wait(3)
        return original_update(key,**changes)
    owned.cursor.execute.side_effect=execute
    observed=[];failures=[]
    def read():
        try:observed.append(call(owned,'receipt',review_id=record['review_id']))
        except BaseException as error:failures.append(error)
    def describe(token):polling.set();return original_describe(token)
    with patch.object(owned.archive,'update',side_effect=update):
        apply(owned,record);assert executing.wait(3)
        try:
            finish_sql.set();assert releasing.wait(3)
            with patch.object(owned.client,'describe_result',side_effect=describe):
                reader=threading.Thread(target=read);reader.start();assert polling.wait(3)
                finish_release.set();reader.join(3)
        finally:finish_sql.set();finish_release.set()
    owned.client._eds_pool_reviews[record['review_id']]['token'].worker.join(3)
    assert not failures and len(observed)==1
    assert not observed[0]['native_operation_running']
    assert observed[0]['last_native_phase']=='session_release' and 'native_after' in observed[0]


def test_read_only_archive_pagination_and_mutation_rejection(owned):
    values=[review(owned) for _ in range(3)]
    first=owned.archive.recent(0,2);last=owned.archive.recent(2,2)
    assert first['more'] and not last['more'] and first['total']==3
    assert len({item['review_id'] for item in first['receipts']+last['receipts']})==3
    with pytest.raises(ValueError):owned.archive.recent(True,25)
    with pytest.raises(ValueError):owned.archive.update(values[0]['review_id'],source='ALTER DATABASE')
    call(owned,'discard',review_id=values[0]['review_id'],review_digest=values[0]['review_digest'])
    assert apply(owned,values[0])['state']=='discarded'
    owned.cursor.execute.assert_not_called()


def test_retention_never_removes_unresolved_dispatch_or_authorizes_replay(owned):
    record=review(owned)
    assert owned.archive.claim(record['review_id'],record['review_digest'])
    with pytest.raises(ValueError,match='unresolved'):
        owned.archive.remove(record['review_id'],record['review_digest'],True)
    owned.archive.update(record['review_id'],last_native_phase='session_release',native_acknowledged=True)
    with pytest.raises(ValueError):owned.archive.remove(record['review_id'],record['review_digest'],False)
    removed=owned.archive.remove(record['review_id'],record['review_digest'],True)
    assert not removed['native_operation_requested'] and not removed['automatic_retry']
    with pytest.raises(ValueError):apply(owned,record)
    owned.cursor.execute.assert_not_called()


def test_cancel_uses_existing_native_signal_and_preserves_ack_before_late_cleanup(owned):
    record=review(owned);entered=threading.Event();release=threading.Event()
    def execute(*_):entered.set();assert release.wait(3)
    owned.cursor.execute.side_effect=execute
    def cancel(native_type):
        if native_type==owned.client.module.CancelType.DISABLE:
            # First acknowledgement must already be durable before signal cleanup.
            assert owned.archive.get(record['review_id'])['native_acknowledged']
            raise RuntimeError('Owned late cancellation cleanup')
    owned.handle._att.cancel_operation.side_effect=cancel
    try:
        apply(owned,record);assert entered.wait(3)
        requested=call(owned,'cancel',review_id=record['review_id'])
        assert requested['cancellation_requested'] and requested['cancellation_delivery_accepted']
    finally:release.set()
    owned.client._eds_pool_reviews[record['review_id']]['token'].worker.join(3)
    receipt=call(owned,'receipt',review_id=record['review_id'])
    assert receipt['native_acknowledged'] and receipt['session_reuse_blocked']
    assert owned.client.module.CancelType.ABORT not in [call.args[0] for call in owned.handle._att.cancel_operation.call_args_list]
    owned.handle.rollback.assert_not_called()


def test_archive_admission_does_not_resolve_provider_or_native_workspace(tmp_path):
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    from pgadmin.cdeadmin.workspace.firebird_eds_pool_receipts import for_workspace
    endpoint=SimpleNamespace(id='endpoint',profile_id='firebird-native',provider_id='org.cdeadmin.firebird')
    service=SimpleNamespace(endpoint_service=Mock(),operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'ops')),
        _principal_id=lambda _server:1)
    service.endpoint_service.provider_registry.admitted_permissions.return_value={'data_read'}
    archive=for_workspace(service,SimpleNamespace(endpoint_profile=endpoint),'registered-target')
    assert archive.binding==[1,'endpoint','registered-target']
    service.endpoint_service.workspace.assert_not_called()
    service.endpoint_service.provider_registry.resolve.assert_not_called()
    service.endpoint_service._owned_database_target.assert_called_once_with(endpoint,'registered-target')
    service.endpoint_service.provider_registry.admitted_permissions.return_value=set()
    with pytest.raises(ValueError,match='permission'):for_workspace(service,SimpleNamespace(endpoint_profile=endpoint),'registered-target')
    endpoint.provider_id='org.cdeadmin.firebird.embedded'
    with pytest.raises(ValueError,match='registration'):for_workspace(service,SimpleNamespace(endpoint_profile=endpoint),'registered-target')
