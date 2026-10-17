"""Native observation semantics, selection admission and packaged contracts."""
import json
from pathlib import Path

import pytest

from pgadmin.cdeadmin.providers.postgresql import metrics
from pgadmin.cdeadmin.providers.postgresql.contracts import PROFILE, dialect_task_ids
from pgadmin.cdeadmin.engine_contracts import contract_descriptor
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from tools.reference_engine_demos.generate_postgresql_metrics_inventory import metric


def test_packaged_postgresql_contracts_have_exact_native_acceptance():
    result=contract_descriptor(PROFILE,'pgadmin.cdeadmin.providers.postgresql.provider',dialect_task_ids())
    assert result['state']=='passed'
    root=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/providers/postgresql'
    dialect=json.loads((root/'postgresql_dialect_18_3.json').read_text())
    assert len(dialect['task_templates'])==37
    assert all(task['source_format']=='provider_native_compiler_reference' and task['native_statement_sha256s'] for task in dialect['task_templates'])
    inventory=metrics.inventory()
    assert len(inventory)==52
    assert sum(len(item['columns']) for item in inventory.values())==604
    assert metrics.source_catalog()['state']=='available'


@pytest.mark.parametrize('value',[None,'pg_stat_wal',['pg_stat_wal','pg_stat_wal'],['pg_stat_unrecognized'],[True]])
def test_native_selection_is_bounded_known_and_unambiguous(value):
    with pytest.raises(ValueError):metrics.select_sources(value)


def test_native_selection_is_frozen_and_catalog_is_not_mutable():
    value=['pg_stat_wal'];policy=MonitoringPolicy(owner_id=1,endpoint_id='endpoint',target_id=None,
        interval_seconds=15,native_metric_sources=value)
    value.append('pg_stat_io')
    assert policy.native_metric_sources==('pg_stat_wal',)
    catalog=metrics.source_catalog();catalog['sources'][0]['columns'][0]['name']='mutated'
    assert metrics.source_catalog()['sources'][0]['columns'][0]['name']!='mutated'
    assert metrics.select_sources([])==()


@pytest.mark.parametrize('view,column,value_type,kind,unit,reset',[
    ('pg_stat_database','numbackends','integer','gauge','connections','current_native_state_or_operation'),
    ('pg_stat_wal','wal_bytes','numeric','counter','bytes','native_statistics_reset_or_object_lifecycle'),
    ('pg_stat_replication','replay_lag','interval','gauge','seconds','current_native_state_or_operation'),
    ('pg_stat_recovery_prefetch','wal_distance','integer','gauge','bytes','current_native_state_or_operation'),
    ('pg_stat_xact_all_tables','n_tup_ins','bigint','counter','rows','native_current_transaction_end'),
    ('pg_stat_all_tables','n_mod_since_analyze','bigint','counter','rows','native_analyze'),
    ('pg_prepared_statements','generic_plans','bigint','counter','plans','native_prepared_statement_lifetime'),
])
def test_native_metric_semantics_retain_reset_and_unit(view,column,value_type,kind,unit,reset):
    result=metric(view,column,value_type)
    assert (result['kind'],result['unit'],result['reset_behavior'])==(kind,unit,reset)


@pytest.mark.parametrize('view,column,value_type',[
    ('pg_stat_activity','pid','integer'),('pg_stat_wal_receiver','sender_port','integer'),
    ('pg_shmem_allocations','off','bigint'),('pg_settings','setting','text'),
    ('pg_locks','objid','oid'),('pg_stat_activity','query','text'),
])
def test_native_identifiers_and_settings_are_not_counters(view,column,value_type):
    assert metric(view,column,value_type) is None
