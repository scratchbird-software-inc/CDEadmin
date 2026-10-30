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


TARGET_POLICY = {
    'resource_id': 'placement-policy:p', 'resource_kind': 'placement-policy',
    'display_name': 'p', 'display_path': ['p'],
    'authority_path': ['placement-policy', 'p'],
    'native': {'followers': 2, 'voters': 3, 'constraints': '[+disk=ssd]',
               'learners': 0, 'survival_preferences': '[region]'}}


def compiled(planned):
    return planned['provider_payload']['compiled']['statements'][0]


def test_placement_alter_carries_unedited_options_forward():
    statement = compiled(ADMINISTRATION.plan({
        'resource_kind': 'placement-policy', 'operation_id': 'alter',
        'target_resource': TARGET_POLICY,
        '_provider_route': {'database': 'd1'},
        'draft': {'placement_style': 'constraints', 'followers': 1}}))
    assert statement['source'] == (
        'ALTER PLACEMENT POLICY `p` FOLLOWERS = %s VOTERS = %s '
        'CONSTRAINTS = %s SURVIVAL_PREFERENCES = %s')
    assert tuple(statement['parameters']) == (
        1, 3, '[+disk=ssd]', '[region]')


def test_placement_styles_do_not_mix():
    with pytest.raises(RelationalClientError, match='placement style'):
        plan('placement-policy', 'create', {
            'name': 'p', 'schedule': 'even', 'constraints': '[+disk=ssd]'})
    with pytest.raises(RelationalClientError, match='learner replica'):
        plan('placement-policy', 'create', {
            'name': 'p', 'placement_style': 'constraints',
            'learner_constraints': '[+disk=ssd]'})


def test_runaway_query_limit():
    statement = compiled(plan('resource-group', 'create', {
        'name': 'g', 'ru_mode': 'limited', 'ru_per_sec': 10,
        'priority': 'LOW', 'query_limit_action': 'KILL',
        'query_limit_exec_elapsed': '1m30s'}))
    assert statement['source'].endswith(
        'QUERY_LIMIT = (EXEC_ELAPSED = %s, ACTION = KILL)')
    with pytest.raises(RelationalClientError, match='execution time'):
        plan('resource-group', 'create', {
            'name': 'g', 'ru_mode': 'unlimited', 'priority': 'LOW',
            'query_limit_action': 'KILL'})


@pytest.mark.parametrize('definitions', [
    'PARTITION p9 VALUES LESS THAN (9); DROP TABLE x',
    'p9 VALUES LESS THAN (9)',
    'PARTITION p9 VALUES LESS THAN (9',
])
def test_partition_definitions_stay_one_clause(definitions):
    target = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
              'display_name': 't', 'display_path': ['d1', 't'],
              'authority_path': ['d1', 'table', 't']}
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.plan({
            'resource_kind': 'table', 'operation_id': 'add_partitions',
            'target_resource': target,
            '_provider_route': {'database': 'd1'},
            'draft': {'definitions': definitions}})


def test_location_labels_accept_text_or_list():
    target = {'resource_id': 'table:d1:t', 'resource_kind': 'table',
              'display_name': 't', 'display_path': ['d1', 't'],
              'authority_path': ['d1', 'table', 't']}
    statement = compiled(ADMINISTRATION.plan({
        'resource_kind': 'table', 'operation_id': 'set_tiflash_replica',
        'target_resource': target, '_provider_route': {'database': 'd1'},
        'draft': {'replica_count': 2, 'location_labels': 'zone, rack'}}))
    assert tuple(statement['parameters']) == (2, 'zone', 'rack')
