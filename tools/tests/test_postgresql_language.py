"""Real offline parser boundaries and retained-session admission."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.postgresql.language import analyze
from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator
from pgadmin.cdeadmin.data_studio.studio import DataStudioService
from test_cdeadmin_postgresql_provider import (
    PostgreSQLProvider, FakeDriver, FakePermissions, endpoint,
)


def check(source, **kwargs):
    return analyze(source, standard_strings='on', **kwargs)


def test_sql_body_and_unicode_use_native_boundaries():
    source = "SELECT 'é;😀'; CREATE FUNCTION f() RETURNS int LANGUAGE SQL BEGIN ATOMIC SELECT 1; END; SELECT $$a;b$$;"
    result = check(source, script=True)
    assert result['grammar_valid'] and result['script_ready']
    assert len(result['statements']) == 3
    assert 'BEGIN ATOMIC SELECT 1; END' in result['statements'][1]['source']
    for statement in result['statements']:
        assert source[statement['start']:statement['end']] == statement['source']
    assert result['parser_version'] == 'pglast v8.5; PostgreSQL 18.6'


def test_syntax_error_is_not_lexical_success():
    source = "SELECT 'é';\nSELCT 2"
    result = check(source, script=True)
    assert not result['grammar_valid'] and not result['script_ready']
    error = result['diagnostics'][0]
    assert error['offset'] == source.index('SELCT')
    assert (error['line'], error['column']) == (2, 1)


@pytest.mark.parametrize('source,code', [
    ('COPY t FROM STDIN', 'DATA_FRAMING_REQUIRED'),
    ('RESET ALL', 'SESSION_FRAMING_CHANGE'),
    ('DISCARD ALL', 'SESSION_FRAMING_CHANGE'),
    ('SET standard_conforming_strings=off', 'SESSION_FRAMING_CHANGE'),
    ("SELECT pg_catalog.set_config('standard_conforming_strings','off',false)", 'SESSION_FRAMING_CHANGE'),
    ('SELECT 1\x00; DROP TABLE t', 'INVALID_SOURCE'),
    ('-- only comment', 'EMPTY_SOURCE'),
])
def test_unsafe_script_framing_is_refused(source, code):
    result = check(source, script=True)
    assert not result['script_ready']
    assert code in {item['code'] for item in result['diagnostics']}


def test_words_in_literals_do_not_change_session():
    assert check("SELECT 'SET standard_conforming_strings=off'; -- COPY t FROM STDIN", script=True)['script_ready']


def test_nonstandard_or_unknown_strings_not_assumed():
    for mode in (None, 'off'):
        assert not analyze('SELECT 1', script=True, standard_strings=mode)['script_ready']


def test_parser_checks_sql_not_quoted_body_semantics():
    result = check("CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$not valid plpgsql$$")
    assert result['grammar_valid']
    assert 'quoted procedural bodies are not checked' in result['scope']


def test_bounds():
    with pytest.raises(LanguageToolError):
        check('x' * (2 * 1024 * 1024 + 1))
    assert not check('SELECT 1;' * 1001, script=True)['script_ready']


def test_provider_checks_retained_session_without_sql():
    provider = PostgreSQLProvider(endpoint(), FakePermissions(), FakeDriver())
    session = provider.open_session({'route': {'server_id': 7}})
    connection = provider._sessions[session['session_id']].connection
    connection.info = SimpleNamespace(parameter_status=Mock(return_value='on'), server_version=180003)
    result = provider.validate_source_without_execution({
        'session_id': session['session_id'], 'language_profile': 'postgresql-sql',
        'source': 'DROP TABLE does_not_exist',
    })
    assert result['grammar_valid'] and result['server_version'] == 180003
    assert connection.executions == [] and connection.connect_calls == []
    provider._sessions[session['session_id']].uncertain = True
    with pytest.raises(RuntimeError, match='unknown'):
        provider.validate_source_without_execution({
            'session_id': session['session_id'], 'language_profile': 'postgresql-sql',
            'source': 'SELECT 1'})


def test_studio_passes_provider_identity_and_script_rechecks_mode():
    mode = ['on']
    def validate(request):
        assert request['session_id'] == 'native-id'
        return analyze(request['source'], script=request.get('script', False), standard_strings=mode[0])
    studio = SimpleNamespace(
        _operational_session=lambda *_: (
            SimpleNamespace(language_profile='postgresql-sql', provider_session={'session_id': 'native-id'}),
            SimpleNamespace(instance=SimpleNamespace(
                validate_source_without_execution=validate,
                script_statement_outcome=lambda _: 'success'))),
        execute=Mock(return_value={'occurrence_id': 'o1'}), poll=lambda *_: {})
    context = SimpleNamespace(endpoint_id='endpoint')
    result = DataStudioService.validate_source(studio, context, 'public-id', 'SELECT 1')
    assert result['grammar_valid']
    coordinator = ScriptCoordinator(studio)
    plan = coordinator.prepare(context, 'public-id', 'SELECT 1; SELECT 2')
    plan = coordinator.advance(context, plan['plan_id'], plan['revision'])
    plan = coordinator.advance(context, plan['plan_id'], plan['revision'])
    mode[0] = 'off'
    plan = coordinator.advance(context, plan['plan_id'], plan['revision'])
    assert plan['state'] == 'stopped' and not plan.get('unresolved')
    assert studio.execute.call_count == 1
