"""MySQL family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Set ``CDEADMIN_ROUNDTRIP_MYSQL`` to a JSON object ``{"host", "port", "user",
"password"}`` for an account that may create databases and accounts (the demo's
root, ``dev.sh start mysql``). The test creates and drops its own database and
accounts. Skipped otherwise.
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

SETTINGS = os.environ.get('CDEADMIN_ROUNDTRIP_MYSQL')
if not SETTINGS:
    pytest.skip('CDEADMIN_ROUNDTRIP_MYSQL is not set', allow_module_level=True)
mysql_connector = pytest.importorskip('mysql.connector')

from pgadmin.cdeadmin.providers.mysql_family.provider import (  # noqa: E402
    MYSQL_ADMINISTRATION as ADMINISTRATION, MYSQL_PROFILE, _create_client, _resources,
)
from pgadmin.cdeadmin.security.secrets import SecretLease  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, record_draft, record_from_resource, resolved_form  # noqa: E402

SETTINGS = json.loads(SETTINGS)
UNIQUE = uuid.uuid4().hex[:6]
DATABASE = f'ui_rt_{UNIQUE}'


def admin(database=None):
    return mysql_connector.connect(host=SETTINGS['host'], port=int(SETTINGS['port']), user=SETTINGS['user'],
                                   password=SETTINGS['password'], autocommit=True, use_pure=True,
                                   **({'database': database} if database else {}))


@pytest.fixture(scope='module')
def live():
    seed = admin()
    cursor = seed.cursor()
    cursor.execute(f'CREATE DATABASE `{DATABASE}`')
    cursor.execute(f'CREATE TABLE `{DATABASE}`.owner(id INT PRIMARY KEY, label VARCHAR(40))')
    seed.close()
    route = {'host': SETTINGS['host'], 'port': int(SETTINGS['port']), 'database': DATABASE, 'user': SETTINGS['user'],
             'credential_reference_id': 'ui-roundtrip', 'principal_reference': 'ui-roundtrip'}
    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=lambda *_args: SecretLease(SETTINGS['password'])),
                            SimpleNamespace(pool_namespace=f'ui-roundtrip-{UNIQUE}'))
    try:
        yield route, client
    finally:
        client.close()
        cleanup = admin()
        for statement in (f'DROP DATABASE IF EXISTS `{DATABASE}`',
                          f"DROP USER IF EXISTS 'rt_user_{UNIQUE}'@'localhost'",
                          f"DROP ROLE IF EXISTS 'rt_role_{UNIQUE}'"):
            cleanup.cursor().execute(statement)
        cleanup.close()


def resources(client, route):
    connection = client._connect({'route': dict(route)})
    try:
        return list(_resources(connection, {'route': route}, MYSQL_PROFILE))
    finally:
        client._forget_and_close(connection)


def run(client, route, kind, operation, draft, target=None):
    """Validate, plan (with the client's native review step) and apply, as the app does."""
    request = {'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    errors = client.validate_admin_operation(request)['errors']
    assert errors == [], errors
    planned = client.plan_admin_operation(request)
    sql = '\n'.join(statement['source'] for statement in planned['command_preview']['statements'])
    assert client.apply_admin_operation(planned)['accepted'], sql
    return sql


VARIANTS = {'materialized-view': 'materialized'}  # capabilities.json; the editor host adds it to the record


def record(client, route, kind, name, family):
    rows = resources(client, route)
    row = next(item for item in rows if item['resource_kind'] == kind and item['display_name'] == name)
    form = resolved_form('mysql', family)
    native = record_from_resource(form, row, rows)
    if kind in VARIANTS:
        native['variant'] = VARIANTS[kind]
    return row, record_draft(form, native)


def query(sql, database=None):
    connection = admin(database)
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        connection.close()


def test_view_form_every_field_round_trips_and_alter_keeps_the_rest(live):
    route, client = live
    form = resolved_form('mysql', 'view')
    run(client, route, 'view', 'create', backend_draft(form, {
        'name': 'rt_v', 'parent': DATABASE, 'query': 'SELECT id, label FROM owner',
        'column_aliases': [{'value': 'owner_id'}, {'value': 'owner_label'}],
        'algorithm': 'MERGE', 'check_option': 'LOCAL', 'sql_security': 'INVOKER',
        'definer_user': 'root', 'definer_host': '%'}))
    view, baseline = record(client, route, 'view', 'rt_v', 'view')
    assert baseline['query'].lower().startswith('select')
    assert [row['value'] for row in baseline['column_aliases']] == ['owner_id', 'owner_label']
    assert (baseline['algorithm'], baseline['check_option'], baseline['sql_security']) == ('MERGE', 'LOCAL', 'INVOKER')
    assert (baseline['definer_user'], baseline['definer_host']) == ('root', '%')
    # The editor sends only what changed; ALTER VIEW must keep the rest.
    alter = backend_draft(form, {**baseline, 'check_option': 'CASCADED'}, mode='alter', baseline=baseline)
    assert alter == {'check_option': 'CASCADED'}
    run(client, route, 'view', 'alter', alter, target=view)
    view, after = record(client, route, 'view', 'rt_v', 'view')
    assert after['check_option'] == 'CASCADED'
    assert [row['value'] for row in after['column_aliases']] == ['owner_id', 'owner_label']
    assert (after['algorithm'], after['sql_security'], after['definer_host']) == ('MERGE', 'INVOKER', '%')
    alter = backend_draft(form, {**after, 'column_aliases': [{'value': 'k'}, {'value': 'v'}]}, mode='alter', baseline=after)
    assert alter == {'columns': ['k', 'v']}
    run(client, route, 'view', 'alter', alter, target=view)
    _view, final = record(client, route, 'view', 'rt_v', 'view')
    assert [row['value'] for row in final['column_aliases']] == ['k', 'v'] and final['check_option'] == 'CASCADED'
    # A view declared without aliases keeps none when another option changes.
    run(client, route, 'view', 'create', backend_draft(form, {'name': 'rt_plain', 'parent': DATABASE,
                                                             'query': 'SELECT id FROM owner'}))
    plain, plain_record = record(client, route, 'view', 'rt_plain', 'view')
    assert plain_record['column_aliases'] == []
    run(client, route, 'view', 'alter', backend_draft(form, {**plain_record, 'sql_security': 'INVOKER'},
                                                      mode='alter', baseline=plain_record), target=plain)
    ddl = query(f'SHOW CREATE VIEW `{DATABASE}`.`rt_plain`')[0][1]
    assert 'SQL SECURITY INVOKER' in ddl and '`rt_plain` AS select' in ddl  # no alias list was added


def test_materialized_view_form_round_trips_and_stays_materialized(live):
    route, client = live
    form = resolved_form('mysql', 'view')
    run(client, route, 'materialized-view', 'create', backend_draft(form, {
        'variant': 'materialized', 'name': 'rt_mv', 'parent': DATABASE, 'query': 'SELECT id, label FROM owner',
        'column_aliases': [{'value': 'k'}, {'value': 'v'}], 'algorithm': 'MERGE', 'sql_security': 'INVOKER',
        'definer_user': 'root', 'definer_host': '%'}))
    view, baseline = record(client, route, 'materialized-view', 'rt_mv', 'view')
    assert baseline['variant'] == 'materialized' and 'check_option' not in backend_draft(form, baseline)
    assert [row['value'] for row in baseline['column_aliases']] == ['k', 'v']
    assert (baseline['algorithm'], baseline['sql_security'], baseline['definer_host']) == ('MERGE', 'INVOKER', '%')
    alter = backend_draft(form, {**baseline, 'algorithm': 'TEMPTABLE'}, mode='alter', baseline=baseline)
    assert alter == {'algorithm': 'TEMPTABLE'}
    run(client, route, 'materialized-view', 'alter', alter, target=view)
    ddl = query(f'SHOW CREATE VIEW `{DATABASE}`.`rt_mv`')[0][1]
    assert 'ALGORITHM=TEMPTABLE MATERIALIZED' in ddl and '(`k`,`v`)' in ddl and 'SQL SECURITY INVOKER' in ddl
    _view, after = record(client, route, 'materialized-view', 'rt_mv', 'view')
    assert after['algorithm'] == 'TEMPTABLE' and [row['value'] for row in after['column_aliases']] == ['k', 'v']


def show_create(table):
    return query(f'SHOW CREATE TABLE `{DATABASE}`.`{table}`')[0][1]


def test_index_form_every_create_field_and_alter(live):
    route, client = live
    form = resolved_form('mysql', 'index')
    query(f'CREATE TABLE `{DATABASE}`.docs(id INT PRIMARY KEY, a VARCHAR(40), b INT, body TEXT)')
    query(f'CREATE TABLE `{DATABASE}`.packed(id INT PRIMARY KEY, a INT) ENGINE=MyISAM')
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_ix', 'table': f'{DATABASE}.docs', 'index_kind': 'NORMAL', 'unique': True, 'method': 'BTREE',
        'columns': [{'name': 'a', 'prefix_length': 10, 'direction': 'DESC'}, {'expression': '`b` + 1', 'direction': 'ASC'}],
        'comment': 'round trip', 'visible': False, 'secondary_engine_attribute': {'k': 'v'}}))
    # Algorithm and lock are statement options, not stored: they must reach the executed DDL.
    # MySQL refuses INPLACE with an expression key part (1846), so they get plain columns.
    sql = run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_inplace', 'table': f'{DATABASE}.docs', 'columns': [{'name': 'b'}],
        'algorithm': 'INPLACE', 'lock': 'NONE'}))
    assert 'ALGORITHM=INPLACE' in sql and 'LOCK=NONE' in sql
    sql = run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_copy', 'table': f'{DATABASE}.docs', 'columns': [{'name': 'a'}],
        'algorithm': 'COPY', 'lock': 'SHARED'}))
    assert 'ALGORITHM=COPY' in sql and 'LOCK=SHARED' in sql
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_ft', 'table': f'{DATABASE}.docs', 'index_kind': 'FULLTEXT', 'columns': [{'name': 'body'}],
        'parser': 'ngram'}))
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_kb', 'table': f'{DATABASE}.packed', 'columns': [{'name': 'a'}], 'key_block_size': '4'}))
    query(f'CREATE TABLE `{DATABASE}`.places(id INT PRIMARY KEY, spot POINT NOT NULL SRID 0) ENGINE=InnoDB')
    query(f'CREATE TABLE `{DATABASE}`.lookup(id INT PRIMARY KEY, code INT) ENGINE=MEMORY')
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_sp', 'table': f'{DATABASE}.places', 'index_kind': 'SPATIAL', 'columns': [{'name': 'spot'}]}))
    run(client, route, 'index', 'create', backend_draft(form, {
        'name': 'rt_hash', 'table': f'{DATABASE}.lookup', 'method': 'HASH', 'columns': [{'name': 'code'}]}))
    assert 'SPATIAL KEY `rt_sp` (`spot`)' in show_create('places')
    assert 'KEY `rt_hash` (`code`) USING HASH' in show_create('lookup')
    ddl = show_create('docs')
    assert 'UNIQUE KEY `rt_ix` (`a`(10) DESC,((`b` + 1))) USING BTREE' in ddl and "COMMENT 'round trip'" in ddl
    assert '/*!80000 INVISIBLE */' in ddl and 'SECONDARY_ENGINE_ATTRIBUTE' in ddl
    assert 'FULLTEXT KEY `rt_ft` (`body`) /*!50100 WITH PARSER `ngram` */' in ddl
    assert 'KEY `rt_kb` (`a`) KEY_BLOCK_SIZE=' in show_create('packed')
    index, baseline = record(client, route, 'index', 'rt_ix', 'index')
    assert baseline['new_name'] == 'rt_ix' and baseline['visible'] is False
    alter = backend_draft(form, {**baseline, 'new_name': 'rt_ix2', 'visible': True}, mode='alter', baseline=baseline)
    assert alter == {'new_name': 'rt_ix2', 'visible': True}
    run(client, route, 'index', 'alter', alter, target=index)
    assert query(f"SELECT IS_VISIBLE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='{DATABASE}' "
                 "AND INDEX_NAME='rt_ix2' LIMIT 1") == [('YES',)]
    _index, after = record(client, route, 'index', 'rt_ix2', 'index')
    assert after['new_name'] == 'rt_ix2' and after['visible'] is True
