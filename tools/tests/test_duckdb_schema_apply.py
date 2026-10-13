"""DuckDB DDN review claims one native statement and never replays it."""

from copy import deepcopy
from dataclasses import dataclass
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client, _resource_id
from pgadmin.cdeadmin.providers.duckdb.schema_application import apply_review
from pgadmin.cdeadmin.workspace.duckdb_schema_apply import DuckDBSchemaApplications
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
from pgadmin.cdeadmin.operations.store import JsonOperationStore


def fixture(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb'
    connection = duckdb.connect(str(path)); connection.execute('CREATE TABLE existing(id INTEGER)'); connection.close()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    observed = provider.capture_catalog(route)
    baseline = build_export(observed['resources'], endpoint_id='endpoint-1', target_id='file-1',
        generation=observed['generation'], refreshed=True, engine='duckdb', native_model=True)
    desired = deepcopy(baseline)
    root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
    path_parts = [root, 'main', 'extra']
    identity = _resource_id('table', path_parts[:-1], path_parts[-1])
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'table', 'name': 'extra',
        'path': path_parts, 'system': 'false', 'native': {'system_object': False,
            'catalog_metadata': {}, 'ddl': f'CREATE TABLE "{root}"."main"."extra" (x INTEGER)'}}
    return provider, route, baseline, desired, identity


def review(tmp_path):
    provider, route, baseline, desired, identity = fixture(tmp_path)
    preview = plan(baseline, desired, baseline)
    applications = DuckDBSchemaApplications(tmp_path/'receipts.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
    return provider, route, applications, receipt, identity


def request(receipt):
    return {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}


def test_native_creation_commits_and_rediscovery_receipt_is_not_replayed(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, applications, receipt, identity = review(tmp_path)
    try:
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed' and result['outcome']['rediscovery_verified']
        assert result['outcome']['rediscovered_resource_id'] == identity
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='extra'").fetchone()[0] == 1
        observer.close()
        replay = Mock()
        assert applications.apply(request(receipt), 'owner', 'binding', replay) == result
        replay.assert_not_called()
    finally:
        provider.client.close()


def test_intervening_table_refuses_native_dispatch(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, applications, receipt, _identity = review(tmp_path)
    competing = duckdb.connect(route['database'])
    competing.execute('CREATE TABLE extra(x VARCHAR)'); competing.close()
    try:
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'not_dispatched'
        assert result['outcome']['native_rollback_returned']
        assert 'changed since review' in result['outcome']['rejection_reason']
    finally:
        provider.client.close()


def test_file_identity_change_refuses_reviewed_dispatch(tmp_path):
    provider, route, baseline, desired, _identity = fixture(tmp_path)
    preview = plan(baseline, desired, baseline)
    applications = DuckDBSchemaApplications(tmp_path/'receipts.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1',
        file_identity=[0, 0])
    try:
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'not_dispatched'
        assert outcome['outcome']['error_type'] == 'ValueError'
    finally:
        provider.client.close()


def test_durable_claim_survives_worker_loss_and_is_owner_bound(tmp_path):
    provider, _route, applications, receipt, _identity = review(tmp_path)
    class WorkerLoss(BaseException): pass
    try:
        with pytest.raises(WorkerLoss):
            applications.apply(request(receipt), 'owner', 'binding',
                lambda _record: (_ for _ in ()).throw(WorkerLoss()))
        restarted = DuckDBSchemaApplications(tmp_path/'receipts.json')
        execute = Mock()
        observed = restarted.apply(request(receipt), 'owner', 'binding', execute)
        assert observed['state'] == 'unknown_outcome'
        execute.assert_not_called()
        with pytest.raises(ValueError, match='unavailable'):
            restarted.get(receipt['review_id'], 'other', 'binding')
    finally:
        provider.client.close()


def test_workspace_review_binds_file_identity_and_rejects_foreign_receipt(tmp_path):
    provider, route, baseline, desired, identity = fixture(tmp_path)
    observed = provider.capture_catalog(route)
    addition = desired['rows'][identity]
    native_resource = {'resource_id': identity, 'resource_kind': 'table',
        'display_name': addition['name'], 'display_path': addition['path'],
        'native': addition['native']}
    common = {'endpoint_id': 'endpoint-1', 'target_id': 'file-1',
        'generation': observed['generation'], 'engine': 'duckdb'}
    before = build_export(observed['resources'], **common)
    after = build_export([*observed['resources'], native_resource], **common)

    @dataclass
    class Context:
        endpoint_id: str = 'endpoint-1'
        provider_id: str = 'org.cdeadmin.duckdb'
        profile_id: str = 'duckdb-native'

    context = Context()
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, {'route': route}, None)),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    service.operation_bus = SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
    service.resource_service = SimpleNamespace(invalidate=Mock())
    service._principal_id = Mock(return_value=7)
    server = SimpleNamespace()
    body = {'database_target_id': 'file-1', 'baseline': json.dumps(before['snapshot']),
        'desired': json.dumps(after['snapshot'])}
    try:
        preview = service.duckdb_schema_plan(server, body)
        receipt = service.duckdb_schema_application(server, 'duckdb_schema_review', {
            **body, 'execution_sha256': preview['execution_sha256']})
        assert receipt['state'] == 'reviewed'
        with pytest.raises(ProviderWorkspaceError, match='unavailable'):
            service._principal_id.return_value = 8
            service.duckdb_schema_application(server, 'duckdb_schema_receipt', {
                'database_target_id': 'file-1', 'review_id': receipt['review_id']})
        service._principal_id.return_value = 7
        applied = service.duckdb_schema_application(server, 'duckdb_schema_apply', {
            'database_target_id': 'file-1', 'review_id': receipt['review_id'],
            'review_digest': receipt['review_digest'], 'confirmed': True})
        assert applied['state'] == 'committed' and applied['outcome']['rediscovery_verified']
        service.resource_service.invalidate.assert_called_once_with(context)
    finally:
        provider.client.close()


@pytest.mark.parametrize(('kind', 'schema', 'name', 'suffix'), [
    ('schema', None, 'additional', ''),
    ('view', 'main', 'projected', ' AS SELECT 1 AS x'),
    ('sequence', 'main', 'counter', ''),
    ('type', 'main', 'status', " AS ENUM ('ready', 'done')"),
    ('macro', 'main', 'plus_one', '(x) AS x + 1'),
])
def test_every_admitted_native_creation_kind_is_executed_and_rediscovered(tmp_path, kind, schema, name, suffix):
    provider, route, baseline, desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        desired = deepcopy(baseline)
        path = [root, name] if schema is None else [root, schema, name]
        identity = _resource_id(kind, path[:-1], name)
        target = '.'.join('"' + part + '"' for part in path)
        sql = f'CREATE {kind.upper()} {target}{suffix}'
        desired['rows'][identity] = {'resource_id': identity, 'kind': kind, 'name': name,
            'path': path, 'system': 'false', 'native': {'system_object': False,
                'catalog_metadata': {}, 'ddl': sql}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'receipts.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', (kind, result)
        assert result['outcome']['rediscovery_verified'], (kind, result)
    finally:
        provider.client.close()


def test_explicit_drop_and_view_replace_are_native_and_one_time(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE VIEW observed_view AS SELECT 1 AS x'); connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1', target_id='file-1',
            generation=observed['generation'], refreshed=True, engine='duckdb', native_model=True)
        for kind, name, change in (('view', 'observed_view', {'action': 'replace'}),
                                   ('table', 'existing', {'action': 'drop', 'confirmation': 'existing'})):
            current = next(row for row in baseline['rows'].values() if row['kind'] == kind and row['name'] == name)
            desired = deepcopy(baseline)
            after = desired['rows'][current['resource_id']]
            after['native']['duckdb_change'] = change
            if kind == 'view':
                catalog = current['path'][0]
                after['native']['ddl'] = f'CREATE OR REPLACE VIEW "{catalog}"."main"."observed_view" AS SELECT 2 AS x'
            preview = plan(baseline, desired, baseline)
            assert preview['application_supported'], preview['blockers']
            applications = DuckDBSchemaApplications(tmp_path/f'{kind}.json', clock=lambda: 100)
            receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
            result = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
            assert result['state'] == 'committed', result
            assert result['outcome']['rediscovery_verified'], result
            baseline = build_export(provider.capture_catalog(route)['resources'], endpoint_id='endpoint-1',
                target_id='file-1', generation='fresh', refreshed=True, engine='duckdb', native_model=True)
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT x FROM observed_view').fetchall() == [(2,)]
        assert observer.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='existing'").fetchone()[0] == 0
        observer.close()
    finally:
        provider.client.close()


def test_reviewed_index_creation_and_drop_use_native_table_identity(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        path = [root, 'main', 'existing', 'existing_id_ix']
        identity = _resource_id('index', path[:-1], path[-1])
        desired = deepcopy(baseline)
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'index',
            'name': 'existing_id_ix', 'path': path, 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {},
                'ddl': f'CREATE INDEX "existing_id_ix" ON "{root}"."main"."existing"("id")'}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'index-create.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed' and result['outcome']['rediscovery_verified'], result
        observed = provider.capture_catalog(route)
        fresh = build_export(observed['resources'], endpoint_id='endpoint-1', target_id='file-1',
            generation=observed['generation'], refreshed=True, engine='duckdb', native_model=True)
        assert identity in fresh['rows']
        remove = deepcopy(fresh)
        remove['rows'][identity]['native']['duckdb_change'] = {
            'action': 'drop', 'confirmation': 'existing_id_ix'}
        drop = plan(fresh, remove, fresh)
        assert drop['application_supported'] and drop['operations'][0]['source'] == (
            f'DROP INDEX "{root}"."main"."existing_id_ix" RESTRICT')
        applications = DuckDBSchemaApplications(tmp_path/'index-drop.json', clock=lambda: 100)
        receipt = applications.review(drop, fresh, remove, 'owner', 'binding', 'file-1')
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed' and result['outcome']['rediscovery_verified'], result
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT count(*) FROM duckdb_indexes() WHERE index_name='existing_id_ix'").fetchone() == (0,)
        observer.close()
    finally:
        provider.client.close()


def test_reviewed_nullable_column_add_and_drop_are_native(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        path = [root, 'main', 'existing', 'label']
        identity = _resource_id('column', path[:-1], path[-1])
        desired = deepcopy(baseline)
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'column',
            'name': 'label', 'path': path, 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {
                'data_type': 'VARCHAR', 'nullable': True, 'default': "'ready'"}}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'column-add.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        added = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert added['state'] == 'committed' and added['outcome']['rediscovery_verified'], added
        observed = provider.capture_catalog(route)
        fresh = build_export(observed['resources'], endpoint_id='endpoint-1', target_id='file-1',
            generation=observed['generation'], refreshed=True, engine='duckdb', native_model=True)
        assert identity in fresh['rows']
        remove = deepcopy(fresh)
        remove['rows'][identity]['native']['duckdb_change'] = {
            'action': 'drop', 'confirmation': 'label'}
        preview = plan(fresh, remove, fresh)
        assert preview['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'column-drop.json', clock=lambda: 100)
        receipt = applications.review(preview, fresh, remove, 'owner', 'binding', 'file-1')
        dropped = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert dropped['state'] == 'committed' and dropped['outcome']['rediscovery_verified'], dropped
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT count(*) FROM duckdb_columns() "
            "WHERE table_name='existing' AND column_name='label'").fetchone() == (0,)
        observer.close()
    finally:
        provider.client.close()


def test_reviewed_column_default_and_nullability_are_native(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        for ordinal, action, field, value in (
                (1, 'set-default', 'default', '7'),
                (2, 'set-nullable', 'nullable', False),
                (3, 'set-default', 'default', None)):
            current = next(row for row in baseline['rows'].values()
                if row['kind'] == 'column' and row['name'] == 'id' and row['path'][2] == 'existing')
            desired = deepcopy(baseline)
            desired_row = desired['rows'][current['resource_id']]
            desired_row['native']['catalog_metadata'][field] = value
            desired_row['native']['duckdb_change'] = {'action': action}
            preview = plan(baseline, desired, baseline)
            assert preview['application_supported'], preview['blockers']
            applications = DuckDBSchemaApplications(tmp_path/f'column-alter-{ordinal}.json', clock=lambda: 100)
            receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
            result = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
            assert result['state'] == 'committed' and result['outcome']['rediscovery_verified'], result
            observed = provider.capture_catalog(route)
            baseline = build_export(observed['resources'], endpoint_id='endpoint-1', target_id='file-1',
                generation=observed['generation'], refreshed=True, engine='duckdb', native_model=True)
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT column_default, is_nullable FROM duckdb_columns() "
            "WHERE table_name='existing' AND column_name='id'").fetchone() == (None, False)
        observer.close()
    finally:
        provider.client.close()
