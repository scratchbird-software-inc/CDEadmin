"""Event forms preserve omitted ALTER settings and expose exact native scopes."""
import pytest
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine

TARGET={'display_path':['d`é','e`é']}


def compile(operation,draft,target=TARGET):
    request={'resource_kind':'event','operation_id':operation,'draft':draft,'target_resource':target}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors'],MYSQL_ADMINISTRATION.validate(request)
    return MYSQL_ADMINISTRATION._compile(request)


def test_comment_only_alter_does_not_reset_any_native_state():
    result=compile('alter',{'comment':"owner's note"})
    assert result['statements']==[{'source':'ALTER EVENT `d``é`.`e``é` COMMENT %s','parameters':("owner's note",)}]
    assert result['mysql_owned_event_scope']
    from pgadmin.cdeadmin.providers.mysql_family.descriptor_contracts import routine_contract
    fields=routine_contract('event','alter')['fields']
    assert {field['field_id']:field.get('default') for field in fields if field['field_id'] in {'status','completion'}}=={'status':'UNCHANGED','completion':'UNCHANGED'}


def test_create_retains_native_options_and_binds_time_zone_and_comment():
    result=compile('create',{'database':'d`é','name':'e`é','schedule':"AT '2037-01-01 12:00:00'",'body':'BEGIN SELECT 1; SELECT 2; END',
        'time_zone':'+05:30','completion':'PRESERVE','status':'DISABLE ON REPLICA','comment':"'quoted'",'definer_user':'u`é','definer_host':'%', 'if_not_exists':True},None)
    assert result['statements'][0]=={'source':'SET SESSION time_zone=%s','parameters':('+05:30',)}
    statement=result['statements'][1]
    assert statement['source'].startswith('CREATE DEFINER=`u``é`@`%` EVENT IF NOT EXISTS `d``é`.`e``é`')
    assert 'DISABLE ON REPLICA COMMENT %s DO BEGIN' in statement['source']
    assert statement['parameters']==("'quoted'",)


def test_rename_can_cross_databases_without_losing_exact_names():
    assert compile('rename',{'new_database':'other`é','new_name':'new`é'})['statements'][0]['source']=='ALTER EVENT `d``é`.`e``é` RENAME TO `other``é`.`new``é`'
    assert compile('alter',{'clear_comment':True})['statements'][0]['parameters']==('',)


@pytest.mark.parametrize('draft',[{}, {'status':'UNKNOWN'}, {'enabled':True,'status':'ENABLE'},
    {'clear_comment':True,'comment':'x'}, {'time_zone':'\x00','body':'SELECT 1'}, {'schedule':'EVERY 1 DAY; DROP DATABASE d'}, {'enabled':'true'}])
def test_invalid_or_empty_event_changes_refuse_validation(draft):
    result=MYSQL_ADMINISTRATION.validate({'resource_kind':'event','operation_id':'alter','target_resource':TARGET,'draft':draft})
    assert result['errors']


def test_drop_contract_adds_no_generic_cascade_default():
    # Visual administration fills each contract field's default into the
    # draft; a generic CASCADE default made every native event drop invalid.
    import copy
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient
    catalog = {row['resource_kind']: row for row in MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']}
    legacy = next(item for item in catalog['event']['operations'] if item['operation_id'] == 'drop')['form']['fields']
    assert 'cascade' in {field['field_id'] for field in legacy}
    contract = MySQLDBAPIClient.admin_operation_field_contract(None, {
        'resource_kind': 'event', 'operation_id': 'drop', 'legacy_fields': copy.deepcopy(legacy), 'draft': {}})
    fields = contract['fields']
    assert [field['field_id'] for field in fields] == ['confirmation'] and fields[0]['required'] is True
    admitted = {field['field_id']: field['default'] for field in fields if 'default' in field}
    admitted['confirmation'] = 'nightly'
    target = {'resource_kind': 'event', 'display_name': 'nightly', 'display_path': ['db', 'nightly']}
    request = {'resource_kind': 'event', 'operation_id': 'drop', 'draft': admitted, 'target_resource': target}
    assert MYSQL_ADMINISTRATION.validate(request)['errors'] == []
