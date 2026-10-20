"""Native process-scoped EDS pool facts and reviewed original-session controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import uuid

from ...sdk import RelationalClientError
from .error_diagnostics import status_codes

KEYS=('EXT_CONN_POOL_SIZE','EXT_CONN_POOL_LIFETIME','EXT_CONN_POOL_IDLE_COUNT','EXT_CONN_POOL_ACTIVE_COUNT')
SQL=('SELECT CURRENT_CONNECTION, CURRENT_USER, CURRENT_ROLE, '
    "RDB$GET_CONTEXT('SYSTEM','DB_NAME'), A.MON$SERVER_PID, "+
    ', '.join("RDB$GET_CONTEXT('SYSTEM','"+key+"')" for key in KEYS)+
    ' FROM RDB$DATABASE D JOIN MON$ATTACHMENTS A ON A.MON$ATTACHMENT_ID=CURRENT_CONNECTION')
WARNINGS=[
    'The EDS pool belongs to this native engine process and can be shared by other attachments and databases. It is not an application connection pool or a per-database setting.',
    'Native pool changes take effect immediately and are not undone by transaction rollback. They do not update firebird.conf or databases.conf and do not survive native process restart.',
    'CLEAR ALL closes idle connections and removes active connections from pool tracking. It does not cancel their running external statements. CLEAR OLDEST removes expired idle connections, not an arbitrarily selected connection.',
    'Counts are independent native observations and can change concurrently. An acknowledged command does not prove a later global count or exclusive ownership of the pool.',
    'Firebird5.0.4 parses CLEAR database but its native implementation rejects that operation; this workflow does not emulate it.']


def metadata(row):
    if (not isinstance(row,(tuple,list)) or len(row)!=9 or
            any(not isinstance(row[index],str) or not row[index] for index in (1,2,3))):
        raise RelationalClientError('Native Firebird EDS pool identity is unavailable')
    def integer(value):
        if type(value) is int and value>=0:return str(value)
        if isinstance(value,str) and value.isascii() and value.isdecimal() and len(value)<=20:
            return str(int(value))
        raise RelationalClientError('Native Firebird EDS pool counter is unavailable')
    return {'available':True,'scope':'attachment-engine-process','attachment_id':integer(row[0]),
        'effective_principal':row[1].rstrip(' '),'role':row[2].rstrip(' '),'database':row[3],
        'server_process_id':integer(row[4]),'size':integer(row[5]),'lifetime_seconds':integer(row[6]),
        'idle_count':integer(row[7]),'active_count':integer(row[8]),
        'transactional':False,'configuration_file_updated':False,'native_connection_list_available':False,
        'clear_database_implemented':False,'visibility':'current attachment native context',
        'observation_authority':'RDB$GET_CONTEXT SYSTEM / current MON$ATTACHMENTS row'}


def observe(client,connection):
    module=client.module
    manager=connection.transaction_manager(module.tpb(module.Isolation.READ_COMMITTED_RECORD_VERSION,
        access_mode=module.TraAccessMode.READ,lock_timeout=2),default_action=module.DefaultAction.ROLLBACK)
    cursor=None
    try:
        cursor=manager.cursor();cursor.execute(SQL);row=cursor.fetchone()
        return metadata(row)
    finally:
        failed=False
        if cursor is not None:
            try:cursor.close()
            except BaseException:failed=True
        try:
            if manager.is_active():manager.rollback()
        except BaseException:failed=True
        try:manager.close()
        except BaseException:failed=True
        if failed:
            client._state(connection).result_cleanup_failed=True
            raise RelationalClientError('Native EDS observation cleanup is unconfirmed; close this session')


def compile_operation(draft):
    if not isinstance(draft,dict):raise ValueError('Select one native EDS pool operation')
    operation=draft.get('action')
    if not isinstance(operation,str):raise ValueError('Select one native EDS pool operation')
    if operation=='set_size' and set(draft)=={'action','value'}:
        value=draft['value']
        if type(value) is not int or not 0<=value<=1000:raise ValueError('Native EDS pool size requires an integer from 0 through 1000')
        return 'ALTER EXTERNAL CONNECTIONS POOL SET SIZE '+str(value),{'size':str(value)}
    if operation=='set_lifetime' and set(draft)=={'action','value','unit'}:
        value,unit=draft['value'],draft['unit']
        units={'SECOND':1,'MINUTE':60,'HOUR':3600}
        if type(value) is not int or not 1<=value<=65535 or not isinstance(unit,str) or unit not in units or value*units[unit]>86400:
            raise ValueError('Select native SECOND, MINUTE or HOUR lifetime from 1 second through 1 day, with a uint16 quantity')
        return 'ALTER EXTERNAL CONNECTIONS POOL SET LIFETIME '+str(value)+' '+unit,{'lifetime_seconds':str(value*units[unit])}
    if operation in {'clear_all','clear_oldest'} and set(draft)=={'action'}:
        return 'ALTER EXTERNAL CONNECTIONS POOL CLEAR '+('ALL' if operation=='clear_all' else 'OLDEST'),{}
    raise ValueError('Select an implemented native EDS pool size, lifetime or clear operation')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def identity():
    sources=(Path(__file__),Path(__file__).with_name('query_client.py'))
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}


def stable(observation):
    return {key:observation[key] for key in ('attachment_id','effective_principal','role','database','server_process_id','size','lifetime_seconds')}


def action(client,connection,session_id,request,archive):
    if not isinstance(request,dict):raise ValueError('Select a native Firebird EDS request')
    operation=request.get('operation')
    fields={'inventory':{'operation'},'review':{'operation','draft'},
        'apply':{'operation','review_id','review_digest','confirmed','confirmation'},
        'receipt':{'operation','review_id'},'cancel':{'operation','review_id'},
        'discard':{'operation','review_id','review_digest'}}
    if not isinstance(operation,str) or operation not in fields or set(request)!=fields[operation]:raise ValueError('Unknown native Firebird EDS request')
    records=client._eds_pool_reviews
    def receipt(key):
        task=records.get(key);native=None
        if task and task['connection'] is connection and task.get('token'):
            native=client.describe_result(task['token'])
        # describe_result waits for the worker's release callback. Read durable
        # facts afterwards so a completed flag cannot accompany an older phase.
        value=archive.get(key)
        if native is not None:
            payload=native['payload']
            value.update(native_operation_running=not native['complete'],
                session_reuse_blocked=bool(payload.get('session_reuse_blocked')) or value.get('session_reuse_blocked',False),
                receipt_persistence_failed=bool(payload.get('native_receipt_persistence_failed')))
        return value
    if operation in {'receipt','cancel'}:
        record=archive.get(request['review_id'])
        if record['session_id']!=session_id:raise ValueError('EDS operation belongs to another native session')
        task=records.get(request['review_id'])
        if operation=='cancel' and task and task['connection'] is connection and task.get('token'):
            accepted=client.cancel(task['token'])
            archive.update(request['review_id'],cancellation_requested=True,cancellation_delivery_accepted=bool(accepted))
        return receipt(request['review_id'])
    with client._exclusive(connection):
        if operation=='inventory':
            return {'native_pool':observe(client,connection),'warnings':WARNINGS,'actions':['set_size','set_lifetime','clear_all','clear_oldest']}
        if operation=='review':
            source,expected=compile_operation(request['draft'])
            if len(records)>=64:
                for key in list(records):
                    task=records[key]
                    if not task.get('token') or task['token'].done:records.pop(key)
            if len(records)>=64:raise ValueError('Close completed EDS operations before reviewing another')
            before=observe(client,connection)
            record={'review_id':str(uuid.uuid4()),'session_id':session_id,'state':'reviewed','created_at':time.time(),
                'expires_at':time.time()+300,'source':source,'draft':deepcopy(request['draft']),'expected':expected,
                'native_before':before,'adapter_identity':identity(),'caller_transaction_active_before':connection.main_transaction.is_active(),
                'native_dispatch_admitted':False,'native_acknowledged':False,'automatic_retry':False,
                'caller_transaction_decision_requested':False,'warnings':list(WARNINGS)}
            record['review_digest']=digest(record)
            archive.create(record);records[record['review_id']]={'connection':connection}
            return archive.get(record['review_id'])
        record=archive.get(request['review_id'])
        if record['session_id']!=session_id or request['review_digest']!=record['review_digest']:
            raise ValueError('Select the original native EDS review and session')
        if record['state']!='reviewed':return receipt(record['review_id'])
        if operation=='discard':return archive.update(record['review_id'],state='discarded')
        if request['confirmed'] is not True or request['confirmation']!=record['native_before']['server_process_id']:
            raise ValueError('Confirm the reviewed native engine process shared by EDS attachments')
        if record['expires_at']<time.time() or record['adapter_identity']!=identity():raise ValueError('Native EDS review expired or its adapter changed')
        if compile_operation(record['draft'])!=(record['source'],record['expected']):raise ValueError('Native EDS source differs from its reviewed options')
        current=observe(client,connection)
        if stable(current)!=stable(record['native_before']):raise ValueError('Native EDS identity or settings changed; prepare a new review')
        if not archive.claim(record['review_id'],record['review_digest']):return archive.get(record['review_id'])
        def observed(native,phase):
            payload=native['payload'];error=payload.get('error') or {}
            acknowledged=payload.get('execution_state')=='succeeded' or error.get('native_execution_completed') is True
            changes={'state':'acknowledged' if acknowledged else 'unknown_outcome','native_acknowledged':acknowledged,
                'native_returned_error':bool(error),'native_status_codes':error.get('native_status_codes',[]),
                'native_result_observed_at':time.time(),'automatic_retry':False,'last_native_phase':phase}
            if phase=='session_release':
                changes.update(session_reuse_blocked=bool(payload.get('session_reuse_blocked')),
                    caller_transaction_active_after=connection.main_transaction.is_active())
                if not changes['session_reuse_blocked']:
                    try:
                        after=observe(client,connection);changes['native_after']=after
                        changes['requested_settings_observed']=all(after.get(key)==value for key,value in record['expected'].items()) if record['expected'] else None
                    except BaseException as error:
                        changes['post_observation_error_type']=type(error).__name__
                        changes['session_reuse_blocked']=bool(client._state(connection).result_cleanup_failed)
            archive.update(record['review_id'],**changes)
        try:
            token=client.submit_query(connection,{'source':record['source'],'parameters':[], 'output_policy':{}},observer=observed)
            records[record['review_id']]={'connection':connection,'token':token}
        except BaseException as error:
            archive.update(record['review_id'],dispatch_start_error_type=type(error).__name__,native_status_codes=list(status_codes(error)))
            raise
        return receipt(record['review_id'])
