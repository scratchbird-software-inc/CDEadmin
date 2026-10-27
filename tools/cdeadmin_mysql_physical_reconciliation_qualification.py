"""Native original-process controls across adapter upgrades and MERGE recovery."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch
import uuid


def qualify_reconciliation(app,output,oracle,container,port,password,selected,credentials,legacy_sources):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection,_run
    from pgadmin.model import db,Server
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as native
    legacy_path=Path(legacy_sources).resolve(strict=True)
    if legacy_path.stat().st_size>2097152:raise ValueError('Legacy native source fixture exceeds its bound')
    older=json.loads(legacy_path.read_text())
    assert set(older)==set(native.sources()) and all(isinstance(v,str) for v in older.values())
    assert older['physical']!=native.sources()['physical'],'Use the actual preceding native adapter source'
    root=Path(__file__).resolve().parents[1]
    paths=['tools/cdeadmin_mysql_physical_reconciliation_qualification.py','tools/cdeadmin_mysql_physical_qualification.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_transport.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py',
        'web/pgadmin/cdeadmin/workspace/mysql_recovery_connections.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run',
        'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},
        'legacy_source_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in older.items()},
        'legacy_fixture_sha256':hashlib.sha256(legacy_path.read_bytes()).hexdigest()}
    def host(*args):return _run(['docker','exec',container,*args]).stdout
    def python(code):
        r=subprocess.run(['docker','exec','-i',container,'python3','-'],input=code,text=True,capture_output=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr[-4000:])
        return json.loads(r.stdout)
    bootstrap=native.BOOTSTRAP+'\nload('+repr(native.sources())+')\n'
    def present(process):return python(bootstrap+"print(json.dumps(sys.modules['_cdeadmin_recovery_worker'].present("+repr(process)+')))' )
    def kill_supervisor(process):
        return python(bootstrap+"import signal\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].stop("+repr(process)+',signal.SIGKILL)))')
    with oracle.cursor() as cursor:
        cursor.execute('SELECT @@innodb_data_home_dir,@@innodb_undo_directory,@@innodb_directories')
        proof['native_default_storage_variables']=list(cursor.fetchone())
        assert None in proof['native_default_storage_variables']
        cursor.execute('CREATE DATABASE sr_merge_other')
        cursor.execute('CREATE TABLE sr_merge_other.m LIKE sr_osc.m')
        cursor.execute("INSERT INTO sr_merge_other.m VALUES(2,'native other child')")
        for table in ('merge_absolute','merge_escaping'):
            cursor.execute('CREATE TABLE sr_osc.'+table+' LIKE sr_osc.m')
            cursor.execute('ALTER TABLE sr_osc.'+table+' ENGINE=MRG_MYISAM UNION=(sr_osc.m,sr_merge_other.m) INSERT_METHOD=LAST')

    class Interface:
        def __init__(self,use_c):
            self.use_c=use_c;self.checks=[];self.runtimes=[];self.attached=None
            self.sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
            with app.test_request_context('/'):self.owner=Server.query.get(self.sid).user_id
            self.client=app.test_client()
            with self.client.session_transaction() as s:s['_user_id'],s['_fresh']=str(self.owner),True
            self.url=endpoint(app,self.sid)
        def post(self,action,body,refused=False):
            reply=self.client.post(self.url,json={'action':'mysql_physical_'+action,'request':body});value=reply.get_json()
            if refused:assert not value.get('success'),value;return value
            if reply.status_code!=200 or not value.get('success'):
                (output/'reconciliation-api-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                raise AssertionError('Native reconciliation API failed; inspect retained failure')
            return value['data']
        def review(self,phase,parent=None,**extra):return self.post('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent,**extra},'credentials':credentials})
        def start(self,ticket):return self.post('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
        def wait(self,ticket,running=False,ended=False):
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=self.post('reconcile',{'job_id':ticket['job_id'],'credentials':credentials});remote=value.get('remote_observation') or {}
                if running and value['recovery_running']:return value
                if ended and remote.get('process_termination_confirmed') and remote.get('runtime_process_live') is False:return value
                if not running and not ended and value['file_verification_confirmed']:return value
                if remote.get('error_type'):
                    (output/'reconciliation-native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                    (output/'reconciliation-native-output.json').write_text(json.dumps(self.post('output',{'job_id':ticket['job_id'],'credentials':credentials}),indent=2)+'\n')
                    raise AssertionError('Native reconciliation operation failed')
                time.sleep(.15)
            raise TimeoutError('Native reconciliation operation did not reach its selected state')
        def phase(self,name,parent=None):return self.wait(self.start(self.review(name,parent)))
        def copied(self):
            base=self.phase('backup');prepared=self.phase('prepare',base['job_id']);return base,self.phase('copy_back',prepared['job_id'])
        def editor(self,runtime):
            ticket=self.post('connection_review',{'job_id':runtime['job_id'],'name':'Native MERGE recovered '+str(self.use_c)+' '+runtime['job_id'][:8],'credentials':credentials})
            self.attached=self.post('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
            post=lambda action,**body:query_post(self.client,endpoint(app,self.attached['server_id']),self.attached['database_target_id'],action,**body)
            session=post('open_session',language_profile='mysql-sql',history_sensitive=True)['session_id']
            return post,session
        def detach(self):
            if self.attached:self.post('connection_detach',{'server_id':self.attached['server_id']});self.attached=None

    cases=[Interface(False),Interface(True)]
    try:
        for case in cases:
            guard=_root_connection('mysql',port)
            try:
                with guard.cursor() as cursor:
                    cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(23000+int(case.use_c),));cursor.execute('SAVEPOINT reconciliation_guard')
                _base,copied=case.copied()
                with patch.object(native,'sources',lambda:older):
                    ticket=case.review('recover',copied['job_id'],mysqld='/usr/sbin/mysqld',recovery_gtid_mode='ON',timeout_seconds=600)
                    case.start(ticket)
                case.legacy=case.wait(ticket,running=True);case.runtimes.append(case.legacy)
                assert case.legacy['program']['physical_sha256']==proof['legacy_source_sha256']['physical']
                with guard.cursor() as cursor:
                    cursor.execute('ROLLBACK TO SAVEPOINT reconciliation_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
                case.checks.append('actual-preceding-native-adapter-supervisor-survives-upgrade-with-user-transaction-and-savepoint-preserved')
            finally:guard.rollback();guard.close()

        oracle.autocommit=True
        with oracle.cursor() as cursor:cursor.execute('FLUSH TABLES')
        bodies={'merge_absolute':'/var/lib/mysql/sr_osc/m\n/old/absolute/sr_merge_other/m\n#INSERT_METHOD=LAST\n',
            'merge_escaping':'../../old/source/sr_osc/m\n../../old/source/sr_merge_other/m\n#INSERT_METHOD=LAST\n'}
        for table,body in bodies.items():host('python3','-c','from pathlib import Path;import sys;Path(sys.argv[1]).write_text(sys.argv[2])','/var/lib/mysql/sr_osc/'+table+'.MRG',body)
        for case in cases:
            with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.m SET note='native MyISAM'")
            base,copied=case.copied();assert len(base['remote_observation']['artifact']['merge_members'])==4
            runtime=case.wait(case.start(case.review('recover',copied['job_id'],mysqld='/usr/sbin/mysqld',recovery_gtid_mode='ON',recovery_mode='replay',recovery_port=33487+int(case.use_c),recovery_server_id=23000+int(case.use_c),timeout_seconds=600)),running=True)
            case.runtimes.append(runtime)
            with oracle.cursor() as cursor:cursor.execute("UPDATE sr_osc.m SET note='live source drift'")
            post,session=case.editor(runtime)
            try:
                for table in bodies:
                    rows=execute(post,session,'SELECT id,note FROM '+table+' ORDER BY id')['rows']
                    if rows!=[[1,'native MyISAM'],[2,'native other child']]:
                        (output/'merge-recovery-failure.json').write_text(json.dumps({'use_c':case.use_c,'table':table,'rows':rows},indent=2)+'\n')
                    assert rows==[[1,'native MyISAM'],[2,'native other child']]
                # Both parents share the same native children. Observe their
                # checkpoint before either INSERT changes those children.
                for index,table in enumerate(bodies):
                    execute(post,session,"INSERT INTO "+table+" VALUES("+str(100+int(case.use_c)*10+index)+",'private MERGE insert')")
                execute(post,session,'COMMIT')
                assert execute(post,session,'SELECT COUNT(*) FROM sr_merge_other.m')['rows']==[[3]]
            finally:post('close_session',session_id=session);case.detach()
            with oracle.cursor() as cursor:
                cursor.execute('SELECT note FROM sr_osc.m');assert cursor.fetchall()==[('live source drift',)]
                cursor.execute('SELECT COUNT(*) FROM sr_merge_other.m');assert cursor.fetchone()[0]==1
            for table,body in bodies.items():
                assert host('cat',selected['workspace']+'/'+runtime['job_id']+'/runtime-data/sr_osc/'+table+'.MRG')==body
            case.checks+=['absolute-and-escaping-MERGE-metadata-preserved-through-native-backup-prepare-copy-back-and-replay-recovery',
                'native-MERGE-reads-private-checkpoint-despite-live-source-drift-and-inserts-through-native-child-table-cache',
                'original-MyISAM-source-data-and-original-MERGE-metadata-unchanged-by-recovered-writes']

        host('/usr/bin/mysqladmin','--user=root','--socket=/var/run/mysqld/mysqld.sock','shutdown')
        for case in cases:
            jobs=app.extensions['cdeadmin_provider_workspace'].mysql_physical_jobs
            record=jobs.load(case.legacy['job_id'],case.owner,case.legacy['endpoint_id']);original_digest=record['review_digest']
            state=deepcopy(record['source_state']);state.pop('host_binding');jobs.update(record,source_state=state)
            with app.app_context():
                server=Server.query.get(case.sid);server.endpoint_profile.profile_generation=str(uuid.uuid4());db.session.commit()
            runtime=case.legacy['remote_observation']['runtime_process'];supervisor=case.legacy['remote_observation']['supervisor_process']
            assert kill_supervisor(supervisor)
            deadline=time.monotonic()+15
            while present(supervisor) and time.monotonic()<deadline:time.sleep(.1)
            assert not present(supervisor) and present(runtime)
            value=case.post('reconcile',{'job_id':record['job_id'],'credentials':credentials})
            assert value['state']=='unknown' and value['remote_observation']['supervisor_control_unavailable'] and value['remote_observation']['runtime_process_live']
            assert value['host_binding_source']=='retained_original_host_review'
            wrong=deepcopy(state);wrong['remote_review']['host']['server_uuid']=str(uuid.uuid4());jobs.update(record,source_state=wrong)
            case.post('cancel',{'job_id':record['job_id'],'credentials':credentials},refused=True);assert present(runtime)
            jobs.update(record,source_state=state)
            post,session=case.editor(value)
            try:assert execute(post,session,'SELECT note FROM m WHERE id=1')['rows']==[['native MyISAM']]
            finally:post('close_session',session_id=session);case.detach()
            case.post('output',{'job_id':record['job_id'],'credentials':credentials})
            case.post('cancel',{'job_id':record['job_id'],'credentials':credentials});value=case.wait(record,ended=True)
            assert value['state']=='unknown' and not present(runtime)
            assert jobs.load(record['job_id'],case.owner,record['endpoint_id'])['review_digest']==original_digest
            case.checks+=['source-offline-original-pinned-SSH-control-survives-real-registration-generation-and-native-adapter-changes',
                'missing-duplicate-binding-resolves-only-from-retained-matching-original-host-review-with-original-digest-unchanged',
                'killed-original-supervisor-remains-unknown-while-original-native-process-is-independently-observed',
                'mismatched-retained-source-UUID-refuses-cancellation-and-leaves-original-process-running',
                'fresh-native-editor-attachment-uses-original-binding-after-upgrade-supervisor-loss-and-source-SQL-shutdown',
                'original-pidfd-stop-and-end-observation-work-with-source-SQL-offline-and-original-exit-outcome-unknown']
            for runtime in case.runtimes[1:]:
                case.post('cancel',{'job_id':runtime['job_id'],'credentials':credentials});case.wait(runtime,ended=True)
            proof['interfaces'].append({'use_c':case.use_c,'complete':True,'checks':case.checks})
    finally:
        for case in cases:
            case.detach()
            for runtime in case.runtimes:
                try:case.post('cancel',{'job_id':runtime['job_id'],'credentials':credentials})
                except Exception:pass
    proof['complete']=True;return proof


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',required=True)
    parser.add_argument('--prepare-fixture',action='store_true');parser.add_argument('--private-key');parser.add_argument('--legacy-sources',required=True)
    args=parser.parse_args()
    from cdeadmin_mysql_physical_qualification import qualify
    qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,reconciliation_only=True,legacy_sources=args.legacy_sources)
