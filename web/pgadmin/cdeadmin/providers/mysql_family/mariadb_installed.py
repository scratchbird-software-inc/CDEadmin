"""MariaDB installed completion metadata; no values, code or library paths."""
VARIABLES = (
    'SELECT VARIABLE_NAME,VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,'
    'NUMERIC_MIN_VALUE,NUMERIC_MAX_VALUE,NUMERIC_BLOCK_SIZE,ENUM_VALUE_LIST,'
    'VARIABLE_COMMENT FROM information_schema.SYSTEM_VARIABLES '
    'ORDER BY VARIABLE_NAME LIMIT 25001')
LOADABLE_FUNCTIONS = 'SELECT name,ret,type FROM mysql.func ORDER BY name LIMIT 25001'
PLUGIN_FUNCTIONS = (
    "SELECT PLUGIN_NAME,PLUGIN_STATUS FROM information_schema.PLUGINS "
    "WHERE PLUGIN_TYPE='FUNCTION' ORDER BY PLUGIN_NAME LIMIT 25001")
RETURN_TYPES = {0: 'STRING_RESULT', 1: 'REAL_RESULT', 2: 'INT_RESULT',
                3: 'ROW_RESULT', 4: 'DECIMAL_RESULT', 5: 'TIME_RESULT'}


def discover(query, add):
    for name, scope, data_type, readonly, minimum, maximum, block, choices, comment in query(
            'native-variable-metadata', VARIABLES):
        add('system-variable', [name], str(scope) + ' ' + str(data_type) + ': ' + str(comment),
            native_variable={'scope': scope, 'data_type': data_type, 'read_only': readonly,
                'minimum': minimum, 'maximum': maximum, 'block_size': block,
                'enum_value_list': choices, 'metadata_origin': 'information_schema.SYSTEM_VARIABLES',
                'current_value_observed': False, 'default_value_observed': False})
    registrations = query('native-loadable-functions', LOADABLE_FUNCTIONS)
    for name, result, kind in registrations:
        add('function', [name], 'MariaDB registered loadable ' + str(kind),
            native_function={'origin': 'mysql.func', 'registration_observed': True,
                'return_type_code': result, 'return_type': RETURN_TYPES.get(result),
                'kind': kind, 'signature_observed': False, 'native_load_state_observed': False,
                'invocation_verified': False, 'scope': 'global-registration'})
    for name, status in query('native-plugin-functions', PLUGIN_FUNCTIONS):
        if str(status).upper() == 'ACTIVE':
            add('function', [name], 'MariaDB ACTIVE FUNCTION plugin',
                native_function={'origin': 'information_schema.PLUGINS',
                    'plugin_status': status, 'kind': 'FUNCTION',
                    'signature_observed': False, 'return_type_observed': False,
                    'invocation_verified': False, 'scope': 'global-plugin'})
    return bool(registrations)
