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
    assert not analyze('SELECT 1', script=True, standard_strings=None)['script_ready']


def test_native_string_modes_and_function_overrides():
    from pglast import parser
    if getattr(parser, 'CDEADMIN_PARSE_OPTIONS_REVISION', None) != 2:
        pytest.skip('Requires the pinned native parser options build')
    source = r"SELECT 'it\'s'; SELECT 'é'"
    assert analyze(source, standard_strings='on')['grammar_valid'] is False
    checked = analyze(source, standard_strings='off', script=True)
    assert checked['script_ready'] and len(checked['statements']) == 2
    assert analyze(source, standard_strings='off', backslash_quote='off')['grammar_valid'] is False
    for language, body in [('sql', r"SELECT 'it\'s'"), ('plpgsql', r"BEGIN RETURN 'it\'s'; END")]:
        source = f'CREATE FUNCTION f() RETURNS text LANGUAGE {language} SET standard_conforming_strings TO off AS $b${body}$b$'
        assert analyze(source, standard_strings='on', script=True)['script_ready'] is True
        assert analyze(source.replace('TO off', 'TO on'), standard_strings='off')['grammar_valid'] is False


def test_native_parser_modes_do_not_bleed_between_threads():
    from pglast import parser
    from concurrent.futures import ThreadPoolExecutor
    if getattr(parser, 'CDEADMIN_PARSE_OPTIONS_REVISION', None) != 2:
        pytest.skip('Requires the pinned native parser options build')
    def run(index):
        mode = 'on' if index % 2 else 'off'
        source = r"DO $$BEGIN PERFORM 'it\'s'; END$$"
        return analyze(source, standard_strings=mode)['grammar_valid'] is (mode == 'off')
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(run, range(80)))


def test_parser_checks_quoted_plpgsql_body_without_execution():
    result = check("CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$not valid plpgsql$$")
    assert result['sql_grammar_valid']
    assert result['grammar_valid'] is False
    assert result['procedural_bodies'][0]['grammar_valid'] is False
    assert result['diagnostics'][0]['code'] == 'BODY_SYNTAX'


@pytest.mark.parametrize('source', [
    'CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $$BEGIN RETURN 1; END$$',
    'CREATE PROCEDURE p() LANGUAGE plpgsql AS $$BEGIN PERFORM 1; END$$',
    'DO $$BEGIN RAISE NOTICE \'ok\'; END$$',
    "CREATE FUNCTION f() RETURNS int LANGUAGE SQL AS 'SELECT 1'",
])
def test_native_offline_body_grammars_accept_valid_code(source):
    result = check(source)
    assert result['grammar_valid'] is True
    assert result['procedural_bodies'][0]['grammar_valid'] is True


def test_unknown_installed_body_language_is_not_reported_as_checked():
    result = check('CREATE FUNCTION f() RETURNS int LANGUAGE plpython3u AS $$return 1$$')
    assert result['sql_grammar_valid'] is True
    assert result['grammar_valid'] is None
    assert result['diagnostics'][0]['code'] == 'BODY_GRAMMAR_UNAVAILABLE'


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
    studio.scripts = ScriptCoordinator(studio)
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
