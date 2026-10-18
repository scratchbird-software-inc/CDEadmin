"""Durable request channels for temporary slots on a single owned backend."""
from copy import deepcopy
import hashlib
from pathlib import Path
import socket
import threading
import time

import psutil

from ..providers.postgresql.temporary_slots import TemporarySlotError,options,CHANGES
from .mysql_binlog_jobs import MySQLBinlogJobs,DurableCancellation,review_digest


class TemporarySlotCommands(MySQLBinlogJobs):
    operation='postgresql_temporary_slot_command'
    remote_database_mutation=True
    review_warnings=(
        'Temporary slots belong to one retained native backend. Native SQL errors can remove all temporary slots owned by that backend.',
        'A native command return and later slot liveness are separate facts. Uncertain commands are never replayed automatically.',)
    _worker_maps_lock=MySQLBinlogJobs._maps_lock

    def observed(self,record):
        result=deepcopy(record)
        if record.get('worker_io_closed'):return result
        parent=self.resource_jobs.load(self.resource_id,record['owner'],record['endpoint_id'])
        stopped=parent.get('worker_io_closed') is True
        if not stopped and parent['execution_host']['hostname']==socket.gethostname():
            pid,created=parent.get('worker_identity',(None,None))
            try:stopped=pid is not None and psutil.Process(pid).create_time()!=created
            except psutil.NoSuchProcess:stopped=True
            except psutil.Error:pass
        if stopped:
            result.update(state='unknown' if record.get('native_dispatch_admitted') else 'not_dispatched',worker_io_closed=True)
        return result

    def public(self,record):
        result=deepcopy({key:value for key,value in record.items() if key not in {'owner','configuration','source_state'}})
        result['automatic_retry']=False
        return result


class TemporarySlotResources(MySQLBinlogJobs):
    operation='postgresql_temporary_slot_resource'
    remote_database_mutation=True
    review_warnings=(
        'Open an independent native SQL connection to retain temporary replication slots. User query connections and pending SQL stay separate.',
        'Temporary slots can retain WAL until native removal, connection termination or a native SQL error. Closing the viewer does not release the resource.',
        'Application connection close and independently observed PostgreSQL backend/slot cleanup have separate receipts. Lost commands are never replayed.',)

    def commands(self,record):
        commands=TemporarySlotCommands(str(self.path)+'.commands.'+record['job_id'],self.directory(record)/'commands')
        commands.resource_jobs=self;commands.resource_id=record['job_id']
        return commands

    def public(self,record):
        result=super().public(record)
        result.pop('native_process_termination_confirmed',None)
        result['native_process_dispatched']=False
        return result

    def require_open(self,record):
        if record['state']!='active' or not record.get('ready') or not record.get('native_resource_open_returned') or self.public(record)['state']!='active':
            raise TemporarySlotError('Select an open resource on its recorded application host; an old backend is never reconnected')
        if record.get('pending_command'):raise TemporarySlotError('Wait for the resource request already in progress')

    def queue_review(self,job_id,owner,endpoint,operation,value):
        selected=options(operation,value)
        return self.queue_request(job_id,owner,endpoint,'review',operation,selected)

    def queue_catalog(self,job_id,owner,endpoint,offset=0,limit=25):
        if type(offset) is not int or not 0<=offset<=9223372036854775807 or type(limit) is not int or not 1<=limit<=100:
            raise TemporarySlotError('Select a bounded temporary-slot page')
        return self.queue_request(job_id,owner,endpoint,'catalog','catalog',{'offset':offset,'limit':limit,'timeout_seconds':5})

    def queue_request(self,job_id,owner,endpoint,kind,operation,selected):
        with self.store(job_id) as store:
            def change(state):
                resource=self.record(state,job_id,owner,endpoint);self.require_open(resource)
                commands=self.commands(resource)
                reviewed=commands.review(owner,endpoint,{'operation':operation,'native_options':selected},
                    {'identity':{'resource_id':job_id},'state':{}},resource['configuration'],resource['program'])
                child=commands.load(reviewed['job_id'],owner,endpoint)
                values={'state':'queued_'+kind,'native_review_returned':False}
                if operation in CHANGES:
                    values['operation']='wal_slot_sql_'+operation
                    if operation.startswith('get_'):values['warnings']=[*child['warnings'],'Get consumes native changes. Captured bytes, publication and slot consumption have separate outcomes; a lost result is never replayed.']
                commands.update(child,**values)
                resource['pending_command']={'job_id':child['job_id'],'kind':kind}
                return commands.get(child['job_id'],owner,endpoint)
            return store.change(change)

    def queue_execute(self,job_id,owner,endpoint,request):
        if not isinstance(request,dict) or set(request)!={'job_id','review_digest','confirmed'} or request['confirmed'] is not True:
            raise TemporarySlotError('Confirm the exact reviewed native temporary-slot command')
        with self.store(job_id) as store:
            def change(state):
                resource=self.record(state,job_id,owner,endpoint);commands=self.commands(resource)
                admitted=False
                with commands.store(request['job_id']) as child_store:
                    def admit(child_state):
                        nonlocal admitted
                        child=commands.record(child_state,request['job_id'],owner,endpoint)
                        if child['state']!='reviewed':return commands.public(child)
                        self.require_open(resource)
                        if not child.get('native_review_returned') or child['source'].get('resource_id')!=job_id or child['review_digest']!=request['review_digest'] or child['expires_at']<=time.time():
                            raise TemporarySlotError('The native temporary-slot review is unavailable, changed or expired')
                        child.update(state='queued_execute',confirmed_at=time.time(),worker_io_closed=False)
                        admitted=True
                        return commands.public(child)
                    child=child_store.change(admit)
                if admitted:resource['pending_command']={'job_id':child['job_id'],'kind':'execute'}
                elif child['state']=='queued_execute' and not resource.get('pending_command'):
                    self.require_open(resource)
                    resource['pending_command']={'job_id':child['job_id'],'kind':'execute'}
                return child
            return store.change(change)

    def cancel_command(self,job_id,owner,endpoint,command_id):
        resource=self.load(job_id,owner,endpoint);commands=self.commands(resource)
        with commands.store(command_id) as store:
            def change(state):
                child=commands.record(state,command_id,owner,endpoint)
                if child['state'] in {'queued_review','queued_catalog','reviewing','querying','queued_execute','active'}:child['cancel_requested']=True
                elif child['state']=='reviewed':child.update(state='cancelled',cancel_requested=True)
                return commands.public(child)
            return store.change(change)

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal)
        try:
            self.update(record,state='active')
            result=transport.execute(record,self,cancel)
            self.update(record,state='closed',result=result,finished_at=time.time(),automatic_retry=False)
        except BaseException as error:
            current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
            self.update(record,state='unknown' if current.get('native_resource_open_returned') else 'failed',
                error_type=type(error).__name__,native_error_sqlstate=getattr(error,'sqlstate',None),
                error_message=str(error) if isinstance(error,TemporarySlotError) else None,
                finished_at=time.time(),automatic_retry=False)
        finally:
            try:
                try:
                    current=self.load(record['job_id'],record['owner'],record['endpoint_id']);pending=current.get('pending_command')
                    if pending:
                        commands=self.commands(record);child=commands.load(pending['job_id'],record['owner'],record['endpoint_id'])
                        if child['state'] in {'queued_review','queued_catalog','queued_execute'}:
                            commands.update(child,state='cancelled',resource_closed_before_dispatch=True,worker_io_closed=True)
                        self.update(record,pending_command=None)
                finally:transport.close()
                self.update(record,worker_io_closed=True)
            except BaseException as error:
                self.update(record,state='unknown',worker_io_closed=False,owner_transport_close_error=type(error).__name__)
            finally:
                with self._maps_lock:
                    known=self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():self.workers.pop(record['job_id'],None)

    def process(self,record,native,cancel,expired=lambda:False):
        current=self.load(record['job_id'],record['owner'],record['endpoint_id']);pending=current.get('pending_command')
        if not pending:return False
        commands=self.commands(record);child=commands.load(pending['job_id'],record['owner'],record['endpoint_id'])
        selected=child['options'];done=threading.Event();armed=threading.Event();watcher=None
        deadline=None if selected['native_options']['timeout_seconds'] is None else time.monotonic()+selected['native_options']['timeout_seconds']
        def stopped():
            return cancel.is_set() or expired() or commands.load(child['job_id'],child['owner'],child['endpoint_id']).get('cancel_requested') or deadline is not None and time.monotonic()>=deadline
        def observe():
            while not done.wait(.1):
                try:
                    if armed.is_set() and stopped():native.connection.cancel_safe(timeout=1);return
                except BaseException:
                    # An observer failure closes this owner connection rather
                    # than dispatching another statement on uncertain state.
                    native.usable=False
                    try:native.connection.cancel_safe(timeout=1)
                    except BaseException:pass
                    return
        def finish():
            done.set()
            if watcher is not None:watcher.join(timeout=2)
            if watcher is not None and watcher.is_alive() or not native.usable:
                raise TemporarySlotError('Native cancellation observer cleanup is unconfirmed; release this backend without replay')
        try:
            if child['state'] not in {'queued_review','queued_catalog','queued_execute'}:return False
            if stopped():commands.update(child,state='cancelled',worker_io_closed=True);return True
            if pending['kind']=='catalog':
                commands.update(child,state='querying')
                page=native.inventory(selected['native_options']['offset'],selected['native_options']['limit'])
                commands.update(child,state='completed',result=page,catalog_returned=True,finished_at=time.time(),worker_io_closed=True)
                self.update(record,latest_native_inventory=page,latest_inventory_observed_at=time.time())
            elif pending['kind']=='review':
                commands.update(child,state='reviewing')
                reviewed=native.review(selected['operation'],selected['native_options'])
                updated={**child,'source':{'resource_id':record['job_id'],'native_review':reviewed},'expires_at':time.time()+600}
                commands.update(child,state='reviewed',source=updated['source'],expires_at=updated['expires_at'],
                    review_digest=review_digest(updated),native_review_returned=True,worker_io_closed=True)
            else:
                watcher=threading.Thread(target=observe,daemon=True,name='postgresql-temporary-slot-cancel');watcher.start()
                def dispatching():
                    if stopped():raise TemporarySlotError('Temporary-slot command stopped before native dispatch')
                    commands.update(child,state='active',native_dispatch_admitted=True,dispatched_at=time.time());armed.set()
                def acknowledge(value):commands.update(child,native_command_acknowledged=True,native_acknowledgement=value)
                if selected['operation'] in CHANGES:
                    from . import postgresql_slot_changes as changes
                    def stream_acknowledge(value):
                        commands.update(child,native_command_acknowledged=True,native_sql_acknowledged=True,native_sql_result=value)
                        finish()
                    def check_cancel():
                        if stopped():raise InterruptedError('Native temporary logical output capture was stopped')
                    with native.command_context(child['source']['native_review'],dispatching=dispatching,finished=finish):
                        observed=changes.stream(native.connection,commands.directory(child),'wal_slot_sql_'+selected['operation'],selected['native_options'],
                            acknowledge=stream_acknowledge,progress=lambda value:commands.update(child,progress=value),check_cancel=check_cancel)
                    commands.update(child,change_artifact={**observed,'state':'verified','writer_closed':True})
                    result={'native_output':observed,'slot_after':native.observation(selected['native_options']['slot']),
                        'owned_temporary_slots':native.inventory()}
                else:result=native.command(child['source']['native_review'],acknowledge,dispatching=dispatching,finished=finish)
                commands.update(child,state='completed',result=result,finished_at=time.time(),worker_io_closed=True)
            return True
        except BaseException as error:
            done.set()
            if watcher is not None:watcher.join(timeout=2)
            if watcher is not None and watcher.is_alive():native.usable=False
            latest=commands.load(child['job_id'],child['owner'],child['endpoint_id'])
            commands.update(child,state='unknown' if latest.get('native_command_acknowledged') or latest.get('native_dispatch_admitted') and getattr(error,'sqlstate',None) is None else 'failed',
                error_type=type(error).__name__,native_error_sqlstate=getattr(error,'sqlstate',None),
                error_message=str(error) if isinstance(error,TemporarySlotError) else None,
                finished_at=time.time(),automatic_retry=False,worker_io_closed=watcher is None or not watcher.is_alive())
            if not native.usable or native.connection.closed or native.connection.broken:raise
            self.update(record,latest_native_inventory=native.inventory(),latest_inventory_observed_at=time.time())
            return True
        finally:
            # Each queued identity is consumed once, including uncertain
            # native returns. A lost response never adds it back to the queue.
            with self.store(record['job_id']) as store:
                def clear(state):
                    current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                    if (current.get('pending_command') or {}).get('job_id')==child['job_id']:current['pending_command']=None
                store.change(clear)


class TemporarySlotTransport:
    """Hold native credentials, tunnel and connection for the full lease."""
    def __init__(self,transport):self.transport=transport

    def close(self):self.transport.close()

    def execute(self,record,jobs,cancel):
        from ..providers.postgresql import large_object_files as private_sql
        from ..providers.postgresql.temporary_slots import TemporarySlots
        connection=None;closed=False;opened=time.monotonic();last_observed=0
        lifetime=record['options']['max_lifetime_seconds']
        try:
            with self.transport.parameters() as parameters:
                if cancel.is_set():raise TemporarySlotError('Temporary-slot resource opening was cancelled before attachment')
                connection=private_sql.attach({**parameters,'application_name':'ScratchRobin temp '+record['job_id']},record['source']['sql_identity'])
                with private_sql.cursor(connection) as query:query.execute('SET statement_timeout = 5000')
                native=TemporarySlots(connection)
                if (native.adapter_sha256!=record['program'].get('adapter_sha256') or
                        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=record['program'].get('channel_sha256') or
                        hashlib.sha256(Path(__file__).with_name('postgresql_slot_changes.py').read_bytes()).hexdigest()!=record['program'].get('logical_output_sha256') or
                        hashlib.sha256(Path(private_sql.__file__).read_bytes()).hexdigest()!=record['program'].get('private_transport_sha256')):
                    raise TemporarySlotError('The native temporary-slot adapter changed before worker attachment')
                jobs.update(record,native_resource_open_returned=True,native_resource_id=native.resource_id,
                    backend_pid=native.backend_pid,backend_started_epoch=native.backend_started_epoch,
                    native_adapter_sha256=native.adapter_sha256,source_role_identity=native.source,
                    owner_heartbeat_at=time.time(),ready=True)
                try:
                    while not cancel.is_set():
                        if lifetime is not None and time.monotonic()-opened>=lifetime:
                            jobs.update(record,lifetime_expired=True);break
                        if jobs.process(record,native,cancel,expired=lambda:lifetime is not None and time.monotonic()-opened>=lifetime):continue
                        if time.monotonic()-last_observed>=5:
                            jobs.update(record,latest_native_inventory=native.inventory(),latest_inventory_observed_at=time.time(),owner_heartbeat_at=time.time())
                            last_observed=time.monotonic()
                        cancel.wait(.1)
                finally:
                    # PQfinish closes the local client. The independent
                    # backend/slot cleanup observation remains a separate step.
                    connection.close();closed=True
                    jobs.update(record,native_owner_connection_close_returned=True,ready=False,owner_connection_closed_at=time.time(),remote_cleanup_inferred=False)
        finally:
            if connection is not None and not closed:
                connection.close()
                jobs.update(record,native_owner_connection_close_returned=True,ready=False,owner_connection_closed_at=time.time(),remote_cleanup_inferred=False)
        return {'owner_connection_close_returned':True,'remote_cleanup_inferred':False,
            'cancel_requested':cancel.is_set(),'lifetime_expired':lifetime is not None and time.monotonic()-opened>=lifetime}
