"""CockroachDB family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live cluster -> re-inspect.

Owner direction 2026-10-29: CockroachDB reaches full parity with PostgreSQL
including its native features. Set ``CDEADMIN_ROUNDTRIP_COCKROACHDB`` to a
JSON object ``{"host", "port", "user"}`` for the demo node
(`dev.sh start cockroachdb`). The test creates its own database and roles
and removes them. Skipped otherwise.
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_COCKROACHDB')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_COCKROACHDB is not set',
                allow_module_level=True)
psycopg = pytest.importorskip('psycopg')

from pgadmin.cdeadmin.providers.cockroachdb.provider import (  # noqa: E402
    ADMINISTRATION, PROFILE, create_provider,
)
from ui_descriptor_roundtrip import (  # noqa: E402
    backend_draft, record_draft, record_from_resource, resolved_form,
)

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'rt_{UNIQUE}'


def connect(database='defaultdb'):
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
        query('CREATE TABLE public.t (id INT PRIMARY KEY, v INT)')
        query('CREATE FUNCTION public.on_t() RETURNS TRIGGER '
              'LANGUAGE PLpgSQL AS $$ BEGIN RETURN COALESCE(NEW, OLD); '
              'END $$')
        yield route, client
    finally:
        with connect() as connection:
            connection.execute(f'DROP DATABASE IF EXISTS {DATABASE} CASCADE')
            for role in (f'rt_user_{UNIQUE}', f'rt_role_{UNIQUE}'):
                connection.execute(f'DROP ROLE IF EXISTS {role}')


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
    return planned


def find(client, route, kind, name):
    rows = resources(client, route)
    found = [row for row in rows
             if row['resource_kind'] == kind and row['display_name'] == name]
    assert len(found) == 1, f'{kind} {name}: {len(found)} records'
    return found[0], rows


def record(client, route, kind, name, family):
    row, rows = find(client, route, kind, name)
    form = resolved_form('cockroachdb', family)
    return row, record_draft(form, record_from_resource(form, row, rows))


def refused_sql(sql):
    try:
        query(sql)
    except psycopg.Error as error:
        return str(error)
    return ''


def refused(kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, 'draft': draft}
    return ' '.join(error['message'] for error in
                    ADMINISTRATION.validate(request)['errors'])


def test_trigger_create_reopen_drop(live):
    route, client = live
    form = resolved_form('cockroachdb', 'trigger')
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'tr_rt', 'table': ['public', 't'], 'timing': 'AFTER',
        'events': ['INSERT', 'UPDATE'], 'function': ['public', 'on_t()'],
        'arguments': [{'value': 'a'}, {'value': 'say "hi", a\\b'}],
        'when': '(NEW).v > 0'}))
    target, baseline = record(client, route, 'trigger', 'tr_rt', 'trigger')
    # One record for a two-event trigger (information_schema lists two).
    assert (baseline['table'], baseline['timing'], baseline['events'],
            baseline['function'], baseline['when']) == (
        ['public', 't'], 'AFTER', ['INSERT', 'UPDATE'], ['public', 'on_t()'],
        '(new).v > 0')
    assert [row['value'] for row in baseline['arguments']] == [
        'a', 'say "hi", a\\b']
    run(client, route, 'trigger', 'drop', {'confirmation': 'tr_rt'},
        target=target)
    assert not query("SELECT 1 FROM pg_trigger WHERE tgname = 'tr_rt'")


@pytest.mark.parametrize('draft, reason', [
    ({'timing': 'INSTEAD OF'}, 'no INSTEAD OF'),
    ({'events': ['TRUNCATE']}, 'INSERT, UPDATE, DELETE'),
    # Live: CockroachDB re-renders the quote unescaped and cannot parse it.
    ({'arguments': ["it's"]}, "containing '"),
])
def test_trigger_refuses_what_cockroachdb_refuses(draft, reason):
    base = {'name': 'x', 'table': 'public.t', 'timing': 'BEFORE',
            'events': ['INSERT'], 'function': 'public.on_t'}
    assert reason in refused('trigger', 'create', {**base, **draft})


def test_user_and_role_create_reopen_alter_drop(live):
    route, client = live
    form = resolved_form('cockroachdb', 'role')
    role, user = f'rt_role_{UNIQUE}', f'rt_user_{UNIQUE}'
    run(client, route, 'role', 'create', backend_draft(form, {
        'variant': 'role', 'name': role,
        'privileges': ['CREATEDB', 'VIEWACTIVITY']}))
    planned = run(client, route, 'user', 'create', backend_draft(form, {
        'variant': 'user', 'name': user, 'sql_login': False,
        'valid_until': '2030-01-01', 'member_of': [{'role': role}]}))
    # Insecure demo: no password is set or sent.
    assert 'PASSWORD' not in json.dumps(planned['command_preview'])
    _, made_role = record(client, route, 'role', role, 'role')
    assert (made_role['login'], made_role['privileges']) == (
        False, ['CREATEDB', 'VIEWACTIVITY'])
    target, baseline = record(client, route, 'user', user, 'role')
    assert (baseline['login'], baseline['sql_login'],
            baseline['valid_until'][:10],
            [row['role'] for row in baseline['member_of']]) == (
        True, False, '2030-01-01', [role])
    alter = backend_draft(form, {
        **baseline, 'variant': 'user', 'sql_login': True, 'valid_until': '',
        'privileges': ['CONTROLJOB'], 'member_of': []},
        mode='alter', baseline=baseline)
    assert alter == {'sql_login': True, 'valid_until': '',
                     'privileges': ['CONTROLJOB'], 'member_of': []}
    run(client, route, 'user', 'alter', alter, target=target)
    _, after = record(client, route, 'user', user, 'role')
    assert (after['sql_login'], after['valid_until'], after['privileges'],
            after['member_of']) == (True, None, ['CONTROLJOB'], [])
    # Re-sending a value the record already holds changes nothing.
    assert 'nothing to change' in refused(
        'user', 'alter', {'sql_login': True},
        find(client, route, 'user', user)[0])
    for kind, name in (('user', user), ('role', role)):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query(f"SELECT 1 FROM pg_roles WHERE rolname IN "
                     f"('{user}', '{role}')")


def by_name(rows):
    return {row['name']: row for row in rows}


def test_table_create_reopen_alter_drop(live):
    route, client = live
    query('CREATE TABLE public.parent (k INT8 PRIMARY KEY)')
    form = resolved_form('cockroachdb', 'table')
    run(client, route, 'table', 'create', backend_draft(form, {
        'name': 'rt_orders', 'parent': 'public', 'comment': 'orders',
        'columns': [
            {'name': 'id', 'type': 'INT8', 'nullable': False},
            {'name': 'pk2', 'type': 'INT8', 'nullable': False,
             'default': '0'},
            {'name': 'seq', 'type': 'INT8', 'identity': 'BY DEFAULT',
             'family': 'hot'},
            {'name': 'note', 'type': 'STRING', 'default': "'x'",
             'on_update': "'y'", 'not_visible': True, 'family': 'hot',
             'comment': 'a note'},
            {'name': 'twice', 'type': 'INT8', 'generated_kind': 'VIRTUAL',
             'generated_expression': 'id * 2'},
            {'name': 'ref', 'type': 'INT8'},
        ],
        'primary_key': [{'name': 'rt_orders_pkey', 'columns': ['id']}],
        'unique_constraints': [{'name': 'uq_note', 'columns': ['note']}],
        'foreign_keys': [{'name': 'fk_ref', 'columns': ['ref'],
                          'references_table': ['public', 'parent'],
                          'references_columns': ['k'],
                          'on_delete': 'SET NULL'}],
        'check_constraints': [{'name': 'ck_id', 'expression': 'id > 0'}],
        'ttl_expire_after': '30 days'}))
    target, baseline = record(client, route, 'table', 'rt_orders', 'table')
    columns = by_name(baseline['columns'])
    assert list(columns) == ['id', 'pk2', 'seq', 'note', 'twice', 'ref']
    assert (columns['seq']['identity'], columns['seq']['family'],
            columns['seq']['default']) == ('BY DEFAULT', 'hot', None)
    assert (columns['note']['not_visible'], columns['note']['on_update'],
            columns['note']['comment'], columns['note']['family']) == (
        True, "'y'", 'a note', 'hot')
    assert (columns['twice']['generated_kind'],
            columns['twice']['family']) == ('VIRTUAL', None)
    assert columns['id']['primary_key'] and columns['note']['unique']
    assert [(row['name'], row['columns'])
            for row in baseline['primary_key']] == [
        ('rt_orders_pkey', ['id'])]
    fk = baseline['foreign_keys'][0]
    assert (fk['references_table'], fk['references_columns'],
            fk['on_delete'], fk['on_update']) == (
        ['public', 'parent'], ['k'], 'SET NULL', 'NO ACTION')
    assert baseline['check_constraints'][0]['expression'] == 'id > 0'
    assert (baseline['ttl_expire_after'], baseline['comment']) == (
        '30 days', 'orders')
    # An uncommented table has no comment (a one-argument obj_description
    # returned a built-in function's description here).
    assert record(client, route, 'table', 'parent', 'table')[1][
        'comment'] is None

    # Reopened unchanged: nothing to send.
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    changed = [dict(row) for row in baseline['columns']]
    for row in changed:
        if row['name'] == 'ref':
            row.update(name='ref_id', nullable=True, comment='renamed')
        if row['name'] == 'note':
            row.update(type='STRING(40)', default='', not_visible=False)
    changed.append({'name': 'extra', 'type': 'INT8', 'family': 'cold'})
    alter = backend_draft(form, {
        **baseline, 'columns': changed,
        'unique_constraints': [{'name': 'uq_extra', 'columns': ['extra']}],
        'comment': 'orders v2'}, mode='alter', baseline=baseline)
    assert sorted(alter) == ['add_columns', 'alter_columns', 'comment',
                             'rename_columns', 'unique_constraints']
    run(client, route, 'table', 'alter', alter, target=target)
    target, after = record(client, route, 'table', 'rt_orders', 'table')
    columns = by_name(after['columns'])
    assert (columns['note']['type'], columns['note']['default'],
            columns['note']['not_visible']) == ('STRING(40)', None, False)
    assert columns['ref_id']['comment'] == 'renamed'
    assert columns['extra']['family'] == 'cold'
    assert [row['name'] for row in after['unique_constraints']] == [
        'uq_extra']
    # The untouched grids kept their constraints.
    assert [row['name'] for row in after['check_constraints']] == ['ck_id']
    assert after['foreign_keys'][0]['columns'] == ['ref_id']
    assert after['comment'] == 'orders v2'

    planned = run(client, route, 'table', 'alter', backend_draft(form, {
        **after, 'primary_key': [{'name': 'rt_orders_pkey',
                                  'columns': ['id', 'pk2']}],
        'ttl_expire_after': ''}, mode='alter', baseline=after),
        target=target)
    assert 'UNIQUE index' in planned['warnings'][0]
    target, last = record(client, route, 'table', 'rt_orders', 'table')
    assert last['primary_key'][0]['columns'] == ['id', 'pk2']
    assert last['ttl_expire_after'] is None
    run(client, route, 'table', 'drop', {'confirmation': 'rt_orders'},
        target=target)
    assert not query("SELECT 1 FROM pg_class WHERE relname = 'rt_orders'")


def test_index_create_reopen_alter_drop(live):
    route, client = live
    query('CREATE TABLE public.ix (id INT8 PRIMARY KEY, a INT8, b STRING, '
          'j JSONB, ts TIMESTAMPTZ)')
    form = resolved_form('cockroachdb', 'index')
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'ix_ab', 'table': ['public', 'ix'],
        'keys': [{'expression': 'a', 'direction': 'DESC'},
                 {'expression': 'lower(b)'}],
        'storing': [{'value': 'ts'}], 'predicate': 'a > 0',
        'visibility': 0.25, 'comment': 'partial'}))
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'ix_hash', 'table': ['public', 'ix'], 'unique': True,
        'keys': [{'expression': 'b'}], 'hash_sharded': True,
        'bucket_count': 8}))
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'ix_inv', 'table': ['public', 'ix'], 'method': 'inverted',
        'keys': [{'expression': 'j'}]}))
    target, baseline = record(client, route, 'index', 'ix_ab', 'index')
    assert (baseline['table'], baseline['keys'],
            [row['value'] for row in baseline['storing']],
            baseline['predicate'], baseline['visibility'],
            baseline['comment']) == (
        ['public', 'ix'],
        [{'expression': 'a', 'direction': 'DESC', '_id': '0'},
         {'expression': 'lower(b)', 'direction': 'ASC', '_id': '1'}],
        ['ts'], 'a > 0', 0.25, 'partial')
    _, hashed = record(client, route, 'index', 'ix_hash', 'index')
    assert (hashed['unique'], hashed['hash_sharded'],
            hashed['bucket_count'], hashed['keys'][0]['expression']) == (
        True, True, 8, 'b')
    _, inverted = record(client, route, 'index', 'ix_inv', 'index')
    assert inverted['method'] == 'inverted'
    # Reopened unchanged: nothing to send.
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    alter = backend_draft(form, {**baseline, 'name': 'ix_ab2',
                                 'visibility': 0, 'comment': ''},
                          mode='alter', baseline=baseline)
    assert alter == {'name': 'ix_ab2', 'visibility': 0, 'comment': ''}
    run(client, route, 'index', 'alter', alter, target=target)
    target, after = record(client, route, 'index', 'ix_ab2', 'index')
    assert (after['visibility'], after['comment']) == (0.0, None)
    for name in ('ix_ab2', 'ix_hash', 'ix_inv'):
        run(client, route, 'index', 'drop', {'confirmation': name},
            target=find(client, route, 'index', name)[0])
    assert query("SELECT indexname FROM pg_indexes WHERE tablename='ix'") \
        == [('ix_pkey',)]


def test_enum_and_composite_types(live):
    route, client = live
    form = resolved_form('cockroachdb', 'type')
    query('CREATE TABLE public.not_a_type (id INT8 PRIMARY KEY)')
    run(client, route, 'type', 'create', backend_draft(form, {
        'name': 'rt_status', 'parent': 'public', 'type_kind': 'ENUM',
        'values': [{'value': 'new'}, {'value': "it's"}, {'value': 'done'}],
        'comment': 'status'}))
    run(client, route, 'type', 'create', backend_draft(form, {
        'name': 'rt_point', 'parent': 'public', 'type_kind': 'COMPOSITE',
        'fields': [{'name': 'x', 'type': 'INT8'},
                   {'name': 'label', 'type': 'STRING'}]}))
    kinds = {row['display_name'] for row in resources(client, route)
             if row['resource_kind'] == 'type'}
    # Tables' row types are not types (pg_type lists them as 'c').
    assert kinds == {'rt_status', 'rt_point'}
    target, baseline = record(client, route, 'type', 'rt_status', 'type')
    assert ([row['value'] for row in baseline['values']],
            baseline['comment'], baseline['parent']) == (
        ['new', "it's", 'done'], 'status', 'public')
    _, point = record(client, route, 'type', 'rt_point', 'type')
    assert [(row['name'], row['type']) for row in point['fields']] == [
        ('x', 'bigint'), ('label', 'text')]
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    alter = backend_draft(form, {
        **baseline, 'name': 'rt_state',
        'rename_values': [{'from': 'done', 'to': 'closed'}],
        'values': [{'value': 'draft'}, {'value': 'new'}, {'value': 'closed'},
                   {'value': 'archived'}],
        'comment': ''}, mode='alter', baseline=baseline)
    run(client, route, 'type', 'alter', alter, target=target)
    target, after = record(client, route, 'type', 'rt_state', 'type')
    assert ([row['value'] for row in after['values']], after['comment']) \
        == (['draft', 'new', 'closed', 'archived'], None)
    assert 'reorder' in refused('type', 'alter', {
        'values': ['closed', 'new', 'draft', 'archived']}, target)
    for name in ('rt_state', 'rt_point'):
        run(client, route, 'type', 'drop', {'confirmation': name},
            target=find(client, route, 'type', name)[0])
    assert not query("SELECT 1 FROM pg_type WHERE typname IN "
                     "('rt_state', 'rt_point')")


def test_view_and_materialized_view(live):
    route, client = live
    query('CREATE TABLE public.vt (id INT8 PRIMARY KEY, v INT8)')
    query('INSERT INTO public.vt VALUES (1, 10)')
    form = resolved_form('cockroachdb', 'view')
    run(client, route, 'view', 'create', backend_draft(form, {
        'name': 'rt_v', 'parent': 'public',
        'query': 'SELECT id, v FROM public.vt',
        'column_names': [{'value': 'a'}, {'value': 'b'}]}))
    run(client, route, 'materialized-view', 'create', backend_draft(form, {
        'variant': 'materialized', 'name': 'rt_m', 'parent': 'public',
        'query': 'SELECT id FROM public.vt', 'with_data': False}))
    target, baseline = record(client, route, 'view', 'rt_v', 'view')
    assert 'FROM' in baseline['query'] and baseline['parent'] == 'public'
    assert query('SELECT a, b FROM public.rt_v') == [(1, 10)]
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    assert [row['value'] for row in baseline['column_names']] == ['a', 'b']
    # Replacing keeps the existing names and adds one at the end.
    run(client, route, 'view', 'alter', backend_draft(form, {
        **baseline, 'name': 'rt_v2',
        'query': 'SELECT id, v, v * 2 FROM public.vt',
        'column_names': baseline['column_names'] + [{'value': 'c'}]},
        mode='alter', baseline=baseline), target=target)
    assert query('SELECT a, b, c FROM public.rt_v2') == [(1, 10, 20)]
    mtarget, mbase = record(client, route, 'materialized-view', 'rt_m',
                            'view')
    assert [row['value'] for row in mbase['column_names']] == ['id']
    # WITH NO DATA took effect; pg_matviews.ispopulated would still say
    # true, so the record does not report it.
    assert 'not been populated' in refused_sql('SELECT id FROM public.rt_m')
    assert 'cannot change in place' in refused(
        'materialized-view', 'alter', {'query': 'SELECT 2'}, mtarget)
    run(client, route, 'materialized-view', 'refresh', {}, target=mtarget)
    assert query('SELECT id FROM public.rt_m') == [(1,)]
    run(client, route, 'materialized-view', 'alter', {'name': 'rt_m2'},
        target=mtarget)
    for kind, name in (('view', 'rt_v2'), ('materialized-view', 'rt_m2')):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query("SELECT 1 FROM pg_class WHERE relname LIKE 'rt\\_%'")


def test_sequence_create_reopen_alter_drop(live):
    route, client = live
    query('CREATE TABLE public.st (id INT8 PRIMARY KEY, n INT8)')
    form = resolved_form('cockroachdb', 'sequence')
    run(client, route, 'sequence', 'create', backend_draft(form, {
        'name': 'rt_seq', 'parent': 'public', 'data_type': 'INT4',
        'start': 5, 'increment': 2, 'minimum': 1, 'maximum': 1000,
        'cache': 10, 'cache_scope': 'PER SESSION',
        'owned_by': 'public.st.n'}))
    target, baseline = record(client, route, 'sequence', 'rt_seq',
                              'sequence')
    assert {key: baseline[key] for key in (
        'data_type', 'start', 'increment', 'minimum', 'maximum', 'cache',
        'cache_scope', 'owned_by')} == {
        'data_type': 'INT4', 'start': 5, 'increment': 2, 'minimum': 1,
        'maximum': 1000, 'cache': 10, 'cache_scope': 'PER SESSION',
        'owned_by': 'public.st.n'}
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    run(client, route, 'sequence', 'alter', backend_draft(form, {
        **baseline, 'name': 'rt_seq2', 'data_type': 'INT8',
        'increment': 4, 'maximum': None, 'cache_scope': '', 'owned_by': '',
        'restart': 100}, mode='alter', baseline=baseline), target=target)
    target, after = record(client, route, 'sequence', 'rt_seq2', 'sequence')
    # Leaving PER SESSION took a reset first; a cache above 1 is per node.
    assert (after['data_type'], after['increment'], after['maximum'],
            after['cache'], after['cache_scope'], after['owned_by']) == (
        'INT8', 4, 9223372036854775807, 10, 'PER NODE', None)
    assert query("SELECT nextval('public.rt_seq2')") == [(100,)]
    assert 'CYCLE' in refused('sequence', 'alter', {'cycle': True}, target)
    run(client, route, 'sequence', 'drop', {'confirmation': 'rt_seq2'},
        target=target)
    assert not query("SELECT 1 FROM pg_class WHERE relname = 'rt_seq2'")


def test_functions_and_procedures(live):
    route, client = live
    form = resolved_form('cockroachdb', 'routine')
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_add', 'parent': 'public',
        'parameters': [{'name': 'a', 'type': 'INT8'},
                       {'name': 'b', 'type': 'INT8', 'default': '2'}],
        'returns': 'INT8', 'language': 'SQL', 'volatility': 'IMMUTABLE',
        'strict': True, 'leakproof': True, 'body': 'SELECT a + b'}))
    # An overload of the same name stays a separate routine.
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_add', 'parent': 'public',
        'parameters': [{'name': 'a', 'type': 'STRING'}],
        'returns': 'STRING', 'body': "SELECT a || '!'"}))
    run(client, route, 'function', 'create', backend_draft(form, {
        'variant': 'function', 'name': 'rt_split', 'parent': 'public',
        'parameters': [{'name': 'a', 'type': 'INT8'},
                       {'mode': 'OUT', 'name': 'x', 'type': 'INT8'},
                       {'mode': 'INOUT', 'name': 'y', 'type': 'INT8'}],
        'language': 'PLPGSQL',
        'body': 'BEGIN x := a; y := y + 1; END'}))
    run(client, route, 'procedure', 'create', backend_draft(form, {
        'variant': 'procedure', 'name': 'rt_proc', 'parent': 'public',
        'parameters': [{'name': 'n', 'type': 'INT8'}],
        'language': 'PLPGSQL', 'security': 'DEFINER',
        'body': "BEGIN RAISE NOTICE 'n=%', n; END"}))
    names = sorted(row['display_name'] for row in resources(client, route)
                   if row['resource_kind'] in {'function', 'procedure'} and
                   row['display_name'].startswith('rt_'))
    assert names == ['rt_add(int8, int8)', 'rt_add(text)',
                     'rt_proc(int8)', 'rt_split(int8, int8)']
    target, baseline = record(client, route, 'function',
                              'rt_add(int8, int8)', 'routine')
    assert ([(row['name'], row['type'], row['default'], row['mode'])
             for row in baseline['parameters']], baseline['returns'],
            baseline['volatility'], baseline['strict'],
            baseline['leakproof'], baseline['name']) == (
        [('a', 'INT8', None, 'IN'), ('b', 'INT8', '2', 'IN')], 'INT8',
        'IMMUTABLE', True, True, 'rt_add')
    assert query('SELECT public.rt_add(1)') == [(3,)]
    _, split = record(client, route, 'function', 'rt_split(int8, int8)',
                      'routine')
    assert [row['mode'] for row in split['parameters']] == [
        'IN', 'OUT', 'INOUT']
    assert backend_draft(form, baseline, mode='alter',
                         baseline=baseline) == {}
    # The editor host adds the kind's variant to the record.
    baseline['variant'] = 'function'
    alter = backend_draft(form, {
        **baseline, 'body': 'SELECT a * b', 'volatility': 'STABLE',
        'leakproof': False, 'name': 'rt_mul'},
        mode='alter', baseline=baseline)
    run(client, route, 'function', 'alter', alter, target=target)
    assert query('SELECT public.rt_mul(3)') == [(6,)]
    assert query('SELECT public.rt_add(\'x\')') == [('x!',)]
    _, after = record(client, route, 'function', 'rt_mul(int8, int8)',
                      'routine')
    assert (after['volatility'], after['leakproof']) == ('STABLE', False)
    # ALTER ... SECURITY DEFINER leaves pg_proc.prosecdef false; the record
    # reads the rendering.
    query('ALTER FUNCTION public.rt_mul(INT8, INT8) SECURITY DEFINER')
    assert record(client, route, 'function', 'rt_mul(int8, int8)',
                  'routine')[1]['security'] == 'DEFINER'
    assert 'identity' in refused('function', 'alter', {'parameters': []},
                                 find(client, route, 'function',
                                      'rt_mul(int8, int8)')[0])
    ptarget, proc = record(client, route, 'procedure', 'rt_proc(int8)',
                           'routine')
    assert (proc['security'], proc['language']) == ('DEFINER', 'PLPGSQL')
    query('CALL public.rt_proc(1)')
    for kind, name in (('function', 'rt_mul(int8, int8)'),
                       ('function', 'rt_add(text)'),
                       ('function', 'rt_split(int8, int8)'),
                       ('procedure', 'rt_proc(int8)')):
        run(client, route, kind, 'drop', {'confirmation': name},
            target=find(client, route, kind, name)[0])
    assert not query("SELECT 1 FROM pg_proc WHERE proname LIKE 'rt\\_%'")


def test_database_create_reopen_alter_drop(live):
    route, client = live
    name = f'rt_db_{UNIQUE}'
    owner = f'rt_owner_{UNIQUE}'
    with connect() as connection:
        connection.execute(f'CREATE ROLE {owner}')
    form = resolved_form('cockroachdb', 'database')
    try:
        run(client, route, 'database', 'create', backend_draft(form, {
            'name': name, 'owner': owner, 'comment': 'rt',
            'settings': [{'name': 'timezone', 'value': 'UTC'},
                         {'name': 'statement_timeout', 'value': '10s'}]}))
        target, baseline = record(client, route, 'database', name,
                                  'database')
        assert (baseline['owner'], baseline['comment'],
                baseline['encoding'],
                sorted((row['name'], row['value'])
                       for row in baseline['settings'])) == (
            owner, 'rt', 'UTF8',
            [('statement_timeout', '10s'), ('timezone', 'UTC')])
        assert backend_draft(form, baseline, mode='alter',
                             baseline=baseline) == {}
        alter = backend_draft(form, {
            **baseline, 'name': f'{name}_2', 'owner': 'root', 'comment': '',
            'settings': [{'name': 'timezone', 'value': 'America/Toronto'}]},
            mode='alter', baseline=baseline)
        run(client, route, 'database', 'alter', alter, target=target)
        target, after = record(client, route, 'database', f'{name}_2',
                               'database')
        assert (after['owner'], after['comment'],
                [(row['name'], row['value']) for row in after['settings']]) \
            == ('root', None, [('timezone', 'America/Toronto')])
        run(client, route, 'database', 'drop',
            {'cascade': True, 'confirmation': f'{name}_2'}, target=target)
        assert not query(f"SELECT 1 FROM pg_database WHERE datname LIKE "
                         f"'{name}%'")
    finally:
        with connect() as connection:
            for database in (name, f'{name}_2'):
                connection.execute(
                    f'DROP DATABASE IF EXISTS {database} CASCADE')
            connection.execute(f'DROP ROLE IF EXISTS {owner}')
