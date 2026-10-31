"""YugabyteDB YSQL sequence compilation."""
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

TARGET = {'resource_id': 'sequence:public:s', 'display_name': 's',
          'display_path': ['public', 's'], 'native': {
              'data_type': 'integer', 'start': 1, 'increment': 1,
              'minimum': 1, 'maximum': 1000, 'cache': 100, 'cycle': True,
              'owned_by': 'public.t.n', 'comment': None}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'sequence', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create():
    assert plan('create', {'name': 's', 'parent': 'public',
                           'data_type': 'integer', 'start': 5,
                           'cache': 200, 'cycle': True,
                           'owned_by': 'public.t.n', 'comment': 'c'}) == [
        'CREATE SEQUENCE "public"."s" AS integer START 5 CACHE 200 CYCLE '
        'OWNED BY "public"."t"."n"',
        'COMMENT ON SEQUENCE "public"."s" IS \'c\'']


def test_alter():
    assert plan('alter', {'maximum': None, 'cycle': False, 'owned_by': '',
                          'restart': 9, 'comment': 'x', 'name': 't'},
                TARGET) == [
        'ALTER SEQUENCE "public"."s" NO MAXVALUE NO CYCLE OWNED BY NONE '
        'RESTART WITH 9',
        'COMMENT ON SEQUENCE "public"."s" IS \'x\'',
        'ALTER SEQUENCE "public"."s" RENAME TO "t"']


@pytest.mark.parametrize('draft, reason', [
    ({'data_type': 'numeric'}, 'type is'), ({'cache': 0}, 'at least 1'),
    ({'owned_by': 'n'}, 'table.column'), ({'cycle': True}, 'nothing to'),
])
def test_refusals(draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('alter', draft, TARGET)
