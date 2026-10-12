"""Native result boundaries, bounded buffers and protocol ownership."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_cdeadmin_relational_providers import MARIADB_PROFILE  # noqa
from pgadmin.cdeadmin.providers.mysql_family.mariadb_execution import (
    Executions,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from mariadb.constants import FIELD_TYPE as FieldType


def harness(sets):
    class Cursor:
        cdeadmin_exact_temporals = False
        metadata = {}

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
            return (value,)

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
        python_charset='utf8', ping=Mock())
    client = SimpleNamespace(_uncertain_sessions=set(),
                             _require_usable_session=Mock())
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


def test_cancel_verifies_winning_endpoint_before_native_kill():
    owner, connection, native = harness([list(range(4096))])
    connection.server_name = 'winning-host'
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
        'route': {'host': 'seed-host', 'port': 3306, 'reconnect': False,
                  'pool_size': 2, 'pool_validation_interval': 500,
                  'ssl_verify_cert': True}})
    deadline = time.monotonic() + 3
    while not token.pages.full() and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(RelationalClientError, match='cancellation failed'):
        owner.cancel(token)
    assert observed == {'host': 'winning-host', 'port': 3307,
                        'unix_socket': None, 'ssl_verify_cert': True}
    control_cursor.execute.assert_called_once_with('SELECT @@server_uid')
    assert token.cancelled is False
    assert len([r for p in drain(owner, token)
                for r in p['payload']['rows']]) == 4096


def test_shutdown_keeps_live_worker_ownership_and_blocks_new_work():
    owner, connection, _native = harness([[1]])
    unfinished = SimpleNamespace(
        finished=SimpleNamespace(is_set=lambda: False), worker=Mock())
    owner.tokens.append(unfinished)
    owner.cancel = Mock(return_value=True)
    with pytest.raises(RelationalClientError, match='still owns'):
        owner.close()
    assert unfinished in owner.tokens
    with pytest.raises(RelationalClientError, match='closing'):
        owner.execute(connection, {'source': 'SELECT 1'}, {})
