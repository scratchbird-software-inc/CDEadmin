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
    backend_draft, engine_operations, operation_backend_draft,
    operation_draft, record_draft, record_from_resource, resolved_form,
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


def run(client, route, kind, operation, draft, target=None,
        post_state=False):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    executed = executor_request(request, planned)
    result = ADMINISTRATION.apply(client, executed)
    assert result['accepted'], result
    if post_state:
        # The provider's own after-check, as the executor runs it.
        state = ADMINISTRATION.validate_operation_post_state(client, executed)
        assert state['confirmed'], state.get('reason')
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


def shards_of(keyspace):
    return [row[0].split('/', 1)[1] for row in query('SHOW VITESS_SHARDS')
            if row[0].startswith(keyspace + '/')]


def test_index_create_and_drop_reach_every_shard(live):
    route, client = live
    table = f'rt_ix_t_{UNIQUE}'
    index = f'rt_ix_{UNIQUE}'
    query(f'CREATE TABLE `{table}` (id BIGINT NOT NULL PRIMARY KEY, '
          'a INT, b INT)')
    try:
        query(f'ALTER VSCHEMA ON `{table}` ADD VINDEX xxhash (id)')
        form = resolved_form('vitess', 'index')
        run(client, route, 'index', 'create', backend_draft(form, {
            'name': index, 'parent': KEYSPACE, 'table': table,
            'columns': ['b', 'a'], 'unique': False}))
        target, baseline = record(client, route, 'index', index, 'index')
        assert (baseline['table'],
                [row['value'] for row in baseline['columns']],
                baseline['unique']) == (table, ['b', 'a'], False)
        for shard in shards_of(KEYSPACE):
            assert query(
                f"SHOW INDEX FROM `{table}` WHERE Key_name = '{index}'",
                keyspace=f'{KEYSPACE}:{shard}'), shard
        run(client, route, 'index', 'drop', {'confirmation': index},
            target=target)
        for shard in shards_of(KEYSPACE):
            assert not query(
                f"SHOW INDEX FROM `{table}` WHERE Key_name = '{index}'",
                keyspace=f'{KEYSPACE}:{shard}'), shard
    finally:
        query(f'ALTER VSCHEMA DROP TABLE `{table}`')
        query(f'DROP TABLE IF EXISTS `{table}`')


def test_unsharded_keyspace_objects_are_listed(live):
    # vtgate reads information_schema for the session keyspace unless an
    # equality predicate names another; the catalog reads each keyspace.
    route, client = live
    rows = resources(client, route)
    assert any(row['resource_kind'] == 'table' and
               row['display_path'][0] == 'lookup_keyspace' for row in rows)
    assert any(row['resource_kind'] == 'index' and
               row['display_path'][0] == 'lookup_keyspace' for row in rows)


def test_sequence_create_reopen_alter_drop(live):
    route, client = live
    name = f'rt_seq_{UNIQUE}'
    form = resolved_form('vitess', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(form, {
        'name': name, 'parent': 'lookup_keyspace', 'start': 500,
        'cache': 50}))
    try:
        target, baseline = record(client, route, 'sequence', name,
                                  'sequence')
        assert target['display_path'] == ['lookup_keyspace', name]
        assert (baseline['restart'], baseline['cache']) == (500, 50)
        alter = backend_draft(form, {**baseline, 'restart': 900,
                                     'cache': 20},
                              mode='alter', baseline=baseline)
        run(client, route, 'sequence', 'alter', alter, target=target)
        assert query(f'SELECT next_id, cache FROM `{name}` WHERE id = 0',
                     keyspace='lookup_keyspace') == [(900, 20)]
        run(client, route, 'sequence', 'drop', {'confirmation': name},
            target=target)
        assert find(client, route, 'sequence', name, wait=5) is None
        assert (name,) not in query('SHOW TABLES',
                                    keyspace='lookup_keyspace')
    finally:
        try:
            query(f'ALTER VSCHEMA DROP SEQUENCE `{name}`',
                  keyspace='lookup_keyspace')
        except mysql_connector.Error:
            pass
        query(f'DROP TABLE IF EXISTS `{name}`', keyspace='lookup_keyspace')


def test_sequence_refused_on_sharded_keyspace_leaves_nothing(live):
    route, client = live
    name = f'rt_sseq_{UNIQUE}'
    request = {'resource_kind': 'sequence', 'operation_id': 'create',
               '_provider_route': route, 'target_resource': None,
               'draft': backend_draft(resolved_form('vitess', 'sequence'),
                                      {'name': name, 'parent': KEYSPACE})}
    planned = ADMINISTRATION.plan(request)
    with pytest.raises(Exception, match='sequences .* sharded keyspace'):
        ADMINISTRATION.apply(client, executor_request(request, planned))
    for shard in shards_of(KEYSPACE):
        assert (name,) not in query('SHOW TABLES',
                                    keyspace=f'{KEYSPACE}:{shard}'), shard


def test_table_draws_ids_from_an_attached_sequence(live):
    route, client = live
    sequence = f'rt_aseq_{UNIQUE}'
    table = f'rt_at_{UNIQUE}'
    run(client, route, 'sequence', 'create', backend_draft(
        resolved_form('vitess', 'sequence'),
        {'name': sequence, 'parent': 'lookup_keyspace', 'start': 7000,
         'cache': 10}))
    try:
        form = resolved_form('vitess', 'table')
        run(client, route, 'table', 'create', backend_draft(form, {
            'name': table, 'parent': KEYSPACE,
            'columns': [{'name': 'id', 'type': 'BIGINT', 'nullable': False},
                        {'name': 'v', 'type': 'INT'}],
            'primary_key': [{'name': 'pk', 'columns': ['id']}],
            'register_in_vschema': True, 'vindex_name': 'xxhash',
            'vindex_columns': ['id'], 'auto_increment_column': 'id',
            'auto_increment_sequence': f'lookup_keyspace.{sequence}'}))
        target, baseline = record(client, route, 'table', table, 'table')
        assert (baseline['auto_increment_column'],
                baseline['auto_increment_sequence']) == (
            'id', f'lookup_keyspace.{sequence}')
        query(f'INSERT INTO `{table}` (v) VALUES (1), (2), (3)')
        assert query(f'SELECT id FROM `{table}` ORDER BY id') == [
            (7000,), (7001,), (7002,)]
        run(client, route, 'table', 'drop',
            {'drop_vschema_registration': True, 'confirmation': table},
            target=target)
    finally:
        for statement, keyspace in (
                (f'ALTER VSCHEMA DROP TABLE `{KEYSPACE}`.`{table}`',
                 KEYSPACE),
                (f'DROP TABLE IF EXISTS `{table}`', KEYSPACE),
                (f'ALTER VSCHEMA DROP SEQUENCE `{sequence}`',
                 'lookup_keyspace'),
                (f'DROP TABLE IF EXISTS `{sequence}`', 'lookup_keyspace')):
            try:
                query(statement, keyspace=keyspace)
            except mysql_connector.Error:
                pass


def routing_rules():
    import subprocess
    output = subprocess.run(
        [str(VTCTLD), '--server', 'localhost:15999', 'GetRoutingRules'],
        check=True, capture_output=True, text=True).stdout
    # vtctldclient prints from_table/to_tables and takes either form.
    return [{'fromTable': rule['from_table'], 'toTables': rule['to_tables']}
            for rule in json.loads(output).get('rules') or []]


def test_routing_rules_editor_keeps_existing_rules(live):
    # Vitess replaces the global rule set whole; the editor reopens with the
    # current rules, so an edit adds to them instead of wiping them.
    import subprocess
    route, client = live
    original = routing_rules()
    alias, second = f'rt_alias_{UNIQUE}', f'rt_alias2_{UNIQUE}'
    form = resolved_form('vitess', 'engine_object:routing-rule')
    try:
        target, baseline = record(client, route, 'routing-rule',
                                  'global-routing-rules',
                                  'engine_object:routing-rule')
        rows = baseline['rules'] + [{'from_table': f'{KEYSPACE}.{alias}',
                                     'to_table': f'{KEYSPACE}.customers'}]
        run(client, route, 'routing-rule', 'alter', backend_draft(
            form, {**baseline, 'rules': rows}, mode='alter',
            baseline=baseline), target=target, post_state=True)
        assert {'fromTable': f'{KEYSPACE}.{alias}',
                'toTables': [f'{KEYSPACE}.customers']} in routing_rules()
        for _attempt in range(20):
            try:
                count = query(f'SELECT COUNT(*) FROM `{alias}`')
                break
            except mysql_connector.Error:
                time.sleep(1)
        assert count == query('SELECT COUNT(*) FROM customers')

        target, baseline = record(client, route, 'routing-rule',
                                  'global-routing-rules',
                                  'engine_object:routing-rule')
        assert [(row['from_table'], row['to_table'])
                for row in baseline['rules']] == [
            (rule['fromTable'], rule['toTables'][0]) for rule in original
        ] + [(f'{KEYSPACE}.{alias}', f'{KEYSPACE}.customers')]
        rows = baseline['rules'] + [{'from_table': f'{KEYSPACE}.{second}',
                                     'to_table': f'{KEYSPACE}.assets'}]
        run(client, route, 'routing-rule', 'alter', backend_draft(
            form, {**baseline, 'rules': rows}, mode='alter',
            baseline=baseline), target=target, post_state=True)
        sources = [rule['fromTable'] for rule in routing_rules()]
        assert f'{KEYSPACE}.{alias}' in sources
        assert f'{KEYSPACE}.{second}' in sources

        # vtgate refuses to route a rule with two targets; refused at plan.
        with pytest.raises(Exception, match='one target table'):
            ADMINISTRATION.plan({
                'resource_kind': 'routing-rule', 'operation_id': 'alter',
                'target_resource': target, '_provider_route': route,
                'draft': {'rules': {'rules': [{
                    'fromTable': f'{KEYSPACE}.{alias}',
                    'toTables': [f'{KEYSPACE}.customers',
                                 f'{KEYSPACE}.assets']}]}}})
    finally:
        subprocess.run(
            [str(VTCTLD), '--server', 'localhost:15999', 'ApplyRoutingRules',
             '--rules', json.dumps({'rules': original})],
            check=True, capture_output=True)
    assert routing_rules() == original


def test_tablet_backup_restore_and_backup_delete(live):
    # The demo's tablets share one file backup root. Works on the
    # lookup_keyspace replica, which catches up from its primary afterwards.
    route, client = live
    replica = next(row for row in resources(client, route)
                   if row['resource_kind'] == 'tablet' and
                   row['native'].get('keyspace') == 'lookup_keyspace' and
                   row['native'].get('tablet_type') == 'REPLICA')
    alias = replica['display_name']
    operations = engine_operations('vitess')
    before = {row['resource_id'] for row in resources(client, route)
              if row['resource_kind'] == 'backup'}
    run(client, route, 'tablet', 'backup', operation_backend_draft(
        operations['backup@tablet'], operation_draft(
            operations['backup@tablet'])), target=replica, post_state=True)
    backups = [row for row in resources(client, route)
               if row['resource_kind'] == 'backup' and
               row['resource_id'] not in before]
    assert len(backups) == 1, backups
    backup = backups[0]
    assert backup['display_path'][:2] == ['lookup_keyspace', '-']
    assert backup['display_name'].endswith(alias)
    try:
        # Backup names start with the timestamp RestoreFromBackup takes.
        timestamp = backup['display_name'].rsplit('.', 1)[0]
        restore = operations['restore@tablet']
        run(client, route, 'tablet', 'restore', operation_backend_draft(
            restore, operation_draft(restore, {
                'backup_timestamp': timestamp}, alias)), target=replica)
        for _attempt in range(60):
            tablet = next(row for row in resources(client, route)
                          if row['display_name'] == alias and
                          row['resource_kind'] == 'tablet')
            if tablet['native']['serving_state'] == 'SERVING':
                break
            time.sleep(1)
        assert tablet['native']['serving_state'] == 'SERVING'
        assert tablet['native']['tablet_type'] == 'REPLICA'
    finally:
        run(client, route, 'backup', 'drop',
            {'confirmation': backup['display_name']}, target=backup,
            post_state=True)
    assert backup['resource_id'] not in {
        row['resource_id'] for row in resources(client, route)}


def test_online_ddl_submit_launch_complete(live):
    route, client = live
    table = f'rt_od_{UNIQUE}'
    query(f'CREATE TABLE `{table}` (id BIGINT NOT NULL PRIMARY KEY, v INT)')
    try:
        query(f'ALTER VSCHEMA ON `{table}` ADD VINDEX xxhash (id)')
        form = resolved_form('vitess', 'table')
        target, baseline = record(client, route, 'table', table, 'table')
        alter = backend_draft(form, {
            **baseline, 'columns': baseline['columns'] + [
                {'name': 'w', 'type': 'INT'}],
            'ddl_strategy': 'vitess', 'postpone_launch': True,
            'postpone_completion': True}, mode='alter', baseline=baseline)
        run(client, route, 'table', 'alter', alter, target=target)

        def migration(status=None, wait=60):
            for _attempt in range(wait):
                rows = [row for row in resources(client, route)
                        if row['resource_kind'] == 'online-ddl' and
                        row['native']['table'] == table]
                if rows and (status is None or
                             rows[0]['native']['status'] in status):
                    return rows[0]
                time.sleep(1)
            return rows[0] if rows else None

        queued = migration({'queued'})
        assert queued is not None
        assert (queued['native']['strategy'], queued['native']['status'],
                queued['native']['postpone_launch']) == (
            'vitess', 'queued', True)
        operations = engine_operations('vitess')
        for operation in ('launch', 'complete'):
            if operation == 'complete':
                # Cut-over waits until the copy is in sync.
                for _attempt in range(60):
                    current = migration()
                    if current['native']['ready_to_complete']:
                        break
                    time.sleep(1)
            declared = operations[f'{operation}@online-ddl']
            run(client, route, 'online-ddl', operation,
                operation_backend_draft(declared, operation_draft(declared)),
                target=migration())
        assert migration({'complete'})['native']['status'] == 'complete'
        for shard in shards_of(KEYSPACE):
            columns = [row[0] for row in query(
                f'SHOW COLUMNS FROM `{table}`',
                keyspace=f'{KEYSPACE}:{shard}')]
            assert 'w' in columns, shard
    finally:
        query(f'ALTER VSCHEMA DROP TABLE `{KEYSPACE}`.`{table}`')
        query(f'DROP TABLE IF EXISTS `{table}`')
