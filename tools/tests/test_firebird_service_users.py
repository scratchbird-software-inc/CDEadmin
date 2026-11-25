"""Firebird user changes through the Services API (Decision 21).

When a network server has no registered database there is nothing to attach a
SQL session to, so the provider manages users through the Services API, as the
earlier Security Manager host did. This file ports those checks to the provider.

The Services API itself is exercised with a fake service manager: this
environment has Firebird client libraries only, no server, so the native effect
is NOT verified live here (the embedded runtime has no security database).
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import users
from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider, PROFILE, _create_client
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from tools.tests.test_cdeadmin_actual_engine_pilots import context, Permissions

SERVER_ROUTE = {'host': '127.0.0.1', 'port': 53050, 'user': 'SYSDBA'}


class FakeUsers:
    def __init__(self):
        self.added, self.updated, self.deleted = [], [], []

    def add(self, **kwargs):
        self.added.append(kwargs)

    def update(self, name, **kwargs):
        self.updated.append((name, kwargs))

    def delete(self, name):
        self.deleted.append(name)


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr('pgadmin.cdeadmin.providers.firebird.provider._configure_client_library', Mock())
    client = _create_client(SimpleNamespace(acquire_secret=None))
    service = SimpleNamespace(user=FakeUsers())
    routes = []

    def connect(payload):
        route = dict(payload.get('route') or {})
        routes.append(route)
        if route.get('database') == 'security.db':
            raise RuntimeError('Firebird connection failed; status codes: 335544352')
        return service

    client._connect_server = connect
    client._forget_and_close = Mock()
    provider = FirebirdProvider(context(PROFILE), Permissions(), client)
    return SimpleNamespace(provider=provider, service=service, routes=routes, client=client)


def request(operation, draft, target=None, route=SERVER_ROUTE):
    return {'resource_kind': 'user', 'operation_id': operation, 'draft': draft,
            'target_resource': target, '_provider_route': dict(route)}


def test_create_compiles_a_redacted_preview_and_keeps_the_password_out_of_it():
    compiled = users.compile_service_operation('create', {'name': 'SVC_USER', 'password': 'Strong!Password9'})
    assert compiled['preview'] == 'SERVICES API ADD USER "SVC_USER" PASSWORD <redacted>'
    assert 'Strong!Password9' not in json.dumps(compiled['preview'])
    assert compiled['service_call'] == {'operation': 'create', 'user_name': 'SVC_USER', 'password': 'Strong!Password9'}


def test_create_without_a_password_is_refused():
    with pytest.raises(RelationalClientError, match='non-empty password'):
        users.compile_service_operation('create', {'name': 'SVC_USER'})


@pytest.mark.parametrize('field,value', [('plugin', 'Legacy_UserManager'), ('tags', [{'name': 'a', 'value': 'b'}]),
                                         ('description', 'Ops'), ('active', True)])
def test_a_field_the_services_api_cannot_carry_is_refused_not_dropped(field, value):
    with pytest.raises(RelationalClientError, match='manages only the name, password'):
        users.compile_service_operation('create', {'name': 'U', 'password': 'p', field: value})


def test_name_components_and_the_administrator_flag_are_carried():
    compiled = users.compile_service_operation('alter', {
        'first_name': 'Alice', 'last_name': 'Ng', 'administrator': True, 'password': 'new-pw'},
        target={'display_name': 'ALICE'})
    assert compiled['service_call'] == {'operation': 'alter', 'user_name': 'ALICE', 'password': 'new-pw',
                                        'first_name': 'Alice', 'last_name': 'Ng', 'admin': True}
    assert compiled['preview'] == 'SERVICES API UPDATE USER "ALICE" PASSWORD <redacted>'


def test_an_empty_alteration_is_refused():
    with pytest.raises(RelationalClientError, match='no changes'):
        users.compile_service_operation('alter', {}, target={'display_name': 'ALICE'})


def test_a_hostile_name_is_quoted_in_the_preview():
    with pytest.raises(RelationalClientError):
        users.compile_service_operation('create', {'name': 'X"; DROP USER SYSDBA; --' * 6, 'password': 'p'})
    compiled = users.compile_service_operation('delete'.replace('delete', 'drop'), {}, target={'display_name': 'a"b'})
    assert compiled['preview'] == 'SERVICES API DELETE USER "a""b"'


def test_with_no_database_the_provider_plans_validates_and_applies_through_the_service_manager(rig):
    payload = request('create', {'name': 'SVC_USER', 'password': 'Strong!Password9', 'administrator': False})
    assert rig.provider.validate_visual_admin(payload) == {'errors': []}
    public = rig.provider.plan_visual_admin(payload)
    # The public plan shows the intended action with the secret redacted, and carries no payload.
    assert 'provider_payload' not in public
    assert 'Strong!Password9' not in json.dumps(public)
    assert public['command_preview']['statements'] == [{'source': 'SERVICES API ADD USER "SVC_USER" PASSWORD <redacted>'}]
    result = rig.provider.apply_visual_admin({'plan_id': public['plan_id']})
    assert result == {'accepted': True, 'plan_id': public['plan_id']}
    assert rig.service.user.added == [{'user_name': 'SVC_USER', 'password': 'Strong!Password9', 'admin': False}]
    rig.client._forget_and_close.assert_called_once()
    # It never tried to attach a remote session to security.db.
    assert all(route.get('database') != 'security.db' for route in rig.routes)


def test_alter_and_drop_use_the_service_manager_too(rig):
    target = {'display_name': 'ALICE'}
    alter = rig.provider.plan_visual_admin(request('alter', {'first_name': 'Alice'}, target))
    rig.provider.apply_visual_admin({'plan_id': alter['plan_id']})
    drop = rig.provider.plan_visual_admin(request('drop', {}, target))
    rig.provider.apply_visual_admin({'plan_id': drop['plan_id']})
    assert rig.service.user.updated == [('ALICE', {'password': None, 'first_name': 'Alice'})]
    assert rig.service.user.deleted == ['ALICE']


def test_validation_reports_a_refusal_instead_of_raising(rig):
    verdict = rig.provider.validate_visual_admin(request('create', {'name': 'U', 'password': 'p', 'plugin': 'X'}))
    assert verdict['errors'][0]['code'] == 'invalid_user'
    assert 'manages only the name' in verdict['errors'][0]['message']


def test_a_plan_is_applied_once(rig):
    public = rig.provider.plan_visual_admin(request('drop', {}, {'display_name': 'ALICE'}))
    rig.provider.apply_visual_admin({'plan_id': public['plan_id']})
    assert len(rig.service.user.deleted) == 1
    assert public['plan_id'] not in rig.provider._custom_user_plans


def test_a_route_with_a_database_does_not_take_the_services_path(rig):
    route = {**SERVER_ROUTE, 'database': '/data/app.fdb'}
    assert rig.provider._service_user_request(request('create', {'name': 'U'}, route=route)) is False
    assert rig.provider._service_user_request(request('create', {'name': 'U'})) is True
    # Only user changes are routed this way.
    other = {**request('create', {'name': 'R'}), 'resource_kind': 'role'}
    assert rig.provider._service_user_request(other) is False


def test_a_user_with_name_components_validates_and_plans_through_the_provider_on_a_database_route(rig):
    """The SQL lifecycle path (name parts, tags, comment) is reachable from the provider.

    provider.py once called users.compile_lifecycle_operation without importing
    users, so any such user change raised NameError before reaching the engine.
    """
    route = {**SERVER_ROUTE, 'database': '/data/app.fdb'}
    payload = request('create', {'name': 'ALICE', 'password': 'S3cret!Pw9', 'first_name': 'Alice'}, route=route)
    assert rig.provider.validate_visual_admin(payload) == {'errors': []}
    public = rig.provider.plan_visual_admin(payload)
    statements = [row['source'] for row in public['command_preview']['statements']]
    assert statements and statements[0].startswith('CREATE USER "ALICE"')
    assert all('S3cret!Pw9' not in statement for statement in statements)
    assert 'S3cret!Pw9' not in json.dumps(public)


def test_the_firebird_provider_modules_use_no_undefined_names():
    """A name used but never bound raises NameError only when its branch runs.

    uuid and copy were once missing from provider.py, so the custom user
    lifecycle could not run at all while every test that skipped that branch passed.
    """
    import ast
    import builtins
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/providers/firebird'
    problems = {}
    for name in ('provider.py', 'users.py', 'privileges.py', 'object_privileges.py'):
        tree = ast.parse((root / name).read_text(encoding='utf-8'))
        bound = set(dir(builtins))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
        missing = sorted({node.id for node in ast.walk(tree)
                          if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound})
        if missing:
            problems[name] = missing
    assert problems == {}


class _Cursor:
    """Answers the SEC$ catalog queries a server-user listing makes."""

    def __init__(self, users):
        self.users, self.rows = users, []

    def execute(self, sql, *_args):
        self.rows = self.users if 'FROM SEC$USERS' in sql.upper() else []

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass


def test_server_users_are_listed_from_the_security_catalog():
    from pgadmin.cdeadmin.providers.firebird.provider import _read_server_security_sql_resources
    row = ('SYSDBA', 'Srp', 'System', '', 'Admin', True, True, '')
    connection = SimpleNamespace(cursor=lambda: _Cursor([row]))
    found = [r for r in _read_server_security_sql_resources(connection, 'g') if r['resource_kind'] == 'user']
    assert [r['display_name'] for r in found] == ['SYSDBA']
    assert found[0]['native']['plugin'] == 'Srp' and found[0]['native']['administrator'] is True
    assert found[0]['native']['scope'] == 'server'


def test_server_users_fall_back_to_the_service_manager_when_there_is_no_database():
    from pgadmin.cdeadmin.providers.firebird.provider import _read_server_service_user_resources
    info = SimpleNamespace(user_name='SYSDBA', first_name='System', middle_name='', last_name='Admin', admin=True)
    service = SimpleNamespace(user=SimpleNamespace(get_all=lambda: [info]))
    found = _read_server_service_user_resources(service, 'g')
    assert [r['display_name'] for r in found] == ['SYSDBA']
    assert found[0]['native']['administrator'] is True
    assert found[0]['native']['navigator_scope'] == 'server'


def test_a_security_database_is_never_synthesised_for_a_server_route(rig):
    """A network server must not be asked to attach to security.db remotely (GDS 335544352)."""
    assert rig.provider._resolve_server_security_database_candidates(SERVER_ROUTE) == []
    assert rig.provider._resolve_server_security_database_candidates(
        {**SERVER_ROUTE, 'database': '/data/app.fdb'}) == ['/data/app.fdb']
