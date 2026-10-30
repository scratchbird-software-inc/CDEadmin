"""Dolt administration planning added for MySQL-wire parity (2026-10-29)."""
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

from pgadmin.cdeadmin.providers.dolt.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

DATABASE_TARGET = {
    'resource_id': 'database:d1', 'resource_kind': 'database',
    'display_name': 'd1', 'display_path': ['d1'],
    'authority_path': ['database', 'd1']}


def request(kind, operation, draft, target=None):
    return {'resource_kind': kind, 'operation_id': operation,
            'target_resource': target, '_provider_route': {'database': 'd1'},
            'draft': draft}


def plan(*args, **kwargs):
    return [statement['source'] for statement in ADMINISTRATION.plan(
        request(*args, **kwargs))['command_preview']['statements']]


TRIGGER = {'name': 't6', 'parent': 'd1', 'table': 't', 'timing': 'BEFORE',
           'events': ['INSERT'], 'body': 'SET NEW.v = 3'}


def test_trigger_ordering():
    assert plan('trigger', 'create', {
        **TRIGGER, 'order': 'FOLLOWS', 'other_trigger': 't5'}) == [
        'CREATE TRIGGER `d1`.`t6` BEFORE INSERT ON `t` FOR EACH ROW '
        'FOLLOWS `t5` SET NEW.v = 3']
    with pytest.raises(RelationalClientError, match='needs the trigger'):
        plan('trigger', 'create', {**TRIGGER, 'order': 'PRECEDES'})
    with pytest.raises(RelationalClientError, match='select FOLLOWS'):
        plan('trigger', 'create', {**TRIGGER, 'other_trigger': 't5'})


def test_database_character_set_and_collation():
    assert plan('database', 'create', {
        'name': 'd1', 'character_set': 'utf8mb4',
        'collation': 'utf8mb4_bin'}) == [
        'CREATE DATABASE `d1` DEFAULT CHARACTER SET `utf8mb4` '
        'DEFAULT COLLATE `utf8mb4_bin`']
    assert plan('database', 'alter', {'collation': 'utf8mb4_bin'},
                DATABASE_TARGET) == [
        'ALTER DATABASE `d1` DEFAULT COLLATE `utf8mb4_bin`']
    # MySQL's DEFAULT ENCRYPTION is not claimed for Dolt.
    assert ADMINISTRATION.validate(request(
        'database', 'create', {'name': 'd2', 'encryption': 'Y'}))['errors']


@pytest.mark.parametrize('object_type', ['FUNCTION', 'SEQUENCE'])
def test_grants_only_on_objects_dolt_has(object_type):
    with pytest.raises(RelationalClientError, match='cannot grant'):
        plan('privilege', 'grant', {
            'principal': 'u@%', 'object_type': object_type,
            'object_name': 'd1.x', 'privileges': ['EXECUTE']})
