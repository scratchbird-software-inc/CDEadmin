"""TiDB family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Owner direction 2026-10-29: TiDB reaches full parity with MySQL/MariaDB.
Set ``CDEADMIN_ROUNDTRIP_TIDB`` to a JSON object ``{"host", "port", "user"}``
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_TIDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_TIDB is not set',
                allow_module_level=True)
mysql_connector = pytest.importorskip('mysql.connector')

from pgadmin.cdeadmin.providers.tidb.provider import (  # noqa: E402
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
        profile_version=PROFILE.exact_version, provider_version='0.3.0')
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
                f"DROP USER IF EXISTS 'rt_nopw_{UNIQUE}'@'%'",
                "SET GLOBAL tidb_enable_check_constraint = OFF"):
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
    form = resolved_form('tidb', family)
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
    form = resolved_form('tidb', 'table')
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
    })
    run(client, route, 'table', 'create', draft)
    table, baseline = record(client, route, 'table', 'rt_orders', 'table')
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
    edited = {**baseline, 'columns': baseline['columns'] + [
        {'name': 'amount', 'type': 'DOUBLE'}]}
    alter = backend_draft(form, edited, mode='alter', baseline=baseline)
    assert alter['add_columns'] == [{'name': 'amount', 'type': 'DOUBLE'}]
    run(client, route, 'table', 'alter', alter, target=table)
    assert ('amount',) in query(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='{DATABASE}' AND table_name='rt_orders'")


def test_check_constraint_follows_the_server_setting(live):
    # TiDB drops CHECK while tidb_enable_check_constraint is OFF; the form
    # must refuse instead of reporting a constraint that does not exist.
    route, client = live
    form = resolved_form('tidb', 'table')
    draft = backend_draft(form, {
        'name': 'rt_checked', 'parent': DATABASE,
        'columns': [{'name': 'id', 'type': 'INT', 'nullable': False},
                    {'name': 'v', 'type': 'INT'}],
        'primary_key': [{'name': 'pk', 'columns': ['id']}],
        'check_constraints': [{'name': 'ck_rt', 'expression': 'v > 0'}],
    })
    query('SET GLOBAL tidb_enable_check_constraint = OFF')
    request = {'resource_kind': 'table', 'operation_id': 'create',
               'target_resource': None, '_provider_route': route,
               'draft': draft}
    planned = ADMINISTRATION.plan(request)
    with pytest.raises(Exception, match='tidb_enable_check_constraint'):
        ADMINISTRATION.apply(client, planned)
    assert not query(
        "SELECT 1 FROM information_schema.tables "
        f"WHERE table_schema='{DATABASE}' AND table_name='rt_checked'")
    query('SET GLOBAL tidb_enable_check_constraint = ON')
    run(client, route, 'table', 'create', draft)
    _table, baseline = record(client, route, 'table', 'rt_checked', 'table')
    assert [row['name'] for row in baseline['check_constraints']] == [
        'ck_rt']


def test_view_index_and_sequence_forms(live):
    route, client = live
    run(client, route, 'view', 'create', backend_draft(
        resolved_form('tidb', 'view'),
        {'name': 'rt_v', 'parent': DATABASE, 'query': 'SELECT id FROM owner'}))
    _view, view_record = record(client, route, 'view', 'rt_v', 'view')
    assert 'owner' in view_record['query'].lower()
    run(client, route, 'index', 'create', backend_draft(
        resolved_form('tidb', 'index'), {
            'name': 'rt_ix', 'parent': DATABASE, 'table': 'owner',
            'columns': [{'value': 'label'}], 'unique': True}))
    _index, index_record = record(client, route, 'index', 'rt_ix', 'index')
    assert (index_record['table'], index_record['unique']) == ('owner', True)
    sequence_form = resolved_form('tidb', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(sequence_form, {
        'name': 'rt_seq', 'parent': DATABASE, 'start': 10, 'increment': 5,
        'cycle': False}))
    sequence, baseline = record(client, route, 'sequence', 'rt_seq',
                                'sequence')
    assert (int(baseline['start']), int(baseline['increment']),
            baseline['cycle']) == (10, 5, False)
    alter = backend_draft(sequence_form, {**baseline, 'restart': 100},
                          mode='alter', baseline=baseline)
    run(client, route, 'sequence', 'alter', alter, target=sequence)
    assert query(f'SELECT NEXTVAL(`{DATABASE}`.rt_seq)') == [(100,)]


def test_database_form_create_and_alter(live):
    route, client = live
    form = resolved_form('tidb', 'database')
    run(client, route, 'database', 'create', backend_draft(form, {
        'name': f'{DATABASE}_child', 'character_set': 'utf8mb4',
        'collation': 'utf8mb4_general_ci'}))
    database, baseline = record(client, route, 'database',
                                f'{DATABASE}_child', 'database')
    assert (baseline['character_set'], baseline['collation']) == (
        'utf8mb4', 'utf8mb4_general_ci')
    alter = backend_draft(form, {**baseline, 'collation': 'utf8mb4_bin'},
                          mode='alter', baseline=baseline)
    assert alter == {'collation': 'utf8mb4_bin'}, alter
    run(client, route, 'database', 'alter', alter, target=database)
    assert query(
        'SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA '
        f"WHERE SCHEMA_NAME='{DATABASE}_child'") == [('utf8mb4_bin',)]


def test_users_roles_and_grants(live):
    route, client = live
    role_form = resolved_form('tidb', 'role')
    run(client, route, 'user', 'create', backend_draft(role_form, {
        'variant': 'user', 'name': f'rt_user_{UNIQUE}', 'host': 'localhost',
        'authentication_mode': 'PASSWORD', 'password': 'Rt-pw-2026!'}))
    run(client, route, 'role', 'create', backend_draft(role_form, {
        'variant': 'role', 'name': f'rt_role_{UNIQUE}'}))
    user, baseline = record(client, route, 'user',
                            f'rt_user_{UNIQUE}@localhost', 'role')
    assert (baseline['name'], baseline['host'], baseline['active']) == (
        f'rt_user_{UNIQUE}', 'localhost', True)
    alter = backend_draft(role_form, {**baseline, 'variant': 'user',
                                      'active': False},
                          mode='alter', baseline=baseline)
    assert alter == {'active': False}, alter
    run(client, route, 'user', 'alter', alter, target=user)
    _user, after = record(client, route, 'user',
                          f'rt_user_{UNIQUE}@localhost', 'role')
    assert after['active'] is False
    principal = f'rt_user_{UNIQUE}@localhost'
    grant = {'principal': principal, 'object_type': 'SEQUENCE',
             'object_name': f'{DATABASE}.rt_seq', 'privileges': ['SELECT']}
    run(client, route, 'privilege', 'grant', grant)
    assert any(
        row['native'].get('principal') == principal and
        row['native'].get('object_name') == f'{DATABASE}.rt_seq'
        for row in resources(client, route)
        if row['resource_kind'] == 'privilege')


def test_passwordless_user_form(live):
    # Owner direction 2026-10-29: passwordless accounts may be created.
    route, client = live
    draft = backend_draft(resolved_form('tidb', 'role'), {
        'variant': 'user', 'name': f'rt_nopw_{UNIQUE}', 'host': '%',
        'authentication_mode': 'NONE'})
    assert 'password' not in draft
    assert 'IDENTIFIED' not in run(client, route, 'user', 'create', draft)
    mysql_connector.connect(host=SETTINGS['host'], port=int(SETTINGS['port']),
                            user=f'rt_nopw_{UNIQUE}').close()
