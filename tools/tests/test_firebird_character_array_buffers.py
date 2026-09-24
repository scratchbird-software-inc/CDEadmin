"""No stale bytes or silent C-string truncation in native array packing."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import (
    TemporalArrayCursor,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from firebird.driver import fbapi


@pytest.mark.parametrize('dtype', [
    fbapi.blr_text, fbapi.blr_text2, fbapi.blr_varying, fbapi.blr_varying2])
def test_nested_fresh_buffers_padding_offsets_and_multibyte(dtype):
    native = TemporalArrayCursor(
        SimpleNamespace(sql_dialect=3, _encoding='utf8'), MagicMock())
    varying = dtype in (fbapi.blr_varying, fbapi.blr_varying2)
    size = 10 if varying else 8
    values = [['abcdefgh', 'x'], ['', 'é🐦']]
    data = create_string_buffer(b'!' * (4 * size + 4), 4 * size + 4)
    try:
        end = native._fill_db_array_buffer(
            size, dtype, 0, 0, 0, [2, 2], values,
            create_string_buffer(b'OLDVALUE', size), data, 2)
        expected = b''.join(item.encode('utf8').ljust(
            size, b'\0' if varying else b' ')
            for row in values for item in row)
        assert end == 2 + 4 * size
        assert data.raw == b'!!' + expected + b'!!'
    finally:
        native.close()


@pytest.mark.parametrize('dtype,value,encoding', [
    (fbapi.blr_varying, 'a\0b', 'utf8'),
    (fbapi.blr_varying, '123456789', 'utf8'),
    (fbapi.blr_text, '12345678901', 'utf8'),
    (fbapi.blr_text, '🐦🐦🐦', 'utf8'),
    (fbapi.blr_text, 'é', 'ascii'),
    (fbapi.blr_text, b'bytes', 'utf8'),
    (fbapi.blr_text, None, 'utf8'),
])
def test_invalid_input_fails_before_slice_publication(dtype, value, encoding):
    native = TemporalArrayCursor(
        SimpleNamespace(sql_dialect=3, _encoding=encoding), MagicMock())
    try:
        with pytest.raises(RelationalClientError):
            native._fill_db_array_buffer(
                10, dtype, 0, 0, 0, [1], [value],
                create_string_buffer(10), create_string_buffer(10), 0)
    finally:
        native.close()


def test_fixed_char_preserves_embedded_nul_bytes():
    native = TemporalArrayCursor(
        SimpleNamespace(sql_dialect=3, _encoding='utf8'), MagicMock())
    data = create_string_buffer(8)
    try:
        native._fill_db_array_buffer(
            8, fbapi.blr_text, 0, 0, 0, [1], ['a\0b'],
            create_string_buffer(8), data, 0)
        assert data.raw == b'a\0b     '
    finally:
        native.close()
