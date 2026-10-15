"""Administrative DDL cannot share an Explorer transaction or replay a commit."""
from unittest.mock import Mock, patch

import pytest

from test_cdeadmin_postgresql_provider import PostgreSQLProvider, FakeDriver, FakePermissions, endpoint

MODULE = 'pgadmin.cdeadmin.providers.postgresql.provider'


def setup():
    driver = FakeDriver()
    provider = PostgreSQLProvider(endpoint(), FakePermissions({'network', 'data_read', 'execute', 'administer'}), driver)
    driver.manager._connection.transaction_status = Mock(return_value=0)
    driver.manager._connection.execute_dict = Mock(return_value=(True, {'rows': [{'oid': 10}]}))
    plan = provider.plan_admin_operation({'resource_kind': 'operator-family', 'operation_id': 'create',
        'draft': {'schema': 'public', 'name': 'owned', 'index_method': 'btree'},
        '_provider_route': {'server_id': 7, 'database_id': 10}})
    return provider, driver, plan


def test_admin_owns_connection_and_observes_commit():
    provider, driver, plan = setup()
    with patch(MODULE + '.native_control', side_effect=lambda _, command: (True, command.strip(';'))) as control:
        result = provider.apply_admin_operation(plan)
    assert result['transaction_outcome'] == 'committed'
    assert result['release_status'] == 'confirmed'
    assert driver.manager.connection_calls[-1]['conn_id']
    assert driver.manager.connection_calls[-1]['auto_reconnect'] is False
    assert [call.args[1] for call in control.call_args_list] == ['BEGIN', 'SET LOCAL standard_conforming_strings = on', 'COMMIT', 'ROLLBACK;']
    assert not provider._sessions


def test_lost_commit_reply_releases_but_never_replays_or_claims_rollback():
    provider, driver, plan = setup()
    def native(_, command):
        if command == 'COMMIT':raise OSError('private detail')
        return True, command
    with patch(MODULE + '.native_control', side_effect=native) as control:
        with pytest.raises(RuntimeError, match='outcome is unknown; do not replay'):
            provider.apply_admin_operation(plan)
    assert [call.args[1] for call in control.call_args_list] == ['BEGIN', 'SET LOCAL standard_conforming_strings = on', 'COMMIT']
    assert len(driver.manager._connection.executions) == 1
    assert not provider._sessions and len(driver.manager.release_calls) == 1


def test_database_identity_drift_refuses_ddl():
    provider, driver, plan = setup()
    driver.manager._connection.execute_dict.return_value = True, {'rows': [{'oid': 11}]}
    with patch(MODULE + '.native_control', return_value=(True, 'ROLLBACK')):
        with pytest.raises(RuntimeError, match='identity changed'):
            provider.apply_admin_operation(plan)
    assert not driver.manager._connection.executions
    assert not provider._sessions


def test_release_failure_preserves_an_observed_commit_and_attachment_ownership():
    provider, driver, plan = setup()
    driver.manager.release = Mock(side_effect=OSError('private detail'))
    with patch(MODULE + '.native_control', side_effect=lambda _, command: (True, command.strip(';'))):
        result = provider.apply_admin_operation(plan)
    assert result['transaction_outcome'] == 'committed'
    assert result['release_status'] == 'unconfirmed'
    assert result['release_pending_session_id'] in provider._sessions


def test_modified_sql_is_not_dispatch_authority():
    provider, driver, plan = setup()
    plan['provider_payload']['statement'] = 'DROP DATABASE postgres'
    with pytest.raises(RuntimeError, match='statement changed'):
        provider.apply_admin_operation(plan)
    assert not driver.manager.connection_calls
