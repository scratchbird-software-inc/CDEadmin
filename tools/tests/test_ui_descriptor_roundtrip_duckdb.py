"""DuckDB family forms round-trip (README step 8): draft through the descriptor
fields -> provider plan -> apply on a real database file -> re-inspect."""
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

duckdb = pytest.importorskip('duckdb')
pytest.importorskip('pyarrow')

from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources  # noqa: E402
from ui_descriptor_roundtrip import backend_draft, record_draft, resolved_form  # noqa: E402


@pytest.fixture
def live(tmp_path):
    path = tmp_path / 'owned.duckdb'
    connection = duckdb.connect(str(path))
    connection.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY, label VARCHAR)')
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    try:
        yield path, route, client, connection
    finally:
        client.close()
        connection.close()


def resource(connection, kind, name):
    return next(row for row in _resources(connection, {}) if row['resource_kind'] == kind and row['display_name'] == name)


def run(client, route, kind, operation, draft, target=None):
    request = {'resource_kind': kind, 'operation_id': operation, 'target_resource': target,
               '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    planned = ADMINISTRATION.plan(request)
    sql = planned['command_preview']['statements'][0]['source']
    assert ADMINISTRATION.apply(client, planned)['accepted'], sql
    return sql


def test_table_sequence_type_and_view_forms(live):
    path, route, client, connection = live
    table_form = resolved_form('duckdb', 'table')
    draft = backend_draft(table_form, {
        'name': 'orders', 'parent': 'main',
        'columns': [{'name': 'id', 'type': 'INTEGER', 'nullable': False, 'primary_key': True},
                    {'name': 'owner_id', 'type': 'INTEGER'}, {'name': 'note', 'type': 'VARCHAR'}],
        'primary_key': [], 'unique_constraints': [{'name': 'uq', 'columns': ['note']}],
        'foreign_keys': [{'name': 'fk', 'columns': ['owner_id'], 'references_table': 'owner', 'references_columns': ['id']}],
        'check_constraints': [{'name': 'ck', 'expression': 'length(note) > 0'}],
    })
    sql = run(client, route, 'table', 'create', draft)
    assert 'CONSTRAINT "fk" FOREIGN KEY ("owner_id") REFERENCES "owner" ("id")' in sql
    table = resource(connection, 'table', 'orders')
    baseline = record_draft(table_form, {**table['native'], 'name': table['display_name']})
    assert [(row['name'], row['type']) for row in baseline['columns']][:2] == [('id', 'INTEGER'), ('owner_id', 'INTEGER')]
    # alter through the grid diff
    edited = {**baseline, 'columns': baseline['columns'] + [{'name': 'amount', 'type': 'DOUBLE'}]}
    alter = backend_draft(table_form, edited, mode='alter', baseline=baseline)
    assert alter['add_columns'] == [{'name': 'amount', 'type': 'DOUBLE'}]
    run(client, route, 'table', 'alter', alter, target=table)
    assert 'amount' in [row[0] for row in connection.execute("select column_name from information_schema.columns where table_name='orders'").fetchall()]

    run(client, route, 'sequence', 'create',
        backend_draft(resolved_form('duckdb', 'sequence'), {'name': 'order_seq', 'parent': 'main', 'start': 10, 'increment': 5, 'cycle': False}))
    assert connection.execute("select nextval('order_seq')").fetchone()[0] == 10

    type_form = resolved_form('duckdb', 'type')
    run(client, route, 'type', 'create',
        backend_draft(type_form, {'name': 'mood', 'type_kind': 'ENUM', 'enum_values': [{'value': 'happy'}, {'value': 'sad'}]}))
    assert connection.execute("select 'sad'::mood").fetchone()[0] == 'sad'

    run(client, route, 'view', 'create',
        backend_draft(resolved_form('duckdb', 'view'), {'name': 'owner_names', 'parent': 'main', 'query': 'SELECT label FROM owner'}))
    assert connection.execute('select count(*) from owner_names').fetchone()[0] == 0


def test_index_and_macro_forms(live):
    path, route, client, connection = live
    run(client, route, 'index', 'create',
        backend_draft(resolved_form('duckdb', 'index'), {'name': 'ix_owner_label', 'parent': 'main', 'table': 'owner',
                                                          'columns': [{'value': 'label'}], 'unique': False}))
    assert connection.execute("select index_name from duckdb_indexes()").fetchall() == [('ix_owner_label',)]
    routine_form = resolved_form('duckdb', 'routine')
    run(client, route, 'macro', 'create',
        backend_draft(routine_form, {'name': 'double_it', 'parameters': [{'name': 'x', 'default': ''}], 'expression': 'x * 2', 'table_macro': False,
                                     'complete_definition_confirmed': True, 'metadata_reset_acknowledged': True}))
    assert connection.execute('select double_it(21)').fetchone()[0] == 42


def test_database_form_creates_a_database_file(live):
    path, route, client, connection = live
    form = resolved_form('duckdb', 'database')
    route = {**route, 'database_create_root': route['filesystem_root']}
    draft = backend_draft(form, {'name': 'child', 'config': {'threads': '2'}})
    request = {'resource_kind': 'database', 'operation_id': 'create', 'target_resource': None, '_provider_route': route, 'draft': draft}
    assert ADMINISTRATION.validate(request)['errors'] == []
    result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(request))
    assert result['accepted'], result
    child = Path(route['filesystem_root']) / 'child.duckdb'
    assert child.exists()
    probe = duckdb.connect(str(child))
    assert probe.execute('select 1').fetchone() == (1,)
    probe.close()
