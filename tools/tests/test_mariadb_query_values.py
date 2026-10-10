"""MariaDB values and metadata retain native distinctions at the browser edge.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_cdeadmin_relational_providers import MARIADB_PROFILE
from pgadmin.cdeadmin.providers.mysql_family.mariadb_values import (
    Cursor, columns, parameters, value,
)
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.mark.parametrize('native, expected', [
    (None, None), ('', ''), ('0000-00-00', '0000-00-00'),
    ('-838:59:59.123456', '-838:59:59.123456'),
    (Decimal('1.2300'), '1.2300'), (9007199254740993, '9007199254740993'),
    (-9007199254740993, '-9007199254740993'), (42, 42),
    (b'', {'encoding': 'base64', 'data': '', 'byte_length': 0}),
    (b'\xff\0', {'encoding': 'base64', 'data': '/wA=', 'byte_length': 2}),
])
def test_exact_values(native, expected):
    assert value(native) == expected


def test_old_connector_refused_before_query_execute():
    native = SimpleNamespace(close=Mock(), execute=Mock())
    with pytest.raises(RelationalClientError, match='exact-temporal'):
        Cursor(SimpleNamespace(cursor=lambda **kw: native))
    native.close.assert_called_once()
    native.execute.assert_not_called()


def test_duplicate_metadata_names_and_native_length_correction():
    result = columns(SimpleNamespace(
        description=[('x', 253), ('x', 253), ('x#2', 253)],
        metadata={'length': (0, 0, 0), 'max_length': (48, 48, 48),
                  'charset': (45, 45, 45)}))
    assert [c['name'] for c in result] == ['x', 'x#3', 'x#2']
    assert result[0]['native_metadata']['length'] == 48
    assert result[0]['native_metadata']['max_length'] == 0


def test_typed_parameters_preserve_exact_values_and_native_shapes():
    items = [{'encoding': 'integer', 'data': '18446744073709551615'},
             {'encoding': 'decimal', 'data': '1.2300'},
             {'encoding': 'base64', 'data': '/wA=', 'byte_length': 2}]
    expected = (18446744073709551615, Decimal('1.2300'), b'\xff\0')
    assert parameters(items) == expected
    assert parameters(dict(zip('abc', items))) == dict(zip('abc', expected))
    assert MARIADB_PROFILE.parameter_shape == 'object-or-array'


@pytest.mark.parametrize('item', [
    9007199254740993, float('inf'), float('nan'), [],
    {'encoding': 'decimal', 'data': 'NaN'},
    {'encoding': 'base64', 'data': '*'},
    {'encoding': 'base64', 'data': '', 'byte_length': True},
    {'encoding': 'integer', 'data': '12', 'byte_length': 2},
    {'encoding': 'arbitrary', 'data': 'x'},
])
def test_invalid_parameter_preflight(item):
    with pytest.raises(RelationalClientError):
        parameters([item])


@pytest.mark.parametrize('number', [
    '18446744073709551616', '-9223372036854775809', '9' * 65,
])
def test_wide_integer_envelope_uses_lossless_decimal_binding(number):
    result = parameters([{'encoding': 'integer', 'data': number}])[0]
    assert type(result) is Decimal
    assert str(result) == number


def test_bytearray_binds_native_bytes_not_python_object_text():
    result = parameters([bytearray(b'\xff\0')])[0]
    assert type(result) is bytes
    assert result == b'\xff\0'
