"""Native libraries and global UDFs keep their distinct identities/lifecycles."""
import base64
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.mysql_program_objects import compile_operation
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


def test_library_source_is_bound_or_exact_binary_and_alter_is_comment_only():
    statement=compile_operation('library','create',{'database':'d`é','name':'l`é',
        'body':"export const value='quoted'",'comment':"comment'\\"},None)
    assert statement['source']=='CREATE LIBRARY `d``é`.`l``é` LANGUAGE JAVASCRIPT COMMENT %s AS %s'
    assert statement['parameters']==("comment'\\","export const value='quoted'")
    result=compile_operation('library','create',{'database':'d','name':'l','body':base64.b64encode(b'\x00\xff').decode(), 'source_format':'binary_base64'},None)
    assert result['source'].endswith(" AS X'00ff'") and not result['parameters']
    assert compile_operation('library','alter',{'comment':'changed'},{'display_path':['d','l']})['source']=='ALTER LIBRARY `d`.`l` COMMENT %s'
    with pytest.raises(RelationalClientError):compile_operation('library','alter',{'body':'replacement'},{'display_path':['d','l']})


@pytest.mark.parametrize('kind,draft',[
    ('library',{'database':'d','name':'l','body':'AA?','source_format':'binary_base64'}),
    ('library',{'database':'d','name':'l','body':'x','if_not_exists':'true'}),
    ('library',{'database':'d','name':'l','body':'x\x00'}),
    ('loadable-function',{'name':'u','return_type':'ROW','library':'x.so'}),
    ('loadable-function',{'name':'u','return_type':'STRING','library':'x.so','aggregate':'true'}),
])
def test_invalid_program_options_refuse_before_dispatch(kind,draft):
    with pytest.raises(RelationalClientError):compile_operation(kind,'create',draft,None)


def test_component_owned_function_is_inspection_only():
    with pytest.raises(RelationalClientError,match='owning lifecycle'):
        compile_operation('loadable-function','drop',{}, {'display_path':['u'],'native':{'registration_origin':'runtime-service'}})
    assert compile_operation('loadable-function','drop',{}, {'display_path':['u'],'native':{'registration_origin':'mysql.func'}})['source']=='DROP FUNCTION `u`'


def test_native_forms_are_mysql_only_and_global_scope_is_compiled():
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    for kind,ops in [('library',{'inspect','create','alter','drop'}),('loadable-function',{'inspect','create','drop'})]:
        row=next(row for row in catalog['objects'] if row['resource_kind']==kind)
        assert {item['operation_id'] for item in row['operations']}==ops
        assert MARIADB_ADMINISTRATION.supports(kind,'create') == (kind == 'loadable-function')
    result=MYSQL_ADMINISTRATION._compile({'resource_kind':'loadable-function','operation_id':'create','draft':{'name':'u','return_type':'INTEGER','library':'x.so'}})
    assert result['mysql_global_function_scope']


def test_global_udf_dispatch_refuses_borrowed_or_database_selected_connection():
    compiled=MYSQL_ADMINISTRATION._compile({'resource_kind':'loadable-function','operation_id':'create','draft':{'name':'u','return_type':'INTEGER','library':'x.so'}})
    request={'provider_payload':{'route':{'database':'demo','user':'registered'},'compiled':compiled}}
    client=Mock();connection=Mock();client._connect.return_value=connection
    with pytest.raises(RelationalClientError,match='owned connection'):
        MYSQL_ADMINISTRATION.apply(client,request,connection=connection)
    client._connect.assert_not_called()
    cursor=connection.cursor.return_value;cursor.fetchone.return_value=('leaked_db',)
    client.config.execute_on_connection=False
    with pytest.raises(RelationalClientError,match='dispatch refused'):MYSQL_ADMINISTRATION.apply(client,request)
    assert client._connect.call_args.args[0]['route']=={'database':None,'user':'registered'}
    cursor.execute.assert_called_once_with('SELECT DATABASE()')
    client._forget_and_close.assert_called_once_with(connection)
