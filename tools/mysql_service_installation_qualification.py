"""Actual systemd installation and pre-SQL lifecycle on an owned native host."""
from copy import deepcopy
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch


def cleanup(host_script,pure):
    label='pure' if pure else 'c'
    if not pure:
        host_script('from pathlib import Path;import subprocess;name="sr-installed-desktop.service";subprocess.run(["systemctl","disable","--",name],capture_output=True);Path("/etc/systemd/system/"+name).unlink(missing_ok=True)')
    host_script('from pathlib import Path;name='+repr('sr-installed-'+label+'-lost.service')+';Path("/etc/systemd/system/"+name).unlink(missing_ok=True)')
    host_script('from pathlib import Path;import subprocess,shutil;name='+repr('sr-installed-'+label+'.service')+';subprocess.run(["systemctl","stop","--",name],capture_output=True);subprocess.run(["systemctl","disable","--",name],capture_output=True);Path("/etc/systemd/system/"+name).unlink(missing_ok=True);subprocess.run(["systemctl","daemon-reload"],check=True);shutil.rmtree('+repr('/var/lib/sr-installed-'+label)+',ignore_errors=True);Path('+repr('/etc/sr-installed-'+label+'.cnf')+').unlink(missing_ok=True);Path('+repr('/etc/sr-installed-native % ${HOME} 雪/selected-'+label+'.cnf')+').unlink(missing_ok=True)')


def qualify(app,client,selected,credentials,host_script,output,pure):
    from flask import url_for
    import mysql.connector
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers.mysql_family import mysql_host_transport as native
    from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import Bridge
    from pgadmin.cdeadmin.workspace import mysql_host_service
    label='pure' if pure else 'c';target='/var/lib/sr-installed-'+label;name='sr-installed-'+label+'.service'
    cleanup(host_script,pure)
    port=43307 if pure else 43308;configuration='/etc/sr-installed-native % ${HOME} 雪/selected-'+label+'.cnf'
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        server=Server(user_id=uid,servergroup_id=group.id,name='Unverified native installation '+label,
            host='pending-installation.invalid',port=port,username='root',maintenance_db=None,save_password=0)
        server._cde_endpoint_registration=registration_profile('mysql-native')
        server._cde_endpoint_route_configuration={'host':'pending-installation.invalid','port':port,'user':'root','use_pure':pure,'credential_kinds':['database_password']}
        db.session.add(server);db.session.commit()
        url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
    def post(action,request,refused=False):
        response=client.post(url,json={'action':'mysql_host_'+action,'request':request});value=response.get_json()
        if refused:
            assert response.status_code==400,value
            return value
        if response.status_code!=200 or not value.get('success'):
            (Path(output)/('installation-http-'+label+'.json')).write_text(json.dumps(value,indent=2)+'\n')
            raise AssertionError('Native installation API failed: '+action)
        return value['data']
    def review(options):return post('review',{'options':options,'credentials':credentials})
    def admitted(value):return {**{key:value[key] for key in ('job_id','review_digest')},'confirmed':True,'credentials':credentials}
    def wait(value,state='native_process_returned'):
        deadline=time.monotonic()+120
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned native unit installation deadline')
            time.sleep(.05);value=post('status',{'job_id':value['job_id']})
        assert value['state']==state,value['state']
        return value
    content='[mysqld]\nuser=mysql\ndatadir='+target+'\nsocket='+target+'/mysql.sock\npid-file='+target+'/mysqld.pid\nport='+str(port)+'\nbind-address=127.0.0.1\nmysqlx=OFF\nskip-log-bin\ninnodb-buffer-pool-size=64M\nlog-error='+target+'/mysql-error.log\n'
    host_script('from pathlib import Path;p=Path('+repr(configuration)+');p.parent.mkdir(exist_ok=True);p.write_text('+repr(content)+')')
    base={key:deepcopy(value) for key,value in selected.items() if key not in {'service','disconnect_all_clients'}}
    base['configuration_file']=configuration
    initial={**base,'operation':'initialize_data','initialization':{'datadir':target,'user':'mysql','secure':False}}
    proof={'complete':False,'source_SQL_authority_requested':False,'checks':[],'history_testing':'not run'}
    bridge=None
    try:
        with patch.object(mysql_host_service,'source',side_effect=AssertionError('New service lifecycle must not request a SQL source')):
            initialized=wait(post('start',admitted(review(initial))))
            identity=initialized['remote_receipt']['initialization_result']['native_identity'];assert identity
            options={**base,'operation':'install_service','binding_job_id':initialized['job_id'],
                'service':{'manager':'systemd','name':name},'service_installation':{'user':'mysql'}}
            stale=review(options)
            host_script('from pathlib import Path;p=Path('+repr(configuration)+');p.write_text(p.read_text()+"# changed after review\\n")')
            post('start',admitted(stale),refused=True);post('cancel',{'job_id':stale['job_id']})
            host_script('from pathlib import Path;Path('+repr(configuration)+').write_text('+repr(content)+')')
            post('review',{'options':{**options,'service':{'manager':'systemd','name':'ssh.service'}},'credentials':credentials},refused=True)
            installed=wait(post('start',admitted(review(options))))
            (Path(output)/('installed-service-'+label+'.json')).write_text(json.dumps(installed,indent=2)+'\n')
            result=installed['remote_receipt']['service_installation_result']
            assert result['installed'] and result['daemon_reload']['return_code']==0 and result.get('installed_service_binding'),result.get('association_error_type')
            assert not result['restart_issued'] and not result['enable_issued'] and not result['sql_readiness_observed']
            association=result['installed_service_binding']
            assert association['unit']['ActiveState']=='inactive' and association['unit']['UnitFileState']=='disabled'
            assert post('start',admitted(installed))['remote_receipt']==installed['remote_receipt']
            post('review',{'options':options,'credentials':credentials},refused=True)
            proof['checks'].append('actual-new-unit-native-validation-exclusive-installation-no-replacement-no-start-no-enable-stale-input-refusal-and-no-replay')
            uncertain=review({**options,'service':{'manager':'systemd','name':'sr-installed-'+label+'-lost.service'}})
            original=native.Transport.request;suppressed=[]
            def lost(transport,request,*args,**kwargs):
                result=original(transport,request,*args,**kwargs)
                if request.get('action')=='install_service':
                    suppressed.append(result);raise OSError('Owned missing original installation SSH reply')
                return result
            with patch.object(native.Transport,'request',lost):uncertain=wait(post('start',admitted(uncertain)),'unknown')
            assert len(suppressed)==1 and not uncertain.get('ssh_reply_observed')
            later=post('reconcile',{'job_id':uncertain['job_id'],'credentials':credentials})
            facts=later['reconciliation']['remote_receipt']['service_installation_reconciliation']
            assert later['state']=='unknown' and not later.get('ssh_reply_observed') and facts['matches_installed_unit']
            assert facts['phase_receipt']['native_result_scope']=='systemd_daemon_reload' and facts['phase_receipt']['daemon_reload']['return_code']==0
            assert post('start',admitted(uncertain))['state']=='unknown' and len(suppressed)==1
            proof['checks'].append('actual-native-installation-with-lost-SSH-reply-preserves-original-unknown-acknowledgement-independent-phase-file-manager-facts-and-no-replay')
            def control(operation,reference=installed):
                chosen={**base,'operation':operation,'binding_job_id':reference['job_id'],'service':options['service'],
                    **({'disconnect_all_clients':True} if operation in {'service_stop','service_restart'} else {})}
                planned=review(chosen)
                assert planned['source_identity_scope']=='previous_installed_native_service_association'
                return wait(post('start',admitted(planned)))
            for operation,expected in (('service_enable','enabled'),('service_disable','disabled')):
                value=control(operation)
                assert value['remote_receipt']['result']['return_code']==0
                assert value['remote_receipt']['service_after_process']['service']['unit']['UnitFileState']==expected
            started=control('service_start')
            assert started['remote_receipt']['service_request']['manager_client_completed']
            ssh=native.Transport(selected['connection'],credentials);ssh.connect()
            adapter=SimpleNamespace(open_stream=lambda _request:ssh.transport.open_channel('direct-tcpip',('127.0.0.1',port),('127.0.0.1',0)),close=ssh.close)
            bridge=Bridge({},adapter,{})
            deadline=time.monotonic()+90
            while True:
                try:
                    connection=mysql.connector.connect(host='127.0.0.1',port=bridge.port,user='root',password='',use_pure=pure,connection_timeout=2)
                    break
                except mysql.connector.Error:
                    if time.monotonic()>deadline:raise TimeoutError('Installed native service SQL acceptance deadline')
                    time.sleep(.1)
            try:
                cursor=connection.cursor();cursor.execute('SELECT @@server_uuid,@@datadir,VERSION()');facts=cursor.fetchone()
                assert facts[0]==identity['server_uuid'] and facts[1].rstrip('/')==target and facts[2]=='9.7.0'
                cursor.execute('CREATE DATABASE sr_installed_service');cursor.execute('CREATE TABLE sr_installed_service.t(id BIGINT PRIMARY KEY)')
                cursor.execute('INSERT INTO sr_installed_service.t VALUES(9007199254740993)');connection.commit();cursor.close()
            finally:connection.close()
            reconciled=post('reconcile',{'job_id':started['job_id'],'credentials':credentials})
            observed=reconciled['reconciliation']['remote_receipt']['service_reconciliation']
            assert observed['observed'] and observed['service']['unit']['ActiveState']=='active'
            assert observed['service']['native_process']['unit_control_group_verified']
            stopped=control('service_stop',started);assert stopped['remote_receipt']['result']['return_code']==0
            restarted=control('service_start',stopped)
            deadline=time.monotonic()+90
            while True:
                try:
                    connection=mysql.connector.connect(host='127.0.0.1',port=bridge.port,user='root',password='',use_pure=pure,connection_timeout=2)
                    cursor=connection.cursor();cursor.execute('SELECT @@server_uuid,(SELECT CAST(id AS CHAR) FROM sr_installed_service.t)');assert cursor.fetchone()==(identity['server_uuid'],'9007199254740993')
                    cursor.close();connection.close();break
                except mysql.connector.Error:
                    if time.monotonic()>deadline:raise TimeoutError('Installed service restart acceptance deadline')
                    time.sleep(.1)
            control('service_stop',restarted)
            proof['checks'].append('native-boot-enable-disable-and-start-before-SQL-verification-independent-UUID-data-and-control-group-acceptance-and-reviewed-stop')
            later=post('reconcile',{'job_id':installed['job_id'],'credentials':credentials})
            assert later['reconciliation']['remote_receipt']['service_installation_reconciliation']['matches_installed_unit']
            proof.update(complete=True,server_id=server.id,native_identity=identity,initialized_job_id=initialized['job_id'],installed_job_id=installed['job_id'])
    finally:
        if bridge is not None:bridge.close();bridge.thread.join(timeout=5)
        host_script('import subprocess;subprocess.run(["systemctl","stop","--",'+repr(name)+'],check=False)')
    (Path(output)/('service-installation-'+label+'.json')).write_text(json.dumps(proof,indent=2)+'\n')
    return proof
