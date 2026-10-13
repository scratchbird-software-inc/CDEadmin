"""DuckDB native definition forms retain exact whole-object replacement intent."""

from copy import deepcopy

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def _request(resource, path, operation, draft):
    return {'resource_kind': resource['resource_kind'], 'operation_id': operation,
        'target_resource': resource,
        '_provider_route': {'database': str(path), 'filesystem_root': str(path.parent)},
        'draft': draft}


def _resource(connection, kind, name):
    return next(item for item in _resources(connection, {})
        if item['resource_kind'] == kind and item['display_name'] == name)


def test_native_view_form_uses_replace_and_rename_grammar(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    connection = duckdb.connect(str(path))
    try:
        connection.execute('CREATE VIEW projected AS SELECT 1 AS x')
        resource = _resource(connection, 'view', 'projected')
        operations = ADMINISTRATION.catalog(catalog_for_engine('duckdb'))
        view = next(item for item in operations['objects'] if item['resource_kind'] == 'view')
        assert {item['operation_id'] for item in view['operations']} >= {
            'alter', 'rename'}
        form = ADMINISTRATION._form('view', 'alter')
        assert [item['field_id'] for item in form['fields']] == [
            'query', 'complete_definition_confirmed', 'metadata_reset_acknowledged']
        request = _request(resource, path, 'alter', {'query': 'SELECT 2 AS x',
            'complete_definition_confirmed': True, 'metadata_reset_acknowledged': True})
        assert ADMINISTRATION.validate(request)['errors'] == []
        plan = ADMINISTRATION.plan(request)
        source = plan['command_preview']['statements'][0]['source']
        assert source == 'CREATE OR REPLACE VIEW "owned"."main"."projected" AS SELECT 2 AS x'
        client = _create_client()
        try:
            assert ADMINISTRATION.apply(client, plan)['accepted']
        finally:
            client.close()
        assert connection.execute('SELECT x FROM projected').fetchone() == (2,)
        renamed = ADMINISTRATION.plan(_request(resource, path, 'rename', {'new_name': 'renamed'}))
        rename_source = renamed['command_preview']['statements'][0]['source']
        assert rename_source == 'ALTER VIEW "owned"."main"."projected" RENAME TO "renamed"'
        client = _create_client()
        try:
            assert ADMINISTRATION.apply(client, renamed)['accepted']
        finally:
            client.close()
        assert connection.execute('SELECT x FROM renamed').fetchone() == (2,)
        missing = deepcopy(request)
        missing['draft']['metadata_reset_acknowledged'] = False
        assert ADMINISTRATION.validate(missing)['errors']
        with pytest.raises(RelationalClientError, match='metadata-reset acknowledgement'):
            ADMINISTRATION.plan(missing)
    finally:
        connection.close()


def test_native_macro_form_requires_complete_exact_statement(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    connection = duckdb.connect(str(path))
    try:
        connection.execute('CREATE MACRO overloaded(x) AS x + 1, (x, y) AS x + y')
        resource = _resource(connection, 'macro', 'overloaded')
        assert [item['field_id'] for item in ADMINISTRATION._form('macro', 'alter')['fields']] == [
            'source', 'complete_definition_confirmed', 'metadata_reset_acknowledged']
        source = ('CREATE OR REPLACE MACRO "owned"."main"."overloaded" '
                  '(x) AS x + 2, (x, y) AS x + y + 1')
        request = _request(resource, path, 'alter', {'source': source,
            'complete_definition_confirmed': True, 'metadata_reset_acknowledged': True})
        assert ADMINISTRATION.validate(request)['errors'] == []
        plan = ADMINISTRATION.plan(request)
        assert plan['command_preview']['statements'][0]['source'] == source
        assert plan['command_preview']['provider_constructed'] is False
        client = _create_client()
        try:
            assert ADMINISTRATION.apply(client, plan)['accepted']
        finally:
            client.close()
        assert connection.execute('SELECT overloaded(5), overloaded(5, 6)').fetchone() == (7, 12)
        wrong_target = deepcopy(request)
        wrong_target['draft']['source'] = source.replace('"overloaded"', '"other"')
        assert ADMINISTRATION.validate(wrong_target)['errors']
        legacy = deepcopy(request)
        legacy['draft'] = {'parameters': ['x'], 'expression': 'x + 9',
            'complete_definition_confirmed': True, 'metadata_reset_acknowledged': True}
        assert ADMINISTRATION.validate(legacy)['errors']
    finally:
        connection.close()


def test_native_macro_form_can_preserve_authored_default_arguments(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    connection = duckdb.connect(str(path))
    try:
        connection.execute('CREATE MACRO optional_arg(x, y := 5) AS x + y')
        resource = _resource(connection, 'macro', 'optional_arg')
        source = ('CREATE OR REPLACE MACRO "owned"."main"."optional_arg" '
                  '(x, y := 7) AS x + y')
        request = _request(resource, path, 'alter', {'source': source,
            'complete_definition_confirmed': True, 'metadata_reset_acknowledged': True})
        assert ADMINISTRATION.validate(request)['errors'] == []
        connection.execute(ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source'])
        assert connection.execute('SELECT optional_arg(1)').fetchone() == (8,)
    finally:
        connection.close()
