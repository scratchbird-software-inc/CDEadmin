"""Once-only native logical slot creation through the registered database."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import socket
import time
import uuid

from ..operations.fileio import private_directory
from ..providers.postgresql.continuity import ContinuityError,PhysicalTools
from .postgresql_continuity_slots import name
from .postgresql_logical_stream import option_quoting,require_source

OPERATION='logical_slot_create'


def identity():
    sources=(Path(__file__),Path(__file__).with_name('postgresql_logical_stream.py'),
        Path(__file__).parents[1]/'providers/postgresql/replication_admission.py')
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}


def options(value):
    if not isinstance(value,dict) or set(value)-{'slot','plugin','two_phase','failover','if_not_exists','timeout_seconds'}:
        raise ContinuityError('Select exact native logical slot creation options')
    result={'slot':name(value.get('slot')),'plugin':value.get('plugin','test_decoding'),
        'two_phase':value.get('two_phase',False),'failover':value.get('failover',False),
        'if_not_exists':value.get('if_not_exists',False),'timeout_seconds':value.get('timeout_seconds',30)}
    plugin=result['plugin']
    try:valid=isinstance(plugin,str) and '\x00' not in plugin and 1<=len(plugin.encode('utf8'))<=63
    except UnicodeError:valid=False
    if not valid:raise ContinuityError('Select an exact UTF8 native output plugin identifier of at most63 bytes')
    if any(type(result[key]) is not bool for key in ('two_phase','failover','if_not_exists')):
        raise ContinuityError('Native logical slot flags require booleans')
    timeout=result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise ContinuityError('Select a positive native logical slot deadline or no deadline')
    return result


def arguments(selected,tool):
    plugin=selected['plugin']
    if option_quoting(tool)=='adapter':plugin=plugin.replace('"','""')
    result=['--no-password','--verbose','--create-slot','--slot='+selected['slot'],'--plugin='+plugin]
    for key,argument in (('two_phase','--enable-two-phase'),('failover','--enable-failover'),('if_not_exists','--if-not-exists')):
        if selected[key]:result.append(argument)
    return result


def review(jobs,request,owner,endpoint,source,configuration,paths,runtime_limit):
    if set(request)!={'operation','options'}:raise ContinuityError('Logical slot commands use only the registered replication database')
    selected=options(request['options'])
    if source.get('admission_interface')!='logical-replication':raise ContinuityError('Native logical replication admission is required')
    require_source(source,selected)
    if source.get('server_version')==180003 and '"' in selected['plugin']:
        raise ContinuityError('The pinned PostgreSQL18.3 replication parser cannot represent an embedded double quote in a plugin name; use the native SQL logical-slot workflow')
    if runtime_limit is not None and (type(runtime_limit) is not int or runtime_limit<1 or
            selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit):
        raise ContinuityError('Application policy requires a bounded native logical slot deadline')
    jobs.root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(jobs.root)
    tool=PhysicalTools(paths).identify('pg_recvlogical',jobs.root)
    if tool['available'] is not True:raise ContinuityError('Install native PostgreSQL18 pg_recvlogical on the application host')
    arguments(selected,tool)
    record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
        'operation':OPERATION,'options':selected,'source':deepcopy(source),'paths':deepcopy(paths),
        'tool_identities':{'pg_recvlogical':tool},'client_identity':identity(),'inputs':[],
        'state':'reviewed','created_at':time.time(),'expires_at':time.time()+600,'runtime_limit':runtime_limit,
        'cancel_requested':False,'artifact_wal_method':None,'database_target_id':source['database_target_id'],
        'execution_host':{'kind':'application-host','platform':os.name,'hostname':socket.gethostname()},
        'warnings':[
            'Create a permanent logical replication slot in the registered database. Native slot creation can retain WAL and catalog rows; monitor its storage and consumer separately.',
            'The SQL slot catalog is unobserved. Prior existence, plugin and current identity are unknown. Native utility acknowledgement and current catalog state are separate facts.',
            'If-not-exists accepts an existing slot unchanged, including another type, database or plugin. It does not establish that a new slot was created.',
            'No native snapshot is exported. Native refusal, cancellation, connection loss and transport release do not authorize replay. Temporary slots require their owning backend.']}
    record['artifact_location']=str(jobs.directory(record))
    return jobs.save_review(record)


def run(jobs,record,tools,directory,transport,progress,signal):
    if record.get('client_identity')!=identity():raise ContinuityError('Native logical slot adapter changed after review')
    from ..providers.postgresql.replication_admission import capture
    with transport.parameters() as parameters:
        source,admission=capture(parameters,logical=True)
        try:
            keys=('system_identifier','timeline','server_version','authenticated_principal','database','database_target_id','admission_interface')
            if any(source.get(key)!=record['source'].get(key) for key in keys):
                raise ContinuityError('The reviewed native logical replication peer changed before slot dispatch')
            require_source(source,record['options'])
        finally:admission.close()
        if signal.is_set() or jobs.load(record['job_id'],record['owner'],record['endpoint_id']).get('cancel_requested'):
            jobs.update(record,state='cancelled',native_utility_dispatched=False);return
        jobs.update(record,state='active',phase='native_logical_slot_command',native_utility_dispatched=True)
        result=tools.execute('pg_recvlogical',directory,arguments(record['options'],record['tool_identities']['pg_recvlogical']),
            parameters={**parameters,'client_encoding':'UTF8'},timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
        closed=result['process_observation'].get('cleanup_confirmed') is True
        jobs.update(record,state='completed' if result['return_code']==0 and closed else 'unknown',
            tool_observation=result,native_utility_acknowledged=result['return_code']==0,
            slot_existed_before=None,slot_observation=None,slot_observation_state='unavailable',
            slot_observation_blocker='Logical replication admission does not observe the SQL slot catalog. No SQL connection was opened.',
            finished_at=time.time(),automatic_retry=False,remote_finality_inferred=False)
