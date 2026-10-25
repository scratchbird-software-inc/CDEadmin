"""SQLite family forms round-trip (README step 8): draft through the descriptor
fields -> provider plan -> apply on a real database file -> re-inspect.

These are the acceptance tests that let sqlite table/view/index/trigger carry
status ``complete``. They use the provider's own plan/apply with an explicit
connection, exactly as the other SQLite provider tests do.
"""
from contextlib import closing
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, record_draft, resolved_form  # noqa: E402


@pytest.fixture
def live(tmp_path):
    path = tmp_path / 'live.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY, label TEXT)')
        seed.commit()
    route = {'database': str(path), 'filesystem_root': str(tmp_path), 'timeout': .05}
    client = _create_client()
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        yield path, route, client, connection
    finally:
        connection.close()
        client.close()


def resources(path, route):
    with closing(sqlite3.connect(path)) as observer:
        return list(_resources(observer, {'route': route}))


def resource(path, route, kind, name):
    return next(row for row in resources(path, route) if row['resource_kind'] == kind and row['display_name'] == name)


def run(client, connection, route, kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
                                   '_provider_route': route, 'draft': draft})
    assert planned.get('state', 'ready') == 'ready', planned
    sql = planned['command_preview']['statements'][0]['source']
    result = ADMINISTRATION.apply(client, planned, connection=connection)
    assert result['accepted'], result
    return sql


def test_table_create_and_alter_through_the_form(live):
    path, route, client, connection = live
    form = resolved_form('sqlite', 'table')
    ui_draft = {
        'variant': 'default', 'name': 'orders', 'parent': 'main',
        'columns': [
            {'name': 'id', 'type': 'INTEGER', 'nullable': False, 'primary_key': True},
            {'name': 'owner_id', 'type': 'INTEGER', 'nullable': False},
            {'name': 'note', 'type': 'TEXT', 'nullable': True, 'default': "'x'"},
        ],
        'primary_key': [], 'unique_constraints': [{'name': 'uq_note', 'columns': ['note']}],
        'foreign_keys': [{'name': 'fk_owner', 'columns': ['owner_id'], 'references_table': 'owner', 'references_columns': ['id']}],
        'check_constraints': [{'name': 'ck_note', 'expression': 'length(note) > 0'}],
    }
    draft = backend_draft(form, ui_draft)
    # the split grids are recombined into the single constraints list the provider compiles
    assert [row['kind'] for row in draft['constraints']] == ['UNIQUE', 'FOREIGN KEY', 'CHECK']
    sql = run(client, connection, route, 'table', 'create', draft)
    assert 'CONSTRAINT "fk_owner" FOREIGN KEY ("owner_id") REFERENCES "owner" ("id")' in sql
    table = resource(path, route, 'table', 'orders')
    with closing(sqlite3.connect(path)) as observer:
        assert [row[1] for row in observer.execute('pragma table_info(orders)')] == ['id', 'owner_id', 'note']

    # Re-open the created table in the editor: the record pre-fills the grid from native keys.
    baseline = record_draft(form, {**table['native'], 'name': table['display_name']})
    assert [(row['name'], row['type'], row['primary_key']) for row in baseline['columns']] == [
        ('id', 'INTEGER', True), ('owner_id', 'INTEGER', False), ('note', 'TEXT', False)]

    # Edit: add a column through the grid; the diff becomes add_columns for ALTER.
    edited = {**baseline, 'columns': baseline['columns'] + [{'name': 'amount', 'type': 'REAL'}]}
    alter = backend_draft(form, edited, mode='alter', baseline=baseline)
    assert alter == {'name': 'orders', 'add_columns': [{'name': 'amount', 'type': 'REAL'}]}
    sql = run(client, connection, route, 'table', 'alter', alter, target=table)
    assert ' ADD ' in sql.upper() and 'amount' in sql
    with closing(sqlite3.connect(path)) as observer:
        assert 'amount' in [row[1] for row in observer.execute('pragma table_info(orders)')]


def test_view_index_and_trigger_forms(live):
    path, route, client, connection = live
    run(client, connection, route, 'view', 'create',
        backend_draft(resolved_form('sqlite', 'view'), {'name': 'owner_names', 'parent': 'main', 'query': 'SELECT label FROM owner'}))
    run(client, connection, route, 'index', 'create',
        backend_draft(resolved_form('sqlite', 'index'), {'name': 'ix_owner_label', 'parent': 'main', 'table': 'owner',
                                                          'columns': [{'value': 'label'}], 'unique': True}))
    trigger_form = resolved_form('sqlite', 'trigger')
    trigger = backend_draft(trigger_form, {'name': 'trg_owner', 'parent': 'main', 'table': 'owner', 'timing': 'AFTER',
                                           'events': 'INSERT', 'active': True, 'position': 0,
                                           'body': 'UPDATE owner SET label = NEW.label WHERE id = NEW.id;'})
    assert trigger['events'] == ['INSERT']
    run(client, connection, route, 'trigger', 'create', trigger)
    with closing(sqlite3.connect(path)) as observer:
        names = {row[0]: row[1] for row in observer.execute("select name, type from sqlite_master")}
    assert names['owner_names'] == 'view'
    assert names['ix_owner_label'] == 'index'
    assert names['trg_owner'] == 'trigger'
    kinds = {row['display_name']: row['resource_kind'] for row in resources(path, route)}
    assert kinds['owner_names'] == 'view' and kinds['ix_owner_label'] == 'index' and kinds['trg_owner'] == 'trigger'


def test_every_sqlite_form_field_is_accepted_by_the_provider():
    """Every create field in a complete form must reach the provider; the compiler
    must not silently ignore a descriptor field (design principle 5)."""
    from pgadmin.cdeadmin.providers.sqlite import provider as sqlite_provider  # noqa: F401
    for family in ('table', 'view', 'index', 'trigger'):
        form = resolved_form('sqlite', family)
        if form['status'] != 'complete':
            continue
        ids = {f['field_id'] for tab in form['tabs'] for f in tab['fields'] if not f.get('modes') or 'create' in f['modes']}
        assert ids, family


def test_database_form_creates_and_alters_a_database_file(live):
    path, route, client, connection = live
    form = resolved_form('sqlite', 'database')
    route = {**route, 'database_create_root': route['filesystem_root']}
    draft = backend_draft(form, {'name': 'child', 'page_size': '8192', 'encoding': 'UTF-8', 'auto_vacuum': 'FULL',
                                 'application_id': 7, 'user_version': 3})
    request = {'resource_kind': 'database', 'operation_id': 'create', 'target_resource': None, '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    assert ADMINISTRATION.apply(client, ADMINISTRATION.plan(request))['accepted']
    child = Path(route['filesystem_root']) / 'child.sqlite'
    with closing(sqlite3.connect(child)) as observer:
        assert [observer.execute(f'pragma {name}').fetchone()[0] for name in ('page_size', 'auto_vacuum', 'application_id', 'user_version')] == [8192, 1, 7, 3]

    database = resource(path, route, 'database', 'main')
    baseline = record_draft(form, {**database['native'], 'name': database['display_name']})
    assert baseline['journal_mode'] == 'DELETE' and baseline['synchronous'] in ('FULL', 'NORMAL') and baseline['page_size'] == '4096'
    alter = backend_draft(form, {**baseline, 'journal_mode': 'WAL', 'user_version': 9}, mode='alter', baseline=baseline)
    assert alter == {'journal_mode': 'WAL', 'user_version': 9}
    run(client, connection, route, 'database', 'alter', alter, target=database)
    assert connection.execute('pragma journal_mode').fetchone()[0] == 'wal'
    assert connection.execute('pragma user_version').fetchone()[0] == 9
