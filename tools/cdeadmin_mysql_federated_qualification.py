"""Actual FEDERATED table creation, catalog exchange and private recovery."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def seed(oracle,port,use_c):
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    suffix=str(int(use_c));name='federated_'+suffix;remote='remote_'+suffix;link='sr_federated_'+suffix
    password=secrets.token_urlsafe(24)
    cursor=oracle.cursor()
    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
    route={'host':'127.0.0.1','port':port,'user':'root','database':'sr_osc','use_pure':not use_c}
    try:
        cursor.execute('CREATE TABLE sr_osc.'+remote+'(id BIGINT UNSIGNED PRIMARY KEY,note VARCHAR(80),payload LONGBLOB) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4')
        cursor.execute('INSERT INTO sr_osc.'+remote+' VALUES(%s,%s,%s)',(18446744073709551615,'FEDERATED 雪',b'\0\xff'))
        cursor.execute('CREATE USER '+link+"@'127.0.0.1' IDENTIFIED BY %s",(password,))
        cursor.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON sr_osc.'+remote+' TO '+link+"@'127.0.0.1'")
        def apply(kind,draft):
            reviewed=client.plan_admin_operation({'resource_kind':kind,'operation_id':'create','draft':draft,'_provider_route':route})
            assert password not in json.dumps(reviewed['command_preview'])
            value=MYSQL_ADMINISTRATION.apply(client,reviewed);assert value['accepted'],value
        apply('server-link',{'name':link,'wrapper':'mysql','include_host':True,'host':'127.0.0.1',
            'include_port':True,'port':'3306','include_database':True,'database':'sr_osc',
            'include_username':True,'username':link,'include_password':True,'password':password})
        apply('table',{'name':name,'schema':'sr_osc','columns':[{'name':'id','type':'BIGINT UNSIGNED','primary_key':True},
            {'name':'note','type':'VARCHAR(80)'},{'name':'payload','type':'LONGBLOB'}],
            'mysql_table_options':{'engine':'FEDERATED','character_set':'utf8mb4'},'mysql_connection':link+'/'+remote})
        cursor.execute('SELECT CAST(id AS CHAR),note,HEX(payload) FROM sr_osc.'+name)
        assert cursor.fetchall()==[('18446744073709551615','FEDERATED 雪','00FF')]
        cursor.execute('INSERT INTO sr_osc.'+name+" VALUES(2,'native remote write',X'0100')")
        cursor.execute('SELECT note,HEX(payload) FROM sr_osc.'+remote+' WHERE id=2')
        assert cursor.fetchone()==('native remote write','0100')
        captured=capture(oracle,'sr_osc')
        exported=build_export(captured['resources'],engine='mysql',endpoint_id='owned',target_id='owned',generation=captured['generation'])
        model=read_catalog(json.dumps(exported['snapshot']),engine='mysql')
        row=next(row for row in model['rows'].values() if row['kind']=='table' and row['name']==name)
        assert 'ENGINE=FEDERATED' in row['native']['definition'] and link+'/'+remote in row['native']['definition']
        assert password not in json.dumps(exported['snapshot'])
        options_name='native_options_'+suffix
        apply('table',{'name':options_name,'schema':'sr_osc','columns':[{'name':'id','type':'BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY'}],
            'mysql_table_options':{'engine':'InnoDB','auto_increment':'9007199254740993','row_format':'DYNAMIC',
                'comment':"native quote' 雪",'character_set':'utf8mb4','collation':'utf8mb4_bin','stats_persistent':'1','stats_sample_pages':'32'}})
        cursor.execute('INSERT INTO sr_osc.'+options_name+' VALUES(NULL)')
        cursor.execute('SELECT CAST(id AS CHAR) FROM sr_osc.'+options_name)
        assert cursor.fetchall()==[('9007199254740993',)]
        cursor.execute('SHOW CREATE TABLE sr_osc.'+options_name);definition=cursor.fetchone()[1]
        assert 'ROW_FORMAT=DYNAMIC' in definition and 'utf8mb4_bin' in definition and 'STATS_SAMPLE_PAGES=32' in definition
        return ['typed-native-FEDERATED-table-and-server-reference-create','native-remote-read-write-exact-u64-Unicode-binary',
            'catalog-DDN-retains-native-engine-and-named-reference-without-password','typed-InnoDB-options-and-exact-beyond-JavaScript-integer-auto-increment']
    finally:client.close();cursor.close()


def recover_remote(oracle,container,post,credentials,review,start,copied,use_c,output):
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    suffix=str(int(use_c));name='sr_osc.federated_'+suffix;remote='sr_osc.remote_'+suffix
    checks=[]
    for mode in ('read_only','replay'):
        ticket=review('recover',copied['job_id'],lifetime=180,startup=mode,remote_access=True)
        runtime=start(ticket)
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                runtime=post('reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
                if runtime['recovery_running']:break
                if runtime.get('remote_observation',{}).get('supervisor_finished'):
                    (output/'federated-native-failure.json').write_text(json.dumps(runtime,indent=2))
                    raise RuntimeError('Native FEDERATED recovery failed')
                time.sleep(.2)
            else:raise TimeoutError('Native FEDERATED recovery startup timed out')
            assert runtime['remote_observation']['sql_identity']['federated_support']=='YES'
            socket=runtime['remote_observation']['socket']
            def sql(query,check=True):return _run(['docker','exec',container,'mysql','--no-defaults','--protocol=socket',
                '--socket='+socket,'--user=root','--batch','--raw','--skip-column-names','--default-character-set=utf8mb4','--execute='+query],check=check)
            with oracle.cursor() as cursor:
                cursor.execute('UPDATE '+remote+' SET note=%s WHERE id=2',('live after backup '+mode,))
            assert sql('SELECT note FROM '+name+' WHERE id=2').stdout.strip()=='live after backup '+mode
            mutation=sql('UPDATE '+name+" SET note='recovered remote write' WHERE id=2",False)
            assert (mutation.returncode==0)==(mode=='replay')
            with oracle.cursor() as cursor:
                cursor.execute('SELECT note FROM '+remote+' WHERE id=2')
                assert cursor.fetchone()[0]==('recovered remote write' if mode=='replay' else 'live after backup '+mode)
                cursor.execute('RENAME TABLE '+remote+' TO '+remote+'_unavailable')
                try:assert sql('SELECT * FROM '+name,False).returncode!=0
                finally:cursor.execute('RENAME TABLE '+remote+'_unavailable TO '+remote)
            checks.append('explicit-FEDERATED-'+mode+'-live-remote-rows-native-write-policy-and-unavailable-reference-error')
        finally:
            post('cancel',{'job_id':ticket['job_id'],'credentials':credentials})
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                stopped=post('reconcile',{'job_id':ticket['job_id'],'credentials':credentials})
                if stopped.get('remote_observation',{}).get('process_termination_confirmed'):break
                time.sleep(.2)
            else:raise TimeoutError('Native FEDERATED recovery did not stop')
    return checks


if __name__=='__main__':
    from cdeadmin_mysql_physical_qualification import qualify
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--fixture-image',required=True);parser.add_argument('--private-key')
    parser.add_argument('--prepare-fixture',action='store_true')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args()
    value=qualify(args.output,args.fixture_image,key=args.private_key,prepare=args.prepare_fixture,federated=True,
        browser_binary=args.browser_binary,driver_binary=args.driver_binary)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))
