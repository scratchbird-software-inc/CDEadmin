"""Owned, once-only SQLite changeset exports; capture memory stays connection-local."""
from copy import deepcopy
from contextlib import ExitStack,contextmanager
import hashlib
import json
import os
import stat
import socket
import threading
import time

import psutil

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.session_api import SessionAPIError
from .mysql_binlog_jobs import MySQLBinlogJobs,DurableCancellation,digest


class SQLiteCaptureJobs(MySQLBinlogJobs):
    operation='sqlite_native_capture_export'
    review_warnings=(
        'Export the selected native capture at dispatch on its retained query connection. Captures record table data, not schema changes or a database backup.',
        'The stream may include uncommitted work. Export does not commit, roll back or establish a recovered database. Closing the query connection loses its capture memory.',
        'Native return, verified output and publication have separate receipts. An uncertain export is not automatically repeated. Private partial output is not a complete changeset.',)

    def data_file_name(self,record):return 'capture.'+record['options']['kind']

    def public(self,record):
        result=super().public({**record,'state':'active'} if record['state']=='publishing' else record)
        if record['state']=='publishing' and result['state']=='active':result['state']='publishing'
        artifact=(result.get('result') or {}).get('artifact')
        if artifact is not None:artifact.pop('native_log_count',None)
        result.pop('native_process_termination_confirmed',None)
        result['native_process_dispatched']=False
        return result

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal)
        try:
            self.update(record,state='active')
            result=transport.execute(record,self.directory(record),cancel,lambda event:self.update(record,progress=event))
            self.update(record,state='completed',result=result,finished_at=time.time(),worker_io_closed=True)
        except BaseException as error:
            current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
            self.update(record,state='unknown' if current.get('native_returned') or current.get('native_dispatch_admitted') and getattr(error,'native_result_code',None) is None else
                'cancelled' if cancel.is_set() else 'failed',error_type=type(error).__name__,
                error_message=str(error) if isinstance(error,SessionAPIError) else None,
                native_result_code=getattr(error,'native_result_code',None),finished_at=time.time(),automatic_retry=False)
        finally:
            try:
                transport.close()
                self.update(record,worker_io_closed=True)
            finally:
                with self._maps_lock:
                    known=self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():self.workers.pop(record['job_id'],None)

    def require_stopped(self,record):
        with self._maps_lock:known=self.workers.get(record['job_id'])
        if known and known[0].is_alive():raise SessionAPIError('Cancel the native export and wait for its connection worker to stop')
        if record.get('worker_io_closed') or not record.get('started_at'):return
        if record['program']['execution_host']['hostname']!=socket.gethostname():
            raise SessionAPIError('Inspect native export I/O on its recorded application host')
        pid,created=record.get('worker_identity',(None,None))
        try:alive=pid is not None and psutil.Process(pid).create_time()==created
        except psutil.NoSuchProcess:alive=False
        except psutil.Error:raise SessionAPIError('Native export owner-process termination cannot be inspected') from None
        if alive:raise SessionAPIError('Native export I/O termination is unconfirmed')
        self.update(record,worker_io_closed=True,owner_process_termination_observed=True)

    def verify_artifact(self,record):
        artifact=(record.get('result') or {}).get('artifact') or (record.get('sealed_candidate') or {}).get('artifact')
        if artifact is None:raise SessionAPIError('A sealed native changeset receipt is unavailable')
        root=self.directory(record)/'archive'
        if not root.exists() and record.get('native_returned'):root=self.directory(record)/'archive.incoming'
        for row in artifact['files']:
            path=root/row['path'];before=path.lstat()
            if not stat.S_ISREG(before.st_mode) or path.resolve()!=path or getattr(before,'st_file_attributes',0)&0x400:
                raise SessionAPIError('Native changeset file identity changed')
            digest_value=hashlib.sha256()
            with path.open('rb') as source:
                while block:=source.read(1048576):digest_value.update(block)
            after=path.stat()
            if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=
                    (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or
                    after.st_size!=row['size'] or digest_value.hexdigest()!=row['sha256']):
                raise SessionAPIError('Native changeset bytes differ from their sealed receipt')
        return deepcopy(artifact)

    def reconcile(self,job_id,owner,endpoint,inspector=None):
        record=self.load(job_id,owner,endpoint);self.require_stopped(record)
        if record.get('artifact_removed'):raise SessionAPIError('Native capture files were removed')
        if not ((record.get('result') or {}).get('artifact') or record.get('sealed_candidate')):
            return self.inspect_partial(record,inspector)
        artifact=self.verify_artifact(record)
        incoming=self.directory(record)/'archive.incoming';published=self.directory(record)/'archive'
        if not published.exists():durable_replace(incoming,published)
        self.update(record,state='artifact_verified',result={**(record.get('result') or {}),'artifact':artifact,
            'native_returned':record.get('native_returned') is True,'database_recovery_verified':False},artifact_reconciled_at=time.time())
        return self.get(job_id,owner,endpoint)

    def inspect_partial(self,record,inspector):
        if not record.get('started_at') or inspector is None:raise SessionAPIError('A native partial-output inspector is required')
        path=self.directory(record)/'archive.incoming'/self.data_file_name(record)
        with self.open_partial(record,path.name) as stream:
            before=os.fstat(stream.fileno());hashed=hashlib.sha256()
            while block:=stream.read(1048576):hashed.update(block)
            stream.seek(0)
            try:observed=inspector(stream.fileno(),record['program'])
            except SessionAPIError as error:
                if error.native_result_code is None:raise
                observed={'native_iterator_complete':False,'native_result_code':error.native_result_code}
            after=os.fstat(stream.fileno())
            if self.file_identity(before)!=self.file_identity(after):raise SessionAPIError('Partial capture bytes changed during inspection')
        # A valid prefix is not evidence of a complete original export. Without
        # the dispatch seal, even a native return/length acknowledgement does
        # not bind these current bytes to that dispatch.
        self.update(record,partial_output={'path':'partial/'+path.name,'size':str(after.st_size),
            'sha256':hashed.hexdigest(),'observations':observed,'inspected_at':time.time(),
            'original_export_bytes_verified':False,'complete_export_verified':False,
            'native_returned':record.get('native_returned') is True,'diagnostic_only':True})
        return self.get(record['job_id'],record['owner'],record['endpoint_id'])

    @staticmethod
    def file_identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

    @contextmanager
    def open_partial(self,record,name):
        root=self.directory(record)/'archive.incoming';info=root.lstat()
        if not stat.S_ISDIR(info.st_mode) or root.resolve()!=root or getattr(info,'st_file_attributes',0)&0x400:
            raise SessionAPIError('Partial capture directory identity changed')
        descriptor=os.open(root/name,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            info=os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise SessionAPIError('Partial capture file identity changed')
            yield stream

    @contextmanager
    def diagnostic_download(self,job_id,owner,endpoint,relative):
        record=self.load(job_id,owner,endpoint);self.require_stopped(record)
        selected=record.get('partial_output') or {};name=self.data_file_name(record)
        if record.get('artifact_removed') or relative!='partial/'+name or relative!=selected.get('path'):
            raise SessionAPIError('Select one inspected native capture diagnostic file')
        with self.open_partial(record,name) as stream:
            before=os.fstat(stream.fileno());hashed=hashlib.sha256()
            while block:=stream.read(1048576):hashed.update(block)
            after=os.fstat(stream.fileno())
            if self.file_identity(before)!=self.file_identity(after) or str(after.st_size)!=selected['size'] or hashed.hexdigest()!=selected['sha256']:
                raise SessionAPIError('Partial capture bytes changed after inspection')
            stream.seek(0);yield stream,{**selected,'path':name+'.partial','size':after.st_size}

    def remove_artifact(self,job_id,owner,endpoint,confirmation):
        record=self.load(job_id,owner,endpoint);self.require_stopped(record)
        # The inherited removal contract needs a stopped native utility fact;
        # this job has no subprocess and proves its own I/O worker termination.
        self.update(record,native_process_termination_confirmed=True)
        return super().remove_artifact(job_id,owner,endpoint,confirmation)


class ExportTransport:
    def __init__(self,jobs,client,handle,api,source):
        self.jobs,self.client,self.handle,self.api,self.source=jobs,client,handle,api,source
        self.claimed=False

    def close(self):
        if self.claimed:
            with self.client._lock:self.client._busy.discard(id(self.handle))
            self.claimed=False

    def execute(self,record,directory,cancel,progress):
        with self.client._lock:
            self.client._require_idle(self.handle)
            self.client._busy.add(id(self.handle));self.claimed=True
        capture=record['source']['capture_id']
        current=self.api.status(capture)
        if (self.api.program!=record['program'] or current['database']!=record['source']['database'] or
                self.handle._cdeadmin_session_api is not self.api):raise SessionAPIError('The reviewed native capture or helper changed')
        databases=[list(row) for row in self.handle.execute('PRAGMA database_list')]
        if databases!=record['source']['databases']:raise SessionAPIError('The reviewed native database attachments changed')
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        name='capture.'+record['options']['kind'];path=incoming/name
        with ExitStack() as cleanup:
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600);cleanup.callback(os.close,descriptor);private_file(path)
            read,write=os.pipe();signal_lock=threading.Lock()
            def close_pipe(value):
                with signal_lock:os.close(value)
            cleanup.callback(close_pipe,read);cleanup.callback(close_pipe,write)
            done=threading.Event();failure=[];started=time.monotonic()
            def request_stop():
                with signal_lock:
                    if done.is_set():return False
                    os.write(write,b'cancel');return True
            timeout=record['options']['timeout_seconds'];deadline=None if timeout is None else started+timeout
            def observe():
                signalled=False
                while not done.wait(.1):
                    try:
                        expired=deadline is not None and time.monotonic()>=deadline
                        stop_requested=cancel.is_set() or expired
                        if done.is_set():return
                        if stop_requested and not signalled:signalled=request_stop()
                        progress({'bytes_written':str(path.stat().st_size),'elapsed_seconds':time.monotonic()-started,'deadline_expired':expired})
                    except BaseException as error:
                        failure.append(error)
                        try:
                            if not signalled:signalled=request_stop()
                        except OSError:pass
                        return
            watcher=threading.Thread(target=observe,daemon=True,name='sqlite-capture-progress-'+record['job_id'])
            try:
                watcher.start()
                if cancel.is_set():request_stop()
                transaction_open=self.handle.in_transaction
                self.jobs.update(record,native_dispatch_admitted=True)
                written=self.api.export(capture,record['options']['kind'],descriptor,read)
                # A successful native stream return is saved before fsync, hashing
                # or publication. It never settles the user's SQL transaction.
                self.jobs.update(record,native_returned=True,native_returned_bytes=str(written),
                    source_transaction_open=transaction_open,source_transaction_open_after=self.handle.in_transaction)
                done.set();watcher.join(timeout=2)
                if watcher.is_alive():raise SessionAPIError('Native export progress observer has not stopped')
                if failure:raise SessionAPIError('Native export observation failed; inspect the separate native return receipt')
                os.fsync(descriptor)
            finally:
                done.set()
                if watcher.ident is not None:watcher.join(timeout=2)
        if path.stat().st_size!=written:raise SessionAPIError('Native export length differs from its return acknowledgement')
        input_descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0))
        try:observed=self.api.call('inspect_file',input_descriptor,-1)
        finally:os.close(input_descriptor)
        files=[]
        metadata={'format':'sqlite-native-'+record['options']['kind']+'@3.53.0','source':record['source'],
            'program':record['program'],'native':observed,'source_transaction_open':transaction_open,
            'database_recovery_verified':False,'database_mutation':False}
        with (incoming/'archive.json').open('x',encoding='utf8') as stream:
            private_file(incoming/'archive.json');json.dump(metadata,stream,ensure_ascii=True,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        for target in (path,incoming/'archive.json'):
            hashed=hashlib.sha256()
            with target.open('rb') as stream:
                while block:=stream.read(1048576):hashed.update(block)
            files.append({'path':target.name,'size':target.stat().st_size,'sha256':hashed.hexdigest()})
        artifact={'format':metadata['format'],'files':files,'total_bytes':sum(row['size'] for row in files),**observed}
        self.jobs.update(record,state='publishing',sealed_candidate={'artifact':artifact,'source_transaction_open':transaction_open})
        durable_replace(incoming,directory/'archive')
        return {'artifact':artifact,'source_transaction_open':transaction_open,'source_transaction_open_after':self.handle.in_transaction,
            'native_returned':True,'database_mutation':False,'database_recovery_verified':False}
