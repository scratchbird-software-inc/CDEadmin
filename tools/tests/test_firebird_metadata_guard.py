"""Native metadata review refuses retargeting without finalizing callers."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import firebird.driver as native
import pytest

from pgadmin.cdeadmin.providers.firebird import metadata_guard as guard
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture
def connection():
    cursor = Mock()
    cursor.fetchall.return_value = [(b'12345678', 100)]
    return SimpleNamespace(cursor=Mock(return_value=cursor),
        info=SimpleNamespace(get_info=lambda code: 'owned-guid' if code == native.DbInfoCode.DB_GUID else 'owned-file'),
        main_transaction=SimpleNamespace(info=SimpleNamespace(isolation=native.Isolation.SNAPSHOT)),
        commit=Mock(), rollback=Mock())


@pytest.mark.parametrize('kind', list(guard.CATALOGS))
def test_catalog_names_are_constants_and_object_names_are_parameters(connection, kind):
    name = '1' if kind == 'shadow' else 'odd\"; DROP DATABASE; --'
    selected = {'resource_kind': kind, 'path': ['parent', name] if kind == 'column' else [name]}
    expected = guard.observe(connection, selected)
    guard.verify(connection, expected)
    for call in connection.cursor().execute.call_args_list:
        assert name not in call.args[0]
    connection.commit.assert_not_called(); connection.rollback.assert_not_called()
    record = expected['record'][0] if kind == 'shadow' else expected['record']
    assert record['record_transaction'] == '100'


@pytest.mark.parametrize('change', ['guid', 'file', 'record', 'version', 'parent'])
def test_changed_record_or_database_identity_is_known_predispatch_refusal(connection, change):
    expected = guard.observe(connection, {'resource_kind': 'column', 'path': ['T', 'C']})
    expected = deepcopy(expected)
    if change == 'guid': expected['database_guid'] = 'other'
    elif change == 'file': expected['database_file_id'] = 'other'
    elif change == 'record': expected['record']['record_key_hex'] = b'87654321'.hex()
    elif change == 'version': expected['record']['record_transaction'] = '101'
    else: expected['parent']['record_transaction'] = '101'
    with pytest.raises(RelationalClientError, match='changed since review') as failure:
        guard.verify(connection, expected)
    assert failure.value.rejected and failure.value.nothing_changed
    assert not failure.value.native_dispatched and not failure.value.automatic_retry
    connection.commit.assert_not_called(); connection.rollback.assert_not_called()


def test_read_committed_transaction_is_never_silently_reconfigured(connection):
    expected = guard.observe(connection, {'resource_kind': 'table', 'path': ['T']})
    connection.main_transaction.info.isolation = native.Isolation.READ_COMMITTED_RECORD_VERSION
    with pytest.raises(RelationalClientError, match='SNAPSHOT'):
        guard.verify(connection, expected)
    connection.commit.assert_not_called(); connection.rollback.assert_not_called()


@pytest.mark.parametrize('rows', [[], [(b'12345678', 1), (b'12345678', 1)],
                                   [(None, 1)], [(b'short', 1)], [(b'12345678', True)]])
def test_missing_ambiguous_or_invalid_native_identity_fails_closed(connection, rows):
    connection.cursor().fetchall.return_value = rows
    with pytest.raises(RelationalClientError):
        guard.observe(connection, {'resource_kind': 'table', 'path': ['T']})
    connection.cursor().close.assert_called_once()


@pytest.mark.parametrize('operation', ['create', 'inspect', 'insert', 'update', 'delete'])
def test_guard_does_not_recompile_or_consume_row_selectors(operation):
    administration = Mock()
    assert guard.selection({'resource_kind': 'table', 'operation_id': operation,
                            'target_resource': {}}, administration) is None
    administration._target_path.assert_not_called()
