"""Native Community SDI import, actual table files and both connector paths."""
import argparse
import hashlib
import json
import secrets
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def stage(cursor,container,name,saved):
    """Export a MyISAM table's SDI and data files, drop it, and restore only the data files."""
    qualified='sr_sdi.'+name;pattern=saved+"/quoted ' 雪.sdi"
    cursor.execute('CREATE TABLE '+qualified+'(id BIGINT UNSIGNED PRIMARY KEY,note TEXT,payload LONGBLOB) ENGINE=MyISAM')
    cursor.execute('INSERT INTO '+qualified+' VALUES(%s,%s,%s)',(18446744073709551615,'native SDI 雪',b'\x00\xff'))
    cursor.execute('FLUSH TABLES '+qualified+' WITH READ LOCK')
    def host(source):return subprocess.check_output(['docker','exec','--user=mysql',container,'/bin/sh','-c',source],text=True).strip()
    try:
        host('mkdir -p '+shlex.quote(saved)+'\ncp /var/lib/mysql/sr_sdi/'+name+'*.sdi '+shlex.quote(pattern)+'\ncp /var/lib/mysql/sr_sdi/'+name+'.MYD /var/lib/mysql/sr_sdi/'+name+'.MYI '+shlex.quote(saved)+'/')
    finally:cursor.execute('UNLOCK TABLES')
    cursor.execute('DROP TABLE '+qualified)
    host('cp '+shlex.quote(saved)+'/'+name+'.MYD '+shlex.quote(saved)+'/'+name+'.MYI /var/lib/mysql/sr_sdi/')
    return qualified,pattern


def workspace(app,route,password,target,cursor,container):
    """Import staged SDI files through the authenticated API on both interfaces."""
    from cdeadmin_mysql_online_ddl_qualification import registration
    operations=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure)
        qualified,pattern=stage(cursor,container,'api_table_'+str(int(pure)),'/var/lib/mysql-files/sr-api-sdi-'+str(int(pure)))
        request={'resource_kind':'server','operation_id':'import_table_sdi','target_resource':target,
                 'draft':{'confirmation':'MySQL','files':[pattern],'trusted_host_files':True,'database':'sr_sdi'}}
        checked=post('visual_admin_validate',request);assert checked['valid'],checked['errors']
        plan=post('visual_admin_plan',request);assert plan['state']=='ready' and plan['execution_available'],plan
        body={key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
        post('visual_admin_apply',body)
        replay=post.raw('visual_admin_apply',body);assert replay.status_code!=200 or not replay.get_json().get('success')
        # The receipt is written only after the imported rows read back.
        cursor.execute('SELECT CAST(id AS CHAR),note,HEX(payload) FROM '+qualified)
        assert cursor.fetchall()==[('18446744073709551615','native SDI 雪','00FF')]
        cursor.execute('DROP TABLE '+qualified)
        operations.append({'use_pure':pure,'resource_kind':'server','operation':'import_table_sdi','native_acknowledged':True,'replay_refused':True})
    return {'complete':True,'operations':operations}


def qualify(output,application=False):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    if application:
        from cdeadmin_mysql_dump_verification_qualification import setup_application
        app=setup_application(output)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_instance.py','administration.py','provider.py')]
    proof={'complete':False,'interfaces':[],'history_testing':'ScratchBird history not run',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'fixture') as (route,container,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;cursor=oracle.cursor()
            try:
                cursor.execute('CREATE DATABASE sr_sdi CHARACTER SET utf8mb4');cursor.execute('SELECT @@server_uuid');uuid=cursor.fetchone()[0]
                target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
                for pure in (True,False):
                    name='table_'+str(int(pure));qualified='sr_sdi.'+name
                    cursor.execute('CREATE TABLE '+qualified+'(id BIGINT UNSIGNED PRIMARY KEY,note TEXT,payload LONGBLOB) ENGINE=MyISAM')
                    cursor.execute('INSERT INTO '+qualified+' VALUES(%s,%s,%s)',(18446744073709551615,'native SDI 雪',b'\x00\xff'))
                    cursor.execute('FLUSH TABLES '+qualified+' WITH READ LOCK')
                    saved='/var/lib/mysql-files/sr-sdi-'+str(int(pure));pattern=saved+"/quoted ' 雪.sdi"
                    def host(source):return subprocess.check_output(['docker','exec','--user=mysql',container,'/bin/sh','-c',source],text=True).strip()
                    try:
                        host('mkdir -p '+shlex.quote(saved)+'\ncp /var/lib/mysql/sr_sdi/'+name+'*.sdi '+shlex.quote(pattern)+'\ncp /var/lib/mysql/sr_sdi/'+name+'.MYD /var/lib/mysql/sr_sdi/'+name+'.MYI '+shlex.quote(saved)+'/')
                    finally:cursor.execute('UNLOCK TABLES')
                    cursor.execute('DROP TABLE '+qualified)
                    host('cp '+shlex.quote(saved)+'/'+name+'.MYD '+shlex.quote(saved)+'/'+name+'.MYI /var/lib/mysql/sr_sdi/')
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    try:
                        selected={**route,'database':'sr_sdi','use_pure':pure}
                        original=client._connect;classes=[]
                        def tracked(request):
                            connection=original(request);classes.append(type(connection).__name__);return connection
                        client._connect=tracked
                        def plan(files):return client.plan_admin_operation({'resource_kind':'server',
                            'operation_id':'import_table_sdi','draft':{'confirmation':'MySQL','files':files,'trusted_host_files':True,'database':'sr_sdi'},
                            'target_resource':target,'_provider_route':selected})
                        reviewed=plan([pattern])
                        assert reviewed['provider_payload']['compiled']['statements']==[{'source':'IMPORT TABLE FROM %s','parameters':(pattern,)}]
                        cursor.execute('CREATE TABLE sr_sdi.stale_guard(id INT)')
                        try:MYSQL_ADMINISTRATION.apply(client,reviewed)
                        except RelationalClientError as error:assert error.native_dispatched is False
                        else:raise AssertionError('Changed native table inventory did not invalidate SDI review')
                        cursor.execute('DROP TABLE sr_sdi.stale_guard')
                        value=MYSQL_ADMINISTRATION.apply(client,plan([pattern]))
                        assert value['accepted'] and value['instance_observation']['native_acknowledged'] and value['automatic_retry'] is False
                        cursor.execute('SELECT CAST(id AS CHAR),note,HEX(payload) FROM '+qualified)
                        assert cursor.fetchall()==[('18446744073709551615','native SDI 雪','00FF')]
                        cursor.execute('SHOW CREATE TABLE '+qualified);definition=cursor.fetchone()[1]
                        assert 'ENGINE=MyISAM' in definition and 'bigint unsigned' in definition.lower()
                        cursor.execute('INSERT INTO '+qualified+" VALUES(2,'after native import',X'0100')")
                        missing=plan([saved+'/missing.sdi'])
                        try:MYSQL_ADMINISTRATION.apply(client,missing)
                        except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged is False and error.errno is not None
                        else:raise AssertionError('A missing native SDI file was treated as imported')
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'
                        assert classes and set(classes)=={expected},classes
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'native_import_returned':True,
                            'full_native_rows_and_definition_verified':True,'changed_review_refused':True,
                            'missing_file_native_error_preserved':True,'server_host_filename_unicode_and_apostrophe_preserved':True})
                    finally:client.close()
                    cursor.execute('DROP TABLE '+qualified)
                if application:
                    cursor.execute('CREATE DATABASE sr_osc')
                    password=secrets.token_urlsafe(24);cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(app,route,password,target,cursor,container)
                cursor.execute('DROP DATABASE sr_sdi');proof['complete']=True
            finally:cursor.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--application',action='store_true')
    args=parser.parse_args();result=qualify(args.output,args.application);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))
