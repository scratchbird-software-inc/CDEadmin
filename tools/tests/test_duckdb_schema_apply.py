"""DuckDB DDN reviews bind bounded native operations without replaying outcomes."""

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


@pytest.mark.parametrize('tamper', (None, 'view', 'column'))
def test_view_replacement_restores_native_comment_in_one_transaction(tmp_path, tamper):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE VIEW observed_view AS SELECT 1 AS x')
    connection.execute("COMMENT ON VIEW observed_view IS 'retained note'")
    connection.execute("COMMENT ON COLUMN observed_view.x IS 'column note'")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        current = next(row for row in baseline['rows'].values()
            if row['kind'] == 'view' and row['name'] == 'observed_view')
        desired = deepcopy(baseline)
        edited = desired['rows'][current['resource_id']]['native']
        edited.update(ddl=f'CREATE OR REPLACE VIEW "{current["path"][0]}"."main".'
            '"observed_view" AS SELECT 2 AS x', duckdb_change={'action': 'replace'})
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['statements']) == 3
        changed_comment = deepcopy(desired)
        changed_comment['rows'][current['resource_id']]['native'][
            'catalog_metadata']['comment'] = 'different note'
        assert not plan(baseline, changed_comment, baseline)['application_supported']
        missing_column = deepcopy(desired)
        missing_column['rows'][current['resource_id']]['native']['columns'] = []
        assert not plan(baseline, missing_column, baseline)['application_supported']
        combined = deepcopy(desired)
        child_id = current['native']['columns'][0]['resource_id']
        combined['rows'][child_id]['native']['catalog_metadata']['comment'] = 'new note'
        combined['rows'][child_id]['native']['duckdb_change'] = {
            'action': 'set-comment'}
        assert not plan(baseline, combined, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'view-with-comment.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        from pgadmin.cdeadmin.providers.duckdb import schema_application
        actual_model = schema_application._model

        def conflicting_observation(connection, record, *, in_transaction):
            model = actual_model(connection, record, in_transaction=in_transaction)
            if not in_transaction:
                if tamper == 'view':
                    model['rows'][current['resource_id']]['native'][
                        'catalog_metadata']['comment'] = 'different note'
                else:
                    model['rows'][current['resource_id']]['native'][
                        'columns'][0]['comment'] = 'different note'
            return model

        if tamper:
            with patch.object(schema_application, '_model', conflicting_observation):
                outcome = applications.apply(request(receipt), 'owner', 'binding',
                    lambda record: apply_review(provider, route, record))
        else:
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'] is (tamper is None), outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT x FROM observed_view').fetchall() == [(2,)]
        assert observer.execute("SELECT comment FROM duckdb_views() "
            "WHERE view_name='observed_view'").fetchone()[0] == 'retained note'
        assert observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='observed_view' AND column_name='x'").fetchone()[0] == 'column note'
        observer.close()
    finally:
        provider.client.close()


def test_view_replacement_rolls_back_when_commented_column_disappears(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE VIEW observed_view AS SELECT 1 AS x')
    connection.execute("COMMENT ON COLUMN observed_view.x IS 'column note'")
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
            ddl=f'CREATE OR REPLACE VIEW "{current["path"][0]}"."main".'
                '"observed_view" AS SELECT 2 AS y',
            duckdb_change={'action': 'replace'})
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'missing-commented-column.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'rolled_back', outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT x FROM observed_view').fetchall() == [(1,)]
        assert observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='observed_view' AND column_name='x'").fetchone()[0] == 'column note'
        observer.close()
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


@pytest.mark.parametrize('dependent_sql,admitted', (
    ('CREATE VIEW checked_view AS SELECT id FROM checked', True),
    ('CREATE MACRO checked_count() AS (SELECT count(*) FROM checked)', True),
    ('CREATE MACRO checked_rows() AS TABLE (SELECT id FROM checked)', True),
    ('CREATE MACRO checked_count(n) AS '
        '(SELECT count(*) FROM checked WHERE id > n)', True),
    ('CREATE MACRO checked_count '
        '(n) AS (SELECT count(*) FROM checked WHERE id > n), '
        '(n, k) AS (SELECT count(*) FROM checked WHERE id > n + k)', True),
    ('CREATE MACRO checked_many ' + ', '.join(
        '(' + ', '.join(f'p{number}' for number in range(1, arity + 1)) +
        ') AS (SELECT count(*) FROM checked)' for arity in range(1, 10)), True),
))
def test_check_rebuild_preserves_views_and_distinct_arity_macros(
        tmp_path, dependent_sql, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute('INSERT INTO checked VALUES (1), (2)')
    connection.execute(dependent_sql)
    is_view = 'CREATE VIEW' in dependent_sql
    many_macros = dependent_sql == (
        'CREATE MACRO checked_count() AS (SELECT count(*) FROM checked)')
    if is_view:
        for number in range(2, 18):
            connection.execute(f'CREATE VIEW checked_view{number} '
                'AS SELECT id FROM checked')
        connection.execute("COMMENT ON VIEW checked_view IS 'retained view'")
        connection.execute("COMMENT ON COLUMN checked_view.id IS 'retained column'")
    if many_macros:
        for number in range(2, 18):
            connection.execute(f'CREATE MACRO checked_count{number}() AS '
                '(SELECT count(*) FROM checked)')
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
        assert preview['application_supported'] is admitted, preview['blockers']
        if admitted:
            operation = preview['operations'][0]
            assert len(operation['affected_view_ids']) == (17 if is_view else 0)
            assert len(operation['affected_view_column_ids']) == (17 if is_view else 0)
            assert len(operation['affected_macro_ids']) == (
                17 if many_macros else int(not is_view))
            applications = DuckDBSchemaApplications(tmp_path/'check-view.json',
                clock=lambda: 100)
            receipt = applications.review(preview, baseline, desired,
                'owner', 'binding', 'file-1')
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
            assert outcome['state'] == 'committed', outcome
            assert outcome['outcome']['rediscovery_verified'], outcome
            observer = duckdb.connect(route['database'])
            if is_view:
                assert observer.execute('SELECT id FROM checked_view ORDER BY id').fetchall() == [
                    (1,), (2,)]
                for number in range(2, 18):
                    assert observer.execute(f'SELECT id FROM checked_view{number} '
                        'ORDER BY id').fetchall() == [(1,), (2,)]
                assert observer.execute("SELECT comment FROM duckdb_views() "
                    "WHERE view_name='checked_view'").fetchone()[0] == 'retained view'
                assert observer.execute("SELECT comment FROM duckdb_columns() "
                    "WHERE table_name='checked_view' AND column_name='id'").fetchone()[0] == (
                    'retained column')
            else:
                if 'AS TABLE' in dependent_sql:
                    assert observer.execute('SELECT id FROM checked_rows() ORDER BY id').fetchall() == [
                        (1,), (2,)]
                elif 'checked_count (n)' in dependent_sql:
                    assert observer.execute('SELECT checked_count(0)').fetchone()[0] == 2
                    assert observer.execute('SELECT checked_count(0, 1)').fetchone()[0] == 1
                elif 'checked_count(n)' in dependent_sql:
                    assert observer.execute('SELECT checked_count(1)').fetchone()[0] == 1
                elif 'checked_many' in dependent_sql:
                    for arity in (1, 9):
                        assert observer.execute('SELECT checked_many(' +
                            ','.join(['NULL'] * arity) + ')').fetchone()[0] == 2
                else:
                    assert observer.execute('SELECT checked_count()').fetchone()[0] == 2
                    if many_macros:
                        for number in range(2, 18):
                            assert observer.execute(
                                f'SELECT checked_count{number}()').fetchone()[0] == 2
            observer.close()
        else:
            assert preview['operations'] == [] and preview['blockers']
    finally:
        provider.client.close()


def test_check_rebuild_refuses_macro_that_cannot_bind_placeholder(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0))')
    connection.execute('INSERT INTO checked VALUES (1)')
    connection.execute('CREATE MACRO dynamic_table(n) AS TABLE (FROM query_table(n))')
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
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'unbindable-macro.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'not_dispatched', outcome
        assert outcome['outcome']['native_rollback_returned']
        assert not outcome['outcome'].get('statement_dispatched')
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM checked').fetchall() == [(1,)]
        assert observer.execute('SELECT constraint_text FROM duckdb_constraints() '
            "WHERE table_name='checked'").fetchone()[0] == 'CHECK((id > 0))'
        observer.close()
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


@pytest.mark.parametrize('unique_body', ['id INTEGER UNIQUE, payload VARCHAR',
    'id INTEGER, payload VARCHAR, UNIQUE(id)'])
def test_check_rebuild_preserves_unchanged_unique_constraint(tmp_path, unique_body):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(' + unique_body +
        ', CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO checked VALUES (1, 'a'), (2, 'b')")
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
        edited['constraints'] = [item for item in edited['constraints']
            if item['constraint_type'] != 'CHECK']
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            f'({unique_body})')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        del desired['rows'][check['resource_id']]
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        unsafe = deepcopy(desired)
        unsafe['rows'][original['resource_id']]['native']['ddl'] = (
            f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, payload VARCHAR)')
        assert not plan(baseline, unsafe, baseline)['application_supported']
        altered = deepcopy(desired)
        altered_body = ('id INTEGER, payload VARCHAR UNIQUE' if
            'id INTEGER UNIQUE' in unique_body else
            'id INTEGER, payload VARCHAR, UNIQUE(payload)')
        altered['rows'][original['resource_id']]['native']['ddl'] = (
            f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            f'({altered_body})')
        altered_preview = plan(baseline, altered, baseline)
        assert altered_preview['application_supported'], altered_preview['blockers']
        altered_applications = DuckDBSchemaApplications(
            tmp_path/'wrong-unique-stage.json', clock=lambda: 100)
        altered_receipt = altered_applications.review(altered_preview, baseline,
            altered, 'owner', 'binding', 'file-1')
        altered_outcome = altered_applications.apply(request(altered_receipt),
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert altered_outcome['state'] == 'rolled_back', altered_outcome
        assert altered_outcome['outcome']['native_rollback_returned']
        applications = DuckDBSchemaApplications(tmp_path/'check-unique.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,payload FROM checked ORDER BY id').fetchall() == [
            (1, 'a'), (2, 'b')]
        assert observer.execute('SELECT constraint_type FROM duckdb_constraints() '
            "WHERE table_name='checked'").fetchall() == [('UNIQUE',)]
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


def test_inbound_rebuild_preserves_complete_check_and_unique_sets(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    child_body = ('id INTEGER, parent_id INTEGER, a INTEGER, b INTEGER, '
        'c INTEGER, CHECK((id > 0)), CHECK((a >= 0)), CHECK((b >= 0)), '
        'UNIQUE(a), UNIQUE(b), UNIQUE(c)')
    connection.execute('CREATE TABLE child(' + child_body + ', '
        'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO child VALUES (10, 1, 1, 2, 3)')
    connection.execute('CREATE VIEW child_parent AS SELECT child.id, parent.payload '
        'FROM child JOIN parent ON child.parent_id = parent.id')
    connection.execute('CREATE MACRO child_row_count() AS '
        '(SELECT count(*) FROM child)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        child = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'child')
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        root = parent['path'][0]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        intermediate = f'CREATE TABLE "{root}"."main"."child" ({child_body})'
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_child_resource_id': child['resource_id'],
            'intermediate_child_ddl': intermediate}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        omitted = deepcopy(desired)
        omitted['rows'][parent['resource_id']]['native']['duckdb_change'][
            'intermediate_child_ddl'] = intermediate.replace(', UNIQUE(c)', '')
        assert not plan(baseline, omitted, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'complete-child-constraints.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT * FROM child').fetchall() == [(10, 1, 1, 2, 3)]
        assert observer.execute('SELECT * FROM child_parent').fetchall() == [(10, 'aa')]
        assert observer.execute('SELECT child_row_count()').fetchone()[0] == 1
        assert observer.execute('SELECT constraint_type, count(*) FROM '
            "duckdb_constraints() WHERE table_name='child' GROUP BY 1 "
            'ORDER BY 1').fetchall() == [
                ('CHECK', 3), ('FOREIGN KEY', 1), ('UNIQUE', 3)]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO child VALUES (11, 1, 1, 8, 9)')
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,data_type,admitted', [
    ('id + 1', 'INTEGER', True), ('random()', 'DOUBLE', False)])
def test_constraint_rebuild_preserves_only_safe_generated_columns(
        tmp_path, expression, data_type, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER CHECK(id > 0), '
        f'derived {data_type} GENERATED ALWAYS AS ({expression}))')
    connection.execute('INSERT INTO checked(id) VALUES (1), (2)')
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
            f'(id INTEGER, derived {data_type} GENERATED ALWAYS AS(({expression})), '
            'CHECK((id >= 0)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-constraints',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            assert any('plain CREATE TABLE body' in blocker['reason']
                for blocker in preview['blockers'])
            return
        altered = deepcopy(desired)
        altered['rows'][original['resource_id']]['native']['ddl'] = (
            edited['ddl'].replace('id + 1', 'id + 2'))
        assert not plan(baseline, altered, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'generated-rebuild.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,derived FROM checked ORDER BY id').fetchall() == [
            (1, 2), (2, 3)]
        observer.close()
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


@pytest.mark.parametrize('invalid', [False, True])
@pytest.mark.parametrize('child_count', [1, 2, 3, 4, 7])
@pytest.mark.parametrize('retained_unique', [False, True])
@pytest.mark.parametrize('default_style', [None, 'literal', 'expression'])
@pytest.mark.parametrize('child_checks,child_unique_style', [
    (0, None), (1, None), (2, None), (0, 'inline'), (2, 'table')])
def test_check_rebuild_with_inbound_foreign_keys_is_atomic(
        tmp_path, invalid, child_count, retained_unique, default_style,
        child_checks, child_unique_style):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    unique_definition = 'code INTEGER UNIQUE, ' if retained_unique else ''
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, ' +
        unique_definition + 'payload VARCHAR CHECK(length(payload) > 0))')
    child_columns = ({
        None: 'id INTEGER, parent_id INTEGER',
        'literal': 'id INTEGER DEFAULT(7), parent_id INTEGER DEFAULT(1)',
        'expression': ('id INTEGER DEFAULT((7 + 0)), '
            'parent_id INTEGER DEFAULT((1 + 0))'),
    })[default_style]
    if child_unique_style == 'inline':
        child_columns = child_columns.replace(', parent_id', ' UNIQUE, parent_id')
    child_check = (', CHECK((id > 0))' if child_checks else '') + (
        ', CHECK((parent_id > 0))' if child_checks == 2 else '')
    child_unique = ', UNIQUE(id)' if child_unique_style == 'table' else ''
    connection.execute('CREATE TABLE child(' + child_columns + child_check + child_unique + ', '
        'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    for number in range(2, child_count + 1):
        connection.execute(f'CREATE TABLE child{number}(' + child_columns + child_check + child_unique + ', '
            'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    connection.execute(('INSERT INTO parent VALUES (1, 100, ?), (2, 200, ?)'
        if retained_unique else 'INSERT INTO parent VALUES (1, ?), (2, ?)'),
        ['a' if invalid else 'aa', 'bb'])
    connection.execute('INSERT INTO child VALUES (10, 1), (11, 2)')
    for number in range(2, child_count + 1):
        connection.execute(f'INSERT INTO child{number} VALUES '
            f'({number * 10}, 1), ({number * 10 + 1}, 2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        children = [next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == name)
            for name in ['child', *(f'child{number}'
                for number in range(2, child_count + 1))]]
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, ' + unique_definition + 'payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        change = {'action': ('rebuild-check-with-inbound-child' if child_count == 1
                else 'rebuild-check-with-inbound-children'),
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        intermediate = lambda name: (f'CREATE TABLE "{root}"."main"."{name}" '
            '(' + child_columns + child_check + child_unique + ')')
        if child_count == 1:
            change.update(inbound_child_resource_id=children[0]['resource_id'],
                intermediate_child_ddl=intermediate('child'))
        else:
            change['inbound_children'] = [{'resource_id': item['resource_id'],
                'intermediate_ddl': intermediate(item['name'])} for item in children]
        edited['duckdb_change'] = change
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['statements']) >= 4 + child_count * 8
        if child_count > 1:
            missing = deepcopy(desired)
            missing['rows'][parent['resource_id']]['native'][
                'duckdb_change']['inbound_children'].pop()
            assert not plan(baseline, missing, baseline)['application_supported']
        if child_count == 7:
            excessive = deepcopy(desired)
            excessive['rows'][parent['resource_id']]['native'][
                'duckdb_change']['inbound_children'].append(
                    deepcopy(change['inbound_children'][0]))
            blocked = plan(baseline, excessive, baseline)
            assert not blocked['application_supported']
            assert any('repeats a child identity' in item['reason']
                for item in blocked['blockers'])
        unsafe = deepcopy(desired)
        unsafe_change = unsafe['rows'][parent['resource_id']]['native']['duckdb_change']
        def corrupt_intermediate(source):
            return (source.replace(', CHECK((id > 0))', '') if child_checks else
                source.replace('parent_id INTEGER', 'parent_id VARCHAR'))
        if child_count == 1:
            unsafe_change['intermediate_child_ddl'] = corrupt_intermediate(
                unsafe_change['intermediate_child_ddl'])
        else:
            unsafe_change['inbound_children'][1]['intermediate_ddl'] = corrupt_intermediate(
                unsafe_change['inbound_children'][1]['intermediate_ddl'])
        assert not plan(baseline, unsafe, baseline)['application_supported']
        if retained_unique:
            wrong = deepcopy(desired)
            wrong['rows'][parent['resource_id']]['native']['ddl'] = (
                edited['ddl'].replace('code INTEGER UNIQUE, payload VARCHAR',
                    'code INTEGER, payload VARCHAR UNIQUE'))
            wrong_preview = plan(baseline, wrong, baseline)
            assert wrong_preview['application_supported'], wrong_preview['blockers']
            wrong_applications = DuckDBSchemaApplications(
                tmp_path/'inbound-wrong-unique.json', clock=lambda: 100)
            wrong_receipt = wrong_applications.review(wrong_preview, baseline,
                wrong, 'owner', 'binding', 'file-1')
            wrong_outcome = wrong_applications.apply(request(wrong_receipt),
                'owner', 'binding', lambda record: apply_review(provider, route, record))
            assert wrong_outcome['state'] == 'rolled_back', wrong_outcome
        applications = DuckDBSchemaApplications(tmp_path/'inbound-check.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if invalid else 'committed'), outcome
        if not invalid:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,parent_id FROM child ORDER BY id').fetchall() == [
            (10, 1), (11, 2)]
        expected_child_types = ([('CHECK',)] * child_checks + [('FOREIGN KEY',)] +
            ([('UNIQUE',)] if child_unique_style else []))
        assert sorted(observer.execute("SELECT constraint_type FROM duckdb_constraints() "
            "WHERE table_name='child'").fetchall()) == expected_child_types
        for number in range(2, child_count + 1):
            assert observer.execute(f'SELECT id,parent_id FROM child{number} ORDER BY id').fetchall() == [
                (number * 10, 1), (number * 10 + 1, 2)]
            assert sorted(observer.execute("SELECT constraint_type FROM duckdb_constraints() "
                f"WHERE table_name='child{number}'").fetchall()) == expected_child_types
        assert observer.execute('SELECT id,payload FROM parent ORDER BY id').fetchall() == [
            (1, 'a' if invalid else 'aa'), (2, 'bb')]
        assert observer.execute("SELECT constraint_text FROM duckdb_constraints() "
            "WHERE table_name='parent' AND constraint_type='CHECK'").fetchone()[0] == (
            'CHECK((length(payload) > 0))' if invalid else
            'CHECK((length(payload) >= 2))')
        if default_style and not invalid:
            observer.execute('INSERT INTO child DEFAULT VALUES')
            assert observer.execute('SELECT id,parent_id FROM child WHERE id=7').fetchall() == [
                (7, 1)]
        if child_checks and not invalid:
            with pytest.raises(duckdb.ConstraintException):
                observer.execute('INSERT INTO child VALUES (-1, 1)')
        if child_unique_style and not invalid:
            with pytest.raises(duckdb.ConstraintException):
                observer.execute('INSERT INTO child VALUES (10, 1)')
        if retained_unique:
            assert observer.execute("SELECT constraint_column_names FROM duckdb_constraints() "
                "WHERE table_name='parent' AND constraint_type='UNIQUE'").fetchall() == [
                (['code'],)]
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('child_count,invalid', [
    (8, False), (8, True), (32, False), (33, False),
    (63, False), (64, False), (2, False)])
def test_large_inbound_child_set_is_bounded_and_atomic(tmp_path, child_count, invalid):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute('INSERT INTO parent VALUES (1, ?)',
        ['a' if invalid else 'aa'])
    for number in range(1, child_count + 1):
        connection.execute(f'CREATE TABLE child{number}(id INTEGER, parent_id INTEGER, '
            'FOREIGN KEY(parent_id) REFERENCES parent(id))')
        connection.execute(f'INSERT INTO child{number} VALUES ({number}, 1)')
    if child_count == 2:
        connection.execute('CREATE VIEW child_parent AS SELECT child1.id, '
            'parent.payload FROM child1 JOIN parent '
            'ON child1.parent_id = parent.id')
        connection.execute('CREATE MACRO child2_count() AS '
            '(SELECT count(*) FROM child2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-children',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_children': [{
                'resource_id': next(row['resource_id'] for row in baseline['rows'].values()
                    if row['kind'] == 'table' and row['name'] == f'child{number}'),
                'intermediate_ddl': f'CREATE TABLE "{root}"."main"."child{number}" '
                    '(id INTEGER, parent_id INTEGER)'}
                for number in range(1, child_count + 1)]}
        preview = plan(baseline, desired, baseline)
        if child_count == 64:
            assert not preview['application_supported']
            assert any('two to sixty-three' in item['reason']
                for item in preview['blockers'])
            return
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['statements']) == 4 + 8 * child_count
        if child_count == 63:
            return
        applications = DuckDBSchemaApplications(tmp_path/'many-child-receipt.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if invalid else 'committed'), outcome
        if not invalid:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        for number in range(1, child_count + 1):
            assert observer.execute(f'SELECT id,parent_id FROM child{number}').fetchall() == [
                (number, 1)]
            assert observer.execute('SELECT constraint_type FROM duckdb_constraints() '
                'WHERE table_name=?', [f'child{number}']).fetchall() == [
                ('FOREIGN KEY',)]
        assert observer.execute('SELECT payload FROM parent').fetchone()[0] == (
            'a' if invalid else 'aa')
        if child_count == 2:
            assert observer.execute('SELECT * FROM child_parent').fetchall() == [
                (1, 'aa')]
            assert observer.execute('SELECT child2_count()').fetchone()[0] == 1
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,data_type,admitted', [
    ('random()', 'DOUBLE', True), ('uuid()', 'UUID', True),
    ('current_date', 'DATE', True), ('current_time', 'TIME', True),
    ('current_timestamp', 'TIMESTAMP', True),
    ("CAST('2024-01-01' AS DATE)", 'DATE', True),
    ('CAST(1 AS DECIMAL(10,2))', 'DECIMAL(10,2)', True),
    ("CAST('{\"a\":1}' AS JSON)", 'JSON', True),
    ('CAST(random() AS DOUBLE)', 'DOUBLE', True),
    ("current_setting('TimeZone')", 'VARCHAR', True)])
def test_inbound_child_native_default_preserves_existing_values(
        tmp_path, expression, data_type, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    columns = f'id {data_type} DEFAULT({expression}), parent_id INTEGER'
    intermediate_columns = (columns.replace('AS JSON)', 'AS "JSON")')
        if data_type == 'JSON' else columns)
    connection.execute('CREATE TABLE child(' + columns + ', '
        'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO child(parent_id) VALUES (1)')
    original_value = connection.execute('SELECT id FROM child').fetchone()[0]
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        child = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'child')
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_child_resource_id': child['resource_id'],
            'intermediate_child_ddl': f'CREATE TABLE "{root}"."main"."child" '
                '(' + intermediate_columns + ')'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        applications = DuckDBSchemaApplications(tmp_path/'child-native-default.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,parent_id FROM child').fetchall() == [
            (original_value, 1)]
        observer.execute('INSERT INTO child(parent_id) VALUES (1)')
        assert observer.execute('SELECT count(*) FROM child WHERE id IS NOT NULL').fetchone()[0] == 2
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,data_type,admitted', [
    ('id + 1', 'INTEGER', True), ('random()', 'DOUBLE', False)])
def test_inbound_child_generated_column_is_preserved_only_when_safe(
        tmp_path, expression, data_type, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    columns = (f'id INTEGER, parent_id INTEGER, derived {data_type} '
        f'GENERATED ALWAYS AS(({expression}))')
    connection.execute('CREATE TABLE child(' + columns + ', '
        'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO child(id,parent_id) VALUES (10,1)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        child = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'child')
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_child_resource_id': child['resource_id'],
            'intermediate_child_ddl': f'CREATE TABLE "{root}"."main"."child" '
                '(' + columns + ')'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        applications = DuckDBSchemaApplications(tmp_path/'child-generated.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,parent_id,derived FROM child').fetchall() == [
            (10, 1, 11)]
        assert observer.execute('SELECT constraint_type FROM duckdb_constraints() '
            "WHERE table_name='child'").fetchall() == [('FOREIGN KEY',)]
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('owned', [False, True])
@pytest.mark.parametrize('composed', [False, True])
def test_inbound_child_sequence_default_preserves_position_and_dependency(
        tmp_path, owned, composed):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE SEQUENCE child_seq START 100')
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    sequence_default = "nextval('child_seq')" + (' + 1' if composed else '')
    connection.execute('CREATE TABLE child(id BIGINT DEFAULT (' + sequence_default +
        '), parent_id INTEGER DEFAULT(1), '
        'FOREIGN KEY(parent_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO child DEFAULT VALUES')
    if owned:
        connection.execute('ALTER SEQUENCE child_seq OWNED BY child')
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        child = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'child')
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_child_resource_id': child['resource_id'],
            'intermediate_child_ddl': f'CREATE TABLE "{root}"."main"."child" '
                '(id BIGINT DEFAULT(' + sequence_default + '), '
                'parent_id INTEGER DEFAULT(1))'}
        preview = plan(baseline, desired, baseline)
        if composed:
            assert not preview['application_supported']
            assert any('admitted defaults' in item['reason']
                for item in preview['blockers'])
            assert connection.execute("SELECT last_value FROM duckdb_sequences() "
                "WHERE sequence_name='child_seq'").fetchone()[0] == 100
            return
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'child-sequence.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if owned else 'committed'), outcome['outcome']
        if not owned:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,parent_id FROM child').fetchall() == [(100, 1)]
        assert observer.execute("SELECT last_value FROM duckdb_sequences() "
            "WHERE sequence_name='child_seq'").fetchone()[0] == 100
        if not owned:
            observer.execute('INSERT INTO child DEFAULT VALUES')
            assert observer.execute('SELECT id FROM child ORDER BY id').fetchall() == [
                (100,), (101,)]
        observer.close()
    finally:
        connection.close()
        provider.client.close()


@pytest.mark.parametrize('key_style', ['not-null', 'inline-primary', 'table-primary'])
@pytest.mark.parametrize('other_parent_count', [0, 1, 2, 8, 9])
def test_inbound_child_rebuild_retains_primary_and_not_null_constraints(
        tmp_path, key_style, other_parent_count):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    for number in range(2, other_parent_count + 2):
        connection.execute(f'CREATE TABLE parent{number}(id INTEGER PRIMARY KEY)')
        connection.execute(f'INSERT INTO parent{number} VALUES ({number})')
    id_definition = ('id INTEGER PRIMARY KEY' if key_style == 'inline-primary'
        else 'id INTEGER NOT NULL' if key_style == 'not-null' else 'id INTEGER')
    parent_definition = ('parent_id INTEGER' if key_style == 'table-primary'
        else 'parent_id INTEGER NOT NULL')
    key_definition = ', PRIMARY KEY(id,parent_id)' if key_style == 'table-primary' else ''
    extra_column = ''.join(f', extra{number}_id INTEGER NOT NULL'
        for number in range(2, other_parent_count + 2))
    extra_key = ''.join(f', FOREIGN KEY(extra{number}_id) REFERENCES parent{number}(id)'
        for number in range(2, other_parent_count + 2))
    original_values = (10, 1, *range(2, other_parent_count + 2))
    def values(items):
        return '(' + ', '.join('NULL' if item is None else str(item)
            for item in items) + ')'
    connection.execute('CREATE TABLE child(' + id_definition + ', ' +
        parent_definition + extra_column + key_definition +
        ', FOREIGN KEY(parent_id) REFERENCES parent(id)' + extra_key + ')')
    connection.execute('INSERT INTO child VALUES ' + values(original_values))
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        child = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'child')
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        intermediate = (f'CREATE TABLE "{root}"."main"."child" (' +
            id_definition + ', ' + parent_definition + extra_column +
            key_definition + extra_key + ')')
        edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'inbound_child_resource_id': child['resource_id'],
            'intermediate_child_ddl': intermediate}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        wrong = deepcopy(desired)
        wrong['rows'][parent['resource_id']]['native']['duckdb_change'][
            'intermediate_child_ddl'] = (intermediate.replace(
                ', PRIMARY KEY(id,parent_id)', '') if key_style == 'table-primary'
                else intermediate.replace('parent_id INTEGER NOT NULL',
                    'parent_id INTEGER'))
        assert not plan(baseline, wrong, baseline)['application_supported']
        if other_parent_count:
            last = other_parent_count + 1
            missing_edge = deepcopy(desired)
            missing_edge['rows'][parent['resource_id']]['native'][
                'duckdb_change']['intermediate_child_ddl'] = intermediate.replace(
                    f', FOREIGN KEY(extra{last}_id) REFERENCES parent{last}(id)', '')
            assert not plan(baseline, missing_edge, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'child-not-null.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT * FROM child').fetchall() == [original_values]
        types = sorted(row[0] for row in observer.execute(
            "SELECT constraint_type FROM duckdb_constraints() WHERE table_name='child'").fetchall())
        assert types == sorted(['FOREIGN KEY', 'NOT NULL', 'NOT NULL'] +
            ['FOREIGN KEY', 'NOT NULL'] * other_parent_count +
            (['PRIMARY KEY'] if key_style != 'not-null' else []))
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO child VALUES ' + values((
                11, None, *range(2, other_parent_count + 2))))
        if key_style != 'not-null':
            with pytest.raises(duckdb.ConstraintException):
                observer.execute('INSERT INTO child VALUES ' + values(original_values))
        if other_parent_count:
            with pytest.raises(duckdb.ConstraintException):
                observer.execute('INSERT INTO child VALUES ' + values((11, 1,
                    *range(2, other_parent_count + 1), 999)))
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('view_mode', [None, 'explicit', 'star'])
def test_reviewed_column_reorder_preserves_rows_and_dependencies(tmp_path, view_mode):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN note VARCHAR')
    connection.execute("INSERT INTO existing VALUES (1, 'a'), (2, 'b')")
    connection.execute('CREATE INDEX existing_id_idx ON existing(id)')
    connection.execute("COMMENT ON TABLE existing IS 'table note'")
    connection.execute("COMMENT ON COLUMN existing.note IS 'column note'")
    connection.execute("COMMENT ON INDEX existing_id_idx IS 'index note'")
    if view_mode:
        connection.execute('CREATE VIEW existing_view AS SELECT ' +
            ('id' if view_mode == 'explicit' else '*') + ' FROM existing')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'existing')
        root = table['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        reordered = list(reversed(edited['columns']))
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."existing" '
            '(note VARCHAR, id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-column-order',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        changed_type = deepcopy(desired)
        changed_type['rows'][table['resource_id']]['native']['columns'][0][
            'data_type'] = 'INTEGER'
        assert not plan(baseline, changed_type, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'column-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        expected = 'rolled_back' if view_mode == 'star' else 'committed'
        assert outcome['state'] == expected, outcome
        if expected == 'committed':
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,note FROM existing ORDER BY id').fetchall() == [
            (1, 'a'), (2, 'b')]
        assert [item[0] for item in observer.execute('DESCRIBE existing').fetchall()] == (
            ['id', 'note'] if view_mode == 'star' else ['note', 'id'])
        assert observer.execute("SELECT comment FROM duckdb_tables() "
            "WHERE table_name='existing'").fetchone()[0] == 'table note'
        assert observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='existing' AND column_name='note'").fetchone()[0] == (
            'column note')
        assert observer.execute("SELECT comment FROM duckdb_indexes() "
            "WHERE index_name='existing_id_idx'").fetchone()[0] == 'index note'
        if view_mode:
            assert observer.execute('SELECT * FROM existing_view ORDER BY id').fetchall() == (
                [(1,), (2,)] if view_mode == 'explicit' else
                [(1, 'a'), (2, 'b')])
        observer.close()
    finally:
        provider.client.close()


def test_column_reorder_preserves_complete_check_and_unique_sets(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    names = [f'c{number}' for number in range(1, 10)]
    constraints = [*(f'UNIQUE({name})' for name in names),
        *(f'CHECK(({name} >= 0))' for name in names)]
    connection.execute('CREATE TABLE many_constraints (' + ', '.join(
        [*(f'{name} INTEGER' for name in names), *constraints]) + ')')
    connection.execute('INSERT INTO many_constraints VALUES (' + ', '.join(
        str(number) for number in range(1, 10)) + ')')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'many_constraints')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        new_names = list(reversed(names))
        column_map = {item['name']: item for item in edited['columns']}
        ordered = [column_map[name] for name in new_names]
        for position, column in enumerate(ordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = ordered
        for constraint in edited['constraints']:
            constraint['column_indexes'] = [new_names.index(name)
                for name in constraint['column_names']]
            desired['rows'][constraint['resource_id']]['native'][
                'catalog_metadata']['column_indexes'] = constraint['column_indexes']
        root = table['path'][0]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."many_constraints" (' +
            ', '.join([*(f'{name} INTEGER' for name in new_names), *constraints]) + ')')
        edited['duckdb_change'] = {'action': 'rebuild-column-order',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        missing = deepcopy(desired)
        check_id = next(item['resource_id'] for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        missing['rows'].pop(check_id)
        assert not plan(baseline, missing, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'many-constraint-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert [item[0] for item in observer.execute(
            'DESCRIBE many_constraints').fetchall()] == new_names
        assert observer.execute('SELECT ' + ', '.join(names) +
            ' FROM many_constraints').fetchone() == tuple(range(1, 10))
        assert observer.execute('SELECT constraint_type, count(*) FROM '
            "duckdb_constraints() WHERE table_name='many_constraints' "
            'GROUP BY 1 ORDER BY 1').fetchall() == [('CHECK', 9), ('UNIQUE', 9)]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO many_constraints (' + ', '.join(names) +
                ') VALUES (' + ', '.join(str(number) for number in range(1, 10)) + ')')
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,admitted', [('id * 2', True),
    ('random()', False)])
def test_reviewed_column_reorder_preserves_safe_generated_values(
        tmp_path, expression, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    data_type = 'INTEGER' if admitted else 'DOUBLE'
    generated = (f'doubled {data_type} GENERATED ALWAYS AS(({expression}))')
    connection.execute('CREATE TABLE measurements(id INTEGER, ' + generated +
        ', note VARCHAR)')
    connection.execute("INSERT INTO measurements(id,note) VALUES (1,'a'),(2,'b')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'measurements')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        reordered = [next(item for item in edited['columns'] if item['name'] == name)
            for name in ('note', 'id', 'doubled')]
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        root = table['path'][0]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."measurements" '
            f'(note VARCHAR, id INTEGER, {generated})')
        edited['duckdb_change'] = {'action': 'rebuild-column-order',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        applications = DuckDBSchemaApplications(tmp_path/'generated-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,doubled,note FROM measurements '
            'ORDER BY id').fetchall() == [(1, 2, 'a'), (2, 4, 'b')]
        assert [item[0] for item in observer.execute('DESCRIBE measurements')
            .fetchall()] == ['note', 'id', 'doubled']
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('generated', [False, True])
def test_reviewed_column_reorder_preserves_inline_primary_key(tmp_path, generated):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    generated_sql = (', doubled INTEGER GENERATED ALWAYS AS((id * 2))'
        if generated else '')
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, note VARCHAR' +
        generated_sql + ')')
    connection.execute("INSERT INTO checked(id,note) VALUES (1,'a'),(2,'b')")
    connection.execute('CREATE INDEX checked_note_idx ON checked(note)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        reordered = [next(item for item in edited['columns'] if item['name'] == name)
            for name in (('note', 'id', 'doubled') if generated else ('note', 'id'))]
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        for constraint in edited['constraints']:
            constraint['column_indexes'] = [1]
            desired['rows'][constraint['resource_id']]['native'][
                'catalog_metadata']['column_indexes'] = [1]
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."checked" '
            '(note VARCHAR, id INTEGER PRIMARY KEY' + generated_sql + ')')
        edited['duckdb_change'] = {'action': 'rebuild-column-order',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        malformed = deepcopy(desired)
        malformed['rows'][table['resource_id']]['native'][
            'constraints'][0]['column_indexes'] = [0]
        assert not plan(baseline, malformed, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'keyed-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,note FROM checked ORDER BY id').fetchall() == [
            (1, 'a'), (2, 'b')]
        assert [item[0] for item in observer.execute('DESCRIBE checked')
            .fetchall()] == (['note', 'id', 'doubled'] if generated else ['note', 'id'])
        if generated:
            assert observer.execute('SELECT doubled FROM checked ORDER BY id').fetchall() == [
                (2,), (4,)]
        assert observer.execute('SELECT constraint_type, constraint_column_indexes '
            "FROM duckdb_constraints() WHERE table_name='checked' "
            'ORDER BY constraint_index').fetchall() == [
            ('PRIMARY KEY', [1]), ('NOT NULL', [1])]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute("INSERT INTO checked(id,note) VALUES (1,'duplicate')")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('style', ['inline', 'table', 'with-key'])
def test_reviewed_column_reorder_preserves_unique_constraints(tmp_path, style):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    old_body = ('id INTEGER PRIMARY KEY, code VARCHAR, UNIQUE(code)'
        if style == 'with-key' else
        'id INTEGER, code VARCHAR UNIQUE' if style == 'inline' else
        'id INTEGER, code VARCHAR, UNIQUE(code)')
    new_body = ('code VARCHAR, id INTEGER PRIMARY KEY, UNIQUE(code)'
        if style == 'with-key' else
        'code VARCHAR UNIQUE, id INTEGER' if style == 'inline' else
        'code VARCHAR, id INTEGER, UNIQUE(code)')
    connection.execute('CREATE TABLE checked(' + old_body + ')')
    connection.execute("INSERT INTO checked VALUES (1,'a'),(2,'b')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        reordered = list(reversed(edited['columns']))
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        for constraint in edited['constraints']:
            constraint['column_indexes'] = [0 if name == 'code' else 1
                for name in constraint['column_names']]
            desired['rows'][constraint['resource_id']]['native'][
                'catalog_metadata']['column_indexes'] = constraint['column_indexes']
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."checked" '
            '(' + new_body + ')')
        edited['duckdb_change'] = {'action': 'rebuild-column-order',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'unique-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,code FROM checked ORDER BY id').fetchall() == [
            (1, 'a'), (2, 'b')]
        assert [item[0] for item in observer.execute('DESCRIBE checked')
            .fetchall()] == ['code', 'id']
        with pytest.raises(duckdb.ConstraintException):
            observer.execute("INSERT INTO checked(code,id) VALUES ('a',3)")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('style', ['plain', 'with-key-table',
    'with-key-inline', 'with-key-inline-rekey'])
@pytest.mark.parametrize('addition', [False, True])
def test_reviewed_column_reorder_preserves_table_check(
        tmp_path, style, addition):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    id_sql = 'id INTEGER PRIMARY KEY' if style != 'plain' else 'id INTEGER'
    code_sql = ('code VARCHAR UNIQUE' if style.startswith('with-key-inline')
        else 'code VARCHAR')
    suffix = (', UNIQUE(code)' if style == 'with-key-table' else '') + (
        ', CHECK(length(code) > 1)')
    old_body = f'{id_sql}, {code_sql}' + suffix
    new_body = f'{code_sql}, {id_sql}' + suffix
    connection.execute('CREATE TABLE checked(' + old_body + ')')
    connection.execute("INSERT INTO checked VALUES (1,'aa'),(2,'bb')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        reordered = list(reversed(edited['columns']))
        if addition:
            added = deepcopy(reordered[0])
            added['name'] = 'extra'
            added['resource_id'] = _resource_id('column', table['path'], 'extra')
            for field in ('data_type_id', 'character_maximum_length',
                    'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
                added[field] = None
            reordered.insert(0, added)
            desired['rows'][added['resource_id']] = {
                'resource_id': added['resource_id'], 'kind': 'column',
                'name': 'extra', 'path': [*table['path'], 'extra'],
                'system': 'false', 'native': {'system_object': False,
                'catalog_metadata': {key: value for key, value in added.items()
                    if key not in {'name', 'resource_id'}}}}
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        for constraint in edited['constraints']:
            constraint['column_indexes'] = [(1 if name == 'code' else 2)
                if addition else (0 if name == 'code' else 1)
                for name in constraint['column_names']]
            desired['rows'][constraint['resource_id']]['native'][
                'catalog_metadata']['column_indexes'] = constraint['column_indexes']
        if style == 'with-key-inline-rekey':
            original_children = {item['resource_id']: desired['rows'].pop(
                item['resource_id']) for item in edited['constraints']}
            first_index = min(item['constraint_index']
                for item in edited['constraints'])
            positions = {'UNIQUE': 0, 'PRIMARY KEY': 1,
                'CHECK': 2, 'NOT NULL': 3}
            for item in edited['constraints']:
                old_id = item['resource_id']
                new_index = first_index + positions[item['constraint_type']]
                new_id = _resource_id('constraint', table['path'], item['name'],
                    discriminator=new_index)
                item['resource_id'] = new_id
                item['constraint_index'] = new_index
                child_row = original_children[old_id]
                child_row['resource_id'] = new_id
                child_row['native']['catalog_metadata']['constraint_index'] = new_index
                desired['rows'][new_id] = child_row
            edited['constraints'].sort(key=lambda item: item['constraint_index'])
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."checked" '
            '(' + ('extra VARCHAR, ' if addition else '') + new_body + ')')
        edited['duckdb_change'] = {'action': ('rebuild-add-column-and-reorder'
            if addition else 'rebuild-column-order'),
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'check-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if style == 'with-key-inline'
            else 'committed'), outcome
        if style != 'with-key-inline':
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,code FROM checked ORDER BY id').fetchall() == [
            (1, 'aa'), (2, 'bb')]
        assert [item[0] for item in observer.execute('DESCRIBE checked').fetchall()] == (
            ['id', 'code'] if style == 'with-key-inline' else
            (['extra', 'code', 'id'] if addition else ['code', 'id']))
        if addition and style != 'with-key-inline':
            assert observer.execute('SELECT extra FROM checked').fetchall() == [
                (None,), (None,)]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute("INSERT INTO checked(code,id) VALUES ('x',3)")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('added_type,derived_known', [
    ('INTEGER', True), ('BIGINT', False)])
@pytest.mark.parametrize('wrong_derived_fact', [False, True])
def test_reviewed_add_nullable_column_and_reorder_preserves_rows(
        tmp_path, added_type, derived_known, wrong_derived_fact):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('ALTER TABLE existing ADD COLUMN note VARCHAR')
    connection.execute("INSERT INTO existing VALUES (1,'a'),(2,'b')")
    connection.execute('CREATE INDEX existing_note_idx ON existing(note)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'existing')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        old_columns = {item['name']: item for item in edited['columns']}
        added = deepcopy(old_columns['id'])
        added['name'] = 'extra'
        added['resource_id'] = _resource_id('column', table['path'], 'extra')
        added['ordinal_position'] = 1
        added['data_type'] = added_type
        if not derived_known:
            for field in ('data_type_id', 'character_maximum_length',
                    'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
                added[field] = None
        if wrong_derived_fact:
            added['numeric_precision'] = 999
        old_columns['note']['ordinal_position'] = 2
        old_columns['id']['ordinal_position'] = 3
        edited['columns'] = [added, old_columns['note'], old_columns['id']]
        for name in ('id', 'note'):
            desired['rows'][old_columns[name]['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = old_columns[name][
                    'ordinal_position']
        new_metadata = {key: value for key, value in added.items()
            if key not in {'name', 'resource_id'}}
        desired['rows'][added['resource_id']] = {'resource_id': added['resource_id'],
            'kind': 'column', 'name': 'extra',
            'path': [*table['path'], 'extra'], 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': new_metadata}}
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."existing" '
            f'(extra {added_type}, note VARCHAR, id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-add-column-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert preview['operations'][0]['stage_null_column'] == 'extra'
        unsafe = deepcopy(desired)
        unsafe['rows'][table['resource_id']]['native']['ddl'] = (
            f'CREATE TABLE "{table["path"][0]}"."main"."existing" '
            f'(extra {added_type} DEFAULT 1, note VARCHAR, id INTEGER)')
        assert not plan(baseline, unsafe, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'add-and-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if wrong_derived_fact
            else 'committed'), outcome
        if not wrong_derived_fact:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        if wrong_derived_fact:
            assert observer.execute('SELECT id,note FROM existing ORDER BY id').fetchall() == [
                (1, 'a'), (2, 'b')]
            assert [item[0] for item in observer.execute('DESCRIBE existing')
                .fetchall()] == ['id', 'note']
        else:
            assert observer.execute('SELECT id,note,extra FROM existing ORDER BY id').fetchall() == [
                (1, 'a', None), (2, 'b', None)]
            assert [item[0] for item in observer.execute('DESCRIBE existing')
                .fetchall()] == ['extra', 'note', 'id']
            assert observer.execute('SELECT data_type FROM duckdb_columns() '
                "WHERE table_name='existing' AND column_name='extra'").fetchone()[0] == added_type
        assert observer.execute('SELECT count(*) FROM duckdb_indexes() '
            "WHERE table_name='existing' AND index_name='existing_note_idx'").fetchone()[0] == 1
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,admitted', [
    ('id * 2', True), ('random()', False)])
def test_reviewed_add_and_reorder_preserves_safe_generated_values(
        tmp_path, expression, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    generated_type = 'INTEGER' if admitted else 'DOUBLE'
    generated = (f'doubled {generated_type} '
        f'GENERATED ALWAYS AS(({expression}))')
    connection.execute('CREATE TABLE measurements(id INTEGER, ' + generated +
        ', note VARCHAR)')
    connection.execute("INSERT INTO measurements(id,note) VALUES (1,'a'),(2,'b')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'measurements')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        old_columns = {item['name']: item for item in edited['columns']}
        added = deepcopy(old_columns['note'])
        added['name'] = 'extra'
        added['resource_id'] = _resource_id('column', table['path'], 'extra')
        added['ordinal_position'] = 1
        for field in ('data_type_id', 'character_maximum_length',
                'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
            added[field] = None
        reordered = [added, old_columns['note'], old_columns['id'],
            old_columns['doubled']]
        for position, column in enumerate(reordered, 1):
            column['ordinal_position'] = position
            if column is not added:
                desired['rows'][column['resource_id']]['native'][
                    'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = reordered
        desired['rows'][added['resource_id']] = {
            'resource_id': added['resource_id'], 'kind': 'column', 'name': 'extra',
            'path': [*table['path'], 'extra'], 'system': 'false',
            'native': {'system_object': False, 'catalog_metadata': {
                key: value for key, value in added.items()
                if key not in {'name', 'resource_id'}}}}
        root = table['path'][0]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."measurements" '
            f'(extra VARCHAR, note VARCHAR, id INTEGER, {generated})')
        edited['duckdb_change'] = {'action': 'rebuild-add-column-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        applications = DuckDBSchemaApplications(tmp_path/'generated-add-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,doubled,note,extra FROM measurements '
            'ORDER BY id').fetchall() == [(1, 2, 'a', None), (2, 4, 'b', None)]
        assert [item[0] for item in observer.execute('DESCRIBE measurements')
            .fetchall()] == ['extra', 'note', 'id', 'doubled']
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('expression,added_type,admitted,wrong_catalog_fact', [
    ('id * 2', 'INTEGER', True, False),
    ('id * 2', 'INTEGER', True, True),
    ('random()', 'DOUBLE', False, False)])
def test_reviewed_add_generated_column_and_reorder(
        tmp_path, expression, added_type, admitted, wrong_catalog_fact):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE measurements(id INTEGER, note VARCHAR)')
    connection.execute("INSERT INTO measurements VALUES (1,'a'),(2,'b')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'measurements')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        old_columns = {item['name']: item for item in edited['columns']}
        added = deepcopy(old_columns['id'])
        added['name'] = 'doubled'
        added['resource_id'] = _resource_id('column', table['path'], 'doubled')
        added['data_type'] = added_type
        added['default'] = (f'CAST(({"id * 3" if wrong_catalog_fact else expression}) '
            f'AS {added_type})')
        for field in ('data_type_id', 'character_maximum_length',
                'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
            added[field] = None
        ordered = [old_columns['note'], old_columns['id'], added]
        for position, column in enumerate(ordered, 1):
            column['ordinal_position'] = position
            if column is not added:
                desired['rows'][column['resource_id']]['native'][
                    'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = ordered
        desired['rows'][added['resource_id']] = {
            'resource_id': added['resource_id'], 'kind': 'column',
            'name': 'doubled', 'path': [*table['path'], 'doubled'],
            'system': 'false', 'native': {'system_object': False,
            'catalog_metadata': {key: value for key, value in added.items()
                if key not in {'name', 'resource_id'}}}}
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."measurements" '
            f'(note VARCHAR, id INTEGER, doubled {added_type} '
            f'GENERATED ALWAYS AS(({expression})))')
        edited['duckdb_change'] = {
            'action': 'rebuild-add-generated-column-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        assert 'stage_null_column' not in preview['operations'][0]
        applications = DuckDBSchemaApplications(tmp_path/'new-generated.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if wrong_catalog_fact
            else 'committed'), outcome
        if not wrong_catalog_fact:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        if wrong_catalog_fact:
            assert observer.execute('SELECT id,note FROM measurements '
                'ORDER BY id').fetchall() == [(1, 'a'), (2, 'b')]
        else:
            assert observer.execute('SELECT id,note,doubled FROM measurements '
                'ORDER BY id').fetchall() == [(1, 'a', 2), (2, 'b', 4)]
        assert [item[0] for item in observer.execute('DESCRIBE measurements')
            .fetchall()] == (['id', 'note'] if wrong_catalog_fact else
                ['note', 'id', 'doubled'])
        observer.close()
    finally:
        provider.client.close()


def test_reviewed_add_generated_column_to_one_column_keyed_table(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE measurements(id INTEGER PRIMARY KEY)')
    connection.execute('INSERT INTO measurements VALUES (1),(2)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'measurements')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        old_column = edited['columns'][0]
        added = deepcopy(old_column)
        added['name'] = 'doubled'
        added['resource_id'] = _resource_id('column', table['path'], 'doubled')
        added['ordinal_position'] = 2
        added['nullable'] = True
        added['default'] = 'CAST((id * 2) AS INTEGER)'
        for field in ('data_type_id', 'character_maximum_length',
                'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
            added[field] = None
        edited['columns'].append(added)
        desired['rows'][added['resource_id']] = {
            'resource_id': added['resource_id'], 'kind': 'column',
            'name': 'doubled', 'path': [*table['path'], 'doubled'],
            'system': 'false', 'native': {'system_object': False,
            'catalog_metadata': {key: value for key, value in added.items()
                if key not in {'name', 'resource_id'}}}}
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."measurements" '
            '(id INTEGER PRIMARY KEY, doubled INTEGER '
            'GENERATED ALWAYS AS((id * 2)))')
        edited['duckdb_change'] = {
            'action': 'rebuild-add-generated-column',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert 'stage_null_column' not in preview['operations'][0]
        applications = DuckDBSchemaApplications(tmp_path/'one-column-generated.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,doubled FROM measurements '
            'ORDER BY id').fetchall() == [(1, 2), (2, 4)]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO measurements(id) VALUES (1)')
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('added_count', [2, 8, 9, 32])
@pytest.mark.parametrize('wrong_derived_fact', [False, True])
def test_reviewed_multiple_nullable_columns_and_reorder_preserves_constraints(
        tmp_path, added_count, wrong_derived_fact):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, '
        'code VARCHAR, UNIQUE(code), CHECK(length(code) > 1))')
    connection.execute("INSERT INTO checked VALUES (1,'aa'),(2,'bb')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        old_columns = {item['name']: item for item in edited['columns']}
        additions = []
        for number in range(1, added_count + 1):
            added = deepcopy(old_columns['code'])
            added['name'] = f'extra{number}'
            added['resource_id'] = _resource_id('column', table['path'], added['name'])
            for field in ('data_type_id', 'character_maximum_length',
                    'numeric_precision', 'numeric_precision_radix', 'numeric_scale'):
                added[field] = None
            if wrong_derived_fact and number == 1:
                added['numeric_precision'] = 999
            additions.append(added)
            desired['rows'][added['resource_id']] = {
                'resource_id': added['resource_id'], 'kind': 'column',
                'name': added['name'], 'path': [*table['path'], added['name']],
                'system': 'false', 'native': {'system_object': False,
                'catalog_metadata': {key: value for key, value in added.items()
                    if key not in {'name', 'resource_id'}}}}
        ordered = [*additions, old_columns['code'], old_columns['id']]
        for position, column in enumerate(ordered, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = ordered
        for constraint in edited['constraints']:
            constraint['column_indexes'] = [added_count if name == 'code'
                else added_count + 1 for name in constraint['column_names']]
            desired['rows'][constraint['resource_id']]['native'][
                'catalog_metadata']['column_indexes'] = constraint['column_indexes']
        prefix = ', '.join(f'extra{number} VARCHAR' for number in
            range(1, added_count + 1))
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."checked" '
            f'({prefix}, code VARCHAR, id INTEGER PRIMARY KEY, '
            'UNIQUE(code), CHECK(length(code) > 1))')
        edited['duckdb_change'] = {'action': 'rebuild-add-columns-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert preview['operations'][0]['stage_null_columns'] == [
            f'extra{number}' for number in range(1, added_count + 1)]
        incomplete = deepcopy(desired)
        incomplete['rows'].pop(additions[-1]['resource_id'])
        assert not plan(baseline, incomplete, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'multiple-add-reorder.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if wrong_derived_fact
            else 'committed'), outcome
        if not wrong_derived_fact:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,code FROM checked ORDER BY id').fetchall() == [
            (1, 'aa'), (2, 'bb')]
        assert [item[0] for item in observer.execute('DESCRIBE checked').fetchall()] == (
            ['id', 'code'] if wrong_derived_fact else
            [*[f'extra{number}' for number in range(1, added_count + 1)],
             'code', 'id'])
        if not wrong_derived_fact:
            for number in range(1, added_count + 1):
                assert observer.execute(f'SELECT count(*) FROM checked '
                    f'WHERE extra{number} IS NOT NULL').fetchone()[0] == 0
        with pytest.raises(duckdb.ConstraintException):
            observer.execute("INSERT INTO checked(code,id) VALUES ('aa',3)")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('child_count,indexed_child,with_comments,index_count', [
    (1, 1, False, 1), (1, 1, True, 1), (2, 1, False, 1), (2, 1, True, 1),
    (2, 2, False, 1), (2, 2, True, 1), (3, 2, False, 1),
    (1, 1, False, 3), (2, 2, False, 3), (1, 1, False, 9)])
def test_inbound_rebuild_replays_child_indexes(
        tmp_path, child_count, indexed_child, with_comments, index_count):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY, '
        'payload VARCHAR CHECK(length(payload) > 0))')
    connection.execute("INSERT INTO parent VALUES (1, 'aa')")
    for number in range(1, child_count + 1):
        name = 'child' if number == 1 else f'child{number}'
        connection.execute(f'CREATE TABLE {name}(id INTEGER, parent_id INTEGER, '
            'FOREIGN KEY(parent_id) REFERENCES parent(id))')
        connection.execute(f'INSERT INTO {name} VALUES ({number * 10}, 1)')
        if number == indexed_child:
            connection.execute(f'CREATE INDEX {name}_id_idx ON {name}(id)')
            if index_count >= 2:
                connection.execute(f'CREATE INDEX {name}_parent_idx ON {name}(parent_id)')
            if index_count >= 3:
                connection.execute(f'CREATE INDEX {name}_pair_idx ON {name}(id,parent_id)')
            for index_number in range(4, index_count + 1):
                connection.execute(f'CREATE INDEX {name}_expr{index_number}_idx '
                    f'ON {name}((id + {index_number}))')
        if with_comments:
            connection.execute(f"COMMENT ON TABLE {name} IS 'table note'")
            connection.execute(f"COMMENT ON COLUMN {name}.id IS 'column note'")
            if number == indexed_child:
                connection.execute(f"COMMENT ON INDEX {name}_id_idx IS 'index note'")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        children = [next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] ==
                ('child' if number == 1 else f'child{number}'))
            for number in range(1, child_count + 1)]
        root = parent['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][parent['resource_id']]['native']
        check = next(item for item in edited['constraints']
            if item['constraint_type'] == 'CHECK')
        check['constraint_text'] = 'CHECK((length(payload) >= 2))'
        check['expression'] = '(length(payload) >= 2)'
        desired['rows'][check['resource_id']]['native']['catalog_metadata'].update(
            constraint_text=check['constraint_text'], expression=check['expression'])
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."parent" '
            '(id INTEGER PRIMARY KEY, payload VARCHAR, '
            'CHECK((length(payload) >= 2)))')
        intermediate = lambda name: (f'CREATE TABLE "{root}"."main"."{name}" '
            '(id INTEGER, parent_id INTEGER)')
        if child_count == 1:
            edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-child',
                'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
                'inbound_child_resource_id': children[0]['resource_id'],
                'intermediate_child_ddl': intermediate('child')}
        else:
            edited['duckdb_change'] = {'action': 'rebuild-check-with-inbound-children',
                'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
                'inbound_children': [{'resource_id': item['resource_id'],
                    'intermediate_ddl': intermediate(item['name'])} for item in children]}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        index = next(row for row in baseline['rows'].values()
            if row['kind'] == 'index' and row['name'] == children[indexed_child - 1]['name'] + '_id_idx')
        omitted = deepcopy(desired)
        del omitted['rows'][index['resource_id']]
        assert not plan(baseline, omitted, baseline)['application_supported']
        if with_comments:
            changed = deepcopy(desired)
            changed['rows'][index['resource_id']]['native'][
                'catalog_metadata']['comment'] = 'changed note'
            assert not plan(baseline, changed, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'inbound-index.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        for number in range(1, child_count + 1):
            name = 'child' if number == 1 else f'child{number}'
            assert observer.execute(f'SELECT id,parent_id FROM {name}').fetchall() == [
                (number * 10, 1)]
            if with_comments:
                assert observer.execute('SELECT comment FROM duckdb_tables() '
                    'WHERE table_name=?', [name]).fetchone()[0] == 'table note'
                assert observer.execute('SELECT comment FROM duckdb_columns() '
                    "WHERE table_name=? AND column_name='id'", [name]).fetchone()[0] == (
                    'column note')
        expected_indexes = [index['name']]
        if index_count >= 2:
            expected_indexes.append(children[indexed_child - 1]['name'] + '_parent_idx')
        if index_count >= 3:
            expected_indexes.append(children[indexed_child - 1]['name'] + '_pair_idx')
        for index_number in range(4, index_count + 1):
            expected_indexes.append(children[indexed_child - 1]['name'] +
                f'_expr{index_number}_idx')
        assert sorted(observer.execute('SELECT index_name FROM duckdb_indexes() '
            'WHERE table_name=?', [children[indexed_child - 1]['name']]).fetchall()) == [
            (name,) for name in sorted(expected_indexes)]
        if with_comments:
            assert observer.execute('SELECT comment FROM duckdb_indexes() '
                'WHERE index_name=?', [index['name']]).fetchone()[0] == 'index note'
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('invalid,parent_drift', (
    (False, False), (True, False), (False, True),
))
def test_isolated_foreign_key_rebuild_adds_constraint_or_rolls_back(
        tmp_path, invalid, parent_drift):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE checked(id INTEGER, p_id INTEGER)')
    connection.execute('INSERT INTO parent VALUES (1), (2)')
    connection.execute('INSERT INTO checked VALUES (10, 1), (11, ?)',
        [9 if invalid else 2])
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        parent = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'parent')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        root = original['path'][0]
        child_name = 'checked_p_id_id_fkey'
        child_id = _resource_id('constraint', [root, 'main', 'checked'],
            child_name, discriminator=0)
        constraint = {'resource_id': child_id, 'name': child_name,
            'constraint_index': 0, 'constraint_type': 'FOREIGN KEY',
            'constraint_text': 'FOREIGN KEY (p_id) REFERENCES parent(id)',
            'expression': None, 'column_indexes': [1], 'column_names': ['p_id'],
            'referenced_table': 'parent', 'referenced_column_names': ['id']}
        edited['constraints'] = [constraint]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."checked" '
            '(id INTEGER, p_id INTEGER, FOREIGN KEY (p_id) REFERENCES parent(id))')
        edited['duckdb_change'] = {'action': 'rebuild-foreign-keys',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        desired['rows'][child_id] = {'resource_id': child_id, 'kind': 'constraint',
            'name': child_name, 'path': [root, 'main', 'checked', child_name],
            'system': 'false', 'native': {'system_object': False,
                'catalog_metadata': {key: value for key, value in constraint.items()
                    if key not in {'resource_id', 'name'}}}}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert set(preview['operations'][0]['fk_parent_sha256']) == {
            parent['resource_id']}
        applications = DuckDBSchemaApplications(tmp_path/'foreign-key-add.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        if parent_drift:
            changed_parent = duckdb.connect(route['database'])
            changed_parent.execute('ALTER TABLE parent ADD COLUMN extra INTEGER')
            changed_parent.close()
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        expected = 'not_dispatched' if parent_drift else (
            'rolled_back' if invalid else 'committed')
        assert outcome['state'] == expected, outcome
        if not invalid and not parent_drift:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id, p_id FROM checked ORDER BY id').fetchall() == [
            (10, 1), (11, 9 if invalid else 2)]
        observed_fks = observer.execute("SELECT constraint_type FROM duckdb_constraints() "
            "WHERE table_name='checked'").fetchall()
        assert observed_fks == ([] if invalid or parent_drift else [('FOREIGN KEY',)])
        if not invalid and not parent_drift:
            with pytest.raises(duckdb.ConstraintException):
                observer.execute('INSERT INTO checked VALUES (12, 9)')
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('invalid', [None, 'duplicate', 'null'])
def test_isolated_primary_key_retarget_validates_existing_rows(tmp_path, invalid):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, code VARCHAR)')
    connection.execute('INSERT INTO checked VALUES (1, ?), (2, ?)',
        ['first', None if invalid == 'null' else
            'first' if invalid == 'duplicate' else 'second'])
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        root = original['path'][0]
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."checked" '
            '(id INTEGER, code VARCHAR PRIMARY KEY)')
        edited['duckdb_change'] = {'action': 'rebuild-retarget-primary-key',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        for column in edited['columns']:
            column['nullable'] = column['name'] == 'id'
        for row in desired['rows'].values():
            if row['kind'] == 'column' and row['path'][:3] == original['path']:
                row['native']['catalog_metadata']['nullable'] = row['name'] == 'id'
        for key, row in list(desired['rows'].items()):
            if row['kind'] == 'constraint' and row['path'][:3] == original['path']:
                del desired['rows'][key]
        constraints = []
        for number, (name, kind, source) in enumerate([
                ('checked_code_pkey', 'PRIMARY KEY', 'PRIMARY KEY(code)'),
                ('checked_code_not_null', 'NOT NULL', 'NOT NULL')]):
            child_id = _resource_id('constraint', original['path'], name,
                discriminator=number)
            item = {'resource_id': child_id, 'name': name, 'constraint_index': number,
                'constraint_type': kind, 'constraint_text': source,
                'expression': None, 'column_indexes': [1], 'column_names': ['code'],
                'referenced_table': None, 'referenced_column_names': []}
            constraints.append(item)
            desired['rows'][child_id] = {'resource_id': child_id,
                'kind': 'constraint', 'name': name,
                'path': [*original['path'], name], 'system': 'false',
                'native': {'system_object': False,
                    'catalog_metadata': {key: value for key, value in item.items()
                        if key not in {'resource_id', 'name'}}}}
        edited['constraints'] = constraints
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'primary-key-retarget.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if invalid else 'committed'), outcome
        if not invalid:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT constraint_column_names FROM duckdb_constraints() "
            "WHERE table_name='checked' AND constraint_type='PRIMARY KEY'").fetchone()[0] == (
            ['id'] if invalid else ['code'])
        assert observer.execute('SELECT count(*) FROM checked').fetchone()[0] == 2
        if not invalid:
            observer.execute("INSERT INTO checked VALUES (NULL, 'third')")
            with pytest.raises(duckdb.ConstraintException):
                observer.execute("INSERT INTO checked VALUES (3, 'third')")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('bad_stage', [False, True])
@pytest.mark.parametrize('composite', [False, True])
def test_isolated_primary_key_removal_relaxes_key_and_checks_stage(
        tmp_path, bad_stage, composite):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE checked(id INTEGER, value VARCHAR, '
        'PRIMARY KEY(id, value))' if composite else
        'CREATE TABLE checked(id INTEGER PRIMARY KEY, value VARCHAR)')
    connection.execute('CREATE INDEX checked_value_idx ON checked(value)')
    connection.execute("COMMENT ON TABLE checked IS 'kept table'")
    connection.execute("COMMENT ON COLUMN checked.id IS 'kept id'")
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
        edited['catalog_metadata']['has_primary_key'] = False
        edited['constraints'] = []
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id VARCHAR, value VARCHAR)' if bad_stage else
            f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, value VARCHAR)')
        edited['duckdb_change'] = {'action': 'rebuild-drop-primary-key',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        for item in edited['columns']:
            if item['name'] == 'id' or composite:
                item['nullable'] = True
        for row in desired['rows'].values():
            if (row['kind'] == 'column' and row['path'][:3] == original['path'] and
                    (row['name'] == 'id' or composite)):
                row['native']['catalog_metadata']['nullable'] = True
        for key, row in list(desired['rows'].items()):
            if row['kind'] == 'constraint' and row['path'][:3] == original['path']:
                del desired['rows'][key]
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'primary-key-drop.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if bad_stage else 'committed'), outcome
        if not bad_stage:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id, value FROM checked ORDER BY id').fetchall() == [
            (1, 'one'), (2, 'two')]
        assert observer.execute("SELECT constraint_type FROM duckdb_constraints() "
            "WHERE table_name='checked'").fetchall() == (
            [('PRIMARY KEY',), ('NOT NULL',)] +
            ([('NOT NULL',)] if composite else []) if bad_stage else [])
        assert observer.execute("SELECT comment FROM duckdb_tables() "
            "WHERE table_name='checked'").fetchone()[0] == 'kept table'
        assert observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='checked' AND column_name='id'").fetchone()[0] == 'kept id'
        assert observer.execute("SELECT count(*) FROM duckdb_indexes() "
            "WHERE table_name='checked' AND index_name='checked_value_idx'").fetchone()[0] == 1
        if not bad_stage:
            observer.execute("INSERT INTO checked VALUES (NULL, 'nullable')")
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('action', ['rebuild-drop-primary-key',
    'rebuild-retarget-primary-key'])
@pytest.mark.parametrize('expression,data_type,admitted', [
    ('id * 2', 'INTEGER', True), ('random()', 'DOUBLE', False)])
def test_primary_key_rebuild_preserves_only_safe_generated_values(
        tmp_path, action, expression, data_type, admitted):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    generated = (f'derived {data_type} GENERATED ALWAYS AS(({expression}))')
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, '
        'code VARCHAR, ' + generated + ')')
    connection.execute("INSERT INTO checked(id,code) VALUES (1,'a'),(2,'b')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'checked')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        retarget = action == 'rebuild-retarget-primary-key'
        edited['catalog_metadata']['has_primary_key'] = retarget
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."checked" '
            '(id INTEGER, code VARCHAR' + (' PRIMARY KEY' if retarget else '') +
            ', ' + generated + ')')
        edited['duckdb_change'] = {'action': action,
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        for column in edited['columns']:
            if column['name'] in {'id', 'code'}:
                column['nullable'] = column['name'] != 'code' or not retarget
        for row in desired['rows'].values():
            if row['kind'] == 'column' and row['path'][:3] == table['path'] and (
                    row['name'] in {'id', 'code'}):
                row['native']['catalog_metadata']['nullable'] = (
                    row['name'] != 'code' or not retarget)
        for identity, row in list(desired['rows'].items()):
            if row['kind'] == 'constraint' and row['path'][:3] == table['path']:
                del desired['rows'][identity]
        constraints = []
        if retarget:
            for index, (kind, source) in enumerate([
                    ('PRIMARY KEY', 'PRIMARY KEY(code)'),
                    ('NOT NULL', 'NOT NULL')]):
                name = 'checked_code_' + ('pkey' if index == 0 else 'not_null')
                identity = _resource_id('constraint', table['path'], name,
                    discriminator=index)
                item = {'resource_id': identity, 'name': name,
                    'constraint_index': index, 'constraint_type': kind,
                    'constraint_text': source, 'expression': None,
                    'column_indexes': [1], 'column_names': ['code'],
                    'referenced_table': None, 'referenced_column_names': []}
                constraints.append(item)
                desired['rows'][identity] = {'resource_id': identity,
                    'kind': 'constraint', 'name': name,
                    'path': [*table['path'], name], 'system': 'false',
                    'native': {'system_object': False,
                        'catalog_metadata': {key: value for key, value in item.items()
                            if key not in {'resource_id', 'name'}}}}
        edited['constraints'] = constraints
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'] is admitted, preview['blockers']
        if not admitted:
            return
        applications = DuckDBSchemaApplications(tmp_path/'generated-key.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,code,derived FROM checked '
            'ORDER BY id').fetchall() == [(1, 'a', 2), (2, 'b', 4)]
        assert observer.execute('SELECT constraint_type FROM duckdb_constraints() '
            "WHERE table_name='checked' ORDER BY constraint_index").fetchall() == (
            [('PRIMARY KEY',), ('NOT NULL',)] if retarget else [])
        observer.close()
    finally:
        provider.client.close()


def test_isolated_foreign_key_rebuild_removes_complete_outgoing_set(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE checked(id INTEGER, p_id INTEGER, '
        'FOREIGN KEY (p_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO parent VALUES (1)')
    connection.execute('INSERT INTO checked VALUES (10, 1)')
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
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, p_id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-foreign-keys',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        desired['rows'].pop(child_id)
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'foreign-key-drop.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        observer.execute('INSERT INTO checked VALUES (11, 9)')
        assert observer.execute('SELECT id, p_id FROM checked ORDER BY id').fetchall() == [
            (10, 1), (11, 9)]
        observer.close()
    finally:
        provider.client.close()


def test_foreign_key_rebuild_preserves_independent_unique_constraint(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE checked(id INTEGER UNIQUE, p_id INTEGER, '
        'FOREIGN KEY (p_id) REFERENCES parent(id))')
    connection.execute('INSERT INTO parent VALUES (1), (2)')
    connection.execute('INSERT INTO checked VALUES (10, 1), (11, 2)')
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
        foreign = next(item for item in edited['constraints']
            if item['constraint_type'] == 'FOREIGN KEY')
        edited['constraints'] = [item for item in edited['constraints']
            if item['constraint_type'] != 'FOREIGN KEY']
        root = original['path'][0]
        edited['ddl'] = (f'CREATE TABLE "{root}"."main"."checked" '
            '(id INTEGER UNIQUE, p_id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-foreign-keys',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        desired['rows'].pop(foreign['resource_id'])
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        wrong = deepcopy(desired)
        wrong['rows'][original['resource_id']]['native']['ddl'] = (
            f'CREATE TABLE "{root}"."main"."checked" '
            '(id INTEGER, p_id INTEGER UNIQUE)')
        wrong_preview = plan(baseline, wrong, baseline)
        assert wrong_preview['application_supported'], wrong_preview['blockers']
        wrong_applications = DuckDBSchemaApplications(tmp_path/'fk-wrong-unique.json',
            clock=lambda: 100)
        wrong_receipt = wrong_applications.review(wrong_preview, baseline, wrong,
            'owner', 'binding', 'file-1')
        wrong_outcome = wrong_applications.apply(request(wrong_receipt),
            'owner', 'binding', lambda record: apply_review(provider, route, record))
        assert wrong_outcome['state'] == 'rolled_back', wrong_outcome
        applications = DuckDBSchemaApplications(tmp_path/'fk-unique.json', clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id,p_id FROM checked ORDER BY id').fetchall() == [
            (10, 1), (11, 2)]
        assert observer.execute('SELECT constraint_type FROM duckdb_constraints() '
            "WHERE table_name='checked'").fetchall() == [('UNIQUE',)]
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO checked VALUES (10, 9)')
        observer.execute('INSERT INTO checked VALUES (12, 9)')
        observer.close()
    finally:
        provider.client.close()


def test_isolated_foreign_key_rebuild_retargets_a_parent(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent_old(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE parent_new(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE checked(id INTEGER, p_id INTEGER, '
        'FOREIGN KEY (p_id) REFERENCES parent_old(id))')
    connection.execute('INSERT INTO parent_old VALUES (1), (2)')
    connection.execute('INSERT INTO parent_new VALUES (1)')
    connection.execute('INSERT INTO checked VALUES (10, 1)')
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
        constraint = edited['constraints'][0]
        child_id = constraint['resource_id']
        constraint['constraint_text'] = 'FOREIGN KEY (p_id) REFERENCES parent_new(id)'
        constraint['referenced_table'] = 'parent_new'
        desired['rows'][child_id]['native']['catalog_metadata'].update(
            constraint_text=constraint['constraint_text'],
            referenced_table='parent_new')
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER, p_id INTEGER, FOREIGN KEY (p_id) REFERENCES parent_new(id))')
        edited['duckdb_change'] = {'action': 'rebuild-foreign-keys',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['fk_parent_sha256']) == 2
        applications = DuckDBSchemaApplications(tmp_path/'foreign-key-retarget.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        with pytest.raises(duckdb.ConstraintException):
            observer.execute('INSERT INTO checked VALUES (11, 2)')
        assert observer.execute('SELECT id, p_id FROM checked').fetchall() == [(10, 1)]
        observer.close()
    finally:
        provider.client.close()


def test_foreign_key_rebuild_blocks_an_inbound_reference(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
    connection.execute('CREATE TABLE checked(id INTEGER PRIMARY KEY, p_id INTEGER)')
    connection.execute('CREATE TABLE dependent(checked_id INTEGER REFERENCES checked(id))')
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
        edited['constraints'].append({'constraint_type': 'FOREIGN KEY',
            'referenced_table': 'parent'})
        edited['ddl'] = (f'CREATE TABLE "{original["path"][0]}"."main"."checked" '
            '(id INTEGER PRIMARY KEY, p_id INTEGER, '
            'FOREIGN KEY (p_id) REFERENCES parent(id))')
        edited['duckdb_change'] = {'action': 'rebuild-foreign-keys',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert not preview['application_supported']
        assert any('native key dependencies' in blocker['reason']
            for blocker in preview['blockers'])
    finally:
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


@pytest.mark.parametrize('view_mode', ('none', 'retained', 'star'))
@pytest.mark.parametrize('drop_count', (1, 2))
def test_reviewed_column_removal_and_reorder_preserves_retained_rows(
        tmp_path, view_mode, drop_count):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE shape(id INTEGER, note VARCHAR, obsolete VARCHAR)')
    connection.execute("INSERT INTO shape VALUES (1, 'a', 'x'), (2, 'b', 'y')")
    connection.execute('CREATE INDEX shape_id_idx ON shape(id)')
    connection.execute("COMMENT ON COLUMN shape.note IS 'retained note'")
    if view_mode != 'none':
        connection.execute('CREATE VIEW shape_view AS SELECT ' +
            ('*' if view_mode == 'star' else 'id') + ' FROM shape')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'shape')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        by_name = {column['name']: column for column in edited['columns']}
        removed = [by_name[name] for name in (
            ('obsolete',) if drop_count == 1 else ('note', 'obsolete'))]
        for column in removed:
            desired['rows'].pop(column['resource_id'])
        columns = ([by_name['note'], by_name['id']] if drop_count == 1
            else [by_name['id']])
        for position, column in enumerate(columns, 1):
            column['ordinal_position'] = position
            desired['rows'][column['resource_id']]['native'][
                'catalog_metadata']['ordinal_position'] = position
        edited['columns'] = columns
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."shape" '
            + ('(note VARCHAR, id INTEGER)' if drop_count == 1 else '(id INTEGER)'))
        edited['duckdb_change'] = {'action': 'rebuild-drop-columns-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'discard_columns_confirmed': True,
            'drop_column_ids': sorted(column['resource_id'] for column in removed)}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        operation = preview['operations'][0]
        assert operation['removed_column_ids'] == sorted(
            column['resource_id'] for column in removed)
        unsafe = deepcopy(desired)
        unsafe['rows'][table['resource_id']]['native']['duckdb_change'].pop(
            'discard_columns_confirmed')
        assert not plan(baseline, unsafe, baseline)['application_supported']
        unsafe = deepcopy(desired)
        unsafe['rows'][table['resource_id']]['native']['duckdb_change'][
            'drop_column_ids'] = []
        assert not plan(baseline, unsafe, baseline)['application_supported']
        unsafe = deepcopy(desired)
        unsafe['rows'][table['resource_id']]['native']['columns'][0][
            'data_type'] = 'BOOLEAN'
        assert not plan(baseline, unsafe, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'column-removal.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if view_mode == 'star'
            else 'committed'), outcome
        if view_mode != 'star':
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        if view_mode == 'star' or drop_count == 1:
            assert observer.execute('SELECT id,note FROM shape ORDER BY id').fetchall() == [
                (1, 'a'), (2, 'b')]
        else:
            assert observer.execute('SELECT id FROM shape ORDER BY id').fetchall() == [
                (1,), (2,)]
        assert [row[0] for row in observer.execute('DESCRIBE shape').fetchall()] == (
            ['id', 'note', 'obsolete'] if view_mode == 'star' else
            ['note', 'id'] if drop_count == 1 else ['id'])
        comment = observer.execute("SELECT comment FROM duckdb_columns() "
            "WHERE table_name='shape' AND column_name='note'").fetchone()
        assert comment == (('retained note',) if view_mode == 'star' or
            drop_count == 1 else None)
        assert observer.execute("SELECT count(*) FROM duckdb_indexes() "
            "WHERE index_name='shape_id_idx'").fetchone()[0] == 1
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
        observer.close()
    finally:
        provider.client.close()


def test_column_removal_with_index_on_removed_column_rolls_back(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE TABLE shape(id INTEGER, obsolete VARCHAR)')
    connection.execute("INSERT INTO shape VALUES (1, 'x')")
    connection.execute('CREATE INDEX obsolete_idx ON shape(obsolete)')
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        table = next(row for row in baseline['rows'].values()
            if row['kind'] == 'table' and row['name'] == 'shape')
        desired = deepcopy(baseline)
        edited = desired['rows'][table['resource_id']]['native']
        removed = next(column for column in edited['columns']
            if column['name'] == 'obsolete')
        desired['rows'].pop(removed['resource_id'])
        edited['columns'] = [edited['columns'][0]]
        edited['ddl'] = (f'CREATE TABLE "{table["path"][0]}"."main"."shape" '
            '(id INTEGER)')
        edited['duckdb_change'] = {'action': 'rebuild-drop-columns-and-reorder',
            'complete_definition_confirmed': True, 'preserve_rows_confirmed': True,
            'discard_columns_confirmed': True,
            'drop_column_ids': [removed['resource_id']]}
        preview = plan(baseline, desired, baseline)
        if preview['application_supported']:
            applications = DuckDBSchemaApplications(tmp_path/'indexed-drop.json',
                clock=lambda: 100)
            receipt = applications.review(preview, baseline, desired,
                'owner', 'binding', 'file-1')
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
            assert outcome['state'] == 'rolled_back', outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT * FROM shape').fetchall() == [(1, 'x')]
        assert observer.execute("SELECT count(*) FROM duckdb_indexes() "
            "WHERE index_name='obsolete_idx'").fetchone() == (1,)
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
        connection.execute("COMMENT ON TYPE mood IS 'enum note'")
        name = 'mood'
    else:
        connection.execute('CREATE MACRO plusone(x) AS x + 1')
        connection.execute("COMMENT ON MACRO plusone IS 'scalar note'")
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
        assert len(preview['operations'][0]['statements']) == 2
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
            assert observer.execute("SELECT comment FROM duckdb_types() "
                "WHERE type_name='mood'").fetchone()[0] == 'enum note'
        else:
            assert observer.execute('SELECT plusone(5)').fetchone() == (7,)
            assert observer.execute("SELECT comment FROM duckdb_functions() "
                "WHERE function_name='plusone'").fetchone()[0] == 'scalar note'
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


def test_commented_scalar_macro_replacement_requires_comment_rediscovery(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute('CREATE MACRO plusone(x) AS x + 1')
    connection.execute("COMMENT ON MACRO plusone IS 'retained note'")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'macro' and row['name'] == 'plusone')
        desired = deepcopy(baseline)
        changed = desired['rows'][original['resource_id']]['native']
        changed['definition'] = '(x + 2)'
        changed['overloads'][0]['definition'] = '(x + 2)'
        changed['duckdb_change'] = {
            'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        applications = DuckDBSchemaApplications(tmp_path/'macro-comment-verify.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        from pgadmin.cdeadmin.providers.duckdb import schema_application
        actual_model = schema_application._model

        def conflicting_observation(connection, record, *, in_transaction):
            model = actual_model(connection, record, in_transaction=in_transaction)
            if not in_transaction:
                model['rows'][original['resource_id']]['native'][
                    'catalog_metadata']['comment'] = None
            return model

        with patch.object(schema_application, '_model', conflicting_observation):
            outcome = applications.apply(request(receipt), 'owner', 'binding',
                lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'] is False, outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT plusone(5)').fetchone() == (7,)
        assert observer.execute("SELECT comment FROM duckdb_functions() "
            "WHERE function_name='plusone'").fetchone()[0] == 'retained note'
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
    connection.execute("COMMENT ON MACRO overloaded IS 'group note'")
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
        assert len(preview['operations'][0]['statements']) == 2
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
        assert {row[0] for row in observer.execute("SELECT comment FROM duckdb_functions() "
            "WHERE function_name='overloaded'").fetchall()} == {'group note'}
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
    connection.execute("COMMENT ON SEQUENCE counter IS 'sequence note'")
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
        assert len(preview['operations'][0]['statements']) == 2
        unconfirmed = deepcopy(desired)
        unconfirmed['rows'][original['resource_id']]['native']['duckdb_change'] = {
            'action': 'replace-sequence'}
        assert 'reset confirmation' in plan(
            baseline, unconfirmed, baseline)['blockers'][0]['reason']
        commented_desired = deepcopy(desired)
        commented_desired['rows'][original['resource_id']]['native'][
            'catalog_metadata']['comment'] = 'changed note'
        assert not plan(baseline, commented_desired, baseline)['application_supported']
        applications = DuckDBSchemaApplications(tmp_path/'sequence-replace.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed' and outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute("SELECT nextval('counter')").fetchone() == (20,)
        assert observer.execute("SELECT comment FROM duckdb_sequences() "
            "WHERE sequence_name='counter'").fetchone()[0] == 'sequence note'
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
    connection.execute(f"COMMENT ON TYPE \"{name}\" IS 'type note'")
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
        assert len(preview['operations'][0]['statements']) == 2
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
        assert observer.execute("SELECT comment FROM duckdb_types() WHERE type_name = ?",
            [name]).fetchone()[0] == 'type note'
        if name == 'payload':
            assert observer.execute("SELECT data_type FROM duckdb_columns() "
                "WHERE table_name='typed_payload' AND column_name='value'").fetchone() == (
                    'STRUCT(k INTEGER, l VARCHAR)',)
        observer.close()
        assert applications.apply(request(receipt), 'owner', 'binding', Mock()) == outcome
    finally:
        provider.client.close()


@pytest.mark.parametrize('replacement_default', [None, '3'])
def test_combined_column_properties_drop_incompatible_default_before_type(
        tmp_path, replacement_default):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute("CREATE TABLE combined(id VARCHAR DEFAULT 'bad')")
    connection.execute('CREATE TABLE typed(id INTEGER' +
        (' DEFAULT 3' if replacement_default else '') + ')')
    connection.execute("INSERT INTO combined VALUES ('1')")
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['path'][2] == 'combined')
        typed = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['path'][2] == 'typed')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        for key in ('data_type', 'data_type_id', 'character_maximum_length',
                    'numeric_precision', 'numeric_precision_radix', 'numeric_scale',
                    'default'):
            edited['catalog_metadata'][key] = typed['native']['catalog_metadata'][key]
        edited['duckdb_change'] = {'action': 'alter-column-properties'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        statements = preview['operations'][0]['statements']
        assert len(statements) == (3 if replacement_default else 2)
        assert statements[0].endswith('DROP DEFAULT') and ' TYPE ' in statements[1]
        if replacement_default:
            assert statements[2].endswith('SET DEFAULT 3')
        applications = DuckDBSchemaApplications(tmp_path/'drop-default-first.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == 'committed', outcome
        assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        assert observer.execute('SELECT id FROM combined').fetchall() == [(1,)]
        assert observer.execute("SELECT data_type,column_default FROM duckdb_columns() "
            "WHERE table_name='combined'").fetchone() == ('INTEGER', replacement_default)
        observer.close()
    finally:
        provider.client.close()


@pytest.mark.parametrize('invalid', [False, True])
def test_combined_column_properties_apply_atomically(tmp_path, invalid):
    duckdb = pytest.importorskip('duckdb')
    provider, route, _baseline, _desired, _identity = fixture(tmp_path)
    connection = duckdb.connect(route['database'])
    connection.execute("CREATE TABLE combined(id VARCHAR DEFAULT '1')")
    connection.execute('CREATE TABLE typed(id INTEGER DEFAULT 3 NOT NULL)')
    connection.execute('INSERT INTO combined VALUES (?), (?)',
        ['1', 'bad' if invalid else '2'])
    connection.close()
    try:
        observed = provider.capture_catalog(route)
        baseline = build_export(observed['resources'], endpoint_id='endpoint-1',
            target_id='file-1', generation=observed['generation'], refreshed=True,
            engine='duckdb', native_model=True)
        original = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['path'][2] == 'combined')
        typed = next(row for row in baseline['rows'].values()
            if row['kind'] == 'column' and row['path'][2] == 'typed')
        desired = deepcopy(baseline)
        edited = desired['rows'][original['resource_id']]['native']
        for key in ('data_type', 'data_type_id', 'character_maximum_length',
                    'numeric_precision', 'numeric_precision_radix', 'numeric_scale',
                    'default', 'nullable'):
            edited['catalog_metadata'][key] = typed['native']['catalog_metadata'][key]
        edited['duckdb_change'] = {'action': 'alter-column-properties'}
        preview = plan(baseline, desired, baseline)
        assert preview['application_supported'], preview['blockers']
        assert len(preview['operations'][0]['statements']) == 4
        assert preview['operations'][0]['statements'][0].endswith('DROP DEFAULT')
        assert ' TYPE ' in preview['operations'][0]['statements'][1]
        assert ' SET DEFAULT ' in preview['operations'][0]['statements'][2]
        assert preview['operations'][0]['statements'][3].endswith('SET NOT NULL')
        applications = DuckDBSchemaApplications(tmp_path/'column-properties.json',
            clock=lambda: 100)
        receipt = applications.review(preview, baseline, desired,
            'owner', 'binding', 'file-1')
        outcome = applications.apply(request(receipt), 'owner', 'binding',
            lambda record: apply_review(provider, route, record))
        assert outcome['state'] == ('rolled_back' if invalid else 'committed'), outcome
        if not invalid:
            assert outcome['outcome']['rediscovery_verified'], outcome
        observer = duckdb.connect(route['database'])
        column = observer.execute("SELECT data_type,column_default,is_nullable "
            "FROM duckdb_columns() WHERE table_name='combined'").fetchone()
        assert column == (('VARCHAR', "'1'", True) if invalid else
            ('INTEGER', '3', False))
        assert observer.execute('SELECT id FROM combined ORDER BY id').fetchall() == (
            [('1',), ('bad',)] if invalid else [(1,), (2,)])
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
