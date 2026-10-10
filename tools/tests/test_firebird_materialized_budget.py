"""Admission refuses oversized values before reading and retains cleanup."""
from ctypes import create_string_buffer
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.providers.firebird.materialized_budget import (
    Budget, MAX_CHARGE, MAX_NODES,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from firebird.driver.types import SQLDataType


class Reader:
    def __init__(self, length=1):
        self.length = length
        self.position = 0
        self.read = MagicMock(side_effect=self._read)
        self.close = MagicMock()

    def _read(self):
        self.position = self.length
        return b'x' * self.length

    def tell(self):
        return self.position


def test_admission_accumulates_and_failure_cannot_resume():
    budget = Budget()
    budget.reserve(MAX_CHARGE, MAX_NODES)
    with pytest.raises(RelationalClientError, match='Run streaming'):
        budget.reserve(1)
    with pytest.raises(RelationalClientError):
        budget.reserve(0)
    with pytest.raises(RelationalClientError):
        Budget().reserve(0, MAX_NODES+1)


def test_blob_length_admission_precedes_read_and_closes_all_readers():
    oversized, other = Reader(MAX_CHARGE), Reader()
    with pytest.raises(RelationalClientError):
        Budget().after((oversized, other), Reader)
    oversized.read.assert_not_called()
    other.read.assert_not_called()
    oversized.close.assert_called_once()
    other.close.assert_called_once()


def test_blob_success_preserves_values_and_shared_budget():
    budget = Budget()
    assert budget.after((None, Reader(3), 12), Reader) == (None, b'xxx', 12)
    assert budget.charge == 18


def test_all_reader_closes_attempted_even_when_one_close_fails():
    first, second = Reader(), Reader()
    first.close.side_effect = RuntimeError('native close failed')
    with pytest.raises(RuntimeError):
        Budget().after((first, second), Reader)
    second.close.assert_called_once()


def test_incomplete_native_read_is_not_padded_success():
    reader = Reader(3)
    reader.read.side_effect = lambda: b'x\0\0'
    with pytest.raises(RelationalClientError, match='incomplete'):
        Budget().after((reader,), Reader)
    reader.close.assert_called_once()


def test_array_metadata_admission_never_reads_oversized_slice():
    desc = SimpleNamespace(datatype=SQLDataType.ARRAY, length=8, null_offset=8)
    cursor = SimpleNamespace(_stmt=SimpleNamespace(
        _out_desc=[desc], _out_buffer=create_string_buffer(10)))
    reader = MagicMock(dimensions=[1000, 1000], width=4)
    with patch('pgadmin.cdeadmin.providers.firebird.array_stream.ArrayReader',
               return_value=reader):
        with pytest.raises(RelationalClientError):
            Budget().before(cursor)
    reader.read.assert_not_called()
    reader.close.assert_called_once()


def test_null_array_does_not_lookup_or_read_native_data():
    desc = SimpleNamespace(datatype=SQLDataType.ARRAY, length=8, null_offset=8)
    buffer = create_string_buffer(10)
    buffer[8] = b'\1'
    cursor = SimpleNamespace(_stmt=SimpleNamespace(
        _out_desc=[desc], _out_buffer=buffer))
    budget = Budget()
    target = 'pgadmin.cdeadmin.providers.firebird.array_stream.ArrayReader'
    with patch(target) as reader:
        budget.before(cursor)
        reader.assert_not_called()
    assert budget.nodes == 2 and budget.charge == 320
