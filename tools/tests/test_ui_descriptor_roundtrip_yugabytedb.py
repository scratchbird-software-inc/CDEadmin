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
