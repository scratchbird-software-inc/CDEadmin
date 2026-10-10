"""MySQL query values preserve server text, bytes and browser precision."""
import json
from decimal import Decimal

import pytest
from tools.tests.test_cdeadmin_relational_providers import MYSQL_PROFILE  # noqa
from mysql.connector.constants import FieldType
from pgadmin.cdeadmin.providers.mysql_family.mysql_values import (
    columns, parameters, value,
)
from pgadmin.cdeadmin.sdk import RelationalClientError


def column(kind, name='value', charset=63):
    return (name, kind, None, None, None, None, True, 0, charset)


@pytest.mark.parametrize('kind,raw,expected', [
    (FieldType.DATE, b'0000-00-00', '0000-00-00'),
    (FieldType.DATE, b'2025-00-12', '2025-00-12'),
    (FieldType.DATETIME, b'0000-00-00 00:00:00', '0000-00-00 00:00:00'),
    (FieldType.TIME, b'-838:59:59.000001', '-838:59:59.000001'),
    (FieldType.NEWDECIMAL, b'1234567890123456789.123456',
     '1234567890123456789.123456'),
    (FieldType.LONGLONG, b'18446744073709551615', '18446744073709551615'),
    (FieldType.LONG, b'-200', -200),
    (FieldType.BIT, b'\xff' * 8, '18446744073709551615'),
    (FieldType.DOUBLE, b'-0', '-0'),
    (FieldType.JSON, b'{"n":9007199254740993}', '{"n":9007199254740993}'),
])
def test_exact_native_text(kind, raw, expected):
    result = value(raw, column(kind), 'utf8')
    assert json.loads(json.dumps(result)) == expected


def test_null_empty_binary_and_text_are_distinct():
    assert value(None, column(FieldType.BLOB), 'utf8') is None
    assert value(b'', column(FieldType.BLOB), 'utf8') == {
        'encoding': 'base64', 'data': '', 'byte_length': 0}
    assert value(b'', column(FieldType.BLOB, charset=255), 'utf8') == ''
    assert value(b'\xff\x00', column(FieldType.GEOMETRY), 'utf8') == {
        'encoding': 'base64', 'data': '/wA=', 'byte_length': 2}


def test_duplicate_labels_have_exact_unique_lookup_keys():
    from types import SimpleNamespace
    result = columns(SimpleNamespace(description=[
        column(FieldType.NEWDECIMAL, 'été'),
        column(FieldType.NEWDECIMAL, 'été'),
        column(FieldType.NEWDECIMAL, 'été#2')]))
    assert [c['name'] for c in result] == ['été', 'été#3', 'été#2']
    assert [c['native_name'] for c in result] == ['été', 'été', 'été#2']
    assert all(c['cell_type'] == 'text' for c in result)


def test_typed_named_and_positional_parameters():
    data = [{'encoding': 'integer', 'data': '18446744073709551615'},
            {'encoding': 'decimal', 'data': '1234567890123456789.123456'},
            {'encoding': 'base64', 'data': '/wA=', 'byte_length': 2}]
    expected = (18446744073709551615,
                Decimal('1234567890123456789.123456'), b'\xff\x00')
    assert parameters(data) == expected
    assert parameters(dict(zip(['a', 'b', 'c'], data))) == dict(
        zip(['a', 'b', 'c'], expected))


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


@pytest.mark.parametrize('values', [[], {}, [42], {'name': 42}])
def test_studio_dual_shape_reaches_provider_without_rewriting(values):
    from dataclasses import replace
    from unittest.mock import patch
    from tools.tests.test_cdeadmin_data_studio import harness, endpoint_payload
    context, provider, _registry, service = harness()
    contributions = provider.data_studio_contributions()
    contributions['languages'] = tuple(
        replace(item, parameter_shape='object-or-array')
        for item in contributions['languages'])
    with patch.object(provider, 'data_studio_contributions',
                      return_value=contributions):
        service.open_session(context, endpoint_payload(context), 'example-sql')
    service.execute(context, 'session-one', 'native source', parameters=values)
    request = next(request for action, request in provider.calls
                   if action == 'execute')
    assert request['parameters'] == values


def test_mysql_language_admits_both_binding_styles():
    assert MYSQL_PROFILE.parameter_shape == 'object-or-array'


def test_native_column_charset_overrides_connection_command_encoding():
    assert value(b'\xe9\x80\x81', column(FieldType.STRING, charset=8),
                 'utf8') == 'é€\x81'
    assert value('日本'.encode('shift_jis'),
                 column(FieldType.STRING, charset=13), 'utf8') == '日本'


def test_unmapped_charset_preserves_bytes_and_declares_json_cell():
    from types import SimpleNamespace
    description = column(FieldType.STRING, charset=32)
    assert value(b'AB', description, 'utf8') == {
        'encoding': 'base64', 'data': 'QUI=', 'byte_length': 2,
        'native_charset': 'armscii8', 'charset_id': 32}
    assert columns(SimpleNamespace(description=[description]))[0][
        'cell_type'] == 'json'
