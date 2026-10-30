"""CockroachDB index create/alter compilation and the key reader."""
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

from pgadmin.cdeadmin.providers.cockroachdb import indexes  # noqa: E402
from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'index', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_key_list_reads_expressions_directions_and_stops_at_the_keys():
    assert indexes.key_list(
        'CREATE INDEX i ON d.public.t USING btree (a ASC, lower(b) DESC, '
        "(c || ', x') ASC) STORING (ts) WHERE (a > 0) VISIBILITY 0.25") == [
        {'expression': 'a', 'direction': 'ASC'},
        {'expression': 'lower(b)', 'direction': 'DESC'},
        {'expression': "(c || ', x')", 'direction': 'ASC'}]
    assert indexes.key_list(
        'CREATE UNIQUE INDEX i2 ON d.public.t USING btree (b ASC) USING '
        'HASH WITH (bucket_count=8)') == [
        {'expression': 'b', 'direction': 'ASC'}]


def test_create_with_every_option():
    assert plan('create', {
        'name': 'i', 'table': ['public', 't'],
        'keys': [{'expression': 'a', 'direction': 'DESC'},
                 {'expression': 'lower(b)'}],
        'storing': ['ts'], 'predicate': 'a > 0', 'visibility': 0.25,
        'comment': 'c'}) == [
        'CREATE INDEX "i" ON "public"."t" ("a" DESC, (lower(b))) '
        'STORING ("ts") WHERE a > 0 VISIBILITY 0.25',
        'COMMENT ON INDEX "public"."t"@"i" IS \'c\'']
    assert plan('create', {
        'name': 'h', 'table': 'public.t', 'unique': True,
        'keys': [{'expression': 'b'}], 'hash_sharded': True,
        'bucket_count': 8}) == [
        'CREATE UNIQUE INDEX "h" ON "public"."t" ("b") USING HASH '
        'WITH (bucket_count = 8)']
    assert plan('create', {
        'name': 'g', 'table': 'public.t', 'method': 'inverted',
        'columns': ['j']}) == [
        'CREATE INDEX "g" ON "public"."t" USING GIN ("j")']


TARGET = {'resource_id': 'index:public:t:i', 'display_name': 'i',
          'display_path': ['public', 't', 'i'],
          'native': {'visibility': 1.0, 'comment': None}}


def test_alter_changes_in_place_only():
    assert plan('alter', {'name': 'j', 'visibility': 0,
                          'comment': 'x'}, TARGET) == [
        'ALTER INDEX "public"."t"@"i" NOT VISIBLE',
        'COMMENT ON INDEX "public"."t"@"i" IS \'x\'',
        'ALTER INDEX "public"."t"@"i" RENAME TO "j"']


@pytest.mark.parametrize('operation, draft, reason', [
    ('alter', {'keys': [{'expression': 'b'}]}, 'needs a new index'),
    ('alter', {'visibility': 1}, 'nothing to change'),
    ('create', {'name': 'g', 'table': 't', 'method': 'inverted',
                'unique': True, 'columns': ['j']}, 'inverted index takes'),
    ('create', {'name': 'g', 'table': 't', 'columns': ['j'],
                'bucket_count': 4}, 'needs hash sharding'),
    ('create', {'name': 'g', 'table': 't', 'columns': ['j'],
                'visibility': 2}, 'from 0 to 1'),
])
def test_refusals(operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(operation, draft, TARGET)
