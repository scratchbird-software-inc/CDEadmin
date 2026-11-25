"""Firebird role membership and privilege operations, live (Decision 21).

The dialog draft built from the declared ``operations.json`` entries goes
through the provider's validate, plan and apply on a real embedded Firebird 5
engine, and the effect is read back from ``RDB$USER_PRIVILEGES``. Skipped when
no embedded runtime is available; nothing here uses a mock for the engine.
"""
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from pgadmin.cdeadmin.user_config_db.service import _load_firebird_driver  # noqa: E402
from ui_descriptor_roundtrip import (  # noqa: E402
    engine_operations, operation_backend_draft, operation_draft)

DESCRIPTORS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors'
OPERATIONS = engine_operations('firebird')


@pytest.fixture(scope='module')
def provider():
    try:
        from pgadmin.cdeadmin.providers.firebird.provider import (
            ADMINISTRATION, _create_client, _resources)
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'Firebird provider is unavailable: {error}')
    return SimpleNamespace(administration=ADMINISTRATION, create=_create_client, resources=_resources)


@pytest.fixture
def env(tmp_path, provider):
    try:
        driver = _load_firebird_driver(tmp_path / 'locks')
        database = tmp_path / 'security.fdb'
        seed = driver.create_database(str(database), user='SYSDBA', charset='UTF8')
    except Exception as error:  # noqa: BLE001
        pytest.skip(f'No embedded Firebird 5 runtime: {error}')
    for statement in (
            'CREATE TABLE T1(ID INTEGER NOT NULL PRIMARY KEY, N VARCHAR(10), M VARCHAR(10))',
            'CREATE ROLE R_ONE',
            'CREATE ROLE R_TWO'):
        seed.execute_immediate(statement)
        seed.commit()
    seed.close()
    permissions = SimpleNamespace(require=lambda *args, **kwargs: True,
                                  acquire_secret=lambda *args: SecretLease(''))
    client = provider.create(permissions, attachment_mode='embedded')
    route = {'database': str(database), 'user': 'SYSDBA', 'attachment_mode': 'embedded',
             'filesystem_root': str(tmp_path)}

    def resources():
        connection = client._connect({'route': dict(route)})
        try:
            return list(provider.resources(connection, {}))
        finally:
            client._forget_and_close(connection)

    def request(kind, operation_id, values, target):
        """What the OperationDialog sends: its state (defaults plus input) mapped
        through toOperationDraft, which drops fields hidden by visible_when."""
        operation = OPERATIONS[f'{operation_id}@{kind}']
        state = operation_draft(operation, values)
        return {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target,
                '_provider_route': route, 'draft': operation_backend_draft(operation, state)}

    def run(kind, operation_id, values, target=None):
        payload = request(kind, operation_id, values, target)
        verdict = provider.administration.validate(payload)
        assert verdict['errors'] == [], verdict
        planned = provider.administration.plan(payload)
        statements = [row['source'] for row in planned['command_preview']['statements']]
        result = provider.administration.apply(client, planned)
        assert result['accepted'], result
        return statements

    def refusal(kind, operation_id, values, target=None):
        """The provider's validation messages; nothing is planned or applied."""
        verdict = provider.administration.validate(request(kind, operation_id, values, target))
        assert verdict['errors'], 'the provider accepted a draft it must refuse'
        return [row['message'] for row in verdict['errors']]

    def observe(where, parameters=()):
        connection = driver.connect(str(database), user='SYSDBA')
        try:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT TRIM(RDB$USER), TRIM(RDB$RELATION_NAME), TRIM(RDB$PRIVILEGE), '
                'RDB$GRANT_OPTION, TRIM(RDB$FIELD_NAME) FROM RDB$USER_PRIVILEGES WHERE ' + where,
                parameters)
            return sorted(cursor.fetchall(), key=lambda row: tuple(str(c) for c in row))
        finally:
            connection.close()

    def role(name):
        return next(r for r in resources() if r['resource_kind'] == 'role' and r['display_name'] == name)

    try:
        yield SimpleNamespace(run=run, refusal=refusal, observe=observe, role=role)
    finally:
        client.close()


def test_the_declared_operations_exist_and_match_the_provider_vocabulary():
    for key in ('grant@role', 'revoke@role', 'grant@privilege', 'revoke@privilege'):
        assert key in OPERATIONS, key
        assert OPERATIONS[key]['tier'] == 2
        assert OPERATIONS[key]['menu']['category'] == 'security'
    role_fields = {f['field_id'] for f in OPERATIONS['grant@role']['fields']}
    assert role_fields == {'member', 'member_kind', 'default_role', 'admin_option', 'grantor'}
    assert 'admin_option_only' in {f['field_id'] for f in OPERATIONS['revoke@role']['fields']}


def test_role_membership_grant_with_admin_option_then_revoke(env):
    statements = env.run('role', 'grant',
                         {'member': 'APP_USER', 'member_kind': 'USER', 'admin_option': True},
                         target=env.role('R_ONE'))
    assert statements == ['GRANT "R_ONE" TO USER "APP_USER" WITH ADMIN OPTION']
    assert env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'") == [
        ('APP_USER', 'R_ONE', 'M', 2, None)]
    env.run('role', 'revoke', {'member': 'APP_USER', 'member_kind': 'USER'},
            target=env.role('R_ONE'))
    assert env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'") == []


def test_a_role_can_be_a_member_of_another_role(env):
    statements = env.run('role', 'grant', {'member': 'R_TWO', 'member_kind': 'ROLE'},
                         target=env.role('R_ONE'))
    assert statements == ['GRANT "R_ONE" TO ROLE "R_TWO"']
    assert env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'") == [
        ('R_TWO', 'R_ONE', 'M', 0, None)]


def test_default_role_and_revoking_only_the_delegation(env):
    env.run('role', 'grant',
            {'member': 'APP_USER', 'member_kind': 'USER', 'admin_option': True, 'default_role': True},
            target=env.role('R_ONE'))
    assert env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'")[0][3] == 2
    statements = env.run('role', 'revoke',
                         {'member': 'APP_USER', 'member_kind': 'USER', 'default_role': True,
                          'admin_option_only': True},
                         target=env.role('R_ONE'))
    assert statements == ['REVOKE ADMIN OPTION FOR DEFAULT "R_ONE" FROM USER "APP_USER"']
    # The membership stays; only the delegation was removed.
    remaining = env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'")
    assert [(row[0], row[3]) for row in remaining] == [('APP_USER', 0)]


def test_object_privileges_with_a_column_list_and_grant_option(env):
    statements = env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE',
        'object_name': 'T1', 'privileges': ['SELECT', 'UPDATE'],
        'update_columns': [{'name': 'N'}], 'grant_option': True})
    assert statements == ['GRANT SELECT, UPDATE ("N") ON TABLE "T1" TO USER "APP_USER" WITH GRANT OPTION']
    rows = env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'APP_USER'")
    assert ('APP_USER', 'T1', 'S', 1, None) in rows
    assert ('APP_USER', 'T1', 'U', 1, 'N') in rows
    # Firebird has no per-column SELECT, so UPDATE is the only column-level privilege here.
    assert not [row for row in rows if row[2] == 'S' and row[4]]


def test_revoking_requires_the_exact_grantee_names_and_changes_nothing_otherwise(env):
    env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE',
        'object_name': 'T1', 'privileges': ['SELECT']})
    values = {'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE',
              'object_name': 'T1', 'privileges': ['SELECT']}
    assert any('Confirm the exact grantee names' in m for m in
               env.refusal('privilege', 'revoke', {**values, 'confirmation': 'someone_else'}))
    assert env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'APP_USER'")
    env.run('privilege', 'revoke', {**values, 'confirmation': 'APP_USER'})
    assert env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'APP_USER'") == []


def test_a_column_list_without_its_privilege_is_refused(env):
    messages = env.refusal('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE',
        'object_name': 'T1', 'privileges': ['SELECT'], 'update_columns': [{'name': 'N'}]})
    assert any('requires its UPDATE or REFERENCES' in m for m in messages)
    assert env.observe("TRIM(RDB$USER) = 'APP_USER'") == []


def test_injected_identifiers_are_quoted_not_executed(env):
    hostile = 'X"; DROP TABLE T1; --'
    statements = env.run('role', 'grant', {'member': hostile, 'member_kind': 'USER'},
                         target=env.role('R_ONE'))
    assert statements == ['GRANT "R_ONE" TO USER "X""; DROP TABLE T1; --"']
    # The table is intact and the hostile text was stored as one principal name.
    assert env.observe("RDB$RELATION_NAME = 'R_ONE' AND RDB$PRIVILEGE = 'M'")[0][0] == hostile


def test_column_privileges_in_security_json_match_what_the_provider_accepts():
    document = json.loads((DESCRIPTORS / 'firebird' / 'security.json').read_text(encoding='utf-8'))
    declared = document['grants']['column_privileges']['table']
    assert declared == ['UPDATE', 'REFERENCES']
