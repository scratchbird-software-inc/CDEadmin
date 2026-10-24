"""Real GPL file-keyring encrypted physical chains and private native recovery."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch


def qualify_keyring(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None,*,external=False,desktop_only=False,storage=None):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_family_object_live_orchestrator import _root_connection,_run
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as remote
    selected={**selected,'keyring':{'xtrabackup_plugin_dir':'/usr/lib64/xtrabackup/plugin'}}
    if external:selected['isolate_external_paths']=True
    external_tables=('external_single','external_general','external_named')
    external_files=('/var/lib/mysql-external/general.ibd','/var/lib/mysql-external/sr_osc/external_single.ibd',
        '/var/lib/mysql-external/with; space 雪/sr_osc/external_named.ibd')
    storage_files=([*storage['system_files'],*[storage['undo_root']+'/'+name for name in ('undo_001','undo_002','extra.ibu')]] if storage else [])
    if external:
        _run(['docker','exec',container,'mkdir','-p','/var/lib/mysql-external/with; space 雪'])
        _run(['docker','exec',container,'chown','mysql:mysql','/var/lib/mysql-external/with; space 雪'])
    with oracle.cursor() as cursor:
        if storage:cursor.execute('CREATE UNDO TABLESPACE sr_geometry_undo ADD DATAFILE %s',(storage['undo_root']+'/extra.ibu',))
        cursor.execute("CREATE TABLE sr_osc.encrypted_data(id INT PRIMARY KEY,note VARCHAR(80),b LONGBLOB) ENCRYPTION='Y'")
        cursor.execute("INSERT INTO sr_osc.encrypted_data VALUES(1,'encrypted base 雪',X'00FF')")
        if external:
            cursor.execute("CREATE TABLE sr_osc.external_single(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=InnoDB ENCRYPTION='Y' DATA DIRECTORY='/var/lib/mysql-external'")
            cursor.execute("CREATE TABLESPACE sr_external ADD DATAFILE '/var/lib/mysql-external/general.ibd' ENCRYPTION='Y' ENGINE=InnoDB")
            cursor.execute("CREATE TABLE sr_osc.external_general(id INT PRIMARY KEY,note VARCHAR(80)) TABLESPACE sr_external ENCRYPTION='Y'")
            cursor.execute("CREATE TABLE sr_osc.external_named(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=InnoDB ENCRYPTION='Y' DATA DIRECTORY='/var/lib/mysql-external/with; space 雪'")
            cursor.execute("INSERT INTO sr_osc.external_single VALUES(1,'native external base')")
            cursor.execute("INSERT INTO sr_osc.external_general VALUES(1,'native external base')")
            cursor.execute("INSERT INTO sr_osc.external_named VALUES(1,'native external base')")
            cursor.execute('SET GLOBAL innodb_max_dirty_pages_pct=0')
    paths=['tools/cdeadmin_mysql_physical_keyring_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_keyring.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_geometry.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_paths.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py','web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx']
    root=Path(__file__).resolve().parents[1]
    proof={'complete':False,'interfaces':[],'history_testing':'not run',
        'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}
    if desktop_only:
        sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,True,username='sr_physical')
        from cdeadmin_mysql_physical_qualification import browser
        proof['browser']=browser(app,output/'keyring-desktop',sid,password,selected,credentials,binary,driver_binary)
        proof['qualification_scope']='Built desktop native recovery; separate current API receipts qualify both drivers, incremental and recurring-worker behavior'
        proof['complete']=True;return proof
    for use_c in (False,True):
        sid,_,_=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        from pgadmin.model import Server
        with app.test_request_context('/'):owner=Server.query.get(sid).user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        url=endpoint(app,sid);runtime=attached=None;guard=_root_connection('mysql',port);checks=[]
        def physical(action,body,refused=False):
            response=client.post(url,json={'action':'mysql_physical_'+action,'request':body});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            if response.status_code!=200 or not value.get('success'):
                (output/'keyring-api-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native keyring API failed; inspect keyring-api-failure.json')
            return value['data']
        def review(phase,parent=None,**extra):return physical('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent,**extra},'credentials':credentials})
        def start(ticket,refused=False):return physical('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials},refused)
        def wait(ticket,running=False,stopped=False):
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':ticket['job_id'],'credentials':credentials});observed=value.get('remote_observation') or {}
                if running and value['recovery_running']:return value
                if observed.get('supervisor_finished'):
                    if stopped:return value
                    if not running and value['file_verification_confirmed']:return value
                    (output/'keyring-native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                    (output/'keyring-native-output.json').write_text(json.dumps(physical('output',{'job_id':ticket['job_id'],'credentials':credentials}),indent=2)+'\n')
                    raise AssertionError('Native encrypted operation failed; inspect keyring-native-output.json')
                time.sleep(.15)
            raise TimeoutError('Native encrypted operation did not finish')
        def phase(kind,parent=None,**extra):return wait(start(review(kind,parent,**extra)))
        def host(*args):return _run(['docker','exec',container,*args]).stdout
        def keyhash():return host('sha256sum','/var/lib/mysql-keyring/keyring').split()[0]
        try:
            with guard.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(22300+int(use_c),));cursor.execute('SAVEPOINT keyring_guard')
            plain={key:value for key,value in selected.items() if key!='keyring'}
            physical('review',{'options':plain,'credentials':credentials},refused=True)
            if external:
                no_external={key:value for key,value in selected.items() if key!='isolate_external_paths'}
                physical('review',{'options':no_external,'credentials':credentials},refused=True)
            base=phase('backup');material=base['remote_observation']['artifact']['keyring']
            assert material['private_key_material_retained'] and material['encryption']=={'redo':True,'undo':True,'binlog':True}
            if external:
                assert {row['file_name'] for row in base['native_external_files']}==set(external_files)|set(storage_files)
                if storage:
                    retained=base['remote_observation']['artifact']['storage_geometry']
                    assert [row['source_file'] for row in retained['system_files']]==storage['system_files']
                    assert storage['empty_root'] in retained['scan_directories']
                    if storage.get('filesystem_links'):
                        assert retained['resolved_paths'] and retained['catalog_files']
                        assert retained['data_home']==storage['system_root'] and retained['undo_home']==storage['undo_root']
                        checks.append('native-symlink-parent-paths-retain-host-observed-effective-identities-and-original-catalog-spellings')
            with oracle.cursor() as cursor:
                cursor.execute('ALTER INSTANCE ROTATE INNODB MASTER KEY')
                cursor.execute('INSERT INTO sr_osc.encrypted_data VALUES(%s,%s,%s)',(2+int(use_c),'encrypted delta 雪',b'\x00\xff\x01'))
                if external:
                    for table in external_tables:
                        cursor.execute('INSERT INTO sr_osc.'+table+' VALUES(%s,%s)',(2+int(use_c),'native external delta'))
            ticket=review('incremental',base['job_id']);original=remote.Transport.request
            def lost(channel,body,*args,**kwargs):
                result=original(channel,body,*args,**kwargs)
                if body['action']=='start':raise remote.HostError('Owned lost original encrypted incremental dispatch reply')
                return result
            with patch.object(remote.Transport,'request',lost):start(ticket,True)
            delta=wait(ticket);assert delta['state']=='unknown' and start(ticket)['state']=='unknown'
            newest=delta['remote_observation']['artifact']['keyring']
            assert newest['transition_key_sha256']==material['transition_key_sha256']
            assert newest['keyring_sha256']!=material['keyring_sha256']
            redo=phase('prepare_redo',base['job_id'])
            applied=phase('prepare_redo',redo['job_id'],incremental_job_id=delta['job_id'])
            final=phase('prepare',applied['job_id']);copied=phase('copy_back',final['job_id'])
            checks+=['explicit-key-retention-consent-before-encrypted-source-admission',
                'native-encrypted-full-and-incremental-with-source-master-key-rotation-and-stable-private-native-transition-key',
                'lost-incremental-dispatch-reply-stays-unknown-with-independent-native-completion-and-no-repeat',
                'native-private-redo-apply-finalization-and-copy-back-preserve-encrypted-chain-key-material']
            for mode in ('read_only','replay'):
                before=keyhash()
                if external:
                    deadline=time.monotonic()+60
                    while time.monotonic()<deadline:
                        with oracle.cursor() as cursor:cursor.execute("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_dirty'");dirty=int(cursor.fetchone()[1])
                        if not dirty:break
                        time.sleep(.2)
                    else:raise TimeoutError('Owned native source did not flush its encrypted external pages')
                    external_before=host('sha256sum',*external_files)
                extra={'recovery_port':33487,'recovery_server_id':22310+int(use_c)} if mode=='replay' else {}
                runtime=wait(start(review('recover',copied['job_id'],mysqld='/usr/sbin/mysqld',recovery_gtid_mode='ON',
                    recovery_mode=mode,timeout_seconds=300,**extra)),running=True)
                identity=runtime['remote_observation']['sql_identity']
                if external:
                    assert identity['datadir'].rstrip('/')=='/var/lib/mysql'
                    assert runtime['remote_observation']['filesystem_isolation_observation']['native_filesystem_isolation_observed']
                assert identity['native_keyring_component']=='component_keyring_file'
                assert identity['native_keyring_data_file']==selected['workspace']+'/'+runtime['job_id']+'/runtime-data/.scratchrobin-keyring/keyring'
                assert identity['innodb_redo_log_encrypt']==identity['innodb_undo_log_encrypt']==identity['binlog_encryption']==1
                ticket=physical('connection_review',{'job_id':runtime['job_id'],'name':'Encrypted '+mode+' '+str(use_c),'credentials':credentials})
                attached=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
                post=lambda action,**body:query_post(client,endpoint(app,attached['server_id']),attached['database_target_id'],action,**body)
                session=post('open_session',language_profile='mysql-sql',history_sensitive=True)['session_id']
                try:
                    assert execute(post,session,'SELECT note,HEX(b) FROM encrypted_data WHERE id='+str(2+int(use_c)))['rows']==[['encrypted delta 雪','00FF01']]
                    if storage:
                        assert execute(post,session,'SELECT @@innodb_data_file_path,@@innodb_undo_directory')['rows']==[
                            [storage['runtime_data_file_spec'],storage['undo_root']]]
                    if external:
                        for table in external_tables:
                            assert execute(post,session,'SELECT note FROM '+table+' WHERE id='+str(2+int(use_c)))['rows']==[['native external delta']]
                    if mode=='replay':
                        execute(post,session,'ALTER INSTANCE ROTATE INNODB MASTER KEY')
                        execute(post,session,"INSERT INTO encrypted_data VALUES(100,'private recovered write',X'00FF')")
                        execute(post,session,'COMMIT')
                        assert execute(post,session,'SELECT note FROM encrypted_data WHERE id=100')['rows']==[['private recovered write']]
                        if external:
                            execute(post,session,"CREATE TABLE external_new(id INT PRIMARY KEY) ENGINE=InnoDB DATA DIRECTORY='/var/lib/mysql-external'")
                            execute(post,session,'INSERT INTO external_new VALUES(1)')
                            execute(post,session,'DROP TABLE external_new')
                            execute(post,session,"UPDATE external_single SET note='private external recovered write' WHERE id=1")
                            execute(post,session,"UPDATE external_general SET note='private external recovered write' WHERE id=1")
                            execute(post,session,'COMMIT')
                            if storage:
                                execute(post,session,"CREATE TABLE empty_directory_new(id INT PRIMARY KEY) DATA DIRECTORY='"+storage['empty_root']+"'")
                                execute(post,session,'INSERT INTO empty_directory_new VALUES(1)');execute(post,session,'DROP TABLE empty_directory_new')
                                execute(post,session,"CREATE UNDO TABLESPACE sr_private_undo ADD DATAFILE '"+storage['undo_root']+"/private.ibu'")
                finally:post('close_session',session_id=session)
                assert keyhash()==before
                if external:
                    assert host('sha256sum',*external_files)==external_before
                    checks.append('native-encrypted-external-'+mode+'-data-use-private-original-path-aliases-with-readonly-host-view-and-source-bytes-unchanged')
                    if mode=='replay':checks.append('native-create-insert-and-drop-in-reviewed-original-DATA-DIRECTORY-and-general-and-per-file-updates-remain-private')
                physical('connection_detach',{'server_id':attached['server_id']});attached=None
                physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials});wait(runtime,stopped=True);runtime=None
                checks.append('native-'+mode+'-recovery-and-editor-use-private-keyring-plugin-dependencies-and-original-encryption-policy-with-source-keys-unchanged')
                if storage:checks.append('native-'+mode+'-encrypted-incremental-two-system-files-default-and-user-undo-and-retained-empty-directory-DDL')
            for retained in (base,delta,final):
                observed=physical('reconcile',{'job_id':retained['job_id'],'credentials':credentials})
                assert observed['remote_observation']['artifact']['manifest_sha256']==retained['remote_observation']['artifact']['manifest_sha256']
            assert not host('find',selected['workspace'],'-name','client.cnf','-o','-name','keyring-native.cnf','-o','-name','.scratchrobin-transition.key').strip()
            with guard.cursor() as cursor:cursor.execute('ROLLBACK TO SAVEPOINT keyring_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            guard.rollback();checks+=['original-full-delta-and-final-artifact-byte-manifests-unchanged-after-private-native-key-rotation',
                'ephemeral-native-option-files-cleaned-and-independent-pending-source-savepoint-preserved']
            from cdeadmin_mysql_physical_tls_qualification import qualify_schedule
            qualify_schedule(app,physical,sid,password,selected,None,credentials)
            checks.append('encrypted-backup-and-native-startup-drill-policy-survives-worker-restart-without-interactive-database-or-SSH-secrets')
            if use_c and binary and driver_binary:
                from cdeadmin_mysql_physical_qualification import browser
                proof['browser']=browser(app,output/'keyring-desktop',sid,password,selected,credentials,binary,driver_binary)
            proof['interfaces'].append({'use_c':use_c,'complete':True,'checks':checks})
            (output/'keyring-api-progress.json').write_text(json.dumps(proof,indent=2)+'\n')
        finally:
            guard.rollback();guard.close()
            if attached:
                try:physical('connection_detach',{'server_id':attached['server_id']})
                except Exception:pass
            if runtime:
                physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials});wait(runtime,stopped=True)
    proof['complete']=True;return proof


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--fixture-image',required=True);parser.add_argument('--prepare-fixture',action='store_true')
    parser.add_argument('--private-key');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    parser.add_argument('--external',action='store_true')
    parser.add_argument('--desktop-only',action='store_true')
    parser.add_argument('--geometry',action='store_true')
    parser.add_argument('--relative-storage',action='store_true')
    parser.add_argument('--circular-storage',action='store_true')
    parser.add_argument('--native-backend',type=Path)
    args=parser.parse_args()
    from cdeadmin_mysql_physical_qualification import qualify
    qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,args.browser_binary,args.driver_binary,keyring_only=not args.external,external_only=args.external,keyring_desktop_only=args.desktop_only,storage_geometry=args.geometry,relative_storage=args.relative_storage,circular_storage=args.circular_storage,native_backend=args.native_backend)
