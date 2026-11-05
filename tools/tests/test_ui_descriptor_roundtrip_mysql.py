"""MySQL family forms round-trip (README step 8): draft through the
descriptor fields -> provider plan -> apply on a live server -> re-inspect.

Set ``CDEADMIN_ROUNDTRIP_MYSQL`` to a JSON object ``{"host", "port", "user",
"password"}`` for an account that may create databases and accounts (the demo's
root, ``dev.sh start mysql``). The test creates and drops its own database and
accounts. Skipped otherwise. Trigger and routine reviews also need MySQL Shell 9.7's
grammar library: set ``CDEADMIN_MYSQL_PARSER_LIBRARY`` (the demo runtime ships it at
``tools/reference_engine_demos/runtime/mysql/lib/mysqlsh/yparser/mysql_9.7.so``).
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
    try:
        applied = client.apply_admin_operation(planned)
    except Exception as error:
        raise AssertionError(f"{error} errno={getattr(error, 'errno', None)} "
                             f"sqlstate={getattr(error, 'sqlstate', None)}\n{sql}") from error
    assert applied['accepted'], sql
    return sql


VARIANTS = {'materialized-view': 'materialized', 'procedure': 'procedure', 'function': 'function',
            'event': 'scheduled'}  # capabilities.json; the editor host adds it to the record


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


def test_trigger_form_every_field_creates_and_reopens_locked(live):
    route, client = live
    form = resolved_form('mysql', 'trigger')
    query(f'CREATE TABLE `{DATABASE}`.audited(id INT PRIMARY KEY, label VARCHAR(40), note VARCHAR(40))')
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'rt_first', 'parent': DATABASE, 'table': 'audited', 'timing': 'BEFORE', 'event': 'UPDATE',
        'body': 'SET NEW.label = UPPER(NEW.label)'}))
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'rt_second', 'parent': DATABASE, 'table': 'audited', 'timing': 'BEFORE', 'event': 'UPDATE',
        'if_not_exists': True, 'body': 'SET NEW.note = TRIM(NEW.label)', 'order': 'PRECEDES',
        'other_trigger': 'rt_first', 'definer_user': 'root', 'definer_host': '%'}))
    # FOLLOWS/PRECEDES must name a trigger with the same timing and event (MySQL error 3011).
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'rt_third', 'parent': DATABASE, 'table': 'audited', 'timing': 'BEFORE', 'event': 'UPDATE',
        'body': 'SET NEW.note = CONCAT(NEW.note, \'!\')', 'order': 'FOLLOWS', 'other_trigger': 'rt_first'}))
    run(client, route, 'trigger', 'create', backend_draft(form, {
        'name': 'rt_after', 'parent': DATABASE, 'table': 'audited', 'timing': 'AFTER', 'event': 'DELETE',
        'body': 'SET @rt_deleted = OLD.id'}))
    rows = query(f"SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER, DEFINER FROM "
                 f"information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='{DATABASE}' ORDER BY TRIGGER_NAME")
    assert rows == [('rt_after', 'AFTER', 'DELETE', 1, 'root@%'), ('rt_first', 'BEFORE', 'UPDATE', 2, 'root@%'),
                    ('rt_second', 'BEFORE', 'UPDATE', 1, 'root@%'), ('rt_third', 'BEFORE', 'UPDATE', 3, 'root@%')]
    _trigger, reopened = record(client, route, 'trigger', 'rt_second', 'trigger')
    assert (reopened['name'], reopened['parent'], reopened['table']) == ('rt_second', DATABASE, 'audited')
    assert (reopened['timing'], reopened['event']) == ('BEFORE', 'UPDATE')
    assert reopened['body'] == 'SET NEW.note = TRIM(NEW.label)'
    assert (reopened['definer_user'], reopened['definer_host']) == ('root', '%')
    # Reopened, every stored property is locked: an unchanged edit sends nothing to alter.
    assert backend_draft(form, dict(reopened), mode='alter', baseline=reopened) == {}


def routine_facts(name):
    return query(f"SELECT ROUTINE_COMMENT, SECURITY_TYPE, SQL_DATA_ACCESS, IS_DETERMINISTIC, DEFINER "
                 f"FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='{DATABASE}' AND ROUTINE_NAME='{name}'")[0]


@pytest.mark.parametrize('kind,family', [('procedure', 'routine'), ('function', 'routine')])
def test_routine_forms_every_field_reopen_and_alter_characteristics(live, kind, family):
    route, client = live
    form = resolved_form('mysql', family)
    name = f'rt_{kind}'
    draft = {'variant': kind, 'name': name, 'parent': DATABASE, 'comment': 'first', 'if_not_exists': True,
             'security_create': 'INVOKER', 'data_access_create': 'READS SQL DATA', 'deterministic': True,
             'language': 'SQL', 'definer_user': 'root', 'definer_host': '%'}
    if kind == 'procedure':
        draft.update(parameters=[{'name': 'a', 'mode': 'IN', 'type': 'INT'},
                                 {'name': 'b', 'mode': 'OUT', 'type': 'VARCHAR(10)', 'character_set': 'latin1', 'collation': 'latin1_bin'},
                                 {'name': 'c', 'mode': 'INOUT', 'type': 'INT'}],
                     body="BEGIN SET b = 'x'; SET c = c + a; END")
    else:
        draft.update(parameters=[{'name': 'a', 'type': 'INT'}], returns='VARCHAR(20)', body="RETURN CONCAT('v', a)")
    run(client, route, kind, 'create', backend_draft(form, draft))
    assert routine_facts(name) == ('first', 'INVOKER', 'READS SQL DATA', 'YES', 'root@%')
    routine, reopened = record(client, route, kind, name, family)
    assert reopened['name'] == name and reopened['comment'] == 'first' and reopened['deterministic'] is True
    assert (reopened['security_alter'], reopened['data_access_alter']) == ('INVOKER', 'READS SQL DATA')
    assert reopened['body'] == draft['body'] and (reopened['definer_user'], reopened['definer_host']) == ('root', '%')
    assert [(row['name'], row.get('mode'), row['type'].lower()) for row in reopened['parameters']] == (
        [('a', 'IN', 'int'), ('b', 'OUT', 'varchar(10)'), ('c', 'INOUT', 'int')] if kind == 'procedure' else [('a', 'IN', 'int')])
    if kind == 'procedure':
        assert (reopened['parameters'][1]['character_set'], reopened['parameters'][1]['collation']) == ('latin1', 'latin1_bin')
    else:
        assert reopened['returns'].lower() == 'varchar(20)'
    edited = {**reopened, 'comment': 'second', 'security_alter': 'DEFINER', 'data_access_alter': 'NO SQL',
              'confirmation': name}
    alter = backend_draft(form, edited, mode='alter', baseline=reopened)
    assert alter == {'comment': 'second', 'sql_security': 'DEFINER', 'data_access': 'NO SQL', 'confirmation': name}
    run(client, route, kind, 'alter', alter, target=routine)
    assert routine_facts(name) == ('second', 'DEFINER', 'NO SQL', 'YES', 'root@%')


def event_facts(name):
    return query(f"SELECT EVENT_COMMENT, STATUS, ON_COMPLETION, EVENT_TYPE, INTERVAL_VALUE, INTERVAL_FIELD, "
                 f"EVENT_DEFINITION, DEFINER FROM information_schema.EVENTS WHERE EVENT_SCHEMA='{DATABASE}' "
                 f"AND EVENT_NAME='{name}'")[0]


def test_scheduled_event_variant_every_field_reopen_and_alter(live):
    route, client = live
    form = resolved_form('mysql', 'routine')
    run(client, route, 'event', 'create', backend_draft(form, {
        'variant': 'scheduled', 'name': 'rt_event', 'database': DATABASE, 'if_not_exists': True,
        'event_comment': 'nightly', 'body_create': 'SET @rt_event = 1',
        'schedule_create': "EVERY 2 HOUR STARTS '2030-01-01 00:00:00' ENDS '2031-01-01 00:00:00'",
        'completion_create': 'PRESERVE', 'status_create': 'DISABLE', 'time_zone': '+00:00',
        'event_definer_user': 'root', 'event_definer_host': '%'}))
    assert event_facts('rt_event') == ('nightly', 'DISABLED', 'PRESERVE', 'RECURRING', '2', 'HOUR',
                                       'SET @rt_event = 1', 'root@%')
    event, reopened = record(client, route, 'event', 'rt_event', 'routine')
    assert reopened['variant'] == 'scheduled' and reopened['event_comment'] == 'nightly'
    assert reopened['schedule_alter'] == "EVERY 2 HOUR STARTS '2030-01-01 00:00:00' ENDS '2031-01-01 00:00:00'"
    assert (reopened['completion_alter'], reopened['status_alter']) == ('PRESERVE', 'DISABLE')
    assert reopened['body_alter'] == 'SET @rt_event = 1' and reopened['time_zone'] == '+00:00'
    assert (reopened['event_definer_user'], reopened['event_definer_host']) == ('root', '%')
    edited = {**reopened, 'status_alter': 'ENABLE', 'schedule_alter': 'EVERY 1 DAY', 'body_alter': 'SET @rt_event = 2',
              'event_comment': 'daily', 'completion_alter': 'NOT PRESERVE', 'confirmation': 'rt_event'}
    alter = backend_draft(form, edited, mode='alter', baseline=reopened)
    assert alter == {'status': 'ENABLE', 'schedule': 'EVERY 1 DAY', 'body': 'SET @rt_event = 2', 'comment': 'daily',
                     'completion': 'NOT PRESERVE', 'confirmation': 'rt_event'}
    run(client, route, 'event', 'alter', alter, target=event)
    assert event_facts('rt_event')[:7] == ('daily', 'ENABLED', 'NOT PRESERVE', 'RECURRING', '1', 'DAY', 'SET @rt_event = 2')
    # An edit of one option leaves the rest as they are.
    _event, again = record(client, route, 'event', 'rt_event', 'routine')
    run(client, route, 'event', 'alter', backend_draft(form, {**again, 'status_alter': 'DISABLE', 'confirmation': 'rt_event'},
                                                       mode='alter', baseline=again), target=event)
    assert event_facts('rt_event')[:7] == ('daily', 'DISABLED', 'NOT PRESERVE', 'RECURRING', '1', 'DAY', 'SET @rt_event = 2')
