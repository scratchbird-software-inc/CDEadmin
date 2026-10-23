"""Qualify registered native replica lag gates without credential delegation."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def until(post,receipt,predicate,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        receipt=post('mysql_online_ddl_status',{'review_id':receipt['review_id']})
        if predicate(receipt):return receipt
        if receipt.get('controlled_terminal'):raise AssertionError(receipt)
        time.sleep(.1)
    raise AssertionError(receipt)


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration,terminal
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import _json
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    network='sr-osc-'+secrets.token_hex(7)
    proof={'complete':False,'interfaces':[],'history_testing':'not run','network_removed':False}
    first=second=None
    paths=['web/pgadmin/cdeadmin/workspace/mysql_online_replicas.py','web/pgadmin/cdeadmin/workspace/mysql_online_service.py',
        'web/pgadmin/cdeadmin/workspace/mysql_online_jobs.py','web/pgadmin/cdeadmin/providers/mysql_online_copy.py',
        'web/pgadmin/cdeadmin/providers/mysql_online_copy_hook.pl',str(Path(__file__).relative_to(ROOT))]
    proof['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    subprocess.run(['docker','network','create',network],check=True,capture_output=True)
    try:
        with server(output/'source',network=network,server_id=101) as (route,source_name,first):
            with server(output/'replica',network=network,server_id=102) as (replica_route,replica_name,second):
                primary=_root_connection('mysql',route['port']);primary.autocommit=True;source=primary.cursor()
                secondary=_root_connection('mysql',replica_route['port']);secondary.autocommit=True;replica=secondary.cursor()
                try:
                    password=secrets.token_urlsafe(24);replication=secrets.token_urlsafe(24);monitor_password=secrets.token_urlsafe(24)
                    source.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    source.execute('CREATE DATABASE sr_osc CHARACTER SET utf8mb4');source.execute('CREATE TABLE sr_osc.t(id INT PRIMARY KEY,note VARCHAR(80))')
                    source.execute("INSERT INTO sr_osc.t VALUES(1,'preserved')")
                    source.execute("CREATE USER 'sr_repl'@'%' IDENTIFIED BY %s",(replication,))
                    source.execute("GRANT REPLICATION SLAVE ON *.* TO 'sr_repl'@'%'")
                    replica.execute('CHANGE REPLICATION SOURCE TO SOURCE_HOST=%s,SOURCE_PORT=3306,SOURCE_USER=%s,SOURCE_PASSWORD=%s,SOURCE_AUTO_POSITION=1,GET_SOURCE_PUBLIC_KEY=1',
                        (source_name,'sr_repl',replication));replica.execute('START REPLICA')
                    def catchup():
                        source.execute('SELECT @@gtid_executed');position=source.fetchone()[0]
                        replica.execute('SELECT WAIT_FOR_EXECUTED_GTID_SET(%s,20)',(position,));assert replica.fetchone()[0]==0
                    catchup()
                    replica.execute('SET SESSION sql_log_bin=0')
                    replica.execute("CREATE USER 'sr_lag_monitor'@'%' IDENTIFIED BY %s",(monitor_password,))
                    replica.execute("GRANT REPLICATION CLIENT ON *.* TO 'sr_lag_monitor'@'%'")
                    replica.execute("GRANT SELECT ON sr_osc.* TO 'sr_lag_monitor'@'%'")
                    replica.execute('SET SESSION sql_log_bin=1')
                    app=setup_application(output)
                    for use_c in (False,True):
                        sid,target,post=registration(app,route,password,use_c)
                        replica_id,_replica_target,_=registration(app,replica_route,monitor_password,use_c,'sr_lag_monitor')
                        baseline=post('mysql_catalog_export',{})['snapshot'];desired=deepcopy(baseline)
                        parsed=read_catalog(json.dumps(baseline),engine='mysql')
                        table=next(v for v in parsed['rows'].values() if v['kind']=='table' and v['name']=='t')
                        old=_json(_json(table['native']));native=deepcopy(table['native']);native['definition']=native['definition'].replace('varchar(80)','text')
                        new=_json(_json(native));desired['files']={key:value.replace(old,new) for key,value in desired['files'].items()}
                        selected={'method':'pt-online-schema-change','algorithm':'COPY','lock':'NONE','lock_wait_seconds':2,'timeout_seconds':60,
                            'replicas':[{'endpoint_id':replica_id,'channel':'','max_lag_seconds':1}]}
                        request={'baseline':json.dumps(baseline),'source':json.dumps(desired),'execution':selected}
                        preview=post('mysql_schema_validate',request);assert preview['native_grammar_validated'],preview
                        receipt=post('mysql_schema_review',{**request,'execution_sha256':preview['execution_sha256']})
                        replica.execute('STOP REPLICA SQL_THREAD')
                        source.execute("UPDATE sr_osc.t SET note='DML during lag controlled copy' WHERE id=1")
                        receipt=post('mysql_online_ddl_start',{'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True})
                        paused=until(post,receipt,lambda r:r.get('controlled_job',{}).get('replica_policy_ready') is False)
                        assert paused['controlled_job']['replica_observations'][0]['seconds_behind_source'] is None
                        assert paused['controlled_job'].get('copy_stage')!='cutover-admitted'
                        replica.execute('START REPLICA SQL_THREAD');catchup()
                        waiting=until(post,receipt,lambda r:r.get('controlled_job',{}).get('copy_stage')=='cutover-waiting' and r['controlled_job'].get('replica_policy_ready') is True)
                        replica.execute('STOP REPLICA SQL_THREAD')
                        rejected=post.raw('mysql_online_ddl_cutover',{'review_id':receipt['review_id']}).get_json();assert not rejected['success'],rejected
                        source.execute("SHOW COLUMNS FROM sr_osc.t LIKE 'note'");assert source.fetchone()[1]=='varchar(80)'
                        replica.execute('START REPLICA SQL_THREAD');catchup()
                        until(post,receipt,lambda r:r.get('controlled_job',{}).get('replica_policy_ready') is True)
                        post('mysql_online_ddl_cutover',{'review_id':receipt['review_id']})
                        result=terminal(post,waiting);assert result['state']=='committed' and result['outcome']['utility_cleanup_confirmed'],result
                        catchup();replica.execute("SHOW COLUMNS FROM sr_osc.t LIKE 'note'");assert replica.fetchone()[1]=='text'
                        replica.execute('SELECT note FROM sr_osc.t WHERE id=1');assert replica.fetchone()[0]=='DML during lag controlled copy'
                        proof['interfaces'].append({'use_c':use_c,'complete':True,'checks':['exact-registered-channel-source-binding',
                            'stopped-SQL-channel-pauses-copy-with-native-unknown-lag','fresh-stopped-channel-refuses-cutover',
                            'native-replication-resume-releases-pause','native-source-and-replica-data-and-schema-after-cutover',
                            'distinct-replica-password-stays-in-owned-native-observer']})
                        source.execute('ALTER TABLE sr_osc.t MODIFY note VARCHAR(80)');catchup()
                    proof['complete']=True
                finally:source.close();replica.close();primary.close();secondary.close()
    finally:
        result=subprocess.run(['docker','network','rm',network],capture_output=True)
        proof.update(network_removed=result.returncode==0,source_stopped=bool(first and first['owned_server_stopped']),replica_stopped=bool(second and second['owned_server_stopped']))
        proof['complete'] &= proof['network_removed'] and proof['source_stopped'] and proof['replica_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();qualify(args.output)
