"""Native raw-storage application chains and source-offline recovered editors."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(args):
    import config
    from cdeadmin_mysql_raw_storage_qualification import controller_source
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection,_wait_until_ready,_published_port
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as remote
    from pgadmin.model import Server
    output=args.output.resolve();package=args.package.resolve(strict=True)
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep private qualification outside source')
    if args.browser_binary:
        assert all((ROOT/'web/pgadmin/static/js/generated'/name).is_file() for name in ('app.bundle.js','browser_nodes.js','vendor.main.js')), 'Install the qualified desktop bundle in this source snapshot first'
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    name='sr-raw-application-'+secrets.token_hex(6);volumes=[];loop=None;app=None;oracle=None;interfaces=[]
    paths=['tools/cdeadmin_mysql_raw_application_qualification.py','tools/cdeadmin_mysql_raw_storage_qualification.py',
        'tools/cdeadmin_mysql_physical_qualification.py','tools/cdeadmin_ui_evidence.py',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py','web/pgadmin/cdeadmin/workspace/mysql_recovery_connections.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_geometry.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_paths.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py','web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx']
    proof={'complete':False,'history_testing':'not run','interfaces':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        'native_package':json.loads((package/'PROVENANCE.json').read_text())}
    def run(command,check=True):return subprocess.run(command,capture_output=True,text=True,timeout=300,check=check)
    def host(*command):return run(['docker','exec',name,*command]).stdout
    def source_hashes():
        additional="files['raw-device-first']=hashlib.sha256(Path('/tmp/sr-owned-first.img').read_bytes()).hexdigest();" if args.multiple else ''
        return json.loads(host('/usr/bin/python3','-c',
            "from pathlib import Path;import hashlib,json;root=Path('/sr-source225/mysql');files={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.rglob('*')) if f.is_file()};files['raw-device-backing']=hashlib.sha256(Path('/tmp/sr-owned-system.img').read_bytes()).hexdigest();"+additional+"print(json.dumps(files))"))
    try:
        key=output/'private-key';run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)])
        specification='32M'+(':autoextend:max:48M' if args.autoextend else '')
        controller=controller_source(specification,multiple=args.multiple)
        recovery_specification=('/dev/sr-owned-first:12M;' if args.multiple else '')+'/dev/sr-owned-loop:'+specification
        run(['docker','run','--rm','-d','--cap-add=SYS_ADMIN','--device-cgroup-rule=c 10:237 rwm','--device-cgroup-rule=b 7:* rwm',
            '--name',name,'--mount',f'type=bind,source={package},target=/opt/sr-raw,readonly',
            '-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','-p','127.0.0.1::22',
            '--entrypoint','/usr/bin/python3',args.fixture_image,'-c',controller])
        volumes=[m['Name'] for m in json.loads(run(['docker','inspect','--format','{{json .Mounts}}',name]).stdout) if m['Type']=='volume']
        run(['docker','cp',str(key.with_suffix('.pub')),name+':/root/.ssh/authorized_keys'])
        host('chown','root:root','/root/.ssh','/root/.ssh/authorized_keys');host('chmod','700','/root/.ssh');host('chmod','600','/root/.ssh/authorized_keys')
        port=_wait_until_ready('mysql',name,300);ssh=_published_port(run(['docker','port',name,'22/tcp']).stdout)
        loop=json.loads(host('cat','/var/backups/raw231/loop.json'));oracle=_root_connection('mysql',port);oracle.autocommit=True
        password='raw private 雪-'+secrets.token_urlsafe(20)
        with oracle.cursor() as cursor:
            cursor.execute('CREATE DATABASE sr_osc');cursor.execute('CREATE TABLE sr_osc.t(id INT PRIMARY KEY,note VARCHAR(80),b LONGBLOB) TABLESPACE=innodb_system')
            cursor.execute("INSERT INTO sr_osc.t VALUES(1,'raw base 雪',X'00FF')");cursor.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
            cursor.execute("CREATE USER 'sr_physical'@'%' IDENTIFIED BY %s",(password,))
            cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_physical'@'%' WITH GRANT OPTION")
            cursor.execute('SET GLOBAL innodb_max_dirty_pages_pct=0')
        selected={'connection':{'host':'127.0.0.1','port':ssh,'username':'root','host_key':host('cat','/etc/ssh/ssh_host_ed25519_key.pub').strip(),
            'authentication':'private_key','platform':'posix','python':'/usr/bin/python3'},'workspace':'/var/backups/scratchrobin/jobs',
            'executable':'/opt/sr-raw/bin/xtrabackup','mysql':'/usr/bin/mysql','phase':'backup','sql_host':'127.0.0.1','sql_port':3306,
            'input_job_id':None,'parallel':2,'memory_bytes':268435456,'timeout_seconds':180,'accept_release_candidate':True,'isolate_external_paths':True}
        credentials={'private_key':key.read_text()};app=setup_application(output)

        class Interface:
            def __init__(self,use_c):
                self.use_c=use_c;self.runtime=None;self.attached=None;self.checks=[]
                self.sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
                with app.test_request_context('/'):owner=Server.query.get(self.sid).user_id
                self.client=app.test_client()
                with self.client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
                self.url=endpoint(app,self.sid)
            def physical(self,action,body,refused=False):
                response=self.client.post(self.url,json={'action':'mysql_physical_'+action,'request':body});value=response.get_json()
                if refused:assert not value.get('success'),value;return value
                if response.status_code!=200 or not value.get('success'):
                    (output/'api-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Raw application API refused; inspect api-failure.json')
                return value['data']
            def review(self,phase,parent=None,**extra):
                return self.physical('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent,**extra},'credentials':credentials})
            def start(self,ticket,refused=False):
                return self.physical('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                    'delegate_database_credentials':True,'credentials':credentials},refused)
            def wait(self,ticket,running=False,stopped=False):
                deadline=time.monotonic()+240
                while time.monotonic()<deadline:
                    value=self.physical('reconcile',{'job_id':ticket['job_id'],'credentials':credentials});observed=value.get('remote_observation') or {}
                    if running and value['recovery_running']:return value
                    if observed.get('supervisor_finished'):
                        if stopped or not running and value['file_verification_confirmed']:return value
                        (output/'native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                        (output/'native-output.json').write_text(json.dumps(self.physical('output',{'job_id':ticket['job_id'],'credentials':credentials}),indent=2)+'\n')
                        raise AssertionError('Raw native operation failed; inspect native-output.json')
                    time.sleep(.15)
                raise TimeoutError('Raw native application operation did not finish')
            def phase(self,kind,parent=None,**extra):return self.wait(self.start(self.review(kind,parent,**extra)))
            def close(self):
                if self.attached:self.physical('connection_detach',{'server_id':self.attached['server_id']});self.attached=None
                if self.runtime:self.physical('cancel',{'job_id':self.runtime['job_id'],'credentials':credentials});self.wait(self.runtime,stopped=True);self.runtime=None

        for use_c in (False,True):
            interface=Interface(use_c);interfaces.append(interface);guard=_root_connection('mysql',port)
            try:
                with guard.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(23100+int(use_c),));cursor.execute('SAVEPOINT raw_guard')
                rejected=interface.physical('review',{'options':{**selected,'executable':'/usr/bin/xtrabackup'},'credentials':credentials},True)
                assert 'qualified native backup dependency' in rejected.get('errormsg',''),rejected
                with oracle.cursor() as cursor:
                    cursor.execute("SELECT TOTAL_EXTENTS*EXTENT_SIZE FROM information_schema.FILES WHERE TABLESPACE_NAME='innodb_system' AND FILE_NAME='/dev/sr-owned-loop'")
                    base_extent=int(cursor.fetchone()[0])-(12*1024*1024 if args.multiple else 0)
                base=interface.phase('backup');artifact=base['remote_observation']['artifact']
                assert artifact['storage_geometry']['system_files'][0]['raw_mode']=='newraw'
                assert int(host('/usr/bin/python3','-c',"from pathlib import Path;print(Path('"+selected['workspace']+'/'+base['job_id']+"/artifact/sr-owned-loop').stat().st_size)"))==base_extent
                with oracle.cursor() as cursor:
                    cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(2+int(use_c),'raw delta 雪',b'\x00\xff\x01'))
                    if args.autoextend and not use_c:
                        cursor.execute("INSERT INTO sr_osc.t VALUES(100,'native grown extent',REPEAT('x',"+str(50 if args.multiple else 40)+"*1024*1024))")
                        cursor.execute('SELECT LENGTH(b),SHA2(b,256) FROM sr_osc.t WHERE id=100');proof['grown_payload']=list(cursor.fetchone())
                ticket=interface.review('incremental',base['job_id']);original=remote.Transport.request
                def lost(channel,body,*a,**kw):
                    value=original(channel,body,*a,**kw)
                    if body['action']=='start':raise remote.HostError('Owned lost raw incremental dispatch reply')
                    return value
                with patch.object(remote.Transport,'request',lost):interface.start(ticket,True)
                delta=interface.wait(ticket);assert delta['state']=='unknown' and interface.start(ticket)['state']=='unknown'
                redo=interface.phase('prepare_redo',base['job_id']);applied=interface.phase('prepare_redo',redo['job_id'],incremental_job_id=delta['job_id'])
                final=interface.phase('prepare',applied['job_id']);interface.copied=interface.phase('copy_back',final['job_id'])
                interface.checks+=['stock-reader-refused-before-dispatch','raw-full-native-configured-extent','raw-incremental-lost-reply-stays-unknown-without-replay',
                    'immutable-redo-only-apply-final-prepare-private-regular-copy-back']
                with guard.cursor() as cursor:cursor.execute('ROLLBACK TO SAVEPOINT raw_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending WHERE id=%s',(23100+int(use_c),));assert cursor.fetchone()[0]==1
                interface.checks.append('independent-source-pending-transaction-and-savepoint-preserved')
            finally:guard.rollback();guard.close()
        if args.browser_binary and args.driver_binary:
            from cdeadmin_mysql_physical_qualification import browser
            proof['browser']=browser(app,output/'raw-desktop',interfaces[-1].sid,password,selected,credentials,args.browser_binary,args.driver_binary)
        oracle.close();oracle=None
        host('/usr/bin/mysqladmin','--user=root','--socket=/var/run/mysqld/mysqld.sock','shutdown')
        before=source_hashes();host('rm','/dev/sr-owned-loop',*(['/dev/sr-owned-first'] if args.multiple else []))
        for interface in interfaces:
            for mode in ('read_only','replay'):
                extra={'recovery_port':33487,'recovery_server_id':23110+int(interface.use_c)} if mode=='replay' else {}
                interface.runtime=interface.wait(interface.start(interface.review('recover',interface.copied['job_id'],mysqld='/usr/sbin/mysqld',
                    recovery_gtid_mode='ON',recovery_mode=mode,timeout_seconds=300,**extra)),running=True)
                observed=interface.runtime['remote_observation'];assert observed['filesystem_isolation_observation']['native_filesystem_isolation_observed']
                assert observed['filesystem_isolation_observation']['external_file_aliases']==(2 if args.multiple else 1)
                ticket=interface.physical('connection_review',{'job_id':interface.runtime['job_id'],'name':'Raw '+mode+' '+str(interface.use_c),'credentials':credentials})
                interface.attached=interface.physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                    'delegate_database_credentials':True,'credentials':credentials})['result']
                post=lambda action,**body:query_post(interface.client,endpoint(app,interface.attached['server_id']),interface.attached['database_target_id'],action,**body)
                session=post('open_session',language_profile='mysql-sql',history_sensitive=True)['session_id']
                try:
                    assert execute(post,session,'SELECT note,HEX(b) FROM t WHERE id='+str(2+int(interface.use_c)))['rows']==[['raw delta 雪','00FF01']]
                    assert execute(post,session,'SELECT @@innodb_data_file_path')['rows']==[[recovery_specification]]
                    if args.autoextend:
                        assert execute(post,session,'SELECT LENGTH(b),SHA2(b,256) FROM t WHERE id=100')['rows']==[proof['grown_payload']]
                    if mode=='replay':
                        execute(post,session,"INSERT INTO t VALUES(10000,'private raw recovered write',X'AAFF')");execute(post,session,'COMMIT')
                        assert execute(post,session,'SELECT HEX(b) FROM t WHERE id=10000')['rows']==[['AAFF']]
                finally:post('close_session',session_id=session)
                assert source_hashes()==before
                assert host('/usr/bin/python3','-c',"from pathlib import Path;print(Path('/dev/sr-owned-loop').exists())").strip()=='False'
                interface.close();interface.checks.append('source-offline-missing-device-'+mode+'-native-editor-and-private-writes-with-original-bytes-unchanged')
            proof['interfaces'].append({'use_c':interface.use_c,'checks':interface.checks,'complete':True})
        proof['complete']=True
    finally:
        proof['cleanup_errors']=[]
        for interface in interfaces:
            try:interface.close()
            except Exception as error:proof['cleanup_errors'].append(type(error).__name__)
        if oracle:oracle.close()
        if app:
            workspace=app.extensions['cdeadmin_provider_workspace']
            for component in ('mysql_physical_scheduler','mysql_backup_scheduler','mysql_check_scheduler'):getattr(workspace,component).close()
            from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import bridges
            bridges.close()
        result=run(['docker','logs',name],False);(output/'source.log').write_text(result.stdout+result.stderr)
        result=run(['docker','exec',name,'cat','/tmp/physical-sshd.log'],False);(output/'sshd.log').write_text(result.stdout+result.stderr)
        run(['docker','rm','-fv',name],False)
        for volume in volumes:run(['docker','volume','rm',volume],False)
        proof['owned_container_and_data_removed']=run(['docker','inspect',name],False).returncode!=0 and all(run(['docker','volume','inspect',v],False).returncode!=0 for v in volumes)
        if loop:
            indices=[loop['loop_index'],*[item['loop_index'] for item in loop.get('additional_loops',[])]]
            result=run(['docker','run','--rm','--entrypoint','/usr/bin/python3',args.fixture_image,'-c',
                "from pathlib import Path;import json;indices="+repr(indices)+";print(json.dumps({'owned_loop_detached':all(not Path('/sys/block/loop'+str(index)+'/loop/backing_file').exists() for index in indices)}))"],False)
            proof['loop_cleanup_observation']=json.loads(result.stdout) if result.returncode==0 else {'unknown':True}
        for p in (output/'private-key',output/'private-key.pub'):p.unlink(missing_ok=True)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--package',required=True,type=Path);parser.add_argument('--fixture-image',required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    parser.add_argument('--autoextend',action='store_true')
    parser.add_argument('--multiple',action='store_true')
    print(json.dumps(qualify(parser.parse_args()),indent=2))
