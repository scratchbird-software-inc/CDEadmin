"""Strict zoned envelopes preserve UTC instants independently of DST rules."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird import zoned_values as zones
from pgadmin.cdeadmin.providers.firebird.query_values import normalize_value
from pgadmin.cdeadmin.providers.firebird.query_parameters import (
    normalize_parameters,
)
from pgadmin.cdeadmin.providers.firebird.grid_arrays import convert
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from firebird.driver.types import SQLDataType


STAMP = {'encoding': 'firebird-timestamp-tz',
         'utc': '2025-11-02 06:30:00.000100', 'time_zone': 'America/New_York'}


def test_envelope_array_query_and_grid_round_trip():
    value = zones.parse(STAMP)
    assert normalize_value(value) == STAMP
    assert normalize_parameters([STAMP, [STAMP]]) == (value, [value])
    assert convert([STAMP], {'type': 29, 'bounds': [(2, 2)]}) == [value]
    first = zones.parse({**STAMP, 'utc': '2025-11-02 05:30:00.000100'})
    assert first != value
    assert first.time_zone == value.time_zone


@pytest.mark.parametrize('change', [
    {'extra': True}, {'utc': '2025-11-02 06:30:00.000101'},
    {'utc': '2025-11-02 06:30:00+00:00'}, {'utc': '2025-02-30 00:00:00'},
    {'utc': True}, {'time_zone': ''}, {'time_zone': 'UTC\0'},
    {'time_zone': ' UTC'}, {'time_zone': 'é'}, {'time_zone': 'x'*64},
    {'encoding': 'timestamp'}, {'utc': '20251102T063000'},
])
def test_invalid_envelopes_fail_before_native_work(change):
    with pytest.raises(RelationalClientError):
        zones.parse({**STAMP, **change})


def test_matching_type_required():
    with pytest.raises(RelationalClientError):
        zones.parse(STAMP, 28)


@pytest.mark.parametrize('identity,name', [
    (1439, '+00:00'), (2279, '+14:00'), (599, '-14:00'), (1784, '+05:45'),
])
def test_fixed_offset_identity_needs_no_host_timezone(identity, name):
    assert zones.zone_name(None, identity) == name
    assert zones.zone_id(None, name) == identity


@pytest.mark.parametrize('name', ['+14:01', '-14:30', '+15:00', '+01:60'])
def test_invalid_offset(name):
    with pytest.raises(RelationalClientError):
        zones.zone_id(None, name)


def test_catalog_names_are_attachment_scoped_and_parameter_bound():
    cursor = SimpleNamespace(_transaction=MagicMock())
    query = cursor._transaction.cursor.return_value.__enter__.return_value
    query.fetchone.return_value = (65000, 'America/New_York')
    assert zones.zone_name(cursor, 65000) == 'America/New_York'
    assert zones.zone_name(cursor, 65000) == 'America/New_York'
    assert query.execute.call_count == 1
    assert query.execute.call_args.args[1] == (65000,)
    query.fetchone.return_value = None
    with pytest.raises(RelationalClientError):
        zones.zone_name(cursor, 64999)


def test_unpack_restores_null_flags_after_failure_without_changing_metadata():
    desc = SimpleNamespace(datatype=SQLDataType.TIMESTAMP_TZ,
                           null_offset=12, offset=0, length=12)
    buffer = create_string_buffer(14)
    cursor = SimpleNamespace(_stmt=SimpleNamespace(
        _out_buffer=buffer, _out_desc=[desc]))
    with patch.object(zones, 'decode', return_value=zones.parse(STAMP)):
        def fail():
            assert buffer[12] == b'\1'
            raise RuntimeError('owned failure')
        with pytest.raises(RuntimeError):
            zones.unpack(cursor, fail)
    assert buffer.raw == bytes(14)


def test_pack_releases_transferred_metadata_on_width_failure():
    meta = MagicMock()
    meta.get_count.return_value = 1
    meta.get_type.return_value = SQLDataType.TIMESTAMP_TZ
    result = MagicMock()
    result.get_length.return_value = 8
    native = MagicMock(return_value=(result, create_string_buffer(16)))
    with patch.object(zones, 'encode', return_value=bytes(12)):
        with pytest.raises(RelationalClientError):
            zones.pack(None, meta, None, [zones.parse(STAMP)], native)
    assert native.call_args.args[2] == [None]
    result.release.assert_called_once()
