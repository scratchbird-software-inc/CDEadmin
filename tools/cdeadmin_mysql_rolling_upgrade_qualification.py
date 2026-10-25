"""Rolling native upgrade of an explicitly owned, real three-member Cluster."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,fixture,use_c=False):
    import mysql.connector
    from cdeadmin_mysql_upgrade_qualification import qualify as upgrade
    output=Path(output).resolve();output.mkdir(exist_ok=False)
    fixture=Path(fixture).resolve();owned=json.loads(fixture.read_text())
    assert owned['complete'] and owned['network'].startswith('sr-upgrade246-')
    peers=owned['peers'];assert len(peers)==3
    proof={'complete':False,'use_c':use_c,'checks':[],'members':[],
           'history_testing':'ScratchBird history not run'}
    schema='sr_rolling_'+secrets.token_hex(5)
    def sql(peer,source,parameters=()):
        connection=mysql.connector.connect(host=peers[peer].get('application_host','127.0.0.1'),port=peers[peer]['sql_port'],
            user='sr_upgrade',password='owned-upgrade-private',use_pure=not use_c,
            autocommit=True,connection_timeout=3,read_timeout=5)
        cursor=connection.cursor(dictionary=True)
        try:
            cursor.execute(source,parameters)
            return cursor.fetchall() if cursor.with_rows else []
        finally:cursor.close();connection.close()
    def wait(description,read,expected,timeout=120):
        deadline=time.monotonic()+timeout
        while True:
            try:
                actual=read()
                if actual==expected:return actual
            except mysql.connector.Error:
                if time.monotonic()>deadline:raise
            if time.monotonic()>deadline:raise TimeoutError(description+': '+repr(actual))
            time.sleep(.2)
    def metadata(peer):
        return {'version':sql(peer,'SELECT major,minor,patch FROM mysql_innodb_cluster_metadata.schema_version'),
            'clusters':sql(peer,'SELECT cluster_id,cluster_name,cluster_type FROM mysql_innodb_cluster_metadata.clusters ORDER BY cluster_id'),
            'instances':sql(peer,'SELECT instance_id,mysql_server_uuid,instance_name FROM mysql_innodb_cluster_metadata.instances ORDER BY instance_id')}
    identities=[sql(i,'SELECT @@server_uuid AS uuid,VERSION() AS version')[0] for i in range(3)]
    assert len({p['uuid'] for p in identities})==3 and all(p['version']=='8.4.8' for p in identities)
    original=metadata(0);assert original['version']==[{'major':2,'minor':2,'patch':0}],original
    sql(0,'CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
    sql(0,'CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
    sql(0,'INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'native upgrade 雪',b'\x00\xff'))
    expected=[{'id':'9007199254740993','body':'native upgrade 雪','payload':'00FF'}]
    query='SELECT CAST(id AS CHAR) AS id,body,HEX(payload) AS payload FROM '+schema+'.t'
    def group(peer):return sql(peer,'SELECT MEMBER_ID AS uuid,MEMBER_STATE AS state,MEMBER_ROLE AS role,MEMBER_VERSION AS version FROM performance_schema.replication_group_members ORDER BY MEMBER_ID')
    def healthy(peer):
        members=group(peer)
        return len(members)==3 and all(p['state']=='ONLINE' for p in members)
    for i in range(3):
        wait('Original native Cluster data',lambda i=i:sql(i,query),expected)
        wait('Original native Cluster membership',lambda i=i:healthy(i),True)
    proof['original_metadata']=original
    proof['original_members']=group(0)
    proof['checks'].append('genuine-native-8.4-Shell-created-2.2-metadata-and-three-online-native-8.4.8-members')
    def callback(index):
        def observed(app,client,url,server_id,uuid,local_sql,path):
            def post(action,request):
                response=client.post(url,json={'action':'mysql_topology_'+action,'request':request})
                value=response.get_json();assert response.status_code==200 and value.get('success'),value
                return value['data']
            def call(operation,arguments=(),read=False):
                selected={'operation':operation,'arguments_json':json.dumps(list(arguments)),
                    'context_name':'','context_options_json':'{}','use_advertised_endpoint':True,
                    'witness_server_ids':[],'target_confirmation':uuid,'timeout_seconds':120}
                if read:value=post('inspect_native',{'options':selected})
                else:
                    review=post('review',{'options':selected})
                    value=post('start',{**{k:review[k] for k in ('job_id','review_digest')},'confirmed':True})
                deadline=time.monotonic()+150
                while value['state'] in {'dispatching','active','cancel_requested'}:
                    if time.monotonic()>deadline:raise TimeoutError('Native rolling topology operation deadline')
                    time.sleep(.1);value=post('status',{'job_id':value['job_id']})
                (path/(operation.replace('.','-')+'.json')).write_text(json.dumps(value,indent=2)+'\n')
                assert value['native_operation_outcome']=='returned' and value['native_process_termination_confirmed'],value.get('native_error') or value.get('error_type')
                assert value['workload_readiness_verified'] is False
                return json.loads(value['result']['control']['result_json'])
            wait('Upgraded native member rejoins original Cluster',lambda:healthy(index),True)
            wait('Upgraded native member retains replicated data',lambda:local_sql(query),expected)
            if index==1:
                before=metadata(index);assert before==original
                call('instance.upgrade_metadata')
                after=metadata(index)
                assert after['version']==[{'major':2,'minor':4,'patch':0}],after
                assert after['clusters']==original['clusters'] and after['instances']==original['instances']
                proof['metadata_upgrade']={'before':before,'after':after}
                proof['checks'].append('reviewed-native-metadata-upgrade-2.2-to-2.4-preserves-original-Cluster-and-instance-identities')
            if index==0:
                # Native Group Replication keeps the lowest-version member
                # primary during a mixed-version upgrade. Stopping that last
                # old primary elects an upgraded peer; deliberate promotion
                # is admissible after all members run the new version.
                elected=local_sql('SELECT MEMBER_ID AS uuid FROM performance_schema.replication_group_members WHERE MEMBER_ROLE=\'PRIMARY\'')
                assert len(elected)==1 and elected[0]['uuid'] in {identities[i]['uuid'] for i in (1,2)}
                call('cluster.set_primary',[{'server_id':server_id}])
                wait('Reviewed native promotion after all member upgrades',
                    lambda:local_sql('SELECT MEMBER_ID AS uuid FROM performance_schema.replication_group_members WHERE MEMBER_ROLE=\'PRIMARY\''),[{'uuid':uuid}])
                proof['checks'].append('native-election-when-last-old-primary-stops-and-reviewed-primary-handoff-after-all-member-upgrades')
            status=call('cluster.status',[{'extended':1}],read=True)
            return {'complete':True,'group':group(index),'native_status':status}
        return observed
    try:
        for index in (1,2,0):
            path=output/('member'+str(index))
            selected=Path(peers[index]['qualification_fixture'])
            result=upgrade(path,selected,use_c,checkpoint=schema,after_upgrade=callback(index))
            assert result['complete'] and result['owned_jobs_stopped']
            proof['members'].append({'index':index,'receipt':path.name+'/summary.json','job_id':result['job_id']})
            for peer in range(3):
                wait('Replicated data after rolling step',lambda peer=peer:sql(peer,query),expected)
            primary=[i for i in range(3) if sql(i,'SELECT @@super_read_only AS ro')[0]['ro']==0]
            assert len(primary)==1
            sql(primary[0],'INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(index+1,'rolling checkpoint '+str(index),bytes([index,255])))
            # Keep the existing upgrade exact-data checkpoint unchanged while
            # independently proving fresh writes reach all three native peers.
            for peer in range(3):
                wait('Fresh write replication after rolling step',lambda peer=peer:sql(peer,'SELECT HEX(payload) AS payload FROM '+schema+'.t WHERE id=%s',(index+1,)),[{'payload':bytes([index,255]).hex().upper()}])
            sql(primary[0],'DELETE FROM '+schema+'.t WHERE id=%s',(index+1,))
            for peer in range(3):wait('Owned checkpoint reset replication',lambda peer=peer:sql(peer,query),expected)
            (output/'progress.json').write_text(json.dumps(proof,indent=2)+'\n')
        final=[sql(i,'SELECT @@server_uuid AS uuid,VERSION() AS version')[0] for i in range(3)]
        assert final==[{**p,'version':'9.7.0'} for p in identities]
        assert all(p['version']=='9.7.0' and p['state']=='ONLINE' for p in group(0))
        assert all(metadata(i)==proof['metadata_upgrade']['after'] for i in range(3))
        proof['checks'].append('secondary-first-native-rolling-8.4.8-to-9.7-upgrade-preserves-all-original-UUIDs-quorum-exact-data-and-fresh-write-replication')
        proof.update(complete=True,final_members=group(0),owned_jobs_stopped=True)
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--fixture',required=True);parser.add_argument('--use-c',action='store_true');args=parser.parse_args()
    result=qualify(args.output,args.fixture,args.use_c);print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))
