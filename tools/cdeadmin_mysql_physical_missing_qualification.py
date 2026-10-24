"""Owned native recovery after removal of the original source mount paths.

The source server is deliberately stopped after both drivers create checkpoints.
Its original volumes remain mounted under private hold paths; source bytes are
compared before and after native recovery. No source directory is reconstructed
in the base namespace and no SQL or process observation is mocked.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time


HOLD_SOURCE = r'''
import ctypes,hashlib,json,os,pathlib,stat,sys
roots=json.loads(sys.argv[1]);base=pathlib.Path('/var/backups/scratchrobin/source-held')
base.mkdir(mode=0o700)
native=ctypes.CDLL(None,use_errno=True)
for index,source in enumerate(roots):
    held=base/str(index);held.mkdir()
    if native.mount(os.fsencode(source),os.fsencode(held),None,0x1000|0x4000,None):
        raise OSError(ctypes.get_errno(),'preserve owned source volume')
    if native.umount2(os.fsencode(source),0):
        raise OSError(ctypes.get_errno(),'unmount owned source volume')
    original=pathlib.Path(source)
    # These are empty image-layer stubs, never the held database or key bytes.
    for item in sorted(original.rglob('*'),key=lambda p:len(p.parts),reverse=True):
        mode=item.lstat().st_mode
        if stat.S_ISDIR(mode):item.rmdir()
        elif stat.S_ISREG(mode) and item.stat().st_size==0:item.unlink()
        elif stat.S_ISLNK(mode):item.unlink()
        else:raise RuntimeError('Nonempty image-layer source stub: '+str(item))
    original.rmdir()
assert all(not pathlib.Path(p).exists() for p in roots)
print(json.dumps({'held_source_roots':roots,'base_aliases_absent':True}))
'''


def qualify_missing(app,output,oracle,container,port,password,selected,credentials,variant,datadir,external_root):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection,_run
    from pgadmin.model import Server
    selected={**selected,'keyring':{'xtrabackup_plugin_dir':'/usr/lib64/xtrabackup/plugin'},'isolate_external_paths':True}
    root=Path(__file__).resolve().parents[1]
    paths=['tools/cdeadmin_mysql_physical_missing_qualification.py','tools/cdeadmin_mysql_physical_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_paths.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py']
    proof={'complete':False,'variant':variant,'interfaces':[],'history_testing':'not run',
        'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}
    def host(*args):return _run(['docker','exec',container,*args]).stdout
    def absent():
        return json.loads(host('/usr/bin/python3','-c','import json,pathlib,sys;print(json.dumps([pathlib.Path(p).exists() for p in sys.argv[1:]]))',datadir,external_root,'/var/lib/mysql-keyring'))==[False]*3
    def source_hashes():
        return host('/usr/bin/python3','-c',
            "import pathlib,hashlib,json;p=pathlib.Path('/var/backups/scratchrobin/source-held');print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file()},sort_keys=True))")
    with oracle.cursor() as cursor:
        cursor.execute("CREATE TABLE sr_osc.encrypted_missing(id INT PRIMARY KEY,note VARCHAR(80),b LONGBLOB) ENCRYPTION='Y'")
        cursor.execute("INSERT INTO sr_osc.encrypted_missing VALUES(1,'native missing 雪',X'00FF01')")
        cursor.execute("CREATE TABLE sr_osc.external_missing(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=InnoDB ENCRYPTION='Y' DATA DIRECTORY=%s",(external_root,))
        cursor.execute("CREATE TABLESPACE sr_missing ADD DATAFILE %s ENCRYPTION='Y' ENGINE=InnoDB",(external_root+'/general.ibd',))
        cursor.execute("CREATE TABLE sr_osc.general_missing(id INT PRIMARY KEY,note VARCHAR(80)) TABLESPACE sr_missing ENCRYPTION='Y'")
        for table in ('external_missing','general_missing'):
            cursor.execute('INSERT INTO sr_osc.'+table+" VALUES(1,'native original external')")

    class Interface:
        def __init__(self,use_c):
            self.use_c=use_c;self.runtime=None;self.attached=None;self.checks=[]
            self.sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
            with app.test_request_context('/'):owner=Server.query.get(self.sid).user_id
            self.client=app.test_client()
            with self.client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
            self.url=endpoint(app,self.sid)
        def physical(self,action,body):
            response=self.client.post(self.url,json={'action':'mysql_physical_'+action,'request':body});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'missing-api-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                raise AssertionError('Native missing-path API failed; inspect missing-api-failure.json')
            return value['data']
        def review(self,phase,parent=None,**extra):
            return self.physical('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent,**extra},'credentials':credentials})
        def start(self,ticket):
            return self.physical('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
        def wait(self,ticket,running=False,stopped=False):
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=self.physical('reconcile',{'job_id':ticket['job_id'],'credentials':credentials});observed=value.get('remote_observation') or {}
                if running and value['recovery_running']:return value
                if observed.get('supervisor_finished'):
                    if stopped:return value
                    if not running and value['file_verification_confirmed']:return value
                    (output/'missing-native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                    (output/'missing-native-output.json').write_text(json.dumps(self.physical('output',{'job_id':ticket['job_id'],'credentials':credentials}),indent=2)+'\n')
                    raise AssertionError('Native missing-path recovery failed; inspect missing-native-output.json')
                time.sleep(.15)
            raise TimeoutError('Native missing-path recovery did not finish')
        def phase(self,phase,parent=None):return self.wait(self.start(self.review(phase,parent)))
        def close(self):
            if self.attached:
                self.physical('connection_detach',{'server_id':self.attached['server_id']});self.attached=None
            if self.runtime:
                self.physical('cancel',{'job_id':self.runtime['job_id'],'credentials':credentials})
                stopped=self.wait(self.runtime,stopped=True)
                assert not stopped['recovery_running']
                self.runtime=None

    interfaces=[]
    try:
        for use_c in (False,True):
            case=Interface(use_c);interfaces.append(case)
            guard=_root_connection('mysql',port)
            try:
                with guard.cursor() as cursor:
                    cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(22500+int(use_c),));cursor.execute('SAVEPOINT missing_guard')
                base=case.phase('backup');prepared=case.phase('prepare',base['job_id']);case.copied=case.phase('copy_back',prepared['job_id'])
                assert len(base['native_external_files'])==2
                with guard.cursor() as cursor:
                    cursor.execute('ROLLBACK TO SAVEPOINT missing_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
                case.checks.append('native-encrypted-checkpoint-and-copy-back-preserve-independent-source-savepoint-before-intentional-shutdown')
            finally:guard.rollback();guard.close()
        host('/usr/bin/mysqladmin','--user=root','--socket=/var/run/mysqld/mysqld.sock','shutdown')
        source_roots=['/sr-source225' if variant=='root' else datadir,external_root,'/var/lib/mysql-keyring']
        proof['source_shutdown_and_paths_removed']=json.loads(host('/usr/bin/python3','-c',HOLD_SOURCE,json.dumps(source_roots)))
        assert absent();original=source_hashes()
        for case in interfaces:
            for mode in ('read_only','replay'):
                extra={'recovery_port':33489,'recovery_server_id':22510+int(case.use_c)} if mode=='replay' else {}
                case.runtime=case.wait(case.start(case.review('recover',case.copied['job_id'],mysqld='/usr/sbin/mysqld',
                    recovery_gtid_mode='ON',recovery_mode=mode,timeout_seconds=300,**extra)),running=True)
                observed=case.runtime['remote_observation'];identity=observed['sql_identity']
                assert identity['datadir'].rstrip('/')==datadir
                assert observed['filesystem_isolation_observation']['native_filesystem_isolation_observed']
                assert identity['native_keyring_component']=='component_keyring_file'
                ticket=case.physical('connection_review',{'job_id':case.runtime['job_id'],'name':'Missing '+variant+' '+mode+' '+str(case.use_c),'credentials':credentials})
                case.attached=case.physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
                def post(action,**body):return query_post(case.client,endpoint(app,case.attached['server_id']),case.attached['database_target_id'],action,**body)
                session=post('open_session',language_profile='mysql-sql',history_sensitive=True)['session_id']
                try:
                    assert execute(post,session,'SELECT note,HEX(b) FROM encrypted_missing')['rows']==[['native missing 雪','00FF01']]
                    assert execute(post,session,'SELECT CAST(id AS CHAR),HEX(b) FROM t')['rows']==[['18446744073709551615','00FF']]
                    for table in ('external_missing','general_missing'):
                        assert execute(post,session,'SELECT note FROM '+table)['rows']==[['native original external']]
                    if mode=='replay':
                        execute(post,session,'ALTER INSTANCE ROTATE INNODB MASTER KEY')
                        execute(post,session,"CREATE TABLE external_new(id INT PRIMARY KEY) ENGINE=InnoDB DATA DIRECTORY='"+external_root+"'")
                        execute(post,session,'INSERT INTO external_new VALUES(1)');execute(post,session,'DROP TABLE external_new')
                        execute(post,session,"UPDATE external_missing SET note='private replay' WHERE id=1")
                        execute(post,session,"UPDATE general_missing SET note='private replay' WHERE id=1");execute(post,session,'COMMIT')
                finally:post('close_session',session_id=session)
                assert absent() and source_hashes()==original
                case.close()
                assert absent() and source_hashes()==original
                case.checks.append('source-offline-'+mode+'-native-SQL-editor-and-external-DDL-with-private-keyring-and-original-directory-aliases-absent-in-base-namespace')
                case.checks.append('source-offline-'+mode+'-native-original-process-observed-and-stopped-with-source-volume-and-key-bytes-unchanged')
            proof['interfaces'].append({'use_c':case.use_c,'complete':True,'checks':case.checks})
            (output/'missing-api-progress.json').write_text(json.dumps(proof,indent=2)+'\n')
        proof['complete']=True
    finally:
        for case in reversed(interfaces):case.close()
        (output/'missing-summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--fixture-image',required=True);parser.add_argument('--prepare-fixture',action='store_true')
    parser.add_argument('--private-key');parser.add_argument('--missing-paths',choices=('parent','root'),required=True)
    args=parser.parse_args()
    from cdeadmin_mysql_physical_qualification import qualify
    qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,missing_paths=args.missing_paths)
