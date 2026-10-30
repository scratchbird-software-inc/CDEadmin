"""Dolt family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Owner direction 2026-10-29: Dolt reaches full parity with MySQL/MariaDB.
Set ``CDEADMIN_ROUNDTRIP_DOLT`` to a JSON object ``{"host", "port", "user"}``
plus ``"password"`` unless the account is passwordless, for an account that
may create databases. The test creates and drops its own database. Skipped
otherwise.
"""
import json
import os
import sys
import uuid
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_DOLT')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_DOLT is not set',
                allow_module_level=True)
mysql_connector = pytest.importorskip('mysql.connector')

from pgadmin.cdeadmin.providers.dolt.provider import (  # noqa: E402
    ADMINISTRATION, PROFILE, create_provider,
)
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
PASSWORD = SETTINGS.get('password')
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'ui_rt_{UNIQUE}'


def admin(database=None):
    return mysql_connector.connect(
        host=SETTINGS['host'], port=int(SETTINGS['port']),
        user=SETTINGS['user'], password=PASSWORD or '', autocommit=True,
        **({'database': database} if database else {}))


@pytest.fixture(scope='module')
def live():
    seed = admin()
    cursor = seed.cursor()
    cursor.execute(f'CREATE DATABASE `{DATABASE}`')
    cursor.execute(f'CREATE TABLE `{DATABASE}`.owner'
                   '(id INT PRIMARY KEY, label VARCHAR(40))')
    seed.close()
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']),
             'database': DATABASE, 'user': SETTINGS['user']}
    if PASSWORD:
        route.update(credential_reference_id='ui-roundtrip',
                     principal_reference='ui-roundtrip')
        permissions = SimpleNamespace(
            acquire_secret=lambda *_args: SecretLease(PASSWORD.encode()),
            require=lambda *_args: None)
    else:
        route['passwordless'] = True
        permissions = SimpleNamespace(acquire_secret=None,
                                      require=lambda *_args: None)
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=DATABASE,
        pool_namespace=DATABASE, cache_namespace=DATABASE,
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0')
    client = create_provider(context, permissions).client
    try:
        yield route, client
    finally:
        cleanup = admin()
        for statement in (
                f'DROP DATABASE IF EXISTS `{DATABASE}`',
                f'DROP DATABASE IF EXISTS `{DATABASE}_child`',
                f"DROP USER IF EXISTS 'rt_user_{UNIQUE}'@'localhost'",
                f"DROP ROLE IF EXISTS 'rt_role_{UNIQUE}'",
                f"DROP USER IF EXISTS 'rt_nopw_{UNIQUE}'@'%'"):
            cleanup.cursor().execute(statement)
        cleanup.close()


def resources(client, route):
    return client.list_resources({'route': dict(route)})


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    sql = '\n'.join(statement['source'] for statement in
                    planned['command_preview']['statements'])
    assert ADMINISTRATION.apply(client, planned)['accepted'], sql
    return sql


def record(client, route, kind, name, family):
    rows = resources(client, route)
    row = next(item for item in rows if item['resource_kind'] == kind and
               item['display_name'] == name and
               (kind in {'user', 'role', 'database'} or
                DATABASE in item['display_path']))
    form = resolved_form('dolt', family)
    return row, record_draft(form, record_from_resource(form, row, rows))


def query(sql):
    connection = admin(DATABASE)
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        connection.close()


def test_table_form_create_prefill_and_alter(live):
    route, client = live
    form = resolved_form('dolt', 'table')
    draft = backend_draft(form, {
        'name': 'rt_orders', 'parent': DATABASE,
        'columns': [{'name': 'id', 'type': 'INT', 'nullable': False},
                    {'name': 'owner_id', 'type': 'INT'},
                    {'name': 'note', 'type': 'VARCHAR(40)',
                     'default': "'x'"}],
        'primary_key': [{'name': 'pk_rt', 'columns': ['id']}],
        'unique_constraints': [{'name': 'uq_rt', 'columns': ['note']}],
        'foreign_keys': [{'name': 'fk_rt', 'columns': ['owner_id'],
                          'references_table': 'owner',
                          'references_columns': ['id']}],
        'check_constraints': [{'name': 'ck_rt',
                               'expression': 'CHAR_LENGTH(note) > 0'}],
    })
    run(client, route, 'table', 'create', draft)
    table, baseline = record(client, route, 'table', 'rt_orders', 'table')
    # Re-open: columns in definition order with defaults and keys, and every
    # constraint with its columns and references (Dolt reports them all).
    assert [(row['name'], row['type'], row['nullable'], row.get('default'))
            for row in baseline['columns']] == [
        ('id', 'int', False, None), ('owner_id', 'int', True, None),
        ('note', 'varchar(40)', True, "'x'")]
    assert [(row['name'], row['columns'])
            for row in baseline['primary_key']] == [('PRIMARY', ['id'])]
    assert [(row['name'], row['columns'])
            for row in baseline['unique_constraints']] == [
        ('uq_rt', ['note'])]
    assert [(row['name'], row['columns'], row['references_table'],
             row['references_columns'])
            for row in baseline['foreign_keys']] == [
        ('fk_rt', ['owner_id'], 'owner', ['id'])]
    assert [row['name'] for row in baseline['check_constraints']] == [
        'ck_rt']
    assert 'note' in baseline['check_constraints'][0]['expression']
    edited = {**baseline, 'columns': baseline['columns'] + [
        {'name': 'amount', 'type': 'DOUBLE'}]}
    alter = backend_draft(form, edited, mode='alter', baseline=baseline)
    assert alter['add_columns'] == [{'name': 'amount', 'type': 'DOUBLE'}]
    assert 'constraints' not in alter
    run(client, route, 'table', 'alter', alter, target=table)
    assert ('amount',) in query(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='{DATABASE}' AND table_name='rt_orders'")


def test_view_index_trigger_forms(live):
    route, client = live
    run(client, route, 'view', 'create', backend_draft(
        resolved_form('dolt', 'view'),
        {'name': 'rt_v', 'parent': DATABASE, 'query': 'SELECT id FROM owner'}))
    _view, view_record = record(client, route, 'view', 'rt_v', 'view')
    assert view_record['query'].lower().startswith('select')
    run(client, route, 'index', 'create', backend_draft(
        resolved_form('dolt', 'index'), {
            'name': 'rt_ix', 'parent': DATABASE, 'table': 'owner',
            'columns': [{'value': 'label'}], 'unique': True}))
    _index, index_record = record(client, route, 'index', 'rt_ix', 'index')
    assert index_record['table'] == 'owner'
    assert index_record['unique'] is True
    assert [row.get('value', row) if isinstance(row, dict) else row
            for row in index_record['columns']] == ['label']
    trigger_form = resolved_form('dolt', 'trigger')
    trigger = backend_draft(trigger_form, {
        'name': 'rt_trg', 'parent': DATABASE, 'table': 'owner',
        'timing': 'BEFORE', 'events': 'INSERT',
        'body': "SET NEW.label = COALESCE(NEW.label, '-')"})
    # The MySQL-dialect compiler emits neither, so the form offers neither.
    assert 'active' not in trigger and 'position' not in trigger
    assert trigger['events'] == ['INSERT']
    run(client, route, 'trigger', 'create', trigger)
    _trigger, trigger_record = record(client, route, 'trigger', 'rt_trg',
                                      'trigger')
    assert (trigger_record['table'], trigger_record['timing'],
            trigger_record['events']) == ('owner', 'BEFORE', 'INSERT')
    assert trigger_record['body'] == \
        "SET NEW.label = COALESCE(NEW.label, '-')"
    # FOLLOWS ordering (verified Dolt syntax) places the new trigger after.
    run(client, route, 'trigger', 'create', backend_draft(trigger_form, {
        'name': 'rt_trg_after', 'parent': DATABASE, 'table': 'owner',
        'timing': 'BEFORE', 'events': 'INSERT', 'order': 'FOLLOWS',
        'other_trigger': 'rt_trg', 'body': 'SET NEW.label = NEW.label'}))
    assert query(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
        f"WHERE TRIGGER_SCHEMA='{DATABASE}' ORDER BY ACTION_ORDER") == [
        ('rt_trg',), ('rt_trg_after',)]


def test_procedure_and_event_forms(live):
    route, client = live
    routine_form = resolved_form('dolt', 'routine')
    run(client, route, 'procedure', 'create', backend_draft(routine_form, {
        'variant': 'procedure', 'name': 'rt_proc', 'parent': DATABASE,
        'parameters': [{'name': 'a', 'type': 'INT'}],
        'body': 'BEGIN SELECT a * 2; END'}))
    _procedure, procedure_record = record(client, route, 'procedure',
                                          'rt_proc', 'routine')
    assert procedure_record['body'] == 'BEGIN SELECT a * 2; END'
    assert [(row['name'], row['type'].lower())
            for row in procedure_record['parameters']] == [('a', 'int')]
    run(client, route, 'event', 'create', backend_draft(routine_form, {
        'variant': 'scheduled', 'name': 'rt_ev', 'parent': DATABASE,
        'schedule': 'EVERY 1 DAY', 'preserve': True, 'enabled': False,
        'body': 'DELETE FROM owner WHERE id < 0'}))
    event, event_record = record(client, route, 'event', 'rt_ev', 'routine')
    # Recurring events read back with the STARTS the server recorded.
    assert event_record['schedule'].startswith('EVERY 1 DAY')
    assert (event_record['preserve'], event_record['enabled']) == (
        True, False)
    assert event_record['body'] == 'DELETE FROM owner WHERE id < 0'
    alter = backend_draft(routine_form, {
        **event_record, 'variant': 'scheduled', 'enabled': True},
        mode='alter', baseline=event_record)
    assert alter == {'enabled': True}, alter
    run(client, route, 'event', 'alter', alter, target=event)
    assert query(
        "SELECT status FROM information_schema.events "
        f"WHERE event_schema='{DATABASE}' AND event_name='rt_ev'"
    ) == [('ENABLED',)]


def test_role_and_user_forms(live):
    route, client = live
    role_form = resolved_form('dolt', 'role')
    run(client, route, 'user', 'create', backend_draft(role_form, {
        'variant': 'user', 'name': f'rt_user_{UNIQUE}', 'host': 'localhost',
        'password': 'Rt-pw-2026!'}))
    run(client, route, 'role', 'create', backend_draft(role_form, {
        'variant': 'role', 'name': f'rt_role_{UNIQUE}',
        'members': [f'rt_user_{UNIQUE}@localhost']}))
    _user, user_record = record(client, route, 'user',
                                f'rt_user_{UNIQUE}@localhost', 'role')
    assert (user_record['name'], user_record['host']) == (
        f'rt_user_{UNIQUE}', 'localhost')
    assert 'password' not in user_record
    assert query(
        f"SELECT FROM_USER, TO_USER FROM mysql.role_edges "
        f"WHERE FROM_USER='rt_role_{UNIQUE}'") == [
        (f'rt_role_{UNIQUE}', f'rt_user_{UNIQUE}')]


def test_passwordless_user_form(live):
    # Owner direction 2026-10-29: passwordless accounts may be created.
    route, client = live
    role_form = resolved_form('dolt', 'role')
    draft = backend_draft(role_form, {
        'variant': 'user', 'name': f'rt_nopw_{UNIQUE}', 'host': '%',
        'authentication_mode': 'NONE'})
    assert 'password' not in draft
    sql = run(client, route, 'user', 'create', draft)
    assert 'IDENTIFIED' not in sql
    login = mysql_connector.connect(
        host=SETTINGS['host'], port=int(SETTINGS['port']),
        user=f'rt_nopw_{UNIQUE}')
    login.close()


def test_database_form_create_and_alter(live):
    route, client = live
    form = resolved_form('dolt', 'database')
    run(client, route, 'database', 'create', backend_draft(form, {
        'name': f'{DATABASE}_child', 'character_set': 'utf8mb4',
        'collation': 'utf8mb4_0900_ai_ci'}))
    database, baseline = record(client, route, 'database',
                                f'{DATABASE}_child', 'database')
    assert (baseline['character_set'], baseline['collation']) == (
        'utf8mb4', 'utf8mb4_0900_ai_ci')
    alter = backend_draft(form, {**baseline, 'collation': 'utf8mb4_bin'},
                          mode='alter', baseline=baseline)
    assert alter == {'collation': 'utf8mb4_bin'}, alter
    run(client, route, 'database', 'alter', alter, target=database)
    assert query(
        'SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA '
        f"WHERE SCHEMA_NAME='{DATABASE}_child'") == [('utf8mb4_bin',)]


def test_user_password_change(live):
    route, client = live
    role_form = resolved_form('dolt', 'role')
    user, baseline = record(client, route, 'user',
                            f'rt_user_{UNIQUE}@localhost', 'role')
    alter = backend_draft(role_form, {
        **baseline, 'variant': 'user', 'password': 'Rt-pw-changed-2026!'},
        mode='alter', baseline=baseline)
    assert alter == {'password': 'Rt-pw-changed-2026!'}, alter
    hashed = (
        "SELECT authentication_string FROM mysql.user "
        f"WHERE User='rt_user_{UNIQUE}' AND Host='localhost'")
    before = query(hashed)
    run(client, route, 'user', 'alter', alter, target=user)
    after = query(hashed)
    assert before and after and before != after


def test_grant_and_revoke_appear_in_the_inventory(live):
    route, client = live
    principal = f'rt_user_{UNIQUE}@localhost'
    grant = {'principal': principal, 'object_type': 'DATABASE',
             'object_name': DATABASE, 'privileges': ['SELECT']}

    def grants():
        return sorted(
            (row['native']['object_type'], row['native']['privilege'])
            for row in resources(client, route)
            if row['resource_kind'] == 'privilege' and
            row['native'].get('principal') == principal)

    run(client, route, 'privilege', 'grant', grant)
    assert ('DATABASE', 'SELECT') in grants()
    run(client, route, 'privilege', 'revoke',
        {**grant, 'confirmation': 'REVOKE'})
    assert ('DATABASE', 'SELECT') not in grants()
