"""Native array contents require more than an ARRAY = ? predicate."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.grid_array_identity import (
    snapshot, verify,
)
from pgadmin.cdeadmin.providers.relational_admin import _RowIdentity
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('value', [
    None, [1, 2, 3], [[1, 2], [3, 4]], [Decimal('NaN'), Decimal('1.00')]])
def test_array_preflight_accepts_exact_retained_contents(value):
    cursor = MagicMock()
    cursor.fetchall.return_value = [(value,)]
    guard = {'source': 'SELECT A FROM T WHERE ID = ?', 'parameters': (1,),
             'snapshot': snapshot((value,))}
    verify(cursor, guard)
    cursor.execute.assert_called_once_with(guard['source'], (1,))
    cursor.connection.commit.assert_not_called()


@pytest.mark.parametrize('rows', [
    [], [([1, 2],), ([1, 2],)], [([1, 3],)], [(None,)]])
def test_array_preflight_rejects_changed_or_ambiguous_row(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    with pytest.raises(RelationalClientError, match='unchanged array row'):
        verify(cursor, {'source': 'SELECT A FROM T', 'parameters': (),
                        'snapshot': snapshot(([1, 2],))})


def test_snapshot_preserves_numeric_representation_and_null_distinctions():
    assert snapshot([Decimal('1.0')]) != snapshot([Decimal('1.00')])
    assert snapshot([-0.0]) != snapshot([0.0])
    assert snapshot([False]) != snapshot([0])
    assert snapshot(None) != snapshot([])


def test_array_predicate_uses_native_version_and_keeps_other_original_values():
    identity = _RowIdentity((), ('T',), ('ID',), (1,),
                            {'ID': 1, 'A': [1, 2], 'V': 9}, 0,
                            array_columns=('A',), native_record_version=123)
    assert ADMINISTRATION._identity_predicate(identity) == (
        '"ID" = ? AND "V" = ? AND RDB$RECORD_VERSION = ?', (1, 9, 123))


def test_array_identity_without_native_version_is_rejected():
    identity = _RowIdentity((), ('T',), ('ID',), (1,),
                            {'ID': 1, 'A': [1, 2]}, 0, array_columns=('A',))
    with pytest.raises(RelationalClientError, match='version is unavailable'):
        ADMINISTRATION._identity_predicate(identity)
