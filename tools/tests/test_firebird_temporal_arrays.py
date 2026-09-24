"""Temporal array text and signed native date buffers."""
from ctypes import create_string_buffer
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import (
    TemporalArrayCursor, cursor, parse,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from firebird.driver import core, fbapi


@pytest.mark.parametrize('code,text,expected', [
    (12, '0001-01-01', date(1, 1, 1)),
    (12, '9999-12-31', date(9999, 12, 31)),
    (13, '23:59:59.9999', time(23, 59, 59, 999900)),
    (35, '0001-01-01 12:34:56.0001', datetime(1, 1, 1, 12, 34, 56, 100)),
    (35, '9999-12-31T23:59:59.9999',
     datetime(9999, 12, 31, 23, 59, 59, 999900)),
])
def test_temporal_exact_text(code, text, expected):
    assert parse(text, code) == expected
    assert parse(expected, code) is expected


@pytest.mark.parametrize('code,value', [
    (12, '0000-01-01'), (12, '2023-02-29'), (12, '20000101'),
    (12, datetime(2000, 1, 1)), (13, '24:00:00'), (13, '23:59:60'),
    (13, '12:00:00.12345'), (13, '12:00:00Z'), (13, time(0, microsecond=1)),
    (35, '2000-01-01'), (35, '2000-01-01 00:00:00+01:00'),
    (35, datetime(2000, 1, 1, tzinfo=timezone.utc)), (12, None), (13, True),
])
def test_invalid_type_range_calendar_zone_and_precision(code, value):
    with pytest.raises(RelationalClientError):
        parse(value, code)


@pytest.mark.parametrize('timestamp', [False, True])
def test_signed_date_packing_without_global_driver_mutation(timestamp):
    connection = SimpleNamespace(sql_dialect=3, _encoding='utf8')
    native = TemporalArrayCursor(connection, MagicMock())
    original = core.Cursor._fill_db_array_buffer
    size = 8 if timestamp else 4
    data = create_string_buffer(4 * size + 3)
    day = date(1, 1, 1)
    value = datetime(1, 1, 1, 23, 59, 59, 999900) if timestamp else day
    utility = SimpleNamespace(encode_date=lambda _: -678575,
                              encode_time=lambda _: 863999999)
    with patch.object(core, '_util', utility):
        end = native._fill_db_array_buffer(
            size, fbapi.blr_timestamp if timestamp else fbapi.blr_sql_date,
            0, 0, 0, [2, 2], [[value, value], [value, value]],
            create_string_buffer(size), data, 3)
    assert end == 3 + 4 * size
    leaf = (-678575).to_bytes(4, 'little', signed=True)
    if timestamp:
        leaf += (863999999).to_bytes(4, 'little')
    assert data.raw == b'\0' * 3 + leaf * 4
    assert core.Cursor._fill_db_array_buffer is original
    native.close()


def test_cursor_factory_matches_native_transaction_ownership():
    connection = MagicMock(spec=core.Connection)
    connection.sql_dialect = 3
    connection._encoding = 'utf8'
    transaction = connection.main_transaction
    transaction._cursors = []
    result = cursor(connection)
    assert isinstance(result, TemporalArrayCursor)
    assert result._transaction is transaction
    assert transaction._cursors[0]() is result
    result.close()


def test_non_native_wrappers_keep_their_cursor_factory():
    connection = MagicMock()
    assert cursor(connection) is connection.cursor.return_value
    connection.cursor.assert_called_once_with()
