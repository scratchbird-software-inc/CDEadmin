"""Grid transport preserves native predicate values and exact wire values."""
from decimal import Decimal
from datetime import date, datetime, time
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.grid_values import input_kind
from pgadmin.cdeadmin.providers.firebird.grid_values import (
    input_kinds, materialize, normalize_value, parameter, bind_value,
    table_operations,
)
from firebird.driver.types import SQLDataType
from firebird.driver import DatabaseError
from pgadmin.cdeadmin.providers.relational_admin import _RowIdentity


@pytest.mark.parametrize('value,expected', [
    (date(1, 1, 1), '0001-01-01'),
    (datetime(1, 1, 1), '0001-01-01 00:00:00'),
    (datetime(9999, 12, 31, 23, 59, 59, 999900),
     '9999-12-31 23:59:59.9999'),
    (time(0, 0, 0, 100), '00:00:00.0001'),
    (time(12, 34, 56, 123400), '12:34:56.1234'),
])
def test_temporal_grid_and_identity_share_native_lexical_precision(
        value, expected):
    assert normalize_value(value) == expected
    assert parameter(value) == expected
    identity = _RowIdentity((), ('T',), ('K',), (value,), {'K': value}, 0)
    assert ADMINISTRATION._identity_predicate(identity) == (
        '"K" = ?', (expected,))


def test_temporal_parameter_refuses_silent_precision_loss():
    with pytest.raises(ValueError, match='100 microseconds'):
        parameter(time(0, 0, 0, 1))


@pytest.mark.parametrize('value,expected', [
    (0.1, '0.1'), (-0.0, '-0.0'), (0.0, '0.0'),
    (1.7976931348623157e308, '1.7976931348623157e+308'),
    (2.2250738585072014e-308, '2.2250738585072014e-308'),
])
def test_float_grid_uses_roundtrip_text_and_preserves_negative_zero(
        value, expected):
    import json
    import struct
    result = json.loads(json.dumps(normalize_value(value)))
    assert result == expected
    assert struct.pack('d', float(result)) == struct.pack('d', value)
    assert struct.pack('d', bind_value({'encoding': 'float64',
                                       'data': result})) == struct.pack(
                                           'd', value)


@pytest.mark.parametrize('value', [
    'NaN', 'Infinity', '-Infinity', '1e400', '1e-400',
    '1_2', ' 1', '١', '', None, True])
def test_float_binding_rejects_invalid_or_unrepresentable_input(value):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    with pytest.raises(RelationalClientError):
        bind_value({'encoding': 'float64', 'data': value})


@pytest.mark.parametrize('value', ['1e100', '-1e100', '1e-100', '-1e-100'])
def test_float32_rejects_overflow_and_zero_underflow(value):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    with pytest.raises(RelationalClientError, match='range'):
        bind_value({'encoding': 'float32', 'data': value})


@pytest.mark.parametrize('value', [
    '0.1', '-0.0', '1.401298464324817e-45', '3.4028234663852886e38'])
def test_float32_native_width(value):
    import struct
    actual = bind_value({'encoding': 'float32', 'data': value})
    assert struct.pack('f', actual) == struct.pack('f', float(value))


@pytest.mark.parametrize('value_type,expected', [
    (str, 'text'), (int, 'integer'), (Decimal, 'decimal'), (bool, 'boolean'),
    (float, None), (bytes, None), (list, None), ('INTEGER', None),
])
def test_hints_use_driver_types_not_names(value_type, expected):
    assert input_kind(value_type) == expected


@pytest.mark.parametrize('code,subtype,scale,charset,expected', [
    (SQLDataType.INT128, 0, 0, 0, 'integer'),
    (SQLDataType.INT128, 1, -18, 0, 'decimal'),
    (SQLDataType.INT64, 2, -4, 0, 'decimal'),
    (SQLDataType.DEC16, 0, 0, 0, 'decfloat'),
    (SQLDataType.DEC34, 0, 0, 0, 'decfloat'),
    (SQLDataType.FLOAT, 0, 0, 0, 'float32'),
    (SQLDataType.DOUBLE, 0, 0, 0, 'float64'),
    (SQLDataType.DATE, 0, 0, 0, 'text'),
    (SQLDataType.TIME, 0, 0, 0, 'text'),
    (SQLDataType.TIMESTAMP, 0, 0, 0, 'text'),
    (SQLDataType.VARYING, 0, 0, 4, 'text'),
    (SQLDataType.VARYING, 0, 0, 1, 'binary'),
    (SQLDataType.TEXT, 0, 0, 1, 'binary'),
    (SQLDataType.BLOB, 1, 0, 4, 'text'),
    (SQLDataType.BLOB, 0, 0, 0, 'binary'),
    (SQLDataType.ARRAY, 0, 0, 0, None),
])
def test_native_metadata_wins_over_incomplete_dbapi(
        code, subtype, scale, charset, expected):
    cursor = SimpleNamespace(description=[('VALUE', None)],
                             statement=SimpleNamespace(_out_desc=[
                                 SimpleNamespace(datatype=code,
                                                 subtype=subtype, scale=scale,
                                                 charset=charset, length=16,
                                                 nullable=True, relation='T',
                                                 field='VALUE', owner='O')]))
    assert input_kinds(cursor) == (expected,)


@pytest.mark.parametrize('value', [b'', b'\x00\xff\x7f', bytes(range(256))])
def test_binary_wire_roundtrip(value):
    envelope = normalize_value(value)
    assert bind_value(envelope) == value
    assert envelope['byte_length'] == len(value)


@pytest.mark.parametrize('envelope', [
    {}, {'encoding': 'base64', 'data': 'AA==', 'byte_length': True},
    {'encoding': 'base64', 'data': 'AA==', 'byte_length': 2},
    {'encoding': 'base64', 'data': 'AR==', 'byte_length': 1},
    {'encoding': 'base64', 'data': 'AA', 'byte_length': 1},
    {'encoding': 'base64', 'data': 'é', 'byte_length': 1},
    {'encoding': 'hex', 'data': '00', 'byte_length': 1},
])
def test_binary_envelope_is_strict(envelope):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    with pytest.raises(RelationalClientError):
        bind_value(envelope)


def test_binary_insert_binding_does_not_decode_ordinary_text():
    request = {'resource_kind': 'table',
               'target_resource': {'resource_kind': 'table',
                                   'display_path': ['T']},
               'draft': {'values': {'B': normalize_value(b'\x00\xff'),
                                    'T': 'AP8='}}}
    assert ADMINISTRATION._compile_insert(request)['parameters'] == (
        b'\x00\xff', 'AP8=')


@pytest.mark.parametrize('failed', [False, True])
def test_blob_materialized_before_identity_and_closed_on_failure(failed):
    class Blob:
        read = MagicMock(return_value='text')
        close = MagicMock()
    value = Blob()
    if failed:
        value.read.side_effect = RuntimeError('read failed')
    with patch('firebird.driver.core.BlobReader', Blob):
        if failed:
            with pytest.raises(RuntimeError):
                materialize(value)
        else:
            assert materialize(value) == 'text'
    value.close.assert_called_once_with()


def test_table_admission_prepares_without_executing_and_frees_statements():
    handle = MagicMock()
    cursor = handle.cursor.return_value.__enter__.return_value
    statements = [MagicMock() for _ in range(3)]
    cursor.prepare.side_effect = [statements[0], statements[1],
                                  DatabaseError('denied'), statements[2]]
    assert table_operations(handle, 'T"X', ['V']) == {
        'update': ['V'], 'insert': ['V'], 'delete': False, 'defaults': True}
    assert cursor.prepare.call_args_list[0].args[0] == (
        'UPDATE "T""X" SET "V" = ? WHERE 1 = 0')
    cursor.execute.assert_not_called()
    for statement in statements:
        statement.free.assert_called_once_with()
    handle.commit.assert_not_called()
    handle.rollback.assert_not_called()


def test_firebird_table_default_values_without_generic_dialect_fallback():
    assert ADMINISTRATION._compile_insert({
        'resource_kind': 'table',
        'target_resource': {'resource_kind': 'table', 'display_path': ['T']},
        'draft': {'values': {}}}) == {
            'source': 'INSERT INTO "T" DEFAULT VALUES', 'parameters': ()}


def test_decfloat_identity_uses_total_order_including_key_and_null():
    identity = _RowIdentity((), ('T',), ('K',), (Decimal('NaN'),),
                            {'K': Decimal('NaN'), 'D': Decimal('-0'),
                             'N': None, 'F': Decimal('1.00')}, 0,
                            decfloat_columns=('K', 'D', 'N'))
    source, params = ADMINISTRATION._identity_predicate(identity)
    assert source == ('TOTALORDER("K", ?) = 0 AND TOTALORDER("D", ?) = 0 '
                      'AND "N" IS NULL AND "F" = ?')
    assert [str(v) for v in params] == ['NaN', '-0', '1.00']


def test_grid_retains_native_identity_but_emits_lossless_values():
    handle = MagicMock()
    cursor = handle.cursor.return_value
    cursor.description = [('ID', int), ('V', Decimal), ('TXT', str),
                          ('B', bool)]
    original = (2 ** 100, Decimal('12345678901234567890.1234'), 'null', False)
    cursor.fetchall.return_value = [original]
    client = MagicMock()
    client.config.execute_on_connection = False
    with patch.object(ADMINISTRATION, '_primary_key', return_value=('ID',)):
        page = ADMINISTRATION.read_rows(client, {
            '_provider_route': {'database': 'owned'}, 'session_id': 'owned',
            'target_resource': {'resource_kind': 'table',
                                'display_path': ['T']}}, connection=handle)
    token = page['rows'][0]['identity_token']
    try:
        assert page['rows'][0]['values'] == {
            'ID': str(original[0]), 'V': str(original[1]),
            'TXT': 'null', 'B': False}
        assert [c['input_kind'] for c in page['columns']] == [
            'integer', 'decimal', 'text', 'boolean']
        identity = ADMINISTRATION._row_identities[token]
        assert identity.key_values == (original[0],)
        assert identity.original['V'] == original[1]
    finally:
        ADMINISTRATION._row_identities.pop(token, None)
