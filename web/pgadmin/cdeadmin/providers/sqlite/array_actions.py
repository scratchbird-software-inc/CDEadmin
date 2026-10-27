"""Typed native arrays scoped to one admitted retained SQLite connection."""
from itertools import islice
import os

from .array_api import ArrayAPI,installed_library
from .array_values import encode,TYPES
from .session_api import SessionAPIError,identity


def action(client,connection,request,library=None,max_bytes=None):
    if not isinstance(request,dict):raise SessionAPIError('Select a native array request')
    operation=request.get('operation');api=connection._cdeadmin_array_api
    selected=library or os.environ.get('CDEADMIN_SQLITE_ARRAY_LIBRARY') or installed_library()
    fields={'inventory':{'offset','limit'},'create':{'type','values'},'status':{'array_id'},'close':{'array_id','confirmed'}}
    if operation not in fields or set(request)-({'operation'}|fields[operation]):raise SessionAPIError('Native array operation or arguments are unavailable')
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes<=0):raise SessionAPIError('Native array memory policy is invalid')
    if operation=='inventory':
        offset=request.get('offset',0);limit=request.get('limit',25)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise SessionAPIError('Select a native array page of at most100 entries')
        reason=None;program=None
        try:_path,program=identity(selected,'array')
        except (SessionAPIError,OSError,ValueError) as error:reason=str(error)
        total=0 if api is None else len(api.arrays)
        return {'arrays':[] if api is None else [describe(api,key) for key in islice(api.arrays,offset,offset+limit)],
            'offset':offset,'limit':limit,'total':total,'more':offset+limit<total,'types':list(TYPES),
            'helper_available':api is not None or reason is None,'installed_helper_available':reason is None,
            'unavailable_reason':reason if api is None else None,'native_context_initialized':api is not None,
            'program':program if api is None else api.program,'max_native_data_bytes':None if max_bytes is None else str(max_bytes),
            'scope':'this retained SQLite connection; array values are lost when it closes',
            'transaction_open':connection.in_transaction}
    if operation=='create':
        encoded=encode(request.get('type'),request.get('values'))
        allocated=0 if api is None else sum(int(api.status(key)['native_data_bytes']) for key in api.arrays)
        if max_bytes is not None and allocated+encoded['native_data_bytes']>max_bytes:raise SessionAPIError('Native arrays exceed this connection memory policy; close arrays or ask the operator to adjust it')
        if api is None:api=ArrayAPI(connection,selected,owner_shutdown=client.close)
        item=api.create(encoded['native_type'],encoded['element_count'],encoded['payload'])
        return {'array':describe(api,item['array_id']),'program':api.program,'transaction_open':connection.in_transaction,'database_mutation':False}
    key=request.get('array_id')
    if api is None or key not in api.arrays:raise SessionAPIError('Native array belongs to another or closed query connection')
    if operation=='close':
        if request.get('confirmed') is not True:raise SessionAPIError('Confirm releasing this native array and its parameter bindings')
        api.close(key)
        return {'array_id':key,'closed':True,'database_mutation':False,'transaction_open':connection.in_transaction}
    return {'array':describe(api,key),'program':api.program,'transaction_open':connection.in_transaction}


def describe(api,key):
    item=api.status(key)
    return {**item,'type_name':next(name for name,value in TYPES.items() if value==item['native_type']),
        'binding':{'encoding':'carray','data':key}}
