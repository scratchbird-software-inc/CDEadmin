"""Native DuckDB grammar checks must not execute or disclose source."""

from types import SimpleNamespace
from unittest.mock import Mock

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
    provider = object.__new__(DuckDBPilotProvider)
    provider._sessions = {'owned': SimpleNamespace(handle='retained-handle')}
    provider.client = SimpleNamespace(_require_idle=Mock())
    result = provider.validate_source_without_execution({
        'session_id': 'owned', 'language_profile': 'duckdb-sql',
        'source': 'SELECT 1', 'script': True})
    assert result['grammar_valid'] and result['script_ready']
    provider.client._require_idle.assert_called_once_with('retained-handle')
    with pytest.raises(Exception, match='unavailable'):
        provider.validate_source_without_execution({
            'session_id': 'foreign', 'language_profile': 'duckdb-sql', 'source': 'SELECT 1'})
    with pytest.raises(Exception, match='binding'):
        provider.validate_source_without_execution({
            'session_id': 'owned', 'language_profile': 'postgresql-sql', 'source': 'SELECT 1'})
