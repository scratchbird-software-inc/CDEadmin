"""Named CPython SQLite boolean db_config controls on the retained handle.

Interpreter booleans use their public methods. Additional typed signatures
delegate to the original-handle native component; no caller-supplied numeric
opcodes or pointers are admitted.
"""
from ...sdk import RelationalClientError

CONFIGS = {name.lower(): 'SQLITE_DBCONFIG_' + name for name in (
    'ENABLE_FKEY', 'ENABLE_TRIGGER', 'ENABLE_FTS3_TOKENIZER',
    'ENABLE_LOAD_EXTENSION', 'NO_CKPT_ON_CLOSE', 'ENABLE_QPSG', 'TRIGGER_EQP',
    'RESET_DATABASE', 'DEFENSIVE', 'WRITABLE_SCHEMA', 'LEGACY_ALTER_TABLE',
    'DQS_DML', 'DQS_DDL', 'ENABLE_VIEW', 'LEGACY_FILE_FORMAT', 'TRUSTED_SCHEMA')}
DANGEROUS = frozenset({'reset_database', 'writable_schema', 'enable_load_extension'})


def action(connection, module, request, *, native_work_revision=None):
    if not isinstance(request, dict):
        raise RelationalClientError('Select a named native configuration')
    if request.get('operation')=='capabilities':
        return capabilities(connection,module,request)
    from .extended_config import NAMES,action as extended_action
    if isinstance(request.get('config'),str) and request['config'] in NAMES:
        return extended_action(connection,request,native_work_revision=native_work_revision)
    operation, name = request.get('operation'), request.get('config')
    fields = {'inspect': {'operation', 'config'},
              'review': {'operation', 'config', 'value'},
              'set_connection_config': {'operation', 'config', 'value', 'expected_value', 'confirmed', 'dangerous_change_confirmed'}}
    if (not isinstance(operation, str) or operation not in fields or
            set(request) - fields[operation] or not isinstance(name, str) or name not in CONFIGS):
        raise RelationalClientError('Select an admitted native boolean configuration')
    if operation != 'inspect' and type(request.get('value')) is not bool:
        raise RelationalClientError('Select an explicit boolean configuration value')
    if operation == 'set_connection_config':
        if request.get('confirmed') is not True or type(request.get('expected_value')) is not bool:
            raise RelationalClientError('Refresh and confirm the native configuration')
        if name in DANGEROUS and request['value'] and request.get('dangerous_change_confirmed') is not True:
            raise RelationalClientError('Confirm the native destructive or extension-loading policy')
    code = getattr(module, CONFIGS[name], None)
    if type(code) is not int or not all(callable(getattr(connection, n, None)) for n in ('getconfig', 'setconfig')):
        raise RelationalClientError('Native configuration is unavailable in this interpreter/build')
    try:
        before = connection.getconfig(code)
        if type(before) is not bool:
            raise ValueError('Unrecognized native result')
    except Exception as error:
        failure = RelationalClientError('Native configuration unavailable; setter not dispatched')
        failure.native_outcome = 'not_dispatched'
        raise failure from error
    if operation == 'set_connection_config':
        if before is not request['expected_value']:
            raise RelationalClientError('Original native configuration changed; review again')
        try:
            connection.setconfig(code, request['value'])
            after = connection.getconfig(code)
            if after is not request['value']:
                raise ValueError('Unconfirmed native postcondition')
        except Exception as error:
            failure = RelationalClientError('Native configuration outcome unconfirmed; inspect before retrying')
            failure.native_outcome = 'unknown_outcome'
            raise failure from error
    else:
        after = before
    result = dict(config=name, native_constant=CONFIGS[name], before_value=before,
                  effective_value=after, scope='original-connection',
                  transaction_open=connection.in_transaction, file_persisted=False,
                  future_connection_defaults_changed=False, commit_requested=False,
                  rollback_requested=False, automatic_retry=False)
    if operation != 'inspect':
        result.update(requested_value=request['value'], expected_value=before)
    if operation == 'review':
        result.update(ready_to_apply=True, native_call=CONFIGS[name],
            warning='Connection policy is not restored by rollback. '+{
                'reset_database':'RESET_DATABASE arms subsequent VACUUM to erase the database.',
                'writable_schema':'WRITABLE_SCHEMA bypasses normal catalog protection.',
                'enable_load_extension':'ENABLE_LOAD_EXTENSION changes native loading authority; this operation loads no extension.'
            }.get(name,'The named native policy changes only this connection; no SQL is executed.'))
    if operation == 'set_connection_config':
        result['outcome'] = 'applied'
    return result


def capabilities(connection,module,request):
    """Observe named flags without preparing SQL or occupying lookaside slots."""
    if set(request)!={'operation'}:raise RelationalClientError('Configuration capabilities take no setter values')
    from .extended_config import BOOLEANS,INTEGERS
    bridge=getattr(connection,'_cdeadmin_config_api',None)
    bridge=bridge if bridge is not None and not bridge.closed else None
    rows=[]
    for name,constant in CONFIGS.items():
        try:
            code=getattr(module,constant)
            value=connection.getconfig(code)
            if type(value)is not bool:raise ValueError('Unknown native boolean result')
            rows.append({'config':name,'signature':'boolean','available_observed':True,'current_value':value})
        except Exception as error:
            rows.append({'config':name,'signature':'boolean','available_observed':False,'unavailable_reason':type(error).__name__})
    for name in (*BOOLEANS,*INTEGERS):
        try:
            if bridge is None:raise ValueError('Native helper not bound')
            code,value=bridge.module.boolean(bridge.capsule,name,-1) if name in BOOLEANS else bridge.module.integer(bridge.capsule,0)
            rows.append({'config':name,'signature':'boolean' if name in BOOLEANS else 'integer',
                'available_observed':code==0,'native_result_code':code,
                'current_value':(bool(value) if name in BOOLEANS else value) if code==0 else None})
        except Exception as error:
            rows.append({'config':name,'signature':'boolean' if name in BOOLEANS else 'integer','available_observed':False,'unavailable_reason':type(error).__name__})
    for name,signature in [('main_dbname','retained-utf8-name'),('lookaside','native-owned-slots')]:
        rows.append({'config':name,'signature':signature,'signature_admitted':bridge is not None,
            'setter_availability_observed':False,'current_configuration_observed':False})
    return {'configurations':rows,'scope':'original-connection','original_sql_commands_sent':0,
        'setter_dispatched':False,'native_helper':dict(bridge.program)if bridge is not None else None,
        'allocation_geometry_observed':False,'automatic_retry':False}
