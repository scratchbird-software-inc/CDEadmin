"""Owned native WAL receiver jobs and source-bound append-only archives."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import errno
import os
from pathlib import Path
import re
import shutil
import socket
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError, PhysicalTools
from ..providers.postgresql.continuity_archive import geometry, iter_completed, SEGMENT
from ..providers.postgresql.continuity_wal import ARCHIVE_NAME, _regular


def options(value):
    defaults={'archive':'','compression':'none','slot':'','synchronous':True,'sync':True,
              'status_interval_seconds':10,'end_lsn':'','no_loop':False,'timeout_seconds':None}
    if not isinstance(value,dict) or set(value)-defaults.keys():raise ContinuityError('Invalid native WAL receiver options')
    result={**defaults,**value}
    if not isinstance(result['archive'],str) or ARCHIVE_NAME.fullmatch(result['archive']) is None:
        raise ContinuityError('Select one owned WAL archive name')
    for name in ('slot','compression','end_lsn'):
        if not isinstance(result[name],str) or '\x00' in result[name] or len(result[name])>256:
            raise ContinuityError('Invalid native WAL receiver '+name)
    if result['slot'] and re.fullmatch(r'[a-z0-9_]{1,63}',result['slot']) is None:
        raise ContinuityError('Native replication slots use lowercase letters, digits and underscores')
    if result['compression'].split(':',1)[0] not in {'none','gzip','lz4'} and re.fullmatch(r'[0-9]',result['compression']) is None:
        raise ContinuityError('PostgreSQL 18 WAL receiver supports native none, gzip and lz4 compression')
    if result['end_lsn'] and re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}',result['end_lsn']) is None:
        raise ContinuityError('Select an exact native WAL end position')
    for name in ('synchronous','sync','no_loop'):
        if type(result[name]) is not bool:raise ContinuityError('Native WAL receiver flags require booleans')
    if result['synchronous'] and not result['sync']:raise ContinuityError('Synchronous WAL reception requires native file synchronization')
    interval=result['status_interval_seconds'];timeout=result['timeout_seconds']
    if type(interval) is not int or not 0<=interval<=2147483:
        raise ContinuityError('Select a nonnegative native WAL status interval')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):
        raise ContinuityError('WAL receiver timeout requires a positive duration or no deadline')
    return result


def review(jobs, request, owner, endpoint, source, configuration, paths, runtime_limit):
    if set(request)-{'operation','options'}:raise ContinuityError('Invalid native WAL receiver review')
    selected=options(request.get('options',{}));geometry(source)
    if runtime_limit is not None and (type(runtime_limit) is not int or runtime_limit<1 or
            selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit):
        raise ContinuityError('Application runtime policy requires a bounded native WAL receiver duration')
    jobs.root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(jobs.root)
    tools={'pg_receivewal':PhysicalTools(paths).identify('pg_receivewal',jobs.root)}
    if tools['pg_receivewal']['available'] is not True:raise ContinuityError('Install PostgreSQL 18 pg_receivewal on the application host')
    record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
            'operation':'wal_capture','options':selected,'source':deepcopy(source),'paths':deepcopy(paths),
            'tool_identities':tools,'inputs':[],'state':'reviewed','created_at':time.time(),'expires_at':time.time()+600,
            'execution_host':{'kind':'application-host','platform':os.name,'hostname':socket.gethostname()},
            'artifact_location':str(jobs.archive_directory(owner,endpoint)/selected['archive']),
            'artifact_wal_method':'stream','runtime_limit':runtime_limit,'cancel_requested':False,
            'warnings':['The receiver runs on the application host independently of this viewer. Only completed native files are published; partial files stay in the job workspace.',
                        'An existing archive is resumed after its latest completed segment. A failed or interrupted previous writer must be stopped and reconciled before another receiver starts.',
                        'Files are bound to the native cluster and WAL geometry. Native recovery separately establishes record validity, timeline continuity and the selected recovery target.',
                        'Native reconnect is enabled while no_loop is false. ScratchRobin does not redispatch a stopped job or establish an application restart policy. Cancel retains already published archive files.']}
    if selected['slot']:record['warnings'].append('The selected existing replication slot can retain WAL on the server while this receiver is stopped. This operation does not create or drop the slot.')
    if not selected['sync']:record['warnings'].append('Native receiver synchronization is disabled; successful streaming does not establish power-loss durability.')
    return jobs.save_review(record)


@contextmanager
def claim_lock(descriptor,cancel_signal,check_cancel=None):
    with ExitStack() as stack:
        while True:
            if check_cancel is not None:check_cancel()
            if cancel_signal is not None and cancel_signal.is_set():
                raise ContinuityError('Native WAL archive claim was cancelled')
            try:
                stack.enter_context(exclusive_file_lock(descriptor,blocking=False))
                break
            except OSError as error:
                contention=(getattr(error,'winerror',None)==33 if os.name=='nt' else error.errno in {errno.EAGAIN,errno.EACCES})
                if not contention:raise
                if cancel_signal is None:time.sleep(.1)
                else:cancel_signal.wait(.1)
        yield


@contextmanager
def archive_claim(jobs,record,*,cancel_signal=None,progress=None):
    root=jobs.archive_directory(record['owner'],record['endpoint_id'])
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    private_directory(root.parent);private_directory(root)
    name=record['options']['archive'];archive=root/name;metadata=root/('.'+name+'.metadata.json')
    for path in (archive,metadata,Path(str(metadata)+'.lock')):
        if path.is_symlink() or path.resolve()!=path or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
            raise ContinuityError('Native WAL archive ownership cannot contain links or reparse points')
    descriptor=os.open(str(metadata)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        next_cancel_check=0
        def check_cancel():
            nonlocal next_cancel_check
            if time.monotonic()<next_cancel_check:return
            current=jobs.load(record['job_id'],record['owner'],record['endpoint_id'])
            if current['cancel_requested']:
                if cancel_signal is not None:cancel_signal.set()
                raise ContinuityError('Native WAL archive claim was cancelled')
            next_cancel_check=time.monotonic()+.25
        with claim_lock(descriptor,cancel_signal,check_cancel):
            store=JsonOperationStore(metadata);state=store.read();binding=state.get('wal_archive')
            size,block,identity=geometry(record['source'])
            source={'system_identifier':str(identity),'wal_segment_bytes':size,'wal_block_bytes':block,'server_version':record['source']['server_version']}
            if binding is None:
                if archive.exists() and any(archive.iterdir()):
                    raise ContinuityError('Existing archive files require explicit source adoption before native capture')
                binding={'source':source}
            elif binding['source']!=source:raise ContinuityError('This native WAL archive belongs to a different cluster or WAL geometry')
            previous=binding.get('writer_job_id')
            if previous and previous!=record['job_id']:
                prior=jobs.load(previous,record['owner'],record['endpoint_id'])
                jobs.require_stopped_writer(prior)
                staging=jobs.directory(prior)/'wal-capture'
                if staging.is_dir():
                    recent=[];count=total=0;next_progress=0
                    for receipt in iter_completed(staging,archive,prior['source'],cancel_signal=cancel_signal,check_cancel=check_cancel):
                        count+=1;total+=receipt['bytes'];recent.append(receipt);del recent[:-10]
                        if progress is not None and time.monotonic()>=next_progress:
                            progress({'phase':'reconciling_native_wal','completed_files':count,'bytes':str(total)})
                            next_progress=time.monotonic()+.25
                    jobs.update(prior,archive_reconciliation={'completed_files':recent,'completed_file_count':count,
                        'completed_files_truncated':count>len(recent),'bytes':str(total),
                        'artifact_verified':False,'observed_at':time.time()})
            archive.mkdir(mode=0o700,exist_ok=True);private_directory(archive)
            binding={**binding,'writer_job_id':record['job_id'],'writer_hostname':socket.gethostname(),'updated_at':time.time()}
            store.change(lambda current:current.update(wal_archive=binding))
        yield archive
    finally:os.close(descriptor)


def arguments(selected,staging):
    result=['--directory='+str(staging),'--no-password','--verbose',
            '--status-interval='+str(selected['status_interval_seconds']),'--compress='+selected['compression']]
    if selected['synchronous']:result.append('--synchronous')
    if not selected['sync']:result.append('--no-sync')
    if selected['no_loop']:result.append('--no-loop')
    if selected['slot']:result.append('--slot='+selected['slot'])
    if selected['end_lsn']:result.append('--endpos='+selected['end_lsn'])
    return result


def run(jobs,record,tools,directory,transport,progress,signal):
    staging=directory/'wal-capture';staging.mkdir(mode=0o700);private_directory(staging)
    with archive_claim(jobs,record,cancel_signal=signal,progress=progress) as archive:
        segments=[]
        for path in archive.iterdir():
            if SEGMENT.fullmatch(path.name):_regular(path);segments.append(path)
        seed=max(segments,key=lambda path:path.name) if segments else None
        if seed is not None:
            shutil.copyfile(seed,staging/seed.name)
            from ..operations.fileio import private_file
            private_file(staging/seed.name)
        seen=set();last_files=[];publication_error=[]
        completed_count=new_count=total_bytes=0
        def archive_observation():
            return {'completed_files':completed_count,'new_files':new_count,'bytes':str(total_bytes),
                    'last_files':last_files,'native_record_verification':False,
                    'resumed_after_segment':seed.name if seed is not None else None}
        def publish():
            nonlocal completed_count,new_count,total_bytes
            next_check=0
            def check():
                nonlocal next_check
                if time.monotonic()<next_check:return
                current=jobs.load(record['job_id'],record['owner'],record['endpoint_id'])
                if current['cancel_requested']:signal.set()
                jobs.update(record,archive_observation=archive_observation())
                next_check=time.monotonic()+.25
            check()
            for receipt in iter_completed(staging,archive,record['source'],observed=seen,cancel_signal=signal,check_cancel=check):
                completed_count+=1;new_count+=receipt['published'];total_bytes+=receipt['bytes']
                last_files.append(receipt);del last_files[:-10]
                check()
            # Retain the newest closed segment for native reconnect start
            # selection. Published older files live only in the archive.
            closed=[name for name in seen if re.fullmatch(r'[0-9A-F]{24}(?:\.gz|\.lz4)?',name)]
            latest=max(closed,key=lambda name:name[:24]) if closed else None
            for name in closed:
                if name!=latest:(staging/name).unlink();seen.remove(name)
            jobs.update(record,archive_observation=archive_observation())
        def tick(event):
            try:progress(event);publish()
            except Exception as error:
                if isinstance(error,ContinuityError) and signal.is_set():return
                # observe_process disables a failing callback. Signal the tool
                # first so publication errors cannot leave an unobserved writer.
                publication_error.append(error);signal.set()
        publish();jobs.update(record,state='active',phase='receiving_native_wal')
        with transport.parameters() as parameters:
            result=tools.execute('pg_receivewal',directory,arguments(record['options'],staging),parameters=parameters,
                timeout=record['options']['timeout_seconds'],progress=tick,cancel_signal=signal)
            jobs.update(record,tool_observation=result,native_receiver_returned=result['return_code']==0,
                worker_io_closed=result['process_observation'].get('cleanup_confirmed') is True)
        if publication_error:
            jobs.update(record,state='failed' if result['process_observation'].get('cleanup_confirmed') is True else 'unknown',error_type=type(publication_error[0]).__name__,
                        error_reason='Native WAL archive publication failed; reconcile the writer before resuming')
            return
        if not signal.is_set():publish()
        observation=result['process_observation']
        if observation.get('cleanup_confirmed') is not True:state='unknown'
        elif observation.get('cancel_requested') or signal.is_set():state='cancelled'
        elif result['return_code']!=0:state='failed'
        else:state='captured'
        jobs.update(record,state=state,phase='receiver_stopped',finished_at=time.time(),
                    native_record_verification=False,remote_finality_inferred=False,automatic_retry=False)
