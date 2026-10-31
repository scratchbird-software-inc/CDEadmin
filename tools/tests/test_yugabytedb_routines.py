"""YugabyteDB YSQL functions and procedures."""
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

from pgadmin.cdeadmin.providers.yugabytedb import routines  # noqa: E402
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

FUNCTION = {
    'resource_id': 'function:public:f(integer, integer)',
    'display_name': 'f(integer, integer)',
    'display_path': ['public', 'f(integer, integer)'],
    'native': {
        'name': 'f', 'signature': 'integer, integer',
        'parameters': [{'mode': 'IN', 'name': 'a', 'type': 'integer'},
                       {'mode': 'IN', 'name': 'b', 'type': 'integer',
                        'default': '2'}],
        'returns': 'integer', 'returns_set': False, 'language': 'SQL',
        'security': 'INVOKER', 'volatility': 'IMMUTABLE', 'strict': True,
        'leakproof': False, 'parallel': 'SAFE', 'cost': 5.0, 'rows': None,
        'settings': [], 'body': 'SELECT a + b', 'comment': None}}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1', 'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_create_function_with_table_result_and_settings():
    assert plan('function', 'create', {
        'name': 'f', 'parent': 'public',
        'parameters': [{'mode': 'VARIADIC', 'name': 'xs',
                        'type': 'integer[]'},
                       {'mode': 'TABLE', 'name': 'k', 'type': 'integer'}],
        'rows': 10, 'body': 'SELECT unnest(xs)',
        'settings': [{'name': 'search_path', 'value': 'public'}],
        'comment': 'c'}) == [
        'CREATE FUNCTION "public"."f"(VARIADIC "xs" integer[]) RETURNS '
        'TABLE ("k" integer) VOLATILE CALLED ON NULL INPUT PARALLEL UNSAFE '
        'ROWS 10 LANGUAGE SQL SECURITY INVOKER SET search_path = '
        "'public' AS $cde$\nSELECT unnest(xs)\n$cde$",
        'COMMENT ON FUNCTION "public"."f"(integer[]) IS \'c\'']


def test_create_procedure():
    assert plan('procedure', 'create', {
        'name': 'p', 'parameters': [{'mode': 'INOUT', 'name': 'n',
                                     'type': 'integer'}],
        'language': 'plpgsql', 'security': 'DEFINER',
        'body': 'BEGIN n := n + 1; END'}) == [
        'CREATE PROCEDURE "p"(INOUT "n" integer) LANGUAGE PLPGSQL SECURITY '
        'DEFINER AS $cde$\nBEGIN n := n + 1; END\n$cde$']


def test_alter_replaces_body_and_keeps_signature():
    assert plan('function', 'alter', {
        'body': 'SELECT a * b', 'comment': 'x', 'name': 'g'},
        FUNCTION) == [
        'CREATE OR REPLACE FUNCTION "public"."f"("a" integer, "b" integer '
        'DEFAULT 2) RETURNS integer IMMUTABLE STRICT PARALLEL SAFE COST 5 '
        'LANGUAGE SQL SECURITY INVOKER AS $cde$\nSELECT a * b\n$cde$',
        'COMMENT ON FUNCTION "public"."f"(integer, integer) IS \'x\'',
        'ALTER FUNCTION "public"."f"(integer, integer) RENAME TO "g"']
    assert plan('function', 'drop', {'confirmation': 'f'}, FUNCTION) == [
        'DROP FUNCTION "public"."f"(integer, integer)']


def test_parameters_read_back():
    assert routines.parameters_from(
        'a integer, "B" text DEFAULT \'x\'::text, VARIADIC xs integer[]',
        'TABLE(k integer, v text)', ['a', 'B', 'xs', 'k', 'v'],
        ['i', 'i', 'v', 't', 't']) == [
        {'mode': 'IN', 'name': 'a', 'type': 'integer', 'default': None},
        {'mode': 'IN', 'name': 'B', 'type': 'text',
         'default': "'x'::text"},
        {'mode': 'VARIADIC', 'name': 'xs', 'type': 'integer[]',
         'default': None},
        {'mode': 'TABLE', 'name': 'k', 'type': 'integer', 'default': None},
        {'mode': 'TABLE', 'name': 'v', 'type': 'text', 'default': None}]
    assert routines.returns_from('SETOF integer') == ('integer', True)
    assert routines.returns_from('TABLE(k integer)') == (None, False)


@pytest.mark.parametrize('kind, operation, draft, target, reason', [
    ('function', 'alter', {'parameters': []}, FUNCTION, 'identity'),
    ('procedure', 'create', {'name': 'p', 'body': 'SELECT 1',
                             'returns': 'int'}, None, 'takes no returns'),
    ('function', 'create', {'name': 'f', 'body': 'SELECT 1'}, None,
     'return type or OUT'),
    ('function', 'create', {'name': 'f', 'body': 'SELECT 1',
                            'returns': 'int[];'}, None, 'unsafe'),
    ('function', 'create', {'name': 'f', 'body': 'SELECT 1',
                            'returns': 'int', 'cost': 0}, None, 'positive'),
    ('function', 'create', {'name': 'f', 'body': 'SELECT 1',
                            'returns': 'int', 'parameters': [
                                {'mode': 'OUT', 'type': 'int',
                                 'default': '1'}]}, None, 'no default'),
])
def test_refusals(kind, operation, draft, target, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, operation, draft, target)
