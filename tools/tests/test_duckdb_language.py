"""Native DuckDB grammar checks must not execute or disclose source."""

from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.language import analyze
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider


def test_native_boundaries_preserve_quoted_semicolons_and_unicode():
    pytest.importorskip('duckdb')
    source = "SELECT 'é;😀';\nSELECT $$x;y$$;"
    result = analyze(source, script=True)
    assert result['grammar_valid'] and result['script_ready']
    assert result['authority'] == 'duckdb-1.5.2-native-parser'
    assert len(result['statements']) == 2
    for statement in result['statements']:
        assert source[statement['start']:statement['end']] == statement['source']


def test_native_parser_refuses_invalid_sql_without_echoing_source():
    pytest.importorskip('duckdb')
    sensitive = "CREATE SECRET hidden (TYPE S3, KEY_ID 'private-marker');\nSELCT 1"
    result = analyze(sensitive, script=True)
    assert result['grammar_valid'] is False and not result['script_ready']
    assert result['diagnostics'][0]['code'] == 'DUCKDB_SYNTAX'
    assert 'private-marker' not in str(result)
    assert not analyze('-- comment only', script=True)['script_ready']


def test_provider_requires_retained_idle_session_but_never_runs_sql():
    import duckdb
    handle=Mock();handle.extract_statements.side_effect=duckdb.extract_statements
    provider = object.__new__(DuckDBPilotProvider)
    provider._sessions = {'owned': SimpleNamespace(handle=handle)}
    provider.client = SimpleNamespace(_require_idle=Mock(),_lock=threading.RLock(),_states={})
    result = provider.validate_source_without_execution({
        'session_id': 'owned', 'language_profile': 'duckdb-sql',
        'source': 'SELECT 1', 'script': True})
    assert result['grammar_valid'] and result['script_ready']
    provider.client._require_idle.assert_called_once_with(handle)
    assert handle.extract_statements.call_args_list[0].args==('SELECT 1',)
    handle.execute.assert_not_called()
    with pytest.raises(Exception, match='unavailable'):
        provider.validate_source_without_execution({
            'session_id': 'foreign', 'language_profile': 'duckdb-sql', 'source': 'SELECT 1'})
    with pytest.raises(Exception, match='binding'):
        provider.validate_source_without_execution({
            'session_id': 'owned', 'language_profile': 'postgresql-sql', 'source': 'SELECT 1'})


def test_script_outcome_preserves_unknown_native_dispatch():
    provider = object.__new__(DuckDBPilotProvider)
    def occurrence(*, error=None, blocked=False):
        return {'operation': {'terminal': True}, 'result': {'complete': True,
            'extensions': {'duckdb': {'payload': {
                'error': error, 'session_reuse_blocked': blocked}}}}}
    assert provider.script_statement_outcome(occurrence()) == 'success'
    assert provider.script_statement_outcome(occurrence(error={'type': 'BinderException'})) == 'error'
    assert provider.script_statement_outcome(occurrence(error={'type': 'IOException'}, blocked=True)) == 'unknown'


def test_validation_obeys_original_native_parser_limits_and_preserves_pending_work(tmp_path):
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
    client=_create_client();handle=client.open_session({'route':{'database':':memory:','allow_memory':True,'filesystem_root':str(tmp_path)}})
    provider=object.__new__(DuckDBPilotProvider);provider.client=client;provider._sessions={'owned':SimpleNamespace(handle=handle)}
    request={'session_id':'owned','language_profile':'duckdb-sql','script':True}
    try:
        handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle,'commit')
        handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
        handle.execute('SET max_expression_depth=40')
        source='SELECT '+'abs('*100+'1'+')'*100
        assert duckdb.extract_statements(source)
        refused=provider.validate_source_without_execution({**request,'source':source})
        assert refused['grammar_valid'] is False and refused['parser_context']=='retained-native-session'
        handle.execute('SET max_expression_depth=200')
        accepted=provider.validate_source_without_execution({**request,'source':source})
        assert accepted['grammar_valid'] and accepted['script_ready']
        for submitted in ['CREATE TABLE never_created(id INT)',"INSTALL definitely_uninstalled_extension",'CALL nonexistent_function()']:
            assert provider.validate_source_without_execution({**request,'source':submitted})['grammar_valid']
        assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='never_created'").fetchone()==(0,)
        assert handle.execute('SELECT * FROM pending').fetchall()==[(42,)]
        assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone()==(1,)
        handle.rollback();assert handle.execute('SELECT * FROM pending').fetchall()==[]
    finally:client.close()


def test_native_pragma_catalog_refusal_is_not_reported_as_invalid_grammar():
    import duckdb
    with duckdb.connect() as handle:
        result=analyze('PRAGMA deliberately_unknown_pragma',parser=handle.extract_statements)
        assert result['grammar_valid'] is None and result['diagnostics'][0]['code']=='DUCKDB_PARSE_CONTEXT'


def test_native_pragma_expansion_keeps_original_unicode_comments_and_script_boundaries():
    import duckdb
    source="-- lead; é😀\nPRAGMA table_info('not;executed');\nSELECT 'é;😀', $$body; value$$; /* trailing; comment */"
    with duckdb.connect() as handle:
        result=analyze(source,script=True,parser=handle.extract_statements)
        assert result['grammar_valid'] and result['script_ready'] and len(result['statements'])==2
        first,second=result['statements']
        assert first['source']=="-- lead; é😀\nPRAGMA table_info('not;executed');"
        assert second['source']=="\nSELECT 'é;😀', $$body; value$$;"
        assert first['native_expanded_types']==['SELECT']
        for statement in result['statements']:
            assert source[statement['start']:statement['end']]==statement['source']


def test_native_framing_skips_empty_units_without_splitting_quoted_identifiers():
    import duckdb
    source=';; PRAGMA table_info(\'missing\');; SELECT 1 AS "semi; é"; -- tail;'
    with duckdb.connect() as handle:
        result=analyze(source,script=True,parser=handle.extract_statements)
        assert result['grammar_valid'] and len(result['statements'])==2
        assert result['statements'][1]['source']==' SELECT 1 AS "semi; é";'


def test_generated_native_sql_in_a_comment_cannot_replace_the_original_command():
    import duckdb
    source="PRAGMA table_info('pending'); -- SELECT * FROM pragma_table_info('pending');"
    with duckdb.connect() as handle:
        result=analyze(source,script=True,parser=handle.extract_statements)
        assert result['grammar_valid'] and result['script_ready']
        assert len(result['statements'])==1
        assert result['statements'][0]['source']=="PRAGMA table_info('pending');"
        assert result['statements'][0]['start']==0
