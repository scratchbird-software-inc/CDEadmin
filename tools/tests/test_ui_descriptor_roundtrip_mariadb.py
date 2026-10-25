"""MariaDB family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Needs a reachable MariaDB server and the patched connector the provider
requires (``tools/cdeadmin_build_mariadb_driver.py``). Set
``CDEADMIN_ROUNDTRIP_MARIADB`` to a JSON object ``{"host", "port", "user",
"password"}`` for an account that may create databases and accounts. The test
creates and drops its own database. Skipped otherwise.
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_MARIADB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_MARIADB is not set', allow_module_level=True)
mariadb = pytest.importorskip('mariadb')

from pgadmin.cdeadmin.providers.mysql_family.provider import (  # noqa: E402
    MARIADB_ADMINISTRATION as ADMINISTRATION, MARIADB_PROFILE, _create_client, _resources,
)
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, record_draft, record_from_resource, resolved_form  # noqa: E402

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'ui_rt_{UNIQUE}'


def admin():
    return mariadb.connect(host=SETTINGS['host'], port=int(SETTINGS['port']), user=SETTINGS['user'],
                           password=SETTINGS['password'], autocommit=True)


@pytest.fixture(scope='module')
def live():
    seed = admin()
    seed.cursor().execute(f'CREATE DATABASE `{DATABASE}`')
    seed.cursor().execute(f'CREATE TABLE `{DATABASE}`.owner(id INT PRIMARY KEY, label VARCHAR(40))')
    seed.close()
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']), 'database': DATABASE, 'user': SETTINGS['user'],
             'credential_reference_id': 'ui-roundtrip', 'principal_reference': 'ui-roundtrip'}
    client = _create_client(MARIADB_PROFILE, SimpleNamespace(acquire_secret=lambda *_args: SecretLease(SETTINGS['password'])),
                            SimpleNamespace(pool_namespace=f'ui-roundtrip-{UNIQUE}'))
    try:
        yield route, client
    finally:
        client.close()
        cleanup = admin()
        for statement in (f'DROP DATABASE IF EXISTS `{DATABASE}`', f'DROP DATABASE IF EXISTS `{DATABASE}_child`',
                          f"DROP USER IF EXISTS 'rt_user_{UNIQUE}'@'localhost'", f'DROP ROLE IF EXISTS rt_role_{UNIQUE}'):
            cleanup.cursor().execute(statement)
        cleanup.close()


def resources(client, route):
    connection = client._connect({'route': dict(route)})
    try:
        return list(_resources(connection, {'route': route}, MARIADB_PROFILE))
    finally:
        client._forget_and_close(connection)


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    sql = '\n'.join(statement['source'] for statement in planned['command_preview']['statements'])
    assert ADMINISTRATION.apply(client, planned)['accepted'], sql
    return sql


def record(client, route, kind, name, family):
    rows = resources(client, route)
    row = next(item for item in rows if item['resource_kind'] == kind and item['display_name'] == name)
    form = resolved_form('mariadb', family)
    return row, record_draft(form, record_from_resource(form, row, rows))


def query(sql):
    connection = admin()
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        connection.close()


def test_table_form_create_prefill_and_alter(live):
    route, client = live
    form = resolved_form('mariadb', 'table')
    draft = backend_draft(form, {
        'name': 'rt_orders', 'parent': DATABASE,
        'columns': [{'name': 'id', 'type': 'INT', 'nullable': False}, {'name': 'owner_id', 'type': 'INT'},
                    {'name': 'note', 'type': 'VARCHAR(40)', 'default': "'x'"}],
        'primary_key': [{'name': 'pk_rt', 'columns': ['id']}], 'unique_constraints': [{'name': 'uq_rt', 'columns': ['note']}],
        'foreign_keys': [{'name': 'fk_rt', 'columns': ['owner_id'], 'references_table': 'owner', 'references_columns': ['id']}],
        'check_constraints': [{'name': 'ck_rt', 'expression': 'CHAR_LENGTH(note) > 0'}],
    })
    sql = run(client, route, 'table', 'create', draft)
    assert 'CONSTRAINT `fk_rt` FOREIGN KEY (`owner_id`) REFERENCES `owner` (`id`)' in sql
    table, baseline = record(client, route, 'table', 'rt_orders', 'table')
    # Columns and constraints are separate resources in this inventory; record_children folds them in.
    assert [(row['name'], row['type'], row['nullable']) for row in baseline['columns']] == [
        ('id', 'int(11)', False), ('owner_id', 'int(11)', True), ('note', 'varchar(40)', True)]
    assert baseline['columns'][2]['default'] == "'x'"
    assert [row['name'] for row in baseline['primary_key']] == ['PRIMARY']
    assert [row['name'] for row in baseline['unique_constraints']] == ['uq_rt']
    assert [row['name'] for row in baseline['foreign_keys']] == ['fk_rt']
    assert [row['name'] for row in baseline['check_constraints']] == ['ck_rt']
    edited = {**baseline, 'columns': baseline['columns'] + [{'name': 'amount', 'type': 'DOUBLE'}]}
    alter = backend_draft(form, edited, mode='alter', baseline=baseline)
    assert alter['add_columns'] == [{'name': 'amount', 'type': 'DOUBLE'}] and 'constraints' not in alter
    run(client, route, 'table', 'alter', alter, target=table)
    assert ('amount',) in query(f"SELECT column_name FROM information_schema.columns WHERE table_schema='{DATABASE}' AND table_name='rt_orders'")


def test_view_index_trigger_forms(live):
    route, client = live
    run(client, route, 'view', 'create', backend_draft(resolved_form('mariadb', 'view'),
                                                      {'name': 'rt_v', 'parent': DATABASE, 'query': 'SELECT id FROM owner'}))
    _view, view_record = record(client, route, 'view', 'rt_v', 'view')
    assert view_record['query'].lower().startswith('select')
    run(client, route, 'index', 'create', backend_draft(resolved_form('mariadb', 'index'), {
        'name': 'rt_ix', 'parent': DATABASE, 'table': 'owner', 'columns': [{'value': 'label'}], 'unique': True}))
    _index, index_record = record(client, route, 'index', 'rt_ix', 'index')
    assert index_record['table'] == 'owner' and index_record['unique'] is True
    run(client, route, 'trigger', 'create', backend_draft(resolved_form('mariadb', 'trigger'), {
        'name': 'rt_trg', 'parent': DATABASE, 'table': 'owner', 'timing': 'BEFORE', 'events': ['INSERT'], 'active': True,
        'position': 0, 'body': "SET NEW.label = COALESCE(NEW.label, '-')"}))
    _trigger, trigger_record = record(client, route, 'trigger', 'rt_trg', 'trigger')
    assert trigger_record['table'] == 'owner' and trigger_record['timing'] == 'BEFORE' and trigger_record['events'] == ['INSERT']


def test_sequence_and_routine_forms(live):
    route, client = live
    sequence_form = resolved_form('mariadb', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(sequence_form, {'name': 'rt_seq', 'parent': DATABASE, 'start': 10,
                                                                           'increment': 5, 'cycle': False}))
    sequence, baseline = record(client, route, 'sequence', 'rt_seq', 'sequence')
    assert (baseline['start'], baseline['increment'], baseline['cycle']) == ('10', '5', False)
    alter = backend_draft(sequence_form, {**baseline, 'restart': 100, 'increment': 7}, mode='alter', baseline=baseline)
    assert 'RESTART WITH 100 INCREMENT BY 7' in run(client, route, 'sequence', 'alter', alter, target=sequence)
    assert query(f'SELECT NEXTVAL(`{DATABASE}`.rt_seq)') == [(100,)]

    routine_form = resolved_form('mariadb', 'routine')
    run(client, route, 'procedure', 'create', backend_draft(routine_form, {
        'variant': 'procedure', 'name': 'rt_proc', 'parent': DATABASE, 'parameters': [{'name': 'a', 'type': 'INT'}],
        'body': 'BEGIN SELECT a * 2; END'}))
    run(client, route, 'function', 'create', backend_draft(routine_form, {
        'variant': 'function', 'name': 'rt_fn', 'parent': DATABASE, 'parameters': [{'name': 'a', 'type': 'INT'}], 'returns': 'INT',
        'body': 'RETURN a + 1'}))
    _function, function_record = record(client, route, 'function', 'rt_fn', 'routine')
    assert function_record['returns'] == 'int'
    assert query(f'SELECT `{DATABASE}`.rt_fn(41)') == [(42,)]


def test_role_user_and_database_forms(live):
    route, client = live
    role_form = resolved_form('mariadb', 'role')
    run(client, route, 'role', 'create', backend_draft(role_form, {'variant': 'role', 'name': f'rt_role_{UNIQUE}'}))
    user_draft = backend_draft(role_form, {'variant': 'user', 'name': f'rt_user_{UNIQUE}', 'host': 'localhost',
                                           'authentication_mode': 'PASSWORD', 'password': 'pw1'})
    run(client, route, 'user', 'create', user_draft)
    _role, role_record = record(client, route, 'role', f'rt_role_{UNIQUE}', 'role')
    assert role_record['name'] == f'rt_role_{UNIQUE}'
    user, baseline = record(client, route, 'user', f'rt_user_{UNIQUE}@localhost', 'role')
    assert baseline['name'] == f'rt_user_{UNIQUE}' and baseline['host'] == 'localhost'
    assert baseline['account_lock'] == 'UNLOCK' and baseline['plugin']
    alter = backend_draft(role_form, {**baseline, 'variant': 'user', 'account_lock': 'LOCK'}, mode='alter', baseline=baseline)
    assert alter.get('account_lock') == 'LOCK'
    run(client, route, 'user', 'alter', alter, target=user)
    _user, after = record(client, route, 'user', f'rt_user_{UNIQUE}@localhost', 'role')
    assert after['account_lock'] == 'LOCK'

    database_form = resolved_form('mariadb', 'database')
    run(client, route, 'database', 'create', backend_draft(database_form, {
        'name': f'{DATABASE}_child', 'character_set': 'utf8mb4', 'collation': 'utf8mb4_general_ci', 'comment': 'rt'}))
    assert query(f"SELECT default_character_set_name, schema_comment FROM information_schema.schemata WHERE schema_name='{DATABASE}_child'") == [('utf8mb4', 'rt')]
    database, baseline = record(client, route, 'database', DATABASE, 'database')
    assert baseline['character_set'] == 'utf8mb4'
    alter = backend_draft(database_form, {**baseline, 'comment': 'edited'}, mode='alter', baseline=baseline)
    assert alter == {'comment': 'edited'}
    run(client, route, 'database', 'alter', alter, target=database)
    assert query(f"SELECT schema_comment FROM information_schema.schemata WHERE schema_name='{DATABASE}'") == [('edited',)]
