"""TiDB administration rules added for MySQL-wire parity (2026-10-29)."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.tidb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402


def request(kind, operation, draft):
    return {'resource_kind': kind, 'operation_id': operation,
            'target_resource': None, '_provider_route': {'database': 'd1'},
            'draft': draft}


def plan(*args):
    return ADMINISTRATION.plan(request(*args))


def test_database_character_set_and_collation():
    assert [statement['source'] for statement in plan(
        'database', 'create', {'name': 'd1', 'character_set': 'utf8mb4',
                               'collation': 'utf8mb4_bin'})[
        'command_preview']['statements']] == [
        'CREATE DATABASE `d1` DEFAULT CHARACTER SET `utf8mb4` '
        'DEFAULT COLLATE `utf8mb4_bin`']


def test_grants_on_sequences_but_not_routines():
    assert plan('privilege', 'grant', {
        'principal': 'u@%', 'object_type': 'SEQUENCE', 'object_name': 'd1.s',
        'privileges': ['SELECT']})['command_preview']['statements']
    with pytest.raises(RelationalClientError, match='cannot grant'):
        plan('privilege', 'grant', {
            'principal': 'u@%', 'object_type': 'PROCEDURE',
            'object_name': 'd1.p', 'privileges': ['EXECUTE']})


class Connection:
    def __init__(self, enabled):
        self.enabled, self.closed = enabled, False

    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, source):
                assert 'tidb_enable_check_constraint' in source

            def fetchone(self):
                return ('1' if connection.enabled else '0',)

            def close(self):
                pass
        return Cursor()


def test_check_constraints_are_refused_while_tidb_would_drop_them():
    planned = plan('table', 'create', {
        'name': 't', 'parent': 'd1',
        'columns': [{'name': 'v', 'type': 'INT'}],
        'constraints': [{'kind': 'CHECK', 'name': 'ck',
                         'expression': 'v > 0'}]})
    client = SimpleNamespace(_forget_and_close=lambda _connection: None)
    with pytest.raises(RelationalClientError,
                       match='tidb_enable_check_constraint'):
        ADMINISTRATION.apply(client, planned, connection=Connection(False))
