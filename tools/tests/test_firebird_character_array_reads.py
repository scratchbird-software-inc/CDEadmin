"""Scoped decoder delegates scalars and always restores native row buffers."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.character_arrays import unpack
from firebird.driver.types import SQLDataType


def fixture():
    buffer = create_string_buffer(b'\0\0\1\0', 4)
    descriptions = [SimpleNamespace(datatype=kind, null_offset=index)
                    for index, kind in enumerate([
                        SQLDataType.ARRAY, SQLDataType.TEXT,
                        SQLDataType.ARRAY, SQLDataType.ARRAY])]
    return SimpleNamespace(_stmt=SimpleNamespace(
        _out_buffer=buffer, _out_desc=descriptions))


@pytest.mark.parametrize('failure', [False, True])
def test_restore_row_buffer_on_scalar_success_or_failure(failure):
    cursor = fixture()
    original = cursor._stmt._out_buffer.raw

    def native():
        assert cursor._stmt._out_buffer.raw == b'\1\0\1\0'
        if failure:
            raise ValueError('scalar failure')
        return (None, 'scalar', None, [123])

    with patch('pgadmin.cdeadmin.providers.firebird.character_arrays.read',
               side_effect=[(True, [['text']]), (False, None)]) as read:
        if failure:
            with pytest.raises(ValueError, match='scalar failure'):
                unpack(cursor, native)
        else:
            assert unpack(cursor, native) == (
                [['text']], 'scalar', None, [123])
        assert read.call_count == 2  # NULL and scalar slots are not read.
    assert cursor._stmt._out_buffer.raw == original


def test_restore_earlier_slots_when_second_array_read_fails():
    cursor = fixture()
    original = cursor._stmt._out_buffer.raw
    native = Mock()
    with patch('pgadmin.cdeadmin.providers.firebird.character_arrays.read',
               side_effect=[(True, ['first']), ValueError('native read')]):
        with pytest.raises(ValueError, match='native read'):
            unpack(cursor, native)
    native.assert_not_called()
    assert cursor._stmt._out_buffer.raw == original


def test_no_array_columns_use_unmodified_driver_result():
    cursor = fixture()
    cursor._stmt._out_desc = []
    assert unpack(cursor, lambda: ('scalar', 123)) == ('scalar', 123)
