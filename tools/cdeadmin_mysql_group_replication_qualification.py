"""Qualify native management on an isolated real three-member MySQL group."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    prefix='sr-gr-'+secrets.token_hex(5);network=prefix+'-net'
    nodes=[prefix+'-'+str(i) for i in range(3)];started=[];connections=[];network_created=False
    proof={'passed':False,'checks':[],'task_evidence':{},'image':_image_identity('mysql:9.7.0')}
    password=secrets.token_hex(16);group=str(uuid.uuid4());targets=[]
    def query(index,source,parameters=()):
        cursor=connections[index].cursor()
        try:
            cursor.execute(source,parameters)
            return cursor.fetchall() if cursor.description else []
        finally:cursor.close()
    def execute(index,operation,draft):
        request={'resource_kind':'group-replication','operation_id':operation,'draft':draft,'target_resource':targets[index]}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        result=query(index,statement['source'],statement['parameters'])
        proof['task_evidence']['visual_admin.group-replication.'+operation]={'source':statement['source'],
            'parameter_count':len(statement['parameters']),'native_execution':'passed'}
        return result
    def until(predicate,seconds=60):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.25)
        raise AssertionError('Native group observation did not converge')
    def primary(index):
        rows=query(index,"SELECT MEMBER_ID FROM performance_schema.replication_group_members WHERE MEMBER_ROLE='PRIMARY' AND MEMBER_STATE='ONLINE'")
        return rows[0][0] if len(rows)==1 else None
    try:
        _run(['docker','network','create',network]);network_created=True
        for index,node in enumerate(nodes):
            _run(['docker','run','-d','--rm','--name',node,'--network',network,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes',
                '-p','127.0.0.1::3306','mysql:9.7.0','--server-id='+str(101+index),'--gtid-mode=ON',
                '--enforce-gtid-consistency=ON','--log-bin=sr-group','--log-replica-updates=ON','--loose-group-replication-start-on-boot=OFF','--report-host='+node])
            started.append(node)
        for index,node in enumerate(nodes):
            port=_wait_until_ready('mysql',node,300)
            connection=_root_connection('mysql',port);connection.autocommit=True;connections.append(connection)
            query(index,"INSTALL PLUGIN group_replication SONAME 'group_replication.so'")
            query(index,'SET SESSION sql_log_bin=0')
            query(index,"CREATE USER 'sr_recovery'@'%' IDENTIFIED BY %s",(password,))
            query(index,"GRANT REPLICATION SLAVE, CONNECTION_ADMIN ON *.* TO 'sr_recovery'@'%'")
            query(index,'SET SESSION sql_log_bin=1')
            query(index,'SET GLOBAL group_replication_group_name=%s',(group,))
            query(index,'SET GLOBAL group_replication_local_address=%s',(node+':33061',))
            query(index,'SET GLOBAL group_replication_group_seeds=%s',(','.join(node+':33061' for node in nodes),))
            query(index,'SET GLOBAL group_replication_recovery_get_public_key=ON')
            # Only these disposable servers: Docker initialization created unrelated GTIDs.
            query(index,'RESET BINARY LOGS AND GTIDS')
            resources=_resources(connection,{'route':{}},MYSQL_PROFILE)
            targets.append(next(row for row in resources if row['resource_kind']=='group-replication'))
        query(0,'SET GLOBAL group_replication_bootstrap_group=ON')
        try:execute(0,'start',{'user':'sr_recovery','password':password,'default_auth':'caching_sha2_password'})
        finally:query(0,'SET GLOBAL group_replication_bootstrap_group=OFF')
        for index in (1,2):execute(index,'start',{'user':'sr_recovery','password':password,'default_auth':'caching_sha2_password'})
        until(lambda:all(query(i,"SELECT COUNT(*) FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE'")[0][0]==3 for i in range(3)))
        uuids=[query(i,'SELECT @@server_uuid')[0][0] for i in range(3)]
        query(0,'CREATE DATABASE sr_group_test')
        query(0,'CREATE TABLE sr_group_test.t (id INT PRIMARY KEY, value INT)')
        query(0,'INSERT INTO sr_group_test.t VALUES (42,10)')
        def replicated(index):
            try:return query(index,'SELECT * FROM sr_group_test.t')==[(42,10)]
            except Exception:return False
        until(lambda:all(replicated(i) for i in range(3)))
        execute(0,'set_primary',{'member_uuid':uuids[1],'timeout':30})
        until(lambda:all(primary(i)==uuids[1] for i in range(3)))
        execute(1,'multi_primary',{})
        until(lambda:all(query(i,'SELECT @@GLOBAL.group_replication_single_primary_mode')[0][0]==0 for i in range(3)))
        execute(1,'single_primary',{'member_uuid':uuids[2]})
        until(lambda:all(primary(i)==uuids[2] for i in range(3)))
        protocol=query(2,'SELECT group_replication_get_communication_protocol()')[0][0]
        execute(2,'set_protocol',{'version':protocol})
        concurrency=query(2,'SELECT group_replication_get_write_concurrency()')[0][0]
        execute(2,'set_write_concurrency',{'concurrency':concurrency+1})
        until(lambda:all(query(i,'SELECT group_replication_get_write_concurrency()')[0][0]==concurrency+1 for i in range(3)))
        action={'action_name':'mysql_disable_super_read_only_if_primary','event_name':'AFTER_PRIMARY_ELECTION'}
        execute(2,'disable_member_action',action);execute(2,'enable_member_action',action)
        resources=_resources(connections[2],{'route':{}},MYSQL_PROFILE)
        assert len([row for row in resources if row['resource_kind']=='group-replication-member'])==3
        for index in (0,1,2):execute(index,'stop',{})
        query(2,'SET GLOBAL super_read_only=OFF')
        execute(2,'reset_member_actions',{})
        assert all(replicated(i) for i in range(3))
        proof.update(passed=True,checks=['three real ONLINE members','data replicated to every member','primary election to a different member',
            'multi-primary and explicit single-primary transition','native protocol and distributed write-concurrency functions',
            'member action enable/disable and stopped reset','native member inventory','STOP retains replicated data'])
    finally:
        for connection in connections:
            try:connection.close()
            except Exception:pass
        stopped=[]
        for node in reversed(started):
            logs=_run(['docker','logs',node],check=False)
            (output/(node+'.log')).write_text(logs.stdout+logs.stderr)
            if _run(['docker','stop',node],check=False).returncode==0:stopped.append(node)
        proof['owned_servers_stopped']=len(stopped)==len(started)
        if network_created:proof['owned_network_removed']=_run(['docker','network','rm',network],check=False).returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True)
    qualify(parser.parse_args().output_root)
