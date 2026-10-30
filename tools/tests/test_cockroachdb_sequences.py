"""CockroachDB sequence compilation and the SHOW CREATE reader."""
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

from pgadmin.cdeadmin.providers.cockroachdb import sequences  # noqa: E402
from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

NATIVE = {'data_type': 'INT8', 'start': 1, 'increment': 1, 'minimum': 1,
          'maximum': 9223372036854775807, 'cache': 10,
          'cache_scope': 'PER SESSION', 'owned_by': None}
TARGET = {'resource_id': 'sequence:public:s', 'display_name': 's',
          'display_path': ['public', 's'], 'native': NATIVE}


def plan(operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': 'sequence', 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_parse_create():
    assert sequences.parse_create(
        'CREATE SEQUENCE public."s x" AS INT4 MINVALUE 1 MAXVALUE 2147483647 '
        'INCREMENT -2 START 5 PER SESSION CACHE 5;') == (
        ('public', 's x'), {'data_type': 'INT4', 'start': 5,
                            'increment': -2, 'minimum': 1,
                            'maximum': 2147483647, 'cache': 5,
                            'cache_scope': 'PER SESSION'})
    assert sequences.parse_create(
        'CREATE SEQUENCE public.p MINVALUE 1 MAXVALUE 9 INCREMENT 1 '
        'START 1;')[1]['cache_scope'] == ''
    assert sequences.parse_create('CREATE TABLE public.t (a INT8);') is None


def test_create():
    assert plan('create', {'name': 's', 'parent': 'public',
                           'data_type': 'INT4', 'start': 5, 'cache': 10,
                           'owned_by': 'public.t.n'}) == [
        'CREATE SEQUENCE "public"."s" AS INT4 START 5 OWNED BY '
        '"public"."t"."n" PER NODE CACHE 10']


@pytest.mark.parametrize('draft, steps', [
    ({'cache_scope': 'PER NODE'},
     ['PER SESSION CACHE 1', 'PER NODE CACHE 10']),
    ({'cache': 20}, ['PER SESSION CACHE 20']),
    ({'cache': 1}, ['PER SESSION CACHE 1']),
    ({'cache': 10}, []),
])
def test_cache_steps_name_the_scope_and_reset_out_of_session(draft, steps):
    assert sequences._cache_steps(draft, NATIVE) == steps


def test_alter_runs_cache_steps_first_then_options_then_rename():
    assert plan('alter', {'cache_scope': '', 'maximum': None,
                          'restart': 100, 'name': 't'}, TARGET) == [
        'ALTER SEQUENCE "public"."s" PER SESSION CACHE 1',
        'ALTER SEQUENCE "public"."s" PER NODE CACHE 10',
        'ALTER SEQUENCE "public"."s" NO MAXVALUE RESTART WITH 100',
        'ALTER SEQUENCE "public"."s" RENAME TO "t"']


@pytest.mark.parametrize('draft, reason', [
    ({'cycle': True}, 'CYCLE'), ({'cache': 0}, 'at least 1'),
    ({'data_type': 'INT16'}, 'INT2, INT4 or INT8'),
    ({'owned_by': 'n'}, 'table.column'), ({}, 'nothing to change'),
])
def test_refusals(draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan('alter', draft, TARGET)
