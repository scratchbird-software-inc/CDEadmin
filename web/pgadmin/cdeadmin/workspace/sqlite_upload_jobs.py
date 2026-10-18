"""Bounded native-file intake; checksums and native parsing precede eligibility."""
import base64
import binascii
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.driver import SQLiteConnection
from ..providers.sqlite.session_api import SessionAPI,SessionAPIError
from .sqlite_capture_jobs import SQLiteCaptureJobs
from .mysql_binlog_jobs import review_digest

CHUNK_BYTES=262144
MAX_LENGTH=9223372036854775807


def decimal(value,label):
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}',value) or int(value)>MAX_LENGTH:
        raise SessionAPIError(label+' requires exact nonnegative bounded decimal text')
    return int(value)


def options(value):
    if not isinstance(value,dict) or set(value)-{'filename','length','kind','expected_sha256','timeout_seconds'}:
        raise SessionAPIError('Select native file upload options')
    length=decimal(value.get('length'),'Upload length');filename=value.get('filename');kind=value.get('kind','auto')
    expected=value.get('expected_sha256');timeout=value.get('timeout_seconds',3600)
    if not isinstance(filename,str) or not filename or '\x00' in filename or len(filename.encode('utf8'))>1024:
        raise SessionAPIError('Select a bounded client filename')
    if not isinstance(kind,str) or kind not in {'auto','changeset','patchset'}:raise SessionAPIError('Select automatic native format detection or an expected changeset/patchset')
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
        raise SessionAPIError('The expected whole-file SHA256 must be lowercase hexadecimal text')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise SessionAPIError('Select a positive validation duration or no deadline')
    return {'filename':filename,'length':str(length),'kind':kind,'expected_sha256':expected,'timeout_seconds':timeout}


class SQLiteUploadJobs(SQLiteCaptureJobs):
    operation='sqlite_native_file_upload'
    review_warnings=(
        'File intake writes private application-host staging files in bounded, checksum-acknowledged chunks. It does not modify a registered database.',
        'Whole-file SHA256 and the pinned native changeset iterator validate the staged artifact. Without an expected producer checksum, no independent producer identity is claimed.',
        'Native file structure does not establish schema compatibility or application-data correctness. Applying the file requires a separate native review and confirmation.',)

    def data_file_name(self,record):return 'uploaded.native'

    def create(self,owner,endpoint,selected,configuration,program):
        selected=options(selected)
        result=self.review(owner,endpoint,selected,{'identity':{'client_filename':selected['filename'],'declared_length':selected['length']},'state':{}},configuration,program)
        record=self.load(result['job_id'],owner,endpoint);incoming=self.directory(record)/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        path=incoming/self.data_file_name(record)
        with path.open('xb') as stream:private_file(path);stream.flush();os.fsync(stream.fileno())
        self.update(record,state='uploading',uploaded_bytes='0',chunk_bytes=CHUNK_BYTES)
        return self.get(record['job_id'],owner,endpoint)

    def upload(self,job_id,owner,endpoint,request):
        if not isinstance(request,dict) or set(request)!={'offset','data_base64','sha256'}:raise SessionAPIError('Select an exact upload chunk')
        offset=decimal(request['offset'],'Upload offset');encoded=request['data_base64'];checksum=request['sha256']
        if not isinstance(encoded,str) or len(encoded)>4*((CHUNK_BYTES+2)//3) or not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):
            raise SessionAPIError('Select a bounded checksum-identified chunk')
        try:data=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):raise SessionAPIError('Upload chunks require canonical base64') from None
        if not 1<=len(data)<=CHUNK_BYTES or base64.b64encode(data).decode('ascii')!=encoded or hashlib.sha256(data).hexdigest()!=checksum:
            raise SessionAPIError('Upload chunk encoding or checksum differs')
        self.scope(owner,endpoint)
        with self.store(job_id) as store:
            def append(state):
                record=self.record(state,job_id,owner,endpoint)
                if record['state']!='uploading':raise SessionAPIError('This native intake no longer accepts chunks')
                received=int(record['uploaded_bytes']);end=offset+len(data)
                if offset>received or end>int(record['options']['length']):raise SessionAPIError('Upload chunk exceeds its declared bounds')
                path=self.directory(record)/'archive.incoming'/self.data_file_name(record)
                root=path.parent
                info=path.lstat()
                if root.resolve()!=root or not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                    raise SessionAPIError('Native upload file identity changed')
                descriptor=os.open(path,os.O_RDWR|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
                with os.fdopen(descriptor,'r+b') as stream:
                    opened=os.fstat(descriptor)
                    if self.file_identity(info)!=self.file_identity(opened):raise SessionAPIError('Native upload file changed while opening')
                    size=opened.st_size
                    if offset<received:
                        if end>received:raise SessionAPIError('Upload retry overlaps acknowledged bytes')
                        stream.seek(offset)
                        if stream.read(len(data))!=data:raise SessionAPIError('Upload retry differs from acknowledged bytes')
                    elif size==end:
                        stream.seek(offset)
                        if stream.read(len(data))!=data:raise SessionAPIError('Unacknowledged staged upload bytes differ')
                    elif size==received:
                        stream.seek(offset);stream.write(data);stream.flush();os.fsync(descriptor)
                    else:raise SessionAPIError('Native upload has a partial write; retain its receipt and start another intake')
                record.update(uploaded_bytes=str(max(received,end)),updated_at=time.time())
                return {'job_id':job_id,'uploaded_bytes':record['uploaded_bytes'],'chunk_sha256':checksum}
            return store.change(append)

    def seal(self,job_id,owner,endpoint,configuration,program,library):
        self.scope(owner,endpoint)
        with self.store(job_id) as store:
            def ready(state):
                record=self.record(state,job_id,owner,endpoint)
                if record['state'] in {'uploading','reviewed'} and (configuration!=record['configuration'] or program!=record['program']):
                    raise SessionAPIError('Native intake helper or application policy changed')
                if record['state']=='uploading':
                    if record['uploaded_bytes']!=record['options']['length']:raise SessionAPIError('Upload all declared bytes before native validation')
                    record.update(state='reviewed',expires_at=time.time()+600,updated_at=time.time())
                    record['review_digest']=review_digest(record)
                return record.copy()
            record=store.change(ready)
        request={key:record[key] for key in ('job_id','review_digest')};request['confirmed']=True
        return self.start(request,owner,endpoint,{key:record[key] for key in ('source','configuration','program')},
            UploadTransport(self,library) if record['state']=='reviewed' else None)

    def cancel(self,job_id,owner,endpoint):
        with self.store(job_id) as store:
            def stop(state):
                record=self.record(state,job_id,owner,endpoint)
                if record['state']=='uploading':record.update(state='cancelled',cancel_requested=True,worker_io_closed=True)
            store.change(stop)
        return super().cancel(job_id,owner,endpoint)


class UploadTransport:
    def __init__(self,jobs,library):self.jobs,self.library=jobs,library;self.connection=None

    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None

    @contextmanager
    def native_cancellation(self,cancel,timeout,started,progress,stage='native-validate-upload'):
        read,write=os.pipe();lock=threading.Lock();done=threading.Event();failure=[]
        def signal():
            with lock:
                if not done.is_set():os.write(write,b'cancel')
        def observe():
            sent=False
            while not done.wait(.1):
                try:
                    expired=timeout is not None and time.monotonic()-started>=timeout
                    if not sent and (cancel.is_set() or expired):signal();sent=True
                    progress({'stage':stage,'elapsed_seconds':time.monotonic()-started,'deadline_expired':expired})
                except BaseException as error:
                    failure.append(error)
                    try:
                        if not sent:signal()
                    except OSError:pass
                    return
        watcher=threading.Thread(target=observe,daemon=True,name='sqlite-upload-validation')
        try:
            watcher.start()
            if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout:signal()
            yield read
        finally:
            done.set()
            if watcher.ident is not None:watcher.join(timeout=2)
            with lock:os.close(write);os.close(read)
        if watcher.is_alive():raise SessionAPIError('Native upload observer termination is unconfirmed')
        if failure:raise SessionAPIError('Native upload observation failed; inspect the separate native return receipt')

    def execute(self,record,directory,cancel,progress):
        started=time.monotonic();timeout=record['options']['timeout_seconds']
        def check():
            if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout:
                raise SessionAPIError('Native intake validation was stopped')
        incoming=directory/'archive.incoming';path=incoming/self.jobs.data_file_name(record);hashed=hashlib.sha256();read=0
        with self.jobs.open_partial(record,path.name) as stream:
            before=os.fstat(stream.fileno());header=stream.read(1);stream.seek(0)
            while block:=stream.read(1048576):
                check();hashed.update(block);read+=len(block);progress({'stage':'hash-upload','bytes_read':str(read),'total_bytes':record['options']['length']})
            if str(read)!=record['options']['length'] or record['options']['expected_sha256'] is not None and hashed.hexdigest()!=record['options']['expected_sha256']:
                raise SessionAPIError('Native upload length or expected whole-file checksum differs')
            kind='patchset' if header==b'P' else 'changeset' if header in {b'T',b''} else None
            if kind is None or record['options']['kind'] not in {'auto',kind} and header:
                raise SessionAPIError('Native upload header differs from its selected format')
            check();stream.seek(0);connection=sqlite3.connect(':memory:',factory=SQLiteConnection);self.connection=connection
            api=SessionAPI(connection,self.library)
            if api.program!=record['program']:raise SessionAPIError('The reviewed native intake helper changed')
            # Native parsing, not the single-byte format discriminator, admits
            # the complete stream. Empty streams use SQLite's changeset default.
            with self.native_cancellation(cancel,timeout,started,progress) as cancel_descriptor:
                observed=api.call('inspect_file',stream.fileno(),cancel_descriptor)
                self.jobs.update(record,native_returned=True,native_inspection=observed)
            check();after=os.fstat(stream.fileno())
            if self.jobs.file_identity(before)!=self.jobs.file_identity(after):raise SessionAPIError('Native upload bytes changed during validation')
        metadata={'format':'sqlite-native-'+kind+'@3.53.0','native_kind':kind,'input_name':path.name,
            'original_client_filename':record['options']['filename'],'native_empty_stream':not bool(header),
            'producer_checksum_provided':record['options']['expected_sha256'] is not None,'program':api.program,'native':observed,
            'database_mutation':False,'database_recovery_verified':False}
        metadata_path=incoming/'archive.json'
        with metadata_path.open('x',encoding='utf8') as stream:
            private_file(metadata_path);json.dump(metadata,stream,ensure_ascii=True,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        metadata_bytes=metadata_path.read_bytes()
        files=[{'path':path.name,'size':read,'sha256':hashed.hexdigest()},
            {'path':metadata_path.name,'size':len(metadata_bytes),'sha256':hashlib.sha256(metadata_bytes).hexdigest()}]
        artifact={'format':metadata['format'],'native_kind':kind,'input_name':path.name,'files':files,
            'total_bytes':sum(row['size'] for row in files),**observed}
        check();self.jobs.update(record,state='publishing',sealed_candidate={'artifact':artifact})
        durable_replace(incoming,directory/'archive')
        return {'artifact':artifact,'native_returned':True,'database_mutation':False,'database_recovery_verified':False}
