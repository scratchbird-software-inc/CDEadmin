"""Reviewed native changeset writes with separate apply and commit receipts."""
from contextlib import ExitStack,contextmanager
import hashlib
import json
import os
import sqlite3
import stat
import threading
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.changeset_apply import ApplyFailure,connect,stage,target_snapshot
from ..providers.sqlite.session_api import SessionAPIError
from .sqlite_capture_jobs import SQLiteCaptureJobs
from .mysql_binlog_jobs import DurableCancellation


class SQLiteChangesetJobs(SQLiteCaptureJobs):
    operation='sqlite_native_changeset_apply'
    review_warnings=(
        'Apply the selected verified native changeset/patchset to the registered destination on a separate application-owned connection. Existing query sessions and their pending work stay separate.',
        'Native conflicts use the reviewed per-kind responses. Foreign-key OMIT can retain violations. Replacement is supported only for DATA and CONFLICT. Incompatible selected tables refuse completion and roll back the owned transaction.',
        'Successful native apply stages changes; the commit acknowledgement establishes a separate finality fact. An uncertain commit is never repeated automatically. Rebase/output verification alone cannot prove a database commit.',)

    def public(self,record):
        result=super().public({**record,'state':'active'} if record['state']=='committing' else record)
        if record['state']=='committing' and result['state']=='active':result['state']='committing'
        return result

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal)
        try:
            self.update(record,state='active')
            result=transport.execute(record,self.directory(record),cancel,lambda event:self.update(record,progress=event))
            self.update(record,state='completed',result=result,finished_at=time.time())
        except BaseException as error:
            current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
            unknown=(current.get('commit_admitted') and not current.get('commit_failure_rolled_back') or
                current.get('native_dispatch_admitted') and not current.get('owned_rollback_confirmed'))
            self.update(record,state='unknown' if unknown else 'cancelled' if cancel.is_set() else 'failed',
                error_type=type(error).__name__,error_message=str(error) if isinstance(error,SessionAPIError) else None,
                native_result_code=getattr(error,'native_result_code',None),sqlite_errorcode=getattr(error,'sqlite_errorcode',None),
                sqlite_errorname=getattr(error,'sqlite_errorname',None),finished_at=time.time(),automatic_retry=False)
        finally:
            try:
                transport.close();self.update(record,worker_io_closed=True)
            finally:
                with self._maps_lock:
                    known=self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():self.workers.pop(record['job_id'],None)

    def reconcile(self,job_id,owner,endpoint,inspector=None):
        record=self.load(job_id,owner,endpoint);self.require_stopped(record)
        if record.get('artifact_removed'):raise SessionAPIError('Native apply output files were removed')
        artifact=self.verify_artifact(record)
        incoming=self.directory(record)/'archive.incoming';published=self.directory(record)/'archive'
        if not published.exists():durable_replace(incoming,published)
        self.update(record,result={**(record.get('result') or {}),'artifact':artifact},output_artifact_verified=True,
            output_reconciled_at=time.time())
        # Output bytes and even current database rows cannot establish that an
        # unacknowledged original COMMIT completed. Preserve the original state.
        return self.get(job_id,owner,endpoint)

    @contextmanager
    def output_download(self,job_id,owner,endpoint,relative):
        record=self.load(job_id,owner,endpoint)
        if record.get('artifact_removed') or record['state']!='completed' and not record.get('output_artifact_verified'):
            raise SessionAPIError('Select a verified retained native apply output')
        selected=next((row for row in (record.get('result') or {}).get('artifact',{}).get('files',[]) if row['path']==relative),None)
        if selected is None or relative not in {'archive.json','native.rebase'}:raise SessionAPIError('Select an exact native apply output file')
        root=self.directory(record)/'archive';info=root.lstat()
        if not stat.S_ISDIR(info.st_mode) or root.resolve()!=root or getattr(info,'st_file_attributes',0)&0x400:raise SessionAPIError('Native apply output directory changed')
        descriptor=os.open(root/relative,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            before=os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or getattr(before,'st_file_attributes',0)&0x400:raise SessionAPIError('Native apply output file changed')
            hashed=hashlib.sha256()
            while block:=stream.read(1048576):hashed.update(block)
            after=os.fstat(descriptor)
            if self.file_identity(before)!=self.file_identity(after) or after.st_size!=selected['size'] or hashed.hexdigest()!=selected['sha256']:
                raise SessionAPIError('Native apply output bytes changed after verification')
            stream.seek(0);yield stream,selected


class ApplyTransport:
    def __init__(self,jobs,route,library,input_factory):
        self.jobs,self.route,self.library,self.input_factory=jobs,route,library,input_factory
        self.connection=None

    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None

    def execute(self,record,directory,cancel,progress):
        connection,api=connect(self.route,self.library);self.connection=connection;selected=record['options']
        if api.program!=record['program']:raise SessionAPIError('The reviewed native apply helper changed')
        if target_snapshot(connection,self.route)!=record['source']['destination']:raise SessionAPIError('The reviewed destination file or native schema changed')
        for name in ('foreign_keys','recursive_triggers'):connection.execute('PRAGMA '+name+'='+str(int(selected[name])))
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        with ExitStack() as cleanup:
            stream,_identity=cleanup.enter_context(self.input_factory())
            rebase=-1
            if selected['include_rebase']:
                path=incoming/'native.rebase';rebase=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
                cleanup.callback(os.close,rebase);private_file(path)
            read,write=os.pipe();lock=threading.Lock();done=threading.Event();failure=[];started=time.monotonic()
            def close_pipe(descriptor):
                with lock:os.close(descriptor)
            cleanup.callback(close_pipe,read);cleanup.callback(close_pipe,write)
            def stop():
                with lock:
                    if done.is_set():return
                    os.write(write,b'cancel');connection.interrupt()
            timeout=selected['timeout_seconds']
            def observe():
                signalled=False
                while not done.wait(.1):
                    try:
                        expired=timeout is not None and time.monotonic()-started>=timeout
                        if not signalled and (cancel.is_set() or expired):stop();signalled=True
                        progress({'stage':'native-apply','elapsed_seconds':time.monotonic()-started,'deadline_expired':expired})
                    except BaseException as error:
                        failure.append(error)
                        try:
                            if not signalled:stop()
                        except OSError:pass
                        return
            watcher=threading.Thread(target=observe,daemon=True,name='sqlite-changeset-progress-'+record['job_id'])
            try:
                watcher.start()
                if cancel.is_set():raise ApplyFailure('Native apply was cancelled before its transaction')
                connection.execute('BEGIN IMMEDIATE')
                if target_snapshot(connection,self.route)!=record['source']['destination']:raise SessionAPIError('Destination schema changed while acquiring the native write transaction')
                self.jobs.update(record,native_dispatch_admitted=True)
                native=stage(connection,api,stream.fileno(),selected,cancel_descriptor=read,rebase_descriptor=rebase,
                    acknowledge=lambda result:self.jobs.update(record,native_returned=True,native_apply=result))
                if cancel.is_set() or timeout is not None and time.monotonic()-started>=timeout or failure:
                    raise ApplyFailure('Native apply stopped before commit; roll back the owned transaction',native)
                if rebase>=0:os.fsync(rebase)
                metadata={'format':'sqlite-native-apply-output@1','source':record['source'],'options':selected,
                    'program':record['program'],'native':native,'database_commit_is_a_separate_receipt':True}
                with (incoming/'archive.json').open('x',encoding='utf8') as output:
                    private_file(incoming/'archive.json');json.dump(metadata,output,sort_keys=True,ensure_ascii=True);output.flush();os.fsync(output.fileno())
                files=[]
                for path in sorted(incoming.iterdir()):
                    hashed=hashlib.sha256()
                    with path.open('rb') as output:
                        while block:=output.read(1048576):hashed.update(block)
                    files.append({'path':path.name,'size':path.stat().st_size,'sha256':hashed.hexdigest()})
                artifact={'format':metadata['format'],'files':files,'total_bytes':sum(row['size'] for row in files)}
                self.jobs.update(record,sealed_candidate={'artifact':artifact})
                if cancel.is_set() or failure or timeout is not None and time.monotonic()-started>=timeout:
                    raise ApplyFailure('Native apply stopped before commit; roll back the owned transaction',native)
                # End cancellation observation before admission of COMMIT. A
                # later cancellation cannot retroactively cancel a native commit.
                done.set();watcher.join(timeout=2)
                if watcher.is_alive():raise SessionAPIError('Native apply observer termination is unconfirmed')
                self.jobs.update(record,state='committing',commit_admitted=True)
                try:connection.execute('COMMIT')
                except sqlite3.Error as error:
                    if getattr(error,'sqlite_errorcode',None)==sqlite3.SQLITE_BUSY and connection.in_transaction:
                        connection.rollback();self.jobs.update(record,commit_failure_rolled_back=True,owned_rollback_confirmed=True)
                    raise
                self.jobs.update(record,commit_returned=True,committed_at=time.time())
                durable_replace(incoming,directory/'archive')
                return {'artifact':artifact,'native':native,'database_mutation':True,'commit_returned':True,
                    'database_recovery_verified':False,'data_finality':'native-commit-returned'}
            except BaseException:
                if connection.in_transaction:
                    connection.rollback();self.jobs.update(record,owned_rollback_confirmed=True)
                raise
            finally:
                done.set()
                if watcher.ident is not None:watcher.join(timeout=2)
