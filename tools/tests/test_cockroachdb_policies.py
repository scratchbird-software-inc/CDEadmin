"""CockroachDB row-level security: policies and the table switches."""
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

POLICY = {'resource_id': 'row-policy:public:t:p', 'display_name': 'p',
          'display_path': ['public', 't', 'p'],
          'native': {'roles': ['r1'], 'using': 'v > 0', 'with_check': None,
                     'policy_type': 'PERMISSIVE', 'command': 'ALL'}}
TABLE = {'resource_id': 'table:public:t', 'display_name': 't',
         'display_path': ['public', 't'],
         'native': {'row_level_security': False,
                    'force_row_level_security': False, 'constraints': []}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create_policy():
    assert plan('row-policy', 'create', {
        'name': 'p', 'table': ['public', 't'], 'policy_type': 'RESTRICTIVE',
        'command': 'UPDATE', 'roles': ['r1', 'public'],
        'using': 'v > 0', 'with_check': 'v < 9'}) == [
        'CREATE POLICY "p" ON "public"."t" AS RESTRICTIVE FOR UPDATE TO '
        '"r1", PUBLIC USING (v > 0) WITH CHECK (v < 9)']


def test_alter_policy_in_place_then_rename():
    assert plan('row-policy', 'alter', {
        'roles': [], 'using': 'v > 1', 'with_check': 'v < 5', 'name': 'q'},
        POLICY) == [
        'ALTER POLICY "p" ON "public"."t" TO PUBLIC USING (v > 1) '
        'WITH CHECK (v < 5)',
        'ALTER POLICY "p" ON "public"."t" RENAME TO "q"']
    assert plan('row-policy', 'drop', {'confirmation': 'p'}, POLICY) == [
        'DROP POLICY "p" ON "public"."t"']


def test_table_switches():
    assert plan('table', 'alter', {'row_level_security': True,
                                   'force_row_level_security': True},
                TABLE) == [
        'ALTER TABLE "public"."t" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "public"."t" FORCE ROW LEVEL SECURITY']


@pytest.mark.parametrize('operation, draft, reason', [
    ('alter', {'using': ''}, 'cannot remove'),
    ('alter', {'command': 'SELECT'}, 'cannot change in place'),
    ('alter', {'roles': ['r1']}, 'nothing to change'),
    ('create', {'name': 'p', 'table': 't', 'command': 'INSERT',
                'using': 'true'}, 'INSERT policy has no USING'),
    ('create', {'name': 'p', 'table': 't', 'command': 'SELECT',
                'with_check': 'true'}, 'SELECT policy has no WITH CHECK'),
    ('create', {'name': 'p', 'table': 't', 'policy_type': 'MAYBE'},
     'PERMISSIVE or RESTRICTIVE'),
])
def test_refusals(operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('row-policy', operation, draft, POLICY)
