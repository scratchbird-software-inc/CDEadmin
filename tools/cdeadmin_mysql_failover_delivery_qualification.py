"""Three owned servers: native weighted source failover and GTID delivery."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    import config
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    network='sr-failover-'+secrets.token_hex(8);owned=[];connections=[];cursors=[]
    proof={'complete':False,'owned_servers_stopped':False,'owned_network_removed':False,
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ['web/pgadmin/cdeadmin/providers/mysql_family/mysql_failover.py',str(Path(__file__).relative_to(ROOT))]}}
    def docker(*args):return subprocess.run(['docker',*args],check=True,capture_output=True,text=True).stdout
    def cursor(route):
        handle=_root_connection('mysql',route['port']);connections.append(handle);handle.autocommit=True
        query=handle.cursor();cursors.append(query);return query
    def wait(query,source,expected,timeout=90):
        deadline=time.monotonic()+timeout
        while True:
            try:
                query.execute(source);rows=query.fetchall()
            except Exception as error:
                if getattr(error,'errno',None) not in {1049,1146}:raise
                rows=None
            if rows==expected:return
            if time.monotonic()>deadline:raise TimeoutError('Native failover did not reach the selected data/receiver observation')
            time.sleep(.1)
    docker('network','create',network)
    try:
        with ExitStack() as stack:
            first,host_a,a=stack.enter_context(server(output/'source-a',network=network,server_id=101,restartable=True));owned.append(a)
            second,host_b,b=stack.enter_context(server(output/'source-b',network=network,server_id=102));owned.append(b)
            replica,_name,c=stack.enter_context(server(output/'replica',network=network,server_id=103));owned.append(c)
            qa,qb,qr=cursor(first),cursor(second),cursor(replica);password=secrets.token_urlsafe(20)
            qa.execute('CREATE DATABASE sr_failover');qa.execute('CREATE TABLE sr_failover.t(id INT PRIMARY KEY,note VARCHAR(40))')
            qa.execute("INSERT INTO sr_failover.t VALUES(1,'from-first')")
            qa.execute('CREATE USER failover_repl IDENTIFIED BY %s',(password,));qa.execute('GRANT REPLICATION SLAVE ON *.* TO failover_repl')
            qa.execute('SELECT @@GLOBAL.gtid_executed');prefix=qa.fetchone()[0]
            # Seed the second native source with the same acknowledged checkpoint.
            # Fixture setup uses native SQL; the application does not emulate replication.
            qb.execute('RESET BINARY LOGS AND GTIDS');qb.execute('SET SESSION sql_log_bin=0')
            qb.execute('CREATE DATABASE sr_failover');qb.execute('CREATE TABLE sr_failover.t(id INT PRIMARY KEY,note VARCHAR(40))')
            qb.execute("INSERT INTO sr_failover.t VALUES(1,'from-first')")
            qb.execute('CREATE USER failover_repl IDENTIFIED BY %s',(password,));qb.execute('GRANT REPLICATION SLAVE ON *.* TO failover_repl')
            qb.execute('SET GLOBAL gtid_purged=%s',(prefix,));qb.execute('SET SESSION sql_log_bin=1')
            qr.execute("CHANGE REPLICATION SOURCE TO SOURCE_HOST=%s,SOURCE_PORT=3306,SOURCE_USER='failover_repl',SOURCE_PASSWORD=%s,"
                "SOURCE_AUTO_POSITION=1,SOURCE_SSL=1,SOURCE_CONNECT_RETRY=1,SOURCE_RETRY_COUNT=1 FOR CHANNEL 'native_failover'",(host_a,password))
            qr.execute('SELECT @@server_uuid');instance=qr.fetchone()[0]
            target={'resource_kind':'replication-channel','display_name':'Native failover','native':{'channel_name':'native_failover','server_uuid':instance}}
            classes=[]
            for pure,host,weight in [(True,host_a,100),(False,host_b,1)]:
                client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                try:
                    request=client.plan_admin_operation({'resource_kind':'replication-channel','operation_id':'add_failover_source',
                        'draft':{'confirmation':target['display_name'],'host':host,'port':3306,'weight':weight},'target_resource':target,'_provider_route':{**replica,'use_pure':pure}})
                    value=MYSQL_ADMINISTRATION.apply(client,request);assert value['native_acknowledged']
                    classes.append('pure' if pure else 'c')
                finally:client.close()
            qr.execute("CHANGE REPLICATION SOURCE TO SOURCE_CONNECTION_AUTO_FAILOVER=1 FOR CHANNEL 'native_failover'")
            qr.execute("START REPLICA FOR CHANNEL 'native_failover'")
            wait(qr,"SELECT SERVICE_STATE FROM performance_schema.replication_connection_status WHERE CHANNEL_NAME='native_failover'",[('ON',)])
            wait(qr,'SELECT id,note FROM sr_failover.t ORDER BY id',[(1,'from-first')])
            qa.close();connections[0].close();cursors.remove(qa);connections.pop(0)
            docker('stop','--time','5',host_a)
            qb.execute("INSERT INTO sr_failover.t VALUES(2,'from-second')")
            wait(qr,"SELECT HOST FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME='native_failover'",[(host_b,)])
            wait(qr,'SELECT id,note FROM sr_failover.t ORDER BY id',[(1,'from-first'),(2,'from-second')])
            qr.execute('SELECT @@GLOBAL.gtid_executed');executed=qr.fetchone()[0]
            qb.execute('SELECT @@GLOBAL.gtid_executed');required=qb.fetchone()[0]
            qr.execute('SELECT GTID_SUBSET(%s,%s)',(required,executed));assert qr.fetchone()==(1,)
            qr.execute("STOP REPLICA FOR CHANNEL 'native_failover'")
            proof.update(complete=True,source_shutdown_observed=True,native_candidate_switch_observed=True,
                exact_data_before_and_after=True,gtid_catchup_observed=True,candidate_administration_interfaces=classes,
                application_election_or_sql_replay=False,credentials_excluded=True)
    finally:
        for query in cursors:
            try:query.close()
            except Exception:pass
        for handle in connections:
            try:handle.close()
            except Exception:pass
        proof['owned_servers_stopped']=bool(owned) and all(value['owned_server_stopped'] for value in owned)
        proof['owned_network_removed']=subprocess.run(['docker','network','rm',network],capture_output=True).returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(json.dumps({'complete':qualify(parser.parse_args().output)['complete']}))
