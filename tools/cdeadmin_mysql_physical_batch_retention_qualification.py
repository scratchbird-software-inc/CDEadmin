"""Native MySQL/PXB chain policies, interrupted removal and built desktop."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch


def qualify_batch(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from flask import url_for
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from cdeadmin_mysql_physical_retention_qualification import browser
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
    from mysql_qualification_support import _root_connection
    output=Path(output);root=Path(__file__).resolve().parents[1]
    sources=[Path(__file__),root/'web/pgadmin/cdeadmin/workspace/mysql_physical_batch_retention.py',
        root/'web/pgadmin/static/js/Dialogs/MySQLPhysicalBatchRetention.jsx']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    for use_c in (False,True):
        sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        with app.test_request_context('/'):
            item=__import__('pgadmin.model',fromlist=['Server']).Server.query.get(sid)
            endpoint=url_for('NODE-server.cde_workspace_id',gid=item.servergroup_id,sid=sid);owner=item.user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        checks=[]
        def post(operation,request,refused=False):
            response=client.post(endpoint,json={'action':'mysql_physical_'+operation,'request':request});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def create(phase='backup',parent=None):
            ticket=post('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent},'credentials':credentials})
            value=post('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
                'delegate_database_credentials':True,'credentials':credentials})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=post('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                if value.get('remote_observation',{}).get('supervisor_finished'):
                    assert value['file_verification_confirmed'],value;return value
                time.sleep(.15)
            raise TimeoutError('Native batch backup fixture did not finish')
        def review(anchor):return post('retention_batch_review',{'scope_job_id':anchor['job_id'],'policy':{'retention_days':0,'keep_latest':1},'credentials':credentials})
        def step(ticket,operation='advance',refused=False):return post('retention_batch_'+operation,{'job_id':ticket['job_id'],
            'review_digest':ticket['review_digest'],'confirmed':True,'batch_confirmation':ticket['job_id'],'credentials':credentials},refused)
        def reconcile(ticket):return post('retention_batch_reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
        request=transport.Transport.request
        def lost(channel,payload,*args,**kwargs):
            value=request(channel,payload,*args,**kwargs)
            if payload['action']=='retention_remove':raise transport.HostError('Owned original batch reply loss')
            return value
        backup=create();child=create('prepare',backup['job_id']);newest=create()
        post('retention_pin',{'job_id':child['job_id'],'pinned':True})
        assert review(backup)['state']=='nothing_eligible'
        post('retention_pin',{'job_id':child['job_id'],'pinned':False})
        ticket=review(backup)
        assert ticket['plan']['job_ids']==[child['job_id'],backup['job_id']]
        assert ticket['plan']['retained_full_backup_ids']==[newest['job_id']]
        checks.append('native-full-backup-floor-and-pinned-child-preserve-entire-input-chain')
        post('review',{'options':{**deepcopy(selected),'phase':'copy_back','input_job_id':child['job_id']},'credentials':credentials},refused=True)
        entry=ticket['items'][0]
        post('retention_start',{'job_id':entry['retention_job_id'],'review_digest':entry['retention_digest'],
            'confirmed':True,'job_confirmation':child['job_id'],'credentials':credentials},refused=True)
        checks.append('reserved-native-input-refuses-new-child-and-individual-batch-item-bypass')
        retained_path=selected['workspace']+'/'+newest['job_id']+'/artifact/xtrabackup_binlog_info'
        original_bytes=_run(['docker','exec',container,'python3','-c','from pathlib import Path;import sys;print(Path(sys.argv[1]).read_bytes().hex())',retained_path]).stdout.strip()
        _run(['docker','exec',container,'python3','-c','from pathlib import Path;import sys;p=Path(sys.argv[1]);p.write_bytes(p.read_bytes()+b"\\nchanged")',retained_path])
        step(ticket,refused=True)
        assert _run(['docker','exec',container,'test','-d',selected['workspace']+'/'+child['job_id']+'/artifact']).returncode==0
        _run(['docker','exec',container,'python3','-c','from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(bytes.fromhex(sys.argv[2]))',retained_path,original_bytes])
        assert reconcile(ticket)['state']=='interrupted'
        checks.append('retained-native-full-backup-content-change-refuses-removal-under-host-lock')
        request=transport.Transport.request;sources=transport.sources
        def interrupted(channel,payload,*args,**kwargs):
            if payload['action']!='retention_remove':return request(channel,payload,*args,**kwargs)
            code=sources();needle="if current['identity']['kind']=='directory':shutil.rmtree(detached)"
            assert code['retention'].count(needle)==1
            code['retention']=code['retention'].replace(needle,"if current['identity']['kind']=='directory':\n            victim=next(p for p in detached.rglob('*') if p.is_file());victim.unlink()\n            raise OSError('Owned partial batch removal')")
            with patch.object(transport,'sources',return_value=code):return request(channel,payload,*args,**kwargs)
        with patch.object(transport.Transport,'request',interrupted):step(ticket,'resume',True)
        assert post('retention_batch_status',{'job_id':ticket['job_id']})['state']=='interrupted'
        step(ticket,'resume',True)
        assert step(ticket,'cancel')['state']=='interrupted'
        assert reconcile(ticket)['state']=='interrupted'
        checks.append('genuine-remote-partial-unlink-requires-independent-inspection-and-invalidates-unused-parent-preview')
        oracle.autocommit=False
        with oracle.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(8001+int(use_c),));cursor.execute('SAVEPOINT batch_retention_guard')
        control=_root_connection('mysql',port);control.autocommit=True;locked=False
        try:
            with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT LOCK")
            locked=True
            with patch.object(transport.Transport,'request',lost):step(ticket,'resume',True)
            cancelled=step(ticket,'cancel')
            assert cancelled['state']=='cancelled' and cancelled['removed_job_ids']==[child['job_id']]
            assert cancelled['cancellation_observations'][child['job_id']]['removal_confirmed']
        finally:
            if locked:
                with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT UNLOCK")
            control.close()
            with oracle.cursor() as cursor:
                cursor.execute('ROLLBACK TO SAVEPOINT batch_retention_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            oracle.rollback();oracle.autocommit=True
        assert _run(['docker','exec',container,'test','-d',selected['workspace']+'/'+backup['job_id']+'/artifact']).returncode==0
        checks.append('cancelled-batch-finishes-only-original-item-with-SQL-principal-locked-and-pending-savepoint-preserved')
        ticket=review(backup);assert ticket['plan']['job_ids']==[backup['job_id']]
        with patch.object(transport.Transport,'request',lost):step(ticket,refused=True)
        step(ticket,'resume',True)
        assert reconcile(ticket)['state']=='completed'
        assert post('status',{'job_id':backup['job_id']})['state']==backup['state']
        assert _run(['docker','exec',container,'test','-d',selected['workspace']+'/'+newest['job_id']+'/artifact']).returncode==0
        checks.append('lost-host-removal-reply-reconciles-without-replay-and-preserves-newest-native-full-backup')
        if use_c and binary and driver_binary:
            create()
            proof['browser']=browser(app,output/'physical-batch-retention-desktop',sid,newest['job_id'],password,credentials,binary,driver_binary,batch=True)
            assert post('status',{'job_id':newest['job_id']})['artifact_removed']
        proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
    proof['complete']=True
    (output/'physical-batch-retention-summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
