"""Explicit binary SDL and lossless fixed OCTETS slice values."""
from unittest.mock import MagicMock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from firebird.driver import fbapi
from pgadmin.cdeadmin.providers.firebird.array_sdl import octets
from pgadmin.cdeadmin.providers.firebird.character_arrays import (
    encode, metadata,
)
from pgadmin.cdeadmin.providers.firebird.grid_values import normalize_value
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def descriptor():
    value = fbapi.ISC_ARRAY_DESC(0)
    value.array_desc_length = 256
    value.array_desc_dimensions = 2
    value.array_desc_relation_name = b'T'
    value.array_desc_field_name = b'A'
    for index, (lower, upper) in enumerate([(-1, 0), (2, 3)]):
        value.array_desc_bounds[index].array_bound_lower = lower
        value.array_desc_bounds[index].array_bound_upper = upper
    return value


def test_exact_public_sdl_with_explicit_binary_charset():
    assert octets(descriptor()) == (
        bytes([1, 6, 1, fbapi.blr_text2, 1, 0, 0, 1, 2, 1]) + b'T' +
        bytes([4, 1]) + b'A' +
        bytes([34, 0, 11, 255, 255, 255, 255, 11, 0, 0, 0, 0,
               34, 1, 11, 2, 0, 0, 0, 11, 3, 0, 0, 0,
               36, 1, 8, 0, 2, 7, 0, 7, 1, 255]))


@pytest.mark.parametrize('count', [0, 17])
def test_invalid_dimension_count(count):
    value = descriptor()
    value.array_desc_dimensions = count
    with pytest.raises(RelationalClientError):
        octets(value)


def test_missing_name_zero_width_and_inverted_bounds():
    for field, value in [('array_desc_relation_name', b''),
                         ('array_desc_field_name', b''),
                         ('array_desc_length', 0)]:
        desc = descriptor()
        setattr(desc, field, value)
        with pytest.raises(RelationalClientError):
            octets(desc)
    desc = descriptor()
    desc.array_desc_bounds[0].array_bound_upper = -2
    with pytest.raises(RelationalClientError):
        octets(desc)


def test_every_byte_and_zero_padding_are_independent_of_text_encoding():
    values = [[bytes(range(256)), b'\xff\0'], [b'', b'\0\xff']]
    expected = b''.join(item.ljust(256, b'\0')
                        for row in values for item in row)
    for encoding in ('ascii', 'utf8', 'cp1252'):
        assert encode(values, [2, 2], (14, 256, 1, 1), encoding) == expected
        assert encode(normalize_value(values), [2, 2],
                      (14, 256, 1, 1), encoding) == expected


@pytest.mark.parametrize('value', [
    'text', None, 1, b'12345',
    {'encoding': 'base64', 'data': '??', 'byte_length': 1}])
def test_invalid_binary_leaves(value):
    with pytest.raises(RelationalClientError):
        encode([value], [1], (14, 4, 1, 1), 'utf8')


def test_octets_metadata_uses_byte_width_not_connection_character_width():
    cursor = MagicMock()
    catalog = cursor._transaction.cursor.return_value.__enter__.return_value
    catalog.fetchone.return_value = (14, 256, 1, 4)
    assert metadata(cursor, 'T', 'A') == (14, 256, 1, 1)
    catalog.fetchone.return_value = (37, 256, 1, 4)
    assert metadata(cursor, 'T', 'A') == (37, 256, 1, 1)
    assert encode([b'abc'], [1], (37, 256, 1, 1), 'utf8') == [b'abc']
