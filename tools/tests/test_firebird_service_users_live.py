"""Firebird user changes through the Services API, against a real Firebird 5 server.

The earlier test of this path used a fake service manager. This one drives the
provider's validate, plan and apply against the demo container (a real security
database) and reads the result back with the driver's own service manager.
Skipped when the container is not running; every user it creates is deleted.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')):
    if entry not in sys.path:
        sys.path.insert(0, entry)

CONTAINER, PORT = 'cdeadmin-demo-firebird', 53050


def _password():
    try:
        env = subprocess.check_output(
            ['docker', 'inspect', CONTAINER, '--format', '{{range .Config.Env}}{{println .}}{{end}}'], text=True, timeout=20)
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'{CONTAINER} is not available: {error}')
    for line in env.splitlines():
        if line.startswith('FIREBIRD_ROOT_PASSWORD='):
            return line.split('=', 1)[1]
    pytest.skip('the demo container exposes no SYSDBA password')


@pytest.fixture
def rig():
    import firebird.driver as driver
    from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, PROFILE, _create_client
    from pgadmin.cdeadmin.security.secrets import SecretLease
    from tools.tests.test_cdeadmin_actual_engine_pilots import context
    password = _password()
    secrets = {'demo': password}

    def acquire(reference, principal, purpose, kind):
        return SecretLease(secrets[reference].encode('utf8'))
    permissions = SimpleNamespace(require=lambda *a, **k: True, acquire_secret=acquire)
    client = _create_client(permissions)
    provider = FirebirdProvider(context(PROFILE), permissions, client)
    try:
        manager = driver.connect_server(f'127.0.0.1/{PORT}', user='SYSDBA', password=password)
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'Firebird demo is not reachable: {error}')
    route = {'host': '127.0.0.1', 'port': PORT, 'user': 'SYSDBA',
             'credential_reference_id': 'demo', 'principal_reference': 'demo'}
    created = []

    def run(operation, draft, target=None):
        payload = {'resource_kind': 'user', 'operation_id': operation, 'draft': draft,
                   'target_resource': target, '_provider_route': dict(route)}
        assert provider.validate_visual_admin(payload) == {'errors': []}
        plan = provider.plan_visual_admin(payload)
        assert provider.apply_visual_admin({'plan_id': plan['plan_id']})['accepted']
        return plan

    def users():
        return {u.user_name: u for u in manager.user.get_all()}

    try:
        yield SimpleNamespace(run=run, users=users, created=created, provider=provider, route=route, secrets=secrets)
    finally:
        for name in created:
            try:
                manager.user.delete(name)
            except Exception:  # noqa: BLE001
                pass
        manager.close()
        client.close() if hasattr(client, 'close') else None


def test_create_alter_and_drop_a_user_through_the_provider(rig):
    name = 'SR_' + uuid.uuid4().hex[:8].upper()
    rig.created.append(name)
    plan = rig.run('create', {'name': name, 'password': 'Aa1!' + uuid.uuid4().hex[:8], 'first_name': 'Sr', 'administrator': False})
    assert 'Aa1!' not in str(plan)
    created = rig.users()[name]
    assert created.first_name == 'Sr' and not created.admin
    target = {'display_name': name}
    rig.run('alter', {'last_name': 'Test', 'administrator': True}, target)
    altered = rig.users()[name]
    assert altered.last_name == 'Test' and altered.admin
    # The roster markers the descriptor declares read these native fields.
    import json
    markers = json.loads((ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/firebird/security.json').read_text())['principals'][0]['roster']['markers']
    assert {m['field'] for m in markers} == {'administrator', 'active'}
    listed = rig.provider.list_resources({'_provider_route': dict(rig.route), 'route': dict(rig.route)})
    row = next(r for r in listed if r.get('display_name') == name)
    native = row['native']
    assert native['administrator'] is True and native['active'] is True
    rig.run('drop', {}, target)
    assert name not in rig.users()


def test_the_provider_lists_the_server_users_it_manages(rig):
    from pgadmin.cdeadmin.providers.firebird.provider import _read_server_service_user_resources
    import firebird.driver as driver
    name = 'SR_' + uuid.uuid4().hex[:8].upper()
    rig.created.append(name)
    rig.run('create', {'name': name, 'password': 'Aa1!' + uuid.uuid4().hex[:8]})
    manager = driver.connect_server(f'127.0.0.1/{PORT}', user='SYSDBA', password=_password())
    try:
        listed = {r['display_name']: r for r in _read_server_service_user_resources(manager, 'g')}
    finally:
        manager.close()
    assert name in listed and 'SYSDBA' in listed
    assert listed[name]['resource_kind'] == 'user'


def test_the_providers_server_scope_listing_returns_the_users(rig):
    """The listing used the database connector for a server route and swallowed the failure."""
    name = 'SR_' + uuid.uuid4().hex[:8].upper()
    rig.created.append(name)
    rig.run('create', {'name': name, 'password': 'Aa1!' + uuid.uuid4().hex[:8]})
    result = rig.provider.list_resources({'_provider_route': dict(rig.route), 'route': dict(rig.route)})
    items = result if isinstance(result, list) else (result.get('items') or result.get('resources') or [])
    users = {r['display_name'] for r in items if r.get('resource_kind') == 'user'}
    assert {name, 'SYSDBA'} <= users, sorted(users)


DATABASE = '/var/lib/firebird/data/cdeadmin_demo.fdb'


def _as(rig, name, password, **extra):
    rig.secrets[name] = password
    route = {'host': '127.0.0.1', 'port': PORT, 'user': name, 'credential_reference_id': name,
             'principal_reference': name, **extra}
    return rig.provider.list_resources({'_provider_route': dict(route), 'route': dict(route)})


def test_what_a_non_administrator_sees_is_what_the_server_returns(rig):
    """The earlier host reported a "limited" view. The server itself limits a plain user: at database
    scope the user list is just the account itself, and at server scope it also withholds
    the administrator-only server facts, which the provider says rather than failing."""
    if not os.environ.get('CDEADMIN_FIREBIRD_CLIENT_LIBRARY'):
        pytest.skip('set CDEADMIN_FIREBIRD_CLIENT_LIBRARY to a Firebird 5 client to attach to a database')
    name = 'SR_' + uuid.uuid4().hex[:8].upper()
    password = 'Aa1!' + uuid.uuid4().hex[:8]
    rig.created.append(name)
    rig.run('create', {'name': name, 'password': password, 'administrator': False})
    admin_view = {r['display_name'] for r in _as(rig, 'demo_admin', _password(), database=DATABASE, user='SYSDBA')
                  if r.get('resource_kind') == 'user'}
    plain_view = _as(rig, name, password, database=DATABASE)
    assert {r['display_name'] for r in plain_view if r.get('resource_kind') == 'user'} == {name}
    assert {name, 'SYSDBA'} <= admin_view
    def server_native(view):
        return next(r for r in view if r['resource_kind'] == 'server')['extensions']['firebird']['native']

    server_view = _as(rig, name, password)
    plain = server_native(server_view)
    assert plain['administrator_only_unavailable'] == ['home_directory', 'connection_count'], plain
    assert 'version' in plain and 'home_directory' not in plain
    # The Services API user list is limited by the server to the account itself.
    assert {r['display_name'] for r in server_view if r['resource_kind'] == 'user'} == {name}
    admin = server_native(_as(rig, 'demo_admin', _password(), user='SYSDBA'))
    assert 'home_directory' in admin and 'administrator_only_unavailable' not in admin
