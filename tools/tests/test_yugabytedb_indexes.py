"""YugabyteDB YSQL index compilation and the definition reader."""
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

from pgadmin.cdeadmin.providers.yugabytedb import indexes  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

TARGET = {'resource_id': 'index:public:t:i', 'display_name': 'i',
          'display_path': ['public', 't', 'i'],
          'native': {'tablespace': 'ts', 'comment': None}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'index', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_parse_definition():
    assert indexes.parse_definition(
        'CREATE INDEX i ON public.t USING lsm ((a, b) HASH, id ASC) '
        'INCLUDE (j, "k l") WHERE (a > 0)') == {
        'method': 'lsm', 'keys': [
            {'expression': 'a', 'direction': 'HASH'},
            {'expression': 'b', 'direction': 'HASH'},
            {'expression': 'id', 'direction': 'ASC'}],
        'storing': ['j', 'k l'], 'nulls_not_distinct': False,
        'predicate': 'a > 0'}
    parsed = indexes.parse_definition(
        'CREATE UNIQUE INDEX u ON public.t USING lsm (lower(b) DESC) '
        'NULLS NOT DISTINCT')
    assert (parsed['keys'], parsed['nulls_not_distinct']) == (
        [{'expression': 'lower(b)', 'direction': 'DESC'}], True)
    assert indexes.parse_definition(
        'CREATE INDEX g ON public.t USING ybgin (j)')['method'] == 'gin'


def test_create_orders_include_tablespace_split_where():
    assert plan('create', {
        'name': 'i', 'table': 'public.t', 'nonconcurrently': True,
        'keys': [{'expression': 'a', 'direction': 'HASH'},
                 {'expression': 'b', 'direction': 'HASH'},
                 {'expression': 'lower(c)', 'direction': 'DESC'}],
        'storing': ['j'], 'tablespace': 'ts', 'split_into': 3,
        'predicate': 'a > 0', 'comment': 'c'}) == [
        'CREATE INDEX NONCONCURRENTLY "i" ON "public"."t" (("a", "b") '
        'HASH, (lower(c)) DESC) INCLUDE ("j") TABLESPACE "ts" SPLIT INTO 3 '
        'TABLETS WHERE a > 0',
        'COMMENT ON INDEX "public"."i" IS \'c\'']


def test_alter_in_place():
    assert plan('alter', {'tablespace': '', 'comment': 'x', 'name': 'j'},
                TARGET) == [
        'ALTER INDEX "public"."i" SET TABLESPACE "pg_default"',
        'COMMENT ON INDEX "public"."i" IS \'x\'',
        'ALTER INDEX "public"."i" RENAME TO "j"']


@pytest.mark.parametrize('operation, draft, reason', [
    ('create', {'name': 'i', 'table': 't', 'keys': [
        {'expression': 'a', 'direction': 'ASC'},
        {'expression': 'b', 'direction': 'HASH'}]}, 'must lead'),
    ('create', {'name': 'i', 'table': 't', 'method': 'gin',
                'unique': True, 'columns': ['j']}, 'gin index'),
    ('create', {'name': 'i', 'table': 't', 'columns': ['a'],
                'nulls_not_distinct': True}, 'is for UNIQUE'),
    ('alter', {'keys': [{'expression': 'a'}]}, 'needs a new index'),
])
def test_refusals(operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(operation, draft, TARGET)
