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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_YUGABYTEDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_YUGABYTEDB is not set',
                allow_module_level=True)
psycopg = pytest.importorskip('psycopg')

from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION, PROFILE, create_provider,
)
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'rt_{UNIQUE}'


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
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=f'rt{UNIQUE}',
        pool_namespace=f'rt{UNIQUE}', cache_namespace=f'rt{UNIQUE}',
        provider_id=PROFILE.provider_id, profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version, provider_version='0.2.0')
    client = create_provider(context, SimpleNamespace(
        acquire_secret=None, require=lambda *_args: None)).client
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
        with connect() as connection:
            connection.execute(f'DROP DATABASE IF EXISTS {DATABASE} '
                               'WITH (FORCE)')
            for role in (f'rt_user_{UNIQUE}', f'rt_role_{UNIQUE}',
                         f'rt_user2_{UNIQUE}'):
                connection.execute(f'DROP ROLE IF EXISTS {role}')


def resources(client, route):
    return client.list_resources({'route': dict(route)})


def executor_request(request, planned):
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
                   {'name': 'label', 'type': 'text'}]}))
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
    assert [(row['name'], row['type']) for row in point['fields']] == [
        ('x', 'integer'), ('label', 'text')]
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
                       ('type', 'rt_span'), ('domain', 'rt_code2')):
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
