"""Binary XA identities, native resolution requests and ambiguous outcomes."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_xa as xa
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target, UUID


def draft(**changes):
    return {'gtrid_hex': '0027FF5C', 'bqual_hex': '', 'format_id': '9007199254740993',
        'decision_reference': 'Owned coordinator recovery decision', 'confirmation': 'MySQL', **changes}


def test_binary_identity_has_no_charset_or_sql_literal_escape_dependency():
    value = xa.compile_operation('commit_prepared_xa', draft(), target())
    assert value['statements'] == [{'source': "XA COMMIT X'0027FF5C',X'',9007199254740993", 'parameters': ()}]
    row = xa.decode_row((9007199254740993, 4, 0, b'0x0027ff5c'))
    assert row == value['mysql_xa']['xid']
    assert xa.identity(draft(gtrid_hex='ff'*64, bqual_hex='00'*64))['gtrid_length'] == 64


@pytest.mark.parametrize('changes', [
    {'gtrid_hex': "27';SHUTDOWN;--"}, {'gtrid_hex': 'a'}, {'gtrid_hex': '00'*65},
    {'bqual_hex': ' 00'}, {'bqual_hex': b'00'}, {'format_id': 1}, {'format_id': True},
    {'format_id': '-1'}, {'format_id': '01'}, {'format_id': str(2**63)},
    {'decision_reference': ''}, {'confirmation': 'other'}, {'lock_wait_seconds': True},
    {'extra_source': 'COMMIT'},
])
def test_untrusted_xa_parts_never_become_sql(changes):
    with pytest.raises(RelationalClientError): xa.compile_operation('commit_prepared_xa', draft(**changes), target())


@pytest.mark.parametrize('row', [(1, 2, 0, b'0x00'), (1, 1, 0, b'0xff\xff'),
    (1, True, 0, '0x00'), (1, 65, 0, '0x'+'00'*65), ('1', 0, 0, '0x'),
    (1, 1, 0, 'not hex'), (1, 1, 0, '0x0Z')])
def test_incomplete_or_corrupt_native_xid_is_not_a_resolvable_identity(row):
    with pytest.raises((RelationalClientError, UnicodeError)): xa.decode_row(row)


def test_xa_workflows_are_mysql_native_and_inspection_has_no_resolution_fields():
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    operations = {row['operation_id']: row for resource in catalog['objects']
        if resource['resource_kind'] == 'server' for row in resource['operations']}
    for operation in xa.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('server', operation)
        assert not MARIADB_ADMINISTRATION.supports('server', operation)
        assert operations[operation]['confirmation_required'] == (operation != 'inspect_prepared_xa')
    assert operations['inspect_prepared_xa']['form']['fields'] == []
    with pytest.raises(RelationalClientError): xa.compile_operation('inspect_prepared_xa', draft(), target())


def planned(operation='commit_prepared_xa'):
    compiled = xa.compile_operation(operation, {} if operation == 'inspect_prepared_xa' else draft(), target())
    compiled['mysql_xa']['review'] = {'execution_identity': {'server_uuid': UUID},
        'selected_prepared_xid': compiled['mysql_xa']['xid']}
    return {'provider_payload': {'route': {'host': 'owned'}, 'compiled': compiled}}


@pytest.mark.parametrize('outcome', ['ack', 'stale', 'post-ack-loss', 'no-reply', 'inspect-new-list'])
def test_xa_native_ack_is_separate_from_missing_branch_and_later_read_loss(monkeypatch, outcome):
    client = Mock(); cursor = client._connect.return_value.cursor.return_value
    monkeypatch.setattr(xa, 'environment', lambda _: {'server_uuid': UUID})
    calls = 0
    xid = xa.identity(draft())
    def observe(_):
        nonlocal calls
        calls += 1
        if calls == 2 and outcome == 'post-ack-loss': raise OSError('Owned read loss')
        return [] if outcome in {'stale', 'inspect-new-list'} or calls == 2 else [xid]
    monkeypatch.setattr(xa, 'observe', observe)
    if outcome == 'no-reply':
        def execute(source, *args):
            if source.startswith('XA COMMIT'): raise OSError('Owned missing reply')
        cursor.execute.side_effect = execute
    if outcome in {'stale', 'post-ack-loss', 'no-reply'}:
        with pytest.raises(RelationalClientError) as failure: xa.apply(client, planned())
        assert failure.value.native_dispatched == (outcome != 'stale')
        assert failure.value.native_acknowledged == (outcome == 'post-ack-loss')
        assert not failure.value.automatic_retry
    else:
        result = xa.apply(client, planned('inspect_prepared_xa' if outcome == 'inspect-new-list' else 'commit_prepared_xa'))
        assert result['xa_observation']['prepared_after'] == []
        assert not result['xa_observation']['global_transaction_decision_inferred']
        assert not result['transaction_finality_interpreted_by_common_code']
        assert result['commit_requested'] == (outcome == 'ack')
    client._forget_and_close.assert_called_once()


def test_forged_native_statement_and_borrowed_session_are_refused_before_connect():
    client = Mock(); request = deepcopy(planned())
    request['provider_payload']['compiled']['statements'][0]['source'] = 'SHUTDOWN'
    with pytest.raises(RelationalClientError): xa.apply(client, request)
    with pytest.raises(RelationalClientError): xa.apply(client, planned(), object())
    client._connect.assert_not_called()


def test_prepared_inventory_refuses_overflow_and_ambiguous_duplicate_native_identity(monkeypatch):
    cursor = Mock(); cursor.fetchmany.side_effect = [[(1, 1, 0, b'0x00')]*2, []]
    with pytest.raises(RelationalClientError, match='duplicate'): xa.observe(cursor)
    cursor.fetchmany.side_effect = [[(1, 1, 0, b'0x00')]*2, []]
    monkeypatch.setattr(xa, 'MAX_ROWS', 1)
    with pytest.raises(RelationalClientError, match='20,000'): xa.observe(cursor)


@pytest.mark.parametrize('warning_read_lost', [True, False])
def test_primary_native_recovery_error_survives_supplementary_condition_read(warning_read_lost):
    class Denied(Exception): errno = 1401; sqlstate = 'XAE03'
    error = Denied('Native XA failure'); cursor = Mock()
    cursor.execute.side_effect = [error, OSError('Owned warning read loss') if warning_read_lost else None]
    cursor.fetchall.return_value = [('Error', 1401, 'RMERR'), ('Error', 1227, 'XA_RECOVER_ADMIN')]
    with pytest.raises(Denied) as caught: xa.execute_recovery(cursor)
    assert caught.value is error
    value = xa.failure(error)
    assert value.errno == 1401 and value.sqlstate == 'XAE03'
    assert value.native_status_codes == ((1401,) if warning_read_lost else (1401, 1227))
    assert not value.native_dispatched and not value.automatic_retry


def test_native_diagnostic_read_does_not_refresh_charset_and_replace_error_area():
    class Denied(Exception): errno = 1401; sqlstate = 'XAE03'
    class Cursor:
        __module__ = 'mysql.connector.cursor_cext'
        def execute(self, source):
            assert source == b'SHOW WARNINGS LIMIT 16'
            self.preserved = True
        def fetchall(self):
            assert self.preserved
            return [('Error', 1401, 'RMERR'), ('Error', 1227, 'XA_RECOVER_ADMIN')]
    cursor = Cursor()
    def adapted(source):
        assert source == xa.RECOVER
        raise Denied()
    cursor.execute = adapted
    with pytest.raises(Denied) as caught: xa.execute_recovery(cursor)
    assert xa.failure(caught.value).native_status_codes == (1401, 1227)
