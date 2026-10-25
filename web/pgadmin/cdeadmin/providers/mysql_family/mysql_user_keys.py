"""Native, principal-owned Community keyring UDF operations.

User interface fields and labels are owned solely by the MySQL descriptors.
Key bytes are used privately for stale-review detection and never in receipts.
"""
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from ...sdk import RelationalClientError
from .mysql_instance import target_uuid, environment

OPERATIONS=frozenset({'install_user_key_functions','inspect_user_key','store_user_key','generate_user_key','remove_user_key'})
FUNCTIONS={'keyring_key_store':2,'keyring_key_fetch':0,'keyring_key_type_fetch':0,
    'keyring_key_length_fetch':2,'keyring_key_remove':2,'keyring_key_generate':2}


@lru_cache(maxsize=1)
def catalog_entries():
    root=Path(__file__).resolve().parents[2]/'ui_descriptors/mysql'
    document=json.loads((root/'operations.json').read_text())
    capabilities=json.loads((root/'capabilities.json').read_text())
    declared={row['operation_id']:row for kind in capabilities['kinds'] if kind['resource_kind']=='server' for row in kind['operations']}
    entries=[]
    for op in document['operations']:
        name=op['operation_id']
        if name not in OPERATIONS:continue
        entries.append({'operation_id':name,'title':op['title'],'mutation_class':declared[name]['mutation_class'],
            'target_required':True,'confirmation_required':op['confirmation']!='none',
            'form':{'form_id':'mysql.server.'+name,'title':op['title'],'fields':deepcopy(op['fields'])}})
    if {row['operation_id'] for row in entries}!=OPERATIONS:raise RelationalClientError('The user-key operation descriptors are incomplete')
    return entries


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,Mapping):raise RelationalClientError('Select a structured user-key operation')
    identity=target_uuid(target)
    allowed={'confirmation'}|({'library','trusted_library'} if operation=='install_user_key_functions' else {'key_id'})
    if operation in {'store_user_key','generate_user_key'}:allowed|={'key_type','password'} if operation=='store_user_key' else {'key_type','key_length'}
    if set(draft)-allowed or draft.get('confirmation')!=target['display_name']:
        raise RelationalClientError('Confirm the selected server and user-key fields')
    if operation=='install_user_key_functions':
        library=draft.get('library')
        if not isinstance(library,str) or not re.fullmatch(r'keyring_udf\.(?:so|dll|dylib)',library) or draft.get('trusted_library') is not True:
            raise RelationalClientError('Select and trust the native keyring_udf library installed on the database host')
        statements=[{'source':'INSTALL PLUGIN keyring_udf SONAME %s','parameters':(library,)}]
        statements += [{'source':'CREATE FUNCTION '+name+' RETURNS '+('INTEGER' if result==2 else 'STRING')+' SONAME %s','parameters':(library,)} for name,result in FUNCTIONS.items()]
    else:
        key=draft.get('key_id')
        if not isinstance(key,str) or not key or '\0' in key or len(key.encode('utf8'))>16384:raise RelationalClientError('Select a bounded nonempty key identifier without NUL')
        key_type=draft.get('key_type','AES')
        if operation in {'store_user_key','generate_user_key'} and key_type not in {'AES','RSA','DSA','SECRET'}:raise RelationalClientError('Select an available native key type')
        if operation=='store_user_key':
            value=draft.get('password')
            if not isinstance(value,str) or not value or '\0' in value or len(value.encode('utf8'))>16384:raise RelationalClientError('Key text requires 1–16384 UTF-8 bytes without NUL; the native store UDF uses NUL-terminated text')
            source='SELECT keyring_key_store(%s,%s,%s)';parameters=(key,key_type,value)
        elif operation=='generate_user_key':
            length=draft.get('key_length')
            if isinstance(length,str) and re.fullmatch(r'[0-9]{1,5}',length):length=int(length)
            if type(length) is not int or not 1<=length<=16384:raise RelationalClientError('Select a native key length from 1 through 16384 bytes')
            source='SELECT keyring_key_generate(%s,%s,%s)';parameters=(key,key_type,length)
        elif operation=='remove_user_key':source='SELECT keyring_key_remove(%s)';parameters=(key,)
        else:source='SELECT keyring_key_type_fetch(%s),keyring_key_length_fetch(%s)';parameters=(key,key)
        statements=[{'source':source,'parameters':parameters}]
    return {'statements':statements,'mysql_user_keys':{'operation':operation,'draft':deepcopy(dict(draft)),
        'target':deepcopy(dict(target)),'server_uuid':identity},'warnings':[
        'Native keys belong to CURRENT_USER(), including its host part. They are independent of a query-session transaction and cannot be undone by its rollback.',
        'Native keyring and UDF dependencies, permissions, return values and errors remain authoritative. No automatic retry is performed.']}


def observe(cursor,intent):
    if intent['operation']=='install_user_key_functions':
        cursor.execute("SELECT PLUGIN_STATUS,PLUGIN_LIBRARY FROM information_schema.PLUGINS WHERE PLUGIN_NAME='keyring_udf'")
        plugin=cursor.fetchall()
        cursor.execute('SELECT name,ret,dl,type FROM mysql.func WHERE name IN ('+','.join(['%s']*len(FUNCTIONS))+') ORDER BY name',tuple(FUNCTIONS))
        return {'plugin':[list(row) for row in plugin],'functions':[list(row) for row in cursor.fetchall()]}
    key=intent['draft']['key_id']
    cursor.execute('SELECT keyring_key_type_fetch(%s),keyring_key_length_fetch(%s),SHA2(keyring_key_fetch(%s),256)',(key,key,key))
    row=cursor.fetchone();return {'key_type':row[0],'key_length':row[1],'private_fingerprint':row[2]}


def public(observation):return {key:value for key,value in observation.items() if key!='private_fingerprint'}


def effective(compiled,before):
    if compiled['mysql_user_keys']['operation']!='install_user_key_functions':return compiled['statements']
    library=compiled['mysql_user_keys']['draft']['library']
    if before['plugin'] and before['plugin']!=[['ACTIVE',library]]:raise RelationalClientError('The existing keyring UDF plugin differs from the selected active library')
    functions={row[0]:row[1:] for row in before['functions']}
    for name,(result,existing,kind) in functions.items():
        if result!=FUNCTIONS[name] or existing!=library or str(kind).lower()!='function':
            raise RelationalClientError('An existing key function has another native implementation; it will not be replaced')
    return [statement for index,statement in enumerate(compiled['statements']) if
        (not before['plugin'] if index==0 else list(FUNCTIONS)[index-1] not in functions)]


def bind_review(client,planned):
    compiled=planned['provider_payload']['compiled'];intent=compiled['mysql_user_keys']
    handle=client._connect({'route':planned['provider_payload']['route']});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=environment(cursor)
        if identity['server_uuid']!=intent['server_uuid']:raise RelationalClientError('The selected user-key server identity changed')
        before=observe(cursor,intent);compiled['statements']=effective(compiled,before)
        intent['review']={'identity':identity,'before':before}
        planned['command_preview']['statements']=[{'source':s['source'],'parameter_count':len(s['parameters']),'parameters_redacted':bool(s['parameters'])} for s in compiled['statements']]
        planned['command_preview']['keyring_observation']=public(before)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('User-key operations require an independently owned native connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_user_keys'];review=intent.get('review')
    if not isinstance(review,Mapping):raise RelationalClientError('Review the user-key operation before dispatch')
    expected=compile_operation(intent['operation'],intent['draft'],intent['target']);expected['statements']=effective(expected,review['before'])
    checked=deepcopy(compiled);checked['mysql_user_keys'].pop('review',None)
    if checked!=expected:raise RelationalClientError('The reviewed user-key command changed')
    handle=client._connect({'route':payload['route']});cursor=None;dispatched=acknowledged=False;outcomes=[]
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=environment(cursor);before=observe(cursor,intent)
        if identity!=review['identity'] or before!=review['before']:raise RelationalClientError('The native principal, dependency or selected key changed since review')
        effect=True if compiled['statements'] else None
        for statement in compiled['statements']:
            dispatched=True;acknowledged=False;cursor.execute(statement['source'],statement['parameters']);row=cursor.fetchone() if cursor.description else None
            acknowledged=True
            if intent['operation'] not in {'inspect_user_key','install_user_key_functions'}:effect=bool(row and row[0]==1)
            outcomes.append({'source':statement['source'],'native_acknowledged':True,'native_return':None if row is None else list(row)})
        after=observe(cursor,intent)
        return {'accepted':effect is not False,'automatic_retry':False,'native_implicit_commit':bool(compiled['statements']) and intent['operation']=='install_user_key_functions',
            'commit_requested':False,'rollback_requested':False,'staged_in_provider_session':False,
            'keyring_observation':{'operation':intent['operation'],'execution_identity':identity,'before':public(before),'after':public(after),
                'native_acknowledged':acknowledged,'native_key_effect_acknowledged':effect,'key_material_in_receipt':False,
                'already_configured':not compiled['statements'],
                'native_statements':outcomes,'native_effect_rollback_available':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native user-key operation failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None);failure.statement_outcomes=outcomes
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
