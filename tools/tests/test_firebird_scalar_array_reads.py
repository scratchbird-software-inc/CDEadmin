"""Bounded scalar slices retain native decoding and transaction ownership."""
from ctypes import byref, create_string_buffer, memmove
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.tests.test_firebird_array_chunks import descriptor
from firebird.driver import fbapi
from pgadmin.cdeadmin.providers.firebird import scalar_arrays, varying_arrays
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('cap', [4, 1024 * 1024])
@pytest.mark.parametrize('failure', [
    '', 'short', 'decode', 'subtype', 'width'])
def test_scalar_slices_use_original_transaction_and_exact_decode(
        cap, failure):
    bounds = descriptor([(-1, 2)], 4)
    bounds.array_desc_dtype = fbapi.blr_long
    bounds.array_desc_scale = -2
    if failure == 'width':
        bounds.array_desc_length = 8
    cursor = SimpleNamespace(
        _connection=MagicMock(), _transaction=MagicMock(), _encoding='utf8',
        _stmt=SimpleNamespace(_out_buffer=create_string_buffer(8)))
    desc = SimpleNamespace(relation='T', field='A', offset=0, length=8)
    catalog = cursor._transaction.cursor.return_value.__enter__.return_value
    catalog.fetchone.return_value = None if failure == 'subtype' else (1,)
    calls = []

    def lookup(status, db, transaction, relation, field, target):
        memmove(byref(target), byref(bounds), len(bytes(bounds)))

    def get(status, db, transaction, array_id, part, data, length):
        assert transaction is cursor._transaction._get_handle.return_value
        assert len(data) <= cap
        coordinates = part.array_desc_bounds[0]
        values = range(coordinates.array_bound_lower,
                       coordinates.array_bound_upper + 1)
        packed = b''.join(v.to_bytes(4, 'little', signed=True) for v in values)
        memmove(data, packed, len(packed))
        calls.append(len(data))
        if failure == 'short':
            length.value -= 1

    def decode(width, dtype, subtype, scale, depth, shape, data, offset):
        assert (width, dtype, subtype, scale, depth, offset) == (
            4, fbapi.blr_long, 1, -2, 0, 0)
        return ([int.from_bytes(data.raw[i:i+4], 'little', signed=True)
                 for i in range(0, len(data), 4)],
                len(data) - int(failure == 'decode'))

    cursor._extract_db_array_to_list = decode
    with patch.object(scalar_arrays.api, 'get_api') as native, \
            patch.object(varying_arrays, 'SLICE_BYTES', cap):
        native.return_value.isc_array_lookup_bounds.side_effect = lookup
        native.return_value.isc_array_get_slice.side_effect = get
        if failure:
            with pytest.raises(RelationalClientError):
                scalar_arrays.read(cursor, desc)
        else:
            assert scalar_arrays.read(cursor, desc) == (True, [-1, 0, 1, 2])
            assert calls == ([4] * 4 if cap == 4 else [16])
    cursor._connection.cursor.assert_not_called()
