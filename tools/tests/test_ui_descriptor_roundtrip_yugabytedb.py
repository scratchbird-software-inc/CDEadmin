"""YugabyteDB YSQL family forms round-trip (README step 8): draft through
the descriptor fields -> provider plan -> apply on a live node -> re-inspect.

Owner direction 2026-10-29: YugabyteDB YSQL reaches full parity with
PostgreSQL including its native features. Set
``CDEADMIN_ROUNDTRIP_YUGABYTEDB`` to a JSON object ``{"host", "port",
"user"}`` for the demo node (`dev.sh start yugabytedb`). The test creates
its own database and roles and removes them. Skipped otherwise.
"""
import json
import os
import subprocess
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_YUGABYTEDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_YUGABYTEDB is not set',
                allow_module_level=True)
psycopg = pytest.importorskip('psycopg')

from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION, PROFILE, create_provider,
)
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, engine_operations, operation_backend_draft,
    operation_draft, provider_target, record_draft, record_from_resource,
    resolved_form,
)

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'rt_{UNIQUE}'
YB_ADMIN = (ROOT / 'tools/reference_engine_demos/runtime/yugabyte_tools/'
            'yb-admin')


def connect(database='yugabyte'):
    return psycopg.connect(
        host=SETTINGS['host'], port=int(SETTINGS['port']),
        user=SETTINGS['user'], dbname=database, sslmode='disable',
        autocommit=True)


def query(sql, database=DATABASE):
    with connect(database) as connection:
        cursor = connection.execute(sql)
        return cursor.fetchall() if cursor.description else []


@pytest.fixture(scope='module')
def live():
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']),
             'user': SETTINGS['user'], 'database': DATABASE,
             'sslmode': 'disable'}
    # yb-admin through the demo wrapper (demo_estate.write_yugabyte_tools),
    # at the node's current master address.
    if YB_ADMIN.is_file():
        sys.path.insert(0, str(ROOT / 'tools/reference_engine_demos'))
        from demo_estate import yugabyte_master_addresses
        route.update(yb_admin_path=str(YB_ADMIN),
                     master_addresses=yugabyte_master_addresses())
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=f'rt{UNIQUE}',
        pool_namespace=f'rt{UNIQUE}', cache_namespace=f'rt{UNIQUE}',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0',
        mode='legacy_native', runtime_verification_state='unverified',
        verified_runtime_family=None, declared_runtime_family=None,
        target_adapter_id=None, effective_permissions=frozenset())
    provider = create_provider(context, SimpleNamespace(
        acquire_secret=None, require=lambda *_args: None))
    PROVIDERS[:] = [provider]
    client = provider.client
    try:
        with connect() as connection:
            connection.execute(f'CREATE DATABASE {DATABASE}')
        query('CREATE TABLE public.t (id INT PRIMARY KEY, v INT, w INT)')
        query('CREATE VIEW public.tv AS SELECT id, v FROM public.t')
        query('CREATE FUNCTION public.on_t() RETURNS TRIGGER '
              'LANGUAGE plpgsql AS $$ BEGIN RETURN COALESCE(NEW, OLD); '
              'END $$')
        yield route, client
    finally:
        if 'yb_admin_path' in route:
            # A schedule left on the database blocks dropping it.
            listed = json.loads(admin('list_snapshot_schedules') or '{}')
            for row in listed.get('schedules') or []:
                if (row.get('options') or {}).get('filter') == \
                        f'ysql.{DATABASE}':
                    admin('delete_snapshot_schedule', row['id'])
        with connect() as connection:
            connection.execute(f'DROP DATABASE IF EXISTS {DATABASE} '
                               'WITH (FORCE)')
            connection.execute(f'DROP TABLESPACE IF EXISTS rt_opsts_{UNIQUE}')
            for role in (f'rt_user_{UNIQUE}', f'rt_role_{UNIQUE}',
                         f'rt_user2_{UNIQUE}', f'rt_native_user_{UNIQUE}',
                         f'rt_native_role_{UNIQUE}'):
                connection.execute(f'DROP ROLE IF EXISTS {role}')


def resources(client, route):
    return client.list_resources({'route': dict(route)})


def executor_request(request, planned):
    plan = {key: value for key, value in request.items()
            if key != '_provider_route'}
    plan['command_preview'] = planned.get('command_preview')
    return {'plan': plan, 'provider_payload': planned['provider_payload']}


# The provider the fixture built; run() also validates through it.
PROVIDERS = []


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    # The UI submits through visual administration, whose field contract
    # and catalog must admit the form's draft too (2026-10-31: several did
    # not, while this direct path accepted them).
    ui = PROVIDERS[0].validate_visual_admin({
        **request, 'target_resource': provider_target(target, 'yugabytedb')})
    assert ui['errors'] == [], ui['errors']
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    result = ADMINISTRATION.apply(client, executor_request(request, planned))
    assert result['accepted'], result
    return planned


def find(client, route, kind, name):
    rows = resources(client, route)
    found = [row for row in rows
             if row['resource_kind'] == kind and row['display_name'] == name]
    assert len(found) == 1, f'{kind} {name}: {len(found)} records'
    return found[0], rows


def record(client, route, kind, name, family, variant=None):
    row, rows = find(client, route, kind, name)
    form = resolved_form('yugabytedb', family)
    value = record_draft(form, record_from_resource(form, row, rows))
    if variant:
        # The editor host adds the kind's variant to the record.
        value['variant'] = variant
    return row, value


def refused(kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, 'draft': draft}
    return ' '.join(error['message'] for error in
                    ADMINISTRATION.validate(request)['errors'])


def test_triggers_every_kind_reopen_replace_rename_drop(live):
    route, client = live
    form = resolved_form('yugabytedb', 'trigger')
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'tr_row', 'table': 'public.t', 'timing': 'BEFORE',
        'level': 'ROW', 'events': ['INSERT', 'UPDATE'],
        'update_columns': [{'value': 'v'}], 'when': 'NEW.v > 0',
        'function': 'public.on_t()', 'arguments': [{'value': "it's"}],
        'comment': 'row trigger'}))
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'tr_stmt', 'table': 'public.t', 'timing': 'AFTER',
        'level': 'STATEMENT', 'events': ['TRUNCATE'],
        'function': 'public.on_t()', 'enabled': 'DISABLED'}))
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'tr_view', 'table': 'public.tv', 'timing': 'INSTEAD OF',
        'level': 'ROW', 'events': ['INSERT'],
        'function': 'public.on_t()'}))
    target, baseline = record(client, route, 'trigger', 'tr_row', 'trigger')
    assert (baseline['table'], baseline['timing'], baseline['level'],
            baseline['events'],
            [row['value'] for row in baseline['update_columns']],
            baseline['when'], baseline['function'],
            [row['value'] for row in baseline['arguments']],
            baseline['comment'], baseline['enabled']) == (
        'public.t', 'BEFORE', 'ROW', ['INSERT', 'UPDATE'], ['v'],
        '(new.v > 0)', 'public.on_t()', ["it's"], 'row trigger', 'ORIGIN')
    _, stmt = record(client, route, 'trigger', 'tr_stmt', 'trigger')
    assert (stmt['level'], stmt['events'], stmt['enabled']) == (
        'STATEMENT', ['TRUNCATE'], 'DISABLED')
    _, view = record(client, route, 'trigger', 'tr_view', 'trigger')
    assert (view['timing'], view['table']) == ('INSTEAD OF', 'public.tv')
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'trigger', 'alter', backend_draft(form, {
        **baseline, 'timing': 'AFTER', 'events': ['DELETE'],
        'update_columns': [], 'when': '', 'enabled': 'ALWAYS',
        'comment': '', 'name': 'tr_row2'},
        mode='alter', baseline=baseline), target=target)
    _, after = record(client, route, 'trigger', 'tr_row2', 'trigger')
    assert (after['timing'], after['events'], after['when'],
            after['enabled'], after['comment']) == (
        'AFTER', ['DELETE'], None, 'ALWAYS', None)
    assert 'statement-level' in refused('trigger', 'create', {
        'name': 'x', 'table': 'public.t', 'timing': 'AFTER',
        'level': 'ROW', 'events': ['TRUNCATE'], 'function': 'public.on_t'})
    for name in ('tr_row2', 'tr_stmt', 'tr_view'):
        run(client, route, 'trigger', 'drop', {'confirmation': name},
            target=find(client, route, 'trigger', name)[0])
    assert not query("SELECT 1 FROM pg_trigger WHERE tgname LIKE "
                     "'tr\\_%'")


def test_users_and_roles(live):
    route, client = live
    form = resolved_form('yugabytedb', 'role')
    role, user = f'rt_role_{UNIQUE}', f'rt_user_{UNIQUE}'
    run(client, route, 'role', 'create', backend_draft(form, {
        'variant': 'role', 'name': role,
        'privileges': ['CREATEDB', 'INHERIT'], 'comment': 'a role'}))
    planned = run(client, route, 'user', 'create', backend_draft(form, {
        'variant': 'user', 'name': user, 'password': 'Secret-1!',
        'valid_until': '2030-01-01', 'connection_limit': 5,
        'privileges': ['BYPASSRLS'], 'member_of': [{'role': role}]}))
    assert 'Secret-1!' not in json.dumps(planned['command_preview'])
    _, made = record(client, route, 'role', role, 'role', 'role')
    assert (made['login'], made['privileges'], made['comment']) == (
        False, ['CREATEDB', 'INHERIT'], 'a role')
    target, baseline = record(client, route, 'user', user, 'role', 'user')
    assert (baseline['login'], baseline['privileges'],
            baseline['connection_limit'], baseline['valid_until'][:10],
            [row['role'] for row in baseline['member_of']]) == (
        True, ['BYPASSRLS'], 5, '2030-01-01', [role])
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'user', 'alter', backend_draft(form, {
        **baseline, 'privileges': ['INHERIT', 'CREATEROLE'],
        'connection_limit': -1, 'valid_until': '', 'member_of': [],
        'clear_password': True, 'comment': 'renamed',
        'name': f'rt_user2_{UNIQUE}'}, mode='alter', baseline=baseline),
        target=target)
    _, after = record(client, route, 'user', f'rt_user2_{UNIQUE}', 'role',
                      'user')
    assert (after['privileges'], after['connection_limit'],
            after['valid_until'], after['member_of'], after['comment']) == (
        ['CREATEROLE', 'INHERIT'], -1, None, [], 'renamed')
    assert query(f"SELECT rolpassword IS NULL FROM pg_authid WHERE "
                 f"rolname = 'rt_user2_{UNIQUE}'") == [(True,)]
    for kind, name in (('user', f'rt_user2_{UNIQUE}'), ('role', role)):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query(f"SELECT 1 FROM pg_roles WHERE rolname LIKE "
                     f"'rt\\_%{UNIQUE}'")


def by_name(rows):
    return {row['name']: row for row in rows}


PLACEMENT = ('{"num_replicas":1,"placement_blocks":[{"cloud":"cloud1",'
             '"region":"datacenter1","zone":"rack1","min_num_replicas":1}]}')


def test_table_create_reopen_alter_drop(live):
    route, client = live
    space = f'rt_ts_{UNIQUE}'
    with connect() as connection:
        connection.execute(f"CREATE TABLESPACE {space} WITH "
                           f"(replica_placement='{PLACEMENT}')")
    try:
        query('CREATE TABLE public.parent (k INT PRIMARY KEY)')
        form = resolved_form('yugabytedb', 'table')
        run(client, route, 'table', 'create', backend_draft(form, {
            'name': 'rt_orders', 'parent': 'public', 'comment': 'orders',
            'tablespace': space, 'split_into': 3,
            'columns': [
                {'name': 'region', 'type': 'text', 'nullable': False},
                {'name': 'id', 'type': 'bigint', 'nullable': False,
                 'identity': 'BY DEFAULT'},
                {'name': 'note', 'type': 'varchar(40)', 'collation': 'C',
                 'default': "'x'", 'comment': 'a note'},
                {'name': 'twice', 'type': 'bigint',
                 'generated_expression': 'id * 2'},
                {'name': 'ref', 'type': 'int'},
            ],
            'primary_key': [{'name': 'rt_orders_pkey',
                             'columns': ['region', 'id'],
                             'hash_columns': ['region', 'id']}],
            'unique_constraints': [{'name': 'uq_note',
                                    'columns': ['note']}],
            'foreign_keys': [{'name': 'fk_ref', 'columns': ['ref'],
                              'references_table': 'public.parent',
                              'references_columns': ['k'],
                              'on_delete': 'SET NULL', 'deferrable': True,
                              'initially_deferred': True}],
            'check_constraints': [{'name': 'ck_id',
                                   'expression': 'id > 0'}]}))
        assert query("SELECT num_tablets FROM yb_table_properties("
                     "'public.rt_orders'::regclass)") == [(3,)]
        target, baseline = record(client, route, 'table', 'rt_orders',
                                  'table')
        columns = by_name(baseline['columns'])
        assert list(columns) == ['region', 'id', 'note', 'twice', 'ref']
        assert (columns['id']['identity'], columns['id']['default'],
                columns['note']['type'], columns['note']['collation'],
                columns['note']['default'], columns['note']['comment'],
                columns['twice']['generated_expression']) == (
            'BY DEFAULT', None, 'character varying(40)', 'C',
            "'x'::character varying", 'a note', '(id * 2)')
        pk = baseline['primary_key'][0]
        assert (pk['columns'], pk['hash_columns']) == (
            ['region', 'id'], ['region', 'id'])
        assert [row['name'] for row in baseline['unique_constraints']] \
            == ['uq_note']
        # Live: "DEFERRABLE unique constraints are not supported yet".
        assert 'deferrable unique' in refused('table', 'create', {
            'name': 'x', 'columns': [{'name': 'a', 'type': 'int'}],
            'unique_constraints': [{'columns': ['a'],
                                    'deferrable': True}]})
        fk = baseline['foreign_keys'][0]
        assert (fk['references_table'], fk['on_delete'], fk['deferrable'],
                fk['initially_deferred']) == (
            'public.parent', 'SET NULL', True, True)
        assert (baseline['tablespace'], baseline['comment']) == (
            space, 'orders')
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}

        changed = [dict(row) for row in baseline['columns']]
        for row in changed:
            if row['name'] == 'ref':
                row.update(name='ref_id', type='bigint', comment='renamed')
            if row['name'] == 'note':
                row.update(default='', nullable=False, collation='')
            if row['name'] == 'id':
                row.update(identity='')
            if row['name'] == 'twice':
                row.update(generated_expression='')
        changed.append({'name': 'extra', 'type': 'int'})
        alter = backend_draft(form, {
            **baseline, 'columns': changed,
            'unique_constraints': [{'name': 'uq_extra',
                                    'columns': ['extra']}],
            'primary_key': [{'name': 'rt_orders_pkey',
                             'columns': ['region', 'id'],
                             'hash_columns': [], 'order': 'ASC'}],
            'tablespace': '', 'row_level_security': True,
            'comment': 'orders v2'}, mode='alter', baseline=baseline)
        planned = run(client, route, 'table', 'alter', alter, target=target)
        assert any('rewrites' in item
                   for item in planned.get('warnings') or [])
        target, after = record(client, route, 'table', 'rt_orders', 'table')
        columns = by_name(after['columns'])
        assert (columns['ref_id']['type'], columns['ref_id']['comment'],
                columns['note']['default'], columns['note']['nullable'],
                columns['note']['collation'], columns['id']['identity'],
                columns['twice']['generated_expression']) == (
            'bigint', 'renamed', None, False, None, '', None)
        assert [row['name'] for row in after['unique_constraints']] == [
            'uq_extra']
        assert after['primary_key'][0]['hash_columns'] == []
        assert [row['name'] for row in after['check_constraints']] == [
            'ck_id']
        assert after['foreign_keys'][0]['columns'] == ['ref_id']
        assert (after['tablespace'], after['row_level_security'],
                after['comment']) == (None, True, 'orders v2')

        run(client, route, 'table', 'create', backend_draft(form, {
            'name': 'rt_events', 'parent': 'public',
            'columns': [{'name': 'id', 'type': 'int'},
                        {'name': 'at', 'type': 'date', 'nullable': False}],
            'partition_by': 'RANGE', 'partition_key': 'at'}))
        _, events = record(client, route, 'table', 'rt_events', 'table')
        assert (events['partition_by'], events['partition_key']) == (
            'RANGE', 'at')
        run(client, route, 'table', 'create', backend_draft(form, {
            'name': 'rt_ranges', 'parent': 'public',
            'columns': [{'name': 'id', 'type': 'int', 'nullable': False}],
            'primary_key': [{'columns': ['id'], 'order': 'ASC'}],
            'split_at': [{'value': '10'}, {'value': '20'}]}))
        assert query("SELECT num_tablets FROM yb_table_properties("
                     "'public.rt_ranges'::regclass)") == [(3,)]
        for name in ('rt_orders', 'rt_events', 'rt_ranges'):
            run(client, route, 'table', 'drop', {'confirmation': name},
                target=find(client, route, 'table', name)[0])
        assert not query("SELECT 1 FROM pg_class WHERE relname LIKE "
                         "'rt\\_%'")
    finally:
        query('DROP TABLE IF EXISTS public.rt_orders')
        with connect() as connection:
            connection.execute(f'DROP TABLESPACE IF EXISTS {space}')


def test_index_create_reopen_alter_drop(live):
    route, client = live
    space = f'rt_its_{UNIQUE}'
    with connect() as connection:
        connection.execute(f"CREATE TABLESPACE {space} WITH "
                           f"(replica_placement='{PLACEMENT}')")
    try:
        query('CREATE TABLE public.ix (id INT PRIMARY KEY, a INT, b TEXT, '
              'j JSONB)')
        form = resolved_form('yugabytedb', 'index')
        run(client, route, 'index', 'create', backend_draft(form, {
            'name': 'ix_hash', 'table': 'public.ix',
            'keys': [{'expression': 'a', 'direction': 'HASH'},
                     {'expression': 'b', 'direction': 'HASH'},
                     {'expression': 'id', 'direction': 'ASC'}],
            'storing': [{'value': 'j'}], 'predicate': 'a > 0',
            'split_into': 3, 'tablespace': space, 'comment': 'hashed'}))
        run(client, route, 'index', 'create', backend_draft(form, {
            'name': 'ix_uniq', 'table': 'public.ix', 'unique': True,
            'nulls_not_distinct': True,
            'keys': [{'expression': 'lower(b)', 'direction': 'DESC'}],
            'nonconcurrently': True}))
        run(client, route, 'index', 'create', backend_draft(form, {
            'name': 'ix_gin', 'table': 'public.ix', 'method': 'gin',
            'keys': [{'expression': 'j'}]}))
        assert query("SELECT num_tablets FROM yb_table_properties("
                     "'public.ix_hash'::regclass)") == [(3,)]
        target, baseline = record(client, route, 'index', 'ix_hash',
                                  'index')
        assert ([(row['expression'], row['direction'])
                 for row in baseline['keys']],
                [row['value'] for row in baseline['storing']],
                baseline['predicate'], baseline['tablespace'],
                baseline['comment'], baseline['table']) == (
            [('a', 'HASH'), ('b', 'HASH'), ('id', 'ASC')], ['j'],
            'a > 0', space, 'hashed', 'public.ix')
        _, unique = record(client, route, 'index', 'ix_uniq', 'index')
        assert (unique['unique'], unique['nulls_not_distinct'],
                unique['keys'][0]['expression'],
                unique['keys'][0]['direction']) == (
            True, True, 'lower(b)', 'DESC')
        _, gin = record(client, route, 'index', 'ix_gin', 'index')
        assert gin['method'] == 'gin'
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}
        run(client, route, 'index', 'alter', backend_draft(form, {
            **baseline, 'name': 'ix_hash2', 'tablespace': '',
            'comment': ''}, mode='alter', baseline=baseline),
            target=target)
        _, after = record(client, route, 'index', 'ix_hash2', 'index')
        assert (after['tablespace'], after['comment']) == (None, None)
        assert 'needs a new index' in refused('index', 'alter', {
            'keys': [{'expression': 'a'}]}, target)
        for name in ('ix_hash2', 'ix_uniq', 'ix_gin'):
            run(client, route, 'index', 'drop', {'confirmation': name},
                target=find(client, route, 'index', name)[0])
        assert query("SELECT indexname FROM pg_indexes WHERE "
                     "tablename = 'ix'") == [('ix_pkey',)]
    finally:
        query('DROP TABLE IF EXISTS public.ix')
        with connect() as connection:
            connection.execute(f'DROP TABLESPACE IF EXISTS {space}')


def test_types_and_domains(live):
    route, client = live
    form = resolved_form('yugabytedb', 'type')
    run(client, route, 'type', 'create', backend_draft(form, {
        'name': 'rt_status', 'parent': 'public', 'type_kind': 'ENUM',
        'enum_values': [{'value': 'new'}, {'value': "it's"},
                        {'value': 'done'}], 'comment': 'status'}))
    run(client, route, 'type', 'create', backend_draft(form, {
        'name': 'rt_point', 'parent': 'public', 'type_kind': 'COMPOSITE',
        'fields': [{'name': 'x', 'type': 'int'},
                   {'name': 'label', 'type': 'text'},
                   {'name': 'tags', 'type': 'text[]'},
                   {'name': 'grid', 'type': 'int[][]'}]}))
    run(client, route, 'type', 'create', backend_draft(form, {
        'name': 'rt_span', 'parent': 'public', 'type_kind': 'RANGE',
        'subtype': 'timestamptz', 'subtype_diff': 'tstzrange_subdiff'}))
    run(client, route, 'domain', 'create', backend_draft(form, {
        'variant': 'domain', 'name': 'rt_code', 'parent': 'public',
        'base_type': 'varchar(20)', 'collation': 'C', 'default': "'x'",
        'not_null': True, 'comment': 'a code',
        'checks': [{'name': 'rt_code_len',
                    'expression': 'length(VALUE) > 0'}]}))
    target, baseline = record(client, route, 'type', 'rt_status', 'type')
    assert ([row['value'] for row in baseline['enum_values']],
            baseline['comment'], baseline['type_kind']) == (
        ['new', "it's", 'done'], 'status', 'ENUM')
    _, point = record(client, route, 'type', 'rt_point', 'type')
    # Array fields; like PostgreSQL, YSQL keeps no declared dimensions.
    assert [(row['name'], row['type']) for row in point['fields']] == [
        ('x', 'integer'), ('label', 'text'), ('tags', 'text[]'),
        ('grid', 'integer[]')]
    run(client, route, 'domain', 'create', backend_draft(form, {
        'variant': 'domain', 'name': 'rt_codes', 'parent': 'public',
        'base_type': 'varchar(20)[]'}))
    _, codes = record(client, route, 'domain', 'rt_codes', 'type', 'domain')
    assert codes['base_type'] == 'character varying(20)[]'
    _, span = record(client, route, 'type', 'rt_span', 'type')
    assert (span['type_kind'], span['subtype'], span['subtype_diff']) == (
        'RANGE', 'timestamp with time zone', 'tstzrange_subdiff')
    dtarget, domain = record(client, route, 'domain', 'rt_code', 'type',
                             'domain')
    assert (domain['base_type'], domain['collation'], domain['default'],
            domain['not_null'], domain['comment'],
            [(row['name'], row['expression']) for row in domain['checks']]
            ) == ('character varying(20)', 'C',
                  "'x'::character varying", True, 'a code',
                  [('rt_code_len', '(length((VALUE)::text) > 0)')])
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'type', 'alter', backend_draft(form, {
        **baseline, 'name': 'rt_state',
        'rename_values': [{'from': 'done', 'to': 'closed'}],
        'enum_values': [{'value': 'draft'}, {'value': 'new'},
                        {'value': "it's"}, {'value': 'closed'},
                        {'value': 'archived'}], 'comment': ''},
        mode='alter', baseline=baseline), target=target)
    target, after = record(client, route, 'type', 'rt_state', 'type')
    assert ([row['value'] for row in after['enum_values']],
            after['comment']) == (
        ['draft', 'new', "it's", 'closed', 'archived'], None)
    assert 'cannot be dropped' in refused('type', 'alter', {
        'enum_values': ['draft', 'new']}, target)
    assert 'fixed once created' in refused('type', 'alter', {
        'fields': [{'name': 'z', 'type': 'int'}]},
        find(client, route, 'type', 'rt_point')[0])
    run(client, route, 'domain', 'alter', backend_draft(form, {
        **domain, 'default': '', 'comment': 'code', 'name': 'rt_code2'},
        mode='alter', baseline=domain), target=dtarget)
    _, domain2 = record(client, route, 'domain', 'rt_code2', 'type',
                        'domain')
    assert (domain2['default'], domain2['comment']) == (None, 'code')
    assert 'cannot change' in refused('domain', 'alter', {
        'not_null': False}, find(client, route, 'domain', 'rt_code2')[0])
    for kind, name in (('type', 'rt_state'), ('type', 'rt_point'),
                       ('type', 'rt_span'), ('domain', 'rt_code2'),
                       ('domain', 'rt_codes')):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query("SELECT 1 FROM pg_type WHERE typname LIKE 'rt\\_%'")


def test_views_and_materialized_views(live):
    route, client = live
    query('CREATE TABLE public.vt (id INT PRIMARY KEY, v INT)')
    query('INSERT INTO public.vt VALUES (1, 10)')
    form = resolved_form('yugabytedb', 'view')
    run(client, route, 'view', 'create', backend_draft(form, {
        'name': 'rt_v', 'parent': 'public',
        'query': 'SELECT id, v FROM public.vt',
        'column_names': [{'value': 'a'}, {'value': 'b'}],
        'security_barrier': True, 'comment': 'a view'}))
    run(client, route, 'materialized-view', 'create', backend_draft(form, {
        'variant': 'materialized', 'name': 'rt_m', 'parent': 'public',
        'query': 'SELECT id, v FROM public.vt', 'with_data': False,
        'comment': 'a matview'}))
    target, baseline = record(client, route, 'view', 'rt_v', 'view')
    assert ([row['value'] for row in baseline['column_names']],
            baseline['security_barrier'], baseline['security_invoker'],
            baseline['comment']) == (['a', 'b'], True, False, 'a view')
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'view', 'alter', backend_draft(form, {
        **baseline, 'name': 'rt_v2',
        'column_names': [{'value': 'a2'}, {'value': 'b'}, {'value': 'c'}],
        'query': 'SELECT id, v, v * 2 FROM public.vt',
        'security_invoker': True, 'comment': ''},
        mode='alter', baseline=baseline), target=target)
    assert query('SELECT a2, b, c FROM public.rt_v2') == [(1, 10, 20)]
    _, after = record(client, route, 'view', 'rt_v2', 'view')
    assert (after['security_invoker'], after['comment']) == (True, None)
    mtarget, mat = record(client, route, 'materialized-view', 'rt_m',
                          'view', 'materialized')
    assert (mat['comment'], [row['value'] for row in mat['column_names']]
            ) == ('a matview', ['id', 'v'])
    assert 'cannot change in place' in refused(
        'materialized-view', 'alter', {'query': 'SELECT 1'}, mtarget)
    query('CREATE UNIQUE INDEX rt_m_id ON public.rt_m (id)')
    run(client, route, 'materialized-view', 'refresh', {}, target=mtarget)
    run(client, route, 'materialized-view', 'refresh',
        {'concurrently': True}, target=mtarget)
    assert query('SELECT id, v FROM public.rt_m') == [(1, 10)]
    run(client, route, 'materialized-view', 'alter', {
        'name': 'rt_m2', 'comment': ''}, target=mtarget)
    for kind, name in (('view', 'rt_v2'), ('materialized-view', 'rt_m2')):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query("SELECT 1 FROM pg_class WHERE relname LIKE "
                     "'rt\\_%'")


def test_sequence_create_reopen_alter_drop(live):
    route, client = live
    query('CREATE TABLE public.st (id INT PRIMARY KEY, n INT)')
    form = resolved_form('yugabytedb', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(form, {
        'name': 'rt_seq', 'parent': 'public', 'data_type': 'integer',
        'start': 5, 'increment': 2, 'minimum': 1, 'maximum': 1000,
        'cache': 200, 'cycle': True, 'owned_by': 'public.st.n',
        'comment': 'a sequence'}))
    target, baseline = record(client, route, 'sequence', 'rt_seq',
                              'sequence')
    assert {key: baseline[key] for key in (
        'data_type', 'start', 'increment', 'minimum', 'maximum', 'cache',
        'cycle', 'owned_by', 'comment')} == {
        'data_type': 'integer', 'start': 5, 'increment': 2, 'minimum': 1,
        'maximum': 1000, 'cache': 200, 'cycle': True,
        'owned_by': 'public.st.n', 'comment': 'a sequence'}
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'sequence', 'alter', backend_draft(form, {
        **baseline, 'name': 'rt_seq2', 'data_type': 'bigint',
        'increment': 4, 'maximum': None, 'cycle': False, 'owned_by': '',
        'restart': 100, 'comment': ''}, mode='alter', baseline=baseline),
        target=target)
    target, after = record(client, route, 'sequence', 'rt_seq2', 'sequence')
    assert (after['data_type'], after['increment'], after['maximum'],
            after['cycle'], after['owned_by'], after['comment']) == (
        'bigint', 4, 9223372036854775807, False, None, None)
    assert query("SELECT nextval('public.rt_seq2')") == [(100,)]
    run(client, route, 'sequence', 'drop', {'confirmation': 'rt_seq2'},
        target=target)
    assert not query("SELECT 1 FROM pg_class WHERE relname = 'rt_seq2'")


def test_functions_and_procedures(live):
    route, client = live
    form = resolved_form('yugabytedb', 'routine')
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_add', 'parent': 'public',
        'parameters': [{'name': 'a', 'type': 'integer'},
                       {'name': 'b', 'type': 'integer', 'default': '2'}],
        'returns': 'integer', 'volatility': 'IMMUTABLE', 'strict': True,
        'parallel': 'SAFE', 'cost': 5, 'body': 'SELECT a + b',
        'comment': 'adds'}))
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_add', 'parent': 'public',
        'parameters': [{'mode': 'VARIADIC', 'name': 'xs',
                        'type': 'integer[]'}],
        'returns': 'integer', 'body': 'SELECT array_length(xs, 1)'}))
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_rows', 'parent': 'public',
        'parameters': [{'name': 'n', 'type': 'integer'},
                       {'mode': 'TABLE', 'name': 'k', 'type': 'integer'},
                       {'mode': 'TABLE', 'name': 'v', 'type': 'text'}],
        'rows': 10, 'body': "SELECT g, 'x' FROM generate_series(1, n) g",
        'settings': [{'name': 'search_path', 'value': 'public'}]}))
    run(client, route, 'procedure', 'create', backend_draft(form, {
        'variant': 'procedure', 'name': 'rt_proc', 'parent': 'public',
        'parameters': [{'mode': 'INOUT', 'name': 'n', 'type': 'integer'}],
        'language': 'PLPGSQL', 'security': 'DEFINER',
        'body': 'BEGIN n := n + 1; END'}))
    names = sorted(row['display_name'] for row in resources(client, route)
                   if row['resource_kind'] in {'function', 'procedure'} and
                   row['display_name'].startswith('rt_'))
    assert names == ['rt_add(integer, integer)', 'rt_add(integer[])',
                     'rt_proc(integer)', 'rt_rows(integer)']
    target, baseline = record(client, route, 'function',
                              'rt_add(integer, integer)', 'routine',
                              'function')
    assert ([(row['name'], row['type'], row['default'], row['mode'])
             for row in baseline['parameters']], baseline['returns'],
            baseline['volatility'], baseline['strict'],
            baseline['parallel'], baseline['cost'],
            baseline['comment']) == (
        [('a', 'integer', None, 'IN'), ('b', 'integer', '2', 'IN')],
        'integer', 'IMMUTABLE', True, 'SAFE', 5, 'adds')
    _, rows = record(client, route, 'function', 'rt_rows(integer)',
                     'routine', 'function')
    assert ([(row['mode'], row['name']) for row in rows['parameters']],
            rows['rows'],
            [(row['name'], row['value']) for row in rows['settings']]) == (
        [('IN', 'n'), ('TABLE', 'k'), ('TABLE', 'v')], 10,
        [('search_path', 'public')])
    assert query('SELECT count(*) FROM public.rt_rows(3)') == [(3,)]
    assert query('SELECT public.rt_add(1, 2, 3)') == [(3,)]
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'function', 'alter', backend_draft(form, {
        **baseline, 'body': 'SELECT a * b', 'volatility': 'STABLE',
        'parallel': 'RESTRICTED', 'comment': '', 'name': 'rt_mul'},
        mode='alter', baseline=baseline), target=target)
    assert query('SELECT public.rt_mul(3)') == [(6,)]
    _, after = record(client, route, 'function', 'rt_mul(integer, integer)',
                      'routine', 'function')
    assert (after['volatility'], after['parallel'], after['comment']) == (
        'STABLE', 'RESTRICTED', None)
    assert 'identity' in refused('function', 'alter', {'parameters': []},
                                 find(client, route, 'function',
                                      'rt_mul(integer, integer)')[0])
    _, proc = record(client, route, 'procedure', 'rt_proc(integer)',
                     'routine', 'procedure')
    assert (proc['security'], proc['parameters'][0]['mode']) == (
        'DEFINER', 'INOUT')
    for kind, name in (('function', 'rt_mul(integer, integer)'),
                       ('function', 'rt_add(integer[])'),
                       ('function', 'rt_rows(integer)'),
                       ('procedure', 'rt_proc(integer)')):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query("SELECT 1 FROM pg_proc WHERE proname LIKE 'rt\\_%'")


def test_array_columns(live):
    route, client = live
    form = resolved_form('yugabytedb', 'table')
    run(client, route, 'table', 'create', backend_draft(form, {
        'name': 'rt_arr', 'parent': 'public',
        'columns': [{'name': 'id', 'type': 'int', 'nullable': False},
                    {'name': 'a', 'type': 'int[]'},
                    {'name': 'b', 'type': 'text [3][]'}],
        'primary_key': [{'columns': ['id']}]}))
    target, baseline = record(client, route, 'table', 'rt_arr', 'table')
    columns = by_name(baseline['columns'])
    assert (columns['a']['type'], columns['b']['type']) == (
        'integer[]', 'text[]')
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    changed = [{**row, 'type': 'bigint[]'} if row['name'] == 'a' else row
               for row in baseline['columns']]
    run(client, route, 'table', 'alter', backend_draft(form, {
        **baseline, 'columns': changed}, mode='alter', baseline=baseline),
        target=target)
    _, after = record(client, route, 'table', 'rt_arr', 'table')
    assert by_name(after['columns'])['a']['type'] == 'bigint[]'
    run(client, route, 'table', 'drop', {'confirmation': 'rt_arr'},
        target=target)


def test_databases(live):
    route, client = live
    name, icu, owner = (f'rt_db_{UNIQUE}', f'rt_icu_{UNIQUE}',
                        f'rt_role_{UNIQUE}')
    query(f'CREATE ROLE {owner}', 'yugabyte')
    form = resolved_form('yugabytedb', 'database')
    try:
        run(client, route, 'database', 'create', backend_draft(form, {
            'name': name, 'owner': owner, 'template': 'template0',
            'encoding': 'UTF8', 'collate': 'C', 'ctype': 'C',
            'connection_limit': 5, 'colocation': True, 'comment': 'a db',
            'settings': [{'name': 'work_mem', 'value': '8MB'},
                         {'name': 'search_path', 'value': 'public, x'}]}))
        run(client, route, 'database', 'create', backend_draft(form, {
            'name': icu, 'template': 'template0',
            'locale_provider': 'icu', 'icu_locale': 'en-US'}))
        target, baseline = record(client, route, 'database', name,
                                  'database')
        assert {key: baseline[key] for key in (
            'owner', 'encoding', 'collate', 'ctype', 'connection_limit',
            'allow_connections', 'is_template', 'comment')} == {
            'owner': owner, 'encoding': 'UTF8', 'collate': 'C', 'ctype': 'C',
            'connection_limit': 5, 'allow_connections': True,
            'is_template': False, 'comment': 'a db'}
        assert [(row['name'], row['value'])
                for row in baseline['settings']] == [
            ('work_mem', '8MB'), ('search_path', 'public, x')]
        # Colocation is read only from inside the database itself.
        assert query('SELECT yb_is_database_colocated()', name) == [(True,)]
        _, own = record(client, route, 'database', DATABASE, 'database')
        assert own['colocation'] is False
        _, icu_record = record(client, route, 'database', icu, 'database')
        assert (icu_record['locale_provider'],
                icu_record['icu_locale']) == ('icu', 'en-US')
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}
        run(client, route, 'database', 'alter', backend_draft(form, {
            **baseline, 'name': f'{name}_b', 'owner': SETTINGS['user'],
            'connection_limit': 7, 'allow_connections': False,
            'comment': '',
            'settings': [{'name': 'search_path', 'value': 'x, public'}]},
            mode='alter', baseline=baseline), target=target)
        target, after = record(client, route, 'database', f'{name}_b',
                               'database')
        assert (after['owner'], after['connection_limit'],
                after['allow_connections'], after['comment'],
                [(row['name'], row['value']) for row in after['settings']]
                ) == (SETTINGS['user'], 7, False, None,
                      [('search_path', 'x, public')])
        assert 'cannot change in place' in refused(
            'database', 'alter', {'is_template': True}, target)
        for value in (f'{name}_b', icu):
            run(client, route, 'database', 'drop', {'confirmation': value},
                target=find(client, route, 'database', value)[0])
        assert not query("SELECT 1 FROM pg_database WHERE datname IN "
                         f"('{name}', '{name}_b', '{icu}')", 'yugabyte')
    finally:
        for value in (name, f'{name}_b', icu):
            query(f'DROP DATABASE IF EXISTS {value} WITH (FORCE)',
                  'yugabyte')
        query(f'DROP ROLE IF EXISTS {owner}', 'yugabyte')


def test_row_security_policies(live):
    route, client = live
    reader = f'rt_reader_{UNIQUE}'
    query(f'CREATE ROLE {reader}', 'yugabyte')
    try:
        query('CREATE TABLE public.secured (id INT PRIMARY KEY, '
              'owner TEXT, v INT)')
        query('ALTER TABLE public.secured ENABLE ROW LEVEL SECURITY')
        form = resolved_form('yugabytedb', 'engine_object:row-policy')
        run(client, route, 'row-policy', 'create', backend_draft(form, {
            'name': 'rt_own', 'table': 'public.secured',
            'policy_type': 'PERMISSIVE', 'command': 'ALL',
            'roles': [{'role': reader}],
            'using': 'owner = current_user', 'with_check': 'v > 0',
            'comment': 'own rows'}))
        run(client, route, 'row-policy', 'create', backend_draft(form, {
            'name': 'rt_cap', 'table': 'public.secured',
            'policy_type': 'RESTRICTIVE', 'command': 'SELECT',
            'using': 'v < 100'}))
        target, baseline = record(client, route, 'row-policy', 'rt_own',
                                  'engine_object:row-policy')
        assert (baseline['table'], baseline['policy_type'],
                baseline['command'],
                [row['role'] for row in baseline['roles']],
                baseline['using'], baseline['with_check'],
                baseline['comment']) == (
            'public.secured', 'PERMISSIVE', 'ALL', [reader],
            '(owner = CURRENT_USER)', '(v > 0)', 'own rows')
        _, cap = record(client, route, 'row-policy', 'rt_cap',
                        'engine_object:row-policy')
        assert ([row['role'] for row in cap['roles']], cap['with_check'],
                cap['policy_type']) == (['public'], None, 'RESTRICTIVE')
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}
        assert 'YugabyteDB cannot remove' in refused(
            'row-policy', 'alter', {'with_check': ''}, target)
        run(client, route, 'row-policy', 'alter', backend_draft(form, {
            **baseline, 'name': 'rt_own2', 'roles': [],
            'using': 'v = 1', 'with_check': 'v > 1', 'comment': 'changed'},
            mode='alter', baseline=baseline), target=target)
        target, after = record(client, route, 'row-policy', 'rt_own2',
                               'engine_object:row-policy')
        assert ([row['role'] for row in after['roles']], after['using'],
                after['with_check'], after['comment']) == (
            ['public'], '(v = 1)', '(v > 1)', 'changed')
        run(client, route, 'row-policy', 'alter', {'comment': ''},
            target=target)
        _, after = record(client, route, 'row-policy', 'rt_own2',
                          'engine_object:row-policy')
        assert after['comment'] is None
        assert 'cannot change in place' in refused(
            'row-policy', 'alter', {'command': 'SELECT'}, target)
        for name in ('rt_own2', 'rt_cap'):
            run(client, route, 'row-policy', 'drop', {'confirmation': name},
                target=find(client, route, 'row-policy', name)[0])
        assert not query("SELECT 1 FROM pg_policies WHERE "
                         "tablename = 'secured'")
    finally:
        query('DROP TABLE IF EXISTS public.secured')
        query(f'DROP ROLE IF EXISTS {reader}', 'yugabyte')


def test_placement_tablespaces(live):
    route, client = live
    space, owner = f'rt_space_{UNIQUE}', f'rt_role_{UNIQUE}'
    query(f'CREATE ROLE {owner}', 'yugabyte')
    form = resolved_form('yugabytedb', 'engine_object:tablespace')
    blocks = [{'cloud': 'cloud1', 'region': 'datacenter1', 'zone': 'rack1',
               'min_num_replicas': 1, 'leader_preference': 1}]
    try:
        assert 'exceed the replicas' in refused('tablespace', 'create', {
            'name': space, 'num_replicas': 1, 'placement_blocks': [
                {**blocks[0], 'min_num_replicas': 2}]})
        assert 'without gaps' in refused('tablespace', 'create', {
            'name': space, 'num_replicas': 1, 'placement_blocks': [
                {**blocks[0], 'leader_preference': 2}]})
        run(client, route, 'tablespace', 'create', backend_draft(form, {
            'name': space, 'owner': owner, 'comment': 'a space',
            'num_replicas': 1, 'placement_blocks': blocks}))
        target, baseline = record(client, route, 'tablespace', space,
                                  'engine_object:tablespace')
        assert (baseline['owner'], baseline['comment'],
                baseline['num_replicas'],
                [{key: value for key, value in row.items() if key != '_id'}
                 for row in baseline['placement_blocks']]) == (
            owner, 'a space', 1, blocks)
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}
        query(f'CREATE TABLE public.placed (id INT PRIMARY KEY) '
              f'TABLESPACE {space}')
        run(client, route, 'tablespace', 'alter', backend_draft(form, {
            **baseline, 'owner': SETTINGS['user'], 'comment': ''},
            mode='alter', baseline=baseline), target=target)
        target, after = record(client, route, 'tablespace', space,
                               'engine_object:tablespace')
        assert (after['owner'], after['comment']) == (SETTINGS['user'], None)
        assert 'does not alter' in refused('tablespace', 'alter', {
            'num_replicas': 3}, target)
        query('DROP TABLE public.placed')
        run(client, route, 'tablespace', 'drop', {'confirmation': space},
            target=target)
        assert not query("SELECT 1 FROM pg_tablespace WHERE spcname = "
                         f"'{space}'", 'yugabyte')
    finally:
        query('DROP TABLE IF EXISTS public.placed')
        query(f'DROP TABLESPACE IF EXISTS {space}', 'yugabyte')
        query(f'DROP ROLE IF EXISTS {owner}', 'yugabyte')


def test_extensions(live):
    route, client = live
    form = resolved_form('yugabytedb', 'engine_object:extension')
    query('CREATE SCHEMA ext')
    run(client, route, 'extension', 'create', backend_draft(form, {
        'name': 'hstore', 'schema': 'ext', 'version': '1.5',
        'comment': 'key-value'}))
    run(client, route, 'extension', 'create', backend_draft(form, {
        'name': 'earthdistance', 'cascade': True}))
    target, baseline = record(client, route, 'extension', 'hstore',
                              'engine_object:extension')
    assert (baseline['schema'], baseline['version'],
            baseline['comment']) == ('ext', '1.5', 'key-value')
    assert target['native']['update_versions'] == ['1.5-yb-1.0',
                                                   '1.8-yb-1.0']
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    assert 'no update path' in refused('extension', 'alter', {
        'version': '1.4'}, target)
    run(client, route, 'extension', 'alter', backend_draft(form, {
        **baseline, 'version': '1.8-yb-1.0', 'schema': 'public',
        'comment': ''}, mode='alter', baseline=baseline), target=target)
    target, after = record(client, route, 'extension', 'hstore',
                           'engine_object:extension')
    assert (after['schema'], after['version'], after['comment']) == (
        'public', '1.8-yb-1.0', None)
    assert query("SELECT 'a=>1'::hstore -> 'a'") == [('1',)]
    assert {'cube', 'earthdistance'} <= {
        row['display_name'] for row in resources(client, route)
        if row['resource_kind'] == 'extension'}
    for name in ('earthdistance', 'cube', 'hstore'):
        run(client, route, 'extension', 'drop', {'confirmation': name},
            target=find(client, route, 'extension', name)[0])
    assert not query("SELECT 1 FROM pg_extension WHERE extname IN "
                     "('hstore', 'cube', 'earthdistance')")
    query('DROP SCHEMA ext')


def test_ddl_mode_detected_and_plans_atomic(live):
    """The demo enables ysql_yb_ddl_transaction_block_enabled."""
    route, client = live
    resources(client, route)  # the catalog read records the server's mode
    request = {'resource_kind': 'sequence', 'operation_id': 'create',
               'target_resource': None, '_provider_route': route,
               'draft': {'name': 'rt_atomic', 'parent': 'public',
                         'comment': 'c'}}
    planned = ADMINISTRATION.plan(request)
    compiled = planned['provider_payload']['compiled']
    assert compiled['ddl_transaction_mode'] == 'atomic'
    assert not compiled.get('warnings')
    # The second statement fails: the first must not stay applied.
    compiled['statements'][1]['source'] = (
        "COMMENT ON SEQUENCE public.rt_absent IS 'x'")
    with pytest.raises(Exception) as failure:
        ADMINISTRATION.apply(client, executor_request(request, planned))
    assert 'stay applied' not in str(failure.value)
    assert not query("SELECT 1 FROM pg_class WHERE relname = 'rt_atomic'")
    result = run(client, route, 'sequence', 'create', request['draft'])
    assert result['provider_payload']['compiled'][
        'ddl_transaction_mode'] == 'atomic'
    query('DROP SEQUENCE public.rt_atomic')


def operate(client, route, kind, operation, values, target,
            confirmation=None):
    """Run an operation from its descriptor, as the OperationDialog does."""
    declared = engine_operations('yugabytedb')[f'{operation}@{kind}']
    return run(client, route, kind, operation, operation_backend_draft(
        declared, operation_draft(declared, values, confirmation)),
        target=target)


def confirmed_drop(client, route, kind, target):
    """A control-plane delete has no form fields: the UI sends an empty
    draft and visual administration refuses to apply it unconfirmed."""
    operation = next(
        item for resource in PROVIDERS[0].visual_admin_descriptor()['objects']
        if resource['resource_kind'] == kind
        for item in resource['operations'] if item['operation_id'] == 'drop')
    assert (operation['mutation_class'], operation['confirmation_required'],
            operation['form']['fields']) == ('destructive', True, [])
    return run(client, route, kind, 'drop', {}, target=target)


def until(check, timeout=120, interval=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
        except psycopg.Error:
            # A restore restarts the tablets ("aborted pending operations").
            value = None
        if value:
            return value
        time.sleep(interval)
    raise AssertionError('condition not reached in time')


def admin(*arguments):
    return subprocess.run(
        [str(YB_ADMIN), '--master_addresses',
         live_masters(), *arguments],
        capture_output=True, text=True, check=True).stdout


def live_masters():
    sys.path.insert(0, str(ROOT / 'tools/reference_engine_demos'))
    from demo_estate import yugabyte_master_addresses
    return yugabyte_master_addresses()


def test_control_plane_operations(live):
    """The yb-admin operations a one-node demo can carry out and show."""
    route, client = live
    if 'yb_admin_path' not in route:
        pytest.skip('demo yb-admin wrapper is not written')

    def one(kind):
        return [row for row in resources(client, route)
                if row['resource_kind'] == kind]
    query('CREATE TABLE public.ops (id INT PRIMARY KEY, v TEXT) '
          'SPLIT INTO 1 TABLETS')
    query("INSERT INTO public.ops SELECT g, repeat('x', 200) "
          'FROM generate_series(1, 50000) g')
    table = find(client, route, 'table', 'ops')[0]
    # Load balancer off and on again.
    # One cluster record: the SQL catalog's and yb-admin's are merged.
    clusters = one('cluster')
    assert [row['resource_id'] for row in clusters] == ['cluster:YugabyteDB']
    cluster = clusters[0]
    assert 'raw' in cluster['native']
    operate(client, route, 'cluster', 'set_load_balancer',
            {'enabled': False}, cluster)
    assert 'DISABLED' in admin('get_load_balancer_state')
    operate(client, route, 'cluster', 'set_load_balancer',
            {'enabled': True}, cluster)
    assert 'ENABLED' in admin('get_load_balancer_state')
    # Flush, then a split the master carries out; then compact.
    operate(client, route, 'table', 'flush', {'timeout_seconds': 60},
            table)
    tablets = [row for row in one('tablet')
               if (row.get('native') or {}).get('table') == 'ops']
    assert len(tablets) == 1
    operate(client, route, 'tablet', 'split', {}, tablets[0])
    until(lambda: len([row for row in one('tablet') if (
        row.get('native') or {}).get('table') == 'ops']) == 2, 180, 5)
    operate(client, route, 'table', 'compact', {'timeout_seconds': 60},
            table)
    # Move the table onto a placement tablespace.
    space = f'rt_opsts_{UNIQUE}'
    with connect() as connection:
        connection.execute(f"CREATE TABLESPACE {space} WITH "
                           f"(replica_placement='{PLACEMENT}')")
    operate(client, route, 'table', 'configure_placement',
            {'tablespace': space}, table)
    assert query("SELECT s.spcname FROM pg_class c JOIN pg_tablespace s "
                 "ON s.oid = c.reltablespace WHERE c.relname = 'ops'") == [
        (space,)]
    # Live placement restated as it is (one node: cloud1.datacenter1.rack1).
    policy = one('placement-policy')[0]
    held = policy['native']['liveReplicas']
    operate(client, route, 'placement-policy', 'configure', {
        'placements': [{'cloud': 'cloud1', 'region': 'datacenter1',
                        'zone': 'rack1', 'min_num_replicas': 1}],
        'replication_factor': 1}, policy)
    assert one('placement-policy')[0]['native']['liveReplicas'][
        'placementBlocks'] == held['placementBlocks']
    # A database snapshot, restored after a delete, then removed. Only the
    # snapshot made here is restored: one a failed earlier run left behind
    # predates this run's tables and cannot restore them.
    earlier = {row['resource_id'] for row in one('snapshot')}
    operate(client, route, 'snapshot', 'create_database', {
        'database': DATABASE, 'retention_hours': 1}, None)
    snapshot = until(lambda: next((
        row for row in one('snapshot')
        if row['resource_id'] not in earlier and
        (row.get('native') or {}).get('state') == 'COMPLETE'), None))
    query('DELETE FROM public.ops WHERE id > 100')
    operate(client, route, 'snapshot', 'restore', {}, snapshot,
            confirmation=snapshot['display_name'])
    until(lambda: query('SELECT count(*) FROM public.ops') == [(50000,)])
    confirmed_drop(client, route, 'snapshot', snapshot)
    assert not [row for row in one('snapshot')
                if row['display_name'] == snapshot['display_name']]
    # A snapshot schedule through its form: create, alter, drop.
    form = resolved_form('yugabytedb', 'engine_object:schedule')
    run(client, route, 'schedule', 'create', backend_draft(form, {
        'namespace': DATABASE, 'namespace_type': 'ysql',
        'interval_minutes': 60, 'retention_minutes': 120}))
    schedule = until(lambda: next((
        row for row in one('schedule')
        if (row.get('native') or {}).get('options', {}).get('filter') ==
        f'ysql.{DATABASE}'), None))
    _, baseline = record(client, route, 'schedule', schedule['display_name'],
                         'engine_object:schedule')
    assert (baseline['namespace'], baseline['namespace_type'],
            baseline['interval_minutes'], baseline['retention_minutes']) == (
        DATABASE, 'ysql', 60, 120)
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'schedule', 'alter', backend_draft(form, {
        **baseline, 'interval_minutes': 30}, mode='alter',
        baseline=baseline), target=schedule)
    _, after = record(client, route, 'schedule', schedule['display_name'],
                      'engine_object:schedule')
    assert after['interval_minutes'] == 30
    # Point-in-time restore from the schedule's snapshots.
    until(lambda: next(row for row in one('schedule') if row[
        'resource_id'] == schedule['resource_id'])['native'].get('snapshots'))
    time.sleep(2)
    moment = query("SELECT to_char(now() AT TIME ZONE 'UTC', "
                   "'YYYY-MM-DD HH24:MI:SS')")[0][0]
    time.sleep(2)
    query('DELETE FROM public.ops WHERE id > 10')
    operate(client, route, 'schedule', 'restore',
            {'restore_timestamp': moment}, schedule,
            confirmation=schedule['display_name'])
    until(lambda: query('SELECT count(*) FROM public.ops') == [(50000,)])
    confirmed_drop(client, route, 'schedule', schedule)
    # A CDCSDK stream through its form: create, drop.
    form = resolved_form('yugabytedb', 'engine_object:changefeed')
    before = {row['resource_id'] for row in one('changefeed')}
    run(client, route, 'changefeed', 'create', backend_draft(form, {
        'namespace': DATABASE, 'namespace_type': 'ysql',
        'record_type': 'ALL', 'snapshot_mode': 'NOEXPORT_SNAPSHOT',
        'dynamic_tables': False}))
    stream = until(lambda: next((row for row in one('changefeed')
                                 if row['resource_id'] not in before), None))
    assert {key: stream['native'][key] for key in (
        'checkpoint_type', 'record_type', 'snapshot_mode',
        'dynamic_tables')} == {
        'checkpoint_type': 'EXPLICIT', 'record_type': 'ALL',
        'snapshot_mode': 'NOEXPORT_SNAPSHOT', 'dynamic_tables': False}
    # Live: "Stream creation with IMPLICIT checkpointing is disabled".
    assert 'IMPLICIT checkpointing is disabled' in str(pytest.raises(
        Exception, run, client, route, 'changefeed', 'create', {
            'namespace': DATABASE, 'checkpoint_type': 'IMPLICIT'}).value)
    confirmed_drop(client, route, 'changefeed', stream)
    # A dropped stream can stay listed while its metadata is deleted.
    assert all((row.get('native') or {}).get('state', '').startswith(
        'DELETING') for row in one('changefeed')
        if row['resource_id'] == stream['resource_id'])
    # A bare YSQL name is sent as ysql.<name>; a missing one says why.
    assert 'not found' in str(pytest.raises(
        Exception, run, client, route, 'schedule', 'create', {
            'namespace': 'rt_no_such_db', 'interval_minutes': 60,
            'retention_minutes': 120}).value)
    query('DROP TABLE public.ops')
    with connect() as connection:
        connection.execute(f'DROP TABLESPACE {space}')


# Native administration added 2026-11-01 (providers/pgwire_administration).
# Each operation goes through the UI path, must be confirmed by the
# provider's own read-back, and is then read back again here.

ADMIN = 'yugabyte'
ADMIN_DATABASE = 'yugabyte'
DATABASE_PRIVILEGES = ['CONNECT', 'CREATE', 'TEMPORARY']
ANALYZED = ("SELECT last_analyze IS NOT NULL FROM "
            "pg_catalog.pg_stat_user_tables WHERE schemaname = '{schema}' "
            "AND relname = '{table}'")


def held(kind, path, role):
    source = {
        'database': ("pg_catalog.pg_database o", "o.datacl",
                     f"o.datname = '{path[0]}'"),
        'schema': ("pg_catalog.pg_namespace o", "o.nspacl",
                   f"o.nspname = '{path[0]}'"),
        'type': ("pg_catalog.pg_type o JOIN pg_catalog.pg_namespace n ON "
                 "n.oid = o.typnamespace", "o.typacl",
                 f"n.nspname = '{path[0]}' AND o.typname = '{path[-1]}'"),
    }[kind]
    return {(name, bool(grantable)) for name, grantable in query(
        f'SELECT a.privilege_type, a.is_grantable FROM {source[0]} CROSS '
        f'JOIN LATERAL aclexplode({source[1]}) a JOIN pg_catalog.pg_roles r '
        f"ON r.oid = a.grantee WHERE {source[2]} AND r.rolname = '{role}'")}


def SESSION_ID(connection):
    return str(connection.execute('SELECT pg_backend_pid()').fetchone()[0])


def SESSION_BUSY(session):
    return query('SELECT state FROM pg_catalog.pg_stat_activity '
                 f'WHERE pid = {int(session)}') == [('active',)]


def control(client, route, kind, operation, draft, target):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, '_provider_route': route,
               'draft': draft}
    run(client, route, kind, operation, draft, target)
    planned = ADMINISTRATION.plan(request)
    state = ADMINISTRATION.validate_operation_post_state(
        client, executor_request(request, planned))
    assert state['confirmed'], state


NATIVE_ROLE = f'rt_native_role_{UNIQUE}'
NATIVE_USER = f'rt_native_user_{UNIQUE}'


def ensure_role(name, login=False):
    if not query(f"SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = "
                 f"'{name}'", database=ADMIN_DATABASE):
        query(f'CREATE ROLE {name}{" LOGIN" if login else ""}',
              database=ADMIN_DATABASE)


def native_row(client, route, kind, path):
    found = [row for row in resources(client, route)
             if row['resource_kind'] == kind and row['display_path'] == path]
    assert len(found) == 1, (kind, path, len(found))
    return found[0]


def test_native_table_maintenance_schema_and_owner(live):
    route, client = live
    query('CREATE TABLE public.rt_m (id INT PRIMARY KEY, v INT)')
    query('INSERT INTO public.rt_m VALUES (1, 1), (2, 2)')
    target = native_row(client, route, 'table', ['public', 'rt_m'])
    control(client, route, 'table', 'truncate', {'cascade': False}, target)
    assert query('SELECT count(*) FROM public.rt_m') == [(0,)]
    query('INSERT INTO public.rt_m VALUES (1, 1), (2, 2)')
    control(client, route, 'table', 'analyze', {}, target)
    assert query(ANALYZED.format(schema='public', table='rt_m')) == [(True,)]
    query('CREATE SCHEMA rt_s')
    control(client, route, 'table', 'set_schema', {'schema': 'rt_s'},
            target)
    assert query("SELECT table_schema FROM information_schema.tables "
                 "WHERE table_name = 'rt_m'") == [('rt_s',)]
    moved = native_row(client, route, 'table', ['rt_s', 'rt_m'])
    ensure_role(NATIVE_ROLE)
    # The new owner needs CREATE on the table's schema (CockroachDB refuses
    # otherwise; a superuser in YugabyteDB is not checked).
    query(f'GRANT CREATE ON SCHEMA rt_s TO {NATIVE_ROLE}')
    control(client, route, 'table', 'set_owner', {'owner': NATIVE_ROLE},
            moved)
    assert query("SELECT tableowner FROM pg_catalog.pg_tables WHERE "
                 "schemaname = 'rt_s' AND tablename = 'rt_m'") == [
        (NATIVE_ROLE,)]
    control(client, route, 'table', 'set_owner', {'owner': ADMIN}, moved)


def test_native_constraint_validation(live):
    route, client = live
    query('CREATE TABLE public.rt_c (id INT PRIMARY KEY, v INT)')
    query('ALTER TABLE public.rt_c ADD CONSTRAINT rt_ck CHECK (v > 0) '
          'NOT VALID')
    validated = ("SELECT c.convalidated FROM pg_catalog.pg_constraint c "
                 "JOIN pg_catalog.pg_class t ON t.oid = c.conrelid "
                 "WHERE t.relname = 'rt_c' AND c.conname = 'rt_ck'")
    assert query(validated) == [(False,)]
    control(client, route, 'constraint', 'validate', {}, native_row(
        client, route, 'constraint', ['public', 'rt_c', 'rt_ck']))
    assert query(validated) == [(True,)]


def test_native_default_settings(live):
    route, client = live
    role = NATIVE_USER
    ensure_role(role, login=True)

    def settings(role_name, database):
        return [entry for row in query(
            'SELECT s.setconfig FROM pg_catalog.pg_db_role_setting s '
            'LEFT JOIN pg_catalog.pg_roles r ON r.oid = s.setrole '
            'LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase '
            f"WHERE coalesce(r.rolname, '') = '{role_name}' "
            f"AND coalesce(d.datname, '') = '{database}'") for entry in row[0]]
    principal = native_row(client, route, 'user', [role])
    control(client, route, 'user', 'set_setting',
            {'setting': 'statement_timeout', 'value': '9s'}, principal)
    assert settings(role, '') == ['statement_timeout=9s']
    control(client, route, 'user', 'set_setting', {
        'setting': 'search_path', 'value': 'public', 'database': DATABASE},
        principal)
    assert settings(role, DATABASE) == ['search_path=public']
    control(client, route, 'user', 'reset_setting',
            {'setting': 'statement_timeout'}, principal)
    assert settings(role, '') == []
    control(client, route, 'user', 'reset_setting', {
        'setting': 'search_path', 'database': DATABASE}, principal)
    assert settings(role, DATABASE) == []


def test_native_database_schema_and_type_grants(live):
    route, client = live
    role = NATIVE_ROLE
    ensure_role(role)
    query('CREATE SCHEMA IF NOT EXISTS rt_g')
    query("CREATE TYPE rt_g.rt_ty AS ENUM ('x')")
    for kind, path, privileges in (
            ('database', [DATABASE], DATABASE_PRIVILEGES),
            ('schema', ['rt_g'], ['CREATE', 'USAGE']),
            ('type', ['rt_g', 'rt_ty'], ['USAGE'])):
        target = native_row(client, route, kind, path)
        control(client, route, kind, 'grant', {
            'principal': role, 'privileges': privileges,
            'grant_option': True}, target)
        assert held(kind, path, role) == {
            (privilege, True) for privilege in privileges}, kind
        control(client, route, kind, 'revoke', {
            'principal': role, 'privileges': privileges}, target)
        assert not {name for name, _ in held(kind, path, role)} & set(
            privileges), kind


def test_native_session_cancel_and_terminate(live):
    import threading
    route, client = live
    victim = connect(DATABASE)
    session = SESSION_ID(victim)
    outcome = []

    def sleep():
        try:
            # Long enough that the cancel, not the sleep, ends it even
            # where listing the catalog is slow (YugabyteDB).
            victim.execute('SELECT pg_sleep(600)')
            outcome.append('finished')
        except Exception as error:
            outcome.append(type(error).__name__)
    worker = threading.Thread(target=sleep)
    worker.start()
    try:
        # Poll the session directly: a full catalog listing per poll is
        # slow on YugabyteDB.
        for _attempt in range(100):
            if SESSION_BUSY(session):
                break
            time.sleep(0.1)
        control(client, route, 'session', 'terminate_query', {},
                native_row(client, route, 'session', [session]))
        worker.join(10)
        assert not worker.is_alive() and outcome == ['QueryCanceled'], \
            outcome
        control(client, route, 'session', 'terminate_connection', {},
                native_row(client, route, 'session', [session]))
        assert not [row for row in resources(client, route)
                    if row['resource_kind'] == 'session' and
                    row['display_path'] == [session]]
    finally:
        worker.join(30)
        try:
            victim.cancel()
            victim.close()
        except Exception:
            pass


def test_native_partitions_create_attach_detach(live):
    route, client = live
    query('CREATE TABLE public.rt_pr (id INT, k INT, PRIMARY KEY (id, k)) '
          'PARTITION BY RANGE (k)')
    query('CREATE TABLE public.rt_pl (id INT, c TEXT, PRIMARY KEY (id, c)) '
          'PARTITION BY LIST (c)')
    query('CREATE TABLE public.rt_ph (id INT PRIMARY KEY) '
          'PARTITION BY HASH (id)')
    query('CREATE TABLE public.rt_loose (id INT, k INT, PRIMARY KEY (id, k))')
    rows = resources(client, route)

    def table(name):
        return next(row for row in rows if row['resource_kind'] == 'table'
                    and row['display_path'] == ['public', name])

    def bound(child):
        return query(
            'SELECT pc.relname, pg_catalog.pg_get_expr(cc.relpartbound, '
            'cc.oid) FROM pg_catalog.pg_class cc LEFT JOIN '
            'pg_catalog.pg_inherits i ON i.inhrelid = cc.oid LEFT JOIN '
            'pg_catalog.pg_class pc ON pc.oid = i.inhparent '
            f"WHERE cc.relname = '{child}'")
    control(client, route, 'table', 'create_partition', {
        'name': 'rt_pr_lo', 'bound': 'RANGE', 'from_mode': 'MINVALUE',
        'to_mode': 'VALUE', 'to_value': '10'}, table('rt_pr'))
    assert bound('rt_pr_lo') == [
        ('rt_pr', 'FOR VALUES FROM (MINVALUE) TO (10)')]
    control(client, route, 'table', 'create_partition', {
        'name': 'rt_pr_rest', 'bound': 'DEFAULT'}, table('rt_pr'))
    assert bound('rt_pr_rest') == [('rt_pr', 'DEFAULT')]
    control(client, route, 'table', 'attach_partition', {
        'table': 'rt_loose', 'bound': 'RANGE', 'from_value': '10',
        'to_value': '20'}, table('rt_pr'))
    assert bound('rt_loose') == [('rt_pr', 'FOR VALUES FROM (10) TO (20)')]
    control(client, route, 'table', 'create_partition', {
        'name': 'rt_pl_ab', 'bound': 'LIST',
        'in_values': [{'value': 'a'}, {'value': "b'c"}]}, table('rt_pl'))
    assert bound('rt_pl_ab') == [('rt_pl', "FOR VALUES IN ('a', 'b''c')")]
    control(client, route, 'table', 'create_partition', {
        'name': 'rt_ph_0', 'bound': 'HASH', 'modulus': 2, 'remainder': 0},
        table('rt_ph'))
    assert bound('rt_ph_0') == [
        ('rt_ph', 'FOR VALUES WITH (modulus 2, remainder 0)')]
    partition = next(
        row for row in resources(client, route)
        if row['resource_kind'] == 'partition' and
        row['display_path'] == ['public', 'rt_pr', 'rt_loose'])
    control(client, route, 'partition', 'detach', {}, partition)
    assert bound('rt_loose') == [(None, None)]


def test_event_triggers_rules_collations_publications(live):
    """2026-11-01: four kinds YugabyteDB YSQL runs that had no editor."""
    route, client = live
    trigger_form = resolved_form('yugabytedb', 'trigger')
    query('CREATE FUNCTION public.rt_evt() RETURNS event_trigger '
          'LANGUAGE plpgsql AS $$ BEGIN END $$')
    query('CREATE TABLE public.rt_ruled (id INT PRIMARY KEY, v INT)')
    query('CREATE TABLE public.rt_log (id INT)')
    # Publications need a primary key ("cannot be replicated" otherwise).
    query('CREATE TABLE public.rt_pubbed (id INT PRIMARY KEY)')
    try:
        run(client, route, 'event-trigger', 'create', backend_draft(
            trigger_form, {
                'variant': 'event', 'name': 'rt_et',
                'event': 'ddl_command_end',
                'function': ['public', 'rt_evt()'],
                'tags': ['CREATE TABLE'], 'enabled': 'REPLICA',
                'comment': 'rt event'}))
        assert query(
            "SELECT evtevent, evtenabled, evttags, obj_description(oid, "
            "'pg_event_trigger') FROM pg_event_trigger WHERE evtname = "
            "'rt_et'") == [('ddl_command_end', 'R', ['CREATE TABLE'],
                            'rt event')]
        target, baseline = record(client, route, 'event-trigger', 'rt_et',
                                  'trigger', variant='event')
        # The editor shows a string grid as rows.
        assert (baseline['event'], [row['value'] for row in baseline['tags']],
                baseline['enabled']) == (
            'ddl_command_end', ['CREATE TABLE'], 'REPLICA')
        run(client, route, 'event-trigger', 'alter', backend_draft(
            trigger_form, {**baseline, 'name': 'rt_et2',
                           'enabled': 'DISABLED'}, mode='alter',
            baseline=baseline), target=target)
        assert query("SELECT evtenabled FROM pg_event_trigger WHERE "
                     "evtname = 'rt_et2'") == [('D',)]
        run(client, route, 'event-trigger', 'drop', {'confirmation': 'x'},
            target=find(client, route, 'event-trigger', 'rt_et2')[0])
        assert not query("SELECT 1 FROM pg_event_trigger")

        rule_form = resolved_form('yugabytedb', 'engine_object:rule')
        run(client, route, 'rule', 'create', backend_draft(rule_form, {
            'name': 'rt_rule', 'table': ['public', 'rt_ruled'],
            'event': 'INSERT', 'condition': 'NEW.v > 10', 'instead': False,
            'actions': 'INSERT INTO public.rt_log VALUES (NEW.id)',
            'comment': 'rt rule'}))
        query('INSERT INTO public.rt_ruled VALUES (1, 5), (2, 50)')
        assert query('SELECT id FROM public.rt_log') == [(2,)]
        target, baseline = record(client, route, 'rule', 'rt_rule',
                                  'engine_object:rule')
        assert (baseline['event'], baseline['condition'],
                baseline['instead'], baseline['comment']) == (
            'INSERT', 'new.v > 10', False, 'rt rule')
        assert backend_draft(rule_form, baseline, mode='alter',
                             baseline=baseline) == {}
        run(client, route, 'rule', 'alter', backend_draft(rule_form, {
            **baseline, 'instead': True, 'actions': ''}, mode='alter',
            baseline=baseline), target=target)
        query('INSERT INTO public.rt_ruled VALUES (3, 99)')
        assert query('SELECT count(*) FROM public.rt_ruled') == [(2,)]
        assert 'rename' in refused('rule', 'alter', {'name': 'rt_rule2'},
                                   target).lower()
        run(client, route, 'rule', 'drop', {'confirmation': 'rt_rule'},
            target=find(client, route, 'rule', 'rt_rule')[0])
        assert not query("SELECT 1 FROM pg_rules WHERE rulename = "
                         "'rt_rule'")

        collation_form = resolved_form('yugabytedb',
                                       'engine_object:collation')
        run(client, route, 'collation', 'create', backend_draft(
            collation_form, {'name': 'rt_coll', 'parent': 'public',
                             'provider': 'icu', 'locale': 'de-DE'}))
        target, baseline = record(client, route, 'collation', 'rt_coll',
                                  'engine_object:collation')
        assert (baseline['provider'], baseline['locale']) == ('icu',
                                                              'de-DE')
        query('CREATE SCHEMA rt_cs')
        run(client, route, 'collation', 'alter', backend_draft(
            collation_form, {**baseline, 'name': 'rt_coll2',
                             'parent': 'rt_cs', 'comment': 'rt coll'},
            mode='alter', baseline=baseline), target=target)
        assert query(
            "SELECT n.nspname, obj_description(c.oid, 'pg_collation') FROM "
            "pg_collation c JOIN pg_namespace n ON n.oid = c.collnamespace "
            "WHERE c.collname = 'rt_coll2'") == [('rt_cs', 'rt coll')]
        run(client, route, 'collation', 'drop', {'confirmation': 'x'},
            target=find(client, route, 'collation', 'rt_coll2')[0])

        publication_form = resolved_form('yugabytedb',
                                         'engine_object:publication')
        run(client, route, 'publication', 'create', backend_draft(
            publication_form, {'name': 'rt_pub',
                               'tables': ['public.rt_ruled']}))
        target, baseline = record(client, route, 'publication', 'rt_pub',
                                  'engine_object:publication')
        assert [row['value'] for row in baseline['tables']] == [
            'public.rt_ruled']
        run(client, route, 'publication', 'alter', backend_draft(
            publication_form, {**baseline, 'name': 'rt_pub2',
                               'tables': ['public.rt_ruled',
                                          'public.rt_pubbed']},
            mode='alter', baseline=baseline), target=target)
        assert sorted(query(
            "SELECT tablename FROM pg_publication_tables WHERE pubname = "
            "'rt_pub2'")) == [('rt_pubbed',), ('rt_ruled',)]
        run(client, route, 'publication', 'drop', {'confirmation': 'x'},
            target=find(client, route, 'publication', 'rt_pub2')[0])
        assert not query("SELECT 1 FROM pg_publication")
    finally:
        for statement in ('DROP EVENT TRIGGER IF EXISTS rt_et',
                          'DROP EVENT TRIGGER IF EXISTS rt_et2',
                          'DROP PUBLICATION IF EXISTS rt_pub',
                          'DROP PUBLICATION IF EXISTS rt_pub2'):
            query(statement)


def test_aggregates_operators_and_casts(live):
    """2026-11-01: aggregates (routine family), operators and casts."""
    route, client = live
    routine_form = resolved_form('yugabytedb', 'routine')
    query('CREATE FUNCTION public.rt_double(int) RETURNS int LANGUAGE sql '
          'IMMUTABLE AS $$ SELECT $1 * 2 $$')
    query("CREATE TYPE public.rt_mood AS ENUM ('calm', 'busy')")
    query('CREATE FUNCTION public.rt_mood_int(public.rt_mood) RETURNS int '
          'LANGUAGE sql IMMUTABLE AS $$ SELECT 1 $$')
    run(client, route, 'aggregate', 'create', backend_draft(routine_form, {
        'variant': 'aggregate', 'name': 'rt_agg', 'parent': 'public',
        'parameters': [{'name': '', 'type': 'int'}],
        'state_function': ['pg_catalog', 'int4pl(integer, integer)'],
        'state_type': 'int',
        'final_function': ['public', 'rt_double(integer)'],
        'initial_condition': '0', 'parallel': 'SAFE',
        'comment': 'rt aggregate'}))
    assert query('SELECT public.rt_agg(x) FROM generate_series(1, 3) x') == [
        (12,)]
    target, baseline = record(client, route, 'aggregate', 'rt_agg(integer)',
                              'routine', variant='aggregate')
    assert (baseline['state_function'], baseline['initial_condition'],
            baseline['comment']) == ('int4pl', '0', 'rt aggregate')
    run(client, route, 'aggregate', 'alter', backend_draft(routine_form, {
        **baseline, 'initial_condition': '5', 'final_function': None},
        mode='alter', baseline=baseline), target=target)
    assert query('SELECT public.rt_agg(x) FROM generate_series(1, 3) x') == [
        (11,)]
    run(client, route, 'aggregate', 'drop', {'confirmation': 'x'},
        target=find(client, route, 'aggregate', 'rt_agg(integer)')[0])
    assert not query("SELECT 1 FROM pg_proc WHERE proname = 'rt_agg'")

    operator_form = resolved_form('yugabytedb', 'engine_object:operator')
    run(client, route, 'operator', 'create', backend_draft(operator_form, {
        'name': '===', 'parent': 'public', 'left_type': 'int',
        'right_type': 'int', 'function': ['pg_catalog', 'int4eq'],
        'commutator': '===', 'restrict': 'eqsel', 'join': 'eqjoinsel',
        'hashes': False, 'merges': False}))
    assert query('SELECT 2 OPERATOR(public.===) 2') == [(True,)]
    target, baseline = record(client, route, 'operator',
                              '===(integer, integer)',
                              'engine_object:operator')
    assert (baseline['function'], baseline['restrict'],
            baseline['commutator']) == ('int4eq', 'eqsel', '===')
    query('CREATE SCHEMA rt_ops')
    run(client, route, 'operator', 'alter', backend_draft(operator_form, {
        **baseline, 'restrict': '', 'join': '', 'parent': 'rt_ops',
        'comment': 'rt op'}, mode='alter', baseline=baseline), target=target)
    assert query(
        "SELECT n.nspname, o.oprrest::regproc::text, obj_description(o.oid, "
        "'pg_operator') FROM pg_operator o JOIN pg_namespace n ON n.oid = "
        "o.oprnamespace WHERE o.oprname = '==='") == [('rt_ops', '-',
                                                      'rt op')]
    run(client, route, 'operator', 'drop', {'confirmation': 'x'},
        target=find(client, route, 'operator', '===(integer, integer)')[0])

    cast_form = resolved_form('yugabytedb', 'engine_object:cast')
    run(client, route, 'cast', 'create', backend_draft(cast_form, {
        'source_type': 'public.rt_mood', 'target_type': 'int',
        'method': 'FUNCTION', 'function': ['public', 'rt_mood_int(rt_mood)'],
        'context': 'ASSIGNMENT'}))
    assert query("SELECT 'busy'::public.rt_mood::int") == [(1,)]
    target, baseline = record(client, route, 'cast', 'rt_mood AS integer',
                              'engine_object:cast')
    assert (baseline['method'], baseline['context']) == ('FUNCTION',
                                                         'ASSIGNMENT')
    run(client, route, 'cast', 'alter', backend_draft(cast_form, {
        **baseline, 'comment': 'rt cast'}, mode='alter', baseline=baseline),
        target=target)
    assert query("SELECT obj_description(oid, 'pg_cast') FROM pg_cast WHERE "
                 "castsource = 'public.rt_mood'::regtype") == [('rt cast',)]
    assert 'only its comment' in refused('cast', 'alter', {
        'context': 'IMPLICIT'}, target)
    run(client, route, 'cast', 'drop', {'confirmation': 'x'},
        target=find(client, route, 'cast', 'rt_mood AS integer')[0])
    assert not query("SELECT 1 FROM pg_cast WHERE castsource = "
                     "'public.rt_mood'::regtype")


def test_foreign_servers_mappings_and_tables(live):
    """2026-11-01: the postgres_fdw chain through its editors."""
    route, client = live
    query('CREATE EXTENSION IF NOT EXISTS postgres_fdw')
    table_form = resolved_form('yugabytedb', 'table')
    server_form = resolved_form('yugabytedb',
                                'engine_object:foreign-server')
    mapping_form = resolved_form('yugabytedb', 'engine_object:user-mapping')
    try:
        run(client, route, 'foreign-server', 'create', backend_draft(
            server_form, {
                'name': 'rt_srv', 'wrapper': 'postgres_fdw',
                'options': [{'name': 'host', 'value': 'localhost'},
                            {'name': 'dbname', 'value': DATABASE}],
                'comment': 'rt server'}))
        target, baseline = record(client, route, 'foreign-server', 'rt_srv',
                                  'engine_object:foreign-server')
        assert {(row['name'], row['value']) for row in baseline['options']} \
            == {('host', 'localhost'), ('dbname', DATABASE)}
        run(client, route, 'foreign-server', 'alter', backend_draft(
            server_form, {**baseline, 'options': [
                {'name': 'host', 'value': 'localhost'},
                {'name': 'port', 'value': '5433'}], 'version': '1'},
            mode='alter', baseline=baseline), target=target)
        assert query("SELECT srvoptions, srvversion FROM pg_foreign_server "
                     "WHERE srvname = 'rt_srv'") == [
            (['host=localhost', 'port=5433'], '1')]
        assert 'secret' in refused('user-mapping', 'create', {
            'user': 'PUBLIC', 'server': 'rt_srv',
            'options': [{'name': 'password', 'value': 'x'}]})
        run(client, route, 'user-mapping', 'create', backend_draft(
            mapping_form, {'user': 'PUBLIC', 'server': 'rt_srv',
                           'options': [{'name': 'user',
                                        'value': 'remote'}]}))
        mapping = next(row for row in resources(client, route)
                       if row['resource_kind'] == 'user-mapping' and
                       row['display_path'] == ['rt_srv', 'public'])
        run(client, route, 'user-mapping', 'alter', {
            'options': [{'name': 'user', 'value': 'remote2'}]},
            target=mapping)
        assert query("SELECT umoptions FROM pg_user_mappings WHERE "
                     "srvname = 'rt_srv'") == [(['user=remote2'],)]
        run(client, route, 'foreign-table', 'create', backend_draft(
            table_form, {
                'variant': 'foreign', 'name': 'rt_ft', 'parent': 'public',
                'server': 'rt_srv',
                'columns': [{'name': 'id', 'type': 'int', 'nullable': False},
                            {'name': 'v', 'type': 'text'}],
                'options': [{'name': 'table_name', 'value': 'src'}],
                'comment': 'rt foreign'}))
        assert query(
            "SELECT s.srvname, t.ftoptions FROM pg_foreign_table t JOIN "
            "pg_foreign_server s ON s.oid = t.ftserver JOIN pg_class c ON "
            "c.oid = t.ftrelid WHERE c.relname = 'rt_ft'") == [
            ('rt_srv', ['table_name=src'])]
        assert not [row for row in resources(client, route)
                    if row['resource_kind'] == 'table' and
                    row['display_name'] == 'rt_ft']
        foreign = find(client, route, 'foreign-table', 'rt_ft')[0]
        run(client, route, 'foreign-table', 'alter', {
            'add_columns': [{'name': 'w', 'type': 'int'}],
            'options': [{'name': 'table_name', 'value': 'src2'}],
            'comment': 'rt foreign 2'}, target=foreign)
        assert query("SELECT ftoptions FROM pg_foreign_table t JOIN pg_class "
                     "c ON c.oid = t.ftrelid WHERE c.relname = 'rt_ft'") == [
            (['table_name=src2'],)]
        assert ('w',) in query("SELECT attname FROM pg_attribute WHERE "
                               "attrelid = 'public.rt_ft'::regclass")
        run(client, route, 'foreign-table', 'drop', {'confirmation': 'x'},
            target=find(client, route, 'foreign-table', 'rt_ft')[0])
        run(client, route, 'user-mapping', 'drop', {'confirmation': 'x'},
            target=mapping)
        run(client, route, 'foreign-server', 'drop', {'confirmation': 'x'},
            target=find(client, route, 'foreign-server', 'rt_srv')[0])
        assert not query("SELECT 1 FROM pg_foreign_server")
    finally:
        query('DROP SERVER IF EXISTS rt_srv CASCADE')
        query('DROP EXTENSION IF EXISTS postgres_fdw CASCADE')
