"""Reviewed adoption of stopped, complete native receiver files into archives."""
from copy import deepcopy
from contextlib import contextmanager,ExitStack
import errno
import os
import socket
import stat

from ..operations.fileio import exclusive_file_lock,private_file
from ..operations.native_writers import inspect,NativeWriterError
from ..providers.mysql_family import continuous_binlog as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from ..sdk.tooling import ProviderToolGrant
from .mysql_binlog_jobs import digest
from .mysql_monitoring_host import MySQLMonitoringHost


@contextmanager
def file_claim(directory,cancel=None):
    """Adoption and removal share one execution-host filesystem claim."""
    path=directory/'.receiver-files.lock'
    if path.is_symlink() or path.resolve()!=path or path.exists() and getattr(path.lstat(),'st_file_attributes',0)&0x400:
        raise BinlogArchiveError('Receiver file claim cannot contain links or reparse points')
    descriptor=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):raise BinlogArchiveError('Receiver file claim must be a regular file')
        private_file(path)
        with ExitStack() as stack:
            while True:
                if cancel is not None and cancel.is_set():raise InterruptedError('Receiver file claim cancelled')
                try:stack.enter_context(exclusive_file_lock(descriptor,blocking=False));break
                except OSError as error:
                    contention=(getattr(error,'winerror',None)==33 if os.name=='nt' else error.errno in {errno.EAGAIN,errno.EACCES})
                    if not contention:raise
                    if cancel is None:raise BinlogArchiveError('Another operation is using this receiver\'s private files') from None
                    cancel.wait(.1)
            yield
    finally:os.close(descriptor)


def stopped_parent(jobs,archives,job_id,owner,endpoint):
    record=jobs.load(job_id,owner,endpoint)
    if (jobs.get(job_id,owner,endpoint)['state'] not in {'unknown','failed','cancelled','captured'} or
            record.get('native_process_termination_confirmed') is not True and
            (record.get('writer_reconciliation') or {}).get('process_scope_stopped') is not True):
        raise BinlogArchiveError('Confirm stopped receiver writers before inspecting or adopting private files')
    with jobs._maps_lock:known=jobs.workers.get(job_id)
    if known is not None and known[0].is_alive():raise BinlogArchiveError('The local receiver worker is still stopping')
    try:
        progress=record.get('progress') or {}
        candidates,_absent=inspect(jobs.writer_scopes(record,archives),
            hostname=record['program']['execution_host'].get('hostname'),started_at=record.get('started_at',record['created_at']),
            expected=[{'pid':progress.get('pid'),'process_create_time':progress.get('process_create_time')}])
        if candidates:raise NativeWriterError('Reconcile remaining native utilities before adopting stopped receiver files')
    except NativeWriterError as error:raise BinlogArchiveError(str(error)) from None
    return record


def selected_files(adapter,parent_directory,captured,selected):
    chosen=adapter.selected_logs(captured,selected);postimages={}
    for row in chosen:
        try:observed=native.file_identity(parent_directory/'receiving'/row['Log_name'])
        except OSError:raise BinlogArchiveError('A selected stopped receiver file is unavailable') from None
        size=adapter.decoded_length(row) if 'server_uuid' in captured['identity'] else int(row['File_size'])
        if observed['st_size']!=str(size):raise BinlogArchiveError('A stopped receiver file is incomplete; complete native closed-log bytes are required')
        postimages[row['Log_name']]=observed
    return chosen,postimages


class StoppedTailTransport:
    def __init__(self,jobs,archives,parent,adapter,client,route,observer,family):
        self.jobs,self.archives,self.parent,self.native=jobs,archives,parent,adapter
        self.client,self.route,self.observer,self.family=client,route,observer,family

    def close(self):
        if self.observer is not None:
            owned=self.observer;self.observer=None;self.client._discard_failed_session(owned)

    def execute(self,record,directory,cancel,progress):
        with file_claim(self.jobs.directory(self.parent),cancel):
            return self.execute_claimed(record,directory,cancel,progress)

    def execute_claimed(self,record,directory,cancel,progress):
        parent=stopped_parent(self.jobs,self.archives,self.parent['job_id'],record['owner'],record['endpoint_id'])
        captured=self.native.capture(self.observer)
        if captured['identity']!=record['source'] or parent['source']!=record['source']:
            raise BinlogArchiveError('The stopped receiver native source identity changed')
        chosen,postimages=selected_files(self.native,self.jobs.directory(parent),captured,record['options'])
        if chosen!=record['source_state']['selected_logs'] or postimages!=record['continuation']['receiver_file_postimages']:
            raise BinlogArchiveError('The reviewed stopped receiver files or native closed-log catalog changed')
        program=self.native.program_identity(self.client,self.route,directory,cancel=cancel,progress=progress)
        program={**program,'execution_host':{**program['execution_host'],'hostname':socket.gethostname()}}
        if program!=record['program']:raise BinlogArchiveError('The reviewed stopped-file native parser changed')
        tool='mysql-binlog' if self.family=='mysql' else 'mariadb-binlog'
        grant=ProviderToolGrant(tool,str(directory),str(self.route.get('host') or 'localhost'),int(self.route.get('port',3306)),
            timeout_seconds=record['options']['timeout_seconds'],allow_unbounded_runtime=record['options']['timeout_seconds'] is None)
        result=native.seal_received(self.native,self.client,self.family,record,directory,
            self.jobs.directory(parent)/'receiving',chosen,grant,self.observer,cancel,progress,source_postimages=postimages)
        return {**result,'producer_receiver_job_id':parent['job_id'],'adopted_stopped_files':True,
            'parent_outcome_rewritten':False,'database_recovery_verified':False}


def action(service,server,operation,request,family,managed):
    from flask import current_app
    from .continuous_binlog_service import program_identity
    jobs,archives,owner,endpoint,_context=managed;adapter=native.adapter(family)
    if operation=='tail_start':
        reviewed=archives.load(request.get('job_id'),owner,endpoint.id)
        continuation=reviewed.get('continuation') or {}
        if not continuation.get('stopped_receiver_job_id'):raise BinlogArchiveError('Select a reviewed stopped receiver archive')
        if reviewed['state']!='reviewed':return archives.start(request,owner,endpoint.id,{},None)
        parent_id=continuation['stopped_receiver_job_id'];selected=reviewed['options']
    elif operation=='tail_review':
        if set(request)!={'job_id','options'}:raise BinlogArchiveError('Review exact stopped receiver file identities and runtime')
        parent_id=request['job_id'];selected=adapter.options(request['options'])
    elif operation=='tail_catalog':
        if set(request)!={'job_id'}:raise BinlogArchiveError('Select one stopped receiver')
        parent_id=request['job_id'];selected=None
    else:raise BinlogArchiveError('Stopped receiver file action is unavailable')
    parent=stopped_parent(jobs,archives,parent_id,owner,endpoint.id)
    client=connection=transport=None
    try:
        context,payload,_root=service.endpoint_service.workspace(server,database_target_id=None)
        from ..providers.mysql_family.provider import MySQLPilotProvider,MariaDBPilotProvider
        provider=service.endpoint_service.provider_registry.resolve(context).instance
        if not isinstance(provider,MySQLPilotProvider if family=='mysql' else MariaDBPilotProvider):
            raise BinlogArchiveError('Native stopped-file client family is unavailable')
        client=provider.client
        if family=='mysql':
            from ..providers.mysql_family.mysql_connections import POOL_ARGUMENTS
            from mysql.connector import Error as NativeError
        else:
            from ..providers.mysql_family.mariadb_connections import POOL_ARGUMENTS
            from mariadb import Error as NativeError
        route={key:value for key,value in payload['route'].items() if key not in POOL_ARGUMENTS}
        try:
            connection=client._connect({'route':{**route,'read_timeout':5,'write_timeout':15}})
            captured=adapter.capture(connection)
            if captured['identity']!=parent['source']:raise BinlogArchiveError('The stopped receiver belongs to a different native source identity')
            if operation=='tail_catalog':
                logs=[]
                for row in captured['logs']:
                    adapter.options({'log_names':[row['Log_name']]})
                    path=jobs.directory(parent)/'receiving'/row['Log_name']
                    if not path.exists() and not path.is_symlink():continue
                    reason=None;observed=None
                    try:
                        observed=native.file_identity(path)
                        selected_files(adapter,jobs.directory(parent),captured,{'log_names':[row['Log_name']]})
                    except (BinlogArchiveError,OSError) as error:reason=str(error) if isinstance(error,BinlogArchiveError) else 'Local receiver file is unavailable'
                    logs.append({**row,'local_bytes':None if observed is None else observed['st_size'],'eligible':reason is None,'reason':reason})
                return {'job_id':parent_id,'source':captured['identity'],'logs':logs,'parent_state':jobs.get(parent_id,owner,endpoint.id)['state']}
            chosen,postimages=selected_files(adapter,jobs.directory(parent),captured,selected)
            program=program_identity(adapter,client,route,archives.prepare_scope(owner,endpoint.id))
            if program!=parent['program']:raise BinlogArchiveError('Use the receiver\'s reviewed native parser for stopped-file adoption')
            limit=current_app.config.get('CDEADMIN_'+family.upper()+('_RAW_BINLOG_MAX_RUNTIME_SECONDS' if family=='mysql' else '_BINLOG_MAX_RUNTIME_SECONDS'))
            if limit is not None and (type(limit) is not int or not 1<=limit<=2147483647 or selected['timeout_seconds'] is None or selected['timeout_seconds']>limit):
                raise BinlogArchiveError('Application policy requires a bounded native archive duration')
            configuration=digest({'registration':MySQLMonitoringHost._configuration(server),'archive_root':str(archives.root),
                'receiver_root':str(jobs.root),'receiver_job_id':parent_id,'runtime_limit':limit})
            captured['state']['selected_logs']=deepcopy(chosen)
            continuation={'continuous_receiver_job_id':parent_id,'stopped_receiver_job_id':parent_id,'receiver_file_postimages':postimages}
            if operation=='tail_review':
                result=archives.review(owner,endpoint.id,selected,captured,configuration,program,continuation)
                native.index_snapshot(jobs.directory(parent),result['job_id'])
                return result
            if continuation!=reviewed['continuation'] or chosen!=reviewed['source_state']['selected_logs']:
                raise BinlogArchiveError('Stopped receiver file postimages changed; prepare a new review')
            transport=StoppedTailTransport(jobs,archives,parent,adapter,client,route,connection,family);connection=None
            admitted=transport;transport=None
            return archives.start(request,owner,endpoint.id,{'source':captured['identity'],'program':program,'configuration':configuration},admitted)
        except NativeError as error:
            raise BinlogArchiveError('Native stopped receiver file admission failed ('+str(error.errno)+', '+str(error.sqlstate)+')') from None
    finally:
        if connection is not None:client._discard_failed_session(connection)
        if transport is not None:transport.close()
