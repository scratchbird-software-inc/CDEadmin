"""Exact fixed-array values and bounded reads across chunk boundaries."""
from ctypes import memmove
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.tests.test_firebird_array_chunks import descriptor
from pgadmin.cdeadmin.providers.firebird import varying_arrays as arrays
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('charset,values,expected', [
    (1, [b'\0\xff\0 ', b'    ', b'\0' * 4, b'abcd'],
     [b'\0\xff\0 ', b'    ', b'\0' * 4, b'abcd']),
    (4, ['é '.encode(), b'a\0', b'  ', '🐦 '.encode()],
     ['é ', 'a\0', '  ', '🐦 ']),
])
@pytest.mark.parametrize('cap', [8, 1024 * 1024])
@pytest.mark.parametrize('failure', ['', 'short', 'native', 'padding'])
def test_fixed_values_and_failures_across_native_rectangles(
        charset, values, expected, cap, failure):
    if charset == 1 and failure == 'padding':
        # Every byte is valid in OCTETS, including apparent text padding.
        failure = ''
    width = 4 if charset == 1 else 8
    desc = descriptor([(-1, 0), (2, 3)], width)
    before = bytes(desc)
    cursor = SimpleNamespace(_connection=MagicMock(), _transaction=MagicMock(),
                             _encoding='utf8')
    index = 0
    sizes = []

    def get(transaction, array_id, sdl, params, data):
        nonlocal index
        assert transaction is cursor._transaction._tra
        assert int.from_bytes(sdl[4:6], 'little') == (
            1 if charset == 1 else 127)
        sizes.append(len(data))
        assert len(data) <= cap
        if failure == 'native':
            raise ValueError('native failure')
        count = len(data) // width
        fill = b'x' if failure == 'padding' else b' '
        packed = b''.join(v.ljust(width, fill)
                          for v in values[index:index+count])
        index += count
        memmove(data, packed, len(packed))
        return len(packed) - int(failure == 'short')

    cursor._connection._att.get_slice.side_effect = get
    with patch.object(arrays, 'SLICE_BYTES', cap):
        if failure:
            with pytest.raises((RelationalClientError, ValueError)):
                arrays.read_fixed(cursor, None, desc, [2, 2], 2, charset)
        else:
            assert arrays.read_fixed(cursor, None, desc, [2, 2], 2,
                                     charset) == [expected[:2], expected[2:]]
            assert len(sizes) == (4 * width // cap if cap == 8 else 1)
    assert bytes(desc) == before
