"""Durable, owner-scoped native backup jobs, independent of an open viewer."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid

import psutil

from ..operations.fileio import durable_replace, exclusive_file_lock, private_file, private_directory
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError, PhysicalTools, backup_options, backup_arguments, combine_options, combine_arguments, manifest
from ..providers.postgresql.continuity_recovery import recovery_options, independent_copy, recovery_command, read_result
from ..providers.postgresql.continuity_tar import materialize
from ..providers.postgresql import continuity_wal
from ..sdk.tooling import ProviderToolError


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


REVIEW_FIELDS=('job_id','owner','endpoint_id','configuration','operation','options','source','paths',
               'tool_identities','inputs','created_at','expires_at','execution_host','artifact_location','artifact_wal_method','runtime_limit','warnings','wal_archive')


def review_digest(record):
    return fingerprint({key:record.get(key) for key in REVIEW_FIELDS})


def job_identity(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (TypeError,ValueError,AttributeError):
        raise ContinuityError('Invalid backup job identity') from None
    return value


class PostgreSQLContinuityJobs:
    _worker_maps = {}
    _worker_maps_lock = threading.RLock()

    def __init__(self, path, root, archive_root=None):
        self.path, self.root = Path(path), Path(root).resolve()
        self.archive_root = Path(archive_root).resolve() if archive_root else self.root/'wal-archives'
        self.lock = threading.RLock()
        with self._worker_maps_lock:
            self.workers=self._worker_maps.setdefault(str(self.path.resolve()),{})
        self.worker_identity = (os.getpid(), psutil.Process().create_time())

    @contextmanager
    def store(self, job_id):
        job_identity(job_id)
        root=Path(str(self.path)+'.jobs')
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        private_directory(root)
        path=root/(job_id+'.json')
        with self.lock:
            descriptor = os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with exclusive_file_lock(descriptor):yield JsonOperationStore(path)
            finally:os.close(descriptor)

    @staticmethod
    def record(state, job_id, owner, endpoint):
        if type(owner) is not int or owner<=0:raise ContinuityError('Invalid backup owner identity')
        record = state.get('postgresql_continuity_jobs',{}).get(job_id)
        if record is None or record['owner']!=owner or record['endpoint_id']!=endpoint:
            raise ContinuityError('Native backup job is unavailable for this owner and endpoint')
        return record

    @staticmethod
    def public(record, *, summary=False):
        result={**deepcopy({key:value for key,value in record.items() if key not in {'owner','configuration'}}),
                'automatic_retry':False}
        if summary:
            result['source']['tablespace_count']=len(result['source'].pop('tablespaces',[]))
            for name in ('tool_observation','verification_observation','process_observation','input_verifications'):
                result.pop(name,None)
        return result

    def directory(self, record):
        job_id = record['job_id']
        job_identity(job_id)
        if type(record['owner']) is not int or record['owner']<=0 or str(uuid.UUID(record['endpoint_id']))!=record['endpoint_id']:
            raise ContinuityError('Invalid native backup artifact scope')
        return self.root / str(record['owner']) / record['endpoint_id'] / job_id

    def archive_directory(self, owner, endpoint):
        self.directory({'owner':owner,'endpoint_id':endpoint,'job_id':'00000000-0000-0000-0000-000000000000'})
        selected=self.archive_root/str(owner)/endpoint
        for path in (selected.parent,selected):
            if path.is_symlink() or path.resolve()!=path or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
                raise ContinuityError('WAL archive ownership directories cannot contain links or reparse points')
        return selected

    def list(self, owner, endpoint, *, offset=0, limit=25):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise ContinuityError('Invalid native backup receipt page')
        self.directory({'owner':owner,'endpoint_id':endpoint,'job_id':str(uuid.UUID(int=0))})
        index=Path(str(self.path)+'.index')/str(owner)/endpoint
        entries=sorted((entry for entry in index.iterdir() if not entry.name.startswith('.')),reverse=True) if index.is_dir() else []
        result=[];unavailable=[]
        # Static index entries do not change during progress updates. Each job
        # has its own locked receipt, so a long-running tool never rewrites all
        # previous backups' output and plans on every heartbeat.
        for entry in entries[offset:offset+limit]:
            job_id=entry.name.split('_',1)[-1]
            try:
                record=self.load(job_id,owner,endpoint)
                observed=self.observed(record)
                result.append({**self.public(record,summary=True),'state':observed['state'],
                               'observation_blocker':observed.get('observation_blocker')})
            except ContinuityError:unavailable.append(job_id)
        return {'jobs':result,'offset':offset,'limit':limit,'total':len(entries),
                'more':offset+limit<len(entries),'unavailable_job_ids':unavailable}

    def load(self, job_id, owner, endpoint):
        with self.store(job_id) as store:
            return self.record(store.read(),job_id,owner,endpoint)

    def get(self, job_id, owner, endpoint):
        record=self.load(job_id,owner,endpoint)
        return self.observed(record)

    def observed(self, record):
        job_id=record['job_id']
        result = self.public(record)
        active=record['state'] in {'dispatching','active','verifying','verifying_inputs','cancel_requested'}
        pending_slot=record.get('slot_observation_state')=='pending'
        if active or pending_slot:
            pid, created = record.get('worker_identity',(None,None))
            try:alive = pid is not None and psutil.Process(pid).create_time()==created
            except psutil.Error:alive=False
            with self._worker_maps_lock:
                known=self.workers.get(job_id)
                local_alive=known is not None and known[0].is_alive()
            if not alive or (tuple(record.get('worker_identity',()))==self.worker_identity and not local_alive):
                if active:result.update(state='unknown', observation_blocker='The worker stopped before a terminal receipt. Inspect the artifact and process; do not repeat the backup.')
                if pending_slot:result.update(slot_observation_state='unavailable',slot_observation_blocker='The later slot observation is unavailable from this worker; refresh the native slot catalog. The recorded native acknowledgement is unchanged.')
        return result

    def require_stopped_writer(self, record):
        if record['state']=='verified':return
        if self.observed(record)['state'] not in {'unknown','failed','cancelled','captured'}:
            raise ContinuityError('The backup artifact still has an active worker')
        if (record.get('writer_reconciliation') or {}).get('process_scope_stopped') is True:
            candidates,_absent=self.writer_processes(record)
            if not candidates:return
            raise ContinuityError('A reviewed native utility is still using this backup workspace; reconcile its writer again')
        receipt=record.get('tool_observation') or record.get('process_observation') or {}
        observation=receipt.get('process_observation',receipt)
        if observation.get('cleanup_confirmed') is True and observation.get('return_code') is not None:return
        progress=record.get('progress') or {}
        pid,created=progress.get('pid'),progress.get('process_create_time')
        if pid is None or created is None:
            raise ContinuityError('Backup writer termination is unconfirmed; reconcile its native process before verification')
        stopped=False
        try:
            process=psutil.Process(pid)
            stopped=process.create_time()!=created or process.status() in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}
        except psutil.NoSuchProcess:stopped=True
        except psutil.Error:pass
        if stopped:
            candidates,_absent=self.writer_processes(record)
            if not candidates:return
        raise ContinuityError('Backup writer termination is unconfirmed; verification cannot inspect files while they may change')

    def writer_processes(self, record):
        """Inspect only this receipt's workspace and reviewed executable bytes."""
        hostname=(record.get('execution_host') or {}).get('hostname') or (record.get('writer_reconciliation') or {}).get('hostname')
        if hostname is not None and hostname!=socket.gethostname():
            raise ContinuityError('Reconcile the native writer on the application host recorded by this job')
        directory=self.directory(record)
        if (not directory.is_dir() or directory.is_symlink() or directory.resolve()!=directory or
                getattr(directory.lstat(),'st_file_attributes',0)&0x400):
            raise ContinuityError('The native job workspace identity is unavailable')
        allowed={value.get('executable_sha256'):name for name,value in record['tool_identities'].items()
                 if value.get('available') is True and value.get('executable_sha256')}
        if not allowed:raise ContinuityError('The reviewed native utility identities are unavailable')
        progress=record.get('progress') or {}
        observation=record.get('tool_observation') or record.get('process_observation') or {}
        observation=observation.get('process_observation',observation)
        expected_pid=progress.get('pid',observation.get('pid'))
        expected_created=progress.get('process_create_time',observation.get('process_create_time'))
        if (expected_pid is None)!=(expected_created is None):
            raise ContinuityError('Recorded native process creation identity is incomplete')
        candidates={};refusals=[];expected_absent=False
        from ..providers.postgresql.continuity import file_sha256
        for process in psutil.process_iter():
            try:
                created=process.create_time()
                if process.pid==expected_pid and created!=expected_created:
                    expected_absent=True;continue
                if process.status() in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}:
                    if process.pid==expected_pid:expected_absent=True
                    continue
                is_expected=process.pid==expected_pid and created==expected_created
                if Path(process.cwd()).resolve()!=directory:
                    if is_expected:refusals.append('Recorded process no longer belongs to the native job workspace')
                    continue
                if created<float(record.get('started_at',record['created_at']))-1:
                    if is_expected:refusals.append('Recorded process predates this native dispatch')
                    continue
                executable=Path(process.exe())
                if not executable.is_file():
                    if is_expected:refusals.append('Recorded process executable is unavailable')
                    continue
                tool=allowed.get(file_sha256(executable))
                if tool is None:
                    if is_expected:refusals.append('Recorded process does not match a reviewed native utility')
                    continue
                candidates[process.pid]=(process,created,tool)
            except psutil.NoSuchProcess:
                if process.pid==expected_pid:expected_absent=True
            except (psutil.Error,OSError):
                if process.pid==expected_pid:refusals.append('Recorded native process ownership could not be inspected')
        if refusals:raise ContinuityError('; '.join(refusals))
        if expected_pid is not None and expected_pid not in candidates:
            try:
                current=psutil.Process(expected_pid)
                expected_absent=current.create_time()!=expected_created or current.status() in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}
            except psutil.NoSuchProcess:expected_absent=True
            except psutil.Error:raise ContinuityError('Recorded native writer termination is unavailable') from None
            if not expected_absent:raise ContinuityError('The recorded native writer was not admitted for reconciliation')
        if hostname is None and not candidates:
            raise ContinuityError('This legacy receipt has no application-host identity or locally observed owned utility')
        return candidates,expected_absent

    def reconcile_writer(self, request, owner, endpoint):
        """Stop owned utilities without inferring SQL or artifact success."""
        if not isinstance(request,dict) or set(request)!={'job_id','confirmed'} or request['confirmed'] is not True:
            raise ContinuityError('Confirm reconciliation of one owned native job')
        record=self.load(request['job_id'],owner,endpoint)
        if self.observed(record)['state'] not in {'unknown','failed','cancelled'}:
            raise ContinuityError('Cancel an active native job before reconciling its writer')
        with self._worker_maps_lock:known=self.workers.get(record['job_id'])
        if known is not None and known[0].is_alive():
            raise ContinuityError('The local job worker is still stopping; refresh its receipt')
        candidates,expected_absent=self.writer_processes(record)
        if not candidates and (record.get('writer_reconciliation') or {}).get('process_scope_stopped') is True:
            return self.get(record['job_id'],owner,endpoint)
        stopped=[]
        # Each captured Process checks creation identity before signalling. A
        # reused PID is never selected merely because its number was recorded.
        for process,created,tool in candidates.values():
            children=[]
            try:
                if process.create_time()!=created:raise ContinuityError('Native process identity changed during reconciliation')
                from ..providers.postgresql.continuity import file_sha256
                if (Path(process.cwd()).resolve()!=self.directory(record) or
                        file_sha256(Path(process.exe()))!=record['tool_identities'][tool]['executable_sha256']):
                    raise ContinuityError('Native utility workspace or executable changed during reconciliation')
                children=process.children(recursive=True)
                for child in reversed(children):
                    try:child.terminate()
                    except psutil.NoSuchProcess:pass
                try:process.terminate()
                except psutil.NoSuchProcess:pass
                _gone,alive=psutil.wait_procs([*children,process],timeout=3)
                for child in alive:
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
                _gone,alive=psutil.wait_procs(alive,timeout=3)
                if any(item.is_running() and item.status() not in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD} for item in alive):
                    raise ContinuityError('Owned native utility termination is unconfirmed')
                stopped.append({'pid':process.pid,'process_create_time':created,'tool':tool,'termination_confirmed':True})
            except psutil.NoSuchProcess:
                stopped.append({'pid':process.pid,'process_create_time':created,'tool':tool,'termination_confirmed':True,'already_absent':True})
            except (psutil.Error,OSError):
                raise ContinuityError('Owned native utility termination could not be confirmed') from None
        remaining,_absent=self.writer_processes({**record,'writer_reconciliation':{'hostname':socket.gethostname()}})
        if remaining:raise ContinuityError('A reviewed native utility is still using this backup workspace')
        receipt={'process_scope_stopped':True,'processes':stopped,'recorded_process_absent':expected_absent,
                 'hostname':socket.gethostname(),
                 'remote_finality_inferred':False,'artifact_verified':False,'observed_at':time.time(),
                 'scope':'reviewed native utilities in this owner/endpoint job workspace'}
        state=record['state'] if record['state'] in {'unknown','failed','cancelled'} else 'unknown'
        self.update(record,state=state,writer_reconciliation=receipt,automatic_retry=False)
        return self.get(record['job_id'],owner,endpoint)

    def review(self, request, owner, endpoint, source, configuration, paths, *, runtime_limit=None):
        if not isinstance(request,dict) or set(request)-{'operation','options','base_job_id','chain'}:
            raise ContinuityError('Invalid native backup review')
        operation = request.get('operation')
        if operation in {'wal_slot_create','wal_slot_drop'}:
            from .postgresql_continuity_slots import review
            return review(self,request,owner,endpoint,source,configuration,paths,runtime_limit)
        if operation=='wal_capture':
            from .postgresql_continuity_capture import review
            return review(self,request,owner,endpoint,source,configuration,paths,runtime_limit)
        if operation not in {'full_backup','incremental_backup','verify','combine','recovery_drill'}:
            raise ContinuityError('Native continuity operation is unavailable')
        options = (recovery_options if operation=='recovery_drill' else combine_options if operation=='combine' else backup_options)(request.get('options',{}))
        if operation=='recovery_drill' and hasattr(os,'geteuid') and os.geteuid()==0:
            raise ContinuityError('Native PostgreSQL recovery requires an application host account other than root')
        if runtime_limit is not None:
            if type(runtime_limit) is not int or not 1<=runtime_limit<=2147483647:
                raise ContinuityError('Invalid application native-tool runtime policy')
            if options['timeout_seconds'] is None or options['timeout_seconds']>runtime_limit:
                raise ContinuityError('Application policy limits each native utility to '+str(runtime_limit)+' seconds')
        inputs = []
        ids = request.get('chain') if operation=='combine' else [request.get('base_job_id')] if operation in {'incremental_backup','verify','recovery_drill'} else []
        if not isinstance(ids,list) or operation=='combine' and not 2<=len(ids)<=64 or operation in {'incremental_backup','verify','recovery_drill'} and len(ids)!=1:
            raise ContinuityError('Select the native backup inputs')
        for job_id in ids:
            previous=self.load(job_id,owner,endpoint)
            uncertain = operation=='verify' and self.observed(previous)['state'] in {'unknown','failed','cancelled'}
            if not uncertain and (previous['state']!='verified' or not previous.get('manifest')):
                raise ContinuityError('Select verified, manifest-bearing backup artifacts')
            proof=previous.get('manifest')
            if previous['operation']=='verify':previous=self.load(previous['artifact_job_id'],owner,endpoint)
            self.require_stopped_writer(previous)
            if previous['operation'] not in {'full_backup','incremental_backup','combine'}:
                raise ContinuityError('Select a native physical backup artifact')
            if operation=='recovery_drill' and (previous['operation']=='incremental_backup' or previous.get('artifact_wal_method',previous['options'].get('wal_method','stream'))=='none'):
                raise ContinuityError('A recovery drill requires a full or reconstructed backup with locally collected WAL')
            if proof is None:
                if not (self.directory(previous)/'backup/backup_manifest').is_file():
                    raise ContinuityError('Native backup manifest is unavailable')
                # Verification is read-only. An interrupted backup without a
                # manifest receipt is inspected asynchronously by its worker.
                proof={'manifest_sha256':None}
            if previous['source']['system_identifier']!=source['system_identifier']:
                raise ContinuityError('Backup input belongs to another native cluster')
            inputs.append({'job_id':previous['job_id'], 'manifest_sha256':proof['manifest_sha256'],
                           'format':previous['options']['format'], 'operation':previous['operation'],
                           'wal_method':previous.get('artifact_wal_method',previous['options'].get('wal_method','stream')),
                           'manifest_checksums':previous['options']['manifest_checksums'],
                           'tablespaces':deepcopy(previous['source'].get('tablespaces',[]))})
        if operation=='incremental_backup' and source.get('summarize_wal')!='on':
            raise ContinuityError('The selected server must enable native WAL summarization before an incremental backup')
        if operation in {'verify','recovery_drill'}:
            options.update({key:inputs[0][key] for key in (('wal_method','manifest_checksums') if operation=='recovery_drill' else ('format','wal_method','manifest_checksums'))})
        record = {'job_id':str(uuid.uuid4()), 'owner':owner, 'endpoint_id':endpoint, 'configuration':configuration,
            'operation':operation, 'options':options, 'source':deepcopy(source), 'paths':deepcopy(paths),
            'inputs':inputs, 'state':'reviewed', 'created_at':time.time(), 'expires_at':time.time()+600,'runtime_limit':runtime_limit,
            'recovery_drill_complete':False,
            'cancel_requested':False, 'execution_host':{'kind':'application-host','platform':os.name,'hostname':socket.gethostname()},
            'warnings':['Physical backups include the complete native cluster, not only the selected database.',
                'Artifacts are written on the application host. The database server may be on another host.',
                'A utility exit does not establish a usable recovery. Native verification and recovery drills have distinct receipts.']}
        artifact_record=self.load(inputs[0]['job_id'],owner,endpoint) if operation=='verify' else record
        record['artifact_location']={'host':'application-host','path':str(self.directory(artifact_record)/('recovered-clone' if operation=='recovery_drill' else 'backup')),
                                     'format':options['format']}
        if operation=='recovery_drill' and options.get('target') is not None:
            # Existing directory validation also checks owner/endpoint shape.
            self.directory(record)
            record['wal_archive'] = continuity_wal.freeze(self.archive_directory(owner,endpoint), options['wal_archive'])
        record['artifact_wal_method']=inputs[-1]['wal_method'] if operation=='combine' else options['wal_method']
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        private_directory(self.root)
        tools=PhysicalTools(paths)
        needed={'pg_verifybackup'}|({'pg_basebackup'} if operation in {'full_backup','incremental_backup'} else {'pg_combinebackup'} if operation=='combine' else {'postgres'} if operation=='recovery_drill' else set())
        record['tool_identities']={name:tools.identify(name,self.root) for name in sorted(needed)}
        if not all(value['available'] for value in record['tool_identities'].values()):
            raise ContinuityError('Install the selected PostgreSQL 18 native continuity utilities on the application host')
        if operation=='recovery_drill':
            record['warnings'].append('The drill copies the artifact and managed tablespaces into private application-host storage, then runs a standalone native backend without a network listener. It requires the source build dependencies and sufficient space for an independent copy.')
            record['warnings'].append('The drill discards source configuration and recovery commands on its copy. It verifies native recovery and only the selected heap row counts; production restore and extension availability require separate qualification.')
            if options.get('target') is not None:
                record['warnings'].append('The selected owner/endpoint WAL archive is read-only. Reviewed file hashes are checked while staging into the independent copy. PostgreSQL validates the cluster, timeline, WAL records and recovery target; missing continuity or an unreachable target fails the drill. The native recovered copy is promoted on its own timeline without starting a listener.')
        if operation=='combine' and any(item['format']=='tar' for item in inputs):
            record['warnings'].append('TAR chain inputs are copied into private plain-file storage and verified before reconstruction. Keep space for the source archives, materialized inputs and output; intermediate copies remain with this job.')
            record['warnings'].append('The native output can retain a TAR tablespace_map with source-host paths. Recovery preparation must replace or remove that map on an independent copy before startup. The application recovery drill does this.')
        if options.get('create_slot'):record['warnings'].append('This operation creates a persistent native replication slot. A refused or cancelled backup can leave that slot retaining WAL; inspect its native state before changing it.')
        if not options['sync']:record['warnings'].append('Native file synchronization is disabled. Verification does not assert that the files are durable after power loss.')
        if options.get('write_recovery_conf'):record['warnings'].append('PostgreSQL writes replication connection settings, including authentication material, into the protected backup. Host paths and temporary SSH routes must be reviewed before a standby uses these files.')
        if options.get('copy_mode')=='link':record['warnings'].append('Native hard-link reconstruction shares files with its inputs. Starting or modifying this output can modify the original backup artifacts; use an independent copy for a recovery drill.')
        if options['manifest_checksums']=='NONE':record['warnings'].append('The manifest has no file content checksums. Native size and WAL checks have a narrower verification scope.')
        if options.get('wal_method')=='none' or operation=='combine' and inputs[-1]['wal_method']=='none':
            record['warnings'].append('This artifact has no locally collected WAL. Verification checks files only; recovery requires an independently available WAL archive.')
        if any(item['manifest_sha256'] is None for item in inputs):
            record['warnings'].append('This uncertain artifact has no prior manifest receipt. Verification records its current manifest identity and native file checks; it does not resume the interrupted backup.')
        if options['timeout_seconds'] is None:
            record['warnings'].append('No runtime deadline is set. Each native utility continues until it exits or cancellation is requested.')
        return self.save_review(record)

    def save_review(self, record):
        record['review_digest']=review_digest(record)
        self.directory(record)  # Validate the artifact scope before publication.
        index=Path(str(self.path)+'.index')/str(record['owner'])/record['endpoint_id']
        index.mkdir(parents=True,exist_ok=True,mode=0o700)
        private_directory(index)
        index_entry=index/(f'{time.time_ns():020d}_'+record['job_id'])
        with self.store(record['job_id']) as store:
            def save(state):
                jobs = state.setdefault('postgresql_continuity_jobs',{})
                jobs[record['job_id']]=record
            store.change(save)
        staging=index/('.'+index_entry.name)
        descriptor=os.open(staging,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:
            private_file(staging);os.fsync(descriptor)
        finally:os.close(descriptor)
        durable_replace(staging,index_entry)
        return self.public(record)

    def start(self, request, owner, endpoint, source, configuration, transport):
        if not isinstance(request,dict) or set(request)!={'job_id','review_digest','confirmed'} or request['confirmed'] is not True:
            transport.close()
            raise ContinuityError('Explicit confirmation of a native backup review is required')
        signal = threading.Event()
        claimed = False
        worker = None
        try:
            with self.store(request['job_id']) as store:
                def claim(state):
                    nonlocal claimed
                    record = self.record(state,request['job_id'],owner,endpoint)
                    if record['review_digest']!=request['review_digest']:
                        raise ContinuityError('Backup review fingerprint changed')
                    if record['state']!='reviewed':return deepcopy(record)
                    hostname=(record.get('execution_host') or {}).get('hostname')
                    if hostname is not None and hostname!=socket.gethostname():
                        raise ContinuityError('Native utility execution host changed; prepare a review on this application host')
                    if review_digest(record)!=record['review_digest']:
                        raise ContinuityError('Backup review fingerprint changed')
                    stable=lambda value:{key:fact for key,fact in value.items() if key not in {'lsn','slot_snapshot'}}
                    if record['expires_at']<time.time() or record['configuration']!=configuration or stable(record['source'])!=stable(source):
                        raise ContinuityError('Native backup target or registration changed; prepare a new review')
                    record.update(state='dispatching',worker_identity=self.worker_identity,started_at=time.time())
                    claimed=True
                    return deepcopy(record)
                record = store.change(claim)
            if not claimed:
                transport.close()
                return self.get(record['job_id'],owner,endpoint)
            worker = threading.Thread(target=self.run,args=(record,transport,signal),daemon=True,
                                      name='postgresql-continuity-'+record['job_id'])
            with self._worker_maps_lock:self.workers[record['job_id']]=(worker,signal)
            worker.start()
            return self.get(record['job_id'],owner,endpoint)
        except BaseException:
            if worker is None or worker.ident is None:
                transport.close()
                if claimed:self.update(record,state='not_dispatched',error_type='worker_start_failed')
            raise

    def update(self, record, **values):
        def compact(value, name):
            if not isinstance(value,dict):return value
            result=deepcopy(value)
            for stream in ('stdout','stderr'):
                text=result.get(stream)
                if isinstance(text,str) and len(text.encode('utf8'))>8192:
                    filename=name+'-'+stream+'.log'
                    path=self.directory(record)/filename
                    with path.open('wb') as output:
                        private_file(path);output.write(text.encode('utf8'));output.flush();os.fsync(output.fileno())
                    result[stream]=text.encode('utf8')[:8192].decode('utf8',errors='replace')
                    result[stream+'_log']={'file':filename,'sha256':hashlib.sha256(text.encode('utf8')).hexdigest(),
                                          'captured_bytes':len(text.encode('utf8'))}
            return result
        values={key:compact(value,key) for key,value in values.items()}
        with self.store(record['job_id']) as store:
            def save(state):
                current = self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                current.update(deepcopy(values),updated_at=time.time())
            store.change(save)

    def cancel(self, job_id, owner, endpoint):
        with self.store(job_id) as store:
            def change(state):
                record = self.record(state,job_id,owner,endpoint)
                if record['state'] in {'dispatching','active','verifying','verifying_inputs','cancel_requested'}:
                    record.update(cancel_requested=True,state='cancel_requested')
                elif record['state']=='reviewed':record.update(cancel_requested=True,state='cancelled')
            store.change(change)
        with self._worker_maps_lock:
            if job_id in self.workers:self.workers[job_id][1].set()
        return self.get(job_id,owner,endpoint)

    def run(self, record, transport, signal):
        directory = self.directory(record)
        try:
            directory.mkdir(parents=True,exist_ok=False,mode=0o700)
            private_directory(directory)
            tools = PhysicalTools(record['paths'])
            for name,identity in record['tool_identities'].items():
                if tools.identify(name,directory)!=identity:raise ContinuityError('Native utility installation changed after review')
            def progress(event):
                current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
                if current['cancel_requested']:signal.set()
                self.update(record,progress=event)
            if record['operation'] in {'wal_slot_create','wal_slot_drop'}:
                from .postgresql_continuity_slots import run
                return run(self,record,tools,directory,transport,progress,signal)
            if record['operation']=='wal_capture':
                from .postgresql_continuity_capture import run
                return run(self,record,tools,directory,transport,progress,signal)
            next_manifest_progress=0
            def file_progress(event):
                nonlocal next_manifest_progress
                if time.monotonic()<next_manifest_progress:return
                current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
                if current['cancel_requested']:signal.set()
                self.update(record,manifest_progress=event)
                next_manifest_progress=time.monotonic()+.25
            def read_proof(path):
                return manifest(path,progress=file_progress,cancel_signal=signal)
            paths = []
            for item in record['inputs']:
                previous=self.load(item['job_id'],record['owner'],record['endpoint_id'])
                self.require_stopped_writer(previous)
                path=self.directory(previous)/'backup'
                observed=read_proof(path)
                if item['manifest_sha256'] is not None and observed['manifest_sha256']!=item['manifest_sha256']:
                    raise ContinuityError('Native backup input changed after review')
                if item['manifest_sha256'] is None:self.update(record,observed_input_manifest=observed)
                paths.append(path)
            operation=record['operation']; destination=directory/'backup'
            if self.load(record['job_id'],record['owner'],record['endpoint_id'])['cancel_requested']:signal.set()
            if signal.is_set():
                self.update(record,state='cancelled',artifact_complete=False)
                return
            self.update(record,state='active')
            if operation=='recovery_drill':
                self.run_recovery(record,tools,paths[0],progress,file_progress,signal)
                return
            if operation in {'full_backup','incremental_backup'}:
                tablespaces=[(item['location'],directory/'tablespaces'/str(item['oid'])) for item in record['source'].get('tablespaces',[]) if item['location']]
                with transport.parameters() as parameters:
                    result=tools.execute('pg_basebackup',directory,
                        backup_arguments(record['options'],destination,incremental_manifest=paths[0]/'backup_manifest' if paths else None,tablespaces=tablespaces),
                        parameters=parameters,timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
            elif operation=='combine':
                self.update(record,state='verifying_inputs')
                input_receipts=[]
                materializations=[]
                for index,(path,item) in enumerate(zip(paths,record['inputs'])):
                    checked=tools.verify(directory,path,format=item['format'],parse_wal=item['wal_method']!='none',timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
                    if checked['return_code']!=0 or signal.is_set() or checked['process_observation'].get('cleanup_confirmed') is not True:
                        self.update(record,state='cancelled' if signal.is_set() else 'failed',input_verification=checked)
                        return
                    input_receipts.append({'job_id':item['job_id'],'format':item['format'],
                                           'manifest_sha256':read_proof(path)['manifest_sha256'],
                                           'return_code':checked['return_code'],'verification_scope':checked['verification_scope'],
                                           'executable_sha256':checked['executable_sha256']})
                    if item['format']=='tar':
                        plain=directory/'materialized-inputs'/item['job_id']/'backup'
                        previous=self.load(item['job_id'],record['owner'],record['endpoint_id'])
                        copied=materialize(path,plain,item.get('tablespaces',previous['source'].get('tablespaces',[])),item['wal_method'],progress=file_progress,cancel_signal=signal)
                        identity=read_proof(plain)
                        if identity['manifest_sha256']!=item['manifest_sha256'] or identity['system_identifier']!=record['source']['system_identifier']:
                            raise ContinuityError('Materialized chain input differs from the reviewed backup')
                        verified=tools.verify(directory,plain,parse_wal=item['wal_method']!='none',timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
                        receipt={'job_id':item['job_id'],'copy_observation':copied,'verification_observation':verified}
                        materializations.append(receipt)
                        self.update(record,input_materializations=materializations)
                        if verified['return_code']!=0 or signal.is_set() or verified['process_observation'].get('cleanup_confirmed') is not True:
                            self.update(record,state='cancelled' if signal.is_set() else 'failed',artifact_complete=False)
                            return
                        paths[index]=plain
                self.update(record,input_verifications=input_receipts)
                self.update(record,state='active')
                tablespaces=[]
                for item in record['source'].get('tablespaces',[]):
                    if not item['location']:continue
                    link=paths[-1]/'pg_tblspc'/str(item['oid'])
                    original=link.resolve(strict=True)
                    if not original.is_relative_to(paths[-1].parent):
                        raise ContinuityError('Backup tablespace points outside its managed artifact')
                    tablespaces.append((original,directory/'tablespaces'/str(item['oid'])))
                result=tools.execute('pg_combinebackup',directory,combine_arguments(record['options'],destination,paths,tablespaces=tablespaces),
                    timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
            else:
                destination=paths[0]
                self.update(record,artifact_job_id=record['inputs'][0]['job_id'])
                result=tools.verify(directory,destination,format=record['inputs'][0]['format'],
                    parse_wal=record['inputs'][0]['wal_method']!='none',timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
            self.update(record,tool_observation=result)
            if result['return_code']!=0 or result['process_observation'].get('cancel_requested'):
                self.update(record,state='cancelled' if result['process_observation'].get('cancel_requested') else 'failed',
                            artifact_complete=False,remote_finality_inferred=False)
                return
            identity=read_proof(destination)
            if identity['system_identifier']!=record['source']['system_identifier']:
                raise ContinuityError('Native artifact belongs to another cluster')
            if operation!='verify':
                self.update(record,state='verifying')
                result=tools.verify(directory,destination,format=record['options']['format'],
                    parse_wal=(record['inputs'][-1]['wal_method'] if operation=='combine' else record['options']['wal_method'])!='none',
                    timeout=record['options']['timeout_seconds'],progress=progress,cancel_signal=signal)
                self.update(record,verification_observation=result)
                if result['return_code']!=0 or signal.is_set():
                    self.update(record,state='cancelled' if signal.is_set() else 'failed',artifact_complete=False)
                    return
            self.update(record,state='verified',manifest=identity,artifact_complete=True,finished_at=time.time(),
                        verification_scope={**result['verification_scope'],
                            'content_checksums':identity['files_with_checksums']>0,
                            'checksum_algorithms':identity['checksum_algorithms'],
                            'files_with_checksums':identity['files_with_checksums'],
                            'files_without_checksums':identity['files_without_checksums']},recovery_drill_complete=False)
        except ProviderToolError as error:
            self.update(record,state='unknown',error_type=type(error).__name__,
                        process_observation=getattr(error,'process_observation',None),automatic_retry=False)
        except ContinuityError as error:
            # Admission messages contain no native connection strings or SQL.
            self.update(record,state='cancelled' if signal.is_set() else 'failed',error_type=type(error).__name__,error_reason=str(error),automatic_retry=False)
        except Exception as error:
            self.update(record,state='failed',error_type=type(error).__name__,automatic_retry=False)
        finally:
            transport.close()
            with self._worker_maps_lock:self.workers.pop(record['job_id'],None)

    def run_recovery(self, record, tools, source, progress, file_progress, signal):
        directory=self.directory(record);options=record['options'];clone=directory/'recovered-clone'
        def verify(path,field,format='plain'):
            result=tools.verify(directory,path,format=format,timeout=options['timeout_seconds'],progress=progress,cancel_signal=signal)
            self.update(record,**{field:result})
            if signal.is_set() or result['return_code']!=0 or result['process_observation'].get('cleanup_confirmed') is not True:
                raise ContinuityError('Native recovery input verification did not complete')
            return result
        self.update(record,state='verifying_inputs',phase='verifying_recovery_source')
        verify(source,'input_verification',record['inputs'][0]['format'])
        self.update(record,state='active',phase='copying_recovery_artifact')
        if record['inputs'][0]['format']=='tar':
            copied=materialize(source,clone,record['source'].get('tablespaces',[]),options['wal_method'],progress=file_progress,cancel_signal=signal)
        else:copied=independent_copy(source,clone,record['source'].get('tablespaces',[]),progress=file_progress,cancel_signal=signal)
        self.update(record,copy_observation=copied,phase='verifying_recovery_copy')
        verified=verify(clone,'copy_verification')
        # Verification and copied manifest identity precede any clone edits.
        identity=manifest(clone,progress=file_progress,cancel_signal=signal)
        if identity['manifest_sha256']!=record['inputs'][0]['manifest_sha256'] or identity['system_identifier']!=record['source']['system_identifier']:
            raise ContinuityError('Independent recovery copy differs from the reviewed backup')
        if options.get('target') is not None:
            self.update(record,phase='staging_recovery_wal')
            archived = continuity_wal.stage(self.archive_directory(record['owner'],record['endpoint_id']),
                record['wal_archive'],clone,progress=file_progress,cancel_signal=signal)
            self.update(record,wal_archive_observation=archived)
        arguments,sql,output=recovery_command(directory,options,record['job_id'])
        self.update(record,phase='native_recovery')
        result=tools.execute('postgres',directory,arguments,input_bytes=sql,timeout=options['timeout_seconds'],progress=progress,cancel_signal=signal)
        self.update(record,tool_observation=result)
        if signal.is_set() or result['return_code']!=0 or result['process_observation'].get('cleanup_confirmed') is not True:
            raise ContinuityError('Native recovery process did not complete with confirmed termination')
        receipt=read_result(output,options,record['job_id'],record['source']['system_identifier'])
        self.update(record,state='recovered',phase='complete',recovery_observation=receipt,
                    recovery_drill_complete=True,artifact_complete=True,finished_at=time.time(),
                    source_artifact_job_id=record['inputs'][0]['job_id'],
                    verification_scope={**verified['verification_scope'],'independent_copy':True,'selected_heap_counts':len(receipt['checks'])})

    def close(self):
        with self._worker_maps_lock:workers=list(self.workers.values())
        for _worker,signal in workers:signal.set()
        for worker,_signal in workers:worker.join(timeout=5)
