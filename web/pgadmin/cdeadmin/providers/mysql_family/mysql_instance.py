"""Reviewed native ALTER INSTANCE with independent protocol ownership."""
from collections.abc import Mapping
from copy import deepcopy
import json
import re
from pathlib import PurePosixPath,PureWindowsPath

from ...sdk import RelationalClientError

OPERATIONS={
    'rotate_innodb_master_key':('Rotate InnoDB master key','ROTATE INNODB MASTER KEY'),
    'rotate_binlog_master_key':('Rotate binary log master key','ROTATE BINLOG MASTER KEY'),
    'reload_tls':('Reload native TLS context','RELOAD TLS'),
    'reload_keyring':('Reload native keyring','RELOAD KEYRING'),
    'enable_innodb_redo':('Enable InnoDB redo logging','ENABLE INNODB REDO_LOG'),
    'disable_innodb_redo':('Disable InnoDB redo for initial load','DISABLE INNODB REDO_LOG'),
    'import_table_sdi':('Import native table definitions from SDI files',None),
}


def target_uuid(target):
    if not isinstance(target,Mapping) or target.get('resource_kind')!='server':
        raise RelationalClientError('Select the exact native MySQL server')
    native=target.get('native') or target.get('extensions',{}).get('mysql',{}).get('native',{})
    value=native.get('server_uuid')
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value):
        raise RelationalClientError('The native MySQL server UUID must be observed')
    plain=target.get('resource_id')=='server:MySQL' and target.get('display_path')==['MySQL'] and target.get('display_name')=='MySQL'
    exchanged=(target.get('resource_id')=='mysql-server:'+json.dumps([value,'server'],separators=(',',':')) and
        target.get('display_path')==[value] and target.get('display_name')=='MySQL '+value)
    if not plain and not exchanged:raise RelationalClientError('The native MySQL server address differs')
    return value


def compile_operation(operation,draft,target):
    if operation not in OPERATIONS or not isinstance(draft,Mapping):
        raise RelationalClientError('Select a native MySQL instance operation')
    uuid=target_uuid(target)
    allowed={'confirmation','lock_wait_seconds'}
    if operation=='reload_tls':allowed|={'channel','rollback_on_error'}
    if operation=='disable_innodb_redo':allowed|={'initial_load_only'}
    if operation=='import_table_sdi':allowed|={'files','trusted_host_files','database'}
    if set(draft)-allowed or draft.get('confirmation')!=target['display_name']:
        raise RelationalClientError('Confirm the exact MySQL server name and native options')
    timeout=draft.get('lock_wait_seconds',15)
    if type(timeout) is not int or not 1<=timeout<=120:
        raise RelationalClientError('Native lock wait requires 1 to 120 seconds')
    parameters=()
    if operation=='import_table_sdi':
        files=draft.get('files')
        if (not isinstance(files,list) or not 1<=len(files)<=32 or
                any(not isinstance(path,str) or '\0' in path or len(path)>4096 or
                    not (PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()) for path in files) or
                len(set(files))!=len(files) or
                draft.get('trusted_host_files') is not True):
            raise RelationalClientError('Select 1 to 32 distinct absolute SDI file patterns on the database host and explicitly trust their definitions')
        parameters=tuple(files);source='IMPORT TABLE FROM '+','.join(['%s']*len(files))
        database=draft.get('database')
        if not isinstance(database,str) or not database or '\0' in database or len(database)>64:
            raise RelationalClientError('Select the exact native default database for SDI import')
    else:source='ALTER INSTANCE '+OPERATIONS[operation][1]
    if operation=='reload_tls':
        channel=draft.get('channel','mysql_main');rollback=draft.get('rollback_on_error',True)
        if channel not in {'mysql_main','mysql_admin'} or type(rollback) is not bool:
            raise RelationalClientError('Select the native main/admin TLS channel and rollback behavior')
        source+=' FOR CHANNEL '+channel
        if not rollback:source+=' NO ROLLBACK ON ERROR'
    if operation=='disable_innodb_redo' and draft.get('initial_load_only') is not True:
        raise RelationalClientError('Confirm this server is dedicated to an initial load before disabling crash recovery')
    return {'statements':[{'source':source,'parameters':parameters}],
        'mysql_instance':{'operation':operation,'draft':dict(draft),'target':deepcopy(dict(target)),'server_uuid':uuid},
        'warnings':['This native instance operation owns a separate connection and cannot be undone by rolling back a query session. It is never automatically replayed.',
            'A native acknowledgement and later runtime observations are reported separately.']+
            (['TLS reload does not attest certificate file contents or reconnect existing clients.'] if operation=='reload_tls' else [])+
            (['Disabling redo is for initial loading of a new instance. Unexpected server termination while redo is disabled can corrupt data; re-enable redo before ordinary service.'] if operation=='disable_innodb_redo' else [])+
            (['SDI files and any corresponding engine data/index files must already be staged on the database host. MySQL owns FILE privileges, secure_file_priv, wildcard expansion, dictionary import and native engine restrictions. No application-host files are read or transferred.',
              'This review binds the selected paths, server identity and visible table inventory, not file bytes or concurrent external writers. Import can change native metadata/files and is never automatically retried.'] if operation=='import_table_sdi' else [])}


def form(operation,field):
    fields=[field('lock_wait_seconds','Native metadata lock wait (seconds)','number',default=15)]
    if operation=='reload_tls':fields += [field('channel','Native TLS channel','select',default='mysql_main',options=('mysql_main','mysql_admin')),
        field('rollback_on_error','Keep the prior TLS context on reload error','boolean',default=True)]
    if operation=='disable_innodb_redo':fields.append(field('initial_load_only','This server is dedicated to an initial load; crash recovery will be unavailable','boolean',True,default=False))
    if operation=='import_table_sdi':fields += [field('database','Native default database for import','text',True),
        field('files','Database-host SDI file patterns (JSON array)','json',True,default=[]),
        field('trusted_host_files','I trust these native definitions and have staged their required engine files on the database host','boolean',True,default=False)]
    fields.append(field('confirmation','Exact server name','text',True))
    return {'form_id':'mysql.server.'+operation,'title':OPERATIONS[operation][0],'fields':fields}


def environment(cursor):
    cursor.execute('SELECT VERSION(),@@server_uuid,CURRENT_USER(),USER(),CURRENT_ROLE()')
    row=cursor.fetchone()
    if not row or len(row)!=5 or any(not isinstance(value,str) for value in row) or row[0].split('-')[0]!='9.7.0':
        raise RelationalClientError('Exact native MySQL instance execution identity is unavailable')
    return dict(zip(('version','server_uuid','effective_principal','authenticated_principal','active_roles'),row))


def observe(cursor,operation,draft):
    try:
        if operation=='import_table_sdi':
            cursor.execute('SELECT @@hostname,@@datadir,@@secure_file_priv,DATABASE()');host=list(cursor.fetchone())
            cursor.execute("SELECT TABLE_SCHEMA,TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','mysql','sys') ORDER BY TABLE_SCHEMA,TABLE_NAME LIMIT 20001")
            rows=cursor.fetchall()
            if len(rows)>20000:raise RelationalClientError('The native table import review exceeds its 20000-table inventory bound')
            return {'available':True,'host':host,'rows':[list(row) for row in rows],'host_file_bytes_observed':False}
        if operation in {'enable_innodb_redo','disable_innodb_redo'}:
            cursor.execute("SHOW GLOBAL STATUS LIKE 'Innodb_redo_log_enabled'")
        elif operation=='reload_tls':
            cursor.execute("SELECT PROPERTY,VALUE FROM performance_schema.tls_channel_status WHERE CHANNEL=%s AND (PROPERTY='Enabled' OR PROPERTY LIKE 'Current_tls_%%') ORDER BY PROPERTY",(draft.get('channel','mysql_main'),))
        elif operation=='rotate_binlog_master_key':
            cursor.execute('SELECT @@GLOBAL.binlog_encryption')
        else:
            cursor.execute("SELECT STATUS_KEY,STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY IN ('Component_name','Component_status') ORDER BY STATUS_KEY")
        rows=cursor.fetchmany(257)
        if len(rows)>256:raise RelationalClientError('Native instance observation exceeds its bound')
        value={'available':bool(rows),'rows':[list(row) for row in rows]}
        if operation=='reload_tls':
            prefix='admin_' if draft.get('channel','mysql_main')=='mysql_admin' else ''
            names=tuple(prefix+name for name in ('ssl_ca','ssl_capath','ssl_cert','ssl_key','ssl_cipher','ssl_crl','ssl_crlpath','tls_version','tls_ciphersuites'))
            cursor.execute('SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_variables WHERE VARIABLE_NAME IN ('+','.join(['%s']*len(names))+') ORDER BY VARIABLE_NAME',names)
            configured=cursor.fetchmany(10)
            value.update(configured_variables=[list(row) for row in configured],configured_variables_complete=len(configured)==len(names))
        return value
    except Exception as error:
        if getattr(error,'errno',None) not in {1044,1045,1142,1143,1227}:raise
        return {'available':False,'native_error_code':error.errno,'rows':[]}


def operation_route(payload,intent):
    return {**payload['route'],'database':intent['draft']['database']} if intent['operation']=='import_table_sdi' else payload['route']


def bind_review(client,planned):
    payload=planned['provider_payload'];intent=payload['compiled']['mysql_instance']
    handle=client._connect({'route':operation_route(payload,intent)});cursor=None
    try:
        handle.autocommit=True;cursor=handle.cursor();identity=environment(cursor)
        if identity['server_uuid']!=intent['server_uuid']:raise RelationalClientError('Native MySQL instance differs from the selected server')
        before=observe(cursor,intent['operation'],intent['draft'])
        intent['review']={'execution_identity':identity,'before':before}
        planned['command_preview'].update(native_execution_identity=identity,native_instance_observation=before)
        return planned
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client,request,connection=None):
    if connection is not None:raise RelationalClientError('MySQL instance maintenance requires an independently owned connection')
    payload=request['provider_payload'];compiled=payload['compiled'];intent=compiled['mysql_instance']
    checked=deepcopy(compiled);review=checked['mysql_instance'].pop('review',None)
    if not isinstance(review,Mapping) or compile_operation(intent['operation'],intent['draft'],intent['target'])!=checked:
        raise RelationalClientError('Review the exact native MySQL instance operation before dispatch')
    handle=client._connect({'route':operation_route(payload,intent)});cursor=None;dispatched=acknowledged=False
    try:
        handle.autocommit=True;handle.get_warnings=True;handle.raise_on_warnings=False
        cursor=handle.cursor();identity=environment(cursor);before=observe(cursor,intent['operation'],intent['draft'])
        if identity!=review['execution_identity'] or before!=review['before']:
            raise RelationalClientError('Native MySQL instance identity or observed maintenance state changed since review')
        cursor.execute('SET SESSION lock_wait_timeout = %s',(intent['draft'].get('lock_wait_seconds',15),))
        statement=compiled['statements'][0];dispatched=True
        if statement['parameters']:cursor.execute(statement['source'],statement['parameters'])
        else:cursor.execute(statement['source'])
        acknowledged=True
        warnings=[{'level':level,'code':code,'message':text} for level,code,text in (cursor.warnings or ())]
        after=observe(cursor,intent['operation'],intent['draft'])
        redo={'enable_innodb_redo':'ON','disable_innodb_redo':'OFF'}.get(intent['operation'])
        verified=(after['rows']==[['Innodb_redo_log_enabled',redo]]) if redo else None
        return {'accepted':True,'native_implicit_commit':True,'commit_requested':False,'rollback_requested':False,
            'staged_in_provider_session':False,'automatic_retry':False,'native_warnings':warnings,
            'driver_observation_only':True,'transaction_finality_interpreted_by_common_code':False,
            'instance_observation':{'native_acknowledged':True,'execution_identity':identity,'operation':intent['operation'],
                'before':before,'after':after,'redo_state_verified':verified,
                'native_effect_rollback_available':False,'existing_tls_clients_reconnected':False}}
    except Exception as error:
        failure=error if isinstance(error,RelationalClientError) else RelationalClientError('Native MySQL instance operation failed ('+type(error).__name__+')')
        failure.native_dispatched=dispatched;failure.native_acknowledged=acknowledged;failure.automatic_retry=False
        failure.errno=getattr(error,'errno',None);failure.sqlstate=getattr(error,'sqlstate',None)
        failure.native_status_codes=(failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None:client._safe_close(cursor)
        client._forget_and_close(handle)
