"""Offline, reviewed removal of private receiver inputs; archive receipts survive."""
from copy import deepcopy
import hashlib
import heapq
import os
from pathlib import Path
import socket
import threading
import time

from ..providers.mysql_family import continuous_binlog as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .continuous_binlog_tails import stopped_parent,file_claim
from .mysql_binlog_jobs import MySQLBinlogJobs,DurableCancellation,digest
from .mysql_monitoring_host import MySQLMonitoringHost


class CleanupJobs(MySQLBinlogJobs):
    operation='native_receiver_private_file_cleanup'
    review_warnings=(
        'Permanently remove only these private receiver files on the recorded application host. Unpublished changes may be lost and pending stopped-file adoption reviews may become unusable.',
        'Independently published archives and all operation receipts are retained. This does not purge native server logs, validate recovery coverage or establish a database recovery point.',)

    def public(self,record):
        result=super().public(record);result['native_process_dispatched']=False
        result.pop('native_process_termination_confirmed',None)
        return result

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal)
        try:
            self.update(record,state='active',native_process_dispatched=False)
            result=transport.execute(record,self.directory(record),cancel,lambda event:self.update(record,progress=event))
            self.update(record,state='completed',result=result,finished_at=time.time(),automatic_retry=False)
        except BaseException as error:
            observed=self.load(record['job_id'],record['owner'],record['endpoint_id']).get('progress') or {}
            pending=observed.get('removal_intent_recorded') and observed.get('removal_acknowledged') is False
            self.update(record,state='unknown' if pending else 'cancelled' if signal.is_set() or isinstance(error,InterruptedError) else 'failed',
                error_type=type(error).__name__,error_message=str(error) if isinstance(error,BinlogArchiveError) else None,
                local_removal_may_have_started=True,finished_at=time.time(),automatic_retry=False)
        finally:
            with self._maps_lock:
                known=self.workers.get(record['job_id'])
                if known and known[0] is threading.current_thread():self.workers.pop(record['job_id'],None)


def postimages(directory,names):
    result={}
    for name in names:
        try:result[name]=native.file_identity(directory/'receiving'/name)
        except OSError:raise BinlogArchiveError('A selected private receiver file is unavailable') from None
    return result


class CleanupTransport:
    def __init__(self,jobs,archives,parent):self.jobs,self.archives,self.parent=jobs,archives,parent
    def close(self):pass

    def execute(self,record,_directory,cancel,progress):
        directory=self.jobs.directory(self.parent)
        with file_claim(directory,cancel):
            parent=stopped_parent(self.jobs,self.archives,self.parent['job_id'],record['owner'],record['endpoint_id'])
            expected=record['continuation']['file_postimages'];names=record['options']['log_names']
            if parent['source']!=record['source'] or postimages(directory,names)!=expected:
                raise BinlogArchiveError('The reviewed private receiver file postimages changed; prepare a new removal review')
            removed=[];total=0
            for name in names:
                if cancel.is_set():raise InterruptedError('Private receiver file removal cancelled')
                path=directory/'receiving'/name
                if native.file_identity(path)!=expected[name]:raise BinlogArchiveError('A reviewed private receiver file changed before removal')
                progress({'removed_files':deepcopy(removed),'removed_bytes':str(total),'remaining_files':len(names)-len(removed),
                    'current_file':name,'removal_intent_recorded':True,'removal_acknowledged':False})
                path.unlink();total+=int(expected[name]['st_size']);removed.append(name)
                progress({'removed_files':deepcopy(removed),'removed_bytes':str(total),'remaining_files':len(names)-len(removed),
                    'current_file':name,'removal_intent_recorded':True,'removal_acknowledged':True})
            return {'removed_files':removed,'removed_bytes':str(total),'receiver_job_id':parent['job_id'],
                'archives_removed':False,'receipts_removed':False,'remote_database_mutation':False,
                'power_loss_durability_verified':False,'database_recovery_verified':False}


def manager(service,jobs,family):
    from flask import current_app
    with service._semantic_lock:
        attribute=family+'_receiver_cleanup_jobs';result=getattr(service,attribute,None)
        if result is None:
            root=current_app.config.get('CDEADMIN_'+family.upper()+'_RECEIVER_CLEANUP_ROOT') or str(jobs.root.parent/(family+'-receiver-cleanup'))
            result=CleanupJobs(str(jobs.path)+'.private-cleanup',root);setattr(service,attribute,result)
            import atexit
            atexit.register(result.close)
    return result


def action(service,server,operation,request,family,managed):
    jobs,archives,owner,endpoint,_context=managed;cleanups=manager(service,jobs,family)
    if operation=='cleanup_list':
        if set(request)-{'offset','limit'}:raise BinlogArchiveError('Select one private cleanup receipt page')
        return cleanups.list(owner,endpoint.id,**request)
    if operation in {'cleanup_status','cleanup_cancel'}:
        if set(request)!={'job_id'}:raise BinlogArchiveError('Select one private cleanup receipt')
        return (cleanups.get if operation=='cleanup_status' else cleanups.cancel)(request['job_id'],owner,endpoint.id)
    if operation=='cleanup_start':
        reviewed=cleanups.load(request.get('job_id'),owner,endpoint.id)
        if reviewed['state']!='reviewed':return cleanups.start(request,owner,endpoint.id,{},None)
        parent_id=reviewed['continuation']['receiver_job_id'];names=reviewed['options']['log_names']
    elif operation=='cleanup_review':
        if set(request)!={'job_id','file_names'}:raise BinlogArchiveError('Review exact private receiver file identities')
        parent_id=request['job_id'];names=native.adapter(family).options({'log_names':request['file_names']})['log_names']
    elif operation=='cleanup_catalog':
        if set(request)-{'job_id','after','limit'} or 'job_id' not in request:raise BinlogArchiveError('Select one stopped receiver file page')
        after=request.get('after');limit=request.get('limit',100)
        if type(limit) is not int or not 1<=limit<=100:raise BinlogArchiveError('Select a private receiver file page of at most100 entries')
        if after is not None:native.adapter(family).options({'log_names':[after]})
        parent_id=request['job_id'];names=None
    else:raise BinlogArchiveError('Private receiver cleanup action is unavailable')
    parent=stopped_parent(jobs,archives,parent_id,owner,endpoint.id);directory=jobs.directory(parent)
    with file_claim(directory):
        if operation=='cleanup_catalog':
            receiving=directory/'receiving';files=[]
            more=False
            if receiving.is_symlink() or receiving.exists() and (not receiving.is_dir() or receiving.resolve()!=receiving or getattr(receiving.lstat(),'st_file_attributes',0)&0x400):
                raise BinlogArchiveError('Private receiver directory identity changed')
            if receiving.is_dir():
                with os.scandir(receiving) as entries:
                    page=heapq.nsmallest(limit+1,(entry.name for entry in entries if after is None or entry.name>after))
                more=len(page)>limit
                for name in page[:limit]:
                    native.adapter(family).options({'log_names':[name]})
                    observed=native.file_identity(receiving/name);files.append({'name':name,'bytes':observed['st_size']})
            return {'receiver_job_id':parent_id,'source':parent['source'],'files':files,'more':more,
                'next_after':files[-1]['name'] if more else None,'native_catalog_checked':False,'execution_host':parent['program']['execution_host']}
        observed=postimages(directory,names)
        configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'receiver_root':str(jobs.root),'cleanup_root':str(cleanups.root)})
        sources=[Path(__file__),Path(__file__).with_name('continuous_binlog_tails.py'),Path(native.__file__),Path(__file__).parents[1]/'operations/fileio.py']
        program={'kind':'application-filesystem-adapter','adapter_sha256':digest({path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}),
            'execution_host':{'kind':'application-host','platform':os.name,'hostname':socket.gethostname()}}
        continuation={'receiver_job_id':parent_id,'file_postimages':observed}
        if operation=='cleanup_review':
            return cleanups.review(owner,endpoint.id,{'log_names':names},{'identity':parent['source'],'state':{}},configuration,program,continuation)
        if continuation!=reviewed['continuation']:raise BinlogArchiveError('Private receiver file postimages changed; prepare a new removal review')
        return cleanups.start(request,owner,endpoint.id,{'configuration':configuration,'source':parent['source'],'program':program},
            CleanupTransport(jobs,archives,parent))
