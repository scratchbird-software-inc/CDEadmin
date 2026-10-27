"""Typed native MySQL privilege scopes and independently reviewed DCL."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from ..mysql_roles import account
from .mysql_indexes import identifier, context
from .mysql_accounts import check_grammar


def accounts(rows, label):
    if not isinstance(rows, list) or not rows or len(rows) > 4096:
        raise RelationalClientError(label+' requires bounded native account records')
    result=[]
    for row in rows:
        if not isinstance(row, Mapping) or set(row)-{'user','host'}:
            raise RelationalClientError(label+' requires separate user and host values')
        user,host=row.get('user'),row.get('host','%')
        account(user,host);result.append({'user':user,'host':host})
    return result


def compile_operation(operation, draft):
    if operation not in {'grant','revoke'} or not isinstance(draft,Mapping):
        raise RelationalClientError('Select a native privilege grant or revoke')
    draft=deepcopy(dict(draft))
    allowed={'grantees','principal','object_type','object_name','database','object','privileges',
             'grant_option','if_exists','ignore_unknown_user','proxy_user','proxy_host',
             'grant_as_user','grant_as_host','grant_as_roles_mode','grant_as_roles','confirmation'}
    if set(draft)-allowed:raise RelationalClientError('Unknown native privilege option')
    rows=draft.get('grantees')
    if 'principal' in draft:
        principal=draft['principal']
        if rows is not None or not isinstance(principal,str) or principal.count('@')>1:
            raise RelationalClientError('Use separate native grantee user and host values')
        user,host=principal.rsplit('@',1) if '@' in principal else (principal,'%')
        rows=[{'user':user,'host':host}]
    grantees=accounts(rows,'Grantees');identities=list(grantees)
    scope=draft.get('object_type')
    if not isinstance(scope,str) or scope not in {'GLOBAL','DATABASE','TABLE','VIEW','PROCEDURE','FUNCTION','LIBRARY','PROXY','ACCOUNT'}:
        raise RelationalClientError('Select a native privilege scope')
    flags={key:draft.get(key,False) for key in ('grant_option','if_exists','ignore_unknown_user')}
    if any(type(value) is not bool for value in flags.values()):raise RelationalClientError('Privilege options must be boolean')
    if operation=='grant' and (flags['if_exists'] or flags['ignore_unknown_user']):raise RelationalClientError('IF EXISTS and IGNORE UNKNOWN USER apply to REVOKE')
    if operation=='revoke' and flags['grant_option']:raise RelationalClientError('Revoke GRANT OPTION as an explicit privilege')
    prefix=operation.upper()+(' IF EXISTS' if flags['if_exists'] else '')+' '
    names=draft.get('privileges',[])
    if not isinstance(names,list) or len(names)>4096:raise RelationalClientError('Privileges require typed records or legacy names')
    if scope in {'PROXY','ACCOUNT'}:
        if scope == 'ACCOUNT' and {'proxy_user','proxy_host'} & set(draft):raise RelationalClientError('Proxy identity requires PROXY scope')
        if names or {'object_name','database','object'}&set(draft):raise RelationalClientError('This account scope has no object privilege list')
        if scope=='ACCOUNT':
            if operation!='revoke':raise RelationalClientError('All-account privilege removal is a native REVOKE action')
            privilege='ALL PRIVILEGES, GRANT OPTION';on=''
        else:
            proxy=accounts([{'user':draft.get('proxy_user'),'host':draft.get('proxy_host','%')}],'Proxy account')[0]
            identities.append(proxy);privilege='PROXY';on=' ON '+account(proxy['user'],proxy['host'])
    else:
        if {'proxy_user','proxy_host'}&set(draft):raise RelationalClientError('Proxy identity requires PROXY scope')
        if not names:raise RelationalClientError('Select at least one native privilege')
        parts=[]
        for row in names:
            if isinstance(row,str):row={'name':row}
            if not isinstance(row,Mapping) or set(row)-{'name','columns'}:raise RelationalClientError('Unknown privilege record field')
            name=row.get('name');columns=row.get('columns',[])
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?: [A-Za-z][A-Za-z0-9_]*)*',name):
                raise RelationalClientError('Privilege name requires native keyword or dynamic-privilege text')
            if not isinstance(columns,list) or len(columns)>4096 or columns and scope not in {'TABLE','VIEW'}:
                raise RelationalClientError('Column privileges require a table or view and native column names')
            parts.append(name.upper()+(' ('+','.join(identifier(column) for column in columns)+')' if columns else ''))
        privilege=', '.join(parts)
        database,object_name=draft.get('database'),draft.get('object')
        if 'object_name' in draft:
            if database is not None or object_name is not None:raise RelationalClientError('Use native scope fields or legacy object_name, not both')
            legacy=draft['object_name']
            if scope!='GLOBAL':
                if isinstance(legacy,list):path=legacy
                elif isinstance(legacy,str):path=legacy.split('.')
                else:raise RelationalClientError('Select a native privilege object')
                if scope=='DATABASE' and len(path)==1:database=path[0]
                elif scope in {'TABLE','VIEW','PROCEDURE','FUNCTION','LIBRARY'} and len(path)==2:database,object_name=path
                else:raise RelationalClientError('Use separate database/object fields for literal dotted names')
        if scope=='GLOBAL':
            if database is not None or object_name is not None:raise RelationalClientError('GLOBAL scope has no database or object')
            target='*.*'
        elif scope=='DATABASE':
            if object_name is not None:raise RelationalClientError('DATABASE scope has no individual object')
            target=identifier(database)+'.*'
        else:target=identifier(database)+'.'+identifier(object_name)
        on=' ON '+(scope+' ' if scope in {'PROCEDURE','FUNCTION','LIBRARY'} else '')+target
    sql=prefix+privilege+on+(' TO ' if operation=='grant' else ' FROM ')+','.join(account(row['user'],row['host']) for row in grantees)
    if flags['grant_option']:sql+=' WITH GRANT OPTION'
    if 'grant_as_user' in draft:
        if operation!='grant' or scope!='GLOBAL':raise RelationalClientError('Native GRANT AS supports global privileges only')
        grantor=accounts([{'user':draft['grant_as_user'],'host':draft.get('grant_as_host','%')}],'Grantor')[0]
        identities.append(grantor);sql+=' AS '+account(grantor['user'],grantor['host'])
        mode=draft.get('grant_as_roles_mode','NONE')
        if not isinstance(mode,str) or mode not in {'NONE','DEFAULT','ALL','SELECTED','ALL_EXCEPT'}:raise RelationalClientError('Select native GRANT AS role behavior')
        roles=draft.get('grant_as_roles',[])
        if mode in {'SELECTED','ALL_EXCEPT'}:
            roles=accounts(roles,'Grantor roles');identities.extend(roles)
            sql+=' WITH ROLE '+('ALL EXCEPT ' if mode=='ALL_EXCEPT' else '')+','.join(account(row['user'],row['host']) for row in roles)
        else:
            if roles:raise RelationalClientError('Selected grantor roles require SELECTED or ALL_EXCEPT')
            sql+=' WITH ROLE '+mode
    elif {'grant_as_host','grant_as_roles_mode','grant_as_roles'}&set(draft):raise RelationalClientError('Grantor options require a GRANT AS account')
    if flags['ignore_unknown_user']:sql+=' IGNORE UNKNOWN USER'
    return {'statements':[{'source':sql,'parameters':(),'parser_source':sql}],
            'mysql_privilege_change':{'operation':operation,'draft':draft,'identities':identities},
            'warnings':['Native grants may authorize future object names. Privilege validity, partial revokes and plugin/dynamic-privilege availability remain MySQL-owned. External privilege writers are not fenced. No mutation is automatically replayed.']}


def observe(cursor,intent):
    observations=[]
    for row in intent['identities']:
        cursor.execute('SELECT COUNT(*) FROM mysql.user WHERE User=%s AND Host=%s',(row['user'],row['host']))
        present=cursor.fetchone()[0]==1
        grants=[]
        if present:
            cursor.execute('SHOW GRANTS FOR '+account(row['user'],row['host']));grants=sorted(str(value[0]) for value in cursor.fetchall())
        observations.append({**row,'present':present,'grants':grants})
    return observations


def identity(cursor):
    result=context(cursor)
    cursor.execute('SELECT @@GLOBAL.partial_revokes')
    return {**result,'partial_revokes':bool(cursor.fetchone()[0])}


def bind_review(client,planned):
    compiled=planned['provider_payload']['compiled'];intent=compiled['mysql_privilege_change']
    handle=client._connect({'route':{**planned['provider_payload']['route'],'database':None}});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();observed_identity=identity(cursor)
        grammar=check_grammar(client,compiled,observed_identity['sql_mode']);before=observe(cursor,intent)
        intent['review']={'identity':observed_identity,'before':before,'grammar':grammar}
        planned['command_preview'].update(native_execution_identity=observed_identity,native_grants=before,native_grammar=grammar)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('Privilege changes require an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_privilege_change'];review=intent.get('review')
    if not isinstance(review,Mapping):raise RelationalClientError('Review native grants before dispatch')
    checked=deepcopy(compiled);checked['mysql_privilege_change'].pop('review',None)
    if compile_operation(intent['operation'],intent['draft'])!=checked:raise RelationalClientError('The reviewed privilege change was modified')
    if check_grammar(client,checked,review['identity']['sql_mode'])!=review['grammar']:raise RelationalClientError('Native grammar dependency changed')
    handle=client._connect({'route':{**payload['route'],'database':None}});cursor=None;dispatched=acknowledged=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False;cursor=handle.cursor()
        if identity(cursor)!=review['identity'] or observe(cursor,intent)!=review['before']:raise RelationalClientError('Native execution identity or grants changed since review')
        dispatched=True;cursor.execute(compiled['statements'][0]['source']);acknowledged=True
        warnings=[{'level':level,'code':code,'message':message} for level,code,message in (cursor.warnings or ())]
        after=observe(cursor,intent)
        return {'accepted':True,'native_implicit_commit':True,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            'privilege_observation':{'native_acknowledged':True,'before':review['before'],'after':after,'concurrent_external_writers_fenced':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native privilege change failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
