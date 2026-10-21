"""Exact named MyISAM cache variables, native rounding and release semantics."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from .mysql_catalog import identifier
from .mysql_instance import environment,target_uuid

VARIABLES=('key_buffer_size','key_cache_block_size','key_cache_division_limit','key_cache_age_threshold')
OPERATIONS={'inspect_key_cache':'Inspect named MyISAM key cache','configure_key_cache':'Configure MyISAM key cache','release_key_cache':'Release named MyISAM key cache'}


def source(name):return 'SELECT '+','.join('@@GLOBAL.'+identifier(name)+'.'+identifier(field) for field in VARIABLES)


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,Mapping):raise RelationalClientError('Select a native MySQL key-cache workflow')
    uuid=target_uuid(target);allowed={'cache_name','confirmation'}
    if operation=='configure_key_cache':allowed|={'variable','value_mode','value'}
    if set(draft)-allowed or operation!='inspect_key_cache' and draft.get('confirmation')!=target['display_name']:
        raise RelationalClientError('Confirm the exact native server and key-cache options')
    name=draft.get('cache_name')
    if not isinstance(name,str) or not name or len(name)>64 or '\0' in name:raise RelationalClientError('Specify an exact native key-cache name of 1 to 64 characters')
    params=()
    if operation=='inspect_key_cache':statement=source(name)
    else:
        field='key_buffer_size' if operation=='release_key_cache' else draft.get('variable','key_buffer_size')
        if field not in VARIABLES:raise RelationalClientError('Select a native key-cache variable')
        statement='SET GLOBAL '+identifier(name)+'.'+identifier(field)+' = '
        mode='VALUE' if operation=='release_key_cache' else draft.get('value_mode','VALUE')
        if mode=='DEFAULT':statement+='DEFAULT'
        elif mode=='VALUE':
            value='0' if operation=='release_key_cache' else draft.get('value')
            if not isinstance(value,str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})',value) or int(value)>2**64-1:
                raise RelationalClientError('Use exact unsigned 64-bit decimal text for a native cache value')
            statement+='%s';params=(int(value),)
        else:raise RelationalClientError('Select a bound value or native DEFAULT')
    return {'statements':[{'source':statement,'parameters':params}],
        'mysql_key_cache_lifecycle':{'operation':operation,'cache_name':name,'server_uuid':uuid,'draft':dict(draft),'target':deepcopy(dict(target))},
        'warnings':['Native cache values are runtime server settings. The native server owns allocation, bounds, rounding and warnings; values are not persisted to server configuration.',
            'Inspection is limited to the selected prefix. Native MySQL does not enumerate named caches through SHOW GLOBAL VARIABLES; all-zero observations do not prove a cache exists.',
            'Release sets the selected buffer to zero. MySQL moves its assigned tables to the default cache and retains the named prefix; native error1438 protects the default cache.']}


def form(operation,field):
    fields=[field('cache_name','Exact native key-cache name','text',True,default='default')]
    if operation=='configure_key_cache':fields += [field('variable','Native key-cache variable','select',default='key_buffer_size',options=VARIABLES),
        field('value_mode','Value source','select',default='VALUE',options=('VALUE','DEFAULT')),
        {**field('value','Exact unsigned native value','text',True,default='4194304'), 'visible_when':{'field_id':'value_mode','equals':'VALUE'}}]
    if operation!='inspect_key_cache':fields.append(field('confirmation','Exact server name','text',True))
    return {'form_id':'mysql.server.'+operation,'title':OPERATIONS[operation],'fields':fields}


def observe(cursor,name):
    cursor.execute(source(name));row=cursor.fetchone()
    if not row or len(row)!=4 or any(type(value) is not int or not 0<=value<=2**64-1 for value in row):
        raise RelationalClientError('Exact native key-cache values are unavailable')
    return {'cache_name':name,'native_values':dict(zip(VARIABLES,map(str,row))),
        'scope':'selected-native-prefix','native_cache_existence_asserted':False}


def bind_review(client,planned):
    payload=planned['provider_payload'];intent=payload['compiled']['mysql_key_cache_lifecycle']
    handle=client._connect({'route':payload['route']});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=environment(cursor)
        if identity['server_uuid']!=intent['server_uuid']:raise RelationalClientError('Native MySQL instance differs from the selected cache server')
        before=observe(cursor,intent['cache_name'])
        intent['review']={'execution_identity':identity,'before':before}
        planned['command_preview'].update(native_execution_identity=identity,native_key_cache=before)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('Key-cache management requires an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_key_cache_lifecycle']
    checked=deepcopy(compiled);review=checked['mysql_key_cache_lifecycle'].pop('review',None)
    if not isinstance(review,Mapping) or compile_operation(intent['operation'],intent['draft'],intent['target'])!=checked:
        raise RelationalClientError('Review the exact native key-cache workflow before dispatch')
    handle=client._connect({'route':payload['route']});cursor=None;dispatched=acknowledged=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False
        cursor=handle.cursor();identity=environment(cursor)
        if identity!=review['execution_identity']:raise RelationalClientError('Native key-cache execution identity changed since review')
        if intent['operation']=='inspect_key_cache':
            # A changed cache is precisely what a fresh inspection must report.
            before=review['before'];dispatched=True
            after=observe(cursor,intent['cache_name']);acknowledged=True;warnings=[]
        else:
            before=observe(cursor,intent['cache_name'])
            if before!=review['before']:raise RelationalClientError('Native key-cache values changed since review')
            statement=compiled['statements'][0];dispatched=True
            cursor.execute(statement['source'],statement['parameters']);acknowledged=True
            warnings=[{'level':level,'code':code,'message':text} for level,code,text in (cursor.warnings or ())]
            after=observe(cursor,intent['cache_name'])
        return {'accepted':True,'native_implicit_commit':False,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            'key_cache_observation':{'native_acknowledged':acknowledged,'execution_identity':identity,'operation':intent['operation'],
                'before':before,'after':after,'server_configuration_persisted':False,
                'native_prefix_deleted':False,'cache_contents_observed':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native MySQL key-cache workflow failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        failure.native_status_codes=(failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
