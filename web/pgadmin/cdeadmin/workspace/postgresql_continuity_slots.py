"""Reviewed native physical-slot creation and replication-slot removal."""
from copy import deepcopy
import json
import os
import re
import socket
import time
import uuid

from ..operations.fileio import private_directory
from ..providers.postgresql.continuity import ContinuityError, PhysicalTools

OPERATIONS={'wal_slot_create','wal_slot_drop'}
IDENTITY=('slot_name','slot_type','database','plugin','temporary','two_phase','failover','synced')
SLOT_PROPERTIES="(pg_catalog.to_jsonb(s) || pg_catalog.jsonb_build_object('safe_wal_size',s.safe_wal_size::pg_catalog.text))"


def name(value):
    if not isinstance(value,str) or re.fullmatch(r'[a-z0-9_]{1,63}',value) is None:
        raise ContinuityError('Native replication slot names require 1 to 63 lowercase letters, digits or underscores')
    return value


def observe(transport,slot):
    import psycopg
    from psycopg.rows import tuple_row
    with transport.parameters() as parameters:
        try:
            with psycopg.connect(**{**parameters,'autocommit':True,'connect_timeout':5,'row_factory':tuple_row}) as connection:
                connection.execute('SET statement_timeout = 5000')
                row=connection.execute('SELECT '+SLOT_PROPERTIES+'::pg_catalog.text FROM pg_catalog.pg_replication_slots s WHERE s.slot_name=%s',
                                       (name(slot),)).fetchone()
                return json.loads(row[0]) if row else None
        except psycopg.Error as error:
            raise ContinuityError('Native replication slot observation failed ('+(error.sqlstate or type(error).__name__)+')') from None


def enrich(source,transport,slot):
    observed=observe(transport,slot)
    return {**source,'slot_snapshot':observed,
            'slot_identity':None if observed is None else {key:observed.get(key) for key in IDENTITY}}


def catalog(source,transport,request):
    import psycopg
    from psycopg.rows import tuple_row
    if set(request)-{'offset','limit'}:raise ContinuityError('Invalid native replication slot page')
    offset,limit=request.get('offset',0),request.get('limit',25)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ContinuityError('Select a bounded native replication slot page')
    query=('WITH native_slots AS MATERIALIZED (SELECT s.slot_name,'+SLOT_PROPERTIES+' AS properties '
        'FROM pg_catalog.pg_replication_slots s) SELECT (SELECT pg_catalog.count(*) FROM native_slots),'
        "COALESCE((SELECT pg_catalog.jsonb_agg(properties ORDER BY slot_name) FROM "
        "(SELECT slot_name,properties FROM native_slots ORDER BY slot_name LIMIT %s OFFSET %s) visible),'[]'::pg_catalog.jsonb)::pg_catalog.text")
    with transport.parameters() as parameters:
        try:
            with psycopg.connect(**{**parameters,'autocommit':True,'connect_timeout':5,'row_factory':tuple_row}) as connection:
                connection.execute('SET statement_timeout = 5000')
                total,rows=connection.execute(query,(limit,offset)).fetchone()
        except psycopg.Error as error:
            raise ContinuityError('Native replication slot catalog failed ('+(error.sqlstate or type(error).__name__)+')') from None
    return {'slots':json.loads(rows),'total':int(total),'offset':offset,'limit':limit,'more':offset+limit<int(total),
            'source':source,'coverage':'native pg_replication_slots observation; one materialized catalog page'}


def options(operation,value):
    if operation not in OPERATIONS:raise ContinuityError('Native replication slot operation is unavailable')
    if not isinstance(value,dict) or set(value)-{'slot','if_not_exists','timeout_seconds'}:
        raise ContinuityError('Invalid native replication slot options')
    result={'slot':name(value.get('slot')),'if_not_exists':value.get('if_not_exists',False),'timeout_seconds':value.get('timeout_seconds',30)}
    if type(result['if_not_exists']) is not bool or operation=='wal_slot_drop' and result['if_not_exists']:
        raise ContinuityError('Native if-not-exists applies only to slot creation')
    timeout=result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise ContinuityError('Slot utility timeout requires a positive duration or no deadline')
    return result


def review(jobs,request,owner,endpoint,source,configuration,paths,runtime_limit):
    if set(request)-{'operation','options'}:raise ContinuityError('Invalid native replication slot review')
    operation=request['operation'];selected=options(operation,request.get('options',{}))
    if runtime_limit is not None and (type(runtime_limit) is not int or runtime_limit<1 or
            selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit):
        raise ContinuityError('Application runtime policy requires a bounded native slot utility duration')
    if source.get('slot_snapshot') is not None and source['slot_snapshot'].get('slot_name')!=selected['slot']:
        raise ContinuityError('Native slot observation does not match the reviewed name')
    jobs.root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(jobs.root)
    identity=PhysicalTools(paths).identify('pg_receivewal',jobs.root)
    if identity['available'] is not True:raise ContinuityError('Install PostgreSQL 18 pg_receivewal on the application host')
    record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
            'operation':operation,'options':selected,'source':deepcopy(source),'paths':deepcopy(paths),
            'tool_identities':{'pg_receivewal':identity},'inputs':[],'state':'reviewed','created_at':time.time(),
            'expires_at':time.time()+600,'runtime_limit':runtime_limit,'cancel_requested':False,
            'execution_host':{'kind':'application-host','platform':os.name,'hostname':socket.gethostname()},
            'artifact_wal_method':None,'warnings':[
                'Native replication-slot commands run on the selected cluster through the application host. The native slot name identifies the object; PostgreSQL governs concurrent use.',
                'Native utility acknowledgement and current catalog observations are separate facts. An interrupted utility is never automatically repeated and local process cleanup does not establish its remote outcome.']}
    record['artifact_location']=str(jobs.directory(record))
    if operation=='wal_slot_create':
        record['warnings'].append('This creates a permanent physical replication slot. Native WAL reservation starts when a receiver attaches; retained WAL can consume server storage while that receiver is stopped.')
        if selected['if_not_exists']:record['warnings'].append('Native if-not-exists accepts an existing slot unchanged, including another slot type. The receipt reports the observed type and does not claim a new physical slot was created.')
    else:record['warnings'].append('Dropping a slot removes its retained replication position. PostgreSQL refuses an active slot; no session is terminated automatically. Receivers may require a new base backup after the slot is removed.')
    return jobs.save_review(record)


def run(jobs,record,tools,directory,transport,progress,signal):
    selected=record['options'];operation=record['operation']
    arguments=['--no-password','--verbose','--slot='+selected['slot'],
               '--create-slot' if operation=='wal_slot_create' else '--drop-slot']
    if selected['if_not_exists']:arguments.append('--if-not-exists')
    jobs.update(record,state='active',phase='native_replication_slot_command')
    with transport.parameters() as parameters:
        result=tools.execute('pg_receivewal',directory,arguments,parameters=parameters,
            timeout=selected['timeout_seconds'],progress=progress,cancel_signal=signal)
    jobs.update(record,tool_observation=result)
    observation=result['process_observation']
    if observation.get('cleanup_confirmed') is not True:state='unknown'
    elif result['return_code']==0:state='completed'
    else:state='unknown'
    jobs.update(record,state=state,finished_at=time.time(),remote_finality_inferred=False,
                native_utility_acknowledged=state=='completed',slot_observation_state='pending',automatic_retry=False,
                slot_existed_before=record['source'].get('slot_snapshot') is not None)
    after=None;blocker=None
    try:after=observe(transport,selected['slot'])
    except ContinuityError as error:blocker=str(error)
    except Exception as error:blocker='Current native slot observation is unavailable ('+type(error).__name__+')'
    jobs.update(record,slot_observation=after,slot_observation_state='unavailable' if blocker else 'observed',
                slot_observation_blocker=blocker,slot_observed_at=time.time())
