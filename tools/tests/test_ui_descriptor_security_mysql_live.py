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
        yield SimpleNamespace(names=names, listed=listed, run=run, one=one, tag=tag)
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
