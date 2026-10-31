"""immudb family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Owner direction 2026-10-29: immudb reaches full parity with the beta
engines including its native features; 2026-10-31: offer only what can be
read back, by any engine method. Set ``CDEADMIN_ROUNDTRIP_IMMUDB`` to a
JSON object ``{"host", "port", "web_port", "user", "password"}`` for the
demo server (`dev.sh start immudb`). The test creates its own database
and removes it (native unload and delete). Skipped otherwise.
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
    backend_draft, record_draft, record_from_resource, resolved_form,
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
