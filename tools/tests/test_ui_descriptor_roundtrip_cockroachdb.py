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
        'events': ['INSERT', 'UPDATE'], 'function': ['public', 'on_t'],
        'arguments': [{'value': 'a'}, {'value': 'say "hi", a\\b'}],
        'when': '(NEW).v > 0'}))
    target, baseline = record(client, route, 'trigger', 'tr_rt', 'trigger')
    # One record for a two-event trigger (information_schema lists two).
    assert (baseline['table'], baseline['timing'], baseline['events'],
            baseline['function'], baseline['when']) == (
        ['public', 't'], 'AFTER', ['INSERT', 'UPDATE'], ['public', 'on_t'],
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
