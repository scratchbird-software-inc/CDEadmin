"""Durable PostgreSQL receipts do not infer outcomes or replay a dispatch."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.operations.fileio import has_private_file_permissions
from tools.tests.test_postgresql_schema_plan import documents as base_documents, IDENTITY
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan
from pgadmin.cdeadmin.workspace.postgresql_schema_apply import PostgreSQLSchemaApplications
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplyError


def documents():
    before = base_documents()[0]
    row = before['rows'][IDENTITY]
    row['native']['schema'] = 'public'
    after = deepcopy(before)
    after['rows'][IDENTITY]['native']['comment'] = 'reviewed'
    return before, after


def review(tmp_path):
    before, after = documents()
    plan = build_plan(before, after, before)
    assert plan['application_supported'], plan
    store = PostgreSQLSchemaApplications(tmp_path / 'reviews.json', lambda: 100)
    return store, store.review(plan, before, after, 7, 'bound-route', 'postgresql-database:42')


def request(receipt):
    return {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}


def test_review_and_confirmation_owner_binding_expiry(tmp_path):
    store, receipt = review(tmp_path)
    assert not {'owner', 'binding', 'baseline', 'desired'} & receipt.keys()
    assert has_private_file_permissions(store.path)
    execute = Mock()
    for owner, binding in [(8, 'bound-route'), (7, 'other')]:
        with pytest.raises(SchemaApplyError):store.apply(request(receipt), owner, binding, execute)
    with pytest.raises(SchemaApplyError):store.apply({**request(receipt), 'confirmed': False}, 7, 'bound-route', execute)
    expired = PostgreSQLSchemaApplications(store.path, lambda: 401)
    with pytest.raises(SchemaApplyError, match='expired'):expired.apply(request(receipt), 7, 'bound-route', execute)
    execute.assert_not_called()


def test_concurrent_claim_and_restart_never_redispatch(tmp_path):
    store, receipt = review(tmp_path)
    another = PostgreSQLSchemaApplications(store.path, lambda: 100)
    execute = Mock(return_value={'state': 'native_commit_returned'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: item.apply(request(receipt), 7, 'bound-route', execute), [store, another]))
    assert execute.call_count == 1
    assert all(result['state'] in {'unknown_outcome', 'native_commit_returned'} for result in results)
    assert another.apply(request(receipt), 7, 'bound-route', execute)['state'] == 'native_commit_returned'
    assert execute.call_count == 1


def test_process_death_remains_unknown_after_restart(tmp_path):
    store, receipt = review(tmp_path)
    def terminate(_record):raise SystemExit()
    with pytest.raises(SystemExit):store.apply(request(receipt), 7, 'bound-route', terminate)
    execute = Mock()
    reopened = PostgreSQLSchemaApplications(store.path, lambda: 100)
    assert reopened.apply(request(receipt), 7, 'bound-route', execute)['state'] == 'unknown_outcome'
    execute.assert_not_called()


def test_unsupported_objects_never_prepare(tmp_path):
    before, after = documents()
    for value in (before, after):value['rows'][IDENTITY]['kind'] = 'materialized-view'
    plan = build_plan(before, after, before)
    assert not plan['application_supported']
    with pytest.raises(SchemaApplyError):
        PostgreSQLSchemaApplications(tmp_path / 'r.json').review(plan, before, after, 7, 'route', 'db')


@pytest.mark.parametrize('kind', ['trigger', 'rule', 'policy'])
def test_reloaded_child_deletion_retains_owning_table_baseline(tmp_path, kind):
    from tools.tests.test_postgresql_schema_plan import owned_documents
    identity, (before, after, live), _ = owned_documents(kind)
    after['rows'][identity]['native']['drop'] = True
    plan = build_plan(before, after, live)
    assert plan['application_supported'], plan['blockers']
    path = tmp_path / 'owned.json'
    store = PostgreSQLSchemaApplications(path, lambda: 100)
    receipt = store.review(plan, before, after, 7, 'bound-route', 'postgresql-database:42')
    def execute(record):
        assert set(record['baseline']['rows']) == {identity, IDENTITY}
        assert set(record['desired']['rows']) == {identity, IDENTITY}
        fresh = build_plan(record['baseline'], record['desired'], live)
        assert fresh['application_supported']
        assert fresh['execution_sha256'] == plan['execution_sha256']
        return {'state': 'native_commit_returned'}
    reopened = PostgreSQLSchemaApplications(path, lambda: 100)
    assert reopened.apply(request(receipt), 7, 'bound-route', execute)['state'] == 'native_commit_returned'
