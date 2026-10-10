"""ARRAY spool structure, cleanup and pre-publication validation."""
import base64
import json
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from firebird.driver import fbapi
from firebird.driver.types import SQLDataType
from pgadmin.cdeadmin.providers.firebird import array_file, array_upload
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def records():
    return [
        {'format': array_file.FORMAT, 'bounds': [[-1, 0]], 'element_count': 2,
         'native_element_type': 8, 'scale': 0, 'subtype': 0,
         'charset_id': None},
        {'offset': 0, 'coordinates': [-1], 'values': [1]},
        {'offset': 1, 'coordinates': [0], 'values': [2]},
        {'complete': True, 'element_count': 2},
    ]


def spool(value=None, raw=None):
    result = array_file.ArrayUpload()
    data = raw if raw is not None else ''.join(
        json.dumps(row) + '\n' for row in value or records()).encode('utf8')
    for offset in range(0, len(data), 65536):
        result.append(offset, base64.b64encode(
            data[offset:offset+65536]).decode())
    return result


def test_finish_and_multiple_bounded_passes_preserve_offsets():
    upload = spool()
    try:
        assert upload.finish() is upload
        assert list(upload.chunks()) == [(0, [1]), (1, [2])]
        assert list(upload.chunks()) == [(0, [1]), (1, [2])]
        with pytest.raises(RelationalClientError):
            upload.append(upload.size, 'eA==')
    finally:
        upload.close()
    with pytest.raises(RelationalClientError):
        list(upload.chunks())


@pytest.mark.parametrize('change', [
    lambda rows: rows.pop(),
    lambda rows: rows.append({'unexpected': True}),
    lambda rows: rows[0].update(element_count=3),
    lambda rows: rows[0].update(bounds=[[True, 2]]),
    lambda rows: rows[0].update(bounds=[[0, -1]]),
    lambda rows: rows[1].update(offset=True),
    lambda rows: rows[1].update(coordinates=[0]),
    lambda rows: rows[1].update(values=[]),
    lambda rows: rows[2].update(offset=0),
    lambda rows: rows[-1].update(complete=False),
    lambda rows: rows[-1].update(element_count=2.0),
])
def test_invalid_structure_poisons_spool_without_releasing_ownership(change):
    rows = records()
    change(rows)
    upload = spool(rows)
    try:
        with pytest.raises(RelationalClientError):
            upload.finish()
        assert upload.failed and not upload.ready and not upload.closed
        with pytest.raises(RelationalClientError):
            upload.finish()
    finally:
        upload.close()


@pytest.mark.parametrize('raw', [
    b'{"format":"first","format":"second"}\n', b'\xff\n',
    b'{"x":NaN}\n', b' ' * (1048576+1), b'[]\n', b'\n',
])
def test_invalid_json_and_line_budget_are_not_bindable(raw):
    upload = spool(raw=raw)
    try:
        with pytest.raises(RelationalClientError):
            upload.finish()
        assert not upload.ready
    finally:
        upload.close()


@pytest.mark.parametrize('ordinary', [False, True])
def test_late_invalid_value_prevents_all_native_writes(monkeypatch, ordinary):
    rows = records()
    rows[2]['values'] = [2**63]
    upload = spool(rows)
    upload.finish()
    bounds = fbapi.ISC_ARRAY_DESC(0)
    bounds.array_desc_dimensions = 1
    bounds.array_desc_dtype = fbapi.blr_long
    bounds.array_desc_length = 4
    bounds.array_desc_bounds[0].array_bound_lower = -1
    bounds.array_desc_bounds[0].array_bound_upper = 0
    monkeypatch.setattr(array_upload.character_arrays, 'metadata',
                        lambda *args: None)
    monkeypatch.setattr(array_upload.scalar_arrays, 'describe',
                        lambda *args: (bounds, 4, 0))
    monkeypatch.setattr(array_upload.grid_arrays, 'descriptor',
                        lambda *args: {'type': 8, 'subtype': 0, 'scale': 0,
                                       'bounds': [(-1, 0)]})
    cursor = MagicMock()
    try:
        with pytest.raises(RelationalClientError, match='native range'):
            array_upload.ArrayWriter(cursor, 'T', 'A',
                                     [1, 2**63] if ordinary else upload)
        cursor._connection._att.put_slice.assert_not_called()
    finally:
        upload.close()


def test_native_write_failure_releases_transferred_metadata(monkeypatch):
    upload = spool()
    upload.finish()
    meta, result_meta = Mock(), Mock()
    meta.get_count.return_value = 1
    meta.get_type.return_value = SQLDataType.ARRAY
    result_meta.get_length.return_value = 8
    writer = Mock()
    writer.write.side_effect = OSError('native write failed')
    monkeypatch.setattr(array_upload, 'ArrayWriter', Mock(return_value=writer))
    native_pack = Mock(return_value=(result_meta, create_string_buffer(10)))
    try:
        with pytest.raises(OSError):
            array_upload.pack(SimpleNamespace(), meta, None, [upload],
                              native_pack)
        result_meta.release.assert_called_once_with()
        assert native_pack.call_args.args[-1] == [None]
    finally:
        upload.close()


@pytest.mark.parametrize('lower', [-2147483648, 65536, 2147483646])
def test_full_signed_catalog_coordinates_survive_staging(lower):
    rows = records()
    rows[0]['bounds'] = [[lower, lower+1]]
    rows[1]['coordinates'] = [lower]
    rows[2]['coordinates'] = [lower+1]
    upload = spool(rows)
    try:
        upload.finish()
        assert upload.header['bounds'] == [[lower, lower+1]]
        assert list(upload.chunks()) == [(0, [1]), (1, [2])]
    finally:
        upload.close()


@pytest.mark.parametrize('lower', [-2147483649, 2147483647])
def test_file_rejects_coordinates_outside_native_range(lower):
    rows = records()
    rows[0]['bounds'] = [[lower, lower+1]]
    upload = spool(rows)
    try:
        with pytest.raises(RelationalClientError):
            upload.finish()
    finally:
        upload.close()
