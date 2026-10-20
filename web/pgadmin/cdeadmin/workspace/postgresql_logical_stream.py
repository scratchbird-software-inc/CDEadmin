"""Owned pg_recvlogical streams with separate native-return and file receipts."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import socket
import time
import uuid

from ..operations.fileio import private_file,private_directory
from ..providers.postgresql import large_object_files as private_sql
from ..providers.postgresql.continuity import ContinuityError,PhysicalTools
from . import postgresql_continuity_slot_sql as slots
from . import postgresql_slot_changes as files

OPERATION='logical_stream_capture'
FILENAME='logical-stream.native'


def options(value):
    defaults={'slot':'','start_lsn':'0/0','end_lsn':'','plugin_options':[],
              'status_interval_seconds':10,'fsync_interval_seconds':1,'timeout_seconds':None}
    if not isinstance(value,dict) or set(value)-defaults.keys():raise ContinuityError('Select exact native logical receiver options')
    result={**defaults,**value}
    selected=files.options({'slot':result['slot'],'plugin_options':result['plugin_options']})
    result['slot']=selected['slot'];result['plugin_options']=selected['plugin_options']
    if any('=' in pair['name'] for pair in result['plugin_options']):
        raise ContinuityError('The native pg_recvlogical option-name syntax cannot represent equals signs')
    for key in ('start_lsn','end_lsn'):
        value=result[key]
        if key=='end_lsn' and value=='':continue
        if not isinstance(value,str) or re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}',value) is None:
            raise ContinuityError('Select an exact native logical receiver WAL position')
        result[key]=value.upper()
    for key in ('status_interval_seconds','fsync_interval_seconds'):
        if type(result[key]) is not int or not 0<=result[key]<=2147483:raise ContinuityError('Select a native receiver interval from 0 to 2147483 seconds')
    if result['timeout_seconds'] is not None and (type(result['timeout_seconds']) is not int or not 1<=result['timeout_seconds']<=2147483647):
        raise ContinuityError('Select a positive receiver deadline or no deadline')
    return result


def client_identity():
    return {**slots.client_identity(),'logical_receiver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def option_quoting(identity):
    # PostgreSQL18.3/18.4 interpolate options;18.6 quotes them internally.
    # Keep unknown client revisions outside this quoting boundary.
    version=re.fullmatch(r'\(PostgreSQL\) 18\.(\d+)',identity.get('version') or '')
    if version is None:raise ContinuityError('The logical receiver option quoting revision is unavailable')
    minor=int(version[1])
    if minor<=4:return 'adapter'
    if minor>=6:return 'utility'
    raise ContinuityError('This native logical receiver option quoting revision requires qualification')


def require_source(source,selected):
    if source.get('admission_interface')=='logical-replication':
        database=source.get('database')
        if (source.get('sql_admission_performed') is not False or source.get('slot_catalog_observed') is not False or
                any(source.get(key) is not None for key in ('sql_identity','slot_snapshot','slot_identity')) or
                not isinstance(database,str) or not database or not source.get('authenticated_principal') or
                source.get('database_target_id')!='postgresql-replication-database:'+database.encode('utf8').hex()):
            raise ContinuityError('Logical replication admission cannot claim unobserved SQL database or slot facts')
        return
    native=source.get('slot_snapshot') or {};identity=source.get('sql_identity') or {}
    if native.get('slot_type')!='logical' or native.get('temporary') is not False or native.get('database')!=identity.get('database'):
        raise ContinuityError('Select an existing permanent logical slot in this database; temporary slots require their owning protocol backend')
    if native.get('active') is True:raise ContinuityError('The native logical slot already has an active consumer')
    if identity.get('effective_principal')!=identity.get('authenticated_principal'):
        raise ContinuityError('The native receiver authenticates directly; select a registration for the reviewed effective principal')
    if native.get('slot_name')!=selected['slot']:raise ContinuityError('The native logical slot identity changed')


def bind_source(source):
    return {**source,'logical_stream_confirmed_lsn':(source.get('slot_snapshot') or {}).get('confirmed_flush_lsn')}


def review(jobs,request,owner,endpoint,source,configuration,paths,runtime_limit):
    if set(request)!={'operation','options','database_target_id'}:raise ContinuityError('Select one explicit database and native logical stream')
    selected=options(request['options']);require_source(source,selected)
    if source.get('admission_interface')=='logical-replication' and request['database_target_id']!=source['database_target_id']:
        raise ContinuityError('The native logical stream belongs to another registered database')
    if runtime_limit is not None and (type(runtime_limit) is not int or runtime_limit<1 or selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit):
        raise ContinuityError('Application policy requires a bounded logical receiver duration')
    jobs.root.mkdir(parents=True,exist_ok=True,mode=0o700)
    private_directory(jobs.root)
    tool=PhysicalTools(paths).identify('pg_recvlogical',jobs.root)
    if not tool['available']:raise ContinuityError('Install native PostgreSQL18 pg_recvlogical on the application host')
    option_quoting(tool)
    record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
            'operation':OPERATION,'options':selected,'database_target_id':request['database_target_id'],
            'source':deepcopy(bind_source(source)),'paths':deepcopy(paths),'inputs':[],'tool_identities':{'pg_recvlogical':tool},
            'client_identity':client_identity(),'state':'reviewed','created_at':time.time(),'expires_at':time.time()+600,
            'runtime_limit':runtime_limit,'cancel_requested':False,'artifact_wal_method':None,
            'execution_host':{'kind':'application-host','hostname':socket.gethostname(),'platform':os.name},
            'warnings':[
                'The native logical receiver consumes this permanent slot and sends native write/flush feedback. Native consumption, utility return and captured bytes are separate facts.',
                'The receiver runs once with no reconnect loop. Lost results and interrupted streams are never restarted or replayed automatically.',
                'Native plugin payloads are written with pg_recvlogical newline delimiters. This is the native utility file format, not a framed replication-message or transaction archive.',
                'The independent receiver uses UTF8 client encoding for native plugin options and output. User query connections and pending SQL stay separate.',
                'Output remains on the application host. A checksummed file does not prove remote slot finality, transaction completeness, applied replication or recoverability.']}
    if selected['fsync_interval_seconds']==0:record['warnings'].append('Native file synchronization is disabled. Native flush feedback does not establish power-loss durability.')
    if source.get('admission_interface')=='logical-replication':
        record['warnings'].append('Replication-only admission identifies the registered database and native principal without SQL. The selected slot name governs dispatch; prior existence, plugin, temporary status, active consumer and flush position are unobserved. The native receiver may refuse the slot. Concurrent replacement or consumption is not detected by catalog preflight. Temporary slots require their owning backend.')
    record['artifact_location']=str(jobs.directory(record)/FILENAME)
    return jobs.save_review(record)


def arguments(selected,path,*,quoting):
    result=['--start','--no-loop','--no-password','--verbose','--slot='+selected['slot'],
            '--file='+str(path),'--startpos='+selected['start_lsn'],
            '--status-interval='+str(selected['status_interval_seconds']),
            '--fsync-interval='+str(selected['fsync_interval_seconds'])]
    if selected['end_lsn']:result.append('--endpos='+selected['end_lsn'])
    for pair in selected['plugin_options']:
        # pg_recvlogical embeds these in quoted protocol option literals.
        # Its native argument parser splits only the first equals sign.
        name,value=pair['name'],pair['value']
        if quoting=='adapter':name=name.replace('"','""');value=value.replace("'","''")
        elif quoting!='utility':raise ContinuityError('The native option quoting mode is unavailable')
        result.append('--option='+name+'='+value)
    return result


def run(jobs,record,tools,directory,transport,progress,signal):
    if client_identity()!=record['client_identity']:raise ContinuityError('The native logical receiver adapter changed after review')
    selected=record['options'];path=directory/FILENAME
    with transport.parameters() as parameters:
        if record['source'].get('admission_interface')=='logical-replication':
            from ..providers.postgresql.replication_admission import capture
            observed,admission=capture(parameters,logical=True)
            try:
                keys=('system_identifier','timeline','server_version','authenticated_principal','database','database_target_id','admission_interface')
                if any(observed.get(key)!=record['source'].get(key) for key in keys):
                    raise ContinuityError('The reviewed native logical replication peer changed before receiver dispatch')
                require_source(observed,selected)
            finally:admission.close()
        else:
            connection=private_sql.attach(parameters,record['source']['sql_identity'])
            try:
                with private_sql.cursor(connection) as query:query.execute('SET statement_timeout=5000')
                observed=slots.enrich(record['source']['sql_identity'],connection,selected);require_source(observed,selected)
                if observed['slot_identity']!=record['source']['slot_identity']:raise ContinuityError('The reviewed native slot changed before receiver dispatch')
                if bind_source(observed)['logical_stream_confirmed_lsn']!=record['source']['logical_stream_confirmed_lsn']:
                    raise ContinuityError('The reviewed native slot consumption position changed before receiver dispatch')
            finally:connection.close()
        current=jobs.load(record['job_id'],record['owner'],record['endpoint_id'])
        if signal.is_set() or current.get('cancel_requested'):
            jobs.update(record,state='cancelled',sql_dispatched=False,worker_io_closed=True);return
        # Reserve exactly this new owned file; the utility's native append mode
        # can never adopt an earlier stream or a caller-supplied pathname.
        with path.open('xb') as output:private_file(path)
        def tick(event):
            try:progress({**event,'captured_bytes':str(path.stat().st_size)})
            except BaseException:signal.set();raise
        native_parameters={**parameters,'application_name':'ScratchRobin logical '+record['job_id'],
                           'client_encoding':'UTF8'}
        jobs.update(record,state='active',phase='native_logical_replication_stream',native_receiver_dispatch_admitted=True)
        result=tools.execute('pg_recvlogical',directory,arguments(selected,path,quoting=option_quoting(record['tool_identities']['pg_recvlogical'])),parameters=native_parameters,
                             timeout=selected['timeout_seconds'],progress=tick,cancel_signal=signal)
        observed=result['process_observation'];closed=observed.get('cleanup_confirmed') is True
        state='unknown' if not closed else 'cancelled' if observed.get('cancel_requested') or signal.is_set() else 'failed' if result['return_code']!=0 else 'captured'
        jobs.update(record,state=state,tool_observation=result,native_receiver_returned=result['return_code']==0,
                    worker_io_closed=closed,phase='logical_receiver_stopped',finished_at=time.time(),
                    logical_stream_artifact={'state':'sealing' if closed else 'unavailable','writer_closed':closed},
                    remote_finality_inferred=False,automatic_retry=False)
    if closed:
        try:reconcile(jobs,jobs.load(record['job_id'],record['owner'],record['endpoint_id']))
        except (OSError,ContinuityError):jobs.update(record,logical_stream_artifact={'state':'unavailable','writer_closed':True})


def reconcile(jobs,record):
    if record.get('operation')!=OPERATION:raise ContinuityError('Select an owned native logical stream')
    with files.artifact_lock(jobs,record) as current:
        jobs.require_stopped_writer(current)
        path=jobs.directory(current)/FILENAME;checksum=hashlib.sha256();length=0
        with files.regular_file(path,writable=True) as source:
            before=files.file_identity(os.fstat(source.fileno()))
            prior=current.get('logical_stream_artifact') or {}
            if prior.get('state')=='sealed' and before!=prior['file_identity']:
                raise ContinuityError('Previously sealed native logical output changed; its checksum cannot be replaced')
            while block:=source.read(1048576):checksum.update(block);length+=len(block)
            os.fsync(source.fileno())
            if before!=files.file_identity(os.fstat(source.fileno())):raise ContinuityError('Native logical output changed while sealing')
            if prior.get('state')=='sealed' and checksum.hexdigest()!=prior['sha256']:
                raise ContinuityError('Previously sealed native logical output checksum changed')
        artifact={'state':'sealed','filename':FILENAME,'bytes':str(length),'sha256':checksum.hexdigest(),
                  'file_identity':before,'writer_closed':True,'native_receiver_returned':current.get('native_receiver_returned') is True,
                  'format':'pg_recvlogical native payloads with newline delimiters','transaction_completeness_inferred':False}
        jobs.update(current,logical_stream_artifact=artifact)
    return jobs.get(record['job_id'],record['owner'],record['endpoint_id'])


@contextmanager
def payload(jobs,record):
    artifact=record.get('logical_stream_artifact') or {}
    if record.get('operation')!=OPERATION or artifact.get('state')!='sealed' or artifact.get('filename')!=FILENAME or artifact.get('writer_closed') is not True:
        raise ContinuityError('Select sealed native logical output from a stopped receiver')
    with files.regular_file(jobs.directory(record)/FILENAME) as source:
        if files.file_identity(os.fstat(source.fileno()))!=artifact['file_identity']:raise ContinuityError('The sealed native logical output changed')
        yield source


def preview(jobs,record,request):
    import base64
    if set(request)-{'job_id','offset','limit'}:raise ContinuityError('Select a bounded native logical byte preview')
    offset=request.get('offset','0');limit=request.get('limit',4096)
    if (not isinstance(offset,str) or not offset.isascii() or not offset.isdecimal() or len(offset)>19 or
            offset!=str(int(offset)) or type(limit) is not int or not 1<=limit<=65536):
        raise ContinuityError('Select an exact byte offset and preview length from 1 to 65536')
    with payload(jobs,record) as source:
        before=files.file_identity(os.fstat(source.fileno()));start=int(offset)
        if start>before[2]:raise ContinuityError('Native logical preview offset is beyond the captured file')
        source.seek(start);data=source.read(limit);end=source.tell()
        if before!=files.file_identity(os.fstat(source.fileno())):raise ContinuityError('Native logical bytes changed during preview')
    try:text=data.decode('utf8')
    except UnicodeError:text=None
    return {'offset':offset,'bytes':len(data),'data_base64':base64.b64encode(data).decode('ascii'),
            'utf8_preview':text,'next_offset':str(end) if end<before[2] else None,
            'transaction_completeness_inferred':False,'format':record['logical_stream_artifact']['format']}
