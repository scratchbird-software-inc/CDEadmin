"""Native running-query observations and replacement-query fencing."""
from contextlib import contextmanager, closing
from copy import deepcopy
import threading
import time
from types import SimpleNamespace
import uuid

import pytest
from test_mariadb_server_diagnostics import native, SETTINGS, record_native_execution
from pgadmin.cdeadmin.providers.mysql_family import mariadb_live_plans as plans
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, MARIADB_ADMINISTRATION, _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from tools.mysql_driver_gate_support import provider_access
from ui_descriptor_roundtrip import engine_operations, operation_draft


@contextmanager
def running(n, user=None):
    import mariadb
    handle = mariadb.connect(**{**SETTINGS, **({'user': user, 'password': 'owned'} if user else {})})
    handle.autocommit = True
    c = handle.cursor(); c.execute('SELECT CONNECTION_ID()'); identifier = str(c.fetchone()[0]); c.close()
    outcomes = []
    def execute():
        cursor = handle.cursor()
        try:
            cursor.execute('SELECT seq,SLEEP(0.01) FROM seq_1_to_10000')
            cursor.fetchall(); outcomes.append('completed')
        except mariadb.Error as error:
            outcomes.append(error.errno)
        finally:
            cursor.close()
    worker = threading.Thread(target=execute); worker.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            n.cursor.execute('SELECT COMMAND,QUERY_ID FROM information_schema.PROCESSLIST WHERE ID=%s', (int(identifier),))
            row = n.cursor.fetchone()
            if row and row[0] == 'Query' and row[1]: break
            time.sleep(0.02)
        else: pytest.fail('Owned native query did not become active')
        yield identifier
    finally:
        if worker.is_alive(): n.cursor.execute('KILL QUERY ' + identifier)
        worker.join(5)
        assert not worker.is_alive(), 'Owned native query must stop before connection cleanup'
        handle.close()
        assert outcomes and outcomes[0] in ('completed', 1317)


def review(n, identifier, operation='inspect_live_explain', output='TABULAR'):
    spec = engine_operations('mariadb')[operation + '@server']
    draft = operation_draft(spec, {'connection_id': identifier, 'output_format': output, 'private_data_confirmed': True}, confirmation=n.target['display_name'])
    request = dict(resource_kind='server', operation_id=operation, target_resource=n.target, draft=draft, _provider_route=n.route)
    assert MARIADB_ADMINISTRATION.validate(request)['errors'] == []
    return n.client.plan_admin_operation(request)


@pytest.mark.parametrize('operation', plans.OPERATIONS)
@pytest.mark.parametrize('output', ['TABULAR', 'JSON'])
def test_native_live_plan_formats_and_original_transaction(native, operation, output):
    n = native
    n.cursor.execute('START TRANSACTION'); n.cursor.execute('INSERT INTO observer_pending VALUES(37)')
    n.cursor.execute('SAVEPOINT caller')
    with running(n) as identifier:
        plan = review(n, identifier, operation, output)
        result = n.client.apply_admin_operation(plan)
        data = result['live_plan']
        assert data['rows'] and data['columns']
        assert data['complete'] and data['native_acknowledged'] and data['identity_revalidated_after_read']
        assert data['subject']['connection_id'] == identifier and data['subject']['query_id']
        assert not data['atomic_query_reservation']
        assert result['connection_release']['connection_released']
        assert not result['commit_requested'] and not result['rollback_requested']
        record_native_execution(plan, result, 'live_plan')
        if output == 'JSON':
            import json
            assert isinstance(json.loads(data['rows'][0][0]), dict)
    n.cursor.execute('SELECT * FROM observer_pending'); assert n.cursor.fetchall() == [(37,)]
    n.cursor.execute('ROLLBACK TO SAVEPOINT caller')


def test_replaced_or_completed_query_refuses_before_native_dispatch(native):
    n = native
    with running(n) as identifier:
        plan = review(n, identifier)
    with pytest.raises(RelationalClientError) as failed:
        n.client.apply_admin_operation(plan)
    assert not failed.value.native_dispatched and not failed.value.native_acknowledged
    assert failed.value.connection_release['connection_released']


def test_native_truncation_withholds_unfenced_output(native, monkeypatch):
    n = native
    with running(n) as identifier:
        plan = review(n, identifier)
        monkeypatch.setattr(plans, 'MAX_BYTES', 1)
        result = n.client.apply_admin_operation(plan)
    data = result['live_plan']
    assert data['truncated'] and data['rows'] == [] and not data['native_acknowledged']
    assert result['connection_release']['connection_released']


def test_native_own_user_without_process_and_foreign_visibility_refusal(native):
    n = native; user = 'plan_' + uuid.uuid4().hex[:16]
    n.cursor.execute('CREATE USER `' + user + "`@'%' IDENTIFIED BY 'owned'")
    n.cursor.execute('GRANT SELECT ON owned_management.* TO `' + user + "`@'%'")
    route, permissions = provider_access({**SETTINGS, 'user': user, 'ssl': False, 'ssl_verify_cert': False}, 'owned')
    client = _create_client(MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace='owned-plan-' + user))
    peer = SimpleNamespace(client=client, target=n.target, route=route)
    try:
        with running(n, user) as identifier:
            result = client.apply_admin_operation(review(peer, identifier))
            assert result['live_plan']['native_acknowledged']
        with running(n) as foreign:
            with pytest.raises(RelationalClientError, match='not visible'):
                review(peer, foreign)
    finally:
        client.close(); n.cursor.execute('DROP USER `' + user + "`@'%'")


@pytest.mark.parametrize('identifier', [1, True, '0', '-1', '1;KILL 1', '18446744073709551616', '01'])
def test_exact_native_connection_id_required(identifier):
    target = dict(resource_kind='server', resource_id='server:MariaDB', display_name='MariaDB', display_path=['MariaDB'], native={'server_uid': 'A'*27+'='})
    with pytest.raises(RelationalClientError):
        plans.compile_operation('inspect_live_explain', dict(connection_id=identifier, private_data_confirmed=True, confirmation='MariaDB'), target)


def test_query_finishing_during_native_read_withholds_output(native, monkeypatch):
    n = native
    with running(n) as identifier:
        plan = review(n, identifier)
        read_native = plans.bounded_result
        def finish_after_read(cursor):
            output = read_native(cursor)
            assert output['rows'] and output['complete']
            n.cursor.execute('KILL QUERY ' + identifier)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                n.cursor.execute('SELECT COMMAND FROM information_schema.PROCESSLIST WHERE ID=%s', (int(identifier),))
                row = n.cursor.fetchone()
                if row is None or row[0] != 'Query': return output
                time.sleep(.02)
            pytest.fail('Owned query did not finish after native interruption')
        monkeypatch.setattr(plans, 'bounded_result', finish_after_read)
        with pytest.raises(RelationalClientError) as failed:
            n.client.apply_admin_operation(plan)
        assert failed.value.native_dispatched and not failed.value.native_acknowledged
        assert failed.value.connection_release['connection_released']
