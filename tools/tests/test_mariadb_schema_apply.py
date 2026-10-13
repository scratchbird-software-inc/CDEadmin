"""MariaDB durable admissions preserve native scope and uncertain dispatch."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from tools.tests.test_mariadb_sql_export import model
from tools.tests.test_mariadb_schema_plan import table
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import plan
from pgadmin.cdeadmin.workspace.mariadb_schema_apply import MariaDBSchemaApplications
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplyError


def reviewed(path):
    before = model(); table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` INT)'
    desired = deepcopy(before)
    table(desired)['native']['definition'] = table(desired)['native']['definition'].replace('INT', 'BIGINT')
    preview = plan(before, desired, before); preview['native_grammar_validated'] = True
    applications = MariaDBSchemaApplications(path/'receipts.json')
    receipt = applications.review(preview, before, desired, 'owner', 'binding', 'target')
    return applications, receipt


def request(receipt):
    return {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}


def test_process_death_retains_unknown_receipt_and_never_replays(tmp_path):
    applications, receipt = reviewed(tmp_path)
    class ProcessDeath(BaseException): pass
    def die(record):
        assert record['desired']['rows'][record['plan']['operations'][0]['resource_id']]['native']['system_object'] is False
        raise ProcessDeath()
    with pytest.raises(ProcessDeath): applications.apply(request(receipt), 'owner', 'binding', die)
    restarted = MariaDBSchemaApplications(tmp_path/'receipts.json'); execute = Mock()
    assert restarted.apply(request(receipt), 'owner', 'binding', execute)['state'] == 'unknown_outcome'
    execute.assert_not_called()
    for owner, binding in [('other', 'binding'), ('owner', 'other')]:
        with pytest.raises(SchemaApplyError): restarted.get(receipt['review_id'], owner, binding)


def test_confirmation_digest_and_completed_outcome_are_bound(tmp_path):
    applications, receipt = reviewed(tmp_path); execute = Mock(return_value={'state': 'committed', 'rediscovery_verified': True})
    for change in [{'confirmed': False}, {'review_digest': 'different'}]:
        with pytest.raises(SchemaApplyError): applications.apply({**request(receipt), **change}, 'owner', 'binding', execute)
    result = applications.apply(request(receipt), 'owner', 'binding', execute)
    assert result['state'] == 'committed' and result['plan']['engine_id'] == 'mariadb'
    applications.apply(request(receipt), 'owner', 'binding', execute)
    execute.assert_called_once()


def test_workspace_requires_maintenance_confirmation_before_receipt_dispatch(tmp_path):
    from dataclasses import dataclass, asdict
    from types import SimpleNamespace
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
    @dataclass
    class Context:
        endpoint_id: str = 'owned'
        profile_id: str = 'mariadb-native'
    context = Context(); endpoint = {'route': {'database': 'demo'}}
    provider = Mock(); service = object.__new__(ProviderWorkspaceService)
    service._mariadb_catalog_context = lambda server, target: (context, endpoint, provider)
    service._principal_id = lambda server: 'owner'
    store = JsonOperationStore(tmp_path/'operations.json')
    service.operation_bus = SimpleNamespace(store=store); service.resource_service = Mock()
    binding = digest({'context': asdict(context), 'route': endpoint['route'], 'target': 'target'})
    applications = MariaDBSchemaApplications(str(store.path)+'.mariadb-schema-applications.json')
    before = model(); table(before)['native']['definition'] = 'CREATE TABLE `a` (`id` INT)'
    desired = deepcopy(before); table(desired)['native']['definition'] += " COMMENT='changed'"
    preview = plan(before, desired, before); preview['native_grammar_validated'] = True
    receipt = applications.review(preview, before, desired, 'owner', binding, 'target')
    body = {**request(receipt), 'database_target_id': 'target'}
    with pytest.raises(ProviderWorkspaceError, match='maintenance window'):
        service.mariadb_schema_application(None, 'mariadb_schema_apply', body)
    provider.apply_schema_review.assert_not_called()
    assert applications.get(receipt['review_id'], 'owner', binding)['state'] == 'reviewed'
    provider.apply_schema_review.return_value = {'state': 'committed', 'rediscovery_verified': True}
    result = service.mariadb_schema_application(None, 'mariadb_schema_apply', {**body, 'maintenance_window_confirmed': True})
    assert result['state'] == 'committed'
    provider.apply_schema_review.assert_called_once()
