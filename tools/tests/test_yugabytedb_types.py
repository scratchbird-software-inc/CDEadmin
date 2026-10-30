"""YugabyteDB YSQL types and domains compilation."""
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

ENUM = {'resource_id': 'type:public:s', 'display_name': 's',
        'display_path': ['public', 's'],
        'native': {'type_kind': 'ENUM', 'enum_values': ['a', 'b'],
                   'comment': None}}
DOMAIN = {'resource_id': 'domain:public:d', 'display_name': 'd',
          'display_path': ['public', 'd'],
          'native': {'default': "'x'", 'comment': None}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create_enum_composite_range_and_domain():
    assert plan('type', 'create', {
        'name': 's', 'parent': 'public', 'type_kind': 'ENUM',
        'enum_values': ['a', "b'c"], 'comment': 'x'}) == [
        'CREATE TYPE "public"."s" AS ENUM (\'a\', \'b\'\'c\')',
        'COMMENT ON TYPE "public"."s" IS \'x\'']
    assert plan('type', 'create', {
        'name': 'r', 'type_kind': 'RANGE', 'subtype': 'timestamptz',
        'subtype_diff': 'tstzrange_subdiff'}) == [
        'CREATE TYPE "r" AS RANGE (subtype = timestamptz, '
        'subtype_diff = tstzrange_subdiff)']
    assert plan('domain', 'create', {
        'name': 'd', 'base_type': 'varchar(20)', 'collation': 'C',
        'default': "'x'", 'not_null': True,
        'checks': [{'name': 'c', 'expression': 'length(VALUE) > 0'}]}) == [
        'CREATE DOMAIN "d" AS varchar(20) COLLATE "C" DEFAULT \'x\' NOT NULL '
        'CONSTRAINT "c" CHECK (length(VALUE) > 0)']


def test_alter_enum_and_domain():
    assert plan('type', 'alter', {
        'rename_values': [{'from': 'b', 'to': 'bb'}],
        'enum_values': ['first', 'a', 'bb']}, ENUM) == [
        'ALTER TYPE "public"."s" RENAME VALUE \'b\' TO \'bb\'',
        'ALTER TYPE "public"."s" ADD VALUE \'first\' BEFORE \'a\'']
    assert plan('domain', 'alter', {'default': '', 'name': 'e'},
                DOMAIN) == [
        'ALTER DOMAIN "public"."d" DROP DEFAULT',
        'ALTER DOMAIN "public"."d" RENAME TO "e"']


@pytest.mark.parametrize('kind, draft, target, reason', [
    ('type', {'enum_values': ['a']}, ENUM, 'cannot be dropped'),
    ('type', {'enum_values': ['b', 'a']}, ENUM, 'reordered'),
    ('type', {'fields': []}, ENUM, 'fixed once created'),
    ('domain', {'not_null': False}, DOMAIN, 'cannot change'),
    ('domain', {'checks': []}, DOMAIN, 'cannot change'),
])
def test_refusals(kind, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, 'alter', draft, target)
