"""Native result boundaries, bounded buffers and protocol ownership."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_cdeadmin_relational_providers import MYSQL_PROFILE  # noqa
from pgadmin.cdeadmin.providers.mysql_family.mysql_execution import Executions
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.providers.mysql_family.mysql_values import MySQLParameterAdmissionError
from mysql.connector.constants import FieldType


def harness(sets):
    class Cursor:
        def __init__(self):
            self.index = 0
            self.offset = 0
            self.closed = False

        @property
        def description(self):
            return [(f'column_{self.index}', FieldType.LONG, None, None,
                     None, None, True, 0, 63)]

        @property
        def rowcount(self):
            return self.offset

        def execute(self, *args):
            pass

        def fetchone(self):
            rows = sets[self.index]
            if self.offset == len(rows):
                return None
            value = rows[self.offset]
            self.offset += 1
            return (str(value).encode(),)

        def nextset(self):
            if self.index + 1 == len(sets):
                return None
            self.index += 1
            self.offset = 0
            return True

        def close(self):
            self.closed = True

    native = Cursor()
    identity = Mock()
    identity.fetchone.return_value = ('server-one', 7)
    connection = SimpleNamespace(
        cursor=lambda **kw: native if kw else identity,
        python_charset='utf8', ping=Mock(), server_host='winning-endpoint',
        server_port=3306, unix_socket=None)
    control = Mock()
    control.cursor.return_value.fetchone.return_value = ('server-one',)
    client = SimpleNamespace(
        _uncertain_sessions=set(), _require_usable_session=Mock(),
        module=SimpleNamespace(connect=Mock()),
        _invoke_connector=Mock(return_value=control),
        _safe_close=lambda obj: obj.close() if obj is not None else None)
    return Executions(client), connection, native


def drain(executions, token):
    result = []
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        page = executions.describe(token)
        result.append(page)
        if page['complete']:
            return result
    raise AssertionError('worker did not terminate')


def test_multiple_results_keep_metadata_and_empty_set():
    owner, connection, native = harness([[1, 2], [], [3]])
    token = owner.execute(connection, {'source': 'native batch'}, {})
    pages = drain(owner, token)
    data = [p for p in pages if p['payload']['has_page']]
    assert [p['payload']['rows'] for p in data] == [[(1,), (2,)], [], [(3,)]]
    assert [p['schema']['columns'][0]['native_name'] for p in data] == [
        'column_0', 'column_1', 'column_2']
    assert [p['payload']['result_set_index'] for p in data] == [0, 1, 2]
    assert native.closed
    with pytest.raises(RelationalClientError):
        owner.describe(token)


def test_parameter_admission_failure_does_not_quarantine_or_replay_user_sql():
    owner, connection, native = harness([[1]])
    native.execute = Mock(side_effect=MySQLParameterAdmissionError('private input'))
    pages = drain(owner, owner.execute(connection, {'source':'native query'}, {}))
    assert pages[-1]['payload']['error'] == {
        'type':'MySQLParameterAdmissionError','query_dispatch':'not_started',
        'commands_dispatched':0}
    assert not pages[-1]['payload']['session_reuse_blocked']
    assert id(connection) not in owner.client._uncertain_sessions
    assert native.execute.call_count == 1 and native.closed
    connection.ping.assert_not_called()


def test_backpressure_blocks_native_fetch_and_second_execution():
    owner, connection, native = harness([list(range(4096))])
    token = owner.execute(connection, {'source': 'native rows'}, {})
    deadline = time.monotonic() + 3
    while not token.pages.full() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert token.pages.full()
    assert native.offset <= 3 * owner.PAGE_ROWS + 1
    assert not token.finished.is_set()
    with pytest.raises(RelationalClientError, match='active'):
        owner.execute(connection, {'source': 'another query'}, {})
    pages = drain(owner, token)
    assert [row[0] for p in pages for row in p['payload']['rows']] == list(
        range(4096))
    assert pages[-1]['complete']


def test_shutdown_releases_unconsumed_result_backpressure():
    owner, connection, native = harness([list(range(4096))])
    token = owner.execute(connection, {'source': 'native rows'}, {})
    deadline = time.monotonic() + 3
    while not token.pages.full() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert token.pages.full()
    owner.close()
    assert token.finished.is_set() and native.closed and not owner.tokens


def test_shutdown_during_identity_read_prevents_dispatch():
    import threading
    owner, connection, native = harness([[1]])
    entered, release = threading.Event(), threading.Event()
    identity = connection.cursor()
    def read_identity():
        entered.set(); release.wait(2)
        return ('server-one', 7)
    identity.fetchone.side_effect = read_identity
    native.execute = Mock()
    token = owner.execute(connection, {'source': 'native rows'}, {})
    assert entered.wait(1)
    timer = threading.Timer(0.05, release.set); timer.start()
    try: owner.close()
    finally: release.set(); timer.join()
    assert token.finished.is_set() and not owner.tokens
    native.execute.assert_not_called()


def test_late_error_keeps_earlier_result_and_protocol_failure_quarantines():
    owner, connection, native = harness([[1]])
    native.nextset = Mock(side_effect=RuntimeError('secret SQL text'))
    connection.ping.side_effect = OSError('wire unavailable')
    token = owner.execute(connection, {'source': 'native query'}, {})
    pages = drain(owner, token)
    assert [r for p in pages for r in p['payload']['rows']] == [(1,)]
    assert pages[-1]['payload']['error'] == {'type': 'RuntimeError'}
    assert pages[-1]['payload']['session_reuse_blocked'] is True
    assert id(connection) in owner.client._uncertain_sessions
    connection.ping.assert_not_called()


def test_c_driver_ok_then_rows_keeps_raw_values_and_later_server_error():
    from mysql.connector.errors import ProgrammingError
    owner, connection, native = harness([[], [1]])
    mode = {'raw': False}  # The preceding identity/catalog cursor used typed rows.
    connection._cmysql = SimpleNamespace(raw=lambda enabled: mode.update(raw=enabled))
    fetch = native.fetchone
    advance = native.nextset

    def fetchone():
        row = fetch()
        # The C connector's initial OK response leaves its previous conversion
        # mode intact, even though this query cursor was requested raw=True.
        return row if mode['raw'] or row is None else (int(row[0]),)

    def nextset():
        if native.index == 1:
            raise ProgrammingError(msg='Owned later statement failed', errno=1146, sqlstate='42S02')
        return advance()

    native.fetchone = fetchone
    native.nextset = nextset
    token = owner.execute(connection, {'source': 'INSERT; SELECT; failing SELECT'}, {})
    pages = drain(owner, token)
    assert [row for page in pages for row in page['payload']['rows']] == [(1,)]
    assert pages[-1]['payload']['error']['errno'] == 1146
    assert pages[-1]['payload']['session_reuse_blocked'] is False


def test_cancel_verifies_winning_endpoint_before_native_kill():
    owner, connection, native = harness([list(range(4096))])
    connection.server_host = 'winning-host'
    connection.server_port = 3307
    connection.unix_socket = None
    control_cursor = Mock()
    control_cursor.fetchone.return_value = ('different-server',)
    control = Mock()
    control.cursor.return_value = control_cursor
    owner.client.config = SimpleNamespace(
        connect_arguments=lambda route: route)
    owner.client.module = SimpleNamespace(connect=Mock())
    owner.client._safe_close = lambda obj: obj.close() if obj else None
    observed = {}

    def connect(request, connector, *, connect_arguments):
        observed.update(connect_arguments(request['route']))
        return control

    owner.client._invoke_connector = connect
    token = owner.execute(connection, {'source': 'native rows'}, {
        'route': {'host': 'seed-host', 'port': 3306, 'dns_srv': True,
                  'pool_size': 2, 'failover': [{'host': 'another'}],
                  'ssl_verify_identity': True}})
    deadline = time.monotonic() + 3
    while not token.pages.full() and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(RelationalClientError, match='cancellation failed'):
        owner.cancel(token)
    assert observed == {'host': 'winning-host', 'port': 3307,
                        'unix_socket': None, 'ssl_verify_identity': True}
    control_cursor.execute.assert_called_once_with('SELECT @@server_uuid')
    assert token.cancelled is False
    assert len([r for p in drain(owner, token)
                for r in p['payload']['rows']]) == 4096


def test_mysql_native_options_do_not_extend_mariadb_routes():
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        MARIADB_PROFILE, _route_arguments,
    )
    route = {'host': 'one', 'use_pure': False, 'allow_local_infile': False,
             'allow_local_infile_in_path': '/owned/imports'}
    assert _route_arguments(route, MYSQL_PROFILE) == route
    assert _route_arguments(route, MARIADB_PROFILE) == {'host': 'one'}
    with pytest.raises(RelationalClientError, match='boolean'):
        _route_arguments({'use_pure': 'false'}, MYSQL_PROFILE)


def test_mysql_profile_omits_removed_plugin_without_changing_wire_profiles():
    import json
    from pathlib import Path
    from pgadmin.cdeadmin.endpoints.field_sets import expand_field_sets
    from pgadmin.cdeadmin.endpoints.capability_sets import (
        expand_capability_set,
    )
    path = Path(__file__).resolve().parents[2] / (
        'web/pgadmin/cdeadmin/providers/mysql_family/'
        'mysql_provider_manifest.json')
    registration = json.loads(path.read_text())['registration']
    fields, _ = expand_field_sets(registration)
    auth = next(f for f in fields if f['field_id'] == 'auth_plugin')
    assert 'mysql_native_password' not in {o['value'] for o in auth['options']}
    caps = expand_capability_set(registration)['categories']
    assert 'native-password' not in caps['authentication']['features']
    assert 'provider-private-pool' in caps['pooling']['features']
    wire = expand_capability_set({
        'connection_capability_set': 'mysql-connector-python-v1'})
    native_auth = wire['categories']['authentication']['features']
    assert 'native-password' in native_auth
    from pgadmin.cdeadmin.providers.mysql_family.provider import (
        _route_arguments,
    )
    with pytest.raises(RelationalClientError, match='does not support'):
        _route_arguments(
            {'auth_plugin': 'mysql_native_password'}, MYSQL_PROFILE)


def test_native_error_text_excludes_local_connector_exceptions():
    from mysql.connector.errors import ProgrammingError, InterfaceError
    server = Executions._error(ProgrammingError(msg='Unknown column', errno=1054, sqlstate='42S22'))
    assert server['message_primary'] == 'Unknown column'
    local = Executions._error(InterfaceError(msg='private credential material', errno=2003))
    assert 'message_primary' not in local
    assert 'private' not in str(local)


def test_failed_native_dispatch_retains_timing_and_diagnostic_without_replay():
    from mysql.connector.errors import ProgrammingError
    owner, connection, native = harness([[1]])
    native.execute = Mock(side_effect=ProgrammingError(
        msg='Unknown column', errno=1054, sqlstate='42S22'))
    token = owner.execute(connection, {'source': 'SELECT missing_column'}, {})
    pages = drain(owner, token)
    payload = pages[-1]['payload']
    assert not any(p['payload']['has_page'] for p in pages)
    assert payload['error']['errno'] == 1054
    assert payload['error']['sqlstate'] == '42S22'
    assert payload['error']['message_primary'] == 'Unknown column'
    metrics = payload['statement_metrics']
    assert metrics['dispatch_ms'] >= 0
    assert metrics['prepare_ms'] is metrics['execute_ms'] is metrics['plan'] is None
    native.execute.assert_called_once()
    connection.ping.assert_called_once_with(reconnect=False)
    assert native.closed and not owner.client._uncertain_sessions
