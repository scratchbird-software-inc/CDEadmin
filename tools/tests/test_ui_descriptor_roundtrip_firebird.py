"""Firebird family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Needs a reachable Firebird 5 server. Set ``CDEADMIN_ROUNDTRIP_FIREBIRD`` to a
JSON object ``{"host", "port", "user", "password", "database_root"}`` where
``database_root`` is a directory the server process can create files in, and
``CDEADMIN_FIREBIRD_CLIENT_LIBRARY`` to a Firebird 5 ``libfbclient``. The test
creates its own database under ``database_root``. Skipped otherwise.
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_FIREBIRD')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_FIREBIRD is not set', allow_module_level=True)
driver = pytest.importorskip('firebird.driver')

from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, record_draft, resolved_form  # noqa: E402

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope='module')
def live():
    path = str(Path(SETTINGS['database_root']) / f'ui_roundtrip_{UNIQUE}.fdb')
    dsn = f"{SETTINGS['host']}/{SETTINGS['port']}:{path}"
    # The provider selects the client library; create the client before the
    # driver touches the API so both use the configured Firebird 5 library.
    client = _create_client(SimpleNamespace(acquire_secret=lambda *_args: SecretLease(SETTINGS['password'])))
    seed = driver.create_database(dsn, user=SETTINGS['user'], password=SETTINGS['password'])
    seed.execute_immediate('CREATE TABLE OWNER(ID INTEGER NOT NULL PRIMARY KEY, LABEL VARCHAR(40))')
    seed.commit()
    seed.close()
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']), 'database': path, 'user': SETTINGS['user'],
             'credential_reference_id': 'ui-roundtrip', 'principal_reference': 'ui-roundtrip'}
    try:
        yield route, client
    finally:
        for statement in (f'DROP USER "RT_USER_{UNIQUE}"',):
            try:
                connection = driver.connect(dsn, user=SETTINGS['user'], password=SETTINGS['password'])
                connection.execute_immediate(statement)
                connection.commit()
                connection.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        client.close()
        try:
            driver.connect(dsn, user=SETTINGS['user'], password=SETTINGS['password']).drop_database()
        except Exception:  # noqa: BLE001
            Path(path).unlink(missing_ok=True)


def resources(client, route):
    connection = client._connect({'route': dict(route)})
    try:
        return list(_resources(connection, {}))
    finally:
        client._forget_and_close(connection)


def resource(client, route, kind, name):
    return next(row for row in resources(client, route) if row['resource_kind'] == kind and row['display_name'] == name)


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    sql = '\n'.join(statement['source'] for statement in planned['command_preview']['statements'])
    assert ADMINISTRATION.apply(client, planned)['accepted'], sql
    return sql


def record(client, route, kind, name, family):
    row = resource(client, route, kind, name)
    return row, record_draft(resolved_form('firebird', family), {**row['native'], 'name': row['display_name']})


def test_table_form_create_prefill_and_alter(live):
    route, client = live
    form = resolved_form('firebird', 'table')
    draft = backend_draft(form, {
        'name': 'RT_ORDERS', 'table_type': 'PERSISTENT',
        'columns': [
            {'name': 'ID', 'column_mode': 'STORED', 'data_type': 'INTEGER', 'constraints': [{'kind': 'NOT NULL'}]},
            {'name': 'OWNER_ID', 'column_mode': 'STORED', 'data_type': 'INTEGER'},
            {'name': 'NOTE', 'column_mode': 'STORED', 'data_type': 'VARCHAR', 'length': 40,
             'has_default': True, 'default_kind': 'TEXT', 'default_value': 'x'},
            {'name': 'DOUBLED', 'column_mode': 'COMPUTED', 'data_type': 'INTEGER', 'expression': 'ID * 2'},
        ],
        'primary_key': [{'name': 'PK_RT', 'columns': ['ID']}],
        'unique_constraints': [{'name': 'UQ_RT', 'columns': ['NOTE']}],
        'foreign_keys': [{'name': 'FK_RT', 'columns': ['OWNER_ID'], 'references_table': 'OWNER', 'references_columns': ['ID']}],
        'check_constraints': [{'name': 'CK_RT', 'expression': 'CHAR_LENGTH(NOTE) > 0'}],
    })
    assert [row['kind'] for row in draft['constraints']] == ['PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', 'CHECK']
    sql = run(client, route, 'table', 'create', draft)
    assert 'CONSTRAINT "FK_RT" FOREIGN KEY ("OWNER_ID") REFERENCES "OWNER" ("ID")' in sql
    assert '"DOUBLED" INTEGER COMPUTED BY (ID * 2' in sql

    table, baseline = record(client, route, 'table', 'RT_ORDERS', 'table')
    columns = {row['name']: row for row in baseline['columns']}
    assert columns['ID']['column_mode'] == 'STORED' and columns['ID']['data_type'] == 'INTEGER'
    assert columns['ID']['constraints'] == [{'kind': 'NOT NULL'}]
    assert columns['NOTE']['has_default'] is True and columns['NOTE']['default_value'] == "'x'"
    assert columns['NOTE']['data_type'] == 'VARCHAR' and columns['NOTE']['length'] == 40
    assert columns['DOUBLED']['column_mode'] == 'COMPUTED' and columns['DOUBLED']['expression'] == 'ID * 2'
    assert [row['name'] for row in baseline['primary_key']] == ['PK_RT']
    assert baseline['primary_key'][0]['columns'] == ['ID']
    assert baseline['foreign_keys'][0]['references_table'] == 'OWNER'
    assert baseline['check_constraints'][0]['expression'] == 'CHAR_LENGTH(NOTE) > 0'
    assert baseline['table_type'] == 'PERSISTENT'

    edited = {**baseline, 'columns': baseline['columns'] + [{'name': 'AMOUNT', 'column_mode': 'STORED', 'data_type': 'DOUBLE PRECISION'}]}
    alter = backend_draft(form, edited, mode='alter', baseline=baseline)
    assert alter['add_columns'] == [{'name': 'AMOUNT', 'column_mode': 'STORED', 'data_type': 'DOUBLE PRECISION'}]
    assert 'constraints' not in alter
    run(client, route, 'table', 'alter', alter, target=table)
    _table, after = record(client, route, 'table', 'RT_ORDERS', 'table')
    assert 'AMOUNT' in {row['name'] for row in after['columns']}


def test_view_index_and_trigger_forms(live):
    route, client = live
    run(client, route, 'view', 'create', backend_draft(resolved_form('firebird', 'view'),
                                                      {'name': 'RT_V', 'query': 'SELECT ID FROM OWNER'}))
    _view, view_record = record(client, route, 'view', 'RT_V', 'view')
    assert view_record['query'] == 'SELECT ID FROM OWNER'

    index_form = resolved_form('firebird', 'index')
    run(client, route, 'index', 'create', backend_draft(index_form, {
        'name': 'RT_IX', 'table': 'OWNER', 'index_kind': 'columns', 'columns': [{'value': 'LABEL'}],
        'unique': False, 'direction': 'DESCENDING'}))
    run(client, route, 'index', 'create', backend_draft(index_form, {
        'name': 'RT_IXE', 'table': 'OWNER', 'index_kind': 'expression', 'expression': 'UPPER(LABEL)', 'unique': False}))
    _index, index_record = record(client, route, 'index', 'RT_IX', 'index')
    assert index_record['table'] == 'OWNER'
    assert [row['value'] for row in index_record['columns']] == ['LABEL']
    assert index_record['unique'] is False and index_record['direction'] == 'DESCENDING'
    assert index_record['index_kind'] == 'columns' and index_record['active'] is True
    _expr, expression_record = record(client, route, 'index', 'RT_IXE', 'index')
    assert expression_record['index_kind'] == 'expression'
    assert expression_record['expression'] == 'UPPER(LABEL)'

    trigger_form = resolved_form('firebird', 'trigger')
    run(client, route, 'trigger', 'create', backend_draft(trigger_form, {
        'name': 'RT_TRG', 'table': 'OWNER', 'timing': 'BEFORE', 'events': ['INSERT', 'UPDATE'], 'active': True,
        'position': 0, 'body': "BEGIN IF (NEW.LABEL IS NULL) THEN NEW.LABEL = '-'; END"}))
    _trigger, trigger_record = record(client, route, 'trigger', 'RT_TRG', 'trigger')
    assert trigger_record['table'] == 'OWNER' and trigger_record['timing'] == 'BEFORE'
    assert trigger_record['events'] == ['INSERT', 'UPDATE'] and trigger_record['active'] is True
    assert trigger_record['body'].startswith('BEGIN')


def test_sequence_and_domain_forms(live):
    route, client = live
    sequence_form = resolved_form('firebird', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(sequence_form,
                                                          {'name': 'RT_SEQ', 'start': '10', 'increment': 5, 'description': 'rt'}))
    sequence, baseline = record(client, route, 'sequence', 'RT_SEQ', 'sequence')
    assert baseline['start'] == '10' and baseline['increment'] == 5 and baseline['description'] == 'rt'
    alter = backend_draft(sequence_form, {**baseline, 'restart': '100', 'increment': 7}, mode='alter', baseline=baseline)
    assert alter == {'increment': 7, 'restart': '100'}
    assert 'RESTART WITH 100 INCREMENT BY 7' in run(client, route, 'sequence', 'alter', alter, target=sequence)

    type_form = resolved_form('firebird', 'type')
    run(client, route, 'domain', 'create', backend_draft(type_form, {
        'name': 'RT_DOM', 'data_type': 'VARCHAR(10)', 'default': "'a'", 'not_null': True, 'check': "VALUE <> ''"}))
    domain, baseline = record(client, route, 'domain', 'RT_DOM', 'type')
    assert baseline['data_type'].startswith('VARCHAR(10)')
    assert baseline['default'] == "'a'" and baseline['not_null'] is True and baseline['check'] == "VALUE <> ''"
    alter = backend_draft(type_form, {**baseline, 'default': "'b'"}, mode='alter', baseline=baseline)
    assert 'SET DEFAULT \'b\'' in run(client, route, 'domain', 'alter', alter, target=domain)


def test_routine_and_role_forms(live):
    route, client = live
    routine_form = resolved_form('firebird', 'routine')
    run(client, route, 'procedure', 'create', backend_draft(routine_form, {
        'variant': 'procedure', 'name': 'RT_PROC', 'parameters': [{'name': 'A', 'type': 'INTEGER'}],
        'return_parameters': [{'name': 'B', 'type': 'INTEGER'}], 'body': 'BEGIN B = A * 2; SUSPEND; END'}))
    run(client, route, 'function', 'create', backend_draft(routine_form, {
        'variant': 'function', 'name': 'RT_FN', 'parameters': [{'name': 'A', 'type': 'INTEGER'}], 'returns': 'INTEGER',
        'body': 'BEGIN RETURN A + 1; END'}))
    _procedure, procedure_record = record(client, route, 'procedure', 'RT_PROC', 'routine')
    assert [(row['name'], row['type']) for row in procedure_record['parameters']] == [('A', 'INTEGER')]
    assert [(row['name'], row['type']) for row in procedure_record['return_parameters']] == [('B', 'INTEGER')]
    assert procedure_record['body'] == 'BEGIN B = A * 2; SUSPEND; END'
    _function, function_record = record(client, route, 'function', 'RT_FN', 'routine')
    assert function_record['returns'] == 'INTEGER'
    assert [(row['name'], row['type']) for row in function_record['parameters']] == [('A', 'INTEGER')]

    role_form = resolved_form('firebird', 'role')
    run(client, route, 'role', 'create', backend_draft(role_form, {
        'variant': 'role', 'name': 'RT_ROLE', 'description': 'rt role', 'system_privileges': ['USER_MANAGEMENT']}))
    role, role_record = record(client, route, 'role', 'RT_ROLE', 'role')
    assert role_record['system_privileges'] == ['USER_MANAGEMENT'] and role_record['description'] == 'rt role'
    assert 'password' not in backend_draft(role_form, {'variant': 'role', 'name': 'RT_ROLE', 'password': 'never'})
    user_draft = backend_draft(role_form, {'variant': 'user', 'name': f'RT_USER_{UNIQUE}', 'password': 'pw1', 'active': True})
    assert 'host' not in user_draft
    run(client, route, 'user', 'create', user_draft)
    _user, user_record = record(client, route, 'user', f'RT_USER_{UNIQUE}', 'role')
    assert user_record['active'] is True and user_record['plugin']


def test_database_form_creates_a_database_under_the_approved_root(live):
    route, client = live
    form = resolved_form('firebird', 'database')
    name = f'ui_roundtrip_child_{UNIQUE}.fdb'
    draft = backend_draft(form, {'database_path': name, 'page_size': '8192', 'default_charset': 'UTF8', 'sql_dialect': '3',
                                 'forced_writes': True, 'reserve_space': True})
    request = {'resource_kind': 'database', 'operation_id': 'create', 'target_resource': None,
               '_provider_route': {**route, 'database_create_root': SETTINGS['database_root']}, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    result = ADMINISTRATION.apply(client, planned)
    assert result['accepted'], result
    created = Path(SETTINGS['database_root']) / name
    assert created.exists()
    try:
        connection = driver.connect(f"{SETTINGS['host']}/{SETTINGS['port']}:{created}", user=SETTINGS['user'],
                                    password=SETTINGS['password'])
        with connection.cursor() as cursor:
            cursor.execute("SELECT MON$PAGE_SIZE, MON$SQL_DIALECT FROM MON$DATABASE")
            assert cursor.fetchone() == (8192, 3)
        connection.drop_database()
    finally:
        if created.exists():
            created.unlink()
