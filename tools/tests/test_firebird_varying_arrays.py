"""Exact variable byte lengths, descriptor selection and native slice calls."""
from ctypes import memmove, string_at
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from firebird.driver import fbapi
from pgadmin.cdeadmin.providers.firebird.varying_arrays import (
    read, read_text, unpad, write)
from pgadmin.cdeadmin.providers.firebird.character_arrays import encode
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('value', [
    b'', b'\0', b' ', b'\0 ', b' \0', b'\0\xff\0', b'   ',
    bytes(range(256)), bytes(reversed(range(256)))])
@pytest.mark.parametrize('extra', [0, 1, 7])
def test_padding_pair_retains_every_original_byte_and_length(value, extra):
    width = len(value) + extra
    assert unpad(value.ljust(width, b'\0'), value.ljust(width, b' ')) == value


@pytest.mark.parametrize('zero,space', [
    (b'\0', b'  '), (b'a\0x', b'a  '), (b'a\0\0', b'a x')])
def test_inconsistent_native_slices_fail_closed(zero, space):
    with pytest.raises(RelationalClientError):
        unpad(zero, space)


def test_encoding_retains_variable_lengths_and_rejects_overflow():
    values = [[b'\0 ', b''], [b' \0', b'\xff\0']]
    assert encode(values, [2, 2], (37, 2, 1, 1), 'utf8') == [
        b'\0 ', b'', b' \0', b'\xff\0']
    with pytest.raises(RelationalClientError):
        encode([b'123'], [1], (37, 2, 1, 1), 'utf8')


@pytest.mark.parametrize('charset', [1, 127])
def test_each_write_has_an_exact_source_width_and_preserves_original_bounds(
        charset):
    desc = fbapi.ISC_ARRAY_DESC(0)
    desc.array_desc_dimensions = 1
    desc.array_desc_length = 8
    desc.array_desc_relation_name = b'T'
    desc.array_desc_field_name = b'A'
    desc.array_desc_bounds[0].array_bound_lower = -1
    desc.array_desc_bounds[0].array_bound_upper = 0
    cursor = SimpleNamespace(_connection=MagicMock(), _transaction=MagicMock())
    captured = []

    def put(transaction, array_id, sdl, params, data):
        captured.append((sdl, string_at(data, len(data))))

    cursor._connection._att.put_slice.side_effect = put
    write(cursor, fbapi.ISC_QUAD(0, 0), desc, [b'a\0b', b''], charset=charset)
    assert all(int.from_bytes(sdl[4:6], 'little') == charset
               for sdl, _ in captured)
    assert captured[0][0][3] == fbapi.blr_text2
    assert captured[0][0][6:8] == b'\3\0'
    assert captured[0][1] == b'a\0b'
    assert captured[1][0][3] == fbapi.blr_cstring2
    assert captured[1][0][6:8] == b'\1\0'
    assert captured[1][1] == b'\0'
    assert desc.array_desc_length == 8
    assert desc.array_desc_bounds[0].array_bound_lower == -1
    assert desc.array_desc_bounds[0].array_bound_upper == 0
    with pytest.raises(RelationalClientError, match='count mismatch'):
        write(cursor, fbapi.ISC_QUAD(0, 0), desc, [b'x'])
    assert len(captured) == 2


@pytest.mark.parametrize('short_read', [False, True])
def test_read_preserves_shape_and_rejects_incomplete_slice(short_read):
    desc = fbapi.ISC_ARRAY_DESC(0)
    desc.array_desc_dimensions = 2
    desc.array_desc_length = 4
    desc.array_desc_relation_name = b'T'
    desc.array_desc_field_name = b'A'
    for index in range(2):
        desc.array_desc_bounds[index].array_bound_lower = -1
        desc.array_desc_bounds[index].array_bound_upper = 0
    cursor = SimpleNamespace(_connection=MagicMock(), _transaction=MagicMock())
    values = [b'', b'\0 ', b' \0', b'abcd']
    calls = []

    def get(transaction, array_id, sdl, params, data):
        charset = int.from_bytes(sdl[4:6], 'little')
        calls.append(charset)
        packed = b''.join(v.ljust(4, b'\0' if charset == 1 else b' ')
                          for v in values)
        memmove(data, packed, len(packed))
        return len(packed) - int(short_read)

    cursor._connection._att.get_slice.side_effect = get
    if short_read:
        with pytest.raises(RelationalClientError, match='Incomplete'):
            read(cursor, fbapi.ISC_QUAD(0, 0), desc, [2, 2])
        assert calls == [1]
    else:
        assert read(cursor, fbapi.ISC_QUAD(0, 0), desc, [2, 2]) == [
            values[:2], values[2:]]
        assert calls == [1, 0]


@pytest.mark.parametrize('charset,encoding,value', [
    (2, 'ascii', 'x\0 '), (4, 'utf8', '🐦\0é '),
    (21, 'iso8859_1', 'é\0 '), (53, 'cp1252', '€\0 '),
])
@pytest.mark.parametrize('failure', ['', 'short', 'padding', 'conversion'])
def test_text_lengths_preserve_nuls_and_require_native_conversion(
        charset, encoding, value, failure):
    desc = fbapi.ISC_ARRAY_DESC(0)
    desc.array_desc_dimensions = 1
    desc.array_desc_length = 32
    desc.array_desc_relation_name = b'T'
    desc.array_desc_field_name = b'A'
    desc.array_desc_bounds[0].array_bound_lower = -1
    desc.array_desc_bounds[0].array_bound_upper = 0
    cursor = SimpleNamespace(_connection=MagicMock(), _transaction=MagicMock(),
                             _encoding='utf8')

    def get(transaction, array_id, sdl, params, data):
        assert int.from_bytes(sdl[4:6], 'little') == 127
        if failure == 'conversion':
            raise ValueError('native transliteration failure')
        fill = b'x' if failure == 'padding' else b' '
        packed = value.encode('utf8').ljust(32, fill) + b' ' * 32
        memmove(data, packed, len(packed))
        return len(packed) - int(failure == 'short')

    cursor._connection._att.get_slice.side_effect = get
    with patch('pgadmin.cdeadmin.providers.firebird.varying_arrays._read',
               return_value=[value.encode(encoding), b'']) as raw_read:
        if failure:
            with pytest.raises((RelationalClientError, ValueError)):
                read_text(cursor, fbapi.ISC_QUAD(0, 0), desc, [2], 8, charset)
        else:
            assert read_text(cursor, fbapi.ISC_QUAD(0, 0), desc, [2], 8,
                             charset) == [value, '']
        stored = raw_read.call_args.args[2]
        assert stored.array_desc_length == (32 if charset == 4 else 8)
    assert desc.array_desc_length == 32


@pytest.mark.parametrize('charset', [2, 4, 21, 53])
def test_variable_text_encoding_retains_nuls_and_exact_lengths(charset):
    assert encode(['a\0b', '', ' \0'], [3], (37, 8, charset, 4),
                  'utf8') == [b'a\0b', b'', b' \0']


@pytest.mark.parametrize('characters', [0, -1, 16384])
def test_stored_slice_width_cannot_wrap_before_native_call(characters):
    with pytest.raises(RelationalClientError, match='width out of range'):
        read_text(None, None, None, [1], characters, 4)
