"""immudb family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Owner direction 2026-10-29: immudb reaches full parity with the beta
engines including its native features; 2026-10-31: offer only what can be
read back, by any engine method. Set ``CDEADMIN_ROUNDTRIP_IMMUDB`` to a
JSON object ``{"host", "port", "web_port", "user", "password"}`` (and
``"metrics_port"``, default 9497) for the
demo server (`dev.sh start immudb`). The test creates its own databases
and removes them (native unload and delete). immudb keeps every user, so
each run leaves one deactivated rt_user_* user. Skipped otherwise.
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_IMMUDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_IMMUDB is not set',
                allow_module_level=True)

from pgadmin.cdeadmin.providers.immudb.provider import (  # noqa: E402
    PROFILE, create_provider,
)
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, engine_operations, operation_backend_draft,
    operation_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'rt_{UNIQUE}'


class _Lease:
    def __init__(self, value):
        self.value = bytearray(value.encode('utf-8'))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.value[:] = b'\x00' * len(self.value)

    def use(self, callback):
        return callback(memoryview(self.value))


def _client():
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=f'rt{UNIQUE}',
        pool_namespace=f'rt{UNIQUE}', cache_namespace=f'rt{UNIQUE}',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0')
    return create_provider(context, SimpleNamespace(
        acquire_secret=lambda *_args: _Lease(SETTINGS['password']),
        require=lambda *_args: None,
        allows=lambda *_args: True)).client


def native(client, route, path, body, database=None):
    return client.rest_admin(route, 'POST', path, body,
                             database=database)['document']


def sql(client, route, statement):
    return native(client, route, '/db/sqlexec', {
        'sql': statement, 'params': [], 'noWait': False}, DATABASE)


@pytest.fixture(scope='module')
def live():
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']),
             'web_port': int(SETTINGS['web_port']),
             'metrics_port': int(SETTINGS.get('metrics_port', 9497)),
             'user': SETTINGS['user'], 'database': DATABASE,
             'sslmode': 'disable', 'credential_reference_id': 'rt',
             'principal_reference': 'rt'}
    client = _client()
    native(client, route, '/db/create/v2', {'name': DATABASE,
                                            'settings': {}})
    try:
        yield route, client
    finally:
        for path in ('/db/unload', '/db/delete'):
            native(client, route, path, {'database': DATABASE})


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    assert client.validate_admin_operation(request)['errors'] == []
    planned = client.plan_admin_operation(request)
    handle = {'plan': request, 'provider_payload': planned['provider_payload']}
    result = client.apply_admin_operation(handle)
    assert result['accepted'], result
    assert client.validate_admin_post_state(handle)['confirmed'] is True
    return planned


def operate(client, route, kind, operation, values, target=None,
            confirmation=None):
    """Run an operation from its descriptor, as the OperationDialog does."""
    declared = engine_operations('immudb')[f'{operation}@{kind}']
    return run(client, route, kind, operation, operation_backend_draft(
        declared, operation_draft(declared, values, confirmation)), target)


def refused(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    return ' '.join(error['message'] for error in
                    client.validate_admin_operation(request)['errors'])


def find(client, route, kind, name):
    rows = client.list_resources({'route': dict(route)})
    found = [row for row in rows
             if row['resource_kind'] == kind and row['display_name'] == name]
    assert len(found) == 1, f'{kind} {name}: {len(found)} records'
    return found[0], rows


def record(client, route, kind, name, family):
    row, rows = find(client, route, kind, name)
    form = resolved_form('immudb', family)
    return row, record_draft(form, record_from_resource(form, row, rows))


def test_table_create_reopen_alter_drop(live):
    route, client = live
    form = resolved_form('immudb', 'table')
    planned = run(client, route, 'table', 'create', backend_draft(form, {
        'name': 'rt_orders',
        'columns': [
            {'name': 'id', 'type': 'INTEGER', 'nullable': False,
             'auto_increment': True},
            {'name': 'code', 'type': 'VARCHAR', 'max_length': 16,
             'nullable': False, 'default': "'none'"},
            {'name': 'qty', 'type': 'INTEGER', 'default': '1'},
            {'name': 'price', 'type': 'FLOAT'},
            {'name': 'payload', 'type': 'BLOB', 'max_length': 32},
            {'name': 'made', 'type': 'TIMESTAMP', 'default': 'NOW()'}],
        'primary_key': ['id'],
        'check_constraints': [
            {'name': 'qty_positive', 'expression': 'qty > 0'},
            {'expression': 'price >= 0'}]}))
    # Shown as sent: one native batch.
    assert planned['command_preview']['statements'][0][
        'source'].startswith('CREATE TABLE "rt_orders"')
    target, baseline = record(client, route, 'table', 'rt_orders', 'table')
    assert [(row['name'], row['type'], row['max_length'], row['nullable'],
             row['default'], row['auto_increment'])
            for row in baseline['columns']] == [
        ('id', 'INTEGER', None, False, None, True),
        ('code', 'VARCHAR', 16, False, "'none'", False),
        ('qty', 'INTEGER', None, True, '1', False),
        ('price', 'FLOAT', None, True, None, False),
        ('payload', 'BLOB', 32, True, None, False),
        ('made', 'TIMESTAMP', None, True, 'now()', False)]
    assert baseline['primary_key'] == ['id']
    assert [(row['name'], row['expression'])
            for row in baseline['check_constraints']] == [
        ('qty_positive', 'qty > 0'), ('rt_orders_check1', 'price >= 0')]
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    # The defaults and checks the record shows are the ones enforced.
    sql(client, route, "INSERT INTO rt_orders(qty, price) VALUES (2, 1.0)")
    with pytest.raises(Exception, match='check constraint violation'):
        sql(client, route, 'INSERT INTO rt_orders(qty) VALUES (0)')
    # A column a check reads cannot be renamed while the check stays.
    renamed = [{**row, 'name': 'quantity'} if row['name'] == 'qty' else row
               for row in baseline['columns']]
    assert 'check qty_positive uses qty' in refused(
        client, route, 'table', 'alter', backend_draft(form, {
            **baseline, 'columns': renamed}, mode='alter',
            baseline=baseline), target)
    columns = [row for row in renamed if row['name'] != 'payload'] + [
        {'name': 'note', 'type': 'VARCHAR', 'default': "'n'"}]
    alter = backend_draft(form, {
        **baseline, 'name': 'rt_orders2', 'columns': columns,
        'check_constraints': [
            row for row in baseline['check_constraints']
            if row['name'] != 'qty_positive']},
        mode='alter', baseline=baseline)
    run(client, route, 'table', 'alter', alter, target)
    target, after = record(client, route, 'table', 'rt_orders2', 'table')
    assert [(row['name'], row['default']) for row in after['columns']] == [
        ('id', None), ('code', "'none'"), ('quantity', '1'),
        ('price', None), ('made', 'now()'), ('note', "'n'")]
    assert [row['name'] for row in after['check_constraints']] == [
        'rt_orders_check1']
    sql(client, route,
        'INSERT INTO rt_orders2(quantity, price) VALUES (0, 1.0)')
    # Refused before sending: what 1.11.0 would accept and not keep.
    changed = [{**row, 'nullable': False} if row['name'] == 'price' else row
               for row in after['columns']]
    assert 'does not keep it' in refused(
        client, route, 'table', 'alter', backend_draft(form, {
            **after, 'columns': changed}, mode='alter', baseline=after),
        target)
    assert 'no ADD CONSTRAINT' in refused(
        client, route, 'table', 'alter', {'check_constraints': [
            *after['check_constraints'],
            {'name': 'more', 'expression': 'id > 0'}]}, target)
    run(client, route, 'table', 'drop', {'confirmation': 'rt_orders2'},
        target)
    assert not [row for row in client.list_resources({'route': dict(route)})
                if row['resource_kind'] == 'table']


def test_index_create_reopen_drop(live):
    route, client = live
    sql(client, route, 'CREATE TABLE "rt_ix" ("id" INTEGER, "a" VARCHAR[32], '
        '"b" INTEGER, PRIMARY KEY ("id"))')
    form = resolved_form('immudb', 'index')
    run(client, route, 'index', 'create', backend_draft(form, {
        'table': 'rt_ix', 'columns': [{'value': 'b'}, {'value': 'a'}],
        'unique': True}))
    indexes = [row for row in client.list_resources({'route': dict(route)})
               if row['resource_kind'] == 'index' and
               row['native'].get('table') == 'rt_ix' and
               not row['native'].get('columns') == ['id']]
    assert len(indexes) == 1
    form_record = record_draft(form, record_from_resource(
        form, indexes[0], []))
    assert (form_record['table'],
            [row['value'] for row in form_record['columns']],
            form_record['unique']) == ('rt_ix', ['b', 'a'], True)
    assert backend_draft(form, form_record, mode='alter',
                         baseline=form_record) == {}
    run(client, route, 'index', 'drop',
        {'confirmation': indexes[0]['display_name']}, indexes[0])
    sql(client, route, 'DROP TABLE "rt_ix"')


def test_user_create_reopen_operations_drop(live):
    route, client = live
    name = f'rt_user_{UNIQUE}'
    form = resolved_form('immudb', 'role')
    run(client, route, 'user', 'create', backend_draft(form, {
        'variant': 'user', 'name': name, 'password': 'Rt-pass-2026!',
        'database': DATABASE, 'permission': 'readwrite'}))
    target, baseline = record(client, route, 'user', name, 'role')
    assert (baseline['active'], baseline['createdby'],
            [{key: row[key] for key in ('database', 'permission')}
             for row in baseline['database_permissions']]) == (
        True, SETTINGS['user'],
        [{'database': DATABASE, 'permission': 'readwrite'}])
    operate(client, route, 'user', 'change_password', {
        'old_password': 'Rt-pass-2026!', 'new_password': 'Rt-pass-2027!'},
        target)
    operate(client, route, 'permission', 'grant_sql', {
        'username': name, 'database': DATABASE,
        'privileges': ['SELECT', 'INSERT']})
    _, granted = record(client, route, 'user', name, 'role')
    assert {row['privilege'] for row in granted['sql_privileges']
            if row['database'] == DATABASE} >= {'SELECT', 'INSERT'}
    operate(client, route, 'permission', 'revoke_sql', {
        'username': name, 'database': DATABASE, 'privileges': ['INSERT']})
    _, revoked = record(client, route, 'user', name, 'role')
    assert 'INSERT' not in {row['privilege']
                            for row in revoked['sql_privileges']
                            if row['database'] == DATABASE}
    run(client, route, 'permission', 'grant', backend_draft(form, {
        'variant': 'grant', 'username': name, 'database': 'defaultdb',
        'permission': 'read'}))
    _, widened = record(client, route, 'user', name, 'role')
    assert {(row['database'], row['permission'])
            for row in widened['database_permissions']} == {
        (DATABASE, 'readwrite'), ('defaultdb', 'read')}
    run(client, route, 'permission', 'revoke', backend_draft(form, {
        'variant': 'grant', 'username': name, 'database': 'defaultdb',
        'permission': 'read'}))
    _, narrowed = record(client, route, 'user', name, 'role')
    assert [row['database'] for row in narrowed['database_permissions']] \
        == [DATABASE]
    operate(client, route, 'user', 'set_active', {'active': False}, target)
    assert record(client, route, 'user', name, 'role')[1]['active'] is False
    operate(client, route, 'user', 'set_active', {'active': True}, target)
    # immudb keeps every user: drop deactivates it.
    run(client, route, 'user', 'drop', {'confirmation': name}, target)
    assert record(client, route, 'user', name, 'role')[1]['active'] is False


def test_database_create_reopen_settings_drop(live):
    route, client = live
    name = f'rt_db_{UNIQUE}'
    form = resolved_form('immudb', 'database')
    try:
        run(client, route, 'database', 'create', backend_draft(form, {
            'name': name, 'autoload': True, 'max_value_length': 1048576,
            'max_transaction_entries': 2048, 'max_concurrency': 12,
            'index_cache_size': 1000, 'aht_sync_threshold': 50000}))
        target, baseline = record(client, route, 'database', name,
                                  'database')
        assert {key: baseline.get(key) for key in (
            'max_value_length', 'max_transaction_entries',
            'max_concurrency', 'index_cache_size',
            'aht_sync_threshold')} == {
            'max_value_length': 1048576, 'max_transaction_entries': 2048,
            'max_concurrency': 12, 'index_cache_size': 1000,
            'aht_sync_threshold': 50000}
        operate(client, route, 'database', 'update_settings', {
            'max_concurrency': 20, 'index_cache_size': 2000,
            'autoload': True}, target)
        _, after = record(client, route, 'database', name, 'database')
        assert (after['max_concurrency'], after['index_cache_size'],
                after['max_value_length']) == (20, 2000, 1048576)
        # Permanent after create: refused before it reaches the server.
        assert 'can not be changed after database creation' in refused(
            client, route, 'database', 'update_settings',
            {'max_value_length': 2048}, target)
        # Unload and load. Live, 1.11.0: while any database is unloaded the
        # server cannot list databases ("already closed" from /db/list,
        # /db/list/v2 and DATABASES(), pkg/server/server.go
        # DatabaseListV2), nor answer /serverinfo. The catalog then lists
        # the databases the metrics endpoint names, checked by /db/use.
        operate(client, route, 'database', 'unload', {}, target,
                confirmation=name)
        unloaded, rows = find(client, route, 'database', name)
        assert unloaded['native']['loaded'] is False
        assert 'cannot list databases' in unloaded['native'][
            'database_list_unread']
        # The rest of the endpoint's catalog is still read.
        assert any(row['resource_kind'] == 'user' for row in rows)
        operate(client, route, 'database', 'load', {}, unloaded)
        loaded, _ = find(client, route, 'database', name)
        assert loaded['native']['loaded'] is True
        assert 'database_list_unread' not in loaded['native']
        # Load by typed name, for a database the navigator cannot show.
        operate(client, route, 'database', 'unload', {}, loaded,
                confirmation=name)
        operate(client, route, 'server', 'load_database', {'name': name},
                find(client, route, 'server', 'immudb')[0])
        assert find(client, route, 'database', name)[0]['native'][
            'max_concurrency'] == 20
    finally:
        names = [row['display_name'] for row in client.list_resources(
            {'route': dict(route)}) if row['resource_kind'] == 'database']
        if name in names:
            run(client, route, 'database', 'drop', {'confirmation': name},
                find(client, route, 'database', name)[0])
    assert name not in [row['display_name'] for row in client.list_resources(
        {'route': dict(route)}) if row['resource_kind'] == 'database']


def test_unload_and_load_the_connected_database(live):
    route, client = live
    target, _ = find(client, route, 'database', DATABASE)
    operate(client, route, 'database', 'unload', {}, target,
            confirmation=DATABASE)
    try:
        # Still listed: marked unloaded; its own keys are not read.
        unloaded, rows = find(client, route, 'database', DATABASE)
        assert unloaded['native']['loaded'] is False
        assert not [row for row in rows if row['resource_kind'] == 'key']
        # Create and delete still confirm while the list cannot be read.
        side = f'rt_side_{UNIQUE}'
        form = resolved_form('immudb', 'database')
        run(client, route, 'database', 'create', backend_draft(
            form, {'name': side, 'autoload': True}))
        run(client, route, 'database', 'drop', {'confirmation': side},
            find(client, route, 'database', side)[0])
    finally:
        operate(client, route, 'database', 'load', {},
                find(client, route, 'database', DATABASE)[0])
    assert find(client, route, 'database', DATABASE)[0]['native'][
        'loaded'] is True
