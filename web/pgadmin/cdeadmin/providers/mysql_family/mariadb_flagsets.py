"""Explicit original-session MariaDB FLAGSET workflows, never a disposable SET."""
from ...sdk import RelationalClientError
from .mariadb_variables import validate_flagset, flagset_assignments, flagset_bitmask

VARIABLES = ('optimizer_switch', 'optimizer_trace')


def action(handle, request):
    if not isinstance(request,dict):raise RelationalClientError('Select a typed session FLAGSET')
    operation,name=request.get('operation'),request.get('variable')
    common={'operation','variable','diagnostics_change_confirmed'}
    fields={'inspect':common,'review':common|{'value_mode','value','flags','reset_defaults','bitmask'},
            'set_session_flags':common|{'value_mode','value','flags','reset_defaults','bitmask','expected_value','confirmed'}}
    if (not isinstance(operation,str) or operation not in fields or set(request)-fields[operation]
            or not isinstance(name,str) or name not in VARIABLES):
        raise RelationalClientError('Select an admitted session FLAGSET request')
    if request.get('diagnostics_change_confirmed') is not True:
        raise RelationalClientError('Confirm that explicit native inspection changes session diagnostics')
    cursor=handle.cursor()
    try:
        def read():
            cursor.execute('SELECT VARIABLE_SCOPE,VARIABLE_TYPE,READ_ONLY,ENUM_VALUE_LIST,SESSION_VALUE,DEFAULT_VALUE FROM information_schema.SYSTEM_VARIABLES WHERE VARIABLE_NAME=?',(name.upper(),))
            row=cursor.fetchone()
            if (not row or row[0] not in {'SESSION','SESSION ONLY'} or row[1]!='FLAGSET'
                    or row[2]!='NO' or not isinstance(row[3],str) or not isinstance(row[4],str)):
                raise RelationalClientError('Native writable session FLAGSET metadata is unavailable')
            return row
        before=read()
        expression=None;arguments=();warnings=[];warnings_truncated=False
        if operation!='inspect':
            mode=request.get('value_mode')
            try:
                if mode=='FLAGS':
                    value=flagset_assignments(request.get('flags'),request.get('reset_defaults',False),before[3])
                    expression='?';arguments=(value,)
                elif mode=='VALUE':
                    value=request.get('value');validate_flagset(value,before[3]);expression='?';arguments=(value,)
                elif mode=='BITMASK':expression=str(flagset_bitmask(request.get('bitmask'),before[3]))
                elif mode=='DEFAULT':expression='DEFAULT'
                else:raise ValueError('Select a native FLAGSET value mode')
            except (ValueError,TypeError) as error:raise RelationalClientError(str(error)) from None
        if operation=='set_session_flags':
            if request.get('confirmed') is not True or not isinstance(request.get('expected_value'),str):
                raise RelationalClientError('Refresh and confirm the session FLAGSET')
            if before[4]!=request['expected_value']:
                raise RelationalClientError('Original session FLAGSET changed; review again')
            try:
                cursor.execute('SET SESSION `'+name+'` = '+expression,arguments)
                cursor.execute('SHOW WARNINGS LIMIT 101')
                native_warnings=cursor.fetchall()
                warnings_truncated=len(native_warnings)>100
                warnings=[{'level':str(row[0]),'code':int(row[1])} for row in native_warnings[:100]]
                after=read()
                if after[:4]!=before[:4]:raise ValueError('Native variable metadata changed')
                # Native expands partial/default/numeric forms into full text;
                # report that exact observation, never echo the requested form.
                validate_flagset(after[4],after[3])
            except Exception as error:
                failure=RelationalClientError('Native session FLAGSET outcome unconfirmed; inspect before retrying')
                failure.native_outcome='unknown_outcome';raise failure from error
        else:after=before
        result=dict(variable=name,scope='original-session',before_value=before[4],effective_value=after[4],
            native_option_names=before[3].split(','),native_default=before[5],
            commit_requested=False,rollback_requested=False,future_connection_defaults_changed=False,
            global_value_changed=False,automatic_retry=False,native_diagnostics_preserved=False,
            native_warnings=warnings,native_warnings_truncated=warnings_truncated,
            native_warning_messages_included=False)
        if operation!='inspect':
            result.update(expected_value=before[4],native_statement='SET SESSION `'+name+'` = '+expression,
                bound_parameters=list(arguments))
        if operation=='review':result['ready_to_apply']=True
        if operation=='set_session_flags':result['outcome']='native_acknowledged_with_readback'
        return result
    finally:cursor.close()
