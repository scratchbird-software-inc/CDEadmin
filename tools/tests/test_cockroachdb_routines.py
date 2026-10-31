"""CockroachDB function and procedure compilation and the routine reader."""
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

from pgadmin.cdeadmin.providers.cockroachdb import routines  # noqa: E402
from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION, _array_signature,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

NATIVE = {'name': 'f', 'signature': 'int8, int8', 'language': 'SQL',
          'security': 'INVOKER', 'volatility': 'IMMUTABLE', 'strict': True,
          'leakproof': True, 'body': 'SELECT a + b;', 'returns': 'INT8',
          'returns_set': False, 'parameters': [
              {'mode': 'IN', 'name': 'a', 'type': 'INT8', 'default': None},
              {'mode': 'IN', 'name': 'b', 'type': 'INT8', 'default': '2'}]}
TARGET = {'resource_id': 'function:public:f(int8, int8)',
          'display_name': 'f(int8, int8)',
          'display_path': ['public', 'f(int8, int8)'], 'native': NATIVE}


def plan(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation,
        'target_resource': target, 'draft': draft,
        '_provider_route': {'host': '127.0.0.1'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def test_parse_create_reads_types_defaults_modes_and_options():
    statement = (
        'CREATE FUNCTION public.g(IN a INT8, OUT "x y" INT8, '
        'INOUT b STRING DEFAULT \'p, q\':::STRING)\n\tRETURNS RECORD\n'
        '\tSTABLE\n\tNOT LEAKPROOF\n\tSTRICT\n\tLANGUAGE plpgsql\n'
        '\tSECURITY DEFINER\n\tAS $$\n\tBEGIN END;\n$$;')
    key, facts = routines.parse_create(statement, ['a', 'x y', 'b'],
                                       ['i', 'o', 'b'])
    assert key == ('public', 'g')
    assert facts == {
        'parameters': [
            {'mode': 'IN', 'name': 'a', 'type': 'INT8', 'default': None},
            {'mode': 'OUT', 'name': 'x y', 'type': 'INT8', 'default': None},
            {'mode': 'INOUT', 'name': 'b', 'type': 'STRING',
             'default': "'p, q'"}],
        'returns': 'RECORD', 'returns_set': False, 'security': 'DEFINER',
        'language': 'PLPGSQL', 'volatility': 'STABLE', 'leakproof': False,
        'strict': True}


def test_create_function_and_procedure():
    assert plan('function', 'create', {
        'name': 'f', 'parent': 'public', 'returns': 'INT8',
        'returns_set': True, 'volatility': 'STABLE',
        'parameters': [{'name': 'a', 'type': 'INT8', 'default': '1'}],
        'body': 'SELECT $cde$x$cde$'}) == [
        'CREATE FUNCTION "public"."f"("a" INT8 DEFAULT 1) RETURNS SETOF '
        'INT8 STABLE CALLED ON NULL INPUT LANGUAGE SQL SECURITY INVOKER AS '
        '$cde1$\nSELECT $cde$x$cde$\n$cde1$']
    assert plan('procedure', 'create', {
        'name': 'p', 'language': 'PLPGSQL', 'security': 'DEFINER',
        'parameters': [{'mode': 'INOUT', 'name': 'n', 'type': 'INT8'}],
        'body': 'BEGIN END'}) == [
        'CREATE PROCEDURE "p"(INOUT "n" INT8) LANGUAGE PLPGSQL SECURITY '
        'DEFINER AS $cde$\nBEGIN END\n$cde$']


def test_alter_replaces_with_the_fixed_signature_then_renames():
    assert plan('function', 'alter', {
        'body': 'SELECT a * b', 'leakproof': False, 'volatility': 'STABLE',
        'name': 'g'}, TARGET) == [
        'CREATE OR REPLACE FUNCTION "public"."f"("a" INT8, "b" INT8 '
        'DEFAULT 2) RETURNS INT8 STABLE STRICT LANGUAGE SQL SECURITY '
        'INVOKER AS $cde$\nSELECT a * b\n$cde$',
        'ALTER FUNCTION "public"."f"(int8, int8) RENAME TO "g"']


def test_drop_names_the_signature():
    assert plan('function', 'drop', {'confirmation': 'f'}, TARGET) == [
        'DROP FUNCTION "public"."f"(int8, int8)']


@pytest.mark.parametrize('kind, operation, draft, reason', [
    ('function', 'alter', {'parameters': []}, 'identity'),
    ('function', 'alter', {'returns': 'TEXT'}, 'identity'),
    ('function', 'alter', {'volatility': 'VOLATILE'}, 'must be IMMUTABLE'),
    ('procedure', 'create', {'name': 'p', 'volatility': 'STABLE',
                             'body': 'SELECT 1'}, 'procedure takes no'),
    ('function', 'create', {'name': 'f', 'body': 'SELECT 1'},
     'return type or OUT'),
    ('function', 'create', {'name': 'f', 'returns': 'INT8', 'body': 'x',
                            'parameters': [{'mode': 'OUT', 'type': 'INT8',
                                            'default': '1'}]},
     'OUT parameter takes no default'),
])
def test_refusals(kind, operation, draft, reason):
    with pytest.raises(RelationalClientError, match=reason):
        plan(kind, operation, draft, TARGET)


def test_array_arguments_read_as_brackets():
    # Live, 26.1.3: pg_get_function_arguments gives _int8; _odd is a user
    # type of that name, not an array.
    assert _array_signature('_int8, _odd, int8, __odd',
                            [True, False, False, True]) == \
        'int8[], _odd, int8, _odd[]'
    assert _array_signature('', None) == ''
    assert _array_signature('_int8', [True, False]) == '_int8'
