"""Native ARRAY coordinates, allocation bounds and stream ownership."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from firebird.driver import fbapi
from pgadmin.cdeadmin.providers.firebird import array_stream
from pgadmin.cdeadmin.providers.firebird.result_stream import ResultStream
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def reader(monkeypatch, bounds=((-2, -1), (3, 602)), width=4):
    native = fbapi.ISC_ARRAY_DESC(0)
    native.array_desc_dimensions = len(bounds)
    native.array_desc_dtype = fbapi.blr_long
    for slot, (lower, upper) in zip(native.array_desc_bounds, bounds):
        slot.array_bound_lower, slot.array_bound_upper = lower, upper
    monkeypatch.setattr(array_stream.character_arrays, 'metadata',
                        lambda *args: None)
    monkeypatch.setattr(array_stream.scalar_arrays, 'describe',
                        lambda *args: (native, width, 0))
    buffer = create_string_buffer(bytes(fbapi.ISC_QUAD(1, 2)))
    cursor = SimpleNamespace(_stmt=SimpleNamespace(_out_buffer=buffer))
    return array_stream.ArrayReader(cursor, SimpleNamespace(
        relation='T', field='A', offset=0, length=8))


def test_array_coordinates_cross_dimensions_without_large_allocation(
        monkeypatch):
    value = reader(monkeypatch)
    calls = []

    def read(cursor, array_id, bounds, width, subtype, shape):
        coordinates = [(b.array_bound_lower, b.array_bound_upper) for b in
                       bounds.array_desc_bounds[:2]]
        calls.append((coordinates, shape))
        assert shape[0] == 1
        assert shape[1] <= 256
        assert width * shape[1] <= 65536
        return [[i for i in range(shape[1])]]

    monkeypatch.setattr(array_stream.scalar_arrays, 'rectangle', read)
    offset, positions = 0, []
    while offset < value.count:
        chunk = value.read(offset)
        positions.append(chunk['coordinates'])
        assert chunk['next_offset'] > offset
        offset = chunk['next_offset']
    assert offset == 1200
    assert positions == [[-2, 3], [-2, 259], [-2, 515],
                         [-1, 3], [-1, 259], [-1, 515]]
    assert calls[2] == ([(-2, -2), (515, 602)], [1, 88])
    assert chunk['complete']
    value.close()
    with pytest.raises(RelationalClientError):
        value.read(0)


def test_array_identity_copied_before_next_cursor_row(monkeypatch):
    value = reader(monkeypatch)
    value.cursor._stmt._out_buffer[0] = b'\x7f'
    assert bytes(value.array_id) == bytes(fbapi.ISC_QUAD(1, 2))


def test_array_byte_bound_precedes_element_bound(monkeypatch):
    value = reader(monkeypatch, width=16000)
    native = Mock(return_value=[[1, 2, 3, 4]])
    monkeypatch.setattr(array_stream.scalar_arrays, 'rectangle', native)
    assert value.read(0)['next_offset'] == 4
    assert native.call_args.args[-1] == [1, 4]


@pytest.mark.parametrize('offset', [True, -1, 1200, '0', None])
def test_array_offset_rejected_before_native_read(monkeypatch, offset):
    value = reader(monkeypatch)
    native = Mock()
    monkeypatch.setattr(array_stream.scalar_arrays, 'rectangle', native)
    with pytest.raises(RelationalClientError):
        value.read(offset)
    native.assert_not_called()


class Array:
    def __init__(self):
        self.describe = Mock(return_value={'bounds': [[-1, 0]],
                                           'element_count': 2})
        self.read = Mock(side_effect=[
            {'offset': 0, 'next_offset': 1, 'coordinates': [-1],
             'values': [12], 'complete': False},
            {'offset': 1, 'next_offset': 2, 'coordinates': [0],
             'values': [13], 'complete': True},
        ])
        self.close = Mock()


def owned_stream(array, count=1):
    cursor = Mock()
    cursor.fetchone.side_effect = [(array,)] + [(None,)] * (count-1) + [None]
    return ResultStream(cursor, [], (), Array)


def test_last_array_pull_retry_cannot_mutate_cache_or_reread_native():
    value = Array()
    stream = owned_stream(value)
    page = stream.fetch(0)
    reference = page['rows'][0][0]['array_reference']
    value.read.assert_not_called()
    chunk = stream.read_array(reference, 0)
    chunk['values'][0] = 'modified'
    assert stream.read_array(reference, 0)['values'] == [12]
    assert value.read.call_count == 1
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 2)
    assert stream.read_array(reference, 1)['complete']
    assert stream.read_array(reference, 1)['complete']
    assert value.read.call_count == 2
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 0)
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 2)
    stream.close()
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 1)


def test_page_replacement_expires_array_reference():
    value = Array()
    stream = owned_stream(value, 101)
    reference = stream.fetch(0)['rows'][0][0]['array_reference']
    stream.fetch(1)
    value.close.assert_called_once()
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 0)
    value.read.assert_not_called()
    stream.close()


def test_array_failure_requires_cleanup_before_further_native_work():
    value = Array()
    value.read.side_effect = OSError('native failure')
    stream = owned_stream(value)
    reference = stream.fetch(0)['rows'][0][0]['array_reference']
    with pytest.raises(OSError):
        stream.read_array(reference, 0)
    with pytest.raises(RelationalClientError):
        stream.read_array(reference, 0)
    value.read.assert_called_once()
    stream.close()
    value.close.assert_called_once()


def test_unknown_varying_charset_never_uses_cstring_fallback(monkeypatch):
    from pgadmin.cdeadmin.providers.firebird import character_arrays
    cursor = SimpleNamespace(_stmt=SimpleNamespace(
        _out_buffer=create_string_buffer(bytes(fbapi.ISC_QUAD(1, 2)))))
    description = SimpleNamespace(relation='T', field='A', offset=0, length=8)
    monkeypatch.setattr(character_arrays, 'metadata',
                        lambda *args: (37, 8, 200, 4))
    monkeypatch.setattr(character_arrays, 'layout',
                        lambda *args: (object(), [1], 34, 1))
    native = Mock()
    monkeypatch.setattr(character_arrays.api, 'get_api', native)
    with pytest.raises(RelationalClientError, match='lossless slice adapter'):
        character_arrays.read(cursor, description)
    with pytest.raises(RelationalClientError, match='lossless slice adapter'):
        character_arrays.encode(['a\0b'], [1], (37, 8, 200, 4), 'utf8')
    native.assert_not_called()


def test_none_charset_decodes_exact_stored_bytes_in_attachment_encoding():
    from pgadmin.cdeadmin.providers.firebird.varying_arrays import (
        _decode_nested,
    )
    values = [[b'\xc3\xa9\0 ', b''], [b' \0', b'abc     ']]
    assert _decode_nested(values, 'utf8') == [
        ['é\0 ', ''], [' \0', 'abc     ']]
    with pytest.raises(UnicodeDecodeError):
        _decode_nested([[b'\xff']], 'utf8')


def test_gbk_length_keeps_euro_separate_from_multibyte_trail():
    from pgadmin.cdeadmin.providers.firebird.varying_arrays import _text_length
    assert _text_length(b'\x80\0 \x81\x80', 67) == 4
    with pytest.raises(UnicodeDecodeError):
        _text_length(b'\x81', 67)
