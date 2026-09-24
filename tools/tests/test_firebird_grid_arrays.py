"""Exact, native-bound array input rejects ctypes wrapping and rounding."""
from decimal import Decimal

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.grid_arrays import convert
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def spec(code=8, scale=0, subtype=0, bounds=((0, 0),)):
    return dict(type=code, scale=scale, subtype=subtype, bounds=bounds)


@pytest.mark.parametrize('code,bits', [(7, 16), (8, 32), (16, 64), (26, 128)])
@pytest.mark.parametrize('sign', [-1, 1])
def test_exact_native_integer_boundaries(code, bits, sign):
    limit = -(1 << (bits-1)) if sign < 0 else (1 << (bits-1))-1
    assert convert([str(limit)], spec(code)) == [limit]
    with pytest.raises(RelationalClientError, match='range'):
        convert([str(limit+sign)], spec(code))


@pytest.mark.parametrize('value', [
    True, None, 1.2, '1.2', '1e3', 'NaN', '\u0661', '', {}, [1]])
def test_invalid_integer_elements(value):
    with pytest.raises(RelationalClientError):
        convert([value], spec())


@pytest.mark.parametrize('value', ['1.234', '327.68', '-327.69', '1e9999999'])
def test_fixed_point_rejects_rounding_and_overflow(value):
    with pytest.raises(RelationalClientError):
        convert([value], spec(7, -2, 1))


def test_exact_scaled_boundaries_and_nested_non_one_based_dimensions():
    descriptor = spec(7, -2, 1, ((-1, 0), (3, 4)))
    assert convert([['327.67', '-327.68'], ['0', '1e-2']], descriptor) == [
        [Decimal('327.67'), Decimal('-327.68')],
        [Decimal('0'), Decimal('0.01')]]
    assert convert(None, descriptor) is None
    for invalid in ([], [1, 2], [[1], [2]], [[1, 2, 3], [4, 5, 6]]):
        with pytest.raises(RelationalClientError, match='dimension'):
            convert(invalid, descriptor)


@pytest.mark.parametrize('code,value', [
    (10, '1e100'), (10, '1e-100'), (27, '1e400'), (27, '1e-400'),
    (27, 'NaN'), (10, None)])
def test_float_array_rejects_native_width_loss(code, value):
    with pytest.raises(RelationalClientError):
        convert([value], spec(code))


def test_float_and_boolean_native_conversion():
    import math
    assert math.copysign(1, convert(['-0.0'], spec(10))[0]) == -1
    assert convert([True], spec(23)) == [True]
    for value in ('true', 1, None):
        with pytest.raises(RelationalClientError):
            convert([value], spec(23))


def test_nested_array_transport_preserves_native_scalar_precision():
    from datetime import datetime
    from pgadmin.cdeadmin.providers.firebird.grid_values import normalize_value
    values = [[-0.0, 1e-300], [datetime(1, 1, 1), (1 << 63)-1]]
    assert normalize_value(values) == [
        ['-0.0', '1e-300'], ['0001-01-01 00:00:00', '9223372036854775807']]


@pytest.mark.parametrize('rows', [[], [(8, 0, 0, 1, 0, 1)]])
def test_parameter_binding_rejects_missing_or_inconsistent_native_bounds(rows):
    from unittest.mock import MagicMock
    from firebird.driver.types import SQLDataType
    from pgadmin.cdeadmin.providers.firebird.grid_arrays import parameters
    connection, cursor = MagicMock(), MagicMock()
    statement = cursor.prepare.return_value
    meta = statement._in_meta
    meta.get_count.return_value = 1
    meta.get_type.return_value = SQLDataType.ARRAY
    catalog = connection.cursor.return_value.__enter__.return_value
    catalog.fetchall.return_value = rows
    with pytest.raises(RelationalClientError, match='metadata unavailable'):
        parameters(connection, cursor, 'INSERT INTO T(A) VALUES (?)', ([1],))
    statement.free.assert_called_once_with()


def test_binding_uses_prepared_native_destination_and_releases_statement():
    from unittest.mock import MagicMock
    from firebird.driver.types import SQLDataType
    from pgadmin.cdeadmin.providers.firebird.grid_arrays import parameters
    connection, cursor = MagicMock(), MagicMock()
    statement = cursor.prepare.return_value
    meta = statement._in_meta
    meta.get_count.return_value = 1
    meta.get_type.return_value = SQLDataType.ARRAY
    meta.get_relation.return_value = 'Target View'
    meta.get_field.return_value = 'Native Field'
    catalog = connection.cursor.return_value.__enter__.return_value
    catalog.fetchall.return_value = [(16, 0, 0, 0, -1, -1)]
    source = 'INSERT INTO "Target View"("Native Field") VALUES (?)'
    assert parameters(connection, cursor, source,
                      (['9223372036854775807'],)) == ([9223372036854775807],)
    cursor.prepare.assert_called_once_with(source)
    assert catalog.execute.call_args.args[1] == ('Target View', 'Native Field')
    statement.free.assert_called_once_with()


def test_scalars_do_not_add_preparation_or_catalog_roundtrips():
    from unittest.mock import MagicMock
    from pgadmin.cdeadmin.providers.firebird.grid_arrays import parameters
    connection, cursor = MagicMock(), MagicMock()
    values = ('text', 1, None, Decimal('2.01'), b'bytes')
    assert parameters(connection, cursor, 'unused', values) is values
    cursor.prepare.assert_not_called()
    connection.cursor.assert_not_called()


@pytest.mark.parametrize('code,subtype,scale,kind', [
    (7, 0, 0, 'integer'), (8, 1, -2, 'decimal'), (16, 0, 0, 'integer'),
    (26, 2, -4, 'decimal'), (10, 0, 0, 'float32'),
    (27, 0, 0, 'float64'), (23, 0, 0, 'boolean'), (12, 0, 0, None),
    (14, 0, 0, None), (24, 0, 0, 'decfloat'), (25, 0, 0, 'decfloat'),
])
def test_only_verified_element_types_advertise_editor(
        code, subtype, scale, kind):
    from unittest.mock import MagicMock
    from pgadmin.cdeadmin.providers.firebird.grid_arrays import editor_specs
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [(code, subtype, scale, 0, -1, 2)]
    result = editor_specs(connection, [{
        'native_type': 'ARRAY', 'source_relation': 'T', 'source_field': 'A',
        'native_name': 'ALIAS'}])
    assert bool(result) == bool(kind)
    if kind:
        assert result['ALIAS']['element_kind'] == kind
        assert result['ALIAS']['bounds'] == [(-1, 2)]
        assert result['ALIAS']['scale'] == scale


@pytest.mark.parametrize('code,values', [
    (24, ['9.999999999999999e384', '1e-398', '-0', '1234567890123456']),
    (25, ['9.999999999999999999999999999999999e6144', '1e-6176', '-0',
          '1234567890123456789012345678901234']),
])
def test_decfloat_arrays_preserve_native_boundaries(code, values):
    for value in values + ['NaN', '-NaN', 'sNaN', '-sNaN', 'Infinity',
                           '-Infinity']:
        actual = convert([value], spec(code))[0]
        assert actual.compare_total(Decimal(value)) == 0


@pytest.mark.parametrize('code,values', [
    (24, ['1e385', '1e-399', '12345678901234567']),
    (25, ['1e6145', '1e-6177', '12345678901234567890123456789012345']),
])
def test_decfloat_arrays_reject_silent_packing_rounding(code, values):
    for value in values + ['NaN12', ' 1', '1_0', '', True, None, 0.1]:
        with pytest.raises(RelationalClientError):
            convert([value], spec(code))


@pytest.mark.parametrize('code', [24, 25])
def test_decfloat_binding_is_independent_of_ambient_decimal_context(code):
    from decimal import localcontext, InvalidOperation, ROUND_DOWN
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.traps[InvalidOperation] = False
        assert convert(['1234567890123456'], spec(code)) == [
            Decimal('1234567890123456')]
        with pytest.raises(RelationalClientError):
            convert(['1e999999999999999999999999999999999'], spec(code))
