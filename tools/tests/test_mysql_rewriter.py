"""Rewriter review integrity and native acknowledgement boundaries."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_rewriter as rewriter
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target, UUID


def draft(operation):
    value = {} if operation == 'inspect_rewrite_rules' else {'confirmation': 'MySQL'}
    if operation in {'alter_rewrite_rule', 'drop_rewrite_rule'}: value['rule_id'] = '-2147483648'
    if operation in {'create_rewrite_rule', 'alter_rewrite_rule'}:
        value.update(pattern='SELECT ? /* é */', pattern_database='', replacement="SELECT 'x; SHUTDOWN'", enabled='YES')
    if operation == 'reload_rewrite_rules': value['all_queries_affected'] = True
    return value


def observation():
    return {'plugin': ['Rewriter', '1.0', 'ACTIVE', 'rewriter.so'], 'reload_procedure_sha256': 'native-procedure',
            'rules': [dict(zip(rewriter.COLUMNS, [-2147483648, 'SELECT ?', None, 'SELECT 2', 'YES', None, 'digest', 'SELECT ?']))],
            'native_status': {'Rewriter_number_reloads': '1'}, 'in_memory_rules_enumerated': False, 'complete_stored_rules': True}


def request(operation):
    compiled = rewriter.compile_operation(operation, draft(operation), target())
    compiled['mysql_rewriter']['review'] = {'execution_identity': {'server_uuid': UUID},
        'binding': rewriter.binding(observation(), operation, compiled['mysql_rewriter']['rule_id'])}
    return {'provider_payload': {'route': {'host': 'owned'}, 'compiled': compiled}}


def test_editor_text_is_bound_as_native_data_and_not_executed_as_admin_sql():
    value = request('create_rewrite_rule')['provider_payload']['compiled']['statements'][0]
    assert "x; SHUTDOWN" not in value['source'] and 'SELECT' not in value['source']
    assert value['parameters'] == ('SELECT ? /* é */', None, "SELECT 'x; SHUTDOWN'", 'YES')
    for text in ('-2147483648', '0', '2147483647'):
        value = rewriter.compile_operation('drop_rewrite_rule', {'confirmation': 'MySQL', 'rule_id': text}, target())
        assert value['statements'][0]['parameters'] == (int(text),)


def test_native_null_and_empty_database_text_remain_distinct():
    values = draft('create_rewrite_rule')
    values['pattern_database_mode'] = 'VALUE'
    statement = rewriter.compile_operation('create_rewrite_rule', values, target())['statements'][0]
    assert statement['parameters'][1] == ''
    values['pattern_database_mode'] = 'NULL'
    assert rewriter.compile_operation('create_rewrite_rule', values, target())['statements'][0]['parameters'][1] is None


@pytest.mark.parametrize('text', ['2147483648', '-2147483649', '01', '1; DROP DATABASE mysql', True, 1])
def test_rule_identity_cannot_be_ambiguous_or_injected(text):
    with pytest.raises(RelationalClientError):
        rewriter.compile_operation('drop_rewrite_rule', {'confirmation': 'MySQL', 'rule_id': text}, target())


def test_actions_are_mysql_only_and_have_typed_reviewed_forms():
    server = next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects'] if row['resource_kind'] == 'server')
    actions = {row['operation_id']: row for row in server['operations']}
    for operation in rewriter.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('server', operation) and not MARIADB_ADMINISTRATION.supports('server', operation)
        assert actions[operation]['form']['form_id'] == 'mysql.server.' + operation
        assert actions[operation]['confirmation_required'] == (operation != 'inspect_rewrite_rules')
    with pytest.raises(RelationalClientError):
        rewriter.compile_operation('reload_rewrite_rules', {'confirmation': 'MySQL', 'all_queries_affected': 'true'}, target())


@pytest.mark.parametrize('outcome', ['changed-rule', 'changed-locked-row', 'commit-reply-lost', 'post-commit-observer-lost', 'ack'])
def test_commit_ack_is_separate_from_dml_and_later_observation(monkeypatch, outcome):
    client = Mock(); handle = client._connect.return_value; cursor = handle.cursor.return_value
    cursor.nextset.return_value = None; cursor.with_rows = False; cursor.warnings = []; cursor.fetchone.return_value = ('InnoDB',)
    cursor.fetchall.side_effect = [[], [list(observation()['rules'][0].values())] if outcome != 'changed-locked-row' else []]
    monkeypatch.setattr(rewriter, 'environment', lambda _: {'server_uuid': UUID})
    calls = 0
    def observe(_):
        nonlocal calls
        calls += 1
        if calls == 2 and outcome == 'post-commit-observer-lost': raise OSError('owned later loss')
        value = observation()
        if outcome == 'changed-rule': value['rules'][0]['pattern'] = 'changed'
        return value
    monkeypatch.setattr(rewriter, 'observe', observe)
    if outcome == 'commit-reply-lost': handle.commit.side_effect = OSError('owned missing commit reply')
    if outcome in {'changed-rule', 'changed-locked-row', 'commit-reply-lost'}:
        with pytest.raises(RelationalClientError) as failure: rewriter.apply(client, request('alter_rewrite_rule'))
        assert failure.value.native_dispatched == (outcome == 'commit-reply-lost')
        assert failure.value.native_acknowledged == (outcome == 'commit-reply-lost')
        assert not failure.value.native_commit_acknowledged and not failure.value.automatic_retry
    else:
        value = rewriter.apply(client, request('alter_rewrite_rule'))['rewriter_observation']
        assert value['native_acknowledged'] and value['native_commit_acknowledged'] and value['stored_table_only']
        assert not value['reload_requested'] and not value['query_rewrite_effectiveness_asserted']
        assert bool(value['later_observation_error']) == (outcome == 'post-commit-observer-lost')
    client._forget_and_close.assert_called_once_with(handle)


def test_failed_reload_can_already_have_changed_plugin_memory(monkeypatch):
    client = Mock(); cursor = client._connect.return_value.cursor.return_value
    monkeypatch.setattr(rewriter, 'environment', lambda _: {'server_uuid': UUID})
    monkeypatch.setattr(rewriter, 'observe', lambda _: observation())
    error = RuntimeError('native reload rejected some rules'); error.errno = 1644; error.sqlstate = '45000'
    cursor.execute.side_effect = [None, None, error]
    with pytest.raises(RelationalClientError) as failure: rewriter.apply(client, request('reload_rewrite_rules'))
    assert failure.value.errno == 1644 and failure.value.sqlstate == '45000'
    assert failure.value.native_dispatched and not failure.value.native_acknowledged and not failure.value.automatic_retry
    client._connect.return_value.commit.assert_not_called()


def test_forged_and_borrowed_operations_are_refused_without_opening_a_handle():
    client = Mock(); value = deepcopy(request('create_rewrite_rule'))
    value['provider_payload']['compiled']['statements'][0]['source'] = 'SHUTDOWN'
    with pytest.raises(RelationalClientError): rewriter.apply(client, value)
    with pytest.raises(RelationalClientError): rewriter.apply(client, request('create_rewrite_rule'), object())
    client._connect.assert_not_called()
