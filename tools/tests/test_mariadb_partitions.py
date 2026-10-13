"""MariaDB partition operations retain their native context and confirmation."""
import pytest
from pgadmin.cdeadmin.providers import mariadb_partitions as partitions
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION, MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

TARGET={'display_name':'p`0','display_path':['db`é','t`é','p`0']}
TABLE={'display_name':'t`é','display_path':['db`é','t`é']}


def test_native_conversion_is_not_mysql_partition_grammar():
    draft={'exchange_database':'db`é','exchange_table':'standalone','definitions':'PARTITION p2 VALUES LESS THAN (30)'}
    source=partitions.compile_operation('table','convert_from_table',draft,TABLE)['source']
    assert source=='ALTER TABLE `db``é`.`t``é` CONVERT TABLE `db``é`.`standalone` TO PARTITION p2 VALUES LESS THAN (30) WITH VALIDATION'
    source=partitions.compile_operation('partition','convert_to_table',{'exchange_database':'db','exchange_table':'standalone','validation':'WITHOUT VALIDATION'},TARGET)['source']
    assert source.endswith('CONVERT PARTITION `p``0` TO TABLE `db`.`standalone` WITHOUT VALIDATION')
    assert not MYSQL_ADMINISTRATION.supports('table','convert_from_table')
    assert not MYSQL_ADMINISTRATION.supports('partition','repair')


def test_all_native_forms_are_context_bound_confirmed_and_maria_named():
    catalog={row['resource_kind']:row for row in MARIADB_ADMINISTRATION.catalog(catalog_for_engine('mariadb'))['objects']}
    for kind,operations in partitions.OPERATIONS.items():
        nodes={row['operation_id']:row for row in catalog[kind]['operations']}
        for operation in operations:
            assert MARIADB_ADMINISTRATION.supports(kind,operation)
            assert nodes[operation]['target_required'] and nodes[operation]['confirmation_required']
            assert nodes[operation]['form']['form_id']=='mariadb.'+kind+'.'+operation


def test_runtime_dialect_gate_covers_every_executable_native_admin_task():
    import json
    from pathlib import Path
    from pgadmin.cdeadmin.engine_contracts import validate_dialect_contract
    from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE
    path=Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_dialect_12_2_2.json'
    document=validate_dialect_contract(json.loads(path.read_text()),MARIADB_PROFILE,
                                      MARIADB_ADMINISTRATION.dialect_task_ids())
    assert document['coverage']['authoritative_task_count']==len(MARIADB_ADMINISTRATION.dialect_task_ids())


@pytest.mark.parametrize('draft', [
    {'exchange_database':'db','exchange_table':'t','definitions':'PARTITION p2 VALUES LESS THAN (30);DROP TABLE t'},
    {'exchange_database':'db','exchange_table':'t','definitions':'PARTITION p2 VALUES LESS THAN (30)','validation':'invented'},
    {'exchange_database':'db','exchange_table':'t','definitions':'PARTITION p2 VALUES LESS THAN (30)','disable_checks':True},
])
def test_conversion_refuses_unadmitted_fragments_and_options(draft):
    with pytest.raises(RelationalClientError):partitions.compile_operation('table','convert_from_table',draft,TABLE)
