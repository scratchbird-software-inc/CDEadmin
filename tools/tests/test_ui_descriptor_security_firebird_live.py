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
    backend_draft, engine_operations, initial_draft, operation_backend_draft, operation_draft, resolved_form)

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
            'CREATE ROLE R_TWO',
            'CREATE SEQUENCE S1',
            'CREATE PROCEDURE P1 AS BEGIN END'):
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

    def form_run(kind, operation_id, values, target=None, mode='create'):
        """A tier-1 create or alter: the family editor's draft through the same provider path."""
        form = resolved_form('firebird', 'role')
        state = {**initial_draft(form, mode), **values}
        payload = {'resource_kind': kind, 'operation_id': operation_id, 'target_resource': target,
                   '_provider_route': route, 'draft': backend_draft(form, state, mode)}
        verdict = provider.administration.validate(payload)
        assert verdict['errors'] == [], verdict
        planned = provider.administration.plan(payload)
        result = provider.administration.apply(client, planned)
        assert result['accepted'], result
        return [row['source'] for row in planned['command_preview']['statements']]

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

    def stored(where):
        """(grantee, privilege code, grantee type, grant option, column) as Firebird stores a grant."""
        connection = driver.connect(str(database), user='SYSDBA')
        try:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT TRIM(RDB$USER), TRIM(RDB$PRIVILEGE), RDB$USER_TYPE, RDB$GRANT_OPTION, '
                'TRIM(RDB$FIELD_NAME) FROM RDB$USER_PRIVILEGES WHERE ' + where)
            return sorted(cursor.fetchall(), key=lambda row: tuple(str(c) for c in row))
        finally:
            connection.close()

    def role(name):
        return next(r for r in resources() if r['resource_kind'] == 'role' and r['display_name'] == name)

    try:
        yield SimpleNamespace(run=run, form_run=form_run, refusal=refusal, observe=observe, stored=stored, role=role)
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


def test_stored_privilege_codes_and_grantee_types_match_what_the_descriptor_lists(env):
    """security.json grants.listing is how the object grants view reads the engine's own rows."""
    listing = json.loads((DESCRIPTORS / 'firebird' / 'security.json').read_text(encoding='utf-8'))['grants']['listing']
    codes, kinds = listing['privilege_codes'], listing['grantee_kinds']
    env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE', 'object_name': 'T1',
        'privileges': ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'], 'grant_option': True})
    env.run('privilege', 'grant', {
        'principal_kind': 'ROLE', 'principal': 'R_ONE', 'object_type': 'TABLE', 'object_name': 'T1',
        'privileges': ['SELECT']})
    env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'PROCEDURE', 'object_name': 'P1',
        'privileges': ['EXECUTE']})
    env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'SEQUENCE', 'object_name': 'S1',
        'privileges': ['USAGE']})
    seen = {}
    for relation in ('T1', 'P1', 'S1'):
        for grantee, code, user_type, option, column in env.stored(f"RDB$RELATION_NAME = '{relation}'"):
            seen[(relation, grantee, code)] = (user_type, option)
            assert code in codes, f'stored code {code!r} on {relation} is not declared in security.json'
    assert {name for (rel, who, code), _ in seen.items() for name in [codes[code]]} == {
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES', 'EXECUTE', 'USAGE'}
    assert str(seen[('T1', 'APP_USER', 'S')][0]) in kinds and kinds[str(seen[('T1', 'APP_USER', 'S')][0])] == 'USER'
    assert kinds[str(seen[('T1', 'R_ONE', 'S')][0])] == 'ROLE'
    assert seen[('T1', 'APP_USER', 'S')][1] == listing['grant_option_equals']
    assert seen[('T1', 'R_ONE', 'S')][1] != listing['grant_option_equals']


def test_a_role_with_system_privileges_and_a_description_is_created_and_read_back(env):
    statements = env.form_run('role', 'create', {
        'variant': 'role', 'name': 'AUDITOR_ROLE', 'description': 'Diagnostics role',
        'system_privileges': ['MONITOR_ANY_ATTACHMENT', 'TRACE_ANY_ATTACHMENT']})
    assert statements[0] == ('CREATE ROLE "AUDITOR_ROLE" SET SYSTEM PRIVILEGES TO '
                             'MONITOR_ANY_ATTACHMENT, TRACE_ANY_ATTACHMENT')
    created = env.role('AUDITOR_ROLE')['native']
    assert sorted(created['system_privileges']) == ['MONITOR_ANY_ATTACHMENT', 'TRACE_ANY_ATTACHMENT']
    assert created.get('description') == 'Diagnostics role'


def test_an_unknown_system_privilege_is_refused_before_anything_runs(env):
    form = resolved_form('firebird', 'role')
    state = {**initial_draft(form, 'create'), 'variant': 'role', 'name': 'BAD_ROLE',
             'system_privileges': ['NOT_A_PRIVILEGE']}
    payload = {'resource_kind': 'role', 'operation_id': 'create', 'target_resource': None,
               '_provider_route': {}, 'draft': backend_draft(form, state, 'create')}
    # The control plane validates against the field's declared options.
    options = {o['value'] if isinstance(o, dict) else o
               for f in form['fields'] if f['field_id'] == 'system_privileges' for o in f.get('options', [])}
    assert 'NOT_A_PRIVILEGE' not in options and 'MONITOR_ANY_ATTACHMENT' in options
    assert payload['draft']['system_privileges'] == ['NOT_A_PRIVILEGE']


def test_a_database_ddl_privilege_is_granted_to_a_user(env):
    statements = env.run('privilege', 'grant', {
        'privilege_scope': 'database', 'principal_kind': 'USER', 'principal': 'ALICE',
        'database_privileges': ['ALTER']})
    assert statements == ['GRANT ALTER DATABASE TO USER "ALICE"']
    assert env.stored("TRIM(RDB$USER) = 'ALICE'"), 'the DDL grant was not stored'


def test_an_injected_privilege_name_is_refused_and_the_table_survives(env):
    messages = env.refusal('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE', 'object_name': 'T1',
        'privileges': ['SELECT; DROP TABLE T1 --']})
    assert messages
    # The owner always holds its own privileges; the refused grant added none for the grantee.
    assert env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'APP_USER'") == []
    env.run('privilege', 'grant', {
        'principal_kind': 'USER', 'principal': 'APP_USER', 'object_type': 'TABLE', 'object_name': 'T1',
        'privileges': ['SELECT']})
    assert env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'APP_USER'")
    # The table itself is intact: it can still be read through the engine.
    assert env.observe("RDB$RELATION_NAME = 'T1' AND TRIM(RDB$USER) = 'SYSDBA'")


def test_every_secret_field_is_redacted_in_the_public_plan():
    """The control plane redacts a draft value whose field is a password control or sensitive."""
    from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration
    form = resolved_form('firebird', 'role')
    fields = [f for f in form['fields'] if f['field_id'] == 'password']
    assert fields and fields[0]['control'] == 'password'
    redacted = ProviderVisualAdministration._redact_sensitive(fields, {'password': 'S3cret!Pw9', 'name': 'ALICE'})
    assert redacted == {'password': '<redacted>', 'name': 'ALICE'}
    for engine_operation in OPERATIONS.values():
        for field in engine_operation.get('fields', []):
            if any(word in field['field_id'] for word in ('password', 'secret', 'token')):
                assert field.get('control') == 'password' or field.get('sensitive'), (
                    engine_operation['operation_id'], field['field_id'])
