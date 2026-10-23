"""Durable native replay claims and target fences; unknown jobs never replay."""
from contextlib import contextmanager
from copy import deepcopy
import os
import shutil
from pathlib import Path
import threading
import time

from ..operations.fileio import exclusive_file_lock,private_directory
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .mysql_binlog_jobs import MySQLBinlogJobs,DurableCancellation,identity,digest


class MySQLBinlogReplayJobs(MySQLBinlogJobs):
    operation='mysql_binary_log_replay'
    remote_database_mutation=True
    review_warnings=('Replays server-wide changes on the confirmed target. A compatible restored base is required.',
        'Native transactions can commit individually. Cancellation and local process exit do not roll back earlier transactions.',
        'Native GTID coverage and utility return do not verify restored data or production cutover.')

    def public(self,record):
        result=super().public(record);result['target']=result.pop('source')
        reference=record['source_state']['input_reference']
        result['source_archive']={key:deepcopy(reference[key]) for key in ('server_id','endpoint_id','job_id','artifact_digest','summary')}
        summary=result['source_archive']['summary']
        summary['total_bytes']=str(summary['total_bytes'])
        for name in ('start_from','end_at'):
            if isinstance(summary.get(name),dict) and 'position' in summary[name]:summary[name]['position']=str(summary[name]['position'])
        result['native_load_outcome']=record.get('native_load_outcome','not_dispatched' if record['state'] in {'reviewed','cancelled','not_dispatched'} and not record.get('native_load_may_have_dispatched') else 'unknown')
        result['data_recovery_verified']=False
        result['utility_cancellation_available']=bool(record.get('durable_tools')) and result.get('native_process_termination_confirmed') is not True
        return result

    def progress(self,record,value):
        if not isinstance(value,dict) or not value.get('durable_tool'):return super().progress(record,value)
        reference=value['durable_tool'];name=reference.get('name')
        raw=record['source_state']['input_reference'].get('family')=='raw'
        if not raw and name!='shell-replay-client':return super().progress(record,value)
        if name not in ({'raw-replay-decoder','raw-replay-client'} if raw else {'shell-replay-client'}):
            raise BinlogArchiveError('Native replay utility reference is not admitted')
        with self.store(record['job_id']) as store:
            def change(state):
                current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                tools=current.setdefault('durable_tools',{})
                if name in tools and tools[name]!=reference:raise BinlogArchiveError('An original replay utility cannot be replaced or repeated')
                tools[name]=deepcopy(reference);current.update(progress=deepcopy(value),durable_tool=deepcopy(reference))
            store.change(change)

    def observe_utility(self,record,*,cancel=False):
        from ..sdk import durable_tool
        tools=record.get('durable_tools')
        if not tools:return super().observe_utility(record,cancel=cancel)
        raw=record['source_state']['input_reference'].get('family')=='raw'
        expected=({'raw-replay-decoder':record['program']['decoder']['executable_sha256'],
            'raw-replay-client':record['program']['client']['executable_sha256']} if raw else
            {'shell-replay-client':record['program']['executable_sha256']})
        operation=durable_tool.cancel if cancel else durable_tool.observe
        observed={}
        for name,reference in tools.items():
            if name not in expected or reference.get('name')!=name:raise BinlogArchiveError('Original native replay utility association changed')
            observed[name]=operation(self.directory(record),reference,expected[name])
        required=({'raw-replay-decoder','raw-replay-client'} if record.get('native_load_may_have_dispatched') else {'raw-replay-decoder'}) if raw else {'shell-replay-client'}
        stopped=required.issubset(observed) and all(observed[name].get('complete') is True and observed[name].get('cleanup_confirmed') is True for name in required)
        result={'tools':observed,'native_process_termination_confirmed':stopped,'original_native_load_outcome_unchanged':True,
            'automatic_retry':False,'observed_at':time.time()}
        values={'interrupted_utility_observation':result,'native_process_termination_confirmed':stopped}
        if self.public(record)['state']=='unknown':values['state']='unknown'
        self.update(record,**values)
        return result

    @staticmethod
    def target_identity(record):return record['source']['server_uuid']

    @contextmanager
    def fence_store(self,target_uuid):
        root=Path(str(self.path)+'.target-fences');root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(root)
        path=root/(identity(target_uuid)+'.json')
        descriptor=os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
        try:
            with exclusive_file_lock(descriptor):yield JsonOperationStore(path)
        finally:os.close(descriptor)

    def claim_fence(self,record):
        with self.fence_store(self.target_identity(record)) as store:
            def claim(state):
                current=state.get('replay_fence')
                if current is not None and current['job_id']!=record['job_id']:
                    if current.get('operation', self.operation) != self.operation:
                        raise BinlogArchiveError('This native target has another active or unresolved recovery operation; reconcile its original receipt')
                    # A crash between saving a terminal receipt and releasing
                    # the fence can be reconciled from that durable fact.
                    previous=self.load(current['job_id'],current['owner'],current['endpoint_id'])
                    if (previous.get('native_load_outcome') not in {'returned','not_dispatched'} or
                            previous.get('native_process_termination_confirmed') is not True or
                            previous.get('recovery_fence_release_confirmed', True) is not True):
                        raise BinlogArchiveError('This native target has an active or unresolved replay; reconcile its receipt before another dispatch')
                state['replay_fence']={key:record[key] for key in ('job_id','owner','endpoint_id','operation')}
            store.change(claim)

    def release_fence(self,record):
        with self.fence_store(self.target_identity(record)) as store:
            def release(state):
                if state.get('replay_fence',{}).get('job_id')==record['job_id']:state.pop('replay_fence',None)
            store.change(release)

    def cancel(self,job_id,owner,endpoint):
        super().cancel(job_id,owner,endpoint)
        record=self.load(job_id,owner,endpoint)
        # Atomic worker admission changes the reviewed state and records both
        # worker_identity and started_at. Cancelling the review first prevents
        # that admission, including a caller paused after claiming its fence.
        admitted=('worker_identity','started_at','native_load_may_have_dispatched',
                  'native_checks_may_have_started','durable_tool','server_lock_owner')
        if record['state']=='cancelled' and not any(key in record for key in admitted):
            self.release_fence(record)
        return self.get(job_id,owner,endpoint)

    def start(self,request,owner,endpoint,current,transport):
        record=self.load(request.get('job_id') if isinstance(request,dict) else None,owner,endpoint)
        if record['state']!='reviewed':return super().start(request,owner,endpoint,current,transport)
        try:self.claim_fence(record)
        except BaseException:
            if transport is not None:transport.close()
            raise
        try:
            result=super().start(request,owner,endpoint,current,transport)
            if result['state'] in {'reviewed','cancelled','not_dispatched'}:self.release_fence(record)
            return result
        except BaseException:
            current_record=self.load(record['job_id'],owner,endpoint)
            if current_record['state'] in {'reviewed','cancelled','not_dispatched'}:self.release_fence(record)
            raise

    def run(self,record,transport,signal):
        cancel=DurableCancellation(self,record,signal);dispatched=False
        try:
            self.update(record,state='active',phase='verifying_input',native_load_outcome='not_dispatched')
            def progress(value):self.progress(record,value)
            def boundary():
                nonlocal dispatched
                if cancel.is_set():raise InterruptedError('Replay cancelled before native dispatch')
                self.update(record,phase='native_dispatch',native_load_outcome='unknown',native_load_may_have_dispatched=True)
                dispatched=True
            result=transport.execute(record,self.directory(record),cancel,progress,boundary)
            control=result.get('control') or {};process=result['tool']['process_observation']
            stopped=process.get('cleanup_confirmed') is True
            returned=control.get('native_load_returned') is True and result['tool']['return_code']==0
            not_dispatched=control.get('native_load_invoked') is False
            state='native_load_returned' if returned and stopped else 'not_dispatched' if not_dispatched and stopped else 'unknown'
            outcome='returned' if state=='native_load_returned' else 'not_dispatched' if state=='not_dispatched' else 'unknown'
            self.update(record,state=state,phase='finished',result=result,native_load_outcome=outcome,
                native_process_termination_confirmed=stopped,finished_at=time.time())
            if outcome!='unknown' and stopped:self.release_fence(record)
        except BaseException as error:
            observed=getattr(error,'observation',None) or getattr(error,'process_observation',None)
            if isinstance(observed,dict):observed={key:value for key,value in observed.items() if key not in {'stdout','stderr'}}
            stopped=(observed or {}).get('process_observation',{}).get('cleanup_confirmed')
            if stopped is None and getattr(error,'native_preparation_refused',False):stopped=True
            control=getattr(error,'control',None) or {}
            not_dispatched=not dispatched or control.get('native_load_invoked') is False
            decoder_guardian=not dispatched and bool(self.load(record['job_id'],record['owner'],record['endpoint_id']).get('durable_tools'))
            self.update(record,state='cancelled' if not_dispatched and cancel.is_set() else 'not_dispatched' if not_dispatched else 'unknown',
                native_load_outcome='not_dispatched' if not_dispatched else 'unknown',
                native_process_termination_confirmed=False if decoder_guardian else True if not dispatched else stopped,
                tool_observation=observed,native_control=control or None,error_type=type(error).__name__,finished_at=time.time())
            if decoder_guardian:
                current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
                # No SQL client was dispatched, but its decoder may still
                # be running under a guardian after this observer exits.
                try:self.observe_utility(current)
                except Exception as failure:
                    self.update(record,native_process_termination_confirmed=False,
                        utility_reconciliation_error_type=type(failure).__name__)
            if not_dispatched and (not dispatched or stopped is True):self.release_fence(record)
        finally:
            try:transport.close()
            finally:
                with self._maps_lock:
                    entry=self.workers.get(record['job_id'])
                    if entry and entry[0] is threading.current_thread():self.workers.pop(record['job_id'],None)

    def reconcile(self,record,observation):
        with self._maps_lock:
            known=self.workers.get(record['job_id'])
            if known and known[0].is_alive():raise BinlogArchiveError('The native replay worker is still active')
        if self.public(record)['state'] in {'dispatching','active','cancel_requested'}:
            raise BinlogArchiveError('The original native replay worker is still active')
        self.observe_utility(record)
        record=self.load(record['job_id'],record['owner'],record['endpoint_id'])
        if record.get('durable_tools') and record.get('native_process_termination_confirmed') is True:
            path=self.directory(record)/'input'
            if path.is_symlink():raise BinlogArchiveError('Original replay input cleanup scope changed')
            if path.exists():shutil.rmtree(path)
            self.update(record,staged_input_cleanup={'complete':not path.exists(),'observed_at':time.time()})
        self.update(record,reconciliation={**observation,'observed_at':time.time()},
            native_load_outcome=record.get('native_load_outcome','unknown'))
        return self.get(record['job_id'],record['owner'],record['endpoint_id'])

    def acknowledge(self,record,observation,request):
        with self._maps_lock:
            known=self.workers.get(record['job_id'])
            if known and known[0].is_alive():raise BinlogArchiveError('The native replay worker is still active')
        if self.public(record)['state'] in {'dispatching','active','cancel_requested'}:
            raise BinlogArchiveError('The original native replay worker is still active')
        self.observe_utility(record)
        record=self.load(record['job_id'],record['owner'],record['endpoint_id'])
        if self.public(record)['state']!='unknown':raise BinlogArchiveError('Only an uncertain native replay needs target acknowledgement')
        if request.get('target_confirmation')!=self.target_identity(record) or request.get('observation_digest')!=digest(observation):
            raise BinlogArchiveError('Confirm the exact native target and current reconciliation facts')
        if record.get('native_process_termination_confirmed') is not True or observation.get('native_lock_free') is not True:
            raise BinlogArchiveError('Native process termination and the released native replay lock must be observed before acknowledging this target')
        self.update(record,target_state_acknowledged_at=time.time(),target_state_acknowledgement=observation)
        self.release_fence(record)
        return self.get(record['job_id'],record['owner'],record['endpoint_id'])
