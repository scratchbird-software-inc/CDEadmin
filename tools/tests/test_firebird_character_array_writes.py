"""Exact character slice binding and native metadata ownership."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.character_arrays import (
    encode, layout, pack,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from firebird.driver.types import SQLDataType


@pytest.mark.parametrize('code', [14, 37])
def test_character_width_is_not_stored_byte_width(code):
    expected = b''.join(value.encode('utf8').ljust(
        34 if code == 37 else 32, b'\0' if code == 37 else b' ')
        for value in ('é' * 8, '€' * 8, '', 'x'))
    assert encode([['é' * 8, '€' * 8], ['', 'x']], [2, 2],
                  (code, 8, 21, 4), 'utf8') == expected


@pytest.mark.parametrize('value', [
    ['123456789', ''], ['é' * 9, ''], [None, ''], [True, ''],
    [b'bytes', ''], ['', 'a\0b'], ['x'], [['x'], ['y']],
])
def test_reject_lossy_or_misshaped_varying_values(value):
    with pytest.raises(RelationalClientError):
        encode(value, [2], (37, 8, 4, 4), 'utf8')


def test_unencodable_and_fixed_embedded_nul():
    with pytest.raises(RelationalClientError):
        encode(['é'], [1], (14, 8, 2, 1), 'ascii')
    assert encode(['a\0b'], [1], (14, 8, 4, 4), 'utf8') == (
        b'a\0b' + b' ' * 29)


def test_native_write_failure_releases_transferred_metadata():
    cursor = SimpleNamespace(_encoding='utf8', _connection=MagicMock(),
                             _transaction=MagicMock())
    meta = MagicMock()
    meta.get_count.return_value = 2
    meta.get_type.side_effect = [SQLDataType.ARRAY, SQLDataType.LONG]
    returned_meta = MagicMock()
    native_pack = MagicMock(return_value=(returned_meta,
                                          create_string_buffer(20)))
    original = (['text'], 42)
    prefix = 'pgadmin.cdeadmin.providers.firebird.character_arrays.'
    with patch(prefix + 'metadata', return_value=(14, 8, 4, 4)), \
            patch(prefix + 'layout', return_value=(None, [1], 32, 1)), \
            patch(prefix + 'api.get_api') as api:
        api.return_value.isc_array_put_slice.side_effect = ValueError('native')
        with pytest.raises(ValueError, match='native'):
            pack(cursor, meta, None, original, native_pack)
    assert original == (['text'], 42)
    assert native_pack.call_args.args[2] == [None, 42]
    returned_meta.release.assert_called_once_with()


def test_wrong_parameter_count_remains_a_driver_error():
    meta, native = MagicMock(), MagicMock()
    meta.get_count.return_value = 2
    assert pack(None, meta, None, [1], native) is native.return_value
    native.assert_called_once_with(meta, None, [1])


def test_invalid_character_rejected_before_delegated_packing():
    cursor = SimpleNamespace(_encoding='utf8')
    meta, native = MagicMock(), MagicMock()
    meta.get_count.return_value = 1
    meta.get_type.return_value = SQLDataType.ARRAY
    prefix = 'pgadmin.cdeadmin.providers.firebird.character_arrays.'
    with patch(prefix + 'metadata', return_value=(37, 8, 4, 4)), \
            patch(prefix + 'layout', return_value=(None, [1], 34, 1)):
        with pytest.raises(RelationalClientError):
            pack(cursor, meta, None, [['a\0b']], native)
    native.assert_not_called()


@pytest.mark.parametrize('description', [
    (14, 16384, 4, 4), (37, 21845, 3, 3)])
def test_slice_descriptor_overflow_rejected_before_native_call(description):
    cursor = SimpleNamespace(_connection=MagicMock())
    with pytest.raises(RelationalClientError, match='width out of range'):
        layout(cursor, 'T', 'A', description)
