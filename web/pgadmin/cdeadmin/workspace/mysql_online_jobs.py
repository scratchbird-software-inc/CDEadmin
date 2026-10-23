"""Durable DDN ALTER jobs; native replies, progress and cancellation stay separate."""
from copy import deepcopy
import os
import platform
import threading
import time

import psutil

from .firebird_schema_plan import digest
from .mysql_online_policy import policy
from ..providers.mysql_family.mysql_clone import rows, thread_identity, thread_matches


class OnlineRuntime:
    def __init__(self, applications, review, owner, binding, worker, control, dispose, authorize):
        self.applications,self.review,self.owner,self.binding=applications,review,owner,binding
        self.worker,self.control,self.dispose,self.authorize=worker,control,dispose,authorize
        self.lock,self.done,self.cancelled=threading.RLock(),threading.Event(),threading.Event()
        self.closed=False;self.native_identity=None
        self.selected=policy(review['plan']['operations'][0]['execution'])
        self.started=time.monotonic();self.reason=None
        self.thread=threading.Thread(target=self.run,daemon=True,name='mysql-controlled-ddl')
        self.observer=threading.Thread(target=self.observe,daemon=True,name='mysql-controlled-ddl-observer')

    def update(self, **values):
        with self.applications._store() as store:
            def change(state):
                record=self.applications._record(state,self.review['review_id'],self.owner,self.binding)
                record.setdefault('controlled_job',{}).update(deepcopy(values))
            store.change(change)

    def event(self, stage, **facts):
        with self.applications._store() as store:
            def change(state):
                record=self.applications._record(state,self.review['review_id'],self.owner,self.binding)
                job=record.setdefault('controlled_job',{})
                events=job.setdefault('events',[])
                events.append({'stage':stage,'observed_at':time.time(),**facts})
                if len(events)>120:events.pop(0);job['events_truncated']=True
            store.change(change)

    def checkpoint(self):
        self.authorize()
        if self.cancelled.is_set():raise ValueError('Controlled ALTER cancelled before native dispatch')
        if time.monotonic()-self.started>=self.selected['timeout_seconds']:
            raise ValueError('Controlled ALTER runtime budget expired before native dispatch')

    def execute(self, cursor, encoded, record):
        self.checkpoint()
        if self.selected['method']=='native':
            self.event('native-alter-dispatched',algorithm=self.selected['algorithm'],lock=self.selected['lock'])
            cursor.execute(encoded)
        else:
            from ..providers.mysql_online_copy import execute
            execute(self,cursor,record)

    def stop(self, reason='user'):
        with self.lock:
            if self.closed or self.done.is_set():return
            self.cancelled.set();self.reason=reason
            self.update(cancel_requested=True,cancel_reason=reason)
            root=getattr(self,'copy_workspace',None)
            if root is not None and root.is_dir():(root/'cancel').touch(mode=0o600,exist_ok=True)
            try:
                uuid=rows(self.control,'SELECT @@server_uuid AS server_uuid')[0]['server_uuid']
                if uuid!=self.review['plan']['server_uuid']:raise ValueError('Cancellation reached another native server')
                if self.native_identity and thread_matches(self.control,self.native_identity):
                    rows(self.control,'KILL QUERY '+self.native_identity['connection_id'])
                    self.event('cancellation-native-kill-sent')
                else:self.event('cancellation-native-thread-unconfirmed')
                child=getattr(self,'utility_child',None)
                if child is not None and child.poll() is None:child.terminate()
            except Exception as error:self.event('cancellation-unconfirmed',error_type=type(error).__name__,error_code=getattr(error,'errno',None))

    def observe(self):
        last=None
        while not self.done.wait(.5):
            if time.monotonic()-self.started>=self.selected['timeout_seconds'] and not self.cancelled.is_set():self.stop('deadline')
            # One control protocol owner. Holding the runtime lock pins the
            # worker connection until thread verification and cancellation end.
            with self.lock:
                if self.closed:break
                try:
                    self.authorize()
                    if self.selected['method']=='pt-online-schema-change':
                        from ..providers.mysql_online_copy import observe
                        observe(self)
                    stages=rows(self.control,'SELECT EVENT_NAME,WORK_COMPLETED,WORK_ESTIMATED '
                        'FROM performance_schema.events_stages_current WHERE THREAD_ID=%s LIMIT 1',
                        (int(self.native_identity['thread_id']),)) if self.native_identity.get('thread_id') else []
                    value=[{str(k):str(v) if v is not None else None for k,v in item.items()} for item in stages]
                    if value!=last:
                        self.event('native-stage-observation',rows=value,
                            coverage='Native current stage only; disabled instruments and absent stages provide no progress estimate')
                        last=value
                except Exception as error:
                    if last!='unavailable':self.event('native-stage-unavailable',error_code=getattr(error,'errno',None),error_type=type(error).__name__)
                    last='unavailable'

    def run(self):
        request={k:self.review[k] for k in ('review_id','review_digest')};request['confirmed']=True
        try:
            self.native_identity=thread_identity(self.worker)
            self.update(state='running',native_thread=self.native_identity,native_interface=type(self.worker).__name__)
            self.observer.start()
            def execute(record):
                from ..providers.mysql_schema_application import apply_review
                return apply_review(self.worker,record,runtime=self)
            result=self.applications.apply(request,self.owner,self.binding,execute)
            self.update(state='terminal',native_outcome=result['state'],finished_at=time.time(),
                cancellation_requested=self.cancelled.is_set(),transactional_rollback_available=False)
        except Exception as error:
            self.update(state='unknown',error_type=type(error).__name__,finished_at=time.time(),automatic_retry=False)
        finally:
            self.done.set()
            if self.observer.ident is not None:self.observer.join(timeout=12)
            with self.lock:
                self.closed=True
                try:self.dispose(self.worker)
                finally:
                    try:self.dispose(self.control)
                    finally:
                        secret=getattr(self,'copy_secret',None)
                        if secret is not None:secret.close()
                        for _item,connection,dispose in getattr(self,'copy_monitors',[]):dispose(connection)


class OnlineJobs:
    def __init__(self):self.lock=threading.RLock();self.jobs={}

    def start(self, applications, request, owner, binding, worker, control, dispose, authorize,copy=None):
        runtime=None
        try:
            if not isinstance(request,dict) or set(request)!={'review_id','review_digest','confirmed'} or request['confirmed'] is not True:
                raise ValueError('Explicit confirmation of the controlled DDN review is required')
            review=applications.get(request['review_id'],owner,binding)
            if review['review_digest']!=request['review_digest']:raise ValueError('The controlled ALTER review changed')
            operations=review['plan']['operations']
            if len(operations)!=1 or not policy(operations[0].get('execution')):
                raise ValueError('Prepare one controlled table ALTER in the native DDN workflow')
            with self.lock:
                self.jobs={key:value for key,value in self.jobs.items() if not value.done.is_set()}
                key=(owner,binding,review['review_id'])
                if key in self.jobs or review['state']!='reviewed':return status(applications,review['review_id'],owner,binding)
                if sum(not r.done.is_set() for r in self.jobs.values())>=16:raise ValueError('Controlled ALTER worker capacity reached')
                # A cross-process durable start claim prevents duplicate workers
                # even while the schema review has not reached native dispatch.
                with applications._store() as store:
                    def claim(state):
                        record=applications._record(state,review['review_id'],owner,binding)
                        if record.get('controlled_job') is not None:return False
                        if time.time()>record['expires_at']:raise ValueError('Controlled ALTER review expired')
                        record['controlled_job']={'state':'starting','worker_pid':os.getpid(),
                            'worker_created':psutil.Process().create_time(),'created_at':time.time(),
                            'execution_host':{'kind':'application-host','platform':platform.system()},'events':[]}
                        return True
                    claimed=store.change(claim)
                if not claimed:return status(applications,review['review_id'],owner,binding)
                runtime=OnlineRuntime(applications,review,owner,binding,worker,control,dispose,authorize)
                if copy:
                    for name,value in copy.items():setattr(runtime,'copy_'+name,value)
                self.jobs[key]=runtime;runtime.thread.start()
            return status(applications,review['review_id'],owner,binding)
        except BaseException:
            if runtime is not None and runtime.thread.ident is None:
                runtime.update(state='unknown',error_type='worker-start-failed',automatic_retry=False)
                runtime.done.set()
                dispose(worker);dispose(control)
                if copy:
                    copy['secret'].close()
                    for _item,connection,release in copy.get('monitors',[]):release(connection)
            raise
        finally:
            if runtime is None:
                dispose(worker);dispose(control)
                if copy:
                    copy['secret'].close()
                    for _item,connection,release in copy.get('monitors',[]):release(connection)

    def cutover(self,applications,review_id,owner,binding):
        review=applications.get(review_id,owner,binding)
        with self.lock:runtime=self.jobs.get((owner,binding,review_id))
        if runtime is None or runtime.done.is_set() or review.get('controlled_job',{}).get('copy_stage')!='cutover-waiting':
            raise ValueError('Observe this owned copy at its cutover gate first')
        runtime.authorize();runtime.checkpoint()
        with runtime.lock:
            from .mysql_online_replicas import observe
            if not observe(runtime):raise ValueError('Registered replica lag is unknown, stopped or above the reviewed bound')
            (runtime.copy_workspace/'cutover.allowed').touch(mode=0o600,exist_ok=True)
            runtime.event('owner-cutover-admitted')
        return status(applications,review_id,owner,binding)

    def cancel(self, applications, review_id, owner, binding):
        applications.get(review_id,owner,binding)
        with self.lock:runtime=self.jobs.get((owner,binding,review_id))
        if runtime is None:raise ValueError('This process cannot cancel an unowned or stopped worker; observe its native state')
        runtime.stop()
        return status(applications,review_id,owner,binding)

    def close(self):
        with self.lock:jobs=list(self.jobs.values())
        for job in jobs:job.stop('application-close')
        for job in jobs:job.thread.join(timeout=12)


def status(applications, review_id, owner, binding):
    record=applications.get(review_id,owner,binding);job=record.get('controlled_job')
    if job and job['state'] in {'starting','running'}:
        try:alive=psutil.Process(job['worker_pid']).create_time()==job['worker_created']
        except psutil.Error:alive=False
        if not alive:job.update(state='unknown',worker_lost=True,automatic_retry=False)
    record['controlled_terminal']=bool(job and job['state'] in {'terminal','unknown'})
    return record
