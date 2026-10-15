"""Native InnoDB tablespace kinds, exact paths and lifecycle admission."""
import pytest
from pgadmin.cdeadmin.providers import mysql_tablespaces as spaces
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

TARGET={'display_name':'space`é','native':{'space_type':'General','engine':'InnoDB'}}


@pytest.mark.parametrize('operation,draft,expected',[
    ('create',{'name':'space`é','datafile':"path/'\\é.ibd",'file_block_size':16384,'autoextend_size':4194304,'encryption':'N'},"CREATE TABLESPACE `space``é` ADD DATAFILE %s FILE_BLOCK_SIZE=16384 AUTOEXTEND_SIZE=4194304 ENCRYPTION='N' ENGINE=InnoDB"),
    ('alter',{'change':'AUTOEXTEND_SIZE','autoextend_size':8388608},'ALTER TABLESPACE `space``é` AUTOEXTEND_SIZE=8388608'),
    ('rename',{'new_name':'renamed`space'},'ALTER TABLESPACE `space``é` RENAME TO `renamed``space`'),
    ('drop',{},'DROP TABLESPACE `space``é`')])
def test_native_tablespace_plans_preserve_exact_parameters(operation,draft,expected):
    request={'resource_kind':'tablespace','operation_id':operation,'draft':draft,'target_resource':TARGET,'_provider_route':{'host':'trusted'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    compiled=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
    assert compiled['source']==expected
    if operation=='create':assert compiled['parameters']==(draft['datafile'],) and draft['datafile'] not in MYSQL_ADMINISTRATION.plan(request)['command_preview']['statements'][0]['source']


def test_undo_state_is_native_and_general_options_cannot_silently_apply_to_it():
    undo={'display_name':'owned_undo','native':{'space_type':'Undo','engine':'InnoDB'}}
    assert spaces.compile_operation('alter',{'change':'INACTIVE'},undo)['source']=='ALTER UNDO TABLESPACE `owned_undo` SET INACTIVE ENGINE=InnoDB'
    assert spaces.compile_operation('create',{'name':'undo','space_type':'Undo','datafile':'owned.ibu','encryption':'UNCHANGED'},None)['source']=='CREATE UNDO TABLESPACE `undo` ADD DATAFILE %s ENGINE=InnoDB'
    for operation,draft,target in [('rename',{'new_name':'new'},undo),('alter',{'change':'ENCRYPTION','encryption':'N'},undo),
        ('drop',{}, {'display_name':'innodb_undo_001','native':undo['native']}),('drop',{}, {'display_name':'system','native':{'space_type':'System','engine':'InnoDB'}}),
        ('create',{'name':'bad','datafile':'\x00'},None),('alter',{'change':'AUTOEXTEND_SIZE','autoextend_size':True},TARGET)]:
        with pytest.raises(RelationalClientError):spaces.compile_operation(operation,draft,target)


def test_native_storage_forms_do_not_inherit_mariadb_tablespace_syntax():
    resource=next(row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects'] if row['resource_kind']=='tablespace')
    operations={row['operation_id']:row for row in resource['operations']}
    assert spaces.OPERATIONS<=operations.keys()
    assert operations['drop']['confirmation_required'] and operations['drop']['target_required']
    assert not MARIADB_ADMINISTRATION.supports('tablespace','rename')


def test_discovered_runtime_options_cannot_be_bypassed():
    target={**TARGET,'native':{**TARGET['native'],'available_tablespace_changes':['AUTOEXTEND_SIZE','ENGINE_ATTRIBUTE']}}
    with pytest.raises(RelationalClientError,match='unavailable'):
        spaces.compile_operation('alter',{'change':'ENCRYPTION','encryption':'Y'},target)
    assert spaces.compile_operation('alter',{'change':'AUTOEXTEND_SIZE','autoextend_size':0},target)['source'].endswith('AUTOEXTEND_SIZE=0')
