"""DuckDB DDN review claims one native statement and never replays it."""

from copy import deepcopy
from dataclasses import dataclass
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


def test_committed_view_replacement_requires_matching_native_body(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE VIEW observed_view AS SELECT 1 AS x')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        current = next(row for row in baseline['rows'].values()
            if row['kind'] == 'view' and row['name'] == 'observed_view')
        desired = deepcopy(baseline)
        desired['rows'][current['resource_id']]['native'].update(
            ddl=f'CREATE OR REPLACE VIEW "{current["path"][0]}"."main"."observed_view" AS SELECT 2 AS x',
            duckdb_change={'action': 'replace'})
        preview = plan(baseline, desired, baseline)
        applications = DuckDBSchemaApplications(tmp_path/'view-body.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        from pgadmin.cdeadmin.providers.duckdb import schema_application
        actual_model = schema_application._model

        def conflicting_observation(connection, record, *, in_transaction):
            model = actual_model(connection, record, in_transaction=in_transaction)
            if not in_transaction:
                model['rows'][current['resource_id']]['native']['ddl'] = (
                    'CREATE VIEW observed_view AS SELECT 3 AS x;')
            return model

        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed'
        assert outcome['outcome']['rediscovery_verified'] is False
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': current['resource_id'], 'verified': False}]
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_committed_view_creation_requires_matching_native_body(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
    desired = deepcopy(baseline)
    path = [root, 'main', 'created_view']
    identity = _resource_id('view', path[:-1], path[-1])
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'view',
        'name': 'created_view', 'path': path, 'system': 'false',
        'native': {'system_object': False, 'catalog_metadata': {},
            'ddl': f'CREATE VIEW "{root}"."main"."created_view" AS SELECT 2 AS x'}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'], preview['blockers']
    applications = DuckDBSchemaApplications(tmp_path/'created-view.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['ddl'] = (
                'CREATE VIEW created_view AS SELECT 3 AS x;')
        return model

    try:
        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed'
        assert outcome['outcome']['rediscovery_verified'] is False
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': False}]
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


@pytest.mark.parametrize('kind', ('table', 'index'))
def test_committed_relation_creation_requires_matching_native_definition(tmp_path, kind):
    provider, route, baseline, desired, identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values()
        if row['kind'] == 'database')
    if kind == 'index':
        desired = deepcopy(baseline)
        path = [root, 'main', 'existing', 'existing_id']
        identity = _resource_id('index', path[:-1], path[-1])
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'index',
            'name': 'existing_id', 'path': path, 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {},
                'ddl': f'CREATE INDEX "existing_id" ON "{root}"."main"."existing"(id)'}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'], preview['blockers']
    applications = DuckDBSchemaApplications(tmp_path/f'{kind}-creation.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired,
        'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['ddl'] = (
                'CREATE TABLE extra(x VARCHAR);' if kind == 'table' else
                'CREATE INDEX existing_id ON existing(x);')
        return model

    try:
        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': False}]
        assert outcome['outcome']['rediscovery_verified'] is False
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_committed_type_creation_requires_matching_resolved_expression(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values()
        if row['kind'] == 'database')
    desired = deepcopy(baseline)
    path = [root, 'main', 'state']
    identity = _resource_id('type', path[:-1], path[-1])
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'type',
        'name': 'state', 'path': path, 'system': 'false',
        'native': {'system_object': False, 'catalog_metadata': {},
            'ddl': f'CREATE TYPE "{root}"."main"."state" AS ENUM (\'ready\', \'done\')'}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'], preview['blockers']
    applications = DuckDBSchemaApplications(tmp_path/'type-creation.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired,
        'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['catalog_metadata']['resolved_type'] = (
                "ENUM('ready', 'other')")
        return model

    try:
        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': False}]
        assert outcome['outcome']['rediscovery_verified'] is False
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_committed_sequence_creation_requires_matching_generator_options(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values()
        if row['kind'] == 'database')
    desired = deepcopy(baseline)
    path = [root, 'main', 'counter']
    identity = _resource_id('sequence', path[:-1], path[-1])
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'sequence',
        'name': 'counter', 'path': path, 'system': 'false',
        'native': {'system_object': False, 'catalog_metadata': {},
            'ddl': f'CREATE SEQUENCE "{root}"."main"."counter" '
                'INCREMENT BY 2 START 3 CYCLE'}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'], preview['blockers']
    assert preview['operations'][0]['postcondition']['sequence_options'] == {
        'start_value': 3, 'min_value': 1, 'max_value': 2 ** 63 - 1,
        'increment_by': 2, 'cycle': True}
    applications = DuckDBSchemaApplications(tmp_path/'sequence-creation.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired,
        'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['catalog_metadata']['increment_by'] = 3
        return model

    try:
        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': False}]
        assert outcome['outcome']['rediscovery_verified'] is False
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


@pytest.mark.parametrize('table_macro,tamper', (
    (False, False), (False, True), (True, False), (True, True),
))
def test_committed_macro_creation_requires_matching_native_body(tmp_path, table_macro, tamper):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values()
        if row['kind'] == 'database')
    desired = deepcopy(baseline)
    path = [root, 'main', 'created_macro']
    identity = _resource_id('macro', path[:-1], path[-1])
    body = 'TABLE SELECT x AS value' if table_macro else 'x + 1'
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'macro',
        'name': 'created_macro', 'path': path, 'system': 'false',
        'native': {'system_object': False, 'catalog_metadata': {},
            'ddl': f'CREATE MACRO "{root}"."main"."created_macro"(x) AS {body}'}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'], preview['blockers']
    applications = DuckDBSchemaApplications(tmp_path/'macro-creation.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired,
        'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['overloads'][0]['definition'] = (
                'SELECT x + 2 AS "value"' if table_macro else '(x + 2)')
        return model

    try:
        if tamper:
            with patch.object(schema_application, '_model', conflicting_observation):
                outcome = applications.apply(request(receipt), 'owner', 'binding',
                    lambda record: apply_review(provider, route, record))
        else:
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': not tamper}]
        assert outcome['outcome']['rediscovery_verified'] is not tamper
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


@pytest.mark.parametrize('kind,old,new,source_sql', [
    ('table', 'existing', 'renamed_table', None),
    ('view', 'old_view', 'renamed_view', 'CREATE VIEW old_view AS SELECT 1 AS x'),
    ('column', 'id', 'renamed_id', None),
])
def test_reviewed_native_rename_rebinds_identity_and_rediscovery(
        tmp_path, kind, old, new, source_sql):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        if source_sql:
            connection = duckdb.connect(route['database'])
            connection.execute(source_sql)
            connection.close()
            observed = provider.capture_catalog(route)
            baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
                target_id='file-1', generation=observed['generation'],
                refreshed=True, engine='duckdb', native_model=True)
        source_row = next(item for item in baseline['rows'].values()
            if item['kind'] == kind and item['name'] == old)
        destination = deepcopy(source_row)
        destination['name'] = new
        destination['path'][-1] = new
        destination['resource_id'] = _resource_id(kind, destination['path'][:-1], new)
        destination['native']['duckdb_change'] = {'action': 'rename',
            'from_resource_id': source_row['resource_id'], 'confirmation': old}
        desired = deepcopy(baseline)
        desired['rows'].pop(source_row['resource_id'])
        desired['rows'][destination['resource_id']] = destination
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/f'{kind}-rename.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        assert outcome['outcome']['rediscovered_resource_id'] == destination['resource_id']
        observed = provider.capture_catalog(route)
        fresh = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'],
            refreshed=True, engine='duckdb', native_model=True)
        assert destination['resource_id'] in fresh['rows']
        assert source_row['resource_id'] not in fresh['rows']
    finally:
        provider.client.close()


@pytest.mark.parametrize('kind,name,setup', [
    ('table', 'existing', None),
    ('view', 'commented_view', 'CREATE VIEW commented_view AS SELECT 1 AS x'),
    ('column', 'id', None),
    ('sequence', 'commented_seq', 'CREATE SEQUENCE commented_seq'),
    ('type', 'commented_type', "CREATE TYPE commented_type AS ENUM ('a', 'b')"),
    ('macro', 'commented_macro', 'CREATE MACRO commented_macro(x) AS x + 1'),
    ('index', 'existing_id_ix', 'CREATE INDEX existing_id_ix ON existing(id)'),
])
def test_native_comment_review_apply_and_fresh_postcondition(tmp_path, kind, name, setup):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        if setup:
            connection = duckdb.connect(route['database'])
            connection.execute(setup)
            connection.close()
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'],
            refreshed=True, engine='duckdb', native_model=True)
        current = next(item for item in baseline['rows'].values()
            if item['kind'] == kind and item['name'] == name)
        desired = deepcopy(baseline)
        after = desired['rows'][current['resource_id']]
        after['native']['catalog_metadata']['comment'] = "owner's note"
        after['native']['duckdb_change'] = {'action': 'set-comment'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/f'{kind}-comment.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observed = provider.capture_catalog(route)
        fresh = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'],
            refreshed=True, engine='duckdb', native_model=True)
        assert fresh['rows'][current['resource_id']]['native']['catalog_metadata']['comment'] == "owner's note"
    finally:
        provider.client.close()


def test_native_batch_creates_schema_table_and_index_in_one_commit(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        desired = deepcopy(baseline)
        for kind, path, source in (
            ('schema', [root, 'design'], f'CREATE SCHEMA "{root}"."design"'),
            ('table', [root, 'design', 'facts'],
             f'CREATE TABLE "{root}"."design"."facts" ("x" INTEGER)'),
            ('index', [root, 'design', 'facts', 'facts_x'],
             f'CREATE INDEX "facts_x" ON "{root}"."design"."facts"("x")'),
        ):
            identity = _resource_id(kind, path[:-1], path[-1])
            desired['rows'][identity] = {'resource_id': identity, 'kind': kind,
                'name': path[-1], 'path': path, 'system': 'false',
                'native': {'system_object': False, 'catalog_metadata': {}, 'ddl': source}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert [item['kind'] for item in preview['operations']] == ['schema', 'table', 'index']
        applications = DuckDBSchemaApplications(tmp_path/'batch.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        assert len(outcome['outcome']['rediscovery_checks']) == 3
    finally:
        provider.client.close()


@pytest.mark.parametrize('violates,tamper', (
    (False, False), (False, True), (True, False),
))
def test_isolated_check_rebuild_preserves_rows_or_rolls_back(tmp_path, violates, tamper):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute('INSERT INTO checked VALUES (1), (2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        expression = 'id > 1' if violates else 'id >= 0'
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            f'(id INTEGER, CHECK(({expression})))')
        edited['constraints'][0]['constraint_text'] = f'CHECK(({expression}))'
        edited['constraints'][0]['expression'] = f'({expression})'
        child_id = edited['constraints'][0]['resource_id']
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text=f'CHECK(({expression}))', expression=f'({expression})')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert preview['operations'][0]['operation'] == 'rebuild'
        unsafe = deepcopy(desired)
        unsafe['rows'][original['resource_id']]['native']['ddl'] = (
            edited['ddl'].replace('id INTEGER', 'id VARCHAR'))
        assert not plan(baseline, unsafe, baseline)['application_supported']
        stale_child = deepcopy(desired)
        stale_child['rows'][child_id]['native']['catalog_metadata']['constraint_text'] = (
            'CHECK((id > 0))')
        assert not plan(baseline, stale_child, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'check-rebuild.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        from pgadmin.cdeadmin.providers.duckdb import schema_application
        actual_model = schema_application._model

        def conflicting_observation(connection, record, *, in_transaction):
            model = actual_model(connection, record, in_transaction=in_transaction)
            if not in_transaction:
                model['rows'][child_id]['native']['catalog_metadata']['constraint_text'] = (
                    'CHECK((id > 99))')
            return model

        if tamper:
            with patch.object(schema_application, '_model', conflicting_observation):
                outcome = applications.apply(request(receipt), 'owner', 'binding',
                    lambda record: apply_review(provider, route, record))
        else:
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM checked ORDER BY id').fetchall() == [(1,), (2,)]
        assert observer.execute("SELECT count(*) FROM duckdb_tables() "
            "WHERE table_name LIKE '__scratchrobin_rebuild_%'").fetchone()[0] == 0
        constraint = observer.execute("SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name='checked'").fetchone()[0]
        assert constraint == (f'CHECK((id > 0))' if violates else f'CHECK(({expression}))')
        observer.close()
        if violates:
            assert outcome['state'] == 'rolled_back', outcome
            assert outcome['outcome']['native_rollback_returned']
        else:
            assert outcome['state'] == 'committed', outcome
            assert outcome['outcome']['rediscovery_verified'] is not tamper, outcome
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


@pytest.mark.parametrize('dependent_sql', (
    'CREATE VIEW checked_view AS SELECT id FROM checked',
))
def test_check_rebuild_blocks_unpreserved_native_dependents(tmp_path, dependent_sql):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute(dependent_sql)
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, CHECK((id >= 0)))')
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        child_id = edited['constraints'][0]['resource_id']
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert not preview['application_supported']
        assert preview['operations'] == [] and preview['blockers']
    finally:
        provider.client.close()


def test_check_rebuild_can_remove_the_complete_check_child_set(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute('INSERT INTO checked VALUES (1), (2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'] = []
        edited['ddl'] = f'CREATE TABLE "{original["path"][0]}"."main"."checked" (id INTEGER)'
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        del desired['rows'][child_id]
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'check-removal.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM checked ORDER BY id').fetchall() == [(1,), (2,)]
        assert observer.execute("SELECT count(*) FROM duckdb_constraints() "
            "WHERE table_name='checked'").fetchone()[0] == 0
        observer.close()
    finally:
        provider.client.close()


def test_isolated_unique_rebuild_can_remove_the_complete_unique_child_set(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE unique_item(id INTEGER UNIQUE)')
    connection.execute('INSERT INTO unique_item VALUES (1), (2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'unique_item')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'] = []
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."unique_item" '
            '(id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-unique-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        del desired['rows'][child_id]
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'unique-removal.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM unique_item ORDER BY id').fetchall() == [(1,), (2,)]
        assert observer.execute("SELECT count(*) FROM duckdb_constraints() "
            "WHERE table_name='unique_item'").fetchone()[0] == 0
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('duplicate', (False, True))
def test_isolated_unique_rebuild_adds_constraint_or_rolls_back_duplicate_data(tmp_path, duplicate):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE plain_item(id INTEGER)')
    connection.execute('CREATE TABLE prototype_item(id INTEGER UNIQUE)')
    connection.execute('INSERT INTO plain_item VALUES (1), (?)', [1 if duplicate else 2])
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'plain_item')
        prototype = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'prototype_item')
        template_id = prototype['native']['constraints'][0]['resource_id']
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child = deepcopy(baseline['rows'][template_id])
        child['name'] = 'plain_item_id_key'
        child['path'] = [*original['path'], child['name']]
        child_id = _resource_id('constraint', original['path'], child['name'], discriminator=0)
        child['resource_id'] = child_id
        child['native']['navigator_parent_resource_id'] = original['resource_id']
        desired['rows'][child_id] = child
        summary = deepcopy(prototype['native']['constraints'][0])
        summary.update(resource_id=child_id, name=child['name'])
        edited['constraints'] = [summary]
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."plain_item" '
            '(id INTEGER UNIQUE)')
        edited['duckdb_change'] = {'action': 'rebuild-unique-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'unique-addition.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT count(*) FROM plain_item').fetchone()[0] == 2
        constraint_count = observer.execute("SELECT count(*) FROM duckdb_constraints() "
            "WHERE table_name='plain_item' AND constraint_type='UNIQUE'").fetchone()[0]
        observer.close()
        if duplicate:
            assert outcome['state'] == 'rolled_back', outcome
            assert constraint_count == 0
        else:
            assert outcome['state'] == 'committed', outcome
            assert outcome['outcome']['rediscovery_verified'], outcome
            assert constraint_count == 1
    finally:
        provider.client.close()


def test_constraint_rebuild_replays_index_and_table_column_index_comments(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0), value VARCHAR)')
    connection.execute("INSERT INTO checked VALUES (1, 'one'), (2, 'two')")
    connection.execute('CREATE INDEX checked_value_idx ON checked(value)')
    connection.execute('CREATE INDEX checked_lower_idx ON checked(lower(value))')
    connection.execute("COMMENT ON TABLE checked IS 'table note'")
    connection.execute("COMMENT ON COLUMN checked.id IS 'column note'")
    connection.execute("COMMENT ON INDEX checked_value_idx IS 'index note'")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, "value" VARCHAR, CHECK((id >= 0)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['affected_index_ids']) == 2
        applications = DuckDBSchemaApplications(tmp_path/'rebuild-with-index.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id, value FROM checked ORDER BY id').fetchall() == [
            (1, 'one'), (2, 'two')]
        assert observer.execute("SELECT comment FROM duckdb_tables() "
            "WHERE table_name='checked'").fetchone()[0] == 'table note'
        assert observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='checked' AND column_name='id'").fetchone()[0] == 'column note'
        assert observer.execute("SELECT comment FROM duckdb_indexes() "
            "WHERE index_name='checked_value_idx'").fetchone()[0] == 'index note'
        assert observer.execute("SELECT count(*) FROM duckdb_indexes() "
            "WHERE table_name='checked' AND index_name='checked_lower_idx'").fetchone()[0] == 1
        observer.close()
    finally:
        provider.client.close()


def test_constraint_rebuild_preserves_column_defaults_without_evaluating_them_for_copied_rows(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute("CREATE TABLE checked(id INTEGER DEFAULT 7 CHECK(id > 0), "
        "value VARCHAR DEFAULT 'ready')")
    connection.execute("INSERT INTO checked VALUES (1, 'one'), (2, 'two')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            "(id INTEGER DEFAULT(7), \"value\" VARCHAR DEFAULT('ready'), CHECK((id >= 0)))")
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        changed_default = deepcopy(desired)
        changed_default['rows'][original['resource_id']]['native']['ddl'] = (
            edited['ddl'].replace('DEFAULT(7)', 'DEFAULT(8)'))
        assert not plan(baseline, changed_default, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'rebuild-with-default.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id, value FROM checked ORDER BY id').fetchall() == [
            (1, 'one'), (2, 'two')]
        observer.execute('INSERT INTO checked DEFAULT VALUES')
        assert observer.execute('SELECT id, value FROM checked WHERE id=7').fetchall() == [
            (7, 'ready')]
        observer.close()
    finally:
        provider.client.close()


def test_constraint_rebuild_blocks_generated_columns_before_dispatch(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0), '
        'derived INTEGER GENERATED ALWAYS AS (id + 1))')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, derived INTEGER GENERATED ALWAYS AS((id + 1)), '
            'CHECK((id >= 0)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert not preview['application_supported']
        assert any('plain CREATE TABLE body' in blocker['reason']
            for blocker in preview['blockers'])
    finally:
        provider.client.close()


def test_constraint_rebuild_preserves_unchanged_primary_key(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO checked VALUES (1, 'one'), (2, 'two')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        child_id = check['resource_id']
        check['constraint_text'] = 'CHECK((length(payload) >= 1))'
        check['expression'] = '(length(payload) >= 1)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((length(payload) >= 1))',
            expression='(length(payload) >= 1)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 1)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        unsafe = deepcopy(desired)
        unsafe['rows'][original['resource_id']]['native']['ddl'] = (
            edited['ddl'].replace('id INTEGER PRIMARY KEY', 'id INTEGER'))
        assert not plan(baseline, unsafe, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'rebuild-with-primary.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id, payload FROM checked ORDER BY id').fetchall() == [
            (1, 'one'), (2, 'two')]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute("INSERT INTO checked VALUES (1, 'again')")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('owned', (False, True))
def test_constraint_rebuild_preserves_independent_sequence_default(tmp_path, owned):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE SEQUENCE seq')
    connection.execute("CREATE TABLE checked(id BIGINT DEFAULT nextval('seq') "
        'CHECK(id > 0))')
    connection.execute('INSERT INTO checked DEFAULT VALUES')
    connection.execute('INSERT INTO checked DEFAULT VALUES')
    if owned:
        connection.execute('ALTER SEQUENCE seq OWNED BY checked')
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            "(id BIGINT DEFAULT(nextval('seq')), CHECK((id >= 0)))")
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'rebuild-with-sequence.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if owned else 'committed'), outcome
        if not owned:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM checked ORDER BY id').fetchall() == [
            (1,), (2,)]
        constraint = observer.execute('SELECT constraint_text FROM duckdb_constraints() '
            "WHERE table_name='checked'").fetchone()[0]
        assert constraint == ('CHECK((id > 0))' if owned else 'CHECK((id >= 0))')
        observer.execute('INSERT INTO checked DEFAULT VALUES')
        assert observer.execute('SELECT max(id) FROM checked').fetchone()[0] == 3
        observer.close()
    finally:
        connection.close()
        provider.client.close()


def test_constraint_rebuild_blocks_observed_sequence_ownership(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE SEQUENCE owned_seq')
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute('ALTER SEQUENCE owned_seq OWNED BY checked')
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        sequence = next(row for row in baseline['rows'].values()
            if row['kind'] == 'sequence' and row['name'] == 'owned_seq')
        assert sequence['native']['catalog_metadata']['automatic_dependency_observed']
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        child_id = edited['constraints'][0]['resource_id']
        edited['constraints'][0]['constraint_text'] = 'CHECK((id >= 0))'
        edited['constraints'][0]['expression'] = '(id >= 0)'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text='CHECK((id >= 0))', expression='(id >= 0)')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, CHECK((id >= 0)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert not preview['application_supported']
        assert any('dependent object' in blocker['reason']
            for blocker in preview['blockers'])
    finally:
        connection.close()
        provider.client.close()


def test_native_batch_rolls_back_all_statements_on_late_failure(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        desired = deepcopy(baseline)
        for kind, name, source in (
            ('table', 'batch_first', f'CREATE TABLE "{root}"."main"."batch_first" (x INTEGER)'),
            ('view', 'batch_late',
             f'CREATE VIEW "{root}"."main"."batch_late" AS SELECT x FROM missing_source'),
        ):
            path = [root, 'main', name]
            identity = _resource_id(kind, path[:-1], name)
            desired['rows'][identity] = {'resource_id': identity, 'kind': kind,
                'name': name, 'path': path, 'system': 'false',
                'native': {'system_object': False, 'catalog_metadata': {}, 'ddl': source}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'batch-failure.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'rolled_back', outcome
        assert outcome['outcome']['native_rollback_returned'], outcome
        connection = duckdb.connect(route['database'])
        assert connection.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='batch_first'").fetchone()[0] == 0
        connection.close()
    finally:
        provider.client.close()


def test_native_batch_adds_column_before_index_on_existing_table(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
        desired = deepcopy(baseline)
        column_path = [root, 'main', 'existing', 'amount']
        column_id = _resource_id('column', column_path[:-1], column_path[-1])
        desired['rows'][column_id] = {'resource_id': column_id, 'kind': 'column',
            'name': 'amount', 'path': column_path, 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {
                'data_type': 'INTEGER', 'nullable': True}}}
        index_path = [root, 'main', 'existing', 'existing_amount_ix']
        index_id = _resource_id('index', index_path[:-1], index_path[-1])
        desired['rows'][index_id] = {'resource_id': index_id, 'kind': 'index',
            'name': 'existing_amount_ix', 'path': index_path, 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {},
                'ddl': f'CREATE INDEX "existing_amount_ix" ON "{root}"."main"."existing"("amount")'}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert [item['kind'] for item in preview['operations']] == ['column', 'index']
        applications = DuckDBSchemaApplications(tmp_path/'column-index.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
    finally:
        provider.client.close()


def test_native_primary_key_addition_verifies_columns_and_rolls_back_bad_data(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    try:
        existing = next(item for item in baseline['rows'].values()
            if item['kind'] == 'table' and item['name'] == 'existing')
        desired = deepcopy(baseline)
        desired['rows'][existing['resource_id']]['native']['duckdb_change'] = {
            'action': 'add-primary-key', 'columns': ['id']}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'primary-key.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        result = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert result['state'] == 'committed', result
        assert result['outcome']['rediscovery_verified'], result
        observed = provider.capture_catalog(route)
        fresh = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'],
            refreshed=True, engine='duckdb', native_model=True)
        assert fresh['rows'][existing['resource_id']]['native']['catalog_metadata']['has_primary_key']
        connection = duckdb.connect(route['database'])
        with pytest.raises(duckdb.Error):
            connection.execute('INSERT INTO existing VALUES (NULL)')
        connection.close()
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


def test_committed_column_add_rejects_mismatched_native_default(tmp_path):
    provider, route, baseline, _desired, _identity = fixture(tmp_path)
    root = next(row['name'] for row in baseline['rows'].values() if row['kind'] == 'database')
    path = [root, 'main', 'existing', 'label']
    identity = _resource_id('column', path[:-1], path[-1])
    desired = deepcopy(baseline)
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'column',
        'name': 'label', 'path': path, 'system': 'false',
        'native': {'system_object': False, 'catalog_metadata': {
            'data_type': 'VARCHAR', 'nullable': True, 'default': "'ready'"}}}
    preview = plan(baseline, desired, baseline)
    assert preview['application_supported'] and preview['operations'][0]['postcondition'] == {
        'data_type': 'VARCHAR', 'nullable': True, 'default': "'ready'"}
    applications = DuckDBSchemaApplications(tmp_path/'column-postcondition.json', clock=lambda: 100)
    receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
    from pgadmin.cdeadmin.providers.duckdb import schema_application
    actual_model = schema_application._model

    def conflicting_observation(connection, record, *, in_transaction):
        model = actual_model(connection, record, in_transaction=in_transaction)
        if not in_transaction:
            model['rows'][identity]['native']['catalog_metadata']['default'] = "'wrong'"
        return model

    try:
        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed'
        assert outcome['outcome']['rediscovery_verified'] is False
        assert outcome['outcome']['rediscovery_checks'] == [
            {'resource_id': identity, 'verified': False}]
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_reviewed_column_type_conversion_preserves_rows_and_is_not_replayed(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN amount VARCHAR')
    connection.execute("INSERT INTO existing VALUES (1, '7')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        column = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['name'] == 'amount')
        desired = deepcopy(baseline)
        changed = desired['rows'][column['resource_id']]
        changed['native']['catalog_metadata']['data_type'] = 'INTEGER'
        changed['native']['duckdb_change'] = {
            'action': 'set-type', 'using': '"amount"::INTEGER'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'column-type.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT amount FROM existing').fetchall() == [(7,)]
        assert observer.execute("SELECT data_type FROM duckdb_columns() "
            "WHERE table_name='existing' AND column_name='amount'").fetchone() == ('INTEGER',)
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_reviewed_struct_field_add_preserves_existing_values(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN shape STRUCT(a INTEGER)')
    connection.execute("INSERT INTO existing VALUES (1, {'a': 7})")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        column = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['name'] == 'shape')
        assert column['native']['catalog_metadata']['data_type'] == 'STRUCT(a INTEGER)'
        desired = deepcopy(baseline)
        changed = desired['rows'][column['resource_id']]
        changed['native']['catalog_metadata']['data_type'] = 'STRUCT(a INTEGER, b VARCHAR)'
        changed['native']['duckdb_change'] = {'action': 'add-field',
            'field': 'b', 'data_type': 'VARCHAR'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert preview['operations'][0]['source'].endswith(
            'ADD COLUMN "shape"."b" VARCHAR')
        wrong = deepcopy(desired)
        wrong['rows'][column['resource_id']]['native']['catalog_metadata'][
            'data_type'] = 'STRUCT(a INTEGER, other VARCHAR)'
        assert not plan(baseline, wrong, baseline)['application_supported']
        duplicate = deepcopy(desired)
        duplicate['rows'][column['resource_id']]['native'][
            'catalog_metadata']['data_type'] = 'STRUCT(a INTEGER, a INTEGER)'
        duplicate['rows'][column['resource_id']]['native'][
            'duckdb_change'].update(field='a', data_type='INTEGER')
        assert 'duplicate an observed field' in plan(
            baseline, duplicate, baseline)['blockers'][0]['reason']
        applications = DuckDBSchemaApplications(tmp_path/'struct-field.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT shape FROM existing').fetchall() == [
            ({'a': 7, 'b': None},)]
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_reviewed_struct_field_drop_preserves_other_nested_values(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN shape '
        'STRUCT(a INTEGER, b DECIMAL(8,2), c STRUCT(x INTEGER, y VARCHAR))')
    connection.execute("INSERT INTO existing VALUES (1, {'a': 7, 'b': 1.25, "
        "'c': {'x': 9, 'y': 'kept'}})")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        column = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['name'] == 'shape')
        desired = deepcopy(baseline)
        changed = desired['rows'][column['resource_id']]
        changed['native']['catalog_metadata']['data_type'] = (
            'STRUCT(a INTEGER, c STRUCT(x INTEGER, y VARCHAR))')
        changed['native']['duckdb_change'] = {'action': 'drop-field', 'field': 'b'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert preview['operations'][0]['source'].endswith(
            'DROP COLUMN "shape"."b" RESTRICT')
        wrong = deepcopy(desired)
        wrong['rows'][column['resource_id']]['native']['catalog_metadata'][
            'data_type'] = 'STRUCT(a INTEGER)'
        assert not plan(baseline, wrong, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'struct-field-drop.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired, 'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT shape FROM existing').fetchall() == [
            ({'a': 7, 'c': {'x': 9, 'y': 'kept'}},)]
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_reviewed_nested_struct_field_add_and_drop_preserve_values(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN shape '
        'STRUCT(child STRUCT(a INTEGER, b VARCHAR), z INTEGER)')
    connection.execute("INSERT INTO existing VALUES (1, {'child': {'a': 7, "
        "'b': 'kept'}, 'z': 9})")
    connection.close()
    try:
        for action, path, wanted_type in (
            ('add-nested-field', ['child', 'c'],
                'STRUCT(child STRUCT(a INTEGER, b VARCHAR, c INTEGER), z INTEGER)'),
            ('drop-nested-field', ['child', 'a'],
                'STRUCT(child STRUCT(b VARCHAR, c INTEGER), z INTEGER)'),
        ):
            observed = provider.capture_catalog(route)
            baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
                target_id='file-1', generation=observed['generation'], refreshed=True,
                engine='duckdb', native_model=True)
            column = next(row for row in baseline['rows'].values()
                if row['kind'] == 'column' and row['name'] == 'shape')
            desired = deepcopy(baseline)
            changed = desired['rows'][column['resource_id']]['native']
            changed['catalog_metadata']['data_type'] = wanted_type
            changed['duckdb_change'] = {'action': action, 'field_path': path}
            if action == 'add-nested-field':
                changed['duckdb_change']['data_type'] = 'INTEGER'
            preview = plan(baseline, desired, baseline)
            assert preview['application_supported'], preview['blockers']
            assert '.'.join('"' + part + '"' for part in ['shape', *path]) in (
                preview['operations'][0]['source'])
            applications = DuckDBSchemaApplications(
                tmp_path/f'{action}.json', clock=lambda: 100)
            receipt = applications.review(preview, baseline, desired,
                'owner', 'binding', 'file-1')
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
            assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
            assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT shape FROM existing').fetchall() == [
            ({'child': {'b': 'kept', 'c': None}, 'z': 9},)]
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('kind', ('type', 'macro'))
def test_reviewed_native_enum_or_scalar_macro_replacement(tmp_path, kind):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    if kind == 'type':
        connection.execute("CREATE TYPE mood AS ENUM ('ok', 'bad')")
        name = 'mood'
    else:
        connection.execute('CREATE MACRO plusone(x) AS x + 1')
        name = 'plusone'
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == kind and row['name'] == name)
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        if kind == 'type':
            changed['native']['catalog_metadata']['labels'].append('great')
            changed['native']['duckdb_change'] = {'action': 'extend-enum'}
        else:
            changed['native']['definition'] = '(x + 2)'
            changed['native']['overloads'][0]['definition'] = '(x + 2)'
            changed['native']['duckdb_change'] = {
                'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/f'{kind}-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        if kind == 'type':
            assert observer.execute("SELECT labels FROM duckdb_types() "
                "WHERE type_name='mood'").fetchone()[0] == ['ok', 'bad', 'great']
        else:
            assert observer.execute('SELECT plusone(5)').fetchone() == (7,)
        observer.close()
    finally:
        provider.client.close()


def test_reviewed_native_table_macro_replacement(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE MACRO rowplus(x) AS TABLE SELECT x + 1 AS value')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'macro' and row['name'] == 'rowplus')
        assert original['native']['overloads'][0]['catalog_metadata']['function_type'] == 'table_macro'
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        changed['native']['definition'] = 'SELECT (x + 2) AS "value"'
        changed['native']['overloads'][0]['definition'] = changed['native']['definition']
        changed['native']['duckdb_change'] = {
            'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'table-macro-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT * FROM rowplus(5)').fetchone() == (7,)
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('third_definition, verified', (
    ('((x + y) + z)', True),
    ('(x + y + z)', False),
))
def test_reviewed_native_complete_macro_overload_replacement(tmp_path, third_definition, verified):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE MACRO overloaded(x) AS x + 1, (x, y) AS x + y')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'macro' and row['name'] == 'overloaded')
        assert original['native']['overload_count'] == 2
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        overloads = changed['native']['overloads']
        overloads[0]['definition'] = '(x + 2)'
        third = deepcopy(overloads[1])
        third['parameters'].append({'name': 'z', 'data_type': None})
        third['definition'] = third_definition
        overloads.append(third)
        changed['native']['overload_count'] = 3
        root = original['path'][0]
        source = ('CREATE OR REPLACE MACRO ' +
            f'"{root}"."main"."overloaded" (x) AS x + 2, '
            '(x, y) AS x + y, (x, y, z) AS x + y + z')
        changed['native']['duckdb_change'] = {'action': 'replace-macro',
            'source': source, 'complete_signature_set_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['postcondition']['overloads']) == 3
        unconfirmed = deepcopy(desired)
        unconfirmed['rows'][original['resource_id']]['native']['duckdb_change'].pop(
            'complete_signature_set_confirmed')
        assert 'complete-signature confirmation' in plan(
            baseline, unconfirmed, baseline)['blockers'][0]['reason']
        wrong_target = deepcopy(desired)
        wrong_target['rows'][original['resource_id']]['native']['duckdb_change']['source'] = (
            source.replace('"overloaded"', '"unrelated"'))
        assert 'exact fully qualified native CREATE target' in plan(
            baseline, wrong_target, baseline)['blockers'][0]['reason']
        applications = DuckDBSchemaApplications(tmp_path/'macro-group-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'] is verified, outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT overloaded(5), overloaded(5, 6), '
            'overloaded(5, 6, 7)').fetchone() == (7, 11, 18)
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_reviewed_native_sequence_replacement_requires_reset_intent(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE SEQUENCE counter START 3 INCREMENT 2')
    assert connection.execute("SELECT nextval('counter')").fetchone() == (3,)
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'sequence' and row['name'] == 'counter')
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        changed['native']['catalog_metadata']['start_value'] = 20
        changed['native']['catalog_metadata']['increment_by'] = 3
        root = original['path'][0]
        changed['native']['ddl'] = (
            f'CREATE OR REPLACE SEQUENCE "{root}"."main"."counter" '
            'START 20 INCREMENT 3')
        changed['native']['duckdb_change'] = {
            'action': 'replace-sequence', 'reset_state_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        unconfirmed = deepcopy(desired)
        unconfirmed['rows'][original['resource_id']]['native']['duckdb_change'] = {
            'action': 'replace-sequence'}
        assert 'reset confirmation' in plan(
            baseline, unconfirmed, baseline)['blockers'][0]['reason']
        commented_baseline = deepcopy(baseline)
        commented_desired = deepcopy(desired)
        commented_baseline['rows'][original['resource_id']]['native']['catalog_metadata']['comment'] = 'keep'
        commented_desired['rows'][original['resource_id']]['native']['catalog_metadata']['comment'] = 'keep'
        assert 'discard native comment' in plan(
            commented_baseline, commented_desired, commented_baseline)['blockers'][0]['reason']
        applications = DuckDBSchemaApplications(tmp_path/'sequence-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT nextval('counter')").fetchone() == (20,)
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


def test_sequence_replacement_does_not_drop_native_dependents(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE SEQUENCE counter START 3')
    connection.execute("CREATE TABLE dependent(id INTEGER DEFAULT nextval('counter'))")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'sequence' and row['name'] == 'counter')
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        changed['native']['catalog_metadata']['start_value'] = 20
        root = original['path'][0]
        changed['native']['ddl'] = (
            f'CREATE OR REPLACE SEQUENCE "{root}"."main"."counter" START 20')
        changed['native']['duckdb_change'] = {
            'action': 'replace-sequence', 'reset_state_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'sequence-dependency.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT start_value FROM duckdb_sequences() "
            "WHERE sequence_name='counter'").fetchone() == (20,)
        assert observer.execute("SELECT count(*) FROM duckdb_tables() "
            "WHERE table_name='dependent'").fetchone() == (1,)
        observer.execute('INSERT INTO dependent DEFAULT VALUES')
        assert observer.execute('SELECT id FROM dependent').fetchone() == (20,)
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('name, original_type, replacement_type, resolved, logical, size', (
    ('payload', 'STRUCT(k INTEGER, l VARCHAR)',
     'STRUCT(k INTEGER, l VARCHAR, m DOUBLE)',
     'STRUCT(k INTEGER, l VARCHAR, m DOUBLE)', 'STRUCT', 0),
    ('alias_number', 'INTEGER', 'BIGINT', 'BIGINT', 'BIGINT', 8),
))
def test_reviewed_native_complete_type_replacement(tmp_path, name, original_type,
                                                   replacement_type, resolved, logical, size):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute(f'CREATE TYPE "{name}" AS {original_type}')
    if name == 'payload':
        connection.execute('CREATE TABLE typed_payload(value payload)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'type' and row['name'] == name)
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]
        changed['native']['catalog_metadata'].update(
            resolved_type=resolved, logical_type=logical, size_bytes=size)
        root = original['path'][0]
        changed['native']['ddl'] = (
            f'CREATE OR REPLACE TYPE "{root}"."main"."{name}" AS {replacement_type}')
        changed['native']['duckdb_change'] = {
            'action': 'replace-type', 'complete_definition_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        unconfirmed = deepcopy(desired)
        unconfirmed['rows'][original['resource_id']]['native']['duckdb_change'] = {
            'action': 'replace-type'}
        assert 'whole-definition confirmation' in plan(
            baseline, unconfirmed, baseline)['blockers'][0]['reason']
        applications = DuckDBSchemaApplications(tmp_path/f'{name}-type-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute(
            f'SELECT typeof(NULL::"{root}"."main"."{name}")').fetchone() == (resolved,)
        if name == 'payload':
            assert observer.execute("SELECT data_type FROM duckdb_columns() "
                "WHERE table_name='typed_payload' AND column_name='value'").fetchone() == (
                    'STRUCT(k INTEGER, l VARCHAR)',)
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
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
