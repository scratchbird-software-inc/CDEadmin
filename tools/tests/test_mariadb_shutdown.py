"""Native shutdown acknowledgement; owned runner independently observes exit."""
from copy import deepcopy
import json
import os
from types import SimpleNamespace
import uuid

import pytest
from test_mariadb_server_diagnostics import native, SETTINGS
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, MARIADB_ADMINISTRATION, _create_client
from pgadmin.cdeadmin.providers.mysql_family import mariadb_shutdown as shutdown
from pgadmin.cdeadmin.sdk import RelationalClientError
from tools.mysql_driver_gate_support import provider_access
from ui_descriptor_roundtrip import engine_operations, operation_draft


def review(peer):
    spec = engine_operations('mariadb')['shutdown_server@server']
    draft = operation_draft(spec, {'service_disruption_confirmed': True}, confirmation=peer.target['display_name'])
    return peer.client.plan_admin_operation(dict(resource_kind='server', operation_id='shutdown_server',
        target_resource=peer.target, draft=draft, _provider_route=peer.route))


def test_native_shutdown_denied_and_expired_reviews_leave_server_running(native):
    n = native; user = 'shutdown_' + uuid.uuid4().hex[:12]
    n.cursor.execute('CREATE USER `' + user + "`@'%' IDENTIFIED BY 'owned'")
    route, permissions = provider_access({**SETTINGS, 'database': None, 'user': user, 'ssl': False, 'ssl_verify_cert': False}, 'owned')
    client = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace=user))
    try:
        plan = review(SimpleNamespace(client=client, target=n.target, route=route))
        with pytest.raises(RelationalClientError) as denied:
            client.apply_admin_operation(plan)
        assert denied.value.errno == 1227 and denied.value.sqlstate == '42000'
        assert denied.value.native_dispatched and not denied.value.native_acknowledged
        assert denied.value.connection_release['connection_released']
        plan = review(n); plan['provider_payload']['compiled'][shutdown.KEY]['review']['review_clock'] -= 61
        with pytest.raises(RelationalClientError, match='expired'):
            n.client.apply_admin_operation(plan)
        n.cursor.execute('SELECT 1'); assert n.cursor.fetchone() == (1,)
    finally:
        client.close(); n.cursor.execute('DROP USER `' + user + "`@'%'")


@pytest.mark.parametrize('draft', [{'service_disruption_confirmed': False, 'confirmation': 'MariaDB'},
    {'service_disruption_confirmed': True, 'confirmation': 'other'},
    {'service_disruption_confirmed': True, 'confirmation': 'MariaDB', 'sql': 'SHUTDOWN'}])
def test_shutdown_requires_exact_typed_confirmation(draft):
    target = dict(resource_kind='server', resource_id='server:MariaDB', display_name='MariaDB', display_path=['MariaDB'], native={'server_uid': 'A'*27+'='})
    with pytest.raises(RelationalClientError): shutdown.compile_operation('shutdown_server', draft, target)


def test_owned_native_shutdown_request_last():
    if not os.environ.get('CDEADMIN_MARIADB_SHUTDOWN_RECEIPT'):
        pytest.skip('A dedicated disposable server with independent exit observation is required')
    import mariadb
    handle = mariadb.connect(**SETTINGS)
    c = handle.cursor(); c.execute('SELECT @@server_uid'); uid = c.fetchone()[0]; c.close(); handle.close()
    route, permissions = provider_access({**SETTINGS, 'ssl': False, 'ssl_verify_cert': False})
    client = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace='owned-stop-' + uuid.uuid4().hex))
    target = dict(resource_kind='server', resource_id='server:MariaDB', display_name='MariaDB', display_path=['MariaDB'], native={'server_uid': uid})
    try:
        result = client.apply_admin_operation(review(SimpleNamespace(client=client, route=route, target=target)))
        assert result['shutdown']['native_acknowledged']
        assert result['shutdown']['process_exit'] == 'not-observed'
        assert not result['shutdown']['host_service_control'] and not result['automatic_retry']
        assert not result['commit_requested'] and not result['rollback_requested']
        assert result['connection_release']['connection_released']
        from pathlib import Path
        Path(os.environ['CDEADMIN_MARIADB_SHUTDOWN_RECEIPT']).write_text(json.dumps(result, indent=2)+'\n')
    finally:
        client.close()
