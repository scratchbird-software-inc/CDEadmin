"""Grid transport preserves native predicate values and exact wire values."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.grid_values import input_kind
from pgadmin.cdeadmin.providers.firebird.grid_values import (
    input_kinds, materialize,
    table_operations,
)
from firebird.driver.types import SQLDataType
from firebird.driver import DatabaseError


@pytest.mark.parametrize('value_type,expected', [
    (str, 'text'), (int, 'integer'), (Decimal, 'decimal'), (bool, 'boolean'),
    (float, None), (bytes, None), (list, None), ('INTEGER', None),
])
def test_hints_use_driver_types_not_names(value_type, expected):
    assert input_kind(value_type) == expected


@pytest.mark.parametrize('code,subtype,scale,charset,expected', [
    (SQLDataType.INT128, 0, 0, 0, 'integer'),
    (SQLDataType.INT128, 1, -18, 0, 'decimal'),
    (SQLDataType.INT64, 2, -4, 0, 'decimal'),
    (SQLDataType.VARYING, 0, 0, 4, 'text'),
    (SQLDataType.VARYING, 0, 0, 1, None),
    (SQLDataType.BLOB, 1, 0, 4, 'text'),
    (SQLDataType.BLOB, 0, 0, 0, None),
    (SQLDataType.ARRAY, 0, 0, 0, None),
])
def test_native_metadata_wins_over_incomplete_dbapi(
        code, subtype, scale, charset, expected):
    cursor = SimpleNamespace(description=[('VALUE', None)],
                             statement=SimpleNamespace(_out_desc=[
                                 SimpleNamespace(datatype=code,
                                                 subtype=subtype, scale=scale,
                                                 charset=charset, length=16,
                                                 nullable=True, relation='T',
                                                 field='VALUE', owner='O')]))
    assert input_kinds(cursor) == (expected,)


@pytest.mark.parametrize('failed', [False, True])
def test_blob_materialized_before_identity_and_closed_on_failure(failed):
    class Blob:
        read = MagicMock(return_value='text')
        close = MagicMock()
    value = Blob()
    if failed:
        value.read.side_effect = RuntimeError('read failed')
    with patch('firebird.driver.core.BlobReader', Blob):
        if failed:
            with pytest.raises(RuntimeError):
                materialize(value)
        else:
            assert materialize(value) == 'text'
    value.close.assert_called_once_with()


def test_table_admission_prepares_without_executing_and_frees_statements():
    handle = MagicMock()
    cursor = handle.cursor.return_value.__enter__.return_value
    statements = [MagicMock() for _ in range(3)]
    cursor.prepare.side_effect = [statements[0], statements[1],
                                  DatabaseError('denied'), statements[2]]
    assert table_operations(handle, 'T"X', ['V']) == {
        'update': ['V'], 'insert': ['V'], 'delete': False, 'defaults': True}
    assert cursor.prepare.call_args_list[0].args[0] == (
        'UPDATE "T""X" SET "V" = ? WHERE 1 = 0')
    cursor.execute.assert_not_called()
    for statement in statements:
        statement.free.assert_called_once_with()
    handle.commit.assert_not_called()
    handle.rollback.assert_not_called()


def test_firebird_table_default_values_without_generic_dialect_fallback():
    assert ADMINISTRATION._compile_insert({
        'resource_kind': 'table',
        'target_resource': {'resource_kind': 'table', 'display_path': ['T']},
        'draft': {'values': {}}}) == {
            'source': 'INSERT INTO "T" DEFAULT VALUES', 'parameters': ()}


def test_grid_retains_native_identity_but_emits_lossless_values():
    handle = MagicMock()
    cursor = handle.cursor.return_value
    cursor.description = [('ID', int), ('V', Decimal), ('TXT', str),
                          ('B', bool)]
    original = (2 ** 100, Decimal('12345678901234567890.1234'), 'null', False)
    cursor.fetchall.return_value = [original]
    client = MagicMock()
    client.config.execute_on_connection = False
    with patch.object(ADMINISTRATION, '_primary_key', return_value=('ID',)):
        page = ADMINISTRATION.read_rows(client, {
            '_provider_route': {'database': 'owned'}, 'session_id': 'owned',
            'target_resource': {'resource_kind': 'table',
                                'display_path': ['T']}}, connection=handle)
    token = page['rows'][0]['identity_token']
    try:
        assert page['rows'][0]['values'] == {
            'ID': str(original[0]), 'V': str(original[1]),
            'TXT': 'null', 'B': False}
        assert [c['input_kind'] for c in page['columns']] == [
            'integer', 'decimal', 'text', 'boolean']
        identity = ADMINISTRATION._row_identities[token]
        assert identity.key_values == (original[0],)
        assert identity.original['V'] == original[1]
    finally:
        ADMINISTRATION._row_identities.pop(token, None)
