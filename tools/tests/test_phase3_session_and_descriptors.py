"""Phase 3 tests: session isolation, Firebird auto-reconnect vs uncommitted guard,
RAM credential desync, virtual folders, context menu deduplication, and descriptors."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.context_menu import database_target_context_actions
from pgadmin.cdeadmin.core.registry import ProviderRegistry
from pgadmin.cdeadmin.data_studio.studio import DataStudioService
from pgadmin.cdeadmin.endpoints.profiles import registration_profile
from pgadmin.cdeadmin.endpoints.service import (
    EndpointService,
    _derived_target_namespace,
)
from pgadmin.cdeadmin.navigator import resource_children
from pgadmin.cdeadmin.providers.firebird.provider import (
    FirebirdProvider,
    PROFILE as FIREBIRD_PILOT_PROFILE,
)
from pgadmin.cdeadmin.providers.firebird.query_client import (
    CONNECTION_DROP_GDS_CODES,
    FirebirdQueryClient,
)
from pgadmin.cdeadmin.providers.firebird.transaction_state import observe_transaction
from pgadmin.cdeadmin.sdk import RelationalClientConfig, RelationalClientError
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService

REPO_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTORS_DIR = REPO_ROOT / 'web' / 'pgadmin' / 'cdeadmin' / 'ui_descriptors'


class _FakeGdsError(Exception):
    def __init__(self, message='connection lost', gds_codes=(335544856,)):
        super().__init__(message)
        self.gds_codes = tuple(gds_codes)


class _FakeTransaction:
    def __init__(self, active=False):
        self.active = active

    def is_active(self):
        return self.active


class _FakeFirebirdConn:
    def __init__(self, name='conn-1', *, healthy=True, autocommit=True):
        self.name = name
        self.healthy = healthy
        self.autocommit = autocommit
        self._closed = False
        self._att = object()
        self.main_transaction = _FakeTransaction(active=False)
        self.ping_calls = 0
        self.close_calls = 0
        self.rollback_calls = 0

    def is_closed(self):
        return self._closed

    def ping(self):
        self.ping_calls += 1
        if not self.healthy or self._closed:
            raise _FakeGdsError('attachment shutdown', (335544856,))

    def rollback(self):
        self.rollback_calls += 1
        self.main_transaction.active = False

    def close(self):
        self.close_calls += 1
        self._closed = True
        self._att = None


def test_demo_estate_sets_restart_unless_stopped():
    demo_source = (
        REPO_ROOT / 'tools' / 'reference_engine_demos' / 'demo_estate.py'
    ).read_text(encoding='utf-8')
    assert "'--restart', 'unless-stopped'" in demo_source or (
        '"--restart", "unless-stopped"' in demo_source
    )


def test_derived_target_namespace_isolates_sibling_databases():
    base_ns = '11111111-2222-4333-8444-555555555555'
    ns_db1 = _derived_target_namespace(base_ns, 'db-target-1')
    ns_db2 = _derived_target_namespace(base_ns, 'db-target-2')
    assert ns_db1 != base_ns
    assert ns_db2 != base_ns
    assert ns_db1 != ns_db2
    assert _derived_target_namespace(base_ns, 'db-target-1') == ns_db1


def test_sibling_database_mutations_do_not_rotate_server_profile_generation(
    monkeypatch,
):
    recorded_exclusions = []

    class _Registry(ProviderRegistry):
        def __init__(self):
            pass

        @contextmanager
        def endpoint_configuration_change(
            self, endpoint_id, *, ownership=None, exclude_session_namespaces=None
        ):
            recorded_exclusions.append(
                (endpoint_id, set(exclude_session_namespaces or ()))
            )
            yield

    fake_db_session = Mock()
    monkeypatch.setitem(
        sys.modules,
        'pgadmin.model',
        SimpleNamespace(db=SimpleNamespace(session=fake_db_session)),
    )

    service = EndpointService(
        _Registry(),
        SimpleNamespace(secrets=SimpleNamespace(register_resolver=Mock())),
    )
    initial_gen = '00000000-0000-4000-8000-000000000001'
    base_ns = '11111111-2222-4333-8444-555555555555'
    target1 = SimpleNamespace(
        id='db-1',
        database='/firebird/data/db1.fdb',
        display_name='db1.fdb',
        active=True,
        primary_target=True,
        configuration='{}',
        secret_references=[],
    )
    target2 = SimpleNamespace(
        id='db-2',
        database='/firebird/data/db2.fdb',
        display_name='db2.fdb',
        active=False,
        primary_target=False,
        configuration='{}',
        secret_references=[],
    )
    route = SimpleNamespace(
        id=1,
        priority=0,
        configuration=json.dumps({
            'host': '127.0.0.1',
            'port': 53050,
            'database': '/firebird/data/db1.fdb',
        }),
    )
    endpoint = SimpleNamespace(
        id='ep-fb-1',
        profile_id='firebird-native',
        provider_id='firebird',
        provider_version='0.1.0',
        profile_generation=initial_gen,
        resource_namespace=base_ns,
        session_namespace=base_ns,
        routes=[route],
        database_targets=[target1, target2],
        secret_references=[],
        runtime_identity=SimpleNamespace(verification_state='verified'),
    )
    server = SimpleNamespace(
        id=10,
        user_id=1,
        username='SYSDBA',
        password='encrypted-secret',
        save_password=1,
        endpoint_profile=endpoint,
    )
    service._managed_endpoint = Mock(
        return_value=(endpoint, registration_profile('firebird-native'))
    )
    service._verify_database_target = Mock()
    service.database_catalog = Mock(return_value={'databases': []})

    db1_session_ns = _derived_target_namespace(base_ns, 'db-1')
    db2_session_ns = _derived_target_namespace(base_ns, 'db-2')

    service.activate_database(server, 'db-2')
    assert endpoint.profile_generation == initial_gen
    assert db1_session_ns in recorded_exclusions[-1][1]

    service.disconnect_database(server)
    assert endpoint.profile_generation == initial_gen

    service.delete_database_target(server, 'db-2', {'confirmation': 'db2.fdb'})
    assert endpoint.profile_generation == initial_gen
    assert db1_session_ns in recorded_exclusions[-1][1]
    assert db2_session_ns not in recorded_exclusions[-1][1]


def test_ram_only_credentials_desync_reports_unverified_after_restart():
    service = EndpointService(
        SimpleNamespace(),
        SimpleNamespace(
            secrets=SimpleNamespace(
                register_resolver=Mock(),
                register_reference=Mock(),
            ),
        ),
    )
    sec_uuid = '00000000-0000-4000-8000-000000000042'
    ep_uuid = '00000000-0000-4000-8000-000000000099'
    secret_ref = SimpleNamespace(
        id=sec_uuid,
        secret_kind='database_password',
        storage_kind='protected_column',
        secret_name='password',
        secret_reference='server:42:password',
        credential_kind='password',
        principal='SYSDBA',
        purpose='connect',
    )
    route = SimpleNamespace(
        id=1,
        priority=0,
        configuration=json.dumps({
            'host': '127.0.0.1',
            'port': 53050,
            'credential_references': {'password': sec_uuid},
        }),
    )
    endpoint = SimpleNamespace(
        id=ep_uuid,
        profile_id='firebird-native',
        endpoint_mode='legacy_native',
        provider_version='0.1.0',
        routes=[route],
        database_targets=[],
        secret_references=[secret_ref],
        runtime_identity=SimpleNamespace(
            verification_state='verified',
            verified_version='5.0.4',
        ),
    )
    server = SimpleNamespace(
        id=42,
        user_id=1,
        username='SYSDBA',
        password=None,
        save_password=0,
        endpoint_profile=endpoint,
    )

    # Process restarted: SQLite says 'verified', but no saved password and empty RAM store.
    assert service.has_usable_credentials(server) is False
    assert service.effective_verification_state(server) == 'unverified'

    # User verifies in RAM for this session -> immediately reports 'verified'.
    service.resolver.remember('server:42:password', 'masterkey')
    assert service.has_usable_credentials(server) is True
    assert service.effective_verification_state(server) == 'verified'

    # Clearing RAM credentials reverts effective state to 'unverified'.
    service.resolver.forget('server:42:password')
    assert service.has_usable_credentials(server) is False
    assert service.effective_verification_state(server) == 'unverified'


def test_workspace_reconnect_session_routes_to_original_database_target():
    endpoint_calls = []

    def fake_workspace(server, database_target_id=None):
        endpoint_calls.append(database_target_id)
        ctx = SimpleNamespace(endpoint_id='ep-1', isolation_key=('ep-1', 'gen', 'ns'))
        return ctx, {}, None

    endpoint_service = SimpleNamespace(workspace=fake_workspace)
    studio_service = SimpleNamespace(
        session_database_target_id=Mock(return_value='db-target-2'),
        reconnect_session=Mock(return_value={
            'session_id': 'sess-2',
            'reconnected': True,
            'had_uncommitted_transaction': True,
        }),
    )
    ws = ProviderWorkspaceService(
        endpoint_service, SimpleNamespace(), studio_service, SimpleNamespace()
    )
    res = ws.reconnect_session(SimpleNamespace(id=42), 'sess-2')
    assert res['reconnected'] is True
    assert res['had_uncommitted_transaction'] is True
    assert endpoint_calls == ['db-target-2']


def test_firebird_pooled_catalog_reuses_healthy_handle_and_replaces_stale():
    created = []

    def make_conn(_request):
        idx = len(created) + 1
        conn = _FakeFirebirdConn(name=f'pooled-{idx}', healthy=True)
        created.append(conn)
        return conn

    fake_client = Mock(spec=FirebirdQueryClient)
    fake_client._admission = threading.RLock()
    fake_client._connections = []
    fake_client._attachment_states = {}
    fake_client._closed = False
    fake_client._uses_server_scope.return_value = False
    fake_client._connect.side_effect = make_conn
    fake_client._forget_connection.side_effect = (
        lambda c: fake_client._connections.remove(c)
        if c in fake_client._connections else None
    )

    provider = object.__new__(FirebirdProvider)
    provider.client = fake_client
    provider._catalog_pool = {}
    provider._catalog_pool_lock = threading.RLock()

    req = {'route': {'host': '127.0.0.1', 'port': 53050, 'database': 'demo.fdb'}}
    observed_handles = []

    def fake_list(scoped_req):
        observed_handles.append(scoped_req['_provider_session_handle'])
        return [{'resource_id': 'table:T1'}]

    assert provider._run_with_pooled_catalog(req, fake_list) == [{'resource_id': 'table:T1'}]
    assert provider._run_with_pooled_catalog(req, fake_list) == [{'resource_id': 'table:T1'}]
    assert len(created) == 1
    assert observed_handles[0] is observed_handles[1]
    assert created[0].ping_calls == 1

    # Simulate idle disconnect on pooled handle -> transparently opens pooled-2.
    created[0].healthy = False
    assert provider._run_with_pooled_catalog(req, fake_list) == [{'resource_id': 'table:T1'}]
    assert len(created) == 2
    assert created[0].close_calls >= 1
    assert observed_handles[2] is created[1]


def test_firebird_session_autocommit_reconnect_vs_uncommitted_transaction_guard(
    monkeypatch,
):
    opened = []

    def connector(**_kwargs):
        conn = _FakeFirebirdConn(
            name=f'session-{len(opened) + 1}',
            healthy=True,
            autocommit=True,
        )
        opened.append(conn)
        return conn

    monkeypatch.setitem(
        sys.modules,
        'fake_fb_phase3_driver',
        SimpleNamespace(connect=connector),
    )

    config = RelationalClientConfig(
        profile=FIREBIRD_PILOT_PROFILE,
        module_name='fake_fb_phase3_driver',
        version_query='SELECT 1',
        connect_arguments=lambda r: dict(r),
        metadata_reader=lambda _c, _r: [],
        transaction_observer=observe_transaction,
        failed_session_releaser=lambda conn: conn.close(),
    )
    client = FirebirdQueryClient(config)
    handle = client.open_session({
        'route': {
            'host': '127.0.0.1',
            'port': 53050,
            'database': '/firebird/data/demo.fdb',
            'transaction_auto_commit': True,
        },
    })
    state = client._state(handle)
    assert len(opened) == 1

    # Case 1: Clean/autocommit state + transient liveness/cleanup/cancel flags -> auto-reconnects!
    state.attachment_liveness_failed = True
    state.result_cleanup_failed = True
    state.cancellation_state_unknown = True
    with client._exclusive(handle) as live_state:
        assert live_state.attachment_liveness_failed is False
        assert live_state.result_cleanup_failed is False
        assert live_state.cancellation_state_unknown is False
        assert live_state.reconnected_count == 1
    assert len(opened) == 2

    # Case 2: Explicit uncommitted user transaction open + attachment drop -> MUST guard!
    state.explicit_transaction_open = True
    handle.healthy = False
    tx_obs = client.describe_transaction(handle)
    assert tx_obs['code'] == 'TRANSACTION_CONNECTION_LOST'
    assert tx_obs['reconnect_required'] is True
    assert tx_obs['had_uncommitted_transaction'] is True
    assert state.uncommitted_connection_lost is True
    assert 335544856 in CONNECTION_DROP_GDS_CODES

    # Subsequent calls continue reporting TRANSACTION_CONNECTION_LOST until user confirms reconnect.
    with pytest.raises(RelationalClientError) as blocked_exc:
        with client._exclusive(handle):
            pass
    assert getattr(blocked_exc.value, 'code', None) == 'TRANSACTION_CONNECTION_LOST'
    assert getattr(blocked_exc.value, 'reconnect_required', False) is True
    assert getattr(blocked_exc.value, 'had_uncommitted_transaction', False) is True

    # Explicit reconnect_session restores usability and reports had_uncommitted_transaction=True.
    outcome = client.reconnect_session(handle)
    assert outcome['reconnected'] is True
    assert outcome['had_uncommitted_transaction'] is True
    assert state.uncommitted_connection_lost is False
    assert state.explicit_transaction_open is False
    with client._exclusive(handle) as clean_state:
        assert clean_state.reconnected_count == 2


def test_data_studio_keeps_sibling_database_sessions_isolated():
    studio = object.__new__(DataStudioService)
    studio._lock = threading.RLock()
    studio._sessions = {
        'sess-db1': SimpleNamespace(database_target_id='db-1'),
        'sess-db2': SimpleNamespace(database_target_id='db-2'),
    }
    studio._occurrences = {
        'occ-db1': SimpleNamespace(session_id='sess-db1'),
    }
    assert studio.session_database_target_id('sess-db1') == 'db-1'
    assert studio.session_database_target_id('sess-db2') == 'db-2'
    assert studio.occurrence_database_target_id('occ-db1') == 'db-1'
    assert studio.session_database_target_id('missing') is None


def test_firebird_network_database_context_menu_deduplicates_connect():
    profile = registration_profile('firebird-native')
    target = {
        'target_id': 'fb-demo',
        'database': '/firebird/data/cdeadmin_demo.fdb',
        'display_name': 'cdeadmin_demo.fdb',
        'active': False,
        'primary': True,
    }
    actions = database_target_context_actions(
        profile, target, runtime_version='5.0.4'
    )
    connect_actions = [
        a for a in actions
        if a['command_id'].endswith('.connect')
        or a['command_id'].endswith('.connect_database')
        or a['label'].lower().rstrip('.').startswith('connect ')
    ]
    assert len(connect_actions) == 1
    assert connect_actions[0]['command_id'] == 'database.firebird.connect'


def test_firebird_monitoring_virtual_folder_exposes_mon_tables():
    resources = [
        {
            'resource_id': 'table:MON$ATTACHMENTS',
            'resource_kind': 'table',
            'display_name': 'MON$ATTACHMENTS',
            'display_path': ['MON$ATTACHMENTS'],
            'authority_path': ['MON$ATTACHMENTS'],
            'extensions': {'firebird': {'native': {'system_object': True}}},
        },
        {
            'resource_id': 'table:MON$STATEMENTS',
            'resource_kind': 'table',
            'display_name': 'MON$STATEMENTS',
            'display_path': ['MON$STATEMENTS'],
            'authority_path': ['MON$STATEMENTS'],
            'extensions': {'firebird': {'native': {'system_object': True}}},
        },
    ]
    visual_catalog = {'engine_id': 'firebird'}
    folders = resource_children(
        resources,
        {'scope': 'database', 'database': 'demo.fdb', 'target_id': 'fb-1'},
        visual_catalog=visual_catalog,
    )
    monitoring = next(
        f for f in folders if f.get('virtual_branch') == 'monitoring'
    )
    assert monitoring['has_children'] is True
    children = resource_children(
        resources,
        {
            'scope': 'kind',
            'resource_kind': 'firebird-folder',
            'virtual_branch': 'monitoring',
            'parent_path': [],
            'database': 'demo.fdb',
            'target_id': 'fb-1',
        },
        visual_catalog=visual_catalog,
    )
    child_names = [c['label'] for c in children]
    assert 'MON$ATTACHMENTS' in child_names
    assert 'MON$STATEMENTS' in child_names


def test_all_14_firebird_engine_object_forms_and_promoted_operations_complete():
    fb_caps = json.loads(
        (DESCRIPTORS_DIR / 'firebird' / 'capabilities.json').read_text(encoding='utf-8')
    )
    expected_14 = {
        'column',
        'constraint',
        'external-function',
        'exception',
        'character-set',
        'collation',
        'blob-filter',
        'authentication-mapping',
        'global-authentication-mapping',
        'shadow',
        'publication',
        'storage-file',
        'configuration',
        'service-operation',
    }
    kinds_by_id = {k['resource_kind']: k for k in fb_caps['kinds']}
    for kind_id in expected_14:
        entry = kinds_by_id[kind_id]
        form_rel = entry.get('form')
        assert form_rel == f'forms/{kind_id}.form.json', kind_id
        form_doc = json.loads(
            (DESCRIPTORS_DIR / 'firebird' / form_rel).read_text(encoding='utf-8')
        )
        assert form_doc['status'] == 'complete', kind_id
        assert len(form_doc['fields']) >= 1, kind_id

    for engine_id in ('mysql', 'sqlite', 'duckdb'):
        ops_doc = json.loads(
            (DESCRIPTORS_DIR / engine_id / 'operations.json').read_text(encoding='utf-8')
        )
        drafts = [
            op['operation_id']
            for op in ops_doc['operations']
            if op.get('status') == 'draft'
        ]
        assert drafts == [], f'{engine_id} still has draft operations: {drafts}'

    duck_ops = json.loads(
        (DESCRIPTORS_DIR / 'duckdb' / 'operations.json').read_text(encoding='utf-8')
    )['operations']
    duck_by_id = {
        (op['resource_kind'], op['operation_id']): op['status']
        for op in duck_ops
    }
    assert duck_by_id[('database', 'update_extensions')] == 'complete'
    assert duck_by_id[('extension', 'execute')] == 'complete'

    mariadb_tools = json.loads(
        (DESCRIPTORS_DIR / 'mariadb' / 'tools.json').read_text(encoding='utf-8')
    )['tools']
    mariadb_ids = {
        t['command_id'].replace('{engine_id}', 'mariadb')
        for t in mariadb_tools
    }
    for expected_id in (
        'endpoint.mariadb.monitoring',
        'endpoint.mariadb.monitoring_policy',
        'endpoint.mariadb.dashboard_editor',
        'endpoint.mariadb.server_catalog',
        'endpoint.mariadb.binlogs',
        'endpoint.mariadb.binlog_replay',
        'database.mariadb.monitoring',
        'database.mariadb.monitoring_policy',
        'database.mariadb.dashboard_editor',
        'database.mariadb.catalog_ddn',
        'database.mariadb.test_data',
    ):
        assert expected_id in mariadb_ids, expected_id
