"""Owner/endpoint bound archive jobs with durable, non-replaying receipts."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import threading
import time
import uuid

import psutil

from ..operations.fileio import durable_replace,exclusive_file_lock,private_directory,private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError,verify

ACTIVE={'dispatching','active','cancel_requested'}
FIELDS=('job_id','owner','endpoint_id','configuration','options','source','source_state','program','continuation','created_at','expires_at')


def identity(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (TypeError,ValueError,AttributeError):raise BinlogArchiveError('Invalid native archive identity') from None
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')).hexdigest()


def review_digest(record):return digest({key:record.get(key) for key in FIELDS})


class DurableCancellation:
    """Observe cancellation admitted by another application worker."""
    def __init__(self,jobs,record,signal):
        self.jobs,self.record,self.signal=jobs,record,signal;self.next_check=0

    def is_set(self):
        if not self.signal.is_set() and time.monotonic()>=self.next_check:
            self.next_check=time.monotonic()+.25
            current=self.jobs.load(self.record['job_id'],self.record['owner'],self.record['endpoint_id'])
            if current.get('cancel_requested'):self.signal.set()
        return self.signal.is_set()

    def wait(self,timeout=None):
        deadline=None if timeout is None else time.monotonic()+max(0,timeout)
        while not self.is_set():
            remaining=None if deadline is None else deadline-time.monotonic()
            if remaining is not None and remaining<=0:return False
            self.signal.wait(.25 if remaining is None else min(.25,remaining))
        return True


class MySQLBinlogJobs:
    _maps={};_maps_lock=threading.RLock()

    def __init__(self,path,root):
        self.path,self.root=Path(path),Path(root).resolve();self.lock=threading.RLock()
        self.worker_identity=[os.getpid(),psutil.Process().create_time()]
        with self._maps_lock:self.workers=self._maps.setdefault(str(self.path.resolve()),{})

    def scope(self,owner,endpoint):
        if type(owner) is not int or owner<=0:raise BinlogArchiveError('Invalid native archive owner')
        return self.root/str(owner)/identity(endpoint)

    def directory(self,record):return self.scope(record['owner'],record['endpoint_id'])/identity(record['job_id'])

    def prepare_scope(self,owner,endpoint):
        scope=self.scope(owner,endpoint)
        for path in (self.root,self.root/str(owner),scope,scope/'index'):
            path.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(path)
        return scope

    @contextmanager
    def store(self,job_id):
        root=Path(str(self.path)+'.jobs');root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(root)
        path=root/(identity(job_id)+'.json')
        with self.lock:
            descriptor=os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with exclusive_file_lock(descriptor):yield JsonOperationStore(path)
            finally:os.close(descriptor)

    @staticmethod
    def record(state,job_id,owner,endpoint):
        record=state.get('mysql_binlog_jobs',{}).get(job_id)
        if record is None or type(owner) is not int or record['owner']!=owner or record['endpoint_id']!=endpoint:
            raise BinlogArchiveError('Native archive is unavailable for this owner and endpoint')
        return record

    def load(self,job_id,owner,endpoint):
        self.scope(owner,endpoint)
        with self.store(job_id) as store:return self.record(store.read(),job_id,owner,endpoint)

    def public(self,record):
        result=deepcopy({key:value for key,value in record.items() if key not in {'owner','configuration','source_state'}})
        result['automatic_retry']=False
        artifact=result.get('result',{}).get('artifact')
        if artifact is not None:
            artifact.pop('files',None);checks=artifact.pop('event_integrity',[])
            artifact['native_log_count']=len(checks)
            artifact['total_bytes']=str(artifact['total_bytes'])
            for key in ('start_from','end_at'):
                if isinstance(artifact.get(key),dict) and 'position' in artifact[key]:
                    artifact[key]['position']=str(artifact[key]['position'])
        if record['state'] in ACTIVE:
            with self._maps_lock:known=self.workers.get(record['job_id'])
            pid,created=record.get('worker_identity',(None,None))
            try:alive=pid is not None and psutil.Process(pid).create_time()==created
            except psutil.Error:alive=False
            if not alive or record.get('worker_identity')==self.worker_identity and not (known and known[0].is_alive()):
                result.update(state='unknown',native_process_termination_confirmed=False)
        return result

    def get(self,job_id,owner,endpoint):return self.public(self.load(job_id,owner,endpoint))

    def update(self,record,**values):
        with self.store(record['job_id']) as store:
            def change(state):
                current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                current.update(deepcopy(values),updated_at=time.time())
            store.change(change)

    def list(self,owner,endpoint,offset=0,limit=25):
        scope=self.scope(owner,endpoint)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise BinlogArchiveError('Invalid native archive page')
        entries=sorted((scope/'index').iterdir(),reverse=True) if (scope/'index').is_dir() else []
        jobs=[];unavailable=[]
        for entry in entries[offset:offset+limit]:
            if entry.name.startswith('.'):continue
            job_id=entry.name.split('_',1)[-1]
            try:jobs.append(self.get(job_id,owner,endpoint))
            except BinlogArchiveError:unavailable.append(job_id)
        return {'jobs':jobs,'offset':offset,'limit':limit,'total':len(entries),'more':offset+limit<len(entries),'unavailable_job_ids':unavailable}

    def review(self,owner,endpoint,selected,capture,configuration,program,continuation=None):
        scope=self.prepare_scope(owner,endpoint)
        record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
            'operation':'mysql_binary_log_dump','options':deepcopy(selected),'source':deepcopy(capture['identity']),
            'source_state':deepcopy(capture['state']),'program':deepcopy(program),'continuation':deepcopy(continuation),
            'created_at':time.time(),'expires_at':time.time()+600,'state':'reviewed','cancel_requested':False,
            'execution_host':{**program['execution_host'],'filesystem_scope':str(scope)},'remote_database_mutation':False,
            'warnings':['Binary-log archives include changes from the whole server and require private storage.',
                'The native utility records the execution snapshot. Archive completion and successful database recovery have separate receipts.']}
        record['review_digest']=review_digest(record)
        directory=self.directory(record);directory.mkdir(mode=0o700);private_directory(directory)
        with self.store(record['job_id']) as store:
            store.change(lambda state:state.setdefault('mysql_binlog_jobs',{}).update({record['job_id']:record}))
        entry=scope/'index'/(f'{time.time_ns():020d}_'+record['job_id']);temporary=entry.with_name('.'+entry.name)
        with temporary.open('xb') as stream:private_file(temporary);stream.flush();os.fsync(stream.fileno())
        durable_replace(temporary,entry)
        return self.public(record)

    def start(self,request,owner,endpoint,current,transport):
        claimed=False;worker=None;signal=threading.Event()
        try:
            if not isinstance(request,dict) or set(request)!={'job_id','review_digest','confirmed'} or request['confirmed'] is not True:
                raise BinlogArchiveError('Confirm the exact native archive review')
            self.scope(owner,endpoint)
            with self.store(request['job_id']) as store:
                def claim(state):
                    nonlocal claimed
                    record=self.record(state,request['job_id'],owner,endpoint)
                    if record['review_digest']!=request['review_digest'] or review_digest(record)!=record['review_digest']:
                        raise BinlogArchiveError('Native archive review changed')
                    if record['state']!='reviewed':return deepcopy(record)
                    if transport is None or time.time()>record['expires_at'] or any(record[key]!=current[key] for key in ('configuration','source','program')):
                        raise BinlogArchiveError('Native archive target, executable or registration changed; prepare a new review')
                    record.update(state='dispatching',worker_identity=self.worker_identity,started_at=time.time())
                    claimed=True;return deepcopy(record)
                record=store.change(claim)
            if not claimed:
                if transport is not None:transport.close()
                return self.get(record['job_id'],owner,endpoint)
            worker=threading.Thread(target=self.run,args=(record,transport,signal),daemon=True,name='mysql-binlog-'+record['job_id'])
            with self._maps_lock:self.workers[record['job_id']]=(worker,signal)
            worker.start();return self.get(record['job_id'],owner,endpoint)
        except BaseException:
            if worker is None or worker.ident is None:
                if transport is not None:transport.close()
                if claimed:
                    self.update(record,state='not_dispatched',error_type='worker_start_failed')
                    with self._maps_lock:
                        known=self.workers.get(record['job_id'])
                        if known and known[0] is worker:self.workers.pop(record['job_id'],None)
            raise

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal)
        try:
            self.update(record,state='active')
            def progress(value):self.update(record,progress=value)
            result=transport.execute(record,self.directory(record),cancel,progress)
            self.update(record,state='completed' if result.get('artifact') is not None else 'no_new_snapshot',
                result=result,finished_at=time.time(),native_process_termination_confirmed=True)
        except BaseException as error:
            from ..providers.mysql_family.mysql_binlog_integrity import BinlogIntegrityError
            observed=getattr(error,'observation',None) or getattr(error,'process_observation',None)
            if isinstance(observed,dict):observed={key:value for key,value in observed.items() if key not in {'stdout','stderr'}}
            process=(observed or {}).get('process_observation',{})
            unknown=process.get('cleanup_confirmed') is False
            self.update(record,state='unknown' if unknown else 'cancelled' if signal.is_set() or isinstance(error,InterruptedError) else 'failed',
                error_type=type(error).__name__,tool_observation=observed,finished_at=time.time(),
                error_message=str(error) if isinstance(error,(BinlogArchiveError,BinlogIntegrityError)) else None,
                native_process_termination_confirmed=process.get('cleanup_confirmed'))
        finally:
            try:transport.close()
            finally:
                with self._maps_lock:
                    entry=self.workers.get(record['job_id'])
                    if entry and entry[0] is threading.current_thread():self.workers.pop(record['job_id'],None)

    def cancel(self,job_id,owner,endpoint):
        self.scope(owner,endpoint)
        with self.store(job_id) as store:
            def change(state):
                record=self.record(state,job_id,owner,endpoint)
                if record['state'] in ACTIVE:record.update(state='cancel_requested',cancel_requested=True)
                elif record['state']=='reviewed':record.update(state='cancelled',cancel_requested=True)
            store.change(change)
        with self._maps_lock:
            known=self.workers.get(job_id)
            if known:known[1].set()
        return self.get(job_id,owner,endpoint)

    def reconcile(self,job_id,owner,endpoint):
        record=self.load(job_id,owner,endpoint)
        with self._maps_lock:
            known=self.workers.get(job_id)
            if known and known[0].is_alive():raise BinlogArchiveError('The archive worker is still active')
        result=verify(self.directory(record)/'archive',record['source'])
        sealed=record.get('result',{}).get('artifact')
        if sealed is not None and digest(result)!=digest(sealed):
            raise BinlogArchiveError('Native archive differs from its durable verification receipt')
        self.update(record,state='artifact_verified',result={**record.get('result',{}),'artifact':result},
            native_process_termination_confirmed=record.get('native_process_termination_confirmed') is True,
            artifact_reconciled_at=time.time())
        return self.get(job_id,owner,endpoint)

    def files(self,job_id,owner,endpoint,offset=0,limit=100):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=200:
            raise BinlogArchiveError('Invalid native archive file page')
        record=self.load(job_id,owner,endpoint);files=(record.get('result',{}).get('artifact') or {}).get('files',[])
        return {'files':[{**row,'size':str(row['size'])} for row in files[offset:offset+limit]],'offset':offset,'limit':limit,
            'total':len(files),'more':offset+limit<len(files),'artifact_removed':bool(record.get('artifact_removed'))}

    @contextmanager
    def download(self,job_id,owner,endpoint,relative):
        record=self.load(job_id,owner,endpoint)
        if record.get('artifact_removed') or record['state'] not in {'completed','artifact_verified'}:
            raise BinlogArchiveError('Select a retained, verified native archive')
        artifact=(record.get('result') or {}).get('artifact') or {}
        selected=next((row for row in artifact.get('files',[]) if row['path']==relative),None)
        if selected is None:raise BinlogArchiveError('Select an exact verified archive file')
        path=self.directory(record)/'archive'
        parts=Path(relative).parts
        if not parts or Path(relative).is_absolute() or '..' in parts:raise BinlogArchiveError('Invalid archive file identity')
        for part in ('',*parts[:-1]):
            if part:path=path/part
            info=path.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise BinlogArchiveError('Archive directory identity changed')
        descriptor=os.open(path/parts[-1],os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or getattr(before,'st_file_attributes',0)&0x400:
                raise BinlogArchiveError('Archive file identity changed')
            checksum=hashlib.sha256()
            while data:=stream.read(1024*1024):checksum.update(data)
            after=os.fstat(stream.fileno())
            identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            if identity(before)!=identity(after) or after.st_size!=selected['size'] or checksum.hexdigest()!=selected['sha256']:
                raise BinlogArchiveError('Native archive file changed after verification')
            stream.seek(0)
            yield stream,deepcopy(selected)

    def remove_artifact(self,job_id,owner,endpoint,confirmation):
        if confirmation!=job_id:raise BinlogArchiveError('Confirm the exact archive job identity before removing its files')
        with self.store(job_id) as store:
            def remove(state):
                record=self.record(state,job_id,owner,endpoint)
                with self._maps_lock:known=self.workers.get(job_id)
                if known and known[0].is_alive():raise BinlogArchiveError('Stop the native archive worker before removing files')
                if record['state'] in ACTIVE or record['state'] not in {'reviewed','cancelled','not_dispatched'} and record.get('native_process_termination_confirmed') is not True:
                    raise BinlogArchiveError('Native archive process termination has not been confirmed')
                for name in ('archive','continuation'):
                    path=self.directory(record)/name
                    if path.exists() or path.is_symlink():
                        info=path.lstat()
                        if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                            raise BinlogArchiveError('Native archive directory identity changed')
                        shutil.rmtree(path)
                record.update(artifact_removed=True,artifact_removed_at=time.time())
                if record['state']=='reviewed':record['state']='cancelled'
            store.change(remove)
        return self.get(job_id,owner,endpoint)

    def close(self,timeout=5):
        with self._maps_lock:workers=list(self.workers.values())
        for _thread,signal in workers:signal.set()
        deadline=time.monotonic()+timeout
        for thread,_signal in workers:
            if thread.ident is not None:thread.join(max(0,deadline-time.monotonic()))
        return all(not thread.is_alive() for thread,_signal in workers)
