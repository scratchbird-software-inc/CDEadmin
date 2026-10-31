"""YugabyteDB YSQL row-level security policies."""
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

TARGET = {'resource_id': 'row-policy:public:t:p', 'display_name': 'p',
          'display_path': ['public', 't', 'p'], 'native': {
              'roles': ['r'], 'using': '(true)', 'with_check': None,
              'comment': None}}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'row-policy', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create_with_comment():
    assert plan('create', {'name': 'p', 'table': 'public.t',
                           'policy_type': 'RESTRICTIVE', 'command': 'UPDATE',
                           'roles': ['r', 'public'], 'using': 'a = 1',
                           'with_check': 'a > 0', 'comment': 'c'}) == [
        'CREATE POLICY "p" ON "public"."t" AS RESTRICTIVE FOR UPDATE TO '
        '"r", PUBLIC USING (a = 1) WITH CHECK (a > 0)',
        'COMMENT ON POLICY "p" ON "public"."t" IS \'c\'']


def test_alter_comments_before_rename():
    assert plan('alter', {'using': 'a = 2', 'comment': 'c', 'name': 'q'},
                TARGET) == [
        'ALTER POLICY "p" ON "public"."t" USING (a = 2)',
        'COMMENT ON POLICY "p" ON "public"."t" IS \'c\'',
        'ALTER POLICY "p" ON "public"."t" RENAME TO "q"']
    assert plan('alter', {'comment': 'c', 'roles': ['r']}, TARGET) == [
        'COMMENT ON POLICY "p" ON "public"."t" IS \'c\'']
    assert plan('drop', {'confirmation': 'p'}, TARGET) == [
        'DROP POLICY "p" ON "public"."t"']


@pytest.mark.parametrize('draft, reason', [
    ({'using': ''}, 'YugabyteDB cannot remove'),
    ({'with_check': ''}, 'nothing to change'),
    ({'command': 'SELECT'}, 'YugabyteDB fixes AS and FOR'),
    ({'roles': ['r']}, 'nothing to change'),
])
def test_refusals(draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('alter', draft, TARGET)
