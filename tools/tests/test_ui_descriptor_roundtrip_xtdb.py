"""XTDB family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> read back.

Owner direction 2026-10-29: XTDB reaches full parity with the beta engines
including its native features; 2026-10-31: offer only what can be read
back, by any engine method. Set ``CDEADMIN_ROUNDTRIP_XTDB`` to a JSON object
``{"host", "port", "healthz_port", "user"}`` for the demo server
(`dev.sh start xtdb`). XTDB 2.1.0 keeps every user and every table it has
seen, so the names here are fixed: one user (``rt_xtdb_user``, created
once, its password changed on later runs) and one table
(``rt_xtdb.order_lines``, its document erased at the end of each run). The
database is attached in memory and detached again. Skipped otherwise.
"""
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_XTDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_XTDB is not set',
                allow_module_level=True)

from pgadmin.cdeadmin.providers.xtdb.client import XTDBClient  # noqa: E402
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, engine_operations, operation_backend_draft,
    operation_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
USER = 'rt_xtdb_user'
# rt_xtdb.orders is not used: a run before integers were bound as int8
# left its _id typed [:union :i16 :i64] for good (types outlive ERASE).
SCHEMA, TABLE = 'rt_xtdb', 'order_lines'
DATABASE = 'rt_xtdb_db'


class _Lease:
    def __init__(self, value):
        self.value = bytearray(value.encode('utf-8'))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.value[:] = b'\x00' * len(self.value)

    def use(self, callback):
        return callback(memoryview(self.value))


@pytest.fixture(scope='module')
def live():
    passwords = {}

    def acquire(reference, *_args):
        return _Lease(passwords.setdefault(reference, uuid.uuid4().hex))

    route = {
        'route_id': 'rt-xtdb', 'host': SETTINGS['host'],
        'port': int(SETTINGS['port']), 'database': 'xtdb',
        'username': SETTINGS['user'], 'tls_mode': 'disable',
        'connect_timeout': 20, 'statement_timeout': 60,
        'application_name': 'CDEadmin-roundtrip',
        'healthz_url': f"http://{SETTINGS['host']}:"
                       f"{int(SETTINGS['healthz_port'])}",
        'principal_reference': 'rt'}
    return route, XTDBClient(acquire)


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    assert client.validate_admin_operation(request)['errors'] == []
    planned = client.plan_admin_operation(request)
    handle = {'plan': request,
              'provider_payload': planned['provider_payload']}
    handle['provider_result'] = client.apply_admin_operation(handle)
    return planned, client.validate_admin_post_state(handle)


def operate(client, route, kind, operation, values, target=None,
            confirmation=None):
    """Run an operation from its descriptor, as the OperationDialog does."""
    declared = engine_operations('xtdb')[f'{operation}@{kind}']
    return run(client, route, kind, operation, operation_backend_draft(
        declared, operation_draft(declared, values, confirmation)), target)


def find(client, route, kind, name):
    rows = client.list_resources({'route': dict(route)})
    found = [row for row in rows
             if row['resource_kind'] == kind and row['display_name'] == name]
    return (found[0] if found else None), rows


def record(client, route, kind, name, family):
    row, rows = find(client, route, kind, name)
    assert row is not None, f'{kind} {name} is not listed'
    form = resolved_form('xtdb', family)
    return row, record_draft(form, record_from_resource(form, row, rows))


def erase(client, route, target):
    rows = client.read_admin_rows({'_provider_route': route,
                                   'target_resource': target, 'limit': 10})
    for row in rows['rows']:
        _, observed = operate(client, route, 'table', 'erase', {
            'row_identity': row['identity_token'],
            'acknowledge_irreversible': True}, target,
            confirmation=target['display_name'])
        assert observed['confirmed'], observed


def test_table_create_from_document_reopen_erase(live):
    route, client = live
    name = f'{SCHEMA}.{TABLE}'
    existing, _ = find(client, route, 'table', name)
    if existing:
        erase(client, route, existing)
    form = resolved_form('xtdb', 'table')
    _, observed = run(client, route, 'table', 'create', backend_draft(form, {
        'schema': SCHEMA, 'name': TABLE,
        'document_fields': [
            {'name': '_id', 'value_type': 'integer', 'value': '1'},
            {'name': 'item', 'value_type': 'text', 'value': 'bolt'},
            {'name': 'qty', 'value_type': 'integer', 'value': '3'},
            {'name': 'price', 'value_type': 'decimal', 'value': '2.50'},
            {'name': 'rush', 'value_type': 'boolean', 'value': 'true'},
            {'name': 'due', 'value_type': 'date', 'value': '2026-12-01'},
            {'name': 'tags', 'value_type': 'nested',
             'value': '{"bin": "A4"}'}],
        'valid_from': '2026-01-01T00:00:00Z', 'valid_to': ''}))
    assert observed['confirmed'], observed
    target, after = record(client, route, 'table', name, 'table')
    types = {row['name']: row['type'] for row in after['columns']
             if not row['temporal']}
    # XTDB's own types, read from information_schema.columns.
    assert types['_id'] == ':i64' and types['item'] == ':utf8'
    assert types['qty'] == ':i64' and types['rush'] == ':bool'
    assert {'price', 'due', 'tags'} <= set(types)
    assert {row['name'] for row in after['columns'] if row['temporal']} == {
        '_valid_from', '_valid_to', '_system_from', '_system_to'}
    # Refused before sending: a value that is not of its declared type.
    request = {'resource_kind': 'table', 'operation_id': 'create',
               '_provider_route': route, 'target_resource': None,
               'draft': {'schema': SCHEMA, 'name': TABLE, 'document_fields': [
                   {'name': '_id', 'value_type': 'integer', 'value': 'x'}]}}
    assert 'not a valid integer' in client.validate_admin_operation(
        request)['errors'][0]['message']
    erase(client, route, target)
    # The table stays listed after its last document is erased.
    assert find(client, route, 'table', name)[0] is not None


def test_user_create_or_change_password(live):
    route, client = live
    form = resolved_form('xtdb', 'role')
    existing, _ = find(client, route, 'user', USER)
    if existing is None:
        _, observed = run(client, route, 'user', 'create', backend_draft(
            form, {'username': USER, 'password_reference': 'rt-first'}))
        assert observed['confirmed'], observed
    target, after = record(client, route, 'user', USER, 'role')
    assert after['username'] == USER and after['usesuper'] is False
    _, observed = run(client, route, 'user', 'alter', backend_draft(
        form, {**after, 'password_reference': 'rt-next'}, mode='alter',
        baseline=after), target)
    assert observed == {**observed, 'confirmed': True,
                        'reason': 'xtdb_password_hash_changed'}


def test_database_attach_list_detach(live):
    route, client = live
    form = resolved_form('xtdb', 'database')
    if find(client, route, 'database', DATABASE)[0] is not None:
        run(client, route, 'database', 'drop', {'acknowledge_detach': True},
            find(client, route, 'database', DATABASE)[0])
    _, observed = run(client, route, 'database', 'create', backend_draft(
        form, {'name': DATABASE,
               'config_yaml': 'log: !InMemory\nstorage: !InMemory\n'}))
    assert observed['confirmed'], observed
    target, after = record(client, route, 'database', DATABASE, 'database')
    assert (after['primary'], after['connected']) == (False, False)
    assert not after.get('database_list_unread')
    primary = record(client, route, 'database', 'xtdb', 'database')[1]
    assert (primary['primary'], primary['connected']) == (True, True)
    _, observed = run(client, route, 'database', 'drop',
                      {'acknowledge_detach': True}, target)
    assert observed == {**observed, 'confirmed': True,
                        'reason': 'xtdb_database_not_attached'}
    assert find(client, route, 'database', DATABASE)[0] is None
