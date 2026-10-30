"""CockroachDB view and materialized view compilation."""
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

VIEW = {'resource_id': 'view:public:v', 'display_name': 'v',
        'display_path': ['public', 'v'],
        'native': {'query': 'SELECT id, v FROM d.public.t',
                   'column_names': ['a', 'b']}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create():
    assert plan('view', 'create', {'name': 'v', 'parent': 'public',
                                   'query': 'SELECT 1',
                                   'column_names': ['x']}) == [
        'CREATE VIEW "public"."v" ("x") AS SELECT 1']
    assert plan('materialized-view', 'create', {
        'name': 'm', 'query': 'SELECT 1', 'with_data': False}) == [
        'CREATE MATERIALIZED VIEW "m" AS SELECT 1 WITH NO DATA']


def test_replace_always_carries_the_column_list():
    assert plan('view', 'alter', {
        'query': 'SELECT id, v, 1 FROM t',
        'column_names': ['a', 'b', 'c'], 'name': 'w'}, VIEW) == [
        'CREATE OR REPLACE VIEW "public"."v" ("a", "b", "c") AS '
        'SELECT id, v, 1 FROM t',
        'ALTER VIEW "public"."v" RENAME TO "w"']
    assert plan('view', 'alter', {'query': 'SELECT id, v + 1 FROM t'},
                VIEW) == [
        'CREATE OR REPLACE VIEW "public"."v" ("a", "b") AS '
        'SELECT id, v + 1 FROM t']


@pytest.mark.parametrize('kind, draft, reason', [
    ('materialized-view', {'query': 'SELECT 2'}, 'cannot change in place'),
    ('view', {'with_data': True}, 'cannot change in place'),
    ('view', {}, 'nothing to change'),
])
def test_refusals(kind, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, 'alter', draft, VIEW)
