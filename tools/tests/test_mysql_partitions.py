"""Exact native partition targets, fragments and confirmations."""
import pytest
from pgadmin.cdeadmin.providers import mysql_partitions as partitions
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

TARGET={'display_name':'p`0','display_path':['db`é','t`é','p`0']}
TABLE={'display_name':'t`é','display_path':['db`é','t`é']}


@pytest.mark.parametrize('operation', ['analyze','check','optimize','rebuild','truncate','drop'])
def test_partition_mutations_address_exact_owning_table(operation):
    result=partitions.compile_operation('partition',operation,{},TARGET)
    assert result['source']==f'ALTER TABLE `db``é`.`t``é` {operation.upper()} PARTITION `p``0`' and not result['parameters']


def test_exchange_is_native_and_defaults_to_validating_rows():
    draft={'exchange_database':'other','exchange_table':'t'}
    assert partitions.compile_operation('partition','exchange',draft,TARGET)['source'].endswith('WITH TABLE `other`.`t` WITH VALIDATION')
    with pytest.raises(RelationalClientError):partitions.compile_operation('partition','exchange',{**draft,'validation':'INVENTED'},TARGET)


@pytest.mark.parametrize('value',["PARTITION p0 VALUES LESS THAN (10); DROP TABLE t",'PARTITION p0 VALUES LESS THAN (10))',"PARTITION p0 VALUES LESS THAN ('a\\b')",'PARTITION p0 VALUES LESS THAN (10) /*x*/', 'ADD COLUMN x INT', 'PARTITION p0 VALUES LESS THAN (10), ADD COLUMN x INT'])
def test_fragments_cannot_escape_native_partition_clause(value):
    with pytest.raises(RelationalClientError):partitions.fragment(value,True)


def test_native_definitions_preserve_expression_and_subpartition_text():
    value="PARTITION `p;0` VALUES LESS THAN ('a''b') (SUBPARTITION s0, SUBPARTITION s1), PARTITION p1 VALUES LESS THAN (MAXVALUE)"
    assert partitions.fragment(value,True)==value
    assert partitions.compile_operation('partition','reorganize',{'definitions':value},TARGET)['source'].endswith('INTO ('+value+')')
    with pytest.raises(RelationalClientError):partitions.compile_operation('partition','reorganize',{'partitions':[{}],'definitions':value},TARGET)
    for value in [True,0,8193,1.5]:
        with pytest.raises(RelationalClientError):partitions.compile_operation('table','coalesce_partitions',{'count':value},TABLE)


def test_forms_and_compiler_are_mysql_specific_and_confirmed():
    catalog={row['resource_kind']:row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']}
    for kind,operations in partitions.OPERATIONS.items():
        nodes={row['operation_id']:row for row in catalog[kind]['operations']}
        for operation in operations:
            assert MYSQL_ADMINISTRATION.supports(kind,operation) and not MARIADB_ADMINISTRATION.supports(kind,operation)
            assert nodes[operation]['target_required'] and nodes[operation]['confirmation_required']
            assert nodes[operation]['form']['form_id']=='mysql.'+kind+'.'+operation
    request={'resource_kind':'table','operation_id':'add_partitions','target_resource':TABLE,'draft':{'mode':'COUNT','count':2},'_provider_route':{'host':'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source'].endswith('ADD PARTITION PARTITIONS 2')
