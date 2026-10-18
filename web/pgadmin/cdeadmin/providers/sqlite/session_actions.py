"""Native capture controls scoped to an admitted retained SQLite connection."""
from itertools import islice
import os

from .session_api import SessionAPI,SessionAPIError,identity,installed_library


def action(client,connection,request,library=None):
    if not isinstance(request,dict) or not isinstance(request.get('operation'),str):
        raise SessionAPIError('Select a native SQLite capture operation')
    operation=request['operation'];api=connection._cdeadmin_session_api
    selected_library=library or os.environ.get('CDEADMIN_SQLITE_SESSION_LIBRARY') or installed_library()
    if operation=='inventory':
        if set(request)-{'operation','offset','limit'}:raise SessionAPIError('Select one native capture inventory page')
        offset=request.get('offset',0);limit=request.get('limit',25)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise SessionAPIError('Select a native capture page of at most100 entries')
        reason=None;program=None
        try:_path,program=identity(selected_library)
        except (SessionAPIError,OSError,ValueError) as error:reason=str(error)
        captures=[] if api is None else [api.status(key) for key in islice(api.captures,offset,offset+limit)]
        total=0 if api is None else len(api.captures)
        return {'captures':captures,'offset':offset,'limit':limit,'total':total,'more':offset+limit<total,
            'helper_available':api is not None or reason is None,'installed_helper_available':reason is None,
            'unavailable_reason':reason if api is None else None,'installed_helper_reason':reason,'program':program if api is None else api.program,
            'native_context_initialized':api is not None,
            'scope':'this retained SQLite connection; capture memory is lost when it closes',
            'databases':[{'name':row[1],'filename':row[2]} for row in connection.execute('PRAGMA database_list')],
            'transaction_open':connection.in_transaction,'preupdate_hook_scope':'Native sessions and an independent preupdate hook cannot share this connection'}
    fields={
        'open':{'database','estimate_size','track_rowids'},'attach':{'capture_id','table_name'},
        'status':{'capture_id'},'configure':{'capture_id','enabled','indirect'},
        'object_config':{'capture_id','option','value'},'diff':{'capture_id','source_database','table_name'},
        'close':{'capture_id','confirmed'}}
    allowed=fields.get(operation)
    if allowed is None or set(request)-({'operation'}|allowed):raise SessionAPIError('Native capture operation or arguments are unavailable')
    if operation=='open':
        database=request.get('database');size=request.get('estimate_size',False);rowids=request.get('track_rowids',False)
        if not isinstance(database,str) or not database or '\x00' in database or type(size) is not bool or type(rowids) is not bool:
            raise SessionAPIError('Select an exact native database name and capture switches')
        if api is None:api=SessionAPI(connection,selected_library,owner_shutdown=client.close)
        capture=api.open(database,estimate_size=size,track_rowids=rowids)
        return {'capture':api.status(capture),'program':api.program,'transaction_open':connection.in_transaction}
    capture=request.get('capture_id')
    if api is None or capture not in api.captures:raise SessionAPIError('Native capture belongs to another or closed connection')
    if operation=='attach':
        if 'table_name' not in request:raise SessionAPIError('Select an exact native table name or all tables')
        api.attach(capture,request['table_name'])
    elif operation=='configure':
        if set(request)=={'operation','capture_id'}:raise SessionAPIError('Select a native enabled or indirect switch')
        for key in ('enabled','indirect'):
            if key in request:
                if type(request[key]) is not bool:raise SessionAPIError('Native capture switches must be boolean')
        for key in ('enabled','indirect'):
            if key in request:
                api.call('enable' if key=='enabled' else 'indirect',capture,int(request[key]))
    elif operation=='object_config':
        option=request.get('option');value=request.get('value')
        if option not in {'estimate_size','track_rowids'} or type(value) is not bool:
            raise SessionAPIError('Select a native size/rowid object configuration switch')
        api.call('object_config',capture,1 if option=='estimate_size' else 2,int(value))
    elif operation=='diff':
        database,table=request.get('source_database'),request.get('table_name')
        if any(not isinstance(value,str) or not value or '\x00' in value for value in (database,table)):
            raise SessionAPIError('Select an attached native source database and exact table name')
        api.call('diff',capture,database,table)
    elif operation=='close':
        if request.get('confirmed') is not True:raise SessionAPIError('Confirm discarding this capture and any unexported changes')
        api.close(capture)
        return {'capture_id':capture,'closed':True,'database_mutation':False,'transaction_open':connection.in_transaction}
    return {'capture':api.status(capture),'program':api.program,'database_mutation':False,'transaction_open':connection.in_transaction}
