"""Durable owner-bound local clone jobs; SQL replies never imply file rollback."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

import psutil

from ..operations.fileio import durable_replace, exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.mysql_family.mysql_clone import CloneError, capture, clone_statement, correlated, destination, observation, operation_key, options, rows, thread_identity, thread_matches


ACTIVE={'dispatching','active','cancel_requested'}
FIELDS=('job_id','owner','endpoint_id','configuration','operation','options','source','donor','created_at','expires_at','native_path_bytes','execution_host','warnings')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


def review_digest(record):
    return digest({key:record.get(key) for key in FIELDS})


def job_identity(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (TypeError,ValueError,AttributeError):raise CloneError('Invalid native clone job identity') from None
    return value


class MySQLCloneJobs:
    _maps={}
    _maps_lock=threading.RLock()

    def __init__(self,path,root):
        self.path,self.root=Path(path),Path(root).resolve()
        self.lock=threading.RLock()
        self.worker_identity=[os.getpid(),psutil.Process().create_time()]
        with self._maps_lock:self.workers=self._maps.setdefault(str(self.path.resolve()),{})

    def scope(self,owner,endpoint):
        if type(owner) is not int or owner<=0:raise CloneError('Invalid native clone owner identity')
        job_identity(endpoint)
        return self.root/str(owner)/endpoint

    def directory(self,record):
        return self.scope(record['owner'],record['endpoint_id'])/job_identity(record['job_id'])

    @contextmanager
    def store(self,job_id):
        root=Path(str(self.path)+'.jobs');root.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(root)
        path=root/(job_identity(job_id)+'.json')
        with self.lock:
            descriptor=os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with exclusive_file_lock(descriptor):yield JsonOperationStore(path)
            finally:os.close(descriptor)

    @staticmethod
    def record(state,job_id,owner,endpoint):
        if type(owner) is not int or owner<=0:raise CloneError('Invalid native clone owner identity')
        record=state.get('mysql_clone_jobs',{}).get(job_id)
        if record is None or record['owner']!=owner or record['endpoint_id']!=endpoint:
            raise CloneError('Native clone job is unavailable for this owner and endpoint')
        return record

    def load(self,job_id,owner,endpoint):
        self.scope(owner,endpoint)
        with self.store(job_id) as store:return self.record(store.read(),job_id,owner,endpoint)

    def public(self,record,*,summary=False):
        result=deepcopy({key:value for key,value in record.items() if key not in {'owner','configuration'}})
        result['automatic_retry']=False
        if summary:result.pop('native_observation',None)
        if record['state'] in ACTIVE:
            pid,created=record.get('worker_identity',(None,None))
            try:alive=psutil.Process(pid).create_time()==created if pid is not None else False
            except psutil.Error:alive=False
            with self._maps_lock:known=self.workers.get(record['job_id'])
            if not alive or record.get('worker_identity')==self.worker_identity and not (known and known[0].is_alive()):
                result.update(state='unknown',observation_blocker='The application worker stopped without a terminal receipt. The server clone may still be running; reconcile its native state before further action.')
        return result

    def get(self,job_id,owner,endpoint):return self.public(self.load(job_id,owner,endpoint))

    def update(self,record,**values):
        with self.store(record['job_id']) as store:
            def change(state):
                current=self.record(state,record['job_id'],record['owner'],record['endpoint_id'])
                current.update(deepcopy(values),updated_at=time.time())
            store.change(change)

    def list(self,owner,endpoint,offset=0,limit=25):
        scope=self.scope(owner,endpoint)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise CloneError('Invalid native clone receipt page')
        index=scope/'index'
        entries=sorted((path for path in index.iterdir() if not path.name.startswith('.')),reverse=True) if index.is_dir() else []
        result=[];unavailable=[]
        for entry in entries[offset:offset+limit]:
            job_id=entry.name.split('_',1)[-1]
            try:result.append(self.public(self.load(job_id,owner,endpoint),summary=True))
            except CloneError:unavailable.append(job_id)
        return {'jobs':result,'offset':offset,'limit':limit,'total':len(entries),'more':offset+limit<len(entries),'unavailable_job_ids':unavailable}

    def review(self,request,owner,endpoint,source,configuration,connection,*,runtime_limit=None,donor=None):
        if not isinstance(request,dict) or set(request)!={'options'}:raise CloneError('Invalid native clone review')
        selected=options(request['options'])
        if ('donor' in selected)!=(donor is not None):raise CloneError('Native donor admission is required for a remote clone')
        if runtime_limit is not None and (type(runtime_limit) is not int or not 1<=runtime_limit<=2147483647):
            raise CloneError('Invalid application native clone runtime policy')
        if runtime_limit is not None and (selected['timeout_seconds'] is None or selected['timeout_seconds']>runtime_limit):
            raise CloneError('Application policy limits each clone client to '+str(runtime_limit)+' seconds')
        size=destination(connection,selected['destination'],source)
        record={'job_id':str(uuid.uuid4()),'owner':owner,'endpoint_id':endpoint,'configuration':configuration,
            'operation':'remote_clone' if donor else 'local_clone','options':selected,'source':deepcopy(source),'donor':deepcopy(donor),'native_path_bytes':size,
            'created_at':time.time(),'expires_at':time.time()+600,'state':'reviewed','cancel_requested':False,
            'execution_host':{'kind':'database-server','operating_system':source['operating_system']},
            'recovery_drill_complete':False,'files_verified':False,
            'warnings':['The native clone plugin copies supported InnoDB data and the data dictionary. It is not a complete backup of other storage engines, configuration, binary logs or external encryption keys.',
                'The destination is on the database-server host, must not exist, and must be outside its active data directory. Native BACKUP_ADMIN and operating-system access govern execution.',
                'Clone creates nontransactional files. Failure, cancellation or a lost reply can leave partial files; SQL rollback cannot remove them.',
                'Native completion and a successful independent recovery drill have separate receipts. External administration is not fenced by the application lock.',
                'Cancellation requires a live native performance-schema thread identity. A client timeout or disconnect does not establish that the server stopped copying.']}
        if donor is not None:
            record['warnings'].extend([
                'The recipient server authenticates directly to the selected donor using delegated credentials. Its clone_valid_donor_list and native CLONE_ADMIN permission, and the donor BACKUP_ADMIN permission, govern execution.',
                'The donor SQL connection verifies the registered identity. The recipient clone protocol identifies its source by the reviewed TCP address; it does not attest that source UUID to the application.',
                'Native CLONE supports required TLS and recipient-side CA verification, but not donor hostname verification. The recipient clone_ssl_ca/cert/key settings govern that channel.'])
        record['review_digest']=review_digest(record)
        scope=self.scope(owner,endpoint)
        for path in (self.root,self.root/str(owner),scope,scope/'index'):
            path.mkdir(parents=True,exist_ok=True,mode=0o700);private_directory(path)
        with self.store(record['job_id']) as store:
            store.change(lambda state:state.setdefault('mysql_clone_jobs',{}).update({record['job_id']:record}))
        entry=scope/'index'/(f'{time.time_ns():020d}_'+record['job_id']);staging=entry.with_name('.'+entry.name)
        with staging.open('xb') as stream:private_file(staging);stream.flush();os.fsync(stream.fileno())
        durable_replace(staging,entry)
        return self.public(record)

    def start(self,request,owner,endpoint,source,configuration,transport):
        worker=None;claimed=False;signal=threading.Event()
        try:
            if not isinstance(request,dict) or set(request)!={'job_id','review_digest','confirmed'} or request['confirmed'] is not True:
                raise CloneError('Explicit confirmation of the native clone review is required')
            self.scope(owner,endpoint)
            with self.store(request['job_id']) as store:
                def claim(state):
                    nonlocal claimed
                    record=self.record(state,request['job_id'],owner,endpoint)
                    if record['review_digest']!=request['review_digest']:raise CloneError('Native clone review fingerprint changed')
                    if record['state']!='reviewed':return deepcopy(record)
                    if transport is None:raise CloneError('Native clone dispatch requires fresh owned connections')
                    if review_digest(record)!=record['review_digest']:raise CloneError('Native clone review fingerprint changed')
                    if record['expires_at']<time.time() or record['configuration']!=configuration or record['source']!=source:
                        raise CloneError('Native clone target or registration changed; prepare a new review')
                    if record.get('donor')!=getattr(transport,'donor_identity',None):
                        raise CloneError('Native clone donor identity or policy changed; prepare a new review')
                    if destination(transport.worker,record['options']['destination'],source)!=record['native_path_bytes']:
                        raise CloneError('Native filesystem encoding changed after review')
                    record.update(state='dispatching',worker_identity=self.worker_identity,started_at=time.time())
                    claimed=True;return deepcopy(record)
                record=store.change(claim)
            if not claimed:
                if transport is not None:transport.close()
                return self.get(record['job_id'],owner,endpoint)
            worker=threading.Thread(target=self.run,args=(record,transport,signal),daemon=True,name='mysql-clone-'+record['job_id'])
            with self._maps_lock:self.workers[record['job_id']]=(worker,signal)
            worker.start()
            return self.get(record['job_id'],owner,endpoint)
        except BaseException:
            if worker is None or worker.ident is None:
                if transport is not None:transport.close()
                if claimed:self.update(record,state='not_dispatched',error_type='worker_start_failed')
            raise

    def cancel(self,job_id,owner,endpoint):
        self.scope(owner,endpoint)
        with self.store(job_id) as store:
            def change(state):
                record=self.record(state,job_id,owner,endpoint)
                if record['state'] in ACTIVE:record.update(cancel_requested=True,state='cancel_requested')
                elif record['state']=='reviewed':record.update(cancel_requested=True,state='cancelled')
            store.change(change)
        with self._maps_lock:
            if job_id in self.workers:self.workers[job_id][1].set()
        return self.get(job_id,owner,endpoint)

    def reconcile(self,record,source,connection):
        if source['server_uuid']!=record['source']['server_uuid'] or source['version']!=record['source']['version']:
            raise CloneError('Native clone reconciliation reached another server')
        if record['state'] in ACTIVE and self.public(record)['state']!='unknown':
            raise CloneError('The application worker is still observing this clone')
        observed=observation(connection)
        observed['job_correlated']=bool(record.get('native_thread') and correlated(observed,record))
        values={'reconciliation_observation':observed}
        if record.get('native_thread') and correlated(observed,record) and observed['status']['state'] in {'Completed','Failed'}:
            values.update(state='native_completed' if observed['status']['state']=='Completed' and observed['status']['error_number']==0 else 'native_failed',
                          native_completion_observed=True,finished_at=time.time(),files_verified=False,recovery_drill_complete=False)
        self.update(record,**values)
        return self.get(record['job_id'],record['owner'],record['endpoint_id'])

    def run(self,record,transport,signal):
        sql_worker=None;done=threading.Event();outcome={};lock='sr:clone:'+record['source']['server_uuid'];locked=False
        try:
            directory=self.directory(record);directory.mkdir(parents=True,exist_ok=False,mode=0o700);private_directory(directory)
            if capture(transport.worker)!=record['source'] or capture(transport.monitor)!=record['source']:
                raise CloneError('Native clone identity or policy changed before dispatch')
            if record.get('donor') is not None and capture(transport.donor)!=record['donor']['native_identity']:
                raise CloneError('Native clone donor identity or policy changed before dispatch')
            identity=thread_identity(transport.worker)
            prior=observation(transport.monitor)
            record['native_thread']=identity
            record['baseline_clone_id']=(prior.get('status') or {}).get('id')
            record['baseline_operation_key']=operation_key(prior.get('status'))
            locked=rows(transport.worker,'SELECT GET_LOCK(%s,0) AS acquired',(lock,))[0]['acquired']==1
            if not locked:raise CloneError('Another application clone holds the native server lock')
            try:can_cancel=thread_matches(transport.monitor,identity)
            except Exception:can_cancel=False
            self.update(record,native_thread=identity,baseline_clone_id=record['baseline_clone_id'],baseline_operation_key=record['baseline_operation_key'],
                        cancel_capability={'available':can_cancel,'identity':'native PFS thread ID and processlist ID'})
            def bind(observed,acknowledged=False):
                if not correlated(observed,record,allow_new=True):return False
                if record.get('native_operation_key') is None:
                    if not acknowledged:
                        try:
                            if not thread_matches(transport.monitor,identity):return False
                        except Exception:return False
                    # Local clone IDs can be reused. Freeze the native start
                    # epoch while this exact connection is still owned; later
                    # reconciliation cannot attach a newer operation to it.
                    record['native_operation_key']=operation_key(observed['status'])
                    self.update(record,native_operation_key=record['native_operation_key'])
                return correlated(observed,record)
            if self.load(record['job_id'],record['owner'],record['endpoint_id'])['cancel_requested']:signal.set()
            if signal.is_set():self.update(record,state='cancelled',statement_dispatched=False);return
            self.update(record,state='active',statement_dispatched=True)
            def execute():
                try:
                    if record.get('donor') is None:
                        rows(transport.worker,'CLONE LOCAL DATA DIRECTORY = %s',(record['options']['destination'],))
                    else:clone_statement(transport.worker,record,transport.password)
                    outcome['acknowledged']=True
                except Exception as error:
                    number=getattr(error,'errno',None);sqlstate=getattr(error,'sqlstate',None)
                    outcome.update(acknowledged=False,error_type=type(error).__name__,error_number=number,sqlstate=sqlstate,
                        native_refusal=type(number) is int and number>=1000 and not 2000<=number<3000 and isinstance(sqlstate,str))
                finally:done.set()
            sql_worker=threading.Thread(target=execute,daemon=True,name='mysql-clone-sql-'+record['job_id']);sql_worker.start()
            started=time.monotonic();cancel_sent=False
            while not done.wait(.25):
                current=self.load(record['job_id'],record['owner'],record['endpoint_id'])
                if current['cancel_requested']:signal.set()
                duration=record['options']['timeout_seconds']
                if duration is not None and time.monotonic()-started>=duration:signal.set()
                observed=observation(transport.monitor)
                self.update(record,native_observation=observed if bind(observed) else {'available':False,'reason':'Native clone status does not identify this job'},
                            progress={'elapsed_seconds':round(time.monotonic()-started,3)})
                if signal.is_set() and not cancel_sent:
                    try:
                        if capture(transport.monitor)['server_uuid']!=record['source']['server_uuid'] or not thread_matches(transport.monitor,identity):
                            raise CloneError('Native cancellation target identity is unavailable')
                        rows(transport.monitor,'KILL QUERY '+identity['connection_id']);cancel_sent=True
                        self.update(record,cancel_delivery={'acknowledged':True,'server_query_stopped':False})
                    except Exception as error:
                        cancel_sent=True;self.update(record,cancel_delivery={'acknowledged':False,'error_type':type(error).__name__})
            sql_worker.join()
            observed=observation(transport.monitor)
            matched=bind(observed,outcome.get('acknowledged') is True)
            observed['job_correlated']=matched
            native_complete=matched and observed['status']['state']=='Completed' and observed['status']['error_number']==0
            native_failed=matched and observed['status']['state']=='Failed'
            state='native_completed' if native_complete else 'cancelled' if native_failed and signal.is_set() else 'native_failed' if native_failed else 'acknowledged' if outcome.get('acknowledged') else 'refused' if outcome.get('native_refusal') else 'unknown'
            self.update(record,state=state,sql_observation=outcome,native_observation=observed,
                        native_completion_observed=native_complete or native_failed,files_verified=False,recovery_drill_complete=False,
                        target_files_may_exist=True,filesystem_rolled_back_by_sql=False,finished_at=time.time())
        except Exception as error:
            self.update(record,state='unknown' if sql_worker is not None else 'not_dispatched',error_type=type(error).__name__,
                        **({'error_reason':str(error)} if isinstance(error,CloneError) else {}))
        finally:
            # Do not race a native DBAPI call with connection disposal. If this
            # observer failed while SQL is active, the SQL thread owns release.
            def release():
                if locked:
                    try:rows(transport.worker,'SELECT RELEASE_LOCK(%s)',(lock,))
                    except Exception:pass
                transport.close()
            if sql_worker is not None and sql_worker.is_alive():
                def finish():sql_worker.join();release()
                threading.Thread(target=finish,daemon=True,name='mysql-clone-release-'+record['job_id']).start()
            else:release()
            with self._maps_lock:self.workers.pop(record['job_id'],None)

    def close(self):
        with self._maps_lock:workers=list(self.workers.values())
        for _worker,signal in workers:signal.set()
        for worker,_signal in workers:worker.join(timeout=5)
