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

from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ROUTE = {'host': '127.0.0.1', 'database': 'yugabyte'}


def compiled(kind, operation, draft, target=None):
    return ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target, '_provider_route': ROUTE,
    })['provider_payload']['compiled']


@pytest.mark.parametrize('kind, draft', [
    ('database', {'name': 'd'}),
    ('tablespace', {'name': 'ts', 'replica_placement': {
        'num_replicas': 1, 'placement_blocks': [
            {'cloud': 'c', 'region': 'r', 'zone': 'z',
             'min_num_replicas': 1}]}}),
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
