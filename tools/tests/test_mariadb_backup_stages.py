"""Native backup-stage admission cannot implicitly commit pending work."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mariadb_backup_stages as stages
from pgadmin.cdeadmin.sdk import RelationalClientError


def fixture():
    connection = Mock()
    row = ['native-server', 42, 'owner@localhost', 'owner@localhost', None,
        '12.2.2-MariaDB', 'STRICT_TRANS_TABLES', 0, 0]
    connection.cursor.return_value.fetchone.side_effect = lambda: tuple(row)
    token = SimpleNamespace(native_dispatched=True, native_acknowledged=True, cancelled=False)
    client = SimpleNamespace(_connections=[connection], _session_requests={id(connection): {}},
        _backup_stage_handles=set(), _backup_stage_reviews={},
        _executions=SimpleNamespace(lock=threading.RLock(), require_idle=Mock()),
        _require_usable_session=Mock(), execute=Mock(return_value=token), cancel=Mock(),
        describe_result=Mock(return_value={'complete':True, 'payload': {'error':None,'session_reuse_blocked':False}}))
    return client, connection, row, token


def review(client, connection):
    return stages.action(client, connection, {'operation':'review', 'draft':{'stage':'START','lock_wait_seconds':5}})


def apply(client, connection, record):
    return stages.action(client, connection, {'operation':'apply','review_id':record['review_id'],
        'review_digest':record['review_digest'],'confirmation':'START','confirmed':True})


@pytest.mark.parametrize('change', [{'stage':'START; DROP DATABASE existing'}, {'stage':'unknown'},
    {'lock_wait_seconds':True}, {'lock_wait_seconds':-1}, {'lock_wait_seconds':1.5},
    {'lock_wait_seconds':'5'}, {'lock_wait_seconds':stages.MAX_LOCK_WAIT+1}, {'source':'BACKUP STAGE START'}])
def test_only_native_stage_and_full_native_integer_timeout_are_admitted(change):
    with pytest.raises(ValueError):
        stages.compile_operation({'stage':'START','lock_wait_seconds':5,**change})
    assert '31536000' in stages.compile_operation({'stage':'END','lock_wait_seconds':stages.MAX_LOCK_WAIT})


def test_active_transaction_is_refused_before_review_and_before_dispatch():
    client, connection, row, _token = fixture()
    row[7] = 1
    with pytest.raises(RelationalClientError, match='implicitly commits'):
        review(client, connection)
    row[7] = 0
    record = review(client, connection)
    row[7] = 1
    with pytest.raises(RelationalClientError, match='active transaction'):
        apply(client, connection, record)
    client.execute.assert_not_called()
    assert not client._backup_stage_handles


@pytest.mark.parametrize('index,value', [(0,'replacement-server'),(1,43),(2,'different@localhost'),
    (4,'different_role'),(6,'ORACLE'),(8,1)])
def test_changed_native_connection_or_authority_retires_review_without_dispatch(index, value):
    client, connection, row, _token = fixture()
    record = review(client, connection)
    row[index] = value
    result = apply(client, connection, record)
    assert result['state']=='refused' and not result['native_dispatched']
    assert apply(client, connection, record)==result
    client.execute.assert_not_called()


def test_review_is_private_and_cannot_move_to_another_connection():
    client, connection, _row, _token = fixture()
    record = review(client, connection)
    assert not {'connection','token','baseline','deadline'} & set(record)
    json.dumps(record)
    with pytest.raises(ValueError, match='another or closed'):
        apply(client, Mock(), record)
    client.execute.assert_not_called()


@pytest.mark.parametrize('uncertain',[False, True])
def test_terminal_acknowledgement_or_unknown_receipt_never_replays(uncertain):
    client, connection, _row, token = fixture()
    record = review(client, connection)
    result = apply(client, connection, record)
    assert result['state']=='executing'
    token.native_acknowledged = not uncertain
    client.describe_result.return_value['payload']['session_reuse_blocked'] = uncertain
    result = apply(client, connection, record)
    assert result['state']==('unknown_outcome' if uncertain else 'acknowledged')
    assert apply(client, connection, record)==result
    assert id(connection) in client._backup_stage_handles
    client.execute.assert_called_once()
    client.describe_result.assert_called_once()


def test_expired_discarded_and_forged_requests_never_execute():
    client, connection, _row, _token = fixture()
    record = review(client, connection)
    client._backup_stage_reviews[record['review_id']]['deadline'] = 0
    with pytest.raises(ValueError, match='Confirm'):
        apply(client, connection, record)
    record = review(client, connection)
    discarded = stages.action(client, connection, {'operation':'discard','review_id':record['review_id'],
        'review_digest':record['review_digest']})
    assert apply(client, connection, record)==discarded
    with pytest.raises(ValueError, match='Unknown native'):
        stages.action(client, connection, {'operation':'inventory','source':'BACKUP STAGE START'})
    client.execute.assert_not_called()


def test_post_acknowledgement_connection_failure_preserves_acknowledgement():
    client, connection, _row, _token = fixture()
    record = review(client, connection)
    apply(client, connection, record)
    client.describe_result.return_value['payload']['session_reuse_blocked'] = True
    result = apply(client, connection, record)
    assert result['state']=='acknowledged' and result['native_acknowledged'] and result['session_reuse_blocked']
    assert apply(client, connection, record)==result
    client.execute.assert_called_once()


def test_application_backup_authority_is_required_before_native_session_access():
    from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider
    def require(permission,*_):
        if permission=='backup_admin':
            raise RelationalClientError('backup authority denied')
    permissions=SimpleNamespace(require=Mock(side_effect=require))
    provider=MariaDBPilotProvider(SimpleNamespace(endpoint_id='owned'),permissions,Mock())
    provider._editor_session=Mock()
    with pytest.raises(RelationalClientError,match='backup authority denied'):
        provider.backup_stage_action({'language_profile':'mariadb-sql','operation':'inventory'})
    permissions.require.assert_any_call('backup_admin','endpoint')
    provider._editor_session.assert_not_called()
