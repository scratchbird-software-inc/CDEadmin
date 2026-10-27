"""Private full-table verification workers; never dispatch data repair."""
from copy import deepcopy
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import uuid

from ..providers.mysql_family import mysql_drift as native
from ..providers.mysql_family import mysql_content_search as catalog
from ..providers.mysql_family.mysql_catalog import identifier
from ..providers.mysql_family.mysql_clone import thread_matches
from .mysql_content_search import public_error
from .mysql_online_replicas import sample


class DriftJob:
    def __init__(self,scope,observers,controls,schemas,tables,selected,authorize,directory):
        self.id,self.scope=str(uuid.uuid4()),scope
        self.observers,self.controls,self.schemas,self.tables=observers,controls,schemas,tables
        self.selected,self.authorize,self.directory=selected,authorize,Path(directory)
        self.lock,self.cancelled=threading.RLock(),threading.Event()
        self.created,self.finished,self.closed=time.monotonic(),None,False
        self.state,self.stage='running','admitted'
        self.coverage=[{**t,'state':'uncompared'} for t in tables]
        self.positions=[];self.release=[];self.cancellation={};self.error={}
        self.disk,self.peak,self.written=0,0,0
        self.authorization_clock=0
        self.worker=threading.Thread(target=self.run,daemon=True,name='mysql-full-data-drift')
        self.timer=threading.Timer(selected['seconds'],lambda:self.stop('deadline'));self.timer.daemon=True

    def snapshot(self):
        with self.lock:
            return {'job_id':self.id,'state':self.state,'stage':self.stage,'terminal':self.finished is not None,
                'identities':[{**{k:catalog.display(v) for k,v in o.identity.items()},'native_interface':o.native_interface} for o in self.observers],
                'schemas':self.schemas,'coverage':deepcopy(self.coverage),'positions':deepcopy(self.positions),'release':deepcopy(self.release),
                'cancellation':dict(self.cancellation),'error':dict(self.error),'options':dict(self.selected),
                'disk_peak_bytes':str(self.peak),'sort_bytes_written':str(self.written),
                'elapsed_seconds':round((self.finished or time.monotonic())-self.created,3),
                'repair_dispatched':False,'automatic_retry':False,
                'retention':'Private process memory for five minutes after completion; temporary sort files removed at completion. No SQL/history persistence.',
                'coverage_basis':'All logical columns and all rows of selected persistent base-table pairs. Catalog visibility is permission filtered; unselected/invisible tables remain unknown.'}

    def update(self,record=None,**values):
        with self.lock:
            if record is None:
                for k,v in values.items():setattr(self,k,v)
            else:record.update(values)

    def checkpoint(self):
        if self.cancelled.is_set():raise native.Error('Full-table comparison was cancelled')
        if time.monotonic()-self.created>=self.selected['seconds']:raise native.Error('Full-table comparison runtime bound reached')
        now=time.monotonic()
        if now-self.authorization_clock>=.5:
            self.authorize();self.authorization_clock=now

    def reserve(self,size):
        self.checkpoint()
        if self.disk+size>self.selected['disk_mib']*1024*1024:raise native.Error('Full-table comparison sort-disk bound reached')
        self.disk+=size;self.written+=max(size,0);self.peak=max(self.peak,self.disk)

    def stop(self,reason='user'):
        self.cancelled.set()
        with self.lock:
            if self.closed:return
            self.cancellation={'requested':True,'reason':reason,'native':[]}
            for observer,control in zip(self.observers,self.controls):
                reply={'server_uuid':observer.identity['server_uuid'],'kill_sent':False}
                try:
                    current=control.query('SELECT @@server_uuid AS server_uuid')[0]
                    identity={k:str(observer.identity[k]) if observer.identity[k] is not None else None for k in ('connection_id','thread_id')}
                    if current['server_uuid']==observer.identity['server_uuid'] and thread_matches(control.connection,identity):
                        control.query('KILL QUERY '+identity['connection_id']);reply['kill_sent']=True
                except Exception as error:reply.update(public_error(error))
                self.cancellation['native'].append(reply)

    def prepare(self):
        self.update(stage='acquiring-source-read-lock')
        self.checkpoint();self.observers[0].query('FLUSH TABLES WITH READ LOCK')
        self.positions=[native.position(self.observers[0])]
        if self.selected['replica']:
            self.update(stage='waiting-for-source-GTID')
            source=self.positions[0]
            if source['gtid_mode']!='ON':raise native.Error('Replica alignment requires native GTID mode ON')
            expected=self.observers[0].identity['server_uuid']
            _identity,status=sample(self.observers[1].connection,self.selected['channel'],expected)
            if status['io_running']!='Yes' or status['sql_running']!='Yes' or status['last_io_errno'] or status['last_sql_errno']:
                raise native.Error('The admitted replica channel is stopped or has native errors')
            if self.observers[1].query('SELECT WAIT_FOR_EXECUTED_GTID_SET(%s,%s) AS waited',
                    (source['gtid_executed'],max(1,int(self.selected['seconds']-(time.monotonic()-self.created)))))[0]['waited']!=0:
                raise native.Error('The replica did not reach the recorded source GTID set')
        self.checkpoint();self.update(stage='acquiring-target-read-lock')
        self.observers[1].query('FLUSH TABLES WITH READ LOCK');self.positions.append(native.position(self.observers[1]))
        if self.selected['replica']:
            _identity,status=sample(self.observers[1].connection,self.selected['channel'],self.observers[0].identity['server_uuid'])
            if status['sql_running']!='Yes' or status['last_sql_errno']:raise native.Error('Replica channel changed before snapshot admission')
            subset=self.observers[1].query('SELECT GTID_SUBSET(%s,@@GLOBAL.gtid_executed) AS admitted',(self.positions[0]['gtid_executed'],))[0]['admitted']
            if subset!=1:raise native.Error('The target no longer attests the source GTID boundary')
            self.positions[1]['reviewed_source_gtid_applied']=True
            self.positions[1]['channel_observation']=status
        for observer in self.observers:
            observer.query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            observer.query('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        sources=[];columns=0
        self.update(stage='pinning-complete-table-scopes')
        for item,report in zip(self.tables,self.coverage):
            self.checkpoint();pair=[]
            for side,observer in enumerate(self.observers):
                table=item['source_table' if side==0 else 'target_table'];schema=self.schemas[side]
                # SELECT * also checks columns invisible to an incomplete
                # privilege-filtered catalog. Explicit columns include native
                # invisible/GIPK columns in the actual full scan.
                observer.query('SELECT * FROM '+identifier(schema)+'.'+identifier(table)+' WHERE 0',limit=1)
                source=native.describe(observer,schema,table)
                if source['fingerprint']!=item['source_fingerprint' if side==0 else 'target_fingerprint']:
                    raise native.Error('A reviewed table structure or native identity changed')
                columns+=len(source['columns'])
                if columns>16384:raise native.Error('The selected metadata scope exceeds 16384 total columns')
                if self.selected['consistency']=='innodb_snapshot' and source['engine']!='InnoDB':
                    raise native.Error('Non-InnoDB tables require the explicitly server-locked scan')
                if source['engine'] not in native.LOCAL_ENGINES:raise native.Error('This engine has no admitted local read-lock consistency profile')
                pair.append(source)
            if native.shape(pair[0])!=native.shape(pair[1]):
                self.update(report,state='schema-different',reason='Logical column names, order, types, generation or collations differ')
                sources.append(None)
            else:
                self.update(report,state='ready',columns=len(pair[0]['columns']),source_key=pair[0]['key'],target_key=pair[1]['key'],
                    engines=[s['engine'] for s in pair])
                sources.append(pair)
        if self.selected['consistency']=='innodb_snapshot':
            for observer in self.observers:observer.query('UNLOCK TABLES')
            self.update(stage='native-snapshots-established')
        return sources

    def run(self):
        try:
            self.directory.mkdir(mode=0o700,parents=True,exist_ok=False)
            # PID creation binding lets a future worker remove only abandoned
            # private sort files; never another live process's files.
            import psutil
            (self.directory/'owner.json').write_text(__import__('json').dumps({'pid':os.getpid(),'created':psutil.Process().create_time()}))
            sources=self.prepare()
            for index,(pair,report) in enumerate(zip(sources,self.coverage)):
                if pair is None:continue
                self.checkpoint();self.update(report,state='scanning')
                with tempfile.TemporaryDirectory(dir=self.directory) as directory:
                    runs=[]
                    for side,observer in enumerate(self.observers):
                        self.update(stage='scanning-'+('source' if side==0 else 'target'))
                        run=native.Runs(Path(directory)/str(side),self.reserve);runs.append(run)
                        native.scan(observer,self.schemas[side],pair[side],run,self.checkpoint,
                            lambda count,side=side:self.update(report,**{('source_scanned_rows' if side==0 else 'target_scanned_rows'):str(count)}))
                    self.update(stage='comparing-complete-multisets')
                    remaining=max(0,self.selected['examples']-sum(len(r.get('examples',[])) for r in self.coverage))
                    self.update(report,**native.compare(*runs,remaining,self.checkpoint))
                self.disk=0
            self.state='completed' if all(r['state'] in {'matched','different'} for r in self.coverage) else 'partial'
        except Exception as error:
            self.error={**public_error(error),'reason':str(error) if isinstance(error,native.Error) else 'Native comparison did not complete'}
            self.state='cancelled' if self.cancelled.is_set() else 'incomplete'
            for report in self.coverage:
                if report['state'] in {'scanning','ready'}:self.update(report,state='incomplete')
        finally:
            self.timer.cancel()
            with self.lock:
                for observer,control in zip(self.observers,self.controls):
                    release={'server_uuid':observer.identity['server_uuid'],'unlock_reply':False,'rollback_reply':False}
                    try:observer.query('UNLOCK TABLES');release['unlock_reply']=True
                    except Exception as error:
                        release.update(public_error(error))
                        try:
                            identity={k:str(observer.identity[k]) if observer.identity[k] is not None else None for k in ('connection_id','thread_id')}
                            if control.identity['server_uuid']==observer.identity['server_uuid'] and thread_matches(control.connection,identity):
                                control.query('KILL CONNECTION '+identity['connection_id']);release['owned_connection_kill_sent']=True
                        except Exception as error:release['kill_error']=public_error(error)
                    try:observer.connection.rollback();release['rollback_reply']=True
                    except Exception as error:release['rollback_error']=public_error(error)
                    try:observer.close();release['session_disposed']=True
                    except Exception as error:release['close_error']=public_error(error)
                    try:control.close()
                    except Exception:pass
                    self.release.append(release)
                try:shutil.rmtree(self.directory);self.release.append({'private_sort_files_removed':True})
                except OSError:self.release.append({'private_sort_files_removed':False})
                self.closed=True;self.finished=time.monotonic();self.stage='terminal'


class DriftJobs:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.lock,self.jobs=threading.RLock(),{}
        self.stopped=threading.Event()
        import json,psutil
        for path in self.directory.iterdir():
            if not path.is_dir() or path.is_symlink():continue
            try:
                owner=json.loads((path/'owner.json').read_text())
                try:alive=psutil.Process(owner['pid']).create_time()==owner['created']
                except psutil.Error:alive=False
                if not alive:shutil.rmtree(path)
            except (OSError,ValueError,KeyError):continue
        self.reaper=threading.Thread(target=self.expire,daemon=True,name='mysql-drift-expiry');self.reaper.start()

    def prune(self):
        for key,job in list(self.jobs.items()):
            if job.finished and time.monotonic()-job.finished>300:
                with job.lock:job.coverage.clear();job.tables=[];job.positions.clear()
                del self.jobs[key]

    def expire(self):
        while not self.stopped.wait(15):
            with self.lock:self.prune()

    def start(self,*args):
        with self.lock:
            self.prune()
            if sum(not j.closed for j in self.jobs.values())>=4 or len(self.jobs)>=32:raise native.Error('Clear or wait for a previous private comparison')
            job=DriftJob(*args,self.directory/str(uuid.uuid4()));self.jobs[job.id]=job
            try:job.worker.start();job.timer.start()
            except BaseException:
                job.stop('worker-start-failed')
                if job.worker.ident is None:
                    for observer in [*job.observers,*job.controls]:observer.close()
                    del self.jobs[job.id]
                raise
            return job.snapshot()

    def get(self,scope,job_id):
        with self.lock:
            self.prune();job=self.jobs.get(job_id)
            if job is None or job.scope!=scope:raise native.Error('This owner-scoped comparison expired or is unavailable')
            return job

    def close(self):
        self.stopped.set();self.reaper.join(timeout=1)
        with self.lock:jobs=list(self.jobs.values())
        for job in jobs:
            if not job.closed:job.stop('application-close')
        for job in jobs:job.worker.join(timeout=12)
