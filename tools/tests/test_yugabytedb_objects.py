"""YugabyteDB YSQL triggers, users and roles compilation."""
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

TRIGGER = {'resource_id': 'trigger:public:t:tr', 'display_name': 'tr',
           'display_path': ['public', 't', 'tr'], 'native': {
               'timing': 'BEFORE', 'level': 'ROW', 'events': ['INSERT'],
               'update_columns': [], 'function': 'public.f()',
               'arguments': [], 'when': None, 'enabled': 'ORIGIN',
               'comment': None}}
ROLE = {'resource_id': 'role:r', 'display_name': 'r', 'display_path': ['r'],
        'native': {'login': False, 'privileges': ['INHERIT'],
                   'connection_limit': -1, 'valid_until': None,
                   'member_of': ['a'], 'comment': None}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item.get('preview_source', item['source']) for item in
            planned['provider_payload']['compiled']['statements']]


def test_trigger_create_with_columns_when_and_disabled():
    assert plan('trigger', 'create', {
        'name': 'tr', 'table': 'public.t', 'timing': 'BEFORE',
        'level': 'ROW', 'events': ['INSERT', 'UPDATE'],
        'update_columns': ['v'], 'when': 'NEW.v > 0',
        'function': 'public.f()', 'arguments': ["it's"],
        'enabled': 'DISABLED', 'comment': 'c'}) == [
        'CREATE TRIGGER "tr" BEFORE INSERT OR UPDATE OF "v" ON "public"."t" '
        'FOR EACH ROW WHEN (NEW.v > 0) EXECUTE FUNCTION "public"."f"'
        "('it''s')",
        'ALTER TABLE "public"."t" DISABLE TRIGGER "tr"',
        'COMMENT ON TRIGGER "tr" ON "public"."t" IS \'c\'']


def test_trigger_alter_replaces_then_renames():
    assert plan('trigger', 'alter', {'events': ['DELETE'],
                                     'enabled': 'REPLICA', 'name': 'tr2'},
                TRIGGER) == [
        'CREATE OR REPLACE TRIGGER "tr" BEFORE DELETE ON "public"."t" '
        'FOR EACH ROW EXECUTE FUNCTION "public"."f"()',
        'ALTER TABLE "public"."t" ENABLE REPLICA TRIGGER "tr"',
        'ALTER TRIGGER "tr" ON "public"."t" RENAME TO "tr2"']


def test_principals():
    assert plan('user', 'create', {
        'name': 'u', 'password': 'p', 'privileges': ['CREATEDB'],
        'connection_limit': 3, 'member_of': ['a'], 'comment': 'c'}) == [
        'CREATE USER "u" WITH LOGIN CREATEDB NOINHERIT CONNECTION LIMIT 3 '
        'PASSWORD <redacted>',
        'GRANT "a" TO "u"', 'COMMENT ON ROLE "u" IS \'c\'']
    assert plan('role', 'alter', {
        'privileges': ['SUPERUSER'], 'connection_limit': 2,
        'member_of': [], 'name': 's'}, ROLE) == [
        'ALTER ROLE "r" WITH SUPERUSER NOINHERIT CONNECTION LIMIT 2',
        'REVOKE "a" FROM "r"', 'ALTER ROLE "r" RENAME TO "s"']


@pytest.mark.parametrize('kind, operation, draft, target, reason', [
    ('trigger', 'create', {'name': 'x', 'table': 't', 'timing': 'AFTER',
                           'level': 'ROW', 'events': ['TRUNCATE'],
                           'function': 'f'}, None, 'statement-level'),
    ('trigger', 'create', {'name': 'x', 'table': 't',
                           'timing': 'INSTEAD OF', 'level': 'STATEMENT',
                           'events': ['INSERT'], 'function': 'f'}, None,
     'row-level'),
    ('trigger', 'create', {'name': 'x', 'table': 't', 'timing': 'AFTER',
                           'events': ['INSERT'], 'update_columns': ['v'],
                           'function': 'f'}, None, 'UPDATE event'),
    ('role', 'alter', {'connection_limit': -2}, ROLE, 'whole number'),
    ('role', 'alter', {'privileges': ['INHERIT']}, ROLE, 'nothing to'),
])
def test_refusals(kind, operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, operation, draft, target)
