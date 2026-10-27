"""Native MySQL row triggers, ordering and independently owned DDL review."""
from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json

from ...sdk import RelationalClientError
from ..mysql_views import _account_part
from .mysql_indexes import identifier, path, context, structural_definition
from .mysql_routines import text, check_grammar

KEYS = {'name','parent','database','table','timing','event','events','body','definition',
        'definer_user','definer_host','if_not_exists','order','other_trigger','active','position'}


def compile_create(draft, mode=None):
    if not isinstance(draft, Mapping):
        raise RelationalClientError('Select structured native trigger properties')
    draft=deepcopy(dict(draft));options=draft.pop('options',{})
    if not isinstance(options, Mapping) or set(options)&set(draft):
        raise RelationalClientError('Ambiguous native trigger options')
    draft.update(options)
    for alias,canonical in (('parent','database'),('definition','body')):
        if alias in draft:
            if canonical in draft:raise RelationalClientError('Ambiguous native trigger field')
            draft[canonical]=draft.pop(alias)
    if set(draft)-KEYS:raise RelationalClientError('Unknown native trigger option')
    database=draft.get('database')
    if isinstance(database,list) and len(database)==1:database=database[0]
    table=path(draft.get('table'))
    if len(table)==2:
        if database is not None and database!=table[0]:raise RelationalClientError('Trigger and table must belong to the same native database')
        database=table[0]
    else:table=[database,*table]
    qualified=identifier(database)+'.'+identifier(draft.get('name'))
    if 'events' in draft:
        if 'event' in draft or not isinstance(draft['events'],list) or len(draft['events'])!=1:
            raise RelationalClientError('MySQL row triggers have one native event')
        draft['event']=draft.pop('events')[0]
    event=draft.get('event','INSERT');timing=draft.get('timing','BEFORE');order=draft.get('order','NONE')
    if event not in {'INSERT','UPDATE','DELETE'} or timing not in {'BEFORE','AFTER'} or order not in {'NONE','FOLLOWS','PRECEDES'}:
        raise RelationalClientError('Select native trigger timing, event and order')
    # Frozen generic clients used to send these no-op defaults. Retain their
    # default requests, but never claim native disablement or numeric ordering.
    if draft.get('active',True) is not True or type(draft.get('position',0)) is not int or draft.get('position',0)!=0:
        raise RelationalClientError('MySQL has no trigger active flag or numeric position; select FOLLOWS/PRECEDES')
    exists=draft.get('if_not_exists',False)
    if type(exists) is not bool:raise RelationalClientError('IF NOT EXISTS must be boolean')
    source='CREATE '
    if 'definer_user' in draft or 'definer_host' in draft:
        source+='DEFINER='+_account_part(draft.get('definer_user'),32)+'@'+_account_part(draft.get('definer_host'),255)+' '
    source+='TRIGGER '+('IF NOT EXISTS ' if exists else '')+qualified+' '+timing+' '+event+' ON '+'.'.join(identifier(part) for part in table)+' FOR EACH ROW'
    if order!='NONE':source+=' '+order+' '+identifier(draft.get('other_trigger'))
    elif draft.get('other_trigger'):raise RelationalClientError('Select FOLLOWS or PRECEDES for the ordering anchor')
    body=text(draft.get('body'),'Trigger body',1024*1024).strip()
    if not body:raise RelationalClientError('Trigger body is required')
    source+='\n'+body
    return {'statements':[{'source':source,'parameters':(),'parser_source':source}],
        'mysql_trigger_create':{'draft':draft,'path':[database,draft['name']],'table':table},
        'warnings':['Native trigger DDL uses its own connection. Trigger execution and privileges remain native. Review does not fence concurrent external DDL; an unknown mutation is never automatically replayed.']}


def observe(cursor,intent,mode):
    cursor.execute('SHOW CREATE TABLE '+'.'.join(identifier(part) for part in intent['table']))
    row=cursor.fetchone()
    if not row or len(row)<2 or not isinstance(row[1],str):raise RelationalClientError('Native owning-table definition is unavailable')
    structure=structural_definition(row[1],mode)
    cursor.execute('SELECT TRIGGER_NAME,ACTION_TIMING,EVENT_MANIPULATION,ACTION_ORDER,ACTION_STATEMENT,DEFINER,CAST(SQL_MODE AS CHAR),CHARACTER_SET_CLIENT,COLLATION_CONNECTION,DATABASE_COLLATION '
        'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND EVENT_OBJECT_SCHEMA=%s AND EVENT_OBJECT_TABLE=%s ORDER BY ACTION_TIMING,EVENT_MANIPULATION,ACTION_ORDER,TRIGGER_NAME',
        (intent['path'][0],*intent['table']))
    rows=[list(row) for row in cursor.fetchall()]
    return {'table_structure_sha256':structure,
        'trigger_definition_sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf8')).hexdigest(),
        'ordered_triggers':[{'name':row[0],'timing':row[1],'event':row[2],'order':row[3]} for row in rows]}


def bind_review(client,planned):
    compiled=planned['provider_payload']['compiled'];intent=compiled['mysql_trigger_create']
    handle=client._connect({'route':planned['provider_payload']['route']});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=context(cursor)
        checked=compile_create(intent['draft'],identity['sql_mode'])
        if checked!=compiled:raise RelationalClientError('Trigger changed during native review')
        grammar=check_grammar(client,checked,identity['sql_mode'])
        before=observe(cursor,intent,identity['sql_mode']);intent['review']={'identity':identity,'before':before,'grammar':grammar}
        planned['command_preview'].update(native_execution_identity=identity,native_trigger_observation=before,native_grammar=grammar)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('Trigger creation requires an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_trigger_create'];review=intent.get('review')
    if not isinstance(review,Mapping):raise RelationalClientError('Review the native trigger before dispatch')
    candidate=deepcopy(compiled);candidate['mysql_trigger_create'].pop('review',None)
    if compile_create(intent['draft'],review['identity']['sql_mode'])!=candidate:raise RelationalClientError('Reviewed trigger changed')
    if check_grammar(client,candidate,review['identity']['sql_mode'])!=review['grammar']:raise RelationalClientError('Native grammar dependency changed')
    handle=client._connect({'route':payload['route']});cursor=None;dispatched=acknowledged=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False
        cursor=handle.cursor();identity=context(cursor)
        if identity!=review['identity'] or observe(cursor,intent,identity['sql_mode'])!=review['before']:
            raise RelationalClientError('Native table, trigger order or execution identity changed since review')
        statement=compiled['statements'][0];dispatched=True
        cursor.execute(statement['source']);acknowledged=True
        warnings=[{'level':level,'code':code,'message':message} for level,code,message in (cursor.warnings or ())]
        after=observe(cursor,intent,identity['sql_mode'])
        return {'accepted':True,'native_implicit_commit':True,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            'trigger_observation':{'native_acknowledged':True,'before':review['before'],'after':after,'concurrent_external_ddl_fenced':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native trigger creation failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
