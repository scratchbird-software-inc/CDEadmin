"""Unit tests for general original-session MariaDB variable assignments."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.data_studio.studio import DataStudioAccessError, DataStudioService
from pgadmin.cdeadmin.providers.mysql_family.mariadb_session_variables import action
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MariaDBPilotProvider,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft


def _row(
    name='SORT_BUFFER_SIZE',
    scope='SESSION',
    variable_type='BIGINT UNSIGNED',
    minimum='1024',
    maximum='4294967295',
    *,
    read_only='NO',
    block='1',
    options=None,
    session_value='2097152',
    global_value='2097152',
    default_value='2097152',
):
    return (
        name, scope, variable_type, read_only, minimum, maximum, block,
        options, session_value, global_value, default_value,
    )


def test_requires_diagnostics_acknowledgement_before_opening_cursor():
    handle = Mock()
    with pytest.raises(RelationalClientError, match='diagnostics'):
        action(handle, {'operation': 'inspect', 'variable': 'sort_buffer_size'})
    handle.cursor.assert_not_called()


@pytest.mark.parametrize('bad_name', ['', '1bad', 'a;DROP', 'x' * 65, None, 42])
def test_rejects_invalid_variable_names_before_cursor(bad_name):
    handle = Mock()
    with pytest.raises(RelationalClientError):
        action(
            handle,
            {
                'operation': 'inspect',
                'variable': bad_name,
                'diagnostics_change_confirmed': True,
            },
        )
    handle.cursor.assert_not_called()


@pytest.mark.parametrize(
    'row,match',
    [
        (None, 'Unknown MariaDB system variable'),
        (_row(read_only='YES'), 'read-only'),
        (_row(scope='GLOBAL'), 'session scope'),
    ],
)
def test_refuses_unknown_readonly_and_global_only_variables(row, match):
    cursor = Mock()
    cursor.fetchone.return_value = row
    handle = SimpleNamespace(cursor=lambda: cursor)
    with pytest.raises(RelationalClientError, match=match):
        action(
            handle,
            {
                'operation': 'inspect',
                'variable': 'max_connections',
                'diagnostics_change_confirmed': True,
            },
        )


@pytest.mark.parametrize(
    'row,values,expected_sql,expected_params',
    [
        (
            _row('SORT_BUFFER_SIZE', 'SESSION', 'BIGINT UNSIGNED', '1024', '10000000', session_value='2048'),
            {'value_mode': 'VALUE', 'value': '4096'},
            'SET SESSION `sort_buffer_size` = 4096',
            [],
        ),
        (
            _row('PSEUDO_THREAD_ID', 'SESSION ONLY', 'INT UNSIGNED', '0', '4294967295', session_value='11'),
            {'value_mode': 'VALUE', 'value': '22'},
            'SET SESSION `pseudo_thread_id` = 22',
            [],
        ),
        (
            _row('LONG_QUERY_TIME', 'SESSION', 'DOUBLE', '0', '31536000', session_value='10.000000'),
            {'value_mode': 'VALUE', 'value': '2.5'},
            'SET SESSION `long_query_time` = 2.5',
            [],
        ),
        (
            _row('FOREIGN_KEY_CHECKS', 'SESSION', 'BOOLEAN', None, None, session_value='ON'),
            {'value_mode': 'VALUE', 'value': 'OFF'},
            'SET SESSION `foreign_key_checks` = 0',
            [],
        ),
        (
            _row(
                'SQL_MODE', 'SESSION', 'SET', None, None,
                options='STRICT_TRANS_TABLES,ANSI_QUOTES,ORACLE',
                session_value='STRICT_TRANS_TABLES',
            ),
            {'value_mode': 'VALUE', 'value': 'ansi_quotes,oracle'},
            'SET SESSION `sql_mode` = ?',
            ['ANSI_QUOTES,ORACLE'],
        ),
        (
            _row(
                'SQL_MODE', 'SESSION', 'SET', None, None,
                options='STRICT_TRANS_TABLES,ANSI_QUOTES',
                session_value='STRICT_TRANS_TABLES',
            ),
            {'value_mode': 'VALUE', 'value': ''},
            'SET SESSION `sql_mode` = ?',
            [''],
        ),
        (
            _row(
                'FORCE_SORT_LEAD', 'SESSION', 'ENUM', None, None,
                options='OFF,ON,FORCE',
                session_value='OFF',
            ),
            {'value_mode': 'VALUE', 'value': 'force'},
            'SET SESSION `force_sort_lead` = ?',
            ['FORCE'],
        ),
        (
            _row(
                'DEFAULT_MASTER_CONNECTION', 'SESSION ONLY', 'VARCHAR', None, None,
                session_value='',
            ),
            {'value_mode': 'VALUE', 'value': 'chan_1'},
            'SET SESSION `default_master_connection` = ?',
            ['chan_1'],
        ),
        (
            _row(
                'OPTIMIZER_SWITCH', 'SESSION', 'FLAGSET', None, None,
                options='index_merge,mrr,default',
                session_value='index_merge=on,mrr=off',
            ),
            {'value_mode': 'FLAGS', 'flags': [{'flag': 'mrr', 'state': 'on'}], 'reset_defaults': False},
            'SET SESSION `optimizer_switch` = ?',
            ['mrr=on'],
        ),
        (
            _row('SORT_BUFFER_SIZE', 'SESSION', 'BIGINT UNSIGNED', '1024', '10000000', session_value='2048'),
            {'value_mode': 'DEFAULT'},
            'SET SESSION `sort_buffer_size` = DEFAULT',
            [],
        ),
    ],
)
def test_review_and_apply_across_session_and_session_only_types(
    row, values, expected_sql, expected_params
):
    after_row = list(row)
    after_row[8] = '4096' if row[2] != 'FLAGSET' else 'index_merge=on,mrr=on'
    cursor = Mock()
    cursor.fetchone.side_effect = [row, row, tuple(after_row)]
    cursor.fetchall.return_value = [('Warning', 1292, 'truncated private detail')]
    handle = SimpleNamespace(cursor=lambda: cursor)

    reviewed = action(
        handle,
        {
            'operation': 'review',
            'variable': row[0],
            'diagnostics_change_confirmed': True,
            **values,
        },
    )
    assert reviewed['ready_to_apply'] is True
    assert reviewed['native_statement'] == expected_sql
    assert reviewed['bound_parameters'] == expected_params

    descriptor = engine_operations('mariadb')['set_session@system-variable']
    draft = operation_draft(
        descriptor,
        {
            'variable': row[0],
            **values,
            'expected_value': reviewed['expected_value'],
            'diagnostics_change_confirmed': True,
            'confirmed': True,
        },
    )
    applied = action(handle, {'operation': 'set_session', **draft})
    assert applied['outcome'] == 'native_acknowledged_with_readback'
    assert applied['commit_requested'] is False
    assert applied['rollback_requested'] is False
    assert applied['global_value_changed'] is False
    assert applied['native_diagnostics_preserved'] is False
    assert applied['native_warnings'] == [{'level': 'Warning', 'code': 1292}]
    assert 'truncated private detail' not in str(applied)


def test_stale_expected_value_refuses_before_set_session():
    row = _row(session_value='4096')
    cursor = Mock()
    cursor.fetchone.return_value = row
    handle = SimpleNamespace(cursor=lambda: cursor)
    with pytest.raises(RelationalClientError, match='changed'):
        action(
            handle,
            {
                'operation': 'set_session',
                'variable': 'sort_buffer_size',
                'diagnostics_change_confirmed': True,
                'value_mode': 'DEFAULT',
                'expected_value': '2048',
                'confirmed': True,
            },
        )
    assert cursor.execute.call_count == 1


def test_deterministic_native_privilege_refusal_keeps_session_usable():
    class NativeRefusal(Exception):
        errno = 1227
        sqlstate = '42000'

    row = _row('SQL_LOG_BIN', 'SESSION ONLY', 'BOOLEAN', None, None, session_value='ON')
    cursor = Mock()
    cursor.fetchone.return_value = row
    cursor.execute.side_effect = [None, NativeRefusal('Access denied')]
    handle = SimpleNamespace(cursor=lambda: cursor)
    client = SimpleNamespace(_uncertain_sessions=set(), _invalidate_editor_context=Mock(),
        _executions=SimpleNamespace(lock=threading.RLock(), closing=False, require_idle=Mock()),
        _connections=[handle], _require_usable_session=Mock())
    provider = SimpleNamespace(client=client, _require=Mock(), _editor_session=lambda _r: handle)

    with pytest.raises(RelationalClientError) as caught:
        MariaDBPilotProvider.native_session_variables_action(
            provider,
            {
                'session_id': 'owned',
                'language_profile': 'mariadb-sql',
                'operation': 'set_session',
                'variable': 'sql_log_bin',
                'diagnostics_change_confirmed': True,
                'value_mode': 'VALUE',
                'value': 'OFF',
                'expected_value': 'ON',
                'confirmed': True,
            },
        )
    assert caught.value.errno == 1227
    assert id(handle) not in client._uncertain_sessions


def test_transport_loss_marks_unknown_outcome_and_requires_session_close():
    class LostConnection(Exception):
        errno = 2013
        sqlstate = 'HY000'

    row = _row()
    cursor = Mock()
    cursor.fetchone.return_value = row
    cursor.execute.side_effect = [None, LostConnection('Lost connection')]
    handle = SimpleNamespace(cursor=lambda: cursor)
    client = SimpleNamespace(_uncertain_sessions=set(), _invalidate_editor_context=Mock(),
        _executions=SimpleNamespace(lock=threading.RLock(), closing=False, require_idle=Mock()),
        _connections=[handle], _require_usable_session=Mock())
    provider = SimpleNamespace(client=client, _require=Mock(), _editor_session=lambda _r: handle)
    session = SimpleNamespace(
        language_profile='mariadb-sql',
        provider_session={'session_id': 'private'},
        provider_isolation_key='owned',
    )
    context = SimpleNamespace(provider_id='org.cdeadmin.mariadb', isolation_key='owned')
    service = SimpleNamespace(
        scripts=SimpleNamespace(lock=threading.RLock(), check_execution=Mock()),
        _sessions={'public': session},
        _operational_session=lambda *_: (
            session,
            SimpleNamespace(
                instance=SimpleNamespace(
                    native_session_variables_action=lambda req: MariaDBPilotProvider.native_session_variables_action(provider, req)
                )
            ),
        ),
    )
    outcome = DataStudioService.mariadb_session_variables_action(
        service,
        context,
        'public',
        {
            'operation': 'set_session',
            'variable': 'sort_buffer_size',
            'diagnostics_change_confirmed': True,
            'value_mode': 'DEFAULT',
            'expected_value': '2097152',
            'confirmed': True,
        },
    )
    assert outcome['outcome'] == 'unknown_outcome'
    assert outcome['accepted'] is False
    assert outcome['close_session_required'] is True
    assert id(handle) in client._uncertain_sessions


def test_unknown_variable_and_forged_global_precheck_are_refused():
    empty_target = {
        'resource_kind': 'system-variable',
        'display_name': 'nonexistent_owned_var',
        'display_path': ['Configuration', 'nonexistent_owned_var'],
        'native': {},
    }
    errors = MARIADB_ADMINISTRATION.validate({
        'resource_kind': 'system-variable',
        'operation_id': 'set_global',
        'target_resource': empty_target,
        'draft': {'value_mode': 'DEFAULT'},
    })['errors']
    assert any(err['code'] == 'unknown_mariadb_system_variable' for err in errors)

    forged_target = {
        **empty_target,
        'native': {'read_only': 'NO', 'variable_scope': 'SESSION', 'variable_type': 'INT'},
    }
    planned = MARIADB_ADMINISTRATION.plan({
        'resource_kind': 'system-variable',
        'operation_id': 'set_global',
        'target_resource': forged_target,
        'draft': {'value_mode': 'VALUE', 'value': '10'},
        '_provider_route': {'host': '127.0.0.1'},
    })
    probe_cursor = Mock()
    probe_cursor.fetchone.return_value = None
    probe = SimpleNamespace(cursor=lambda: probe_cursor)
    fake_client = SimpleNamespace(
        module=SimpleNamespace(__name__='mariadb'),
        _connect=Mock(return_value=probe),
        _forget_and_close=Mock(),
    )
    with pytest.raises(RelationalClientError, match='Unknown MariaDB system variable') as exc:
        MARIADB_ADMINISTRATION.apply(fake_client, planned)
    assert exc.value.native_dispatched is False
    fake_client._forget_and_close.assert_called_once_with(probe)
