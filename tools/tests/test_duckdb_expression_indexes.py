"""Native typed index expressions must survive facade and DDN replay."""
from types import SimpleNamespace
import duckdb
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration
from ui_descriptor_roundtrip import backend_draft, resolved_form


@pytest.fixture
def native(tmp_path):
    path = tmp_path / 'indexes.duckdb'
    connection = duckdb.connect(str(path))
    connection.execute('CREATE TABLE owned(id INTEGER, label VARCHAR)')
    connection.execute("INSERT INTO owned VALUES (1,'ONE'),(2,'TWO')")
    connection.close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    source = client.open_session({'route': route})
    try:
        yield client, source, route
    finally:
        client.close()


def request(route, **draft):
    return {'resource_kind': 'index', 'operation_id': 'create', '_provider_route': route,
        'draft': {'name': 'owned_index', 'table': 'main.owned', **draft}}


def test_descriptor_facade_native_create_definition_query_and_ddn_replay(native):
    client, source, route = native
    form = resolved_form('duckdb', 'index')
    draft = backend_draft(form, {'name': 'owned_index', 'table': 'main.owned',
        'method': 'ART', 'terms': [{'kind': 'expression', 'value': 'lower(label)'},
                                  {'kind': 'column', 'value': 'id'}]})
    facade = ProviderVisualAdministration(SimpleNamespace(endpoint_id='owned', mode='direct', runtime_verification_state='verified'),
        SimpleNamespace(require=lambda *_: None), 'duckdb', '1.5.2', client)
    value = {**request(route), 'draft': draft}
    assert not facade.validate(value)['errors']
    plan = facade.plan(value)
    assert plan['command_preview']['native_index_capabilities']['admitted_methods'] == ['ART']
    result = facade.apply({'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True})
    assert result['provider_result']['accepted']
    source.rollback()  # Refresh the caller's opening catalog snapshot explicitly.
    sql = source.execute("SELECT sql FROM duckdb_indexes() WHERE index_name='owned_index'").fetchone()[0]
    assert 'lower' in sql and 'id' in sql
    assert source.execute("SELECT id FROM owned WHERE lower(label)='one'").fetchall() == [(1,)]
    from pgadmin.cdeadmin.workspace.duckdb_schema_plan import _validated_replayed_index
    database = source.execute('SELECT current_database()').fetchone()[0]
    path = [database, 'main', 'owned', 'owned_index']
    replay = _validated_replayed_index({'name': 'owned_index', 'path': path,
        'native': {'ddl': sql, 'catalog_metadata': {'unique': False, 'primary': False, 'tags': {}}}},
        '.'.join('"' + part.replace('"','""') + '"' for part in path[:3]))
    source.execute('DROP INDEX owned_index')
    source.execute(replay)
    assert source.execute("SELECT count(*) FROM duckdb_indexes() WHERE index_name='owned_index'").fetchone()[0] == 1


def test_unique_expression_constraint_and_invalid_native_dependency_refusal(native):
    client, source, route = native
    plan = client.plan_admin_operation(request(route, unique=True,
        terms=[{'kind': 'expression', 'value': 'lower(label)'}]))
    assert client.apply_admin_operation(plan)['accepted']
    with pytest.raises(duckdb.ConstraintException):
        source.execute("INSERT INTO owned VALUES (3,'one')")
    source.rollback()  # Native constraint refusal aborts this caller-owned transaction.
    assert source.execute('SELECT count(*) FROM owned').fetchone()[0] == 2
    missing = client.plan_admin_operation(request(route, name='missing_index',
        terms=[{'kind': 'expression', 'value': 'unknown_column+1'}]))
    with pytest.raises(RelationalClientError, match='BinderException'):
        client.apply_admin_operation(missing)
    assert not source.execute("SELECT index_name FROM duckdb_indexes() WHERE index_name='missing_index'").fetchall()


@pytest.mark.parametrize('draft', [
    {'terms': [{'kind': 'expression', 'value': 'id);DROP TABLE owned;--'}]},
    {'terms': [{'kind': 'expression', 'value': 'id,label'}]},
    {'terms': [{'kind': 'unknown', 'value': 'id'}]},
    {'terms': [{'kind': 'column', 'value': 'id', 'ignored': True}]},
    {'terms': [{'kind': 'column', 'value': 'id'}], 'columns': ['label']},
    {'terms': [{'kind': 'column', 'value': 'id'}], 'method': 'unqualified_method'},
    {'terms': [{'kind': 'column', 'value': 'id'}], 'index_options': {'silently_ignored': True}},
])
def test_invalid_or_unqualified_inputs_fail_before_native_mutation(native, draft):
    client, source, route = native
    with pytest.raises(RelationalClientError):
        client.plan_admin_operation(request(route, **draft))
    assert source.execute('SELECT count(*) FROM owned').fetchone()[0] == 2
    assert source.execute('SELECT count(*) FROM duckdb_indexes()').fetchone()[0] == 0


def test_plan_parses_but_never_evaluates_an_expression(native):
    client, source, route = native
    calls = []
    source.create_function('owned_observer', lambda x: calls.append(x) or x, ['INTEGER'], 'INTEGER')
    client.plan_admin_operation(request(route, terms=[{'kind':'expression', 'value':'owned_observer(id)'}]))
    assert calls == []
