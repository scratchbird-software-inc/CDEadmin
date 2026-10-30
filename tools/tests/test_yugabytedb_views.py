"""YugabyteDB YSQL views, materialized views and refresh."""
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

VIEW = {'resource_id': 'view:public:v', 'display_name': 'v',
        'display_path': ['public', 'v'],
        'native': {'query': 'SELECT id, v FROM t', 'column_names': ['a', 'b'],
                   'security_barrier': False, 'security_invoker': False,
                   'comment': None}}
MAT = {'resource_id': 'materialized-view:public:m', 'display_name': 'm',
       'display_path': ['public', 'm'],
       'native': {'query': 'SELECT 1', 'column_names': ['x'],
                  'tablespace': None, 'comment': None}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create():
    assert plan('view', 'create', {
        'name': 'v', 'parent': 'public', 'query': 'SELECT 1',
        'column_names': ['x'], 'recursive': True, 'security_barrier': True,
        'comment': 'c'}) == [
        'CREATE RECURSIVE VIEW "public"."v" ("x") WITH '
        '(security_barrier = true) AS SELECT 1',
        'COMMENT ON VIEW "public"."v" IS \'c\'']
    assert plan('materialized-view', 'create', {
        'name': 'm', 'query': 'SELECT 1', 'tablespace': 'ts',
        'with_data': False}) == [
        'CREATE MATERIALIZED VIEW "m" TABLESPACE "ts" AS SELECT 1 '
        'WITH NO DATA']


def test_alter_renames_columns_then_replaces():
    assert plan('view', 'alter', {
        'column_names': ['a2', 'b', 'c'], 'query': 'SELECT id, v, 1 FROM t',
        'security_invoker': True, 'name': 'w'}, VIEW) == [
        'ALTER VIEW "public"."v" RENAME COLUMN "a" TO "a2"',
        'CREATE OR REPLACE VIEW "public"."v" ("a2", "b", "c") AS '
        'SELECT id, v, 1 FROM t',
        'ALTER VIEW "public"."v" SET (security_invoker = true)',
        'ALTER VIEW "public"."v" RENAME TO "w"']
    assert plan('materialized-view', 'alter', {
        'tablespace': 'ts', 'comment': 'c'}, MAT) == [
        'ALTER MATERIALIZED VIEW "public"."m" SET TABLESPACE "ts"',
        'COMMENT ON MATERIALIZED VIEW "public"."m" IS \'c\'']


def test_refresh():
    assert plan('materialized-view', 'refresh', {'concurrently': True},
                MAT) == ['REFRESH MATERIALIZED VIEW CONCURRENTLY '
                         '"public"."m"']
    assert plan('materialized-view', 'refresh', {'with_data': False},
                MAT) == ['REFRESH MATERIALIZED VIEW "public"."m" WITH NO '
                         'DATA']


@pytest.mark.parametrize('kind, operation, draft, target, reason', [
    ('materialized-view', 'alter', {'query': 'SELECT 2'}, MAT,
     'cannot change in place'),
    ('view', 'create', {'name': 'v', 'query': 'SELECT 1',
                        'recursive': True}, None, 'needs column names'),
    ('view', 'create', {'name': 'v', 'query': 'SELECT 1',
                        'with_data': True}, None, 'only a materialized'),
    ('materialized-view', 'refresh', {'concurrently': True,
                                      'with_data': False}, MAT,
     'cannot be WITH NO DATA'),
])
def test_refusals(kind, operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, operation, draft, target)
