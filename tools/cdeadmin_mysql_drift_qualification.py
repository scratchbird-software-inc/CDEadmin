"""Native full-scan and GTID-aligned replica acceptance on both MySQL drivers."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def terminal(post,result,seconds=60):
    deadline=time.monotonic()+seconds
    while not result['terminal'] and time.monotonic()<deadline:
        time.sleep(.05);result=post('status',{'job_id':result['job_id']})
    assert result['terminal'],result
    return result


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    network='sr-drift-'+secrets.token_hex(7)
    proof={'complete':False,'interfaces':[],'history_testing':'not run'};first=second=None
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_drift.py','web/pgadmin/cdeadmin/workspace/mysql_drift_jobs.py',
        'web/pgadmin/cdeadmin/workspace/mysql_drift_service.py',str(Path(__file__).relative_to(ROOT))]
    proof['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    subprocess.run(['docker','network','create',network],capture_output=True,check=True)
    try:
        with server(output/'source',network=network,server_id=101) as (route,source_name,first):
            with server(output/'target',network=network,server_id=102) as (target_route,_target_name,second):
                primary=_root_connection('mysql',route['port']);primary.autocommit=True;source=primary.cursor()
                secondary=_root_connection('mysql',target_route['port']);secondary.autocommit=True;target=secondary.cursor()
                try:
                    password=secrets.token_urlsafe(24);replication=secrets.token_urlsafe(24)
                    source.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    source.execute('CREATE DATABASE sr_osc CHARACTER SET utf8mb4');source.execute('USE sr_osc')
                    source.execute("CREATE TABLE typed(id BIGINT UNSIGNED PRIMARY KEY,n DECIMAL(65,30),f DOUBLE,"
                        "flags SET('a','b','雪'),e ENUM('','x'),d DATETIME(6),z TIMESTAMP(6) NULL,j JSON,g GEOMETRY,v VECTOR(3),b LONGBLOB,"
                        'hidden INT INVISIBLE,derived INT GENERATED ALWAYS AS (hidden+1) STORED)')
                    source.execute("INSERT INTO typed(id,n,f,flags,e,d,z,j,g,v,b,hidden) VALUES(18446744073709551615,"
                        "12345678901234567890123456789012345.000000000000000000000000000001,1.0,'a,b','',"
                        "'2026-01-02 03:04:05.123456','2026-01-02 03:04:05.123456',JSON_OBJECT('雪','retained'),"
                        "ST_GeomFromText('POINT(1 2)',4326),STRING_TO_VECTOR('[1,-2,3]'),UNHEX('00ff2500'),7)")
                    source.execute('CREATE TABLE no_key(value VARCHAR(80))');source.execute("INSERT INTO no_key VALUES('a'),('a'),('b'),('b')")
                    source.execute('CREATE TABLE myisam(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=MyISAM');source.execute("INSERT INTO myisam VALUES(1,'native local')")
                    source.execute('CREATE TABLE big(id INT PRIMARY KEY,note VARCHAR(80))');source.executemany('INSERT INTO big VALUES(%s,%s)',[(i,'native-full-scope') for i in range(12000)])
                    source.execute('CREATE TABLE pending(id INT PRIMARY KEY)')
                    source.execute("CREATE USER 'sr_repl'@'%' IDENTIFIED BY %s",(replication,));source.execute("GRANT REPLICATION SLAVE ON *.* TO 'sr_repl'@'%'")
                    target.execute('CHANGE REPLICATION SOURCE TO SOURCE_HOST=%s,SOURCE_PORT=3306,SOURCE_USER=%s,SOURCE_PASSWORD=%s,SOURCE_AUTO_POSITION=1,GET_SOURCE_PUBLIC_KEY=1',
                        (source_name,'sr_repl',replication));target.execute('START REPLICA')
                    def catchup():
                        source.execute('SELECT @@gtid_executed');position=source.fetchone()[0]
                        target.execute('SELECT WAIT_FOR_EXECUTED_GTID_SET(%s,30)',(position,));assert target.fetchone()[0]==0
                    catchup();target.execute('SET SESSION sql_log_bin=0');target.execute('USE sr_osc')
                    app=setup_application(output)
                    for use_c in (False,True):
                        sid,dbtarget,raw=registration(app,route,password,use_c)
                        peer,_target_id,_=registration(app,target_route,password,use_c)
                        def post(operation,request):return raw('mysql_drift_'+operation,{'peer_endpoint_id':peer,**request})
                        def pairs(names):
                            result=[]
                            for name in names:
                                left=post('describe',{'side':'source','schema_name':'sr_osc','table_name':name})
                                right=post('describe',{'side':'target','schema_name':'sr_osc','table_name':name})
                                result.append({'source_table':name,'target_table':name,'source_fingerprint':left['fingerprint'],'target_fingerprint':right['fingerprint']})
                            return result
                        policy={'consistency':'innodb_snapshot','replica':False,'channel':'','seconds':45,'disk_mib':32,'examples':10}
                        def start(names=None,options=None,selected=None):
                            return post('start',{'source_schema':'sr_osc','target_schema':'sr_osc','tables':selected or pairs(names),
                                'options':options or policy,'confirmed':True})
                        def check(result,state):
                            assert result['state']=='completed' and all(r['state']==state for r in result['coverage']),result
                            assert all('CMySQLConnection' in i['native_interface'] if use_c else 'CMySQLConnection' not in i['native_interface'] for i in result['identities']),result
                            assert result['release'][-1]['private_sort_files_removed'] and not result['repair_dispatched'],result
                        checks=[]
                        result=terminal(post,start(['typed','no_key']));check(result,'matched');checks.append('full-native-types-invisible-generated-vector-spatial-and-duplicate-multiplicity')
                        target.execute("DELETE FROM no_key WHERE value='a' LIMIT 1");target.execute("DELETE FROM no_key WHERE value='b' LIMIT 1");target.execute("INSERT INTO no_key VALUES('c'),('c')")
                        result=terminal(post,start(['no_key']));check(result,'different');assert result['coverage'][0]['source_only_rows']==result['coverage'][0]['target_only_rows']=='2'
                        target.execute('TRUNCATE TABLE no_key');target.execute("INSERT INTO no_key VALUES('a'),('a'),('b'),('b')")
                        checks.append('equal-count-keyless-multiplicity-drift-detected')
                        target.execute('UPDATE typed SET f=%s',(math.nextafter(1.0,2.0),))
                        result=terminal(post,start(['typed']));check(result,'different');target.execute('UPDATE typed SET f=1.0')
                        checks.append('adjacent-IEEE-double-values-remain-distinct')
                        result=terminal(post,start(['typed'],{**policy,'replica':True}));check(result,'matched')
                        assert result['positions'][1]['reviewed_source_gtid_applied'];checks.append('native-GTID-aligned-registered-replica-boundary')
                        target.execute('STOP REPLICA SQL_THREAD');result=terminal(post,start(['typed'],{**policy,'replica':True}))
                        assert result['state']=='incomplete' and not any(r['state']=='matched' for r in result['coverage']),result
                        target.execute('START REPLICA SQL_THREAD');catchup();checks.append('stopped-replica-refuses-alignment-with-no-fallback')
                        result=terminal(post,start(['myisam'],{**policy,'consistency':'locked_scan'}));check(result,'matched')
                        result=terminal(post,start(['myisam']));assert result['state']=='incomplete',result
                        checks.append('native-nontransactional-server-locked-scan-and-snapshot-refusal')
                        stale=pairs(['typed']);target.execute('ALTER TABLE typed ADD COLUMN later INT')
                        result=terminal(post,start(selected=stale));assert result['state']=='incomplete',result
                        result=terminal(post,start(['typed']));assert result['state']=='partial' and result['coverage'][0]['state']=='schema-different',result
                        target.execute('ALTER TABLE typed DROP COLUMN later');checks.append('stale-identity-and-logical-schema-differences-never-match')
                        baseline_big=terminal(post,start(['big']));check(baseline_big,'matched')
                        from pgadmin.cdeadmin.providers.mysql_family import mysql_drift as native
                        original_scan=native.scan;paused=threading.Event();release=threading.Event()
                        def paused_scan(observer,schema,table,*args):
                            if table['table_name']=='big' and observer.identity['server_uuid']==first['server_uuid']:
                                paused.set();assert release.wait(15)
                            return original_scan(observer,schema,table,*args)
                        with patch.object(native,'scan',side_effect=paused_scan):
                            running=start(['big']);assert paused.wait(15)
                            try:source.execute("UPDATE sr_osc.big SET note=CONCAT(note,' new') WHERE id=1")
                            finally:release.set()
                            result=terminal(post,running);check(result,'matched')
                        assert result['coverage'][0]['source_multiset_sha256']==baseline_big['coverage'][0]['source_multiset_sha256']
                        catchup();checks.append('native-pinned-snapshots-survive-concurrent-committed-DML')
                        result=terminal(post,start(['big'],{**policy,'disk_mib':1}));assert result['state']=='incomplete' and not any(r['state']=='matched' for r in result['coverage']),result
                        assert result['release'][-1]['private_sort_files_removed'];checks.append('native-full-scan-disk-bound-is-incomplete-and-cleans-private-files')
                        selected=pairs(['big']);source.execute('LOCK TABLES sr_osc.big WRITE')
                        try:
                            running=start(selected=selected);post('cancel',{'job_id':running['job_id']})
                            result=terminal(post,running);assert result['state']=='cancelled' and not any(r['state']=='matched' for r in result['coverage']),result
                        finally:source.execute('UNLOCK TABLES')
                        checks.append('owned-native-cancellation-releases-global-locks-and-private-runs')
                        primary.autocommit=False
                        try:
                            source.execute('INSERT INTO sr_osc.pending VALUES(99)');source.execute('SAVEPOINT drift_guard')
                            source.execute("SELECT CAST('original warning' AS UNSIGNED)");source.fetchall()
                            source.execute('SHOW COUNT(*) WARNINGS');warnings=source.fetchone()[0];assert warnings
                            terminal(post,start(['typed'],{**policy,'seconds':3}))
                            assert primary.in_transaction
                            source.execute('SHOW COUNT(*) WARNINGS');assert source.fetchone()[0]==warnings
                            source.execute('ROLLBACK TO SAVEPOINT drift_guard');source.execute('SELECT COUNT(*) FROM sr_osc.pending');assert source.fetchone()[0]==1
                        finally:primary.rollback();primary.autocommit=True
                        checks.append('independent-pending-transaction-savepoint-and-native-warning-area')
                        source.execute('SELECT COUNT(*) FROM pending');assert source.fetchone()[0]==0
                        proof['interfaces'].append({'use_c':use_c,'complete':True,'checks':checks})
                    proof['complete']=True
                finally:source.close();target.close();primary.close();secondary.close()
    finally:
        result=subprocess.run(['docker','network','rm',network],capture_output=True)
        proof.update(network_removed=result.returncode==0,source_stopped=bool(first and first['owned_server_stopped']),target_stopped=bool(second and second['owned_server_stopped']))
        proof['complete'] &= proof['network_removed'] and proof['source_stopped'] and proof['target_stopped']
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();qualify(args.output)
