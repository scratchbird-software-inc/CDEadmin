"""Native attribute framing, text encoding, state restoration and private plans."""
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest
from mysql.connector.constants import ClientFlag,ServerCmd
from mysql.connector.protocol import MySQLProtocol

from pgadmin.cdeadmin.providers.mysql_family import mysql_query_attributes as attrs
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator


def test_native_null_attribute_metadata_contains_its_name_and_never_changes_sql():
    value=attrs.packet(MySQLProtocol(),b'SELECT 7',[('tag',None)])
    assert value==b'\x01\x01\x01\x01\x06\x00\x03tagSELECT 7'
    value=attrs.packet(MySQLProtocol(),b'SELECT 7',[('é',None)])
    assert value==b'\x01\x01\x01\x01\x06\x00\x02\xc3\xa9SELECT 7'


class Native:
    client_flags=ClientFlag.CLIENT_QUERY_ATTRIBUTES
    _handshake={'capabilities':ClientFlag.CLIENT_QUERY_ATTRIBUTES}
    _cmysql=None
    def __init__(self):
        self._attrs={'previous':17};self._protocol=MySQLProtocol();self._query=b'SELECT 7';self.sent=[]
    @property
    def query_attrs(self):return list(self._attrs.items())
    def query_attrs_append(self,value):self._attrs[value[0]]=value[1]
    def query_attrs_clear(self):self._attrs={}
    def _send_cmd(self,command,argument,*args,**kwargs):self.sent.append((command,argument));return b'owned-native-reply'
    def cursor(self):raise AssertionError('Original SQL was sent for attribute metadata')


def test_wire_bridge_keeps_native_null_and_exact_latin1_bytes_and_restores_original_client_state(monkeypatch):
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables.observe',lambda _:{'variables':{'character_set_client':'latin1'}})
    native=Native();scope=attrs.Scope(native,{'é':None,'label':'é €'})
    scope.install();scope.bind()
    assert native.query_attrs==[('é',None),('label',b'\xe9 \x80')]
    assert native._send_cmd(ServerCmd.QUERY,b'broken-pinned-metadataSELECT 7')==b'owned-native-reply'
    assert len(native.sent)==1 and native.sent[0][1].endswith(b'\xe9 \x80SELECT 7')
    assert b'\x01\xe9' in native.sent[0][1]
    scope.restore()
    assert native.query_attrs==[('previous',17)] and '_send_cmd' not in native.__dict__


def test_packet_layout_drift_is_refused_before_a_native_command():
    native=Native();scope=attrs.Scope(native,{'label':None});scope.install()
    try:
        with pytest.raises(attrs.AttributeAdmissionError):native._send_cmd(ServerCmd.QUERY,b'different SQL')
        assert not native.sent
    finally:scope.restore()


def test_unnegotiated_native_capability_never_silently_drops_attributes():
    native=Native();native._handshake={'capabilities':0}
    with pytest.raises(attrs.AttributeAdmissionError):attrs.Scope(native,{'tag':1}).install()
    assert native.query_attrs==[('previous',17)] and not native.sent


def test_c_connector_uses_actual_negotiated_native_flags_instead_of_requested_python_flags(monkeypatch):
    monkeypatch.setattr(attrs,'c_attributes_abi',lambda:1)
    native=Native();native.client_flags=0
    native._cmysql=SimpleNamespace(st_client_flag=lambda:ClientFlag.CLIENT_QUERY_ATTRIBUTES)
    scope=attrs.Scope(native,{'label':None});scope.install()
    assert scope.active and not scope.send_override
    scope.restore();assert native.query_attrs==[('previous',17)]


@pytest.mark.parametrize('value',[[],None,{'name\0suffix':'x'},{'name':float('nan')},{'name':'\ud800'}])
def test_invalid_attribute_input_cannot_enter_native_execution(value):
    with pytest.raises(ValueError):attrs.request_value(value)


def test_native_exact_value_encodings_are_decoded_without_entering_sql_source():
    from decimal import Decimal
    value=attrs.decoded({'integer':{'encoding':'integer','data':'9007199254740993'},
        'decimal':{'encoding':'decimal','data':'1.2300'},'binary':{'encoding':'base64','data':'AP8='},'null':None})
    assert value=={'integer':9007199254740993,'decimal':Decimal('1.2300'),'binary':b'\0\xff','null':None}


def test_temporal_attribute_envelopes_use_native_python_values_with_exact_microseconds():
    import datetime
    value=attrs.decoded({'day':{'encoding':'date','data':'2026-10-21'},
        'stamp':{'encoding':'datetime','data':'2026-10-21 12:34:56.123456'},
        'duration':{'encoding':'time','data':'-25:00:00.123400'}})
    assert value=={'day':datetime.date(2026,10,21),'stamp':datetime.datetime(2026,10,21,12,34,56,123456),
        'duration':-datetime.timedelta(hours=25,microseconds=123400)}
    assert attrs.packet(MySQLProtocol(),b'SELECT 1',list(value.items())).endswith(b'SELECT 1')


def test_negative_duration_uses_absolute_native_time_fields_and_explicit_sign():
    import datetime
    import struct
    encoded=attrs.packet(MySQLProtocol(),b'SELECT 1',[('t',-datetime.timedelta(hours=25,microseconds=123400))])
    # count, set count, null bitmap, new types, TIME, flags, name length/name
    assert encoded[:8]==b'\1\1\0\1\x0b\0\1t'
    assert encoded[8:21]==b'\x0c\1'+struct.pack('<I',1)+b'\1\0\0'+struct.pack('<I',123400)
    assert encoded[21:]==b'SELECT 1'


@pytest.mark.parametrize('value',[None,1.2345678901234567,{'encoding':'integer','data':'18446744073709551615'},{'encoding':'time','data':'-25:00:00.123400'}])
def test_stock_c_attribute_port_is_refused_before_touching_native_driver_state(monkeypatch,value):
    monkeypatch.setattr(attrs,'c_attributes_abi',lambda:0)
    native=Native();native._cmysql=SimpleNamespace(st_client_flag=lambda:ClientFlag.CLIENT_QUERY_ATTRIBUTES)
    with pytest.raises(attrs.AttributeAdmissionError,match='corrected Connector/Python'):
        attrs.Scope(native,attrs.decoded({'value':value})).install()
    assert native.query_attrs==[('previous',17)] and not native.sent


def test_patched_c_port_keeps_native_types_and_source_charset_names_without_pure_wire_hook(monkeypatch):
    import datetime
    monkeypatch.setattr(attrs,'c_attributes_abi',lambda:1)
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables.observe',lambda _:{'variables':{'character_set_client':'latin1'}})
    native=Native();native._cmysql=SimpleNamespace(st_client_flag=lambda:ClientFlag.CLIENT_QUERY_ATTRIBUTES)
    values={'é':None,'n':2**64-1,'t':datetime.timedelta(hours=-25),'double':1.2345678901234567}
    scope=attrs.Scope(native,values);scope.install();scope.bind()
    assert native.query_attrs==list(values.items()) and native.query_attrs[0][0].encode('utf8')==b'\xe9'
    assert not scope.send_override and '_send_cmd' not in native.__dict__
    scope.restore();assert native.query_attrs==[('previous',17)]


@pytest.mark.parametrize('encoding,value',[('date','2026-02-30'),('datetime','2026-10-21T12:34:56+04:00'),
    ('datetime','2026-10-21 12:34:56.1234567'),('time','1:70:00')])
def test_invalid_or_lossy_temporal_input_cannot_dispatch(encoding,value):
    with pytest.raises(attrs.AttributeAdmissionError):attrs.decoded({'value':{'encoding':encoding,'data':value}})


def test_private_script_policy_is_frozen_not_returned_and_is_erased_with_the_plan():
    context=SimpleNamespace(endpoint_id='owned')
    session=SimpleNamespace(language_profile='mysql-sql',provider_session={'session_id':'native'})
    statement={'source':'SELECT 1','ordinal':1,'syntax_context_statement':True,'syntax_context':{'sql_mode':''}}
    validator=Mock(side_effect=[{'script_ready':True,'source_sha256':'owned','statements':[statement]},
        {'grammar_valid':True,'sql_mode':''}])
    provider=SimpleNamespace(validate_source_without_execution=validator,script_statement_outcome=lambda _:'success')
    studio=SimpleNamespace(_operational_session=lambda *_:(session,SimpleNamespace(instance=provider)),
        execute=Mock(return_value={'occurrence_id':'once'}),poll=lambda *_:{})
    coordinator=ScriptCoordinator(studio);value={'tag':'private-attribute-value'}
    plan=coordinator.prepare(context,'session','SELECT 1',mysql_query_attributes=value);value['tag']='edited'
    assert 'private-attribute-value' not in json.dumps(plan)
    plan=coordinator.advance(context,plan['plan_id'],plan['revision'])
    assert studio.execute.call_args.kwargs['output_policy']=={'mysql_query_attributes':{'tag':'private-attribute-value'}}
    plan=coordinator.advance(context,plan['plan_id'],plan['revision'])
    coordinator.discard(context,plan['plan_id']);assert not coordinator.execution_policies


def test_attribute_restore_failure_is_explicit_and_does_not_leave_a_wire_hook():
    native=Native();scope=attrs.Scope(native,{'label':None});scope.install()
    native.query_attrs_clear=Mock(side_effect=OSError('owned client state failure'))
    with pytest.raises(RuntimeError,match='restoration is unconfirmed'):scope.restore()
    assert '_send_cmd' not in native.__dict__


def test_worker_retains_completed_rows_and_quarantines_source_if_client_attribute_cleanup_fails(monkeypatch):
    from test_mysql_execution import harness,drain
    owner,connection,_native=harness([[7]])
    scope=SimpleNamespace(install=lambda:None,restore=Mock(side_effect=OSError('owned attribute restore loss')))
    monkeypatch.setattr(attrs,'Scope',lambda *_:scope)
    token=owner.execute(connection,{'source':'SELECT 7','parameters':[]},{})
    pages=drain(owner,token)
    assert any(page['payload']['rows']==[(7,)] for page in pages)
    assert token.cleanup_failed and id(connection) in owner.client._uncertain_sessions
    assert token.error['query_attribute_state_restore_unconfirmed']


def test_public_execution_summary_excludes_bound_attribute_values():
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    value=DataStudioService._execution_summary({'execution_id':'owned','session_id':'native','language_profile':'mysql-sql',
        'source':'SELECT 1','parameters':{},'deadline':None,'output_policy':{'mysql_query_attributes':{'label':'private-attribute-value'}}})
    assert 'private-attribute-value' not in json.dumps(value) and 'mysql_query_attributes' not in value
