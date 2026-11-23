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

    typed_draft = backend_draft(form, {
        'name': 'typed_child',
        'config_threads': 2,
        'config_default_order': 'DESC',
        'config_preserve_insertion_order': 'true',
    })
    assert typed_draft['config'] == {
        'threads': 2,
        'default_order': 'DESC',
        'preserve_insertion_order': 'true',
    }
    typed_req = {
        'resource_kind': 'database', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': typed_draft,
    }
    assert ADMINISTRATION.validate(typed_req)['errors'] == []
    assert ADMINISTRATION.apply(client, ADMINISTRATION.plan(typed_req))['accepted']
    assert (Path(route['filesystem_root']) / 'typed_child.duckdb').exists()


def test_column_facets_and_engine_object_forms(live):
    path, route, client, connection = live
    schema_form = resolved_form('duckdb', 'engine_object:schema')
    run(client, route, 'schema', 'create', backend_draft(schema_form, {'name': 'analytics'}))
    schema_res = resource(connection, 'schema', 'analytics')
    assert schema_res['display_name'] == 'analytics'

    table_form = resolved_form('duckdb', 'table')
    rich_draft = backend_draft(table_form, {
        'name': 'customers',
        'parent': 'analytics',
        'columns': [
            {'name': 'id', 'type': 'INTEGER', 'nullable': False, 'primary_key': True},
            {'name': 'handle', 'type': 'VARCHAR', 'collation': 'NOCASE', 'nullable': False, 'comment': 'Case-insensitive handle'},
            {'name': 'handle_upper', 'type': 'VARCHAR', 'generated_expression': 'upper(handle)'},
        ],
        'primary_key': [], 'unique_constraints': [], 'foreign_keys': [], 'check_constraints': [],
    })
    req = {
        'resource_kind': 'table', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': rich_draft,
    }
    assert ADMINISTRATION.validate(req)['errors'] == []
    planned = ADMINISTRATION.plan(req)
    assert len(planned['command_preview']['statements']) == 2
    assert 'COLLATE NOCASE' in planned['command_preview']['statements'][0]['source']
    assert 'GENERATED ALWAYS AS (upper(handle))' in planned['command_preview']['statements'][0]['source']
    assert 'COMMENT ON COLUMN' in planned['command_preview']['statements'][1]['source']
    assert ADMINISTRATION.apply(client, planned)['accepted']

    connection.execute("INSERT INTO analytics.customers (id, handle) VALUES (1, 'alice')")
    assert connection.execute("SELECT handle = 'ALICE', handle_upper FROM analytics.customers").fetchone() == (True, 'ALICE')
    col_comment = connection.execute(
        "SELECT comment FROM duckdb_columns() WHERE schema_name='analytics' AND table_name='customers' AND column_name='handle'"
    ).fetchone()[0]
    assert col_comment == 'Case-insensitive handle'

    invalid_gen = backend_draft(table_form, {
        'name': 'bad_gen',
        'columns': [{'name': 'g', 'type': 'VARCHAR', 'default': "'x'", 'generated_expression': "'x'"}],
        'primary_key': [], 'unique_constraints': [], 'foreign_keys': [], 'check_constraints': [],
    })
    assert ADMINISTRATION.validate({
        'resource_kind': 'table', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': invalid_gen,
    })['errors'] != []

    col_form = resolved_form('duckdb', 'engine_object:column')
    col_draft = backend_draft(col_form, {
        'table': 'analytics.customers',
        'name': 'region',
        'data_type': 'VARCHAR',
        'collation': 'NOCASE',
        'comment': 'Customer region',
    })
    col_req = {
        'resource_kind': 'column', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': col_draft,
    }
    assert ADMINISTRATION.validate(col_req)['errors'] == []
    assert ADMINISTRATION.apply(client, ADMINISTRATION.plan(col_req))['accepted']
    assert connection.execute(
        "SELECT comment FROM duckdb_columns() WHERE schema_name='analytics' AND table_name='customers' AND column_name='region'"
    ).fetchone()[0] == 'Customer region'

    mat_form = resolved_form('duckdb', 'engine_object:materialization')
    run(client, route, 'materialization', 'create', backend_draft(mat_form, {
        'name': 'customer_rollup',
        'parent': 'analytics',
        'select': 'SELECT count(*) AS total_customers FROM analytics.customers',
    }))
    assert connection.execute('SELECT total_customers FROM analytics.customer_rollup').fetchone() == (1,)

    secret_form = resolved_form('duckdb', 'engine_object:secret')
    secret_draft = backend_draft(secret_form, {
        'name': 'ui_http_secret',
        'secret_type': 'HTTP',
        'persistence_mode': 'TEMPORARY',
        'scope': 'https://example.invalid/api/',
        'properties': {'bearer_token': 'super-secret-token'},
    })
    secret_req = {
        'resource_kind': 'secret', 'operation_id': 'create',
        'target_resource': None, '_provider_route': route, 'draft': secret_draft,
    }
    assert ADMINISTRATION.validate(secret_req)['errors'] == []
    secret_plan = ADMINISTRATION.plan(secret_req)
    assert 'super-secret-token' not in secret_plan['command_preview']['statements'][0]['source']
    sess = client._connect({'route': route})
    try:
        secret_applied = ADMINISTRATION.apply(client, secret_plan, connection=sess)
        assert secret_applied['accepted']
        all_rows = _resources(sess, {})
    finally:
        client._forget_and_close(sess)

    secret_res = next(r for r in all_rows if r['resource_kind'] == 'secret' and r['display_name'] == 'ui_http_secret')
    assert record_draft(secret_form, {**secret_res['native'], 'name': secret_res['display_name']})['secret_type'].upper() == 'HTTP'

    constraint_form = resolved_form('duckdb', 'engine_object:constraint')
    constraint_res = next(r for r in all_rows if r['resource_kind'] == 'constraint')
    assert record_draft(constraint_form, {**constraint_res['native'], 'name': constraint_res['display_name']})['constraint_type']

    fn_form = resolved_form('duckdb', 'engine_object:function')
    fn_res = next(r for r in all_rows if r['resource_kind'] == 'function')
    assert record_draft(fn_form, {**fn_res['native'], 'name': fn_res['display_name']})['function_type']

    ext_form = resolved_form('duckdb', 'engine_object:extension')
    ext_res = next(r for r in all_rows if r['resource_kind'] == 'extension')
    assert 'installed' in record_draft(ext_form, {**ext_res['native'], 'name': ext_res['display_name']})

