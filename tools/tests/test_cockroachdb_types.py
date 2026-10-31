"""CockroachDB enum and composite type compilation."""
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

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

ENUM = {'resource_id': 'type:public:s', 'display_name': 's',
        'display_path': ['public', 's'],
        'native': {'type_kind': 'ENUM', 'enum_values': ['a', 'b', 'c'],
                   'comment': None}}
COMPOSITE = {**ENUM, 'native': {'type_kind': 'COMPOSITE', 'fields': [
    {'name': 'x', 'type': 'bigint'}]}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'type', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create_enum_and_composite():
    assert plan('create', {'name': 's', 'parent': 'public',
                           'type_kind': 'ENUM', 'enum_values': ['a', "b'c"],
                           'comment': 'x'}) == [
        'CREATE TYPE "public"."s" AS ENUM (\'a\', \'b\'\'c\')',
        'COMMENT ON TYPE "public"."s" IS \'x\'']
    assert plan('create', {'name': 'p', 'type_kind': 'COMPOSITE',
                           'fields': [{'name': 'x', 'type': 'INT8'}]}) == [
        'CREATE TYPE "p" AS ("x" INT8)']


def test_enum_alter_renames_first_then_adds_in_place_and_drops():
    assert plan('alter', {
        'rename_values': [{'from': 'c', 'to': 'z'}],
        'enum_values': ['first', 'a', 'mid', 'z']}, ENUM) == [
        'ALTER TYPE "public"."s" RENAME VALUE \'c\' TO \'z\'',
        'ALTER TYPE "public"."s" ADD VALUE \'first\' BEFORE \'a\'',
        'ALTER TYPE "public"."s" ADD VALUE \'mid\' AFTER \'a\'',
        'ALTER TYPE "public"."s" DROP VALUE \'b\'']


@pytest.mark.parametrize('target, draft, reason', [
    (ENUM, {'enum_values': ['c', 'b', 'a']}, 'cannot reorder'),
    (ENUM, {'rename_values': [{'from': 'q', 'to': 'r'}]}, 'enum holds'),
    (ENUM, {'rename_values': [{'from': 'a', 'to': 'b'}]}, 'already has'),
    (ENUM, {'enum_values': ['a', 'a']}, 'must not repeat'),
    (COMPOSITE, {'fields': [{'name': 'y', 'type': 'INT8'}]},
     'fixed once created'),
    (COMPOSITE, {'enum_values': ['a']}, 'only an enum'),
])
def test_refusals(target, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('alter', draft, target)
