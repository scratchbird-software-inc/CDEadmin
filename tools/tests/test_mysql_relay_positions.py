"""Wide coordinates require a target witness and unchanged owned dispatch."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from pgadmin.cdeadmin.providers.mysql_family import relay_positions as relay
from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE, MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.providers.mysql_replication import compile_operation
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import backend_draft, engine_operations, operation_draft

TARGET = {'resource_kind':'replication-channel','display_name':'Owned channel',
          'native':{'channel_name':"owned ' 雪"}}


def request(operation='alter', value=str(2**53+1)):
    options = {'RELAY_LOG_FILE':'relay.000001','RELAY_LOG_POS':value}
    draft = {'source_options':options,'source_password':'owned-private'} if operation == 'alter' else {'thread':'SQL_THREAD','until':options}
    return {'resource_kind':'replication-channel','operation_id':operation,'target_resource':TARGET,
            'draft':draft,'_provider_route':{'host':'trusted','database':'user-work'}}


class Handle:
    def __init__(self, rows, error=None, fetch_error=False, close_error=False):
        self.rows=[(*row,'9.7.0') if len(row)==2 else row for row in rows]; self.error=error; self.fetch_error=fetch_error; self.close_error=close_error
        self.calls=[]; self.autocommit=False; self.closed=False; self.description=None; self.rowcount=0
    def cursor(self): return self
    def execute(self, source, parameters=None):
        self.calls.append((source,parameters))
        if source != relay.QUERY and self.error: raise self.error
        self.description = [('native-result',)] if source != relay.QUERY and self.fetch_error else None
    def fetchall(self):
        if self.calls[-1][0] != relay.QUERY:
            if self.fetch_error: raise OSError('owned lost post-ACK result')
            return []
        return self.rows
    def close(self): self.closed=True


def client(rows=None, **failure):
    value=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
    value.handles=[]; value.routes=[]; value.rows=rows if rows is not None else [('server',str(2**64-1))]
    def connect(request):
        value.routes.append(request['route']); handle=Handle(value.rows,**failure); value.handles.append(handle); return handle
    def close(handle):
        handle.close()
        if handle.close_error: raise OSError('owned close reply lost')
    value._connect=connect; value._safe_close=lambda handle:None; value._forget_and_close=close
    return value


@pytest.mark.parametrize('operation',['alter','start'])
@pytest.mark.parametrize('value',[str(2**32),str(2**53+1),str(2**64-1)])
def test_wide_positions_bind_target_maximum_and_preserve_exact_sql_and_private_credentials(operation,value):
    native=client(); planned=native.plan_admin_operation(request(operation,value))
    assert planned['command_preview']['native_relay_position']=={'server_uuid':'server','maximum':str(2**64-1),'requested':value}
    assert 'owned-private' not in str(planned['command_preview'])
    result=native.apply_admin_operation(planned)
    assert result['native_acknowledged'] and not result['staged_in_provider_session']
    assert not result['commit_requested'] and not result['rollback_requested'] and not result['automatic_retry']
    assert value in native.handles[-1].calls[-1][0]
    assert all(handle.closed and handle.autocommit for handle in native.handles)
    assert all(route['database'] is None for route in native.routes)


@pytest.mark.parametrize('rows',[[('server',str(2**32-1))],[],[('server','18446744073709551614')],[('',str(2**64-1))],[('server',None)]])
def test_small_or_unavailable_target_width_cannot_produce_a_dispatchable_wide_plan(rows):
    native=client(rows)
    with pytest.raises(RelationalClientError): native.plan_admin_operation(request())
    assert all(handle.closed and all(sql==relay.QUERY for sql,_ in handle.calls) for handle in native.handles)


def test_same_uuid_with_a_changed_ceiling_and_replacement_instance_refuse_before_mutation():
    for rows in [[('other-instance',str(2**64-1))],[('server',str(2**32-1))],[]]:
        native=client(); planned=native.plan_admin_operation(request()); native.rows=rows
        with pytest.raises(RelationalClientError) as caught: native.apply_admin_operation(planned)
        assert not caught.value.native_dispatched and not caught.value.automatic_retry
        assert [sql for sql,_ in native.handles[-1].calls]==[relay.QUERY]
        assert native.handles[-1].closed


@pytest.mark.parametrize('fault',['sql','parameter','no-review','multiple-statements'])
def test_private_payload_changes_and_missing_review_never_dispatch(fault):
    native=client(); planned=native.plan_admin_operation(request()); compiled=planned['provider_payload']['compiled']
    if fault=='sql':compiled['statements'][0]['source']+=' extra SQL'
    elif fault=='parameter':compiled['statements'][0]['parameters']=('changed-file','changed-password','changed-channel')
    elif fault=='multiple-statements':compiled['statements'].append(deepcopy(compiled['statements'][0]))
    else:compiled.pop('mysql_relay_review')
    before=len(native.handles)
    with pytest.raises(RelationalClientError): native.apply_admin_operation(planned)
    assert len(native.handles)==before


def test_borrowed_interactive_handle_is_refused_without_metadata_queries():
    native=client(); planned=native.plan_admin_operation(request()); original=Handle([])
    with pytest.raises(RelationalClientError): MYSQL_ADMINISTRATION.apply(native,planned,connection=original)
    assert original.calls==[] and not original.closed


@pytest.mark.parametrize('failure,acknowledged', [('native-error',False),('fetch',True),('close',True)])
def test_native_failure_and_lost_post_ack_observations_are_not_replayed(failure,acknowledged):
    native=client(); planned=native.plan_admin_operation(request())
    error=RuntimeError('owned server detail containing a credential'); error.errno=1236; error.sqlstate='HY000'
    old_connect=native._connect
    def connect(request):
        handle=old_connect(request)
        if failure=='native-error':handle.error=error
        elif failure=='fetch':handle.fetch_error=True
        else:handle.close_error=True
        return handle
    native._connect=connect
    with pytest.raises(RelationalClientError) as caught: native.apply_admin_operation(planned)
    assert caught.value.native_dispatched and caught.value.native_acknowledged is acknowledged
    assert not caught.value.automatic_retry and 'credential' not in str(caught.value)
    if failure=='native-error':assert caught.value.errno==1236 and caught.value.sqlstate=='HY000'
    assert len([sql for sql,_ in native.handles[-1].calls if sql!=relay.QUERY])==1


@pytest.mark.parametrize('value',[True,str(2**64),2**53,'01','-1','1;STOP REPLICA'])
def test_wrong_or_inexact_coordinate_inputs_are_rejected_by_native_input_compilation(value):
    with pytest.raises(RelationalClientError): compile_operation('alter',request(value=value)['draft'],TARGET)


def test_small_positions_keep_the_existing_native_path_without_metadata_requirement():
    compiled=MYSQL_ADMINISTRATION._compile(request(value=str(2**32-1)))
    assert relay.position(compiled) is None


def test_declared_until_text_field_projects_the_full_unsigned_coordinate_without_rounding():
    declaration=engine_operations('mysql')['start@replication-channel']
    ui=operation_draft(declaration,{'until_kind':'RELAY','relay_file':'relay.000001','relay_pos':str(2**64-1)},'Owned channel')
    draft=backend_draft({'tabs':[{'fields':declaration['fields']}]},ui)
    native=client(); planned=native.plan_admin_operation({**request('start'),'draft':draft})
    assert planned['command_preview']['native_relay_position']['requested']==str(2**64-1)


def test_denied_metadata_retains_numeric_error_without_native_exception_text_or_fallback():
    native=client(); error=RuntimeError('private native metadata details'); error.errno=1142; error.sqlstate='42000'
    old=native._connect
    def connect(request):
        handle=old(request)
        def execute(source, parameters=None):
            handle.calls.append((source, parameters)); raise error
        handle.execute=execute
        return handle
    native._connect=connect
    with pytest.raises(RelationalClientError) as caught: native.plan_admin_operation(request())
    assert caught.value.errno==1142 and caught.value.sqlstate=='42000'
    assert not caught.value.native_dispatched and not caught.value.automatic_retry
    assert 'private native metadata details' not in str(caught.value)
    assert native.handles[-1].calls==[(relay.QUERY,None)] and native.handles[-1].closed


def test_changed_native_version_cannot_borrow_the_pinned_unsigned_long_contract():
    native=client([('server',str(2**64-1),'9.8.0')])
    with pytest.raises(RelationalClientError):native.plan_admin_operation(request())
    assert all(handle.closed and [sql for sql,_ in handle.calls]==[relay.QUERY] for handle in native.handles)


def test_cleanup_failure_cannot_replace_the_primary_native_error():
    native=client(); planned=native.plan_admin_operation(request())
    error=RuntimeError('native private detail'); error.errno=1776; error.sqlstate='HY000'
    old=native._connect
    def connect(request):
        handle=old(request); handle.error=error; handle.close_error=True; return handle
    native._connect=connect
    with pytest.raises(RelationalClientError) as caught:native.apply_admin_operation(planned)
    assert caught.value.errno==1776 and caught.value.sqlstate=='HY000'
    assert caught.value.native_dispatched and not caught.value.native_acknowledged
    assert not caught.value.automatic_retry and native.handles[-1].closed


def test_an_outer_exception_does_not_hide_a_later_post_ack_cleanup_failure():
    native=client(); planned=native.plan_admin_operation(request()); old=native._connect
    def connect(request):
        handle=old(request); handle.close_error=True; return handle
    native._connect=connect
    try:raise RuntimeError('unrelated caller exception')
    except RuntimeError:
        with pytest.raises(RelationalClientError) as caught:native.apply_admin_operation(planned)
    assert caught.value.native_acknowledged and not caught.value.automatic_retry
