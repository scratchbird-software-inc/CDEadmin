"""Reviewed native changeset writes with separate apply and commit receipts."""
from contextlib import ExitStack,contextmanager
import hashlib
import json
import os
import re
import socket
import sqlite3
import stat
import threading
import time

from ..operations.fileio import durable_replace,private_directory,private_file
from ..providers.sqlite.changeset_apply import ApplyFailure,connect,stage,target_snapshot
from ..providers.sqlite.conflict_channel import ConflictChannel
from ..providers.sqlite.session_api import SessionAPIError
from .sqlite_capture_jobs import SQLiteCaptureJobs,checked_archive_reads
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

    def decide(self,job_id,owner,endpoint,request):
        if not isinstance(request,dict) or set(request)!={'challenge','choice','remember_kind'} or not isinstance(request['challenge'],str) or not re.fullmatch('[0-9A-F]{32}',request['challenge']) or request['choice'] not in ('omit','replace','abort') or type(request['remember_kind']) is not bool:
            raise SessionAPIError('Select one exact native callback response')
        with self.store(job_id) as store:
            def admit(state):
                record=self.record(state,job_id,owner,endpoint);pending=record.get('pending_conflict') or {}
                if record['state']!='active' or record.get('worker_io_closed') or not pending.get('waiting') or pending.get('challenge')!=request['challenge']:
                    raise SessionAPIError('This native conflict callback is no longer waiting for this response')
                if record['program']['execution_host']['hostname']!=socket.gethostname():raise SessionAPIError('Send the response on the recorded native application host')
                if request['choice'] not in pending['allowed_choices']:raise SessionAPIError('This native conflict kind does not support that response')
                current=record.get('conflict_response')
                if current is not None:
                    if any(current.get(key)!=value for key,value in request.items()):raise SessionAPIError('A different response was already admitted for this callback')
                    return self.public(record)
                record['conflict_response']={**request,'admitted_at':time.time(),'native_pipe_write_returned':False}
                return self.public(record)
            return store.change(admit)

    def conflict(self,job_id,owner,endpoint,challenge):
        record=self.load(job_id,owner,endpoint);pending=record.get('pending_conflict') or {}
        if not isinstance(challenge,str) or pending.get('challenge')!=challenge:raise SessionAPIError('Refresh the current native conflict identity')
        root=self.directory(record)/'archive'
        if not root.exists():root=self.directory(record)/'archive.incoming'
        info=root.lstat()
        if root.resolve()!=root or not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise SessionAPIError('Native conflict output directory changed')
        path=root/'pending-conflict.json';descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            before=os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or getattr(before,'st_file_attributes',0)&0x400 or before.st_size>134217728 or str(before.st_size)!=pending['event_size']:raise SessionAPIError('Native conflict event size or identity changed')
            data=stream.read();after=os.fstat(descriptor)
            if self.file_identity(before)!=self.file_identity(after) or hashlib.sha256(data).hexdigest()!=pending['event_sha256']:raise SessionAPIError('Native conflict event changed; refresh its current identity')
        value=json.loads(data)
        if value.get('challenge')!=challenge:raise SessionAPIError('Native conflict callback identity changed')
        return {'event':value,'pending':pending,'state':record['state'],'database_commit_returned':record.get('commit_returned') is True,
            'scope':'Values observed by this live native callback; the incoming change reflects the reviewed native inversion flag. Apply change sequence is not a source-file record ordinal.'}

    @contextmanager
    def conflict_value(self,job_id,owner,endpoint,challenge,side,column):
        if side not in ('old','new','current') or type(column) is not int or column<0:raise SessionAPIError('Select one exact native conflict byte value')
        event=self.conflict(job_id,owner,endpoint,challenge)['event']
        selected=next((row for row in event.get('byte_values',[]) if row['side']==side and row['column_index']==column),None)
        if selected is None:raise SessionAPIError('The native callback has no byte value at that position')
        record=self.load(job_id,owner,endpoint);root=self.directory(record)/'archive'
        if not root.exists():root=self.directory(record)/'archive.incoming'
        descriptor=os.open(root/'native-conflict-values.bin',os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(descriptor,'rb') as stream:
            before=os.fstat(descriptor);offset=int(selected['byte_offset']);length=int(selected['byte_length'])
            if not stat.S_ISREG(before.st_mode) or getattr(before,'st_file_attributes',0)&0x400 or offset<0 or length<0 or offset+length>before.st_size:raise SessionAPIError('Native conflict byte range changed')
            stream.seek(offset);remaining=length;hashed=hashlib.sha256()
            while remaining:
                block=stream.read(min(remaining,1048576))
                if not block:raise SessionAPIError('Native conflict byte range ended early')
                hashed.update(block);remaining-=len(block)
            after=os.fstat(descriptor)
            if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or hashed.hexdigest()!=selected['sha256']:raise SessionAPIError('Native conflict byte range differs from its acknowledged event')
            stream.seek(offset);yield ConflictValueStream(stream,length),{**selected,'size':length,'path':'conflict-'+side+'-'+str(column+1)+'.bin'}

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
        if selected is None or relative not in {'archive.json','native.rebase','native-conflicts.jsonl','native-conflict-values.bin','pending-conflict.json'}:raise SessionAPIError('Select an exact native apply output file')
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


class ConflictValueStream:
    def __init__(self,stream,length):self.stream,self.remaining=stream,length
    def read(self,size=-1):
        if size is None or size<0:size=self.remaining
        data=self.stream.read(min(size,self.remaining));self.remaining-=len(data);return data
    def close(self):self.stream.close()


class ApplyTransport:
    def __init__(self,jobs,route,library,input_factory):
        self.jobs,self.route,self.library,self.input_factory=jobs,route,library,input_factory
        self.connection=None

    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None

    def execute(self,record,directory,cancel,progress):
        started=time.monotonic();connection,api=connect(self.route,self.library);self.connection=connection;selected=record['options'];timeout=selected['timeout_seconds']
        if api.program!=record['program']:raise SessionAPIError('The reviewed native apply helper changed')
        if target_snapshot(connection,self.route)!=record['source']['destination']:raise SessionAPIError('The reviewed destination file or native schema changed')
        for name in ('foreign_keys','recursive_triggers'):connection.execute('PRAGMA '+name+'='+str(int(selected[name])))
        incoming=directory/'archive.incoming';incoming.mkdir(mode=0o700);private_directory(incoming)
        with ExitStack() as cleanup:
            last_progress=[started]
            def check_source():
                now=time.monotonic()
                if cancel.is_set() or timeout is not None and now-started>=timeout:raise ApplyFailure('Native apply stopped during source verification before its transaction')
                if now-last_progress[0]>=.2:
                    progress({'stage':'verify-native-input','elapsed_seconds':now-started});last_progress[0]=now
            cleanup.enter_context(checked_archive_reads(check_source))
            stream,_identity=cleanup.enter_context(self.input_factory())
            rebase=-1
            if selected['include_rebase']:
                path=incoming/'native.rebase';rebase=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
                cleanup.callback(os.close,rebase);private_file(path)
            read,write=os.pipe();lock=threading.Lock();done=threading.Event();failure=[]
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
                channel=None
                if selected.get('interactive_conflicts'):
                    channel=cleanup.enter_context(ConflictChannel(incoming,
                        lambda **fields:self.jobs.update(record,**fields),
                        lambda:self.jobs.load(record['job_id'],record['owner'],record['endpoint_id']),stop))
                native=stage(connection,api,stream.fileno(),selected,cancel_descriptor=read,rebase_descriptor=rebase,interactive_descriptors=None if channel is None else channel.native_descriptors,
                    acknowledge=lambda result:self.jobs.update(record,native_returned=True,native_apply=result))
                if channel is not None:
                    channel.finish()
                    for descriptor in (channel.native_descriptors[0],channel.native_descriptors[2]):os.fsync(descriptor)
                    channel.close()
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
