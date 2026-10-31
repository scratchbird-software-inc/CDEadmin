"""YugabyteDB YSQL placement tablespaces."""
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

from pgadmin.cdeadmin.providers.yugabytedb import tablespaces  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

BLOCK = {'cloud': 'c', 'region': 'r', 'zone': 'z', 'min_num_replicas': 1}
TARGET = {'resource_id': 'tablespace:s', 'display_name': 's',
          'display_path': ['s'], 'native': {'owner': 'o', 'comment': None}}


def compiled(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'tablespace', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return planned['provider_payload']['compiled']


def test_create():
    result = compiled('create', {
        'name': 's', 'owner': 'o', 'num_replicas': 3, 'comment': 'c',
        'placement_blocks': [
            {**BLOCK, 'leader_preference': 1, 'unknown': 1},
            {**BLOCK, 'zone': '*', 'leader_preference': 2,
             'min_num_replicas': 2}]})
    assert [item['source'] for item in result['statements']] == [
        'CREATE TABLESPACE "s" OWNER "o" WITH (replica_placement=\'{'
        '"num_replicas":3,"placement_blocks":[{"cloud":"c","region":"r",'
        '"zone":"z","min_num_replicas":1,"leader_preference":1},'
        '{"cloud":"c","region":"r","zone":"*","min_num_replicas":2,'
        '"leader_preference":2}]}\')',
        'COMMENT ON TABLESPACE "s" IS \'c\'']
    assert result['statements_outside_transaction'] is True


def test_alter_and_read_back():
    assert [item['source'] for item in compiled('alter', {
        'owner': 'p', 'comment': 'x'}, TARGET)['statements']] == [
        'ALTER TABLESPACE "s" OWNER TO "p"',
        'COMMENT ON TABLESPACE "s" IS \'x\'']
    assert tablespaces.from_options([
        'replica_placement={"num_replicas":1,"placement_blocks":[{"cloud":'
        '"c","region":"r","zone":"z","min_num_replicas":1}]}']) == (
        1, [{**BLOCK, 'leader_preference': None}])


@pytest.mark.parametrize('operation, draft, target, reason', [
    ('create', {'name': 's', 'num_replicas': 1, 'placement_blocks': [
        {**BLOCK, 'min_num_replicas': 2}]}, None, 'exceed the replicas'),
    ('create', {'name': 's', 'num_replicas': 2, 'placement_blocks': [
        {**BLOCK, 'leader_preference': 1},
        {**BLOCK, 'zone': 'y', 'leader_preference': 3}]}, None,
     'without gaps'),
    ('create', {'name': 's', 'num_replicas': 2, 'placement_blocks': [
        BLOCK, BLOCK]}, None, 'listed twice'),
    ('create', {'name': 's', 'num_replicas': 1, 'placement_blocks': [
        {**BLOCK, 'leader_preference': 0}]}, None, 'whole number from 1'),
    ('create', {'name': 's', 'num_replicas': 1, 'placement_blocks': []},
     None, 'at least one block'),
    ('alter', {'num_replicas': 3}, TARGET, 'does not alter'),
    ('alter', {'name': 't'}, TARGET, 'does not alter'),
])
def test_refusals(operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        compiled(operation, draft, target)
