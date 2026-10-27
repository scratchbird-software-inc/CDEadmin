"""Dialect framing, source diagnostics and replay-safe script sequencing."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
import test_cdeadmin_provider_navigator  # noqa: F401
from pgadmin.cdeadmin.data_studio.language_tools import analyze
from pgadmin.cdeadmin.data_studio.scripts import ScriptCoordinator, retained_outcome
from pgadmin.cdeadmin.data_studio.models import DataStudioAccessError


@pytest.mark.parametrize('language,source,count', [
    ('postgresql-sql', "SELECT ';'; /* ; */ SELECT $$a;b$$;", 2),
    ('ysql', 'CREATE FUNCTION f() RETURNS void AS $body$ BEGIN PERFORM 1; END $body$ LANGUAGE plpgsql; SELECT 2;', 2),
    ('mysql-sql', 'DELIMITER //\nCREATE PROCEDURE p() BEGIN SELECT 1; SELECT 2; END//\nDELIMITER ;\nSELECT 3;', 2),
    ('sqlite-sql', 'CREATE TRIGGER t AFTER INSERT ON x BEGIN SELECT 1; SELECT 2; END; SELECT 3;', 2),
    ('cql-3', 'BEGIN BATCH INSERT INTO t (id) VALUES (1); INSERT INTO t (id) VALUES (2); APPLY BATCH; SELECT * FROM t;', 2),
    ('duckdb-sql', "SELECT 'a'';b'; SELECT 2;", 2),
])
def test_native_boundaries(language, source, count):
    result = analyze(source, language, script=True)
    assert result['script_ready'], result
    assert len(result['statements']) == count
    assert result['grammar_valid'] is None


@pytest.mark.parametrize('language', ['mysql-sql', 'mariadb-sql'])
@pytest.mark.parametrize('quote,settings', [
    ('`', {}), ('`', {'no_backslash_escapes': False}),
    ('"', {'ansi_quotes': True, 'no_backslash_escapes': False}),
    ('"', {'ansi_quotes': True, 'no_backslash_escapes': True})])
def test_native_identifier_backslash_does_not_escape_its_closing_quote(language, quote, settings):
    source = 'SELECT 1 AS '+quote+'back\\'+quote+'; SELECT 2;'
    result = analyze(source, language, script=True, settings=settings)
    assert result['script_ready'], result
    assert [row['source'] for row in result['statements']] == source.rstrip(';').split('; ')


@pytest.mark.parametrize('language', ['mysql-sql', 'mariadb-sql'])
def test_unknown_ansi_quote_mode_refuses_ambiguous_backslash_framing(language):
    result = analyze('SELECT "back\\"; SELECT 2;', language, script=True,
                     settings={'no_backslash_escapes': False})
    assert not result['script_ready']
    assert any('ANSI_QUOTES' in row['message'] for row in result['diagnostics'])


def test_mysql_carriage_return_does_not_terminate_native_line_comment():
    result = analyze('# ignored ;\rSELECT 1; -- ignored ;\rSELECT 2;', 'mysql-sql', script=True)
    assert not result['script_ready'] and not result['statements'], result


def test_mysql_client_directive_keywords_use_ascii_case_rules():
    checked = analyze('DELıMıTER //\nSELECT 1;', 'mysql-sql', script=True)
    assert not checked['client_directives']


@pytest.mark.parametrize('language,source,code', [
    ('mysql-sql', "SELECT 'a\\\'b';", 'SESSION_MODE_REQUIRED'),
    ('postgresql-sql', 'SELECT `column`;', 'QUOTE_DIALECT'),
    ('postgresql-sql', "SELECT 'unclosed", 'UNTERMINATED'),
    ('sqlite-sql', '.read secret.sql', 'CLIENT_COMMAND_UNSUPPORTED'),
    ('postgresql-sql', 'COPY t FROM STDIN;\n1\n\\.', 'DATA_FRAMING_REQUIRED'),
    ('opensearch-sql-ppl', 'SELECT 1', 'LANGUAGE_SELECTION_REQUIRED'),
])
def test_unsupported_or_ambiguous_source_is_not_approved(
        language, source, code):
    r = analyze(source, language, script=True)
    assert not r['script_ready']
    assert code in {d['code'] for d in r['diagnostics']}


def test_json_diagnostics_do_not_claim_api_validation():
    r = analyze('{"x":}', 'mongodb-query-api-json')
    assert r['diagnostics'][0]['code'] == 'JSON_SYNTAX'
    r = analyze('{"unknown":1}', 'mongodb-query-api-json')
    assert r['syntax_valid'] and r['grammar_valid'] is None


class Studio:
    def __init__(self): self.calls = []; self.outcome = 'success'

    def _operational_session(self, context, session_id):
        assert session_id == 'session'
        return SimpleNamespace(language_profile='postgresql-sql'), SimpleNamespace(
            instance=SimpleNamespace(script_statement_outcome=lambda _: self.outcome))

    def execute(self, context, session_id, source, **kwargs):
        self.calls.append(source)
        return {'occurrence_id': 'occ-' + str(len(self.calls))}

    def poll(self, context, occurrence_id): return {}


def test_duplicate_steps_cannot_submit_twice_and_poll_cannot_advance_next_statement():
    studio = Studio()
    scripts = ScriptCoordinator(studio)
    ctx = SimpleNamespace(endpoint_id='a')
    p = scripts.prepare(ctx, 'session', 'SELECT 1; SELECT 2;')
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(
                lambda _: scripts.advance(
                    ctx,
                    p['plan_id'],
                    0),
                range(2)))
    assert studio.calls == ['SELECT 1']
    current = scripts.advance(ctx, p['plan_id'], replies[0]['revision'])
    assert current['state'] == 'ready' and studio.calls == ['SELECT 1']
    current = scripts.advance(ctx, p['plan_id'], current['revision'])
    assert studio.calls == ['SELECT 1', 'SELECT 2']
    current = scripts.advance(ctx, p['plan_id'], current['revision'])
    assert current['state'] == 'complete'


@pytest.mark.parametrize('outcome', ['unknown', 'error', 'cancelled'])
def test_failure_never_submits_following_statement(outcome):
    studio = Studio()
    studio.outcome = outcome
    scripts = ScriptCoordinator(studio)
    ctx = SimpleNamespace(endpoint_id='a')
    p = scripts.prepare(ctx, 'session', 'UPDATE t SET x=1; SELECT 2;')
    p = scripts.advance(ctx, p['plan_id'], p['revision'])
    p = scripts.advance(ctx, p['plan_id'], p['revision'])
    assert p['state'] == 'stopped'
    scripts.advance(ctx, p['plan_id'], p['revision'])
    assert len(studio.calls) == 1


def test_plan_is_endpoint_bound():
    scripts = ScriptCoordinator(Studio())
    p = scripts.prepare(
        SimpleNamespace(
            endpoint_id='a'),
        'session',
        'SELECT 1;')
    with pytest.raises(DataStudioAccessError):
        scripts.advance(SimpleNamespace(endpoint_id='b'), p['plan_id'], 0)


def test_terminal_without_positive_provider_observation_is_unknown():
    assert retained_outcome({'operation': {'terminal': True}, 'result': {
                            'complete': True, 'extensions': {'x': {'payload': {}}}}}, 'x') == 'unknown'


@pytest.mark.parametrize('engine', ['influxdb', 'opensearch_sql_ppl'])
def test_distinct_languages_retain_distinct_sessions_and_reject_override(
        engine):
    from test_cdeadmin_actual_engine_pilots import PILOTS, provider
    cls, profile = next((c, p) for c, p in PILOTS if p.engine_id == engine)
    instance = provider(cls, profile)
    contributions = instance.data_studio_contributions()
    sessions = []
    for language in instance.language_routes:
        port = next(
            c for c in contributions['sessions'] if language in c.language_profiles)
        opened = port.open_session(
            SimpleNamespace(
                instance=instance), {
                'route': {
                    'route_id': 'direct'}})
        assert opened['language_profile'] == language
        sessions.append(opened)
    assert sessions[0]['session_id'] != sessions[1]['session_id']
    from pgadmin.cdeadmin.sdk.actual_engine import PilotProviderError
    with pytest.raises(PilotProviderError, match='language'):
        instance.execute(
            {
                'session_id': sessions[0]['session_id'],
                'language_profile': sessions[1]['language_profile'],
                'source': 'SELECT 1'})
    with pytest.raises(PilotProviderError, match='language'):
        instance.execute(
            {
                'session_id': sessions[0]['session_id'],
                'source': '{"language":"bogus","source":"SELECT 1"}'})


def test_running_and_unknown_scripts_reserve_session_until_confirmed_close():
    studio = Studio()
    scripts = ScriptCoordinator(studio)
    ctx = SimpleNamespace(endpoint_id='a')
    p = scripts.prepare(ctx, 'session', 'SELECT 1;')
    p = scripts.advance(ctx, p['plan_id'], 0)
    with pytest.raises(DataStudioAccessError, match='reserved'):
        scripts.check_execution('session')
    studio.outcome = 'unknown'
    p = scripts.advance(ctx, p['plan_id'], p['revision'])
    assert p['unresolved']
    with pytest.raises(DataStudioAccessError):
        scripts.discard(ctx, p['plan_id'])
    scripts.forget_closed_session('session')
    scripts.check_execution('session')


def test_design_references_are_registered_unique_and_reused():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'web/pgadmin'
    refs = json.loads(
        (root /
         'static/js/cdeadmin_ui/navigation/formReferences.json').read_text())['forms']
    assert len({v['reference'] for v in refs.values()}) == len(refs)
    assert refs['inspector']['reference'] == 'SR-F-000002'
    design = json.loads(
        (root / 'cdeadmin/visual_admin/navigation_design.json').read_text())

    def check(node):
        assert refs[node['form_key']]['reference'] == node['form_reference']
        for child in node['children']:
            check(child)
    for engine in design['engines'].values():
        check(engine['root'])


@pytest.mark.parametrize('language,source', [
    ('mysql-sql', '/*! SELECT 1; */'),
    ('postgresql-sql', "SELECT E'a\\\'b';"),
    ('postgresql-sql', 'SET standard_conforming_strings = off; SELECT 1;'),
    ('postgresql-sql', 'CREATE FUNCTION f() RETURNS int LANGUAGE SQL BEGIN ATOMIC SELECT 1; END;'),
    ('influxdb3-influxql', 'SELECT /a;b/ FROM t'),
])
def test_unadmitted_session_dependent_framing_cannot_run(language, source):
    assert not analyze(source, language, script=True)['script_ready']


def test_script_coordinator_runs_through_real_studio_and_blocks_interleaving(
        monkeypatch):
    from test_cdeadmin_data_studio import harness, endpoint_payload
    from pgadmin.cdeadmin.data_studio import scripts as module
    ctx, provider, registry, service = harness()
    service.open_session(ctx, endpoint_payload(ctx), 'example-sql')
    provider.script_statement_outcome = lambda observed: 'success' if observed[
        'operation']['terminal'] else 'pending'
    monkeypatch.setattr(module,
                        'analyze',
                        lambda source,
                        language,
                        **kwargs: analyze(source,
                                          'postgresql-sql',
                                          **kwargs))
    plan = service.scripts.prepare(ctx, 'session-one', 'SELECT 1; SELECT 2;')
    plan = service.scripts.advance(ctx, plan['plan_id'], plan['revision'])
    assert plan['state'] == 'waiting', plan
    with pytest.raises(DataStudioAccessError, match='reserved'):
        service.execute(ctx, 'session-one', 'SELECT 9')
    with pytest.raises(DataStudioAccessError, match='reserved'):
        service.control_transaction(ctx, 'session-one', 'commit')
    plan = service.scripts.advance(ctx, plan['plan_id'], plan['revision'])
    assert plan['state'] == 'ready', plan
    plan = service.scripts.advance(ctx, plan['plan_id'], plan['revision'])
    plan = service.scripts.advance(ctx, plan['plan_id'], plan['revision'])
    assert plan['state'] == 'complete', plan


def test_script_framing_and_outcomes_against_native_sqlite(tmp_path):
    from pgadmin.cdeadmin.providers.sqlite.provider import _create_client
    from test_sqlite_driver import execute, rows
    client = _create_client()
    try:
        handle = client.open_session({'route': {
            'database': str(tmp_path / 'script.sqlite'),
            'filesystem_root': str(tmp_path)}})
        source = ('CREATE TABLE events(id INTEGER); '
                  'CREATE TRIGGER once_only AFTER INSERT ON events '
                  'WHEN NEW.id = 1 BEGIN INSERT INTO events VALUES (2); END; '
                  'INSERT INTO events VALUES (1);')
        checked = analyze(source, 'sqlite-sql', script=True)
        assert checked['script_ready'], checked
        assert len(checked['statements']) == 3
        for statement in checked['statements']:
            pages = execute(client, handle, statement['source'])
            terminal = pages[-1]
            assert retained_outcome({
                'operation': {'terminal': True},
                'result': {'complete': terminal['complete'],
                           'extensions': {'sqlite': {'payload': terminal['payload']}}}
            }, 'sqlite') == 'success', terminal
        assert rows(execute(client, handle, 'SELECT id FROM events ORDER BY id')) == [[1], [2]]
        client.close_session(handle)
    finally:
        client.close()
