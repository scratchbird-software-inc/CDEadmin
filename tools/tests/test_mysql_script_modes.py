"""Deterministic preview contexts and retained execution admission, without SQL."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_script_modes import frame
from pgadmin.cdeadmin.providers.mysql_family import mysql_parser as parser
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator


class Canonical:
    def __init__(self):self.calls=[]
    def __call__(self, value):
        self.calls.append(value)
        if value==4:return 'ANSI_QUOTES'
        if value=='ANSI':return 'ANSI_QUOTES,PIPES_AS_CONCAT'
        if value not in {'','ANSI_QUOTES','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES'}:
            raise ValueError('Native mode refused')
        return value
    def default_mode(self):return 'NO_BACKSLASH_ESCAPES'


def test_boundaries_follow_declared_native_quote_modes_and_keep_source_offsets():
    source="SET sql_mode='NO_BACKSLASH_ESCAPES'; SELECT 'tail\\'; SELECT 2;"
    value=frame(source,'',Canonical())
    assert not value['diagnostics'] and len(value['statements'])==3
    assert [row['sql_mode'] for row in value['statements']]==['','NO_BACKSLASH_ESCAPES','NO_BACKSLASH_ESCAPES']
    for row in value['statements']:
        assert source[row['start']:row['end']]==row['source']
        assert row['syntax_context']=={'sql_mode':row['sql_mode']}


def test_saved_mode_alias_expansion_multiple_assignments_and_restore_are_sequential():
    canonical=Canonical()
    value=frame("SET @old=@@SESSION.sql_mode, sql_mode='ANSI'; CREATE TABLE t(\"id\" INT); SET sql_mode=@OLD; SELECT 1",'',canonical)
    assert not value['diagnostics'] and len(value['statements'])==4
    assert [row['sql_mode'] for row in value['statements']]==['','ANSI_QUOTES,PIPES_AS_CONCAT','ANSI_QUOTES,PIPES_AS_CONCAT','']
    assert canonical.calls==['ANSI','']


def test_numeric_concat_default_and_prospective_global_modes_use_native_canonicalization():
    value=frame("SET sql_mode=4; SET sql_mode=CONCAT(@@sql_mode, ',NO_BACKSLASH_ESCAPES'); SET GLOBAL sql_mode=''; SET SESSION sql_mode=DEFAULT; SELECT 1",'',Canonical())
    assert not value['diagnostics']
    assert [row['sql_mode'] for row in value['statements']]==['','ANSI_QUOTES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES','']
    default=frame('SET SESSION sql_mode=DEFAULT; SELECT 1','',Canonical())
    assert default['statements'][-1]['sql_mode']=='NO_BACKSLASH_ESCAPES'


@pytest.mark.parametrize('expression',['@unknown','@@sql_mode + 1','@@sql_mode(1)','`DEFAULT`','read_mode()','CONCAT(@unknown,\'ANSI_QUOTES\')'])
def test_runtime_expressions_are_never_guessed(expression):
    value=frame('SET sql_mode='+expression+'; SELECT 1','',Canonical())
    assert len(value['statements'])==1 and value['diagnostics'][0]['code']=='NATIVE_FUTURE_MODE'
    assert not value['script_ready']


def test_unknown_final_setting_has_no_unparsed_tail_but_global_default_remains_unknown():
    assert not frame('SET sql_mode=@unknown; -- final comment\n','',Canonical())['diagnostics']
    value=frame('SET GLOBAL sql_mode=DEFAULT; SET SESSION sql_mode=DEFAULT; SELECT 1','',Canonical())
    assert len(value['statements'])==2 and value['diagnostics'][0]['code']=='NATIVE_FUTURE_MODE'
    value=frame("SET PERSIST_ONLY sql_mode='ANSI_QUOTES'; SELECT 1",'',Canonical())
    assert not value['diagnostics'] and value['statements'][-1]['sql_mode']==''


def test_executable_comment_version_gate_and_user_variable_invalidation():
    value=frame("/*!90700 SET sql_mode='ANSI_QUOTES' */; SELECT 1",'',Canonical())
    assert not value['diagnostics'] and value['statements'][-1]['sql_mode']=='ANSI_QUOTES'
    value=frame("/*!99999 SET sql_mode='ANSI_QUOTES' */; SELECT 1",'',Canonical())
    assert not value['diagnostics'] and value['statements'][-1]['sql_mode']==''
    value=frame('SET @old=@@sql_mode; CALL may_change_user_variables(); SET sql_mode=@old; SELECT 1','',Canonical())
    assert len(value['statements'])==3 and value['diagnostics'][0]['code']=='NATIVE_FUTURE_MODE'


@pytest.mark.parametrize('statement',[
    "SET @other=(@old:='ANSI_QUOTES')",'WITH c AS (SELECT 1) SELECT * FROM c',
    "CREATE TABLE t AS SELECT @old:='ANSI_QUOTES'",'EXPLAIN ANALYZE SELECT change_vars()'])
def test_opaque_assignments_and_expression_execution_invalidate_saved_values(statement):
    value=frame('SET @old=@@sql_mode; '+statement+'; SET sql_mode=@old; SELECT 1','',Canonical())
    assert len(value['statements'])==3 and value['diagnostics'][0]['code']=='NATIVE_FUTURE_MODE'


def test_large_nonsetting_commands_bypass_mode_expression_budget_and_client_delimiter_is_preserved():
    source='DELIMITER //\nCREATE LIBRARY l LANGUAGE JAVASCRIPT AS $js$'+('const x = 1; '*3000)+'$js$//\nSELECT 1//'
    value=frame(source,'',Canonical())
    assert not value['diagnostics'] and len(value['statements'])==2
    assert value['statements'][0]['source'].endswith('$js$')


def test_native_parser_receives_each_predicted_context_and_returns_ready_only_for_entire_script(monkeypatch):
    def native(_path, statements):
        assert [row['sql_mode'] for row in statements]==['','ANSI_QUOTES','ANSI_QUOTES']
        return {'statements':[{'sql_syntax_valid':True,'diagnostics':[]} for _ in statements]}
    monkeypatch.setattr(parser,'native',native)
    value=parser.validate(None,"SET sql_mode=4; CREATE TABLE t(\"id\" INT); SELECT 1",
        {'version':'9.7.0','thread_id':1,'connection_id':2,'variables':{'sql_mode':''}},True,Canonical())
    assert value['grammar_valid'] is True and value['script_ready']


@pytest.mark.parametrize('drift',[False,True])
def test_retained_script_checks_statement_context_after_intentional_change_and_blocks_drift(drift):
    source="SET sql_mode='ANSI_QUOTES'; SELECT 1"
    statements=frame(source,'',Canonical())['statements']
    prepared={'script_ready':True,'source_sha256':'owned','statements':statements,'sql_mode':''}
    validator=Mock(side_effect=[prepared,{'grammar_valid':True,'sql_mode':''},
        {'grammar_valid':True,'sql_mode':'' if drift else 'ANSI_QUOTES'}])
    provider=SimpleNamespace(validate_source_without_execution=validator,script_statement_outcome=lambda _: 'success')
    studio=SimpleNamespace(_operational_session=lambda *_: (SimpleNamespace(language_profile='mysql-sql',
        provider_session={'session_id':'native'}),SimpleNamespace(instance=provider)),
        execute=Mock(side_effect=[{'occurrence_id':'first'},{'occurrence_id':'second'}]),poll=lambda *_: {})
    scripts=ScriptCoordinator(studio);context=SimpleNamespace(endpoint_id='owned')
    plan=scripts.prepare(context,'session',source)
    for _ in range(3):plan=scripts.advance(context,plan['plan_id'],plan['revision'])
    assert [call.args[0]['script'] for call in validator.call_args_list]==[True,False,False]
    assert studio.execute.call_count==(1 if drift else 2)
    assert plan['state']==('stopped' if drift else 'waiting')
    if drift:assert plan['stop_reason']=='source-validation-changed'
