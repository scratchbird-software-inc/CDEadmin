"""Native variable metadata is separate from value presence and sensitivity."""
from pgadmin.cdeadmin.providers.mysql_family import system_variables as variables


def test_native_completion_preserves_component_types_and_session_scope_without_reading_values():
    from unittest.mock import Mock
    from pgadmin.cdeadmin.providers.native_editor import metadata
    cursor=Mock()
    rows=[]
    def execute(sql):
        nonlocal rows
        if sql.startswith('SELECT VERSION()'): rows=[('9.7.0','mysql','','utf8mb4',0)]
        elif 'CURRENT_USER()' in sql: rows=[('owner@host','NONE')]
        elif 'variables_metadata' in sql:
            rows=[('validate_password.length','GLOBAL','Integer','0','4294967295','Password length'),
                  ('gtid_next','SESSION_ONLY','String',None,None,'Transaction identity')]
        else: rows=[]
    cursor.execute.side_effect=execute
    cursor.fetchmany.side_effect=lambda *_:rows
    result=metadata(type('Handle',(),{'cursor':lambda _:cursor})(),'mysql')
    variables={row['display_name']:row for row in result['resources'] if row['resource_kind']=='system-variable'}
    assert variables['validate_password.length']['native_variable']=={'scope':'GLOBAL','data_type':'Integer','minimum':'0','maximum':'4294967295'}
    assert variables['gtid_next']['native_variable']['scope']=='SESSION_ONLY'
    assert all('value' not in row and 'value' not in row['native_variable'] for row in variables.values())
    assert not any('global_variables' in call.args[0] or 'session_variables' in call.args[0] for call in cursor.execute.call_args_list)


def test_session_only_server_resources_have_inspection_and_explicit_persisted_cleanup():
    assert variables.administration({'variable_scope':'SESSION_ONLY'})=={'allowed_operations':['inspect']}
    assert variables.administration({'variable_scope':'SESSION_ONLY','persisted_present':1})=={'allowed_operations':['inspect','reset_persist']}
    assert variables.administration({'variable_scope':'SESSION'}) is None
    assert variables.administration({'variable_scope':'GLOBAL'}) is None
    assert variables.administration({'persisted_present':1}) is None


def test_persisted_null_and_empty_are_explicitly_ambiguous_in_current_and_legacy_captures():
    assert variables.persisted_value_ambiguous({'persisted_value_state':'null_or_empty'})
    assert variables.persisted_value_ambiguous({'persisted_value_state':'unconfirmed'})
    assert variables.persisted_value_ambiguous({'persisted_present':1,'persisted_value':''})
    assert variables.persisted_value_ambiguous({'persisted_value':''})
    assert not variables.persisted_value_ambiguous({'persisted_present':0,'persisted_value':''})
    assert not variables.persisted_value_ambiguous({'persisted_value_state':'value','persisted_value':'1'})
    assert not variables.persisted_value_ambiguous({'persisted_value_state':'absent'})
