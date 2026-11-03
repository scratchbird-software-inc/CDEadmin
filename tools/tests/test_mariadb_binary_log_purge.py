"""MariaDB binary-log purge is accepted only when the native index confirms it."""
import pytest

from pgadmin.cdeadmin.providers.mysql_family.mariadb_binary_log_purge import purge
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

LOGS = ['mariadb-bin.000005', 'mariadb-bin.000006', 'mariadb-bin.000007', 'mariadb-bin.000008']
REFUSED = ('Note', 1375, "Binary log 'mariadb-bin.000005' is not purged because it is the current active binlog")


class Server:
    """Answers SHOW BINARY LOGS before and after the purge, and its notes."""

    def __init__(self, after, warnings=()):
        self.logs, self.after, self.warnings = list(LOGS), list(after), list(warnings)
        self.executed, self.closed, self.rows = [], False, []

    def cursor(self):
        return self

    def execute(self, source):
        self.executed.append(source)
        if source == 'SHOW BINARY LOGS':
            self.rows = [(name, 367) for name in self.logs]
        elif source == 'SHOW WARNINGS':
            self.rows = self.warnings
        else:
            self.logs, self.rows = self.after, []

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.closed = True


def test_purge_is_accepted_when_every_earlier_log_is_gone():
    server = Server(LOGS[2:])
    observed = purge(server, {'to_file': LOGS[2]})
    assert server.executed == ['SHOW BINARY LOGS', "PURGE BINARY LOGS TO 'mariadb-bin.000007'",
                               'SHOW WARNINGS', 'SHOW BINARY LOGS']
    assert observed['purged_names'] == LOGS[:2] and observed['retained_names'] == []
    assert observed['native_index_verified'] is True and server.closed


@pytest.mark.parametrize('after, warnings, message', [
    (LOGS, [REFUSED], 'MariaDB kept 2 of 2 binary logs before mariadb-bin.000007, starting with '
                      'mariadb-bin.000005; native note code 1375'),
    (LOGS[1:], [], 'MariaDB kept 1 of 2 binary logs before mariadb-bin.000007, starting with mariadb-bin.000006'),
    (LOGS[3:], [], 'MariaDB kept 0 of 2 binary logs before mariadb-bin.000007, starting with mariadb-bin.000007'),
])
def test_purge_the_native_index_does_not_confirm_is_refused(after, warnings, message):
    # The statement itself succeeds; only the index read-back shows what stayed.
    server = Server(after, warnings)
    with pytest.raises(RelationalClientError) as raised:
        purge(server, {'to_file': LOGS[2]})
    assert str(raised.value) == message
    assert 'not purged because' not in str(raised.value) and server.closed


@pytest.mark.parametrize('options', [{'to_file': "x'; DROP"}, {'to_file': ''}, {'to_file': LOGS[2], 'extra': 1},
                                     {}, None, {'to_file': 'mariadb-bin.000099'}])
def test_purge_without_an_exact_indexed_boundary_runs_nothing(options):
    server = Server(LOGS[2:])
    with pytest.raises(RelationalClientError):
        purge(server, options)
    assert not any(source.startswith('PURGE') for source in server.executed)


def test_purge_plan_previews_the_statement_and_dispatches_through_the_provider():
    log = {'resource_kind': 'binary-log', 'resource_id': 'binary-log:Binary logs:mariadb-bin.000007',
           'display_name': 'mariadb-bin.000007', 'display_path': ['Binary logs', 'mariadb-bin.000007']}
    compiled = MARIADB_ADMINISTRATION._compile({'resource_kind': 'binary-log', 'operation_id': 'purge_before',
                                                'target_resource': log, 'draft': {'confirmation': log['display_name']}})
    assert compiled['driver_operation'] == 'mariadb-tools'
    assert (compiled['operation_id'], compiled['options']) == ('purge_binary_logs', {'to_file': 'mariadb-bin.000007'})
    assert [item['source'] for item in compiled['statements']] == ["PURGE BINARY LOGS TO 'mariadb-bin.000007'"]
