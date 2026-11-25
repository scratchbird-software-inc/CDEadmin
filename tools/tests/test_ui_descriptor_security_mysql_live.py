"""MySQL role membership and privilege operations, live (Decision 21).

Dialog drafts built from the declared ``operations.json`` entries go through the
provider's validate, plan and apply on the demo MySQL container, and the effect
is read back from the server. Skipped when the container is not running. Every
account, role and grant this creates is dropped afterwards.

Privilege operations are reviewed with MySQL Shell's native grammar library; set
``CDEADMIN_MYSQL_PARSER_LIBRARY`` to its ``yparser/mysql_9.7.so`` (with the
sibling ``libmysql_deps.so``) or that test is skipped, not passed.
"""
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')):
    if entry not in sys.path:
        sys.path.insert(0, entry)
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from ui_descriptor_roundtrip import engine_operations, operation_backend_draft, operation_draft  # noqa: E402

CONTAINER, PORT, SCHEMA = 'cdeadmin-demo-mysql', 53306, 'cdeadmin_demo'
OPERATIONS = engine_operations('mysql')


def _root_password():
    try:
        env = subprocess.check_output(
            ['docker', 'inspect', CONTAINER, '--format', '{{range .Config.Env}}{{println .}}{{end}}'],
            text=True, timeout=20)
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'{CONTAINER} is not available: {error}')
    for line in env.splitlines():
        if line.startswith('MYSQL_ROOT_PASSWORD='):
            return line.split('=', 1)[1]
    pytest.skip('the demo container does not expose a root password')


@pytest.fixture
def env():
    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _create_client
    from tools.mysql_driver_gate_support import provider_access
    password = _root_password()
    settings = {'host': '127.0.0.1', 'port': PORT, 'user': 'root', 'database': SCHEMA}
    try:
        server = mysql.connector.connect(**settings, password=password, autocommit=True)
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'MySQL demo is not reachable: {error}')
    tag = uuid.uuid4().hex[:8]
    names = SimpleNamespace(role=f'sr_role_{tag}', member=f'sr_user_{tag}', table=f'sr_t_{tag}')
    cursor = server.cursor()
    for statement in (
            f'CREATE ROLE `{names.role}`@`%`',
            f"CREATE USER `{names.member}`@`%` IDENTIFIED BY '{uuid.uuid4().hex}'",
            f'CREATE TABLE `{SCHEMA}`.`{names.table}` (id INT PRIMARY KEY, a INT, b INT)'):
        cursor.execute(statement)
    route, permissions = provider_access({**settings, 'ssl': False}, password=password)
    client = _create_client(MYSQL_PROFILE, permissions, SimpleNamespace(pool_namespace='sec-' + tag))

    def listed(kind):
        return [r for r in client.list_resources({'route': dict(route)}) if r['resource_kind'] == kind]

    def run(kind, operation_id, values, target=None):
        operation = OPERATIONS[f'{operation_id}@{kind}']
        payload = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target,
                   '_provider_route': route, 'draft': operation_backend_draft(operation, operation_draft(operation, values))}
        verdict = MYSQL_ADMINISTRATION.validate(payload)
        assert verdict['errors'] == [], verdict
        planned = client.plan_admin_operation(payload)
        result = client.apply_admin_operation(planned)
        assert result['accepted'], result
        return planned

    def one(sql, params=()):
        cursor.execute(sql, params)
        return cursor.fetchall()

    try:
        yield SimpleNamespace(names=names, listed=listed, run=run, one=one, exec=lambda sql: cursor.execute(sql), tag=tag)
    finally:
        client.close()
        for statement in (f'DROP TABLE IF EXISTS `{SCHEMA}`.`{names.table}`',
                          f'DROP USER IF EXISTS `{names.member}`@`%`', f'DROP ROLE IF EXISTS `{names.role}`@`%`'):
            cursor.execute(statement)
        cursor.close()
        server.close()


def role_target(env):
    name = env.names.role
    matches = [r for r in env.listed('role') if r['resource_id'] == f'role:{name}@%']
    assert matches, 'the provider does not list the role it just saw created'
    return matches[0]


def test_role_membership_round_trips_and_the_listing_reports_it(env):
    names = env.names
    target = role_target(env)
    env.run('role', 'grant', {'member_user': names.member, 'member_host': '%', 'admin_option': True,
                              'confirmation': names.role}, target)
    edges = env.one('SELECT WITH_ADMIN_OPTION FROM mysql.role_edges WHERE FROM_USER=%s AND TO_USER=%s',
                    (names.role, names.member))
    assert edges == [('Y',)]
    member = next(r for r in env.listed('user') if r['resource_id'] == f'user:{names.member}@%')
    memberships = member['native']['member_of']
    assert [m for m in memberships if m['user'] == names.role and m['host'] == '%'], memberships
    env.run('role', 'revoke', {'member_user': names.member, 'member_host': '%', 'confirmation': names.role}, target)
    assert env.one('SELECT 1 FROM mysql.role_edges WHERE FROM_USER=%s AND TO_USER=%s',
                   (names.role, names.member)) == []


def test_every_account_is_listed_as_both_a_user_and_a_role(env):
    """MySQL cannot tell a role from an account; the provider says so rather than guessing."""
    key = f'@%'
    users = {r['resource_id'] for r in env.listed('user')}
    roles = {r['resource_id'] for r in env.listed('role')}
    assert f'user:{env.names.member}{key}' in users and f'role:{env.names.member}{key}' in roles
    assert all(r['native'].get('named_account_role_alias') for r in env.listed('role')
               if r['resource_id'].startswith('role:' + env.names.member))


def test_table_privilege_grant_and_revoke_round_trip_with_columns(env):
    names = env.names
    base = {'grantees': [{'user': names.member, 'host': '%'}], 'object_type': 'TABLE',
            'database': SCHEMA, 'object': names.table}
    from pgadmin.cdeadmin.sdk import RelationalClientError
    try:
        env.run('privilege', 'grant', {**base, 'privileges': [{'name': 'SELECT'}]})
    except RelationalClientError as error:
        if 'grammar' in str(error):
            pytest.skip(str(error))
        raise
    env.run('privilege', 'revoke', {**base, 'privileges': [{'name': 'SELECT'}], 'confirmation': f"{names.member}@%"})
    env.run('privilege', 'grant', {**base, 'privileges': [{'name': 'SELECT'}, {'name': 'UPDATE', 'columns': ['a']}],
                                   'grant_option': True})
    table = env.one('SELECT PRIVILEGE_TYPE, IS_GRANTABLE FROM information_schema.TABLE_PRIVILEGES '
                    'WHERE GRANTEE=%s AND TABLE_NAME=%s', (f"'{names.member}'@'%'", names.table))
    assert ('SELECT', 'YES') in table
    columns = env.one('SELECT COLUMN_NAME, PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES '
                      'WHERE GRANTEE=%s AND TABLE_NAME=%s', (f"'{names.member}'@'%'", names.table))
    assert columns == [('a', 'UPDATE')]
    listed = [r['native'] for r in env.listed('privilege') if r['native'].get('table_name') == names.table]
    assert {(n['privilege'], n.get('column_name')) for n in listed} >= {('SELECT', None), ('UPDATE', 'a')}, listed
    env.run('privilege', 'revoke', {**base, 'privileges': [{'name': 'SELECT'}, {'name': 'UPDATE', 'columns': ['a']}],
                                    'confirmation': f"{names.member}@%"})
    left = env.one('SELECT PRIVILEGE_TYPE, IS_GRANTABLE FROM information_schema.TABLE_PRIVILEGES '
                   'WHERE GRANTEE=%s AND TABLE_NAME=%s', (f"'{names.member}'@'%'", names.table))
    # MySQL keeps the grant option after its privileges are revoked, as USAGE; it is its own privilege.
    assert left == [('USAGE', 'YES')], left
    env.run('privilege', 'revoke', {**base, 'privileges': [{'name': 'GRANT OPTION'}],
                                    'confirmation': f"{names.member}@%"})
    assert env.one('SELECT 1 FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=%s AND TABLE_NAME=%s',
                   (f"'{names.member}'@'%'", names.table)) == []


def _security():
    import json
    return json.loads((ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/mysql/security.json').read_text(encoding='utf-8'))


def _rows(env, grantee):
    return [r['native'] for r in env.listed('privilege') if r['native'].get('grantee') == grantee]


def _match(listing, kind, native, path):
    """The Python twin of grantRows' filter in DescriptorObjectGrants.jsx."""
    spec = listing['kinds'][kind]
    return (native.get(listing['scope_field']) in spec['scopes']
            and all(native.get(field) == path[len(path) - len(spec['fields']) + i] for i, field in enumerate(spec['fields']))
            and all(native.get(k) == v for k, v in (spec.get('where') or {}).items()))


def test_the_declared_listing_finds_every_scope_the_server_reports(env):
    """The descriptor's grants.listing and grantee template, applied to what the provider returns live."""
    security = _security()
    listing = security['grants']['listing']
    names = env.names
    account = security['grants']['listing']['grantee_template'].format(name=names.member, host='%')
    assert account == f"'{names.member}'@'%'"
    routine = f'sr_p_{env.tag}'
    for statement in (f'CREATE PROCEDURE `{SCHEMA}`.`{routine}`() BEGIN END',
                      f'GRANT PROCESS ON *.* TO `{names.member}`@`%`',
                      f'GRANT SELECT ON `{SCHEMA}`.* TO `{names.member}`@`%` WITH GRANT OPTION',
                      f'GRANT SELECT, UPDATE ON `{SCHEMA}`.`{names.table}` TO `{names.member}`@`%`',
                      f'GRANT INSERT (a) ON `{SCHEMA}`.`{names.table}` TO `{names.member}`@`%`',
                      f'GRANT EXECUTE ON PROCEDURE `{SCHEMA}`.`{routine}` TO `{names.member}`@`%`'):
        env.exec(statement)
    try:
        rows = _rows(env, account)
        by_scope = {}
        for native in rows:
            by_scope.setdefault(native['scope'], []).append(native)
        assert set(by_scope) == {'global', 'database', 'table', 'column', 'routine'}, sorted(by_scope)
        assert [n['privilege'] for n in by_scope['global']] == ['PROCESS']
        table_path = [SCHEMA, names.table]
        found = [(n['privilege'], n.get('column_name')) for n in rows if _match(listing, 'table', n, table_path)]
        assert sorted(found, key=str) == sorted([('SELECT', None), ('UPDATE', None), ('INSERT', 'a')], key=str), found
        assert [n['privilege'] for n in rows if _match(listing, 'database', n, [SCHEMA])] == ['SELECT']
        assert [n['privilege'] for n in rows if _match(listing, 'procedure', n, [SCHEMA, routine])] == ['EXECUTE']
        assert not [n for n in rows if _match(listing, 'function', n, [SCHEMA, routine])]
        grantable = {n['privilege']: n[listing['grant_option_field']] for n in by_scope['database']}
        assert grantable == {'SELECT': listing['grant_option_equals']}
    finally:
        env.exec(f'DROP PROCEDURE IF EXISTS `{SCHEMA}`.`{routine}`')


def test_a_grant_option_left_after_revoking_privileges_is_listed_as_usage(env):
    names = env.names
    account = f"'{names.member}'@'%'"
    env.exec(f'GRANT SELECT ON `{SCHEMA}`.`{names.table}` TO `{names.member}`@`%` WITH GRANT OPTION')
    env.exec(f'REVOKE SELECT ON `{SCHEMA}`.`{names.table}` FROM `{names.member}`@`%`')
    listing = _security()['grants']['listing']
    left = [n for n in _rows(env, account) if _match(listing, 'table', n, [SCHEMA, names.table])]
    assert [(n['privilege'], n[listing['grant_option_field']]) for n in left] == [('USAGE', 'YES')], left


def test_the_membership_listings_name_fields_the_provider_returns(env):
    names = env.names
    membership = _security()['membership']
    env.exec(f'GRANT `{names.role}`@`%` TO `{names.member}`@`%` WITH ADMIN OPTION')
    env.exec(f'SET DEFAULT ROLE `{names.role}`@`%` TO `{names.member}`@`%`')
    role = next(r for r in env.listed('role') if r['resource_id'] == f'role:{names.role}@%')
    account = next(r for r in env.listed('user') if r['resource_id'] == f'user:{names.member}@%')
    members = role['native'][membership['listing']['native_field']]
    held = account['native'][membership['member_of_listing']['native_field']]
    assert [m['principal'] for m in members] == [f'{names.member}@%']
    assert [h['role'] for h in held] == [f'{names.role}@%']
    for column in membership['listing']['columns']:
        assert column['field'] in members[0], column
    for column in membership['member_of_listing']['columns']:
        assert column['field'] in held[0], column
    assert members[0]['admin_option'] is True and held[0]['default_role'] is True
