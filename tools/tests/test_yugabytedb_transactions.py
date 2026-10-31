"""YugabyteDB DDL that refuses a transaction block runs outside one."""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.yugabytedb import ddl_mode  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ROUTE = {'host': '127.0.0.1', 'database': 'yugabyte'}


def compiled(kind, operation, draft, target=None, route=ROUTE):
    return ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target, '_provider_route': route,
    })['provider_payload']['compiled']


@pytest.mark.parametrize('kind, draft', [
    ('database', {'name': 'd'}),
    ('tablespace', {'name': 'ts', 'num_replicas': 1, 'placement_blocks': [
        {'cloud': 'c', 'region': 'r', 'zone': 'z', 'min_num_replicas': 1}]}),
])
def test_database_and_tablespace_create_run_outside_a_transaction(
        kind, draft):
    assert compiled(kind, 'create', draft)[
        'statements_outside_transaction'] is True


def test_other_ddl_stays_in_the_transaction():
    assert 'statements_outside_transaction' not in compiled(
        'schema', 'create', {'name': 's'})


class Connection:
    autocommit = False

    def cursor(self):
        raise AssertionError('not reached')


def test_a_borrowed_connection_is_refused():
    planned = ADMINISTRATION.plan({
        'resource_kind': 'database', 'operation_id': 'create',
        'draft': {'name': 'd'}, '_provider_route': ROUTE})
    with pytest.raises(RelationalClientError, match='owned connection'):
        ADMINISTRATION.apply(object(), {
            'plan': {'resource_kind': 'database', 'operation_id': 'create'},
            'provider_payload': planned['provider_payload']},
            connection=Connection())


def test_multi_statement_ddl_plans_warn_they_are_not_atomic():
    """Live, 2025.2.2.2: DDL commits on its own inside a transaction."""
    many = compiled('sequence', 'create', {'name': 's', 'comment': 'c'})
    assert any('yb_ddl_transaction_block_enabled' in warning
               for warning in many['warnings'])
    assert not compiled('sequence', 'create', {'name': 's'}).get('warnings')


class _Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, source, parameters=()):
        if self.row is None:
            raise RuntimeError('no such setting')

    def fetchall(self):
        return [self.row]

    @property
    def connection(self):
        return self


@pytest.mark.parametrize('row, expected', [
    (('on', 'off', 'read committed'), ddl_mode.ATOMIC),
    (('on', 'on', 'serializable'), ddl_mode.ATOMIC),
    # The read-committed fallback flag turns it back off for RC sessions.
    (('on', 'on', 'read committed'), ddl_mode.PER_STATEMENT),
    (('off', 'off', 'read committed'), ddl_mode.PER_STATEMENT),
    # An older release has no such setting: DDL commits on its own.
    ((None, None, 'read committed'), ddl_mode.PER_STATEMENT),
])
def test_ddl_mode_from_settings(row, expected):
    assert ddl_mode.mode(_Cursor(row)) == expected


def test_plan_follows_the_servers_remembered_mode():
    route = {'host': '127.0.0.1', 'port': 55433, 'database': 'yugabyte'}
    draft = {'name': 's', 'comment': 'c'}
    try:
        ddl_mode.remember(route, ddl_mode.ATOMIC)
        atomic = compiled('sequence', 'create', draft, route=route)
        assert atomic['ddl_transaction_mode'] == ddl_mode.ATOMIC
        assert not atomic.get('warnings')
        ddl_mode.remember(route, ddl_mode.PER_STATEMENT)
        apart = compiled('sequence', 'create', draft, route=route)
        assert apart['warnings'] == [ddl_mode.PER_STATEMENT_WARNING]
    finally:
        ddl_mode._KNOWN.clear()


class _Connection:
    """Answers the DDL-mode probe, then fails a plan's second statement."""

    def __init__(self, setting, executed):
        self.setting, self.executed = setting, executed
        self.autocommit = False
        self.rowcount, self.description = -1, None

    def cursor(self):
        return self

    def execute(self, source, parameters=()):
        if source.startswith('SELECT current_setting'):
            self.description = True
            return
        self.description = None
        if 'absent' in source:
            raise RuntimeError('relation does not exist')
        self.executed.append(source)

    def fetchall(self):
        return [(self.setting, 'off', 'read committed')]

    def rollback(self):
        pass

    commit = rollback


class _Client:
    def __init__(self, setting):
        self.setting, self.executed = setting, []

    def _connect(self, request):
        return _Connection(self.setting, self.executed)

    def _safe_close(self, cursor):
        pass

    def _forget_and_close(self, connection):
        pass


@pytest.mark.parametrize('setting, says_stay_applied', [
    ('off', True), ('on', False)])
def test_apply_reports_what_a_failure_leaves(setting, says_stay_applied):
    request = {'resource_kind': 'sequence', 'operation_id': 'create',
               'target_resource': None, '_provider_route': ROUTE,
               'draft': {'name': 's', 'comment': 'c'}}
    planned = ADMINISTRATION.plan(request)
    planned['provider_payload']['compiled']['statements'][1]['source'] = (
        "COMMENT ON SEQUENCE absent IS 'x'")
    client = _Client(setting)
    try:
        with pytest.raises(RelationalClientError) as failure:
            ADMINISTRATION.apply(client, {
                'plan': {key: value for key, value in request.items()
                         if key != '_provider_route'},
                'provider_payload': planned['provider_payload']})
    finally:
        ddl_mode._KNOWN.clear()
    assert ('stay applied' in str(failure.value)) is says_stay_applied
    assert client.executed == ['CREATE SEQUENCE "s"']
