"""Vitess family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live cluster -> re-inspect.

Owner direction 2026-10-29: Vitess reaches full parity with MySQL/MariaDB
including its native features. Set ``CDEADMIN_ROUNDTRIP_VITESS`` to a JSON
object ``{"host", "port", "user", "keyspace", "http_port"}`` for the demo
vtgate (`dev.sh start vitess`, which also writes the vtctldclient wrapper).
The test works in the given sharded keyspace and the demo's unsharded
``lookup_keyspace``, and removes what it creates. Skipped otherwise.
"""
import json
import os
import sys
import time
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_VITESS')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_VITESS is not set',
                allow_module_level=True)
mysql_connector = pytest.importorskip('mysql.connector')

from pgadmin.cdeadmin.providers.vitess.provider import (  # noqa: E402
    ADMINISTRATION, PROFILE, create_provider,
)
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
KEYSPACE = SETTINGS.get('keyspace', 'test_keyspace')
UNIQUE = uuid.uuid4().hex[:6]
VTCTLD = ROOT.joinpath('tools/reference_engine_demos/runtime/vitess_tools',
                       'vtctldclient')


def admin(keyspace=KEYSPACE):
    return mysql_connector.connect(
        host=SETTINGS['host'], port=int(SETTINGS['port']),
        user=SETTINGS['user'], database=keyspace, autocommit=True)


def query(sql, keyspace=KEYSPACE):
    connection = admin(keyspace)
    try:
        cursor = connection.cursor(buffered=True)
        cursor.execute(sql)
        return cursor.fetchall() if cursor.with_rows else []
    finally:
        connection.close()


@pytest.fixture(scope='module')
def live():
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']),
             'user': SETTINGS['user'], 'database': KEYSPACE,
             'passwordless': True, 'vtgate_http_host': SETTINGS['host'],
             'vtgate_http_port': int(SETTINGS.get('http_port', 15099)),
             'vtgate_http_tls_mode': 'disable',
             'vtctldclient_path': str(VTCTLD),
             'vtctld_server': 'localhost:15999'}
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=f'rt{UNIQUE}',
        pool_namespace=f'rt{UNIQUE}', cache_namespace=f'rt{UNIQUE}',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0')
    client = create_provider(context, SimpleNamespace(
        acquire_secret=None, require=lambda *_args: None)).client
    try:
        yield route, client
    finally:
        for table in (f'rt_orders_{UNIQUE}',):
            try:
                query(f'DROP TABLE IF EXISTS `{table}`')
            except mysql_connector.Error:
                pass


def resources(client, route):
    return client.list_resources({'route': dict(route)})


def executor_request(request, planned):
    """The request shape the visual-admin executor passes to apply."""
    plan = {key: value for key, value in request.items()
            if key != '_provider_route'}
    plan['command_preview'] = planned.get('command_preview')
    return {'plan': plan, 'provider_payload': planned['provider_payload']}


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    result = ADMINISTRATION.apply(client, executor_request(request, planned))
    assert result['accepted'], result
    return result


def find(client, route, kind, name, wait=20):
    # Sharded DDL reaches vtgate schema tracking asynchronously.
    for _attempt in range(wait):
        for row in resources(client, route):
            if row['resource_kind'] == kind and row['display_name'] == name:
                return row
        time.sleep(1)
    return None


def record(client, route, kind, name, form_key):
    row = find(client, route, kind, name)
    assert row is not None, f'{kind} {name} not found'
    form = resolved_form('vitess', form_key)
    rows = resources(client, route)
    return row, record_draft(form, record_from_resource(form, row, rows))


def test_sharded_table_with_vindex_create_reopen_alter_drop(live):
    route, client = live
    table = f'rt_orders_{UNIQUE}'
    form = resolved_form('vitess', 'table')
    run(client, route, 'table', 'create', backend_draft(form, {
        'name': table, 'parent': KEYSPACE,
        'columns': [{'name': 'id', 'type': 'BIGINT', 'nullable': False},
                    {'name': 'note', 'type': 'VARCHAR(40)',
                     'default': "'x'"}],
        'primary_key': [{'name': 'pk', 'columns': ['id']}],
        'unique_constraints': [{'name': 'uq_rt', 'columns': ['note']}],
        'check_constraints': [{'name': 'ck_rt',
                               'expression': 'CHAR_LENGTH(note) > 0'}],
        # Foreign keys are not exercised: the demo keyspaces run
        # foreignKeyMode "unmanaged", where vtgate leaves them to each shard.
        'register_in_vschema': True, 'vindex_name': 'xxhash',
        'vindex_type': 'xxhash', 'vindex_columns': ['id']}))
    target, baseline = record(client, route, 'table', table, 'table')
    assert [(row['name'], row['type'], row['nullable'], row.get('default'))
            for row in baseline['columns']] == [
        ('id', 'bigint', False, None), ('note', 'varchar(40)', True, "'x'")]
    assert [(row['name'], row['columns'])
            for row in baseline['primary_key']] == [('PRIMARY', ['id'])]
    assert [(row['name'], row['columns'])
            for row in baseline['unique_constraints']] == [
        ('uq_rt', ['note'])]
    assert [row['name'] for row in baseline['check_constraints']] == [
        'ck_rt']
    assert 'note' in baseline['check_constraints'][0]['expression']
    assert (baseline['register_in_vschema'], baseline['vindex_type'],
            baseline['vindex_columns']) == (True, 'xxhash', ['id'])
    alter = backend_draft(form, {**baseline, 'columns': baseline['columns'] + [
        {'name': 'amount', 'type': 'DOUBLE'}]}, mode='alter',
        baseline=baseline)
    assert alter == {'add_columns': [{'name': 'amount', 'type': 'DOUBLE'}]}
    run(client, route, 'table', 'alter', alter, target=target)
    assert ('amount',) in query(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name='{table}'")
    run(client, route, 'table', 'drop',
        {'drop_vschema_registration': True, 'confirmation': table},
        target=find(client, route, 'table', table))
    for _attempt in range(20):
        if not query(f"SHOW TABLES LIKE '{table}'"):
            break
        time.sleep(1)
    assert not query(f"SHOW TABLES LIKE '{table}'")


def test_view_alter_and_drop_reach_every_shard(live):
    # vtgate's DROP VIEW returned success and left the view on every shard;
    # the provider now drops it through vtctld ApplySchema.
    route, client = live
    view = f'rt_v_{UNIQUE}'
    run(client, route, 'view', 'create', backend_draft(
        resolved_form('vitess', 'view'),
        {'name': view, 'parent': KEYSPACE, 'query': 'SELECT 1 AS x'}))
    target, baseline = record(client, route, 'view', view, 'view')
    assert 'select' in baseline['query'].lower()
    form = resolved_form('vitess', 'view')
    alter = backend_draft(form, {**baseline, 'query': 'SELECT 2 AS y'},
                          mode='alter', baseline=baseline)
    run(client, route, 'view', 'alter', alter, target=target)
    shards = [row[0].split('/', 1)[1] for row in query('SHOW VITESS_SHARDS')
              if row[0].startswith(KEYSPACE + '/')]
    for shard in shards:
        assert query(
            'SELECT VIEW_DEFINITION FROM information_schema.VIEWS '
            f"WHERE TABLE_NAME='{view}'", keyspace=f'{KEYSPACE}:{shard}'
        ) == [('select 2 AS `y`',)], shard
    run(client, route, 'view', 'drop', {}, target=target)
    for shard in shards:
        names = [row[0] for row in query(
            'SHOW FULL TABLES', keyspace=f'{KEYSPACE}:{shard}')]
        assert view not in names, shard


def test_keyspace_shard_and_vindex_editors(live):
    route, client = live
    keyspace = f'rt_ks_{UNIQUE}'
    run(client, route, 'keyspace', 'create', backend_draft(
        resolved_form('vitess', 'engine_object:keyspace'),
        {'name': keyspace, 'durability_policy': 'none',
         'allow_empty_vschema': True}))
    try:
        run(client, route, 'shard', 'create', backend_draft(
            resolved_form('vitess', 'engine_object:shard'),
            {'keyspace': keyspace, 'shard': '-'}))
        shard, baseline = record(client, route, 'shard', f'{keyspace}/-',
                                 'engine_object:shard')
        assert (baseline['keyspace'], baseline['shard']) == (keyspace, '-')
    finally:
        target = find(client, route, 'keyspace', keyspace)
        run(client, route, 'keyspace', 'drop',
            {'recursive': True, 'force': True}, target=target)
    assert find(client, route, 'keyspace', keyspace, wait=10) is None
    # vtgate serves from SrvVSchema; the drop rebuilds it so vtgate forgets.
    for _attempt in range(20):
        if (keyspace,) not in query('SHOW VITESS_KEYSPACES'):
            break
        time.sleep(1)
    assert (keyspace,) not in query('SHOW VITESS_KEYSPACES')

    vindex = f'rt_vx_{UNIQUE}'
    run(client, route, 'vindex', 'create', backend_draft(
        resolved_form('vitess', 'engine_object:vindex'),
        {'name': vindex, 'vindex_type': 'xxhash'}))
    target, baseline = record(client, route, 'vindex', vindex,
                              'engine_object:vindex')
    assert baseline['vindex_type'] == 'xxhash'
    run(client, route, 'vindex', 'drop', {'confirmation': vindex},
        target=target)
    assert find(client, route, 'vindex', vindex, wait=10) is None


def test_safe_tablet_operations(live):
    route, client = live
    tablet = next(row for row in resources(client, route)
                  if row['resource_kind'] == 'tablet' and
                  row['native'].get('keyspace') == KEYSPACE)
    assert tablet['native']['serving_state'] == 'SERVING'
    for operation in ('ping', 'refresh_state', 'run_health_check'):
        run(client, route, 'tablet', operation, {}, target=tablet)


def test_procedure_in_unsharded_keyspace_and_refused_when_sharded(live):
    route, client = live
    name = f'rt_p_{UNIQUE}'
    form = resolved_form('vitess', 'routine')
    run(client, route, 'procedure', 'create', backend_draft(form, {
        'variant': 'procedure', 'name': name, 'parent': 'lookup_keyspace',
        'parameters': [{'name': 'a', 'type': 'INT', 'mode': 'IN'}],
        'body': 'BEGIN DECLARE b INT; SET b = a; END'}))
    try:
        target, baseline = record(client, route, 'procedure', name, 'routine')
        assert target['display_path'][0] == 'lookup_keyspace'
        assert [(row['name'], row['type'], row['mode'])
                for row in baseline['parameters']] == [('a', 'int', 'IN')]
        # vtgate re-renders the body (keywords lowercased) before storing it.
        assert 'set b = a' in baseline['body'].lower()
        run(client, route, 'procedure', 'drop', {'confirmation': name},
            target=target)
        assert find(client, route, 'procedure', name, wait=5) is None
    finally:
        query(f'DROP PROCEDURE IF EXISTS `lookup_keyspace`.`{name}`')

    request = {'resource_kind': 'procedure', 'operation_id': 'create',
               '_provider_route': route, 'target_resource': None,
               'draft': backend_draft(form, {
                   'variant': 'procedure', 'name': name, 'parent': KEYSPACE,
                   'body': 'BEGIN END'})}
    planned = ADMINISTRATION.plan(request)
    with pytest.raises(Exception, match='sharded keyspace .*VT12001'):
        result = ADMINISTRATION.apply(
            client, executor_request(request, planned))
        assert result['accepted'], result
