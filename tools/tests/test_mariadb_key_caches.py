"""Native segmented cache lifecycle, batch/partition handlers and refusals."""
import uuid
import pytest
from test_mariadb_server_diagnostics import native,record_native_execution
from pgadmin.cdeadmin.providers.mysql_family import mariadb_key_caches as caches
from pgadmin.cdeadmin.sdk import RelationalClientError
from ui_descriptor_roundtrip import engine_operations, operation_draft


def plan(n,op,**values):
    draft=operation_draft(engine_operations('mariadb')[op+'@server'],values,confirmation=n.target['display_name'])
    return n.client.plan_admin_operation(dict(resource_kind='server',operation_id=op,target_resource=n.target,draft=draft,_provider_route=n.route))


def execute(n,op,**values):
    planned=plan(n,op,**values)
    result=n.client.apply_admin_operation(planned)
    record_native_execution(planned,result,'management_observation')
    receipt=result['management_observation']
    assert receipt['native_acknowledged']and result['connection_release']['connection_released']
    assert not result['commit_requested']and not result['rollback_requested']and not result['automatic_retry']
    return receipt


def test_native_named_segmented_cache_lifecycle_and_exact_default(native):
    n=native;cache='owned_'+uuid.uuid4().hex[:12]
    values={'key_buffer_size':'1048576','key_cache_block_size':'1024','key_cache_division_limit':'80',
        'key_cache_age_threshold':'500','key_cache_file_hash_size':'1024','key_cache_segments':'4'}
    try:
        for variable,text in values.items():
            receipt=execute(n,'configure_key_cache',cache_name=cache,variable=variable,value=text)
            assert receipt['after']['values'][variable]==text
        observed=execute(n,'inspect_key_caches')
        assert 'KEY_CACHE_NAME'in observed['columns']
        assert any(row[0]==cache for row in observed['rows'])
        assert execute(n,'inspect_key_cache',cache_name=cache)['after']['values']==values
        default=execute(n,'configure_key_cache',cache_name=cache,variable='key_cache_division_limit',value_mode='DEFAULT')
        assert default['after']['values']['key_cache_division_limit']=='100'
        released=execute(n,'release_key_cache',cache_name=cache)
        assert released['after']['values']['key_buffer_size']=='0'
    finally:n.cursor.execute('SET GLOBAL `'+cache+'`.key_buffer_size=0')


def test_native_batch_and_partition_cache_handlers_preserve_original_work(native):
    n=native;cache='owned_'+uuid.uuid4().hex[:12]
    n.cursor.execute('CREATE TABLE IF NOT EXISTS cached_a(id INT PRIMARY KEY,value INT,KEY ix(value)) ENGINE=MyISAM')
    n.cursor.execute('CREATE TABLE IF NOT EXISTS cached_b(id INT PRIMARY KEY) ENGINE=MyISAM')
    n.cursor.execute('CREATE TABLE IF NOT EXISTS cached_parts(id INT PRIMARY KEY) ENGINE=MyISAM PARTITION BY HASH(id) PARTITIONS 2')
    try:
        execute(n,'configure_key_cache',cache_name=cache,variable='key_buffer_size',value='1048576')
        n.cursor.execute('START TRANSACTION');n.cursor.execute('INSERT INTO observer_pending VALUES(47)');n.cursor.execute('SAVEPOINT caller')
        tables=[dict(database='owned_management',table='cached_a'),dict(database='owned_management',table='cached_b')]
        selection=[{'table_index':0,'index_name':'ix'},{'table_index':1,'index_name':'PRIMARY'}]
        result=execute(n,'assign_index_cache',cache_name=cache,tables=tables,index_selection=selection)
        assert result['native_reported_success']and len(result['rows'])==2
        for row in tables:row['ignore_leaves']=True
        assert execute(n,'preload_index_cache',tables=tables,index_selection=selection)['native_reported_success']
        for op in ['assign_index_cache','preload_index_cache']:
            result=execute(n,op,**({'cache_name':cache}if op=='assign_index_cache'else{}),
                tables=[dict(database='owned_management',table='cached_parts')],partitions=['p0'])
            assert result['native_reported_success']
        n.cursor.execute('ROLLBACK TO SAVEPOINT caller');n.cursor.execute('SELECT * FROM observer_pending');assert n.cursor.fetchall()==[(47,)]
    finally:
        n.handle.rollback();n.cursor.execute('SET GLOBAL `'+cache+'`.key_buffer_size=0')
        for name in ['cached_a','cached_b','cached_parts']:n.cursor.execute('DROP TABLE '+name)


def test_missing_native_index_engine_and_stale_cache_refuse(native):
    n=native
    with pytest.raises(RelationalClientError,match='default cache'):plan(n,'release_key_cache',cache_name='default')
    with pytest.raises(RelationalClientError,match='MyISAM'):plan(n,'preload_index_cache',tables=[dict(database='owned_management',table='observer_pending')])
    cache='owned_'+uuid.uuid4().hex[:12]
    try:
        reviewed=plan(n,'configure_key_cache',cache_name=cache,variable='key_buffer_size',value='1048576')
        n.cursor.execute('SET GLOBAL `'+cache+'`.key_cache_segments=2')
        with pytest.raises(RelationalClientError)as error:n.client.apply_admin_operation(reviewed)
        assert not error.value.native_dispatched and error.value.connection_release['connection_released']
    finally:n.cursor.execute('SET GLOBAL `'+cache+'`.key_buffer_size=0')
