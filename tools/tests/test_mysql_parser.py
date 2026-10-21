"""Versioned server grammar uses observed modes and isolated native parsing."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_parser as parser
from pgadmin.cdeadmin.providers.mysql_family.mysql_native_validation import validate
from pgadmin.cdeadmin.sdk import RelationalClientError
from test_mysql_native_validation import owned


def observation(mode=''):
    return {'version':'9.7.0','thread_id':52,'connection_id':12,'variables':{'sql_mode':mode}}


def native_result(errors=()):
    return {'available':True,'parser_version':'9.7.0','statements':[{'accepted':not errors,
        'sql_syntax_valid':not any(not row['optimizer_hint'] for row in errors),
        'native_status':2 if errors else 0,'diagnostics':list(errors)}],
        'sql_executed':False,'database_connection_opened':False}


def test_native_grammar_reads_only_independent_source_language_facts_without_prepare_or_database_binding(monkeypatch):
    source, observer, _connect, peer, query, client = owned()
    monkeypatch.setattr(parser,'library',lambda _client:Path('/owned/mysql_9.7.so'))
    run=Mock(return_value=native_result());monkeypatch.setattr(parser,'native',run)
    try:
        result=validate(client,source,'SELECT value FROM future_table')
        assert result['grammar_valid'] and result['authority']=='mysql-native-versioned-server-grammar'
        assert result['sql_mode']=='ANSI_QUOTES,NO_BACKSLASH_ESCAPES' and result['original_diagnostics_preserved']
        assert not result['original_session_catalog_binding_validated'] and result['original_session_commands_sent']==0
        assert run.call_args.args[1]==[{'source':'SELECT value FROM future_table','sql_mode':'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'}]
        assert not any(call.args[0].startswith(('PREPARE','USE ','SET ')) for call in query.execute.call_args_list)
        source.cursor.assert_not_called();peer.close.assert_not_called()
    finally:observer.close()


def test_native_grammar_context_loss_closes_only_the_observer_and_requires_authenticated_renewal(monkeypatch):
    source, observer, _connect, peer, query, client=owned()
    monkeypatch.setattr(parser,'library',lambda _client:Path('/owned/mysql_9.7.so'))
    query.execute.side_effect=OSError('Owned private observation loss')
    with pytest.raises(RelationalClientError,match='no original-session metadata command'):
        validate(client,source,'SELECT 1')
    assert observer.needs_connection_refresh and observer.connection is None
    source.cursor.assert_not_called();peer.close.assert_called_once();assert not client._uncertain_sessions


def test_native_grammar_diagnostic_maps_utf8_bytes_and_trimmed_script_offsets_without_source_text(monkeypatch):
    text='  \nSELECT 雪 FROM;'
    run=Mock(return_value=native_result([{'optimizer_hint':False,'byte_offset':len('SELECT 雪 FROM'.encode()),
        'byte_length':1,'native_line':1,'native_line_offset':1}]))
    monkeypatch.setattr(parser,'native',run)
    result=parser.validate(Path('/owned'),text,observation(),True)
    diagnostic=result['diagnostics'][0]
    assert not result['grammar_valid'] and diagnostic['offset']==text.index(';') and diagnostic['line']==2
    assert diagnostic['column']==len('SELECT 雪 FROM')+1 and '雪' not in diagnostic['message']


def test_optimizer_hint_warning_keeps_native_sql_grammar_valid(monkeypatch):
    monkeypatch.setattr(parser,'native',lambda *_args:native_result([{'optimizer_hint':True,'byte_offset':11,
        'byte_length':12,'native_line':1,'native_line_offset':12}]))
    result=parser.validate(Path('/owned'),'SELECT /*+ UNKNOWN_HINT(1) */ 1',observation(),False)
    assert result['grammar_valid'] and result['diagnostics'][0]['severity']=='warning'
    assert result['diagnostics'][0]['code']=='NATIVE_OPTIMIZER_HINT'


@pytest.mark.parametrize('changes',[{'return_code':-11},{'timed_out':True},{'cleanup_confirmed':False},{'stdout':b'{}'}])
def test_missing_or_unconfirmed_native_worker_reply_never_becomes_syntax_success(tmp_path,monkeypatch,changes):
    path=tmp_path/'mysql_9.7.so';path.write_bytes(b'owned native worker test placeholder')
    value={'return_code':0,'timed_out':False,'cleanup_confirmed':True,'stdout':json.dumps(native_result()).encode(),'stderr':b''}
    monkeypatch.setattr(parser,'observe_process',lambda *_args,**_kwargs:{**value,**changes})
    with pytest.raises(RelationalClientError,match='no SQL was executed'):
        parser.native(path,[{'source':'SELECT 1','sql_mode':''}])


def test_single_procedural_statement_bypasses_client_script_splitting_but_executes_no_sql(monkeypatch):
    run=Mock(return_value=native_result());monkeypatch.setattr(parser,'native',run)
    text='CREATE PROCEDURE p() BEGIN DECLARE x INT; SET x=1; END'
    result=parser.validate(Path('/owned'),text,observation(),False)
    assert result['grammar_valid'] and len(run.call_args.args[1])==1
    assert result['native_statements'][0]['native_preparation']=='not_attempted' and result['sql_executed'] is False


def test_script_syntax_mode_transitions_remain_explicitly_unconfirmed_instead_of_using_a_wrong_mode(monkeypatch):
    run=Mock(return_value=native_result());monkeypatch.setattr(parser,'native',run)
    result=parser.validate(Path('/owned'),"SET sql_mode=@runtime_value; SELECT 1",observation(),True)
    assert result['grammar_valid'] is None and not result['script_ready']
    assert any(row['code']=='NATIVE_FUTURE_MODE' for row in result['diagnostics'])
    assert run.call_args.args[1]==[{'source':'SET sql_mode=@runtime_value','sql_mode':''}]


def test_explicit_unavailable_native_library_does_not_silently_substitute_another_version(tmp_path,monkeypatch):
    monkeypatch.setenv('CDEADMIN_MYSQL_PARSER_LIBRARY',str(tmp_path/'absent.so'))
    with pytest.raises(OSError):parser.library(object())
