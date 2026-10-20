"""Native script boundaries must be known before any SQL dispatch."""
import pytest

from tools.tests.test_firebird_async_queries import rig  # noqa: F401

from pgadmin.cdeadmin.providers.firebird.scripts import parse
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def test_psql_delimiters_comments_quotes_and_source_locations():
    source = '''-- heading
SET TERM ^ ;
CREATE PROCEDURE "a;" RETURNS (V VARCHAR(40)) AS
BEGIN
 V = q'{a; ^ ' literal}';
 V = 'x'';^'; /* ; ^ */
 SUSPEND;
END^
SET TERM ; ^
SELECT * FROM "a;";
'''
    entries = parse(source)
    assert [step.kind for step in entries] == [
        'terminator', 'sql', 'terminator', 'sql']
    assert [step.line for step in entries] == [2, 3, 9, 10]
    assert entries[1].source.strip().startswith('CREATE PROCEDURE')
    assert entries[1].source.rstrip().endswith('END')
    assert entries[0].value == '^'
    assert entries[2].value == ';'


@pytest.mark.parametrize('literal', [
    "'a'';b'", "q'{; '' }'", "Q'[; -- /* ]'", "q'(;)'", "q'<;>'",
    "q'!;!'", '"a;""b"',
])
def test_quoted_terminators_are_not_statements(literal):
    entries = parse(f'SELECT {literal} FROM RDB$DATABASE; SELECT 2;')
    assert len(entries) == 2
    assert literal in entries[0].source


def test_native_directives_and_transaction_statements_remain_distinct():
    entries = parse('''SET SQL DIALECT 1; SET AUTO OFF; SET BAIL ON;
SET TRANSACTION READ ONLY READ COMMITTED;
COMMIT WORK RETAIN SNAPSHOT; ROLLBACK TO SAVEPOINT A;
SET TIME ZONE 'UTC';''')
    assert [step.kind for step in entries] == [
        'dialect', 'autoddl', 'bail', 'sql', 'sql', 'sql', 'sql']
    assert [step.value for step in entries[:3]] == [1, False, True]


@pytest.mark.parametrize('ending', [
    "SELECT 'open;", 'SELECT "open;', 'SELECT q\'{open;',
    '/* open', 'SELECT 2', 'SET TERM a b;',
    "SET SQL DIALECT 4;", 'SET BAIL;', 'SET AUTODDL yes;',
    'SET TERM /;', 'SET TERM --x;', 'SET TERM 界;', 'SET TERM /^;',
])
def test_invalid_late_entry_rejects_preflight_without_source_echo(ending):
    with pytest.raises(RelationalClientError) as failure:
        parse("INSERT INTO SECRET_DATA VALUES ('private');\n" + ending)
    assert 'private' not in str(failure.value)
    assert 'SECRET_DATA' not in str(failure.value)


@pytest.mark.parametrize('command', [
    "CONNECT 'private-host' USER 'private-user' PASSWORD 'private-secret'",
    "INPUT '/private/file.sql'", 'IN script.sql', 'OUT file.txt',
    'SHELL private-command', 'CREATE DATABASE private-name', 'DROP DATABASE',
    'EXIT', 'QUIT', 'SHOW TABLES', 'SET NAMES UTF8', 'SET PLAN ON',
])
def test_client_commands_require_explicit_corresponding_workflows(command):
    with pytest.raises(RelationalClientError, match='workspace') as failure:
        parse('SELECT 1;\n' + command + ';')
    assert 'private' not in str(failure.value)


def test_multi_character_delimiter_reset_and_comment_only_tail():
    entries = parse('SET TERM !! ;SELECT 1!!SET TERM!!; /* tail */ -- tail')
    assert [entry.kind for entry in entries] == [
        'terminator', 'sql', 'terminator']
    assert entries[-1].value == ';'


@pytest.mark.parametrize('source', [None, '', '-- comment', '\0', '\ud800',
                                    'x' * (1024 * 1024 + 1),
                                    'é' * (512 * 1024 + 1),
                                    'SELECT 1;' * 1001])
def test_preflight_application_bounds(source):
    with pytest.raises(RelationalClientError):
        parse(source)


def submit_script(rig, source):
    rig.handle.sql_dialect = 3
    return rig.client.submit_query(rig.handle, {
        'source': source, 'parameters': [],
        'output_policy': {'firebird_script': True, 'client_sql_dialect': 3}})


def finish_script(rig, query):
    query.worker.join(5)
    assert not query.worker.is_alive()
    return rig.client.describe_result(query)['payload']


def test_async_script_has_independent_statement_results_without_finality(rig):
    rig.finish.set()
    result = finish_script(rig, submit_script(rig, 'SELECT 1; SELECT 2;'))
    assert result['execution_state'] == 'succeeded'
    entries = result['script']['entries']
    assert [item['state'] for item in entries] == ['succeeded', 'succeeded']
    assert [item['result']['payload']['rows'] for item in entries] == [
        [(42,)], [(42,)]]
    assert rig.cursor.execute.call_count == 2
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()
    assert rig.client._state(rig.handle).script_context is None


@pytest.mark.parametrize('bail', ['ON', 'OFF'])
def test_statement_failure_retains_partial_results_and_obeys_bail(rig, bail):
    rig.cursor.execute.side_effect = [None, ValueError('private-secret'), None]
    result = finish_script(rig, submit_script(
        rig, f'SET BAIL {bail}; SELECT 1; SELECT 2; SELECT 3;'))
    assert result['execution_state'] == 'failed'
    assert [item['state'] for item in result['script']['entries']] == [
        'succeeded', 'succeeded', 'failed',
        'not_run' if bail == 'ON' else 'succeeded']
    assert 'private-secret' not in str(result)
    assert result['script']['stopped_before_end'] == (bail == 'ON')
    rig.handle.commit.assert_not_called()
    rig.handle.rollback.assert_not_called()


def test_script_cancel_does_not_dispatch_the_next_statement(rig):
    query = submit_script(rig, 'SELECT 1; INSERT INTO T VALUES (2);')
    assert rig.entered.wait(2)
    assert rig.client.cancel(query)
    rig.finish.set()
    result = finish_script(rig, query)
    assert result['execution_state'] == 'cancelled'
    assert [item['state'] for item in result['script']['entries']] == [
        'succeeded', 'not_run']
    assert rig.cursor.execute.call_count == 1
    rig.handle.rollback.assert_not_called()


def test_late_client_command_fails_before_any_native_submission(rig):
    with pytest.raises(RelationalClientError, match='workspace'):
        submit_script(rig, 'INSERT INTO T VALUES (1); SHELL private-command;')
    assert rig.client._queries == []
    rig.cursor.execute.assert_not_called()


def test_shared_script_budget_stops_later_dispatch_even_with_bail_off(
        rig, monkeypatch):
    from pgadmin.cdeadmin.providers.firebird import materialized_budget
    monkeypatch.setattr(materialized_budget, 'MAX_CHARGE', 10000)
    rig.finish.set()
    result = finish_script(rig, submit_script(
        rig, 'SET BAIL OFF; SELECT 1; SELECT 2; SELECT 3;'))
    assert [item['state'] for item in result['script']['entries']] == [
        'succeeded', 'succeeded', 'failed', 'not_run']
    assert rig.cursor.execute.call_count == 1
    rig.handle.commit.assert_not_called()


def test_preview_contains_positions_not_source_or_native_preparation():
    from pgadmin.cdeadmin.providers.firebird.scripts import preview
    import hashlib
    source = "SET BAIL OFF; SELECT 'private-canary' FROM RDB$DATABASE;"
    result = preview(source)
    assert result['source_sha256'] == hashlib.sha256(
        source.encode()).hexdigest()
    assert result['total_entries'] == 2
    assert result['entries'][0]['value'] is False
    assert result['native_work_requested'] is False
    assert 'private-canary' not in str(result)


@pytest.mark.parametrize('setting', [
    'STAT', 'BLOB', 'WARNING', 'KEEP_TRAN', 'PER_TAB', 'WIRE'])
def test_native_abbreviated_client_controls_rejected_before_execution(setting):
    with pytest.raises(RelationalClientError, match='workspace control'):
        parse('INSERT INTO T VALUES (1); SET ' + setting + ' ON;')


def test_synchronous_channel_does_not_silently_ignore_script_mode(rig):
    with pytest.raises(RelationalClientError, match='asynchronous'):
        rig.client.execute(rig.handle, {
            'source': 'SELECT 1; SELECT 2;',
            'output_policy': {'firebird_script': True}})
    rig.cursor.execute.assert_not_called()


@pytest.mark.parametrize('failure', [KeyboardInterrupt, RuntimeError])
def test_interruption_and_native_cancel_stop_even_with_bail_off(rig, failure):
    error = failure('private-canary')
    if failure is RuntimeError:
        error.gds_codes = (335544794,)
    rig.cursor.execute.side_effect = error
    result = finish_script(rig, submit_script(
        rig, 'SET BAIL OFF; SELECT 1; INSERT INTO T VALUES (2);'))
    assert result['script']['entries'][-1]['state'] == 'not_run'
    assert rig.client._state(rig.handle).script_context is None
    assert rig.cursor.execute.call_count == 1
    assert 'private-canary' not in str(result)
    assert result['execution_state'] == (
        'failed' if failure is KeyboardInterrupt else 'cancelled')
    if failure is KeyboardInterrupt:
        assert result['session_reuse_blocked'] is True
        assert result['session_reuse_blocked_reason'] == 'worker_interrupted'


def test_preview_identifies_only_exact_finality_and_start_statements():
    from pgadmin.cdeadmin.providers.firebird.scripts import preview
    result = preview('COMMIT WORK RETAIN SNAPSHOT; ROLLBACK; '
                     'ROLLBACK TO SAVEPOINT A; SET TRANSACTION READ ONLY;')
    assert [item['transaction_action'] for item in result['entries']] == [
        'commit retaining', 'rollback', None, 'set transaction']


@pytest.mark.parametrize('provider_id', [
    'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'])
def test_script_preview_rejects_foreign_or_missing_sessions(provider_id):
    from dataclasses import replace
    from unittest.mock import Mock
    from tools.tests.test_cdeadmin_data_studio import (
        context, endpoint_payload, harness,
    )
    from pgadmin.cdeadmin.data_studio import DataStudioAccessError
    ctx, provider, _registry, service = harness()
    native_ctx = replace(ctx, provider_id=provider_id)
    service.open_session(native_ctx, endpoint_payload(native_ctx), 'example-sql')
    provider.preview_script = Mock(return_value={'total_entries': 1})
    service.preview_script(native_ctx, 'session-one', 'SELECT 1;')
    provider.preview_script.assert_called_once_with({
        'source': 'SELECT 1;', 'session_id': 'session-one'})
    with pytest.raises(DataStudioAccessError, match='another endpoint'):
        service.preview_script(context('other'), 'session-one', 'SELECT 1;')
    with pytest.raises(DataStudioAccessError, match='provider scope'):
        service.preview_script(ctx, 'session-one', 'SELECT 1;')
    with pytest.raises(DataStudioAccessError, match='unavailable'):
        service.preview_script(native_ctx, 'missing', 'SELECT 1;')
    provider.preview_script.assert_called_once()
