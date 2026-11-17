"""Native MariaDB observers, private output, permissions and original isolation."""
from contextlib import closing
from copy import deepcopy
import json
import os
from types import SimpleNamespace
import uuid

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, MARIADB_ADMINISTRATION, MYSQL_ADMINISTRATION, _create_client
from pgadmin.cdeadmin.providers.mysql_family import mariadb_server_diagnostics as diagnostics
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft
from tools.mysql_driver_gate_support import provider_access

SETTINGS = json.loads(os.environ.get('CDEADMIN_MARIADB_MANAGEMENT_TEST') or 'null')


def record_native_execution(plan, result, family):
    path = os.environ.get('CDEADMIN_MARIADB_MANAGEMENT_EXECUTIONS')
    if not path:
        return
    from pathlib import Path
    receipt = Path(path)
    rows = json.loads(receipt.read_text()) if receipt.exists() else []
    compiled = plan['provider_payload']['compiled']
    intent = next(value for key, value in compiled.items() if isinstance(value, dict) and 'operation' in value)
    rows.append({'operation': intent['operation'], 'source': compiled['statements'][0]['source'],
                 'native_acknowledged': result[family]['native_acknowledged'],
                 'connection_release': result['connection_release']})
    receipt.write_text(json.dumps(rows, indent=2) + '\n')


@pytest.fixture
def native():
    if SETTINGS is None:
        pytest.skip('Owned native MariaDB management fixture required')
    import mariadb
    with closing(mariadb.connect(**SETTINGS)) as handle:
        handle.autocommit = True
        cursor = handle.cursor()
        cursor.execute('SELECT @@server_uid,VERSION()')
        uid, version = cursor.fetchone()
        assert version.split('-')[0] == '12.2.2'
        cursor.execute('CREATE TABLE IF NOT EXISTS observer_pending(id INTEGER) ENGINE=InnoDB')
        cursor.execute('DELETE FROM observer_pending')
        route, permissions = provider_access({**SETTINGS, 'ssl': False, 'ssl_verify_cert': False})
        client = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace='owned-diagnostics-' + uuid.uuid4().hex))
        target = {'resource_kind': 'server', 'resource_id': 'server:MariaDB', 'display_name': 'MariaDB',
                  'display_path': ['MariaDB'], 'native': {'server_uid': uid}}
        try:
            yield SimpleNamespace(handle=handle, cursor=cursor, client=client, target=target, route=route, permissions=permissions)
        finally:
            client.close()
            if handle.server_status & 1:
                handle.rollback()
            cursor.close()


def planned(n, operation='inspect_engine_status', **values):
    spec = engine_operations('mariadb')[operation + '@server']
    draft = operation_draft(spec, {'engine': 'InnoDB', 'private_data_confirmed': True, **values}, confirmation=n.target['display_name'])
    request = {'resource_kind': 'server', 'operation_id': operation, 'target_resource': n.target, 'draft': draft, '_provider_route': n.route}
    assert MARIADB_ADMINISTRATION.validate(request)['errors'] == []
    return n.client.plan_admin_operation(request)


@pytest.mark.parametrize('operation', diagnostics.OPERATIONS)
@pytest.mark.parametrize('scope', ['ENGINE', 'ALL'])
def test_native_engine_diagnostic_uses_observer_and_preserves_pending_rows(native, operation, scope):
    n = native
    n.cursor.execute('START TRANSACTION')
    n.cursor.execute('INSERT INTO observer_pending VALUES(29)')
    n.cursor.execute('SAVEPOINT caller')
    plan = planned(n, operation, engine_scope=scope, **({'engine': ''} if scope == 'ALL' else {}))
    result = n.client.apply_admin_operation(plan)
    assert result['accepted'] and result['engine_diagnostic']['complete']
    assert result['engine_diagnostic']['columns'] == ['Type', 'Name', 'Status']
    assert result['engine_diagnostic']['native_acknowledged']
    assert result['connection_release']['connection_released']
    assert not result['commit_requested'] and not result['rollback_requested'] and not result['automatic_retry']
    n.cursor.execute('SELECT * FROM observer_pending')
    assert n.cursor.fetchall() == [(29,)]
    record_native_execution(plan, result, 'engine_diagnostic')
    n.cursor.execute('ROLLBACK TO SAVEPOINT caller')
    import mariadb
    with closing(mariadb.connect(**SETTINGS)) as other:
        c = other.cursor();c.execute('SELECT * FROM observer_pending');assert c.fetchall() == [];c.close()


def test_native_unavailable_engine_and_wrong_server_refuse_before_dispatch(native):
    n = native
    with pytest.raises(RelationalClientError, match='unavailable or disabled'):
        planned(n, engine='owned_missing_engine')
    n.target['native']['server_uid'] = 'A' * 27 + '='
    with pytest.raises(RelationalClientError, match='differs'):
        planned(n)


def test_native_truncation_is_not_complete_acknowledgement(native, monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_engine_diagnostics
    n = native
    plan = planned(n)
    monkeypatch.setattr(mysql_engine_diagnostics, 'MAX_BYTES', 1)
    result = n.client.apply_admin_operation(plan)
    assert result['accepted'] and result['engine_diagnostic']['truncated']
    assert not result['engine_diagnostic']['complete'] and not result['engine_diagnostic']['native_acknowledged']
    assert result['connection_release']['connection_released']


@pytest.mark.parametrize('operation', diagnostics.OPERATIONS)
def test_native_process_file_refusal_has_codes_and_observer_cleanup(native, operation):
    n = native
    user = 'observer_' + uuid.uuid4().hex[:16]
    n.cursor.execute('CREATE USER `' + user + "`@'%' IDENTIFIED BY 'owned' ")
    route, permissions = provider_access({**SETTINGS, 'user': user, 'database': None, 'ssl': False, 'ssl_verify_cert': False}, 'owned')
    restricted = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace='restricted-' + user))
    try:
        peer = SimpleNamespace(client=restricted, route=route, target=n.target)
        plan = planned(peer, operation)
        with pytest.raises(RelationalClientError) as denied:
            restricted.apply_admin_operation(plan)
        # MariaDB's native FILE check uses access-denied (1045/28000),
        # whereas STATUS/MUTEX use the PROCESS check (1227/42000).
        expected = (1045, '28000') if operation == 'inspect_engine_logs' else (1227, '42000')
        assert (denied.value.errno, denied.value.sqlstate) == expected
        assert not denied.value.native_acknowledged and denied.value.native_dispatched
        assert denied.value.connection_release['connection_released']
    finally:
        restricted.close();n.cursor.execute('DROP USER `' + user + "`@'%'")


def test_mariadb_native_surface_does_not_borrow_mysql_identity():
    for operation in diagnostics.OPERATIONS:
        assert MARIADB_ADMINISTRATION.supports('server', operation)
        assert not MYSQL_ADMINISTRATION.supports('server', operation)
    target = {'resource_kind': 'server', 'resource_id': 'server:MySQL', 'display_name': 'MySQL', 'display_path': ['MySQL'], 'native': {'server_uuid': str(uuid.uuid4())}}
    with pytest.raises(RelationalClientError, match='server_uid'):
        diagnostics.compile_operation('inspect_engine_status', {'confirmation': 'MySQL', 'private_data_confirmed': True}, target)


@pytest.mark.parametrize('values', [{'private_data_confirmed': False}, {'engine_scope': 'ALL', 'engine': 'InnoDB'}, {'source_sql': 'SHOW STATUS'}, {'engine_scope': 'invalid'}])
def test_diagnostic_compiler_requires_exact_native_request(values):
    target = {'resource_kind': 'server', 'resource_id': 'server:MariaDB', 'display_name': 'MariaDB', 'display_path': ['MariaDB'], 'native': {'server_uid': 'A' * 27 + '='}}
    with pytest.raises(RelationalClientError):
        diagnostics.compile_operation('inspect_engine_status', {'confirmation': 'MariaDB', 'private_data_confirmed': True, 'engine': 'InnoDB', **values}, target)


@pytest.mark.parametrize('target', [None, {}, {'resource_kind': 'server', 'native': 'invalid'},
    {'resource_kind': 'server', 'extensions': []},
    {'resource_kind': 'server', 'extensions': {'mariadb': 'invalid'}}])
def test_malformed_native_identity_refuses_without_attribute_errors(target):
    with pytest.raises(RelationalClientError):
        diagnostics.target_uid(target)
