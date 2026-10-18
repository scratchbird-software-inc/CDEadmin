"""Retained-connection native before-change diagnostics, never commit evidence."""
import base64
import os

from .preupdate_api import PreupdateAPI,installed_library
from .session_api import SessionAPIError,identity

SCOPE='Before-change callbacks, including changes later rolled back; these observations do not establish a committed change. Native rowid fields are undefined for WITHOUT ROWID tables, old rowid on INSERT, and new rowid on DELETE. Schema and virtual/system-table changes do not invoke this hook.'


def decimal(value,name,maximum=2147483647):
    if not isinstance(value,str) or not value.isascii() or not value.isdecimal() or str(int(value))!=value or not 0<int(value)<=maximum:
        raise SessionAPIError('Select exact positive decimal '+name)
    return int(value)


def decode(item):
    for key in ('database','table'):
        raw=bytes.fromhex(item[key+'_hex'])
        try:item[key]=raw.decode('utf8')
        except UnicodeDecodeError:item[key]={'encoding':'base64','data':base64.b64encode(raw).decode('ascii'),'native_storage_class':'text'}
    for side in ('old_values','new_values'):
        if item[side] is None:continue
        for cell in item[side]:
            if 'hex' not in cell:continue
            raw=bytes.fromhex(cell.pop('hex'))
            if cell['native_type']=='text':
                try:cell['data']=raw.decode('utf8');continue
                except UnicodeDecodeError:pass
            cell['data']={'encoding':'base64','data':base64.b64encode(raw).decode('ascii'),'byte_length':len(raw)}
            if cell['native_type']=='text':cell['data']['native_storage_class']='text'
    return item


def action(client,connection,request,library=None):
    if not isinstance(request,dict):raise SessionAPIError('Select a native preupdate request')
    operation=request.get('operation');fields={'inventory':set(),'start':{'max_events','max_json_bytes'},
        'status':set(),'events':{'run_id','after_sequence','limit'},'stop':{'run_id'},'clear':{'run_id','confirmed'}}
    if operation not in fields or set(request)-({'operation'}|fields[operation]):raise SessionAPIError('Native preupdate operation or arguments are unavailable')
    api=connection._cdeadmin_preupdate_api
    selected=library or os.environ.get('CDEADMIN_SQLITE_PREUPDATE_LIBRARY') or installed_library()
    if operation=='inventory':
        program=None;reason=None
        try:_path,program=identity(selected,'preupdate')
        except (SessionAPIError,OSError,ValueError) as error:reason=str(error)
        sessions=connection._cdeadmin_session_api
        return {'helper_available':api is not None or reason is None,'installed_helper_available':reason is None,
            'unavailable_reason':reason if api is None else None,'program':program if api is None else api.program,
            'status':None if api is None else api.status(),'native_context_initialized':api is not None,
            'active_native_captures':0 if sessions is None else len(sessions.captures),'scope':SCOPE,
            'transaction_open':connection.in_transaction}
    if operation=='start':
        events=request.get('max_events',1000)
        if type(events) is not int or not 1<=events<=2147483647:raise SessionAPIError('Select a positive native event limit')
        memory=decimal(request.get('max_json_bytes','16777216'),'native JSON byte limit')
        if api is None:api=PreupdateAPI(connection,selected,owner_shutdown=client.close)
        api.start(events,memory)
    elif api is None:raise SessionAPIError('The retained connection has no native preupdate controller')
    elif operation in {'events','stop','clear'}:
        if not api.run_id or request.get('run_id')!=api.run_id:raise SessionAPIError('Native preupdate observation identity changed; refresh this connection')
        if operation=='events':
            after=request.get('after_sequence','0');limit=request.get('limit',25)
            if not isinstance(after,str) or not after.isascii() or not after.isdecimal() or str(int(after))!=after or int(after)>9223372036854775807 or type(limit) is not int or not 1<=limit<=100:
                raise SessionAPIError('Select an exact native sequence and a page of at most100 observations')
            page=api.call('events',int(after),limit)
            return {**page,'events':[decode(item) for item in page['events']],'status':api.status(),'scope':SCOPE,'transaction_open':connection.in_transaction}
        if operation=='stop':api.stop()
        else:
            if request.get('confirmed') is not True:raise SessionAPIError('Confirm discarding these native preupdate observations')
            api.clear()
    return {'status':api.status(),'program':api.program,'scope':SCOPE,'transaction_open':connection.in_transaction,'database_mutation':False}
