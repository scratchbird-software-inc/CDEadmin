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


def test_security_virtual_projections_hash_state_without_claiming_record_version(connection):
    cursor = connection.cursor()
    cursor.fetchall.side_effect = [
        [('AUD_USER', 'Srp', 'First', None, 'Last', True, False, 'desc')],
        [('dept', 'ops')],
        [('AUD_USER', 'Srp', 'First', None, 'Last', True, False, 'desc')],
        [('dept', 'ops')],
        [('AUD_USER', 'Srp', 'Changed', None, 'Last', True, False, 'desc')],
        [('dept', 'ops')],
    ]
    administration = Mock(_target_path=Mock(return_value=['AUD_USER']))
    selected = guard.selection({
        'resource_kind': 'user',
        'operation_id': 'recreate',
        'target_resource': {'resource_kind': 'user', 'display_name': 'AUD_USER',
                            'native': {'plugin': 'Srp'}},
        'draft': {'confirmation': 'AUD_USER'},
    }, administration)
    assert selected == {'resource_kind': 'user', 'path': ['AUD_USER'], 'plugin': 'Srp'}
    expected = guard.observe(connection, selected)
    assert expected['record']['record_version_available'] is False
    assert 'First' not in str(expected) and 'ops' not in str(expected)
    guard.verify(connection, expected)
    with pytest.raises(RelationalClientError, match='changed since review') as failure:
        guard.verify(connection, expected)
    assert failure.value.rejected and not failure.value.native_dispatched


def test_global_mapping_and_privilege_selection_contracts(connection):
    cursor = connection.cursor()
    cursor.fetchall.side_effect = [
        [('GMAP', 'P', 'Srp', None, 'USER', 'alice', 0, 'ALICE', 'comment')],
        [('GMAP', 'P', 'Srp', None, 'USER', 'alice', 0, 'ALICE', 'comment')],
        [(b'87654321', 42)],
        [(b'87654321', 42)],
    ]
    administration = Mock(_target_path=Mock(return_value=['GMAP']))
    gmap_sel = guard.selection({
        'resource_kind': 'global-authentication-mapping',
        'operation_id': 'drop',
        'target_resource': {'resource_kind': 'global-authentication-mapping', 'display_name': 'GMAP'},
    }, administration)
    observed_gmap = guard.observe(connection, gmap_sel)
    guard.verify(connection, observed_gmap)

    priv_sel = guard.selection({
        'resource_kind': 'privilege',
        'operation_id': 'revoke',
        'target_resource': {
            'resource_kind': 'privilege',
            'display_name': 'R:S on T',
            'native': {
                'grantee': 'R', 'object_name': 'T', 'field': None,
                'privilege': 'S', 'grantor': 'SYSDBA',
                'user_type': 13, 'object_type': 0,
            },
        },
    }, administration)
    observed_priv = guard.observe(connection, priv_sel)
    guard.verify(connection, observed_priv)

    # Collection-level object privilege binds its catalog relation target.
    obj_priv_sel = guard.selection({
        'resource_kind': 'privilege',
        'operation_id': 'grant',
        'draft': {'privilege_scope': 'object', 'object_type': 'TABLE', 'object_name': 'T'},
    }, administration)
    assert obj_priv_sel == {'resource_kind': 'table', 'path': ['T']}

    # create_or_alter targeting a different new name does not bind an unrelated inspected row.
    assert guard.selection({
        'resource_kind': 'view',
        'operation_id': 'create_or_alter',
        'target_resource': {'resource_kind': 'view', 'display_name': 'OLD_V'},
        'draft': {'name': 'NEW_V'},
    }, administration) is None

