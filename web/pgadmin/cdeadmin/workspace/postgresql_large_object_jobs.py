"""Durable owner-bound staging and native whole-file large-object jobs."""
import base64
import binascii
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

import psutil

from ..operations.fileio import durable_replace,exclusive_file_lock,private_directory,private_file
from ..operations.store import JsonOperationStore
from ..providers.postgresql.large_object_files import (LargeObjectFileError as Error,CHUNK_BYTES,
    attach,cursor,decimal,import_file,metadata,options,read_chunks)


ACTIVE={'reviewing','dispatching','active','cancel_requested'}
REVIEW=('job_id','owner','endpoint_id','database_target_id','configuration','options','source','native_object',
        'length','sha256','artifact_identity','expires_at')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


def identifier(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (TypeError,ValueError,AttributeError):raise Error('Invalid file transfer identity') from None
    return value


def file_identity(value):
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns]


class PostgreSQLLargeObjectJobs:
    def __init__(self,path,root):
        self.path,self.root=Path(path),Path(root).resolve()
        self.lock=threading.RLock();self.workers={};self.connections={};self.worker_identity=[os.getpid(),psutil.Process().create_time()]

    def scope(self,owner,endpoint,target):
        if type(owner) is not int or owner<=0 or not isinstance(target,str) or not 1<=len(target)<=256:
            raise Error('Invalid file transfer owner or database scope')
        return self.root/str(owner)/identifier(endpoint)/hashlib.sha256(target.encode('utf8')).hexdigest()

    def directory(self,record):
        return self.scope(record['owner'],record['endpoint_id'],record['database_target_id'])/identifier(record['job_id'])

    @contextmanager
    def store(self,job_id):
        root=Path(str(self.path)+'.jobs');root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(root)
        path=root/(identifier(job_id)+'.json')
        with self.lock:
            descriptor=os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with exclusive_file_lock(descriptor):yield JsonOperationStore(path)
            finally:os.close(descriptor)

    @staticmethod
    def record(state,job_id,owner,endpoint,target):
        result=state.get('postgresql_large_object_files',{}).get(job_id)
        if result is None or type(owner) is not int or result['owner']!=owner or result['endpoint_id']!=endpoint or result['database_target_id']!=target:
            raise Error('File transfer is unavailable for this owner, endpoint and database')
        return result

    def load(self,job_id,owner,endpoint,target):
        self.scope(owner,endpoint,target)
        with self.store(job_id) as store:return self.record(store.read(),job_id,owner,endpoint,target)

    def public(self,record):
        result=deepcopy({key:value for key,value in record.items() if key not in {'owner','configuration','artifact_identity','worker_identity'}})
        result['automatic_retry']=False
        if record['state'] in ACTIVE:
            worker=self.workers.get(record['job_id']);pid,created=record.get('worker_identity',(None,None))
            try:alive=pid is not None and psutil.Process(pid).create_time()==created
            except psutil.Error:alive=False
            if not alive or record.get('worker_identity')==self.worker_identity and not (worker and worker[0].is_alive()):
                result.update(state='unknown',observation_blocker='The worker stopped without a terminal receipt. Native commit or artifact completion is unconfirmed; this job will not be replayed.')
        return result

    def get(self,*scope):return self.public(self.load(*scope))

    def update(self,record,**values):
        with self.store(record['job_id']) as store:
            def change(state):
                current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'],record['database_target_id'])
                current.update(deepcopy(values),updated_at=time.time())
            store.change(change)

    def create(self,owner,endpoint,target,selected,source,configuration,native_object=None):
        selected=options(selected);scope=self.scope(owner,endpoint,target)
        record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'database_target_id':target,
            'options':selected,'source':deepcopy(source),'configuration':configuration,'native_object':deepcopy(native_object),
            'state':'uploading' if selected['operation']=='import' else 'reviewed','created_at':time.time(),
            'expires_at':time.time()+600,'uploaded_bytes':'0','cancel_requested':False,
            'artifact_available':selected['operation']=='import',
            'warnings':['File bytes are staged on the application host in bounded chunks. Native execution owns a separate PostgreSQL transaction.',
                'Import creates a new native large object. Native checksum verification precedes COMMIT; a lost commit reply remains unknown and is never replayed.',
                'Export observes one repeatable-read native snapshot at execution time. Its receipt proves the application artifact, not that a browser saved the file.']}
        if selected['operation']=='export':
            if not isinstance(native_object,dict) or native_object.get('oid')!=selected['oid']:raise Error('Native export admission is required')
            record['length']=native_object['length'];record['review_digest']=digest({key:record.get(key) for key in REVIEW})
        directory=self.directory(record)
        for path in (self.root,self.root/str(owner),scope.parent,scope,scope/'index',directory):
            if path.is_symlink() or path.resolve()!=path or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
                raise Error('File transfer ownership directories cannot contain links or reparse points')
            path.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(path)
        if selected['operation']=='import':
            with (directory/'payload').open('xb') as stream:private_file(directory/'payload');stream.flush();os.fsync(stream.fileno())
        with self.store(record['job_id']) as store:store.change(lambda state:state.setdefault('postgresql_large_object_files',{}).update({record['job_id']:record}))
        entry=scope/'index'/(f'{time.time_ns():020d}_'+record['job_id']);temporary=entry.with_name('.'+entry.name)
        with temporary.open('xb') as stream:private_file(temporary);stream.flush();os.fsync(stream.fileno())
        durable_replace(temporary,entry)
        return self.public(record)

    @contextmanager
    def payload(self,record,mode='rb'):
        path=self.directory(record)/'payload'
        if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:raise Error('File transfer artifacts cannot be links or reparse points')
        flags=os.O_RDONLY if mode=='rb' else os.O_RDWR
        descriptor=os.open(path,flags|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,mode) as stream:
            if file_identity(os.fstat(stream.fileno()))!=file_identity(path.lstat()):raise Error('File transfer artifact identity changed while opening')
            yield stream

    def upload(self,job_id,owner,endpoint,target,request):
        if not isinstance(request,dict) or set(request)!={'offset','data_base64','sha256'}:raise Error('Invalid file upload chunk')
        offset=decimal(request['offset'],'Upload offset');encoded=request['data_base64'];checksum=request['sha256']
        if not isinstance(encoded,str) or len(encoded)>4*((CHUNK_BYTES+2)//3) or not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):
            raise Error('Invalid bounded file upload chunk')
        try:data=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):raise Error('File upload requires canonical base64') from None
        if not 1<=len(data)<=CHUNK_BYTES or base64.b64encode(data).decode('ascii')!=encoded or hashlib.sha256(data).hexdigest()!=checksum:
            raise Error('File upload chunk checksum or encoding differs')
        self.scope(owner,endpoint,target)
        with self.store(job_id) as store:
            def append(state):
                record=self.record(state,job_id,owner,endpoint,target)
                if record['state']!='uploading':raise Error('This file transfer cannot receive chunks')
                received=int(record['uploaded_bytes']);end=offset+len(data)
                if offset>received or end>int(record['options']['length']):raise Error('File upload offset exceeds its reviewed bounds')
                with self.payload(record,'r+b') as stream:
                    size=os.fstat(stream.fileno()).st_size
                    if offset<received:
                        if end>received:raise Error('File upload retry overlaps an acknowledged chunk')
                        stream.seek(offset)
                        if stream.read(len(data))!=data:raise Error('File upload retry differs from acknowledged bytes')
                    elif size==end:
                        stream.seek(offset)
                        if stream.read(len(data))!=data:raise Error('File upload recovery differs from staged bytes')
                    elif size==received:
                        stream.seek(offset);stream.write(data);stream.flush();os.fsync(stream.fileno())
                    else:raise Error('File upload has an unconfirmed partial write; cancel and create another transfer')
                record['uploaded_bytes']=str(max(received,end));record['updated_at']=time.time()
                return {'job_id':job_id,'uploaded_bytes':record['uploaded_bytes'],'chunk_sha256':checksum}
            return store.change(append)

    def list(self,owner,endpoint,target,offset=0,limit=25):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise Error('Invalid file receipt page')
        index=self.scope(owner,endpoint,target)/'index'
        entries=sorted((p for p in index.iterdir() if not p.name.startswith('.')),reverse=True) if index.is_dir() else []
        result=[];unavailable=[]
        for entry in entries[offset:offset+limit]:
            job_id=entry.name.split('_',1)[-1]
            try:result.append(self.get(job_id,owner,endpoint,target))
            except Error:unavailable.append(job_id)
        return {'jobs':result,'offset':offset,'limit':limit,'total':len(entries),'unavailable_job_ids':unavailable}

    def launch(self,record,target):
        signal=threading.Event()
        worker=threading.Thread(target=target,args=(record,signal),daemon=True,name='postgresql-lo-file-'+record['job_id'])
        with self.lock:self.workers[record['job_id']]=(worker,signal)
        try:worker.start()
        except BaseException:
            self.workers.pop(record['job_id'],None);self.update(record,state='not_dispatched');raise

    def forget_worker(self,job_id):
        # A client may confirm immediately after hashing publishes its review.
        # The hashing thread must not remove the newly dispatched SQL worker.
        with self.lock:
            worker=self.workers.get(job_id)
            if worker and worker[0] is threading.current_thread():self.workers.pop(job_id,None)

    def seal(self,job_id,owner,endpoint,target,source,configuration):
        with self.store(job_id) as store:
            def claim(state):
                record=self.record(state,job_id,owner,endpoint,target)
                if record['state']!='uploading':return None
                if record['uploaded_bytes']!=record['options']['length']:raise Error('Upload every selected file byte before review')
                record.update(state='reviewing',worker_identity=self.worker_identity,source=deepcopy(source),configuration=configuration)
                return deepcopy(record)
            record=store.change(claim)
        if record is not None:self.launch(record,self.hash_upload)
        return self.get(job_id,owner,endpoint,target)

    def hash_upload(self,record,signal):
        try:
            checksum=hashlib.sha256();size=0
            with self.payload(record) as stream:
                before=file_identity(os.fstat(stream.fileno()))
                while data:=stream.read(CHUNK_BYTES):
                    if signal.is_set():raise InterruptedError()
                    checksum.update(data);size+=len(data)
                if before!=file_identity(os.fstat(stream.fileno())) or size!=int(record['options']['length']):raise Error('Staged import changed while preparing review')
            record.update(sha256=checksum.hexdigest(),length=str(size),artifact_identity=before,expires_at=time.time()+600)
            with self.store(record['job_id']) as store:
                def finish(state):
                    current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'],record['database_target_id'])
                    if current['cancel_requested'] or signal.is_set():current['state']='cancelled';return
                    current.update(state='reviewed',**{key:record[key] for key in ('sha256','length','artifact_identity','expires_at')},
                        review_digest=digest({key:record.get(key) for key in REVIEW}))
                store.change(finish)
        except Exception as error:self.update(record,state='cancelled' if isinstance(error,InterruptedError) else 'failed',error_type=type(error).__name__)
        finally:self.forget_worker(record['job_id'])

    def start(self,request,owner,endpoint,target,source,configuration,transport):
        claimed=False;handed=False
        try:
            if not isinstance(request,dict) or set(request)!={'job_id','review_digest','confirmed'} or request['confirmed'] is not True:
                raise Error('Confirm the reviewed native file transfer')
            with self.store(request['job_id']) as store:
                def claim(state):
                    nonlocal claimed
                    record=self.record(state,request['job_id'],owner,endpoint,target)
                    if record.get('review_digest')!=request['review_digest']:raise Error('File transfer review fingerprint changed')
                    if record['state']!='reviewed':return deepcopy(record)
                    if record['cancel_requested']:record['state']='cancelled';return deepcopy(record)
                    if transport is None or source!=record['source'] or configuration!=record['configuration'] or record['expires_at']<time.time():
                        raise Error('File transfer identity, policy or review expired; create a new transfer')
                    if digest({key:record.get(key) for key in REVIEW})!=record['review_digest']:raise Error('File transfer review fingerprint changed')
                    record.update(state='dispatching',worker_identity=self.worker_identity);claimed=True
                    return deepcopy(record)
                record=store.change(claim)
            if not claimed:
                if transport is not None:transport.close()
            else:self.launch(record,lambda item,signal:self.run(item,signal,transport));handed=True
            return self.get(record['job_id'],owner,endpoint,target)
        except BaseException:
            if transport is not None and not handed:transport.close()
            raise

    def cancel(self,job_id,owner,endpoint,target):
        record=self.load(job_id,owner,endpoint,target)
        with self.store(job_id) as store:
            def cancel(state):
                value=self.record(state,job_id,owner,endpoint,target)
                if value['state'] in ACTIVE:value.update(cancel_requested=True,state='cancel_requested')
                elif value['state'] in {'uploading','reviewed'}:value.update(cancel_requested=True,state='cancelled')
            store.change(cancel)
        worker=self.workers.get(job_id)
        if worker is not None:worker[1].set()
        connection=self.connections.get(job_id)
        if connection is not None:
            try:connection.cancel()
            except Exception:pass
        return self.get(job_id,owner,endpoint,target)

    def transfer(self,record,signal,connection):
        def check_cancel():
            if self.load(record['job_id'],record['owner'],record['endpoint_id'],record['database_target_id'])['cancel_requested']:signal.set()
            if signal.is_set():raise InterruptedError('File transfer cancellation requested')
        def progress(size,phase='transferring'):
            check_cancel()
            self.update(record,progress={'bytes':str(size),'total':record['length'],'phase':phase})
        check_cancel()
        if record['options']['operation']=='import':
            with self.payload(record) as stream:
                if file_identity(os.fstat(stream.fileno()))!=record['artifact_identity']:raise Error('Staged import changed after review')
                return import_file(connection,stream,record['options'],record['sha256'],cancel=signal,progress=progress,
                    verifying=lambda size:progress(size,'verifying-native-postimage'),
                    created=lambda oid,transaction:self.update(record,native_oid=oid,native_transaction_id=transaction))
        if metadata(connection,record['options']['oid'])!=record['native_object']:raise Error('Native large-object metadata changed after review')
        path=self.directory(record)/'payload';checksum=hashlib.sha256()
        with path.open('xb') as stream:
            private_file(path)
            self.update(record,artifact_available=True)
            for data in read_chunks(connection,record['options']['oid'],record['length'],cancel=signal,progress=progress):stream.write(data);checksum.update(data)
            stream.flush();os.fsync(stream.fileno())
        record['artifact_identity']=file_identity(path.lstat())
        observed=hashlib.sha256()
        with self.payload(record) as stream:
            while data:=stream.read(CHUNK_BYTES):check_cancel();observed.update(data)
        if observed.hexdigest()!=checksum.hexdigest():raise Error('Application export artifact checksum differs')
        return {'oid':record['options']['oid'],'length':record['length'],'sha256':checksum.hexdigest(),
                'application_artifact_verified':True,'client_file_verified':False}

    def run(self,record,signal,transport):
        connection=None;committing=False;entered=False;context=transport.parameters();rolled_back=False
        try:
            parameters=context.__enter__();entered=True
            connection=attach(parameters,record['source'])
            self.connections[record['job_id']]=connection
            with cursor(connection) as query:query.execute('BEGIN ISOLATION LEVEL REPEATABLE READ '+('READ ONLY' if record['options']['operation']=='export' else 'READ WRITE'))
            self.update(record,state='active',progress={'bytes':'0','total':record['length']})
            result=self.transfer(record,signal,connection)
            if self.load(record['job_id'],record['owner'],record['endpoint_id'],record['database_target_id'])['cancel_requested'] or signal.is_set():raise InterruptedError()
            self.update(record,precommit_result=result,artifact_identity=record.get('artifact_identity'),artifact_available=True)
            committing=True
            with cursor(connection) as query:
                query.execute('COMMIT')
                if query.statusmessage!='COMMIT':raise Error('Native transfer commit acknowledgement is unavailable')
            self.update(record,state='committed',result=result,artifact_identity=record.get('artifact_identity'),finished_at=time.time(),
                        native_transaction_outcome='committed',automatic_retry=False)
        except Exception as error:
            if connection is not None and not committing:
                try:
                    with cursor(connection) as query:query.execute('ROLLBACK');rolled_back=query.statusmessage=='ROLLBACK'
                except Exception:pass
            self.update(record,state='unknown' if committing or connection is not None and not rolled_back else 'cancelled' if isinstance(error,InterruptedError) or signal.is_set() else 'failed',
                error_type=type(error).__name__,native_sqlstate=getattr(error,'sqlstate',None),
                native_transaction_outcome='unknown' if committing or connection is not None and not rolled_back else 'rolled_back' if rolled_back else 'not_dispatched',finished_at=time.time())
        finally:
            self.connections.pop(record['job_id'],None)
            try:
                if connection is not None:connection.close()
            finally:
                try:
                    if entered:context.__exit__(None,None,None)
                finally:transport.close();self.forget_worker(record['job_id'])

    def close(self):
        for worker,signal in list(self.workers.values()):signal.set()
        for connection in list(self.connections.values()):
            try:connection.cancel()
            except Exception:pass

    def reconcile(self,record,connection=None):
        observed=self.public(record)
        if observed['state']!='unknown':raise Error('Reconciliation requires an unknown transfer outcome')
        values={}
        if record['options']['operation']=='export':
            result=record.get('precommit_result')
            if not result:raise Error('Complete export bytes were not observed before the worker stopped')
            checksum=hashlib.sha256()
            with self.payload(record) as stream:
                before=file_identity(os.fstat(stream.fileno()))
                if before!=record.get('artifact_identity'):raise Error('Unknown export artifact identity changed')
                while data:=stream.read(CHUNK_BYTES):checksum.update(data)
                if before!=file_identity(os.fstat(stream.fileno())) or checksum.hexdigest()!=result['sha256']:
                    raise Error('Unknown export artifact checksum differs')
            values.update(state='artifact_verified',result=result,native_transaction_outcome='unknown',
                reconciliation={'application_artifact_verified':True,'native_read_only_commit_confirmed':False})
        else:
            transaction=record.get('native_transaction_id')
            if connection is None or not isinstance(transaction,str) or not re.fullmatch('[1-9][0-9]{0,19}',transaction):
                raise Error('Native import transaction identity is unavailable')
            with cursor(connection) as query:
                query.execute('SELECT pg_catalog.pg_xact_status(%s::xid8)',(transaction,));status=query.fetchone()[0]
            values['reconciliation']={'native_transaction_status':status}
            if status=='committed':
                result=record.get('precommit_result')
                if result is None:raise Error('Native commit exists without a retained precommit verification receipt')
                values.update(state='committed',result=result,native_transaction_outcome='committed')
            elif status=='aborted':values.update(state='rolled_back',native_transaction_outcome='rolled_back')
        self.update(record,**values)
        return self.get(record['job_id'],record['owner'],record['endpoint_id'],record['database_target_id'])

    def remove_artifact(self,job_id,owner,endpoint,target,confirmation):
        if confirmation!=job_id:raise Error('Confirm the exact file transfer identity before removing its application artifact')
        with self.store(job_id) as store:
            def remove(state):
                record=self.record(state,job_id,owner,endpoint,target)
                worker=self.workers.get(job_id)
                if worker and worker[0].is_alive():raise Error('Stop the file transfer worker before removing its artifact')
                if record['state'] in ACTIVE:
                    pid,created=record.get('worker_identity',(None,None))
                    try:alive=pid is not None and psutil.Process(pid).create_time()==created
                    except psutil.Error:alive=False
                    if alive:raise Error('The file transfer writer has not been confirmed stopped')
                path=self.directory(record)/'payload'
                if path.exists() or path.is_symlink():
                    with self.payload(record):pass
                    try:path.unlink()
                    except OSError:raise Error('The application file could not be removed while it is in use') from None
                record.update(artifact_available=False,artifact_removed_at=time.time())
                if record['state'] in {'uploading','reviewed'}:record['state']='cancelled'
            store.change(remove)
        return self.get(job_id,owner,endpoint,target)
