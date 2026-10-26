"""Typed MySQL account clauses; native authentication implementations stay native."""
from collections.abc import Mapping
from copy import deepcopy
import json
import re

from ...sdk import RelationalClientError
from ..mysql_roles import account
from .mysql_indexes import identifier
from .mysql_routines import text

LIMITS=('max_queries_per_hour','max_updates_per_hour','max_connections_per_hour','max_user_connections')
KEYS={'name','host','anonymous','authentication_mode','password','plugin','authentication_string',
      'replace_password','retain_current_password','discard_old_password','active','account_lock',
      'password_expire','password_expire_days','password_history','password_reuse_days',
      'password_require_current','failed_login_attempts','password_lock_time',
      'tls_mode','tls_cipher','tls_issuer','tls_subject','comment','attributes',
      'default_roles','if_not_exists','if_exists','confirmation','administrator',*LIMITS}
KEYS.update({'authentication_factors','factor_actions'})


def integer(value,label,maximum=2**32-1,minimum=0):
    if isinstance(value,int) and not isinstance(value,bool):value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}',value) or not minimum<=int(value)<=maximum:
        raise RelationalClientError(label+' requires bounded unsigned decimal text')
    return value


class Statement:
    def __init__(self,source):self.source=source;self.parser_source=source;self.parameters=[]
    def add(self,value):self.source+=value;self.parser_source+=value
    def value(self,value,label):
        self.parameters.append(text(value,label,65535));self.source+='%s';self.parser_source+="''"
    def compiled(self):return {'source':self.source,'parameters':tuple(self.parameters),'parser_source':self.parser_source}


def principal(target):
    target=target or {};native=target.get('native')
    if not isinstance(native,Mapping):native=(target.get('extensions',{}).get('mysql') or {}).get('native',{})
    user=native.get('user');host=native.get('host')
    if not isinstance(user,str) or not isinstance(host,str):
        # Preserve the old API's bare-user/default-host and simple user@host
        # spellings. Names containing multiple @ characters need the separate
        # native facts; never guess which character separates the host.
        legacy=target.get('display_name')
        if isinstance(legacy,str) and legacy.count('@') <= 1:
            user,host=legacy.rsplit('@',1) if '@' in legacy else (legacy,'%')
    if not isinstance(user,str) or not isinstance(host,str):
        raise RelationalClientError('Select the native account with separate user and host identity')
    account(user,host);return user,host


def compile_operation(operation,draft,target=None):
    if operation=='create_role':
        return compile_role(draft)
    if operation in {'drop_user','drop_role','rename_user'}:
        return compile_identity_change(operation,draft,target)
    if operation not in {'create','alter'} or not isinstance(draft,Mapping):
        raise RelationalClientError('Select a native account create or alter operation')
    draft=deepcopy(dict(draft));options=draft.pop('options',{})
    if not isinstance(options,Mapping) or set(options)&set(draft):raise RelationalClientError('Ambiguous native account options')
    draft.update(options)
    if operation=='alter' and 'changes' in draft:
        changes=draft.pop('changes')
        if not isinstance(changes,Mapping) or set(changes)&set(draft):raise RelationalClientError('Ambiguous native account changes')
        draft.update(changes)
    if set(draft)-KEYS:raise RelationalClientError('Unknown native account option')
    if draft.get('administrator',False) is not False:
        raise RelationalClientError('MySQL uses named privileges and roles, not an administrator flag')
    if operation=='create':
        if 'if_exists' in draft:raise RelationalClientError('CREATE USER uses IF NOT EXISTS')
        user,host=draft.get('name'),draft.get('host','%')
        anonymous=draft.get('anonymous',False)
        if type(anonymous) is not bool:raise RelationalClientError('Anonymous account must be boolean')
        if anonymous:
            if user not in (None,''):raise RelationalClientError('An anonymous account cannot also have a username')
            user=''
        elif not isinstance(user,str) or not user:
            raise RelationalClientError('Supply a username or explicitly select an anonymous account')
    else:
        if {'name','host','anonymous','if_not_exists','default_roles'}&set(draft):raise RelationalClientError('Account identity and default-role replacement use their native operations')
        user,host=principal(target)
    selected=account(user,host)
    exists=draft.get('if_not_exists' if operation=='create' else 'if_exists',False)
    if type(exists) is not bool:raise RelationalClientError('Account existence option must be boolean')
    statement=Statement(operation.upper()+' USER '+(('IF NOT EXISTS ' if operation=='create' else 'IF EXISTS ') if exists else '')+selected)
    mode=draft.get('authentication_mode', 'PASSWORD' if 'password' in draft else 'PLUGIN' if draft.get('plugin') else 'UNCHANGED' if operation=='alter' else 'PASSWORD')
    if not isinstance(mode,str) or mode not in {'PASSWORD','RANDOM_PASSWORD','AUTHENTICATION_STRING','PLUGIN','NONE','UNCHANGED'}:
        raise RelationalClientError('Select the native account authentication mode')
    if mode=='UNCHANGED' and operation=='create':raise RelationalClientError('Select explicit create authentication')
    plugin=draft.get('plugin')
    if plugin == '' and mode in {'PASSWORD','RANDOM_PASSWORD','NONE','UNCHANGED'}:
        plugin=None  # Existing optional text controls submit an empty value.
    if plugin is not None:
        plugin=text(plugin,'Authentication plugin',64)
        if not plugin:raise RelationalClientError('Authentication plugin must not be empty')
    if mode in {'AUTHENTICATION_STRING','PLUGIN'} and not plugin:
        raise RelationalClientError('This authentication mode requires a native plugin')
    if mode in {'NONE','UNCHANGED'} and plugin is not None:
        raise RelationalClientError('Plugin selection requires an explicit authentication change')
    if mode=='PASSWORD':
        if 'password' not in draft:raise RelationalClientError('Supply the new native password explicitly')
        statement.add(' IDENTIFIED'+(' WITH '+identifier(plugin) if plugin else '')+' BY ')
        statement.value(draft['password'],'Password')
    elif mode=='RANDOM_PASSWORD':statement.add(' IDENTIFIED'+(' WITH '+identifier(plugin) if plugin else '')+' BY RANDOM PASSWORD')
    elif mode=='AUTHENTICATION_STRING':
        statement.add(' IDENTIFIED WITH '+identifier(plugin)+' AS ');statement.value(draft.get('authentication_string'),'Authentication string')
    elif mode=='PLUGIN':statement.add(' IDENTIFIED WITH '+identifier(plugin))
    elif mode=='NONE' and operation!='create':raise RelationalClientError('NONE is an explicit create default; use a native authentication change on alter')
    if mode not in {'PASSWORD','AUTHENTICATION_STRING'} and {'password','authentication_string'}&set(draft):
        raise RelationalClientError('Authentication input does not match the selected mode')
    if mode=='PASSWORD' and 'authentication_string' in draft or mode=='AUTHENTICATION_STRING' and 'password' in draft:
        raise RelationalClientError('Select password or native authentication string, not both')
    if 'replace_password' in draft:
        if operation!='alter' or mode not in {'PASSWORD','RANDOM_PASSWORD'}:raise RelationalClientError('REPLACE requires an ALTER password change')
        statement.add(' REPLACE ');statement.value(draft['replace_password'],'Current password')
    retain=draft.get('retain_current_password',False);discard=draft.get('discard_old_password',False)
    if type(retain) is not bool or type(discard) is not bool or retain and discard:
        raise RelationalClientError('Select native retained-password behavior')
    if retain:
        if operation!='alter' or mode not in {'PASSWORD','RANDOM_PASSWORD','AUTHENTICATION_STRING'}:raise RelationalClientError('Retaining the current password requires a native ALTER authentication change')
        statement.add(' RETAIN CURRENT PASSWORD')
    if discard:
        if operation!='alter' or mode!='UNCHANGED':raise RelationalClientError('Discarding the secondary password is a separate native ALTER change')
        statement.add(' DISCARD OLD PASSWORD')
    factors=draft.get('authentication_factors',[]);actions=draft.get('factor_actions',[])
    if not isinstance(factors,list) or not isinstance(actions,list) or len(factors)>2 or len(actions)>2:
        raise RelationalClientError('MySQL supports bounded second/third-factor records')
    if operation=='create':
        if actions:raise RelationalClientError('Create factors use authentication_factors')
        for factor in factors:
            statement.add(' AND ');append_factor(statement,factor)
    elif factors:raise RelationalClientError('Alter factors use explicit ADD, MODIFY or DROP records')
    if actions:
        if mode!='UNCHANGED' or retain or discard or 'replace_password' in draft:
            raise RelationalClientError('Native factor changes are separate from first-factor/dual-password changes')
        seen=set();operation_kind=None
        for row in actions:
            if not isinstance(row,Mapping) or set(row)-{'action','factor','mode','plugin','password','authentication_string'}:
                raise RelationalClientError('Unknown native factor action field')
            action=row.get('action');factor=row.get('factor')
            if not isinstance(action,str) or action not in {'ADD','MODIFY','DROP'} or type(factor) is not int or factor not in {2,3} or factor in seen:
                raise RelationalClientError('Select distinct native factors2/3 and one action kind')
            if operation_kind is not None and action!=operation_kind:raise RelationalClientError('Native ALTER combines only the same factor action kind')
            if action=='ADD' and seen and factor<max(seen):raise RelationalClientError('Native ADD factors must be in ascending order')
            seen.add(factor);operation_kind=action;statement.add(' '+action+' '+str(factor)+' FACTOR')
            identity={key:value for key,value in row.items() if key not in {'action','factor'}}
            if action=='DROP':
                if identity:raise RelationalClientError('DROP factor has no replacement authentication data')
            else:statement.add(' ');append_factor(statement,identity)
    roles=draft.get('default_roles')
    if roles is not None:
        if operation!='create' or not isinstance(roles,list):raise RelationalClientError('Default roles require native account records on create')
        values=[]
        for row in roles:
            if not isinstance(row,Mapping) or set(row)-{'user','host'}:raise RelationalClientError('Default role requires separate user and host')
            values.append(account(row.get('user'),row.get('host','%')))
        if values:statement.add(' DEFAULT ROLE '+','.join(values))
    tls=draft.get('tls_mode','UNCHANGED')
    if not isinstance(tls,str) or tls not in {'UNCHANGED','NONE','SSL','X509','SPECIFIED'}:raise RelationalClientError('Select native REQUIRE policy')
    tls_values=[(key,label) for key,label in [('tls_cipher','CIPHER'),('tls_issuer','ISSUER'),('tls_subject','SUBJECT')] if key in draft]
    if tls_values and tls!='SPECIFIED':raise RelationalClientError('Certificate/cipher clauses require SPECIFIED TLS policy')
    if tls=='SPECIFIED':
        if not tls_values:raise RelationalClientError('Supply a native TLS cipher/issuer/subject requirement')
        statement.add(' REQUIRE ')
        for index,(key,label) in enumerate(tls_values):
            if index:statement.add(' AND ')
            statement.add(label+' ');statement.value(draft[key],label)
    elif tls!='UNCHANGED':statement.add(' REQUIRE '+tls)
    limits=[key for key in LIMITS if key in draft]
    if limits:
        statement.add(' WITH '+' '.join(key.upper()+' '+integer(draft[key],key) for key in limits))
    if 'active' in draft:
        if type(draft['active']) is not bool:raise RelationalClientError('Account active must be boolean')
        statement.add(' ACCOUNT '+('UNLOCK' if draft['active'] else 'LOCK'))
    locked=draft.get('account_lock','UNCHANGED')
    if not isinstance(locked,str) or locked not in {'UNCHANGED','LOCK','UNLOCK'}:raise RelationalClientError('Select native account lock behavior')
    if locked!='UNCHANGED':
        if 'active' in draft:raise RelationalClientError('Select either account lock policy or legacy active state')
        statement.add(' ACCOUNT '+locked)
    expiry=draft.get('password_expire','UNCHANGED')
    if not isinstance(expiry,str) or expiry not in {'UNCHANGED','DEFAULT','NEVER','IMMEDIATE','INTERVAL'}:raise RelationalClientError('Select native password expiry policy')
    if 'password_expire_days' in draft and expiry!='INTERVAL':raise RelationalClientError('Expiry days require INTERVAL')
    if expiry=='INTERVAL':statement.add(' PASSWORD EXPIRE INTERVAL '+integer(draft.get('password_expire_days'),'Expiry days',65535,1)+' DAY')
    elif expiry!='UNCHANGED':statement.add(' PASSWORD EXPIRE'+('' if expiry=='IMMEDIATE' else ' '+expiry))
    for key,prefix,suffix in [('password_history',' PASSWORD HISTORY ',''),('password_reuse_days',' PASSWORD REUSE INTERVAL ',' DAY')]:
        if key in draft:
            value=draft[key]
            statement.add(prefix+('DEFAULT' if value=='DEFAULT' else integer(value,key)+suffix))
    current=draft.get('password_require_current','UNCHANGED')
    if not isinstance(current,str) or current not in {'UNCHANGED','REQUIRED','OPTIONAL','DEFAULT'}:raise RelationalClientError('Select native current-password policy')
    if current!='UNCHANGED':statement.add(' PASSWORD REQUIRE CURRENT'+('' if current=='REQUIRED' else ' '+current))
    if 'failed_login_attempts' in draft:statement.add(' FAILED_LOGIN_ATTEMPTS '+integer(draft['failed_login_attempts'],'Failed login attempts',32767))
    if 'password_lock_time' in draft:
        value=draft['password_lock_time'];statement.add(' PASSWORD_LOCK_TIME '+('UNBOUNDED' if value=='UNBOUNDED' else integer(value,'Password lock time',32767)))
    if 'comment' in draft and 'attributes' in draft:raise RelationalClientError('Select native COMMENT or ATTRIBUTE for this change')
    if 'comment' in draft:statement.add(' COMMENT ');statement.value(draft['comment'],'Account comment')
    if 'attributes' in draft:
        if not isinstance(draft['attributes'],Mapping):raise RelationalClientError('Account attributes require a native object')
        try:value=json.dumps(draft['attributes'],ensure_ascii=False,separators=(',',':'),allow_nan=False)
        except (TypeError,ValueError):raise RelationalClientError('Account attributes require finite native JSON values') from None
        statement.add(' ATTRIBUTE ');statement.value(value,'Account attributes')
    if operation=='alter' and statement.source=='ALTER USER '+('IF EXISTS ' if exists else '')+selected:
        raise RelationalClientError('Select at least one native account change')
    return {'statements':[statement.compiled()], 'mysql_account_change':{'operation':operation,'draft':draft,'user':user,'host':host},
        'warnings':['Native account changes use an independent connection and are never automatically replayed. Authentication, TLS and policy enforcement remain MySQL-owned.']}


def observe(cursor,intent):
    """Private concurrency binding; never return native authentication bytes."""
    import hashlib
    cursor.execute('SELECT * FROM mysql.user WHERE User=%s AND Host=%s',(intent['user'],intent['host']))
    names=[str(column[0]).lower() for column in cursor.description]
    rows=cursor.fetchall()
    if len(rows)>1:raise RelationalClientError('Native account identity is ambiguous')
    if not rows:return {'present':False,'private_fingerprint':None,'public':{'present':False,'user':intent['user'],'host':intent['host']}}
    values=dict(zip(names,rows[0]));cursor.execute('SHOW CREATE USER '+account(intent['user'],intent['host']));definition=cursor.fetchone()
    if not definition or not isinstance(definition[0],str):raise RelationalClientError('Native account definition is unavailable')
    def normalized(value):
        if isinstance(value,(bytes,bytearray,memoryview)):return {'bytes_hex':bytes(value).hex()}
        if isinstance(value,(set,frozenset)):return sorted(value)
        return value if value is None or isinstance(value,(str,int,float,bool)) else str(value)
    cursor.execute('SELECT FROM_USER,FROM_HOST,TO_USER,TO_HOST,WITH_ADMIN_OPTION FROM mysql.role_edges '
        'WHERE (FROM_USER=%s AND FROM_HOST=%s) OR (TO_USER=%s AND TO_HOST=%s) ORDER BY FROM_USER,FROM_HOST,TO_USER,TO_HOST',
        (intent['user'],intent['host'],intent['user'],intent['host']))
    edges=[list(row) for row in cursor.fetchall()]
    cursor.execute('SELECT DEFAULT_ROLE_USER,DEFAULT_ROLE_HOST FROM mysql.default_roles WHERE USER=%s AND HOST=%s ORDER BY DEFAULT_ROLE_USER,DEFAULT_ROLE_HOST',
        (intent['user'],intent['host']))
    defaults=[list(row) for row in cursor.fetchall()]
    material=json.dumps({'row':{key:normalized(value) for key,value in values.items()},'definition':definition[0],
        'role_edges':edges,'default_roles':defaults},sort_keys=True,ensure_ascii=False,separators=(',',':'))
    public={key:normalized(values[key]) for key in ('user','host','plugin','account_locked','password_expired','password_lifetime',
        'max_questions','max_updates','max_connections','max_user_connections','ssl_type','password_reuse_history','password_reuse_time','password_require_current') if key in values}
    try:
        attributes=json.loads(values.get('user_attributes') or '{}')
        factors=attributes.get('multi_factor_authentication',[])
        if not isinstance(factors,list):raise ValueError()
        public['authentication_factors']=[{'factor':index+2,'plugin':row['plugin'],
            'requires_registration':bool(row.get('requires_registration')),'passwordless':bool(row.get('passwordless'))}
            for index,row in enumerate(factors)]
        public['factor_catalog_state']='observed'
    except (AttributeError,ValueError,KeyError,TypeError):public['factor_catalog_state']='unavailable'
    return {'present':True,'private_fingerprint':hashlib.sha256(material.encode('utf8')).hexdigest(),
            'public':{'present':True,**public,'role_edges':edges,'default_roles':defaults,'authentication_secrets_returned':False}}


def bind_review(client,planned):
    from . import mysql_passwords
    from .mysql_indexes import context
    compiled=planned['provider_payload']['compiled'];intent=compiled['mysql_account_change']
    scope = planned['provider_payload'].get('password_delivery_scope')
    delivery=mysql_passwords.binding(client,intent,scope)
    handle=client._connect({'route':{**planned['provider_payload']['route'],'database':None}});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=context(cursor)
        grammar=check_grammar(client,compiled,identity['sql_mode']);before=observe(cursor,intent)
        intent['review']={'identity':identity,'before':before,'grammar':grammar,**({'password_delivery':delivery, 'delivery_scope':scope} if delivery else {})}
        planned['command_preview'].update(native_execution_identity=identity,native_account_observation=before['public'],native_grammar=grammar)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    from . import mysql_passwords
    from .mysql_indexes import context
    if connection is not None:raise RelationalClientError('Account changes require an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_account_change'];review=intent.get('review')
    if not isinstance(review,Mapping):raise RelationalClientError('Review the native account before dispatch')
    target={'native':{'user':intent['user'],'host':intent['host']}}
    candidate=deepcopy(compiled);candidate['mysql_account_change'].pop('review',None)
    if compile_operation(intent['operation'],intent['draft'],target)!=candidate:raise RelationalClientError('Reviewed native account change was modified')
    if check_grammar(client,candidate,review['identity']['sql_mode'])!=review['grammar']:raise RelationalClientError('Native grammar dependency changed')
    if mysql_passwords.factors(intent) and not review.get('password_delivery'):raise RelationalClientError('Review protected password delivery before dispatch')
    receiver=mysql_passwords.receiver(client,intent,review.get('password_delivery'))
    handle=client._connect({'route':{**payload['route'],'database':None}});cursor=None;dispatched=acknowledged=False;acknowledgements=[];reservation=None;delivered=[];primary=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False
        cursor=handle.cursor();identity=context(cursor);before=observe(cursor,intent)
        if identity!=review['identity'] or before!=review['before']:raise RelationalClientError('Native account or execution identity changed since review')
        warnings=[]
        if receiver:
            reservation=receiver.reserve(intent['user'],intent['host'],mysql_passwords.factors(intent))
            if reservation is None:raise RelationalClientError('Protected password delivery capacity was not reserved')
        for ordinal,statement in enumerate(compiled['statements'],1):
            dispatched=True
            cursor.execute(statement['source'],statement['parameters'] or None);acknowledged=True
            acknowledgements.append({'ordinal':ordinal,'native_acknowledged':True})
            if receiver:delivered.extend(mysql_passwords.deliver(receiver,reservation,cursor,intent))
            warnings.extend({'level':level,'code':code,**({} if receiver else {'message':message})} for level,code,message in (cursor.warnings or ()))
        after_intent={**intent,**({'user':intent['new_user'],'host':intent['new_host']} if intent['operation']=='rename_user' else {})}
        after=observe(cursor,after_intent)
        return {'accepted':True,'native_implicit_commit':True,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            **({'protected_password_results':delivered} if receiver else {}),
            'account_observation':{'native_acknowledged':True,'acknowledgements':acknowledgements,'before':before['public'],'after':after['public'],'concurrent_external_writers_fenced':False}}
    except Exception as error:
        primary=True
        failure=error if isinstance(error,RelationalClientError) and not receiver else RelationalClientError('Native account change failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.native_acknowledgements=acknowledgements
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        raise failure from None
    finally:
        try:
            if receiver and reservation is not None:receiver.release(reservation)
        except Exception:
            if not primary:
                failure=RelationalClientError('Protected password delivery cleanup failed; inspect native state before another review')
                failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
                raise failure from None
        finally:
            if cursor is not None:client._safe_close(cursor)
            try:client._forget_and_close(handle)
            except Exception:
                if not primary:
                    failure=RelationalClientError('Account connection cleanup failed; inspect native state before another review')
                    failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
                    raise failure from None


def compile_role(draft):
    if not isinstance(draft,Mapping):raise RelationalClientError('Select native role properties')
    draft=deepcopy(dict(draft));options=draft.pop('options',{})
    if not isinstance(options,Mapping) or set(options)&set(draft):raise RelationalClientError('Ambiguous native role options')
    draft.update(options)
    if set(draft)-{'name','host','if_not_exists','members'}:raise RelationalClientError('Unknown native role create option')
    user,host=draft.get('name'),draft.get('host','%');selected=account(user,host)
    exists=draft.get('if_not_exists',False)
    if type(exists) is not bool:raise RelationalClientError('IF NOT EXISTS must be boolean')
    source='CREATE ROLE '+('IF NOT EXISTS ' if exists else '')+selected
    statements=[Statement(source).compiled()]
    members=draft.get('members',[])
    if not isinstance(members,list) or len(members)>4096:raise RelationalClientError('Initial members require native account records')
    recipients=[]
    for row in members:
        if isinstance(row,str) and row.count('@')<=1:
            member,member_host=row.rsplit('@',1) if '@' in row else (row,'%')
        elif isinstance(row,Mapping) and not set(row)-{'user','host'}:
            member,member_host=row.get('user'),row.get('host','%')
        else:raise RelationalClientError('Initial members require separate native user and host')
        recipients.append(account(member,member_host))
    if recipients:statements.append(Statement('GRANT '+selected+' TO '+','.join(recipients)).compiled())
    return {'statements':statements,'mysql_account_change':{'operation':'create_role','draft':draft,'user':user,'host':host},
        'warnings':['Role creation and optional initial grants are separate native statements. A later grant failure does not undo role creation. Inspect native state before a new review; no mutation is automatically replayed.']}


def check_grammar(client,compiled,mode):
    from .mysql_parser import library,native
    try:path=library(client)
    except OSError:path=None
    if path is None:raise RelationalClientError('Account review requires the registered MySQL9.7 Shell native grammar library; no DCL was executed')
    result=native(path,[{'source':statement['parser_source'],'sql_mode':mode} for statement in compiled['statements']])
    if not all(statement['sql_syntax_valid'] for statement in result['statements']):
        raise RelationalClientError('Native MySQL grammar rejected the account change; no DCL was executed')
    return {'library_sha256':result['library_sha256'],'worker_sha256':result['worker_sha256'],
            'parser_version':result['parser_version'],'sql_executed':False}


def append_factor(statement,row):
    if not isinstance(row,Mapping) or set(row)-{'mode','plugin','password','authentication_string'}:
        raise RelationalClientError('Unknown native factor authentication field')
    mode=row.get('mode','PLUGIN' if 'plugin' in row else 'PASSWORD')
    if not isinstance(mode,str) or mode not in {'PASSWORD','RANDOM_PASSWORD','AUTHENTICATION_STRING','PLUGIN'}:
        raise RelationalClientError('Select a native factor identification mode; generated secrets require protected results')
    plugin=row.get('plugin')
    if plugin is not None:
        plugin=text(plugin,'Factor plugin',64)
        if not plugin:raise RelationalClientError('Factor plugin must not be empty')
    if mode in {'PLUGIN','AUTHENTICATION_STRING'} and plugin is None:raise RelationalClientError('Factor mode requires a native plugin')
    statement.add('IDENTIFIED'+(' WITH '+identifier(plugin) if plugin else ''))
    if mode=='PASSWORD':
        if 'authentication_string' in row:raise RelationalClientError('Select password or authentication string')
        statement.add(' BY ');statement.value(row.get('password'),'Factor password')
    elif mode=='RANDOM_PASSWORD':
        if {'password','authentication_string'}&set(row):raise RelationalClientError('Generated factors take no supplied credential')
        statement.add(' BY RANDOM PASSWORD')
    elif mode=='AUTHENTICATION_STRING':
        if 'password' in row:raise RelationalClientError('Select password or authentication string')
        statement.add(' AS ');statement.value(row.get('authentication_string'),'Factor authentication string')
    elif 'password' in row or 'authentication_string' in row:raise RelationalClientError('Plugin-only factor has no supplied credential')


def compile_identity_change(operation,draft,target):
    if not isinstance(draft,Mapping):raise RelationalClientError('Select native account identity properties')
    draft=deepcopy(dict(draft));allowed={'confirmation','if_exists','cascade'} if operation.startswith('drop_') else {'confirmation','new_name','new_host'}
    if set(draft)-allowed:raise RelationalClientError('Unknown native account identity option')
    user,host=principal(target);selected=account(user,host);intent={'operation':operation,'draft':draft,'user':user,'host':host}
    if operation=='rename_user':
        new_user=draft.get('new_name',user);new_host=draft.get('new_host',host)
        if new_user==user and new_host==host:raise RelationalClientError('Select a new account name or host')
        source='RENAME USER '+selected+' TO '+account(new_user,new_host)
        intent.update(new_user=new_user,new_host=new_host)
    else:
        exists=draft.get('if_exists',False)
        if type(exists) is not bool or draft.get('cascade',False) is not False:raise RelationalClientError('Native account drop supports IF EXISTS, not CASCADE')
        source='DROP '+('USER' if operation=='drop_user' else 'ROLE')+' '+('IF EXISTS ' if exists else '')+selected
    return {'statements':[Statement(source).compiled()],'mysql_account_change':intent,
        'warnings':['Users and roles share native account identities. DROP removes the account and its grants; it is not a membership revocation. The independently owned operation is never automatically replayed.']}
