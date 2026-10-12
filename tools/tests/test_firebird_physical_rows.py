"""Physical identities cannot move to a new transaction or attachment."""
from unittest.mock import MagicMock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.physical_rows import verify_owner
from pgadmin.cdeadmin.providers.relational_admin import _RowIdentity
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


@pytest.mark.parametrize('active,actual,expected', [
    (False, (4, 5), (4, 5)), (True, (4, 6), (4, 5)),
    (True, (5, 5), (4, 5)), (True, (4, 5), None),
    (True, (4, 5), (4, True))])
def test_stale_or_malformed_owner_is_refused_without_transaction_control(
        active, actual, expected):
    connection = MagicMock()
    connection.info.id, connection.main_transaction.info.id = actual
    connection.main_transaction.is_active.return_value = active
    with pytest.raises(RelationalClientError):
        verify_owner(connection, expected)
    connection.cursor.assert_not_called()
    connection.main_transaction.begin.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def test_serialized_owner_keeps_exact_native_attachment_and_transaction():
    connection = MagicMock()
    connection.info.id = 4
    connection.main_transaction.info.id = 5
    connection.main_transaction.is_active.return_value = True
    verify_owner(connection, [4, 5])


def test_physical_predicate_keeps_opaque_key_and_version_not_guessed_values():
    identity = _RowIdentity((), ('DUPLICATES',), (), (), {'V': 7}, 0,
                            native_record_version=9,
                            representation_columns=('V',),
                            native_db_key=b'\0\xff\1\2\3\4\5\6',
                            native_row_owner=(4, 5))
    assert ADMINISTRATION._identity_predicate(identity) == (
        'RDB$DB_KEY = ? AND RDB$RECORD_VERSION = ?',
        (b'\0\xff\1\2\3\4\5\6', 9))
