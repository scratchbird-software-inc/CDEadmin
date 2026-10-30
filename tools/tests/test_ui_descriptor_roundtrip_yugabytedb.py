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
