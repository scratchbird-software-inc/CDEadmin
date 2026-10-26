"""Owned MySQL database descriptor create/prefill/alter/native/API round trip."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_indexes import identifier
    from ui_descriptor_roundtrip import resolved_form,record_from_resource,record_draft,backend_draft
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/provider.py','web/pgadmin/cdeadmin/providers/mysql_descriptor_contract.py',
        'web/pgadmin/cdeadmin/providers/form_contracts.py','web/pgadmin/cdeadmin/ui_descriptors/mysql/forms/database.form.json',
        str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'history_testing':'ScratchBird history not run',
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    owned=None
    try:
        with server(output/'fixture',keyring=True) as (route,_container,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                form=resolved_form('mysql','database')
                for pure in (True,False):
                    selected={**route,'database':'sr_osc','use_pure':pure}
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    classes=[];connect=client._connect
                    def tracked(request):
                        handle=connect(request);classes.append(type(handle).__name__);return handle
                    client._connect=tracked;name="db`'雪"+str(int(pure))
                    def run(operation,draft,target=None):
                        request={'resource_kind':'database','operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':selected}
                        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
                        return MYSQL_ADMINISTRATION.apply(client,client.plan_admin_operation(request))
                    def inspect():
                        handle=client._connect({'route':selected})
                        try:
                            rows=_resources(handle,{'route':{**selected,'database':name}},MYSQL_PROFILE)
                            row=next(row for row in rows if row['resource_kind']=='database' and row['display_name']==name)
                            return row,record_draft(form,record_from_resource(form,row,rows))
                        finally:client._forget_and_close(handle)
                    try:
                        create=backend_draft(form,{'name':name,'if_not_exists':True,'character_set':'utf8mb4','collation':'utf8mb4_bin','encryption':'N'})
                        oracle.autocommit=False;q.execute('SAVEPOINT descriptor_guard');q.execute('INSERT INTO sr_osc.pending VALUES(%s)',(int(pure)+1,))
                        assert run('create',create)['accepted'];q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        q.execute('ROLLBACK TO SAVEPOINT descriptor_guard');oracle.rollback();oracle.autocommit=True
                        target,baseline=inspect();assert baseline=={'character_set':'utf8mb4','collation':'utf8mb4_bin','encryption':'N','read_only':'OFF'}
                        q.execute('CREATE TABLE '+identifier(name)+'.preserved(value VARCHAR(30))');q.execute('INSERT INTO '+identifier(name)+'.preserved VALUES(%s)',('Unicode 雪',))
                        edited={**baseline,'character_set':'latin1','collation':'latin1_bin','encryption':'Y','read_only':'ON'}
                        assert run('alter',backend_draft(form,edited,mode='alter',baseline=baseline),target)['accepted']
                        target,observed=inspect();assert observed==edited
                        q.execute('SELECT value FROM '+identifier(name)+'.preserved');assert q.fetchall()==[('Unicode 雪',)]
                        # Native read-only enforcement needs an account without
                        # CONNECTION_ADMIN; root may bypass it.
                        user='db_writer_'+str(int(pure));password=secrets.token_urlsafe(20)
                        q.execute('CREATE USER `'+user+'`@`%` IDENTIFIED BY %s',(password,));q.execute('GRANT INSERT ON '+identifier(name)+'.* TO `'+user+'`@`%`')
                        import mysql.connector
                        writer=mysql.connector.connect(host=route['host'],port=route['port'],user=user,password=password,use_pure=pure,autocommit=True)
                        try:
                            cursor=writer.cursor()
                            try:cursor.execute('INSERT INTO '+identifier(name)+'.preserved VALUES(%s)',('refused',))
                            except mysql.connector.Error as error:assert error.errno==mysql.connector.errorcode.ER_SCHEMA_READ_ONLY
                            else:raise AssertionError('Native database read-only protection did not refuse the write')
                            finally:cursor.close()
                        finally:writer.close()
                        assert run('alter',backend_draft(form,{'read_only':'OFF'},mode='alter'),target)['accepted']
                        target,observed=inspect();assert observed['read_only']=='OFF'
                        q.execute('INSERT INTO '+identifier(name)+'.preserved VALUES(%s)',('later write',))
                        assert run('drop',{'confirmation':name},target)['accepted']
                        q.execute('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',(name,));assert q.fetchone()==(0,)
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'native_connection_class':expected,'complete':True,'descriptor_create_prefill_alter_and_drop':True,
                            'read_only_native_enforcement':True,'existing_unicode_data_preserved':True,'source_diagnostics_and_savepoint_preserved':True})
                    finally:client.close()
                password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                proof['application']=workspace(app,route,password,q,form);proof['complete']=True
            finally:q.close();oracle.close()
    finally:
        proof['owned_server_stopped']=bool(owned and owned['owned_server_stopped'])
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(app,route,password,q,form):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from ui_descriptor_roundtrip import backend_draft
    results=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure);name='api_db_descriptor_'+str(int(pure))
        target={'resource_kind':'database','resource_id':'database:'+name,'display_name':name,'display_path':[name]}
        for operation,values in [('create',{'name':name,'character_set':'utf8mb4','collation':'utf8mb4_bin','encryption':'N'}),
                                 ('alter',{'read_only':'ON'}),('alter',{'read_only':'OFF'}),('drop',{'confirmation':name})]:
            draft=values if operation=='drop' else backend_draft(form,values,mode=operation)
            payload={'resource_kind':'database','operation_id':operation,'draft':draft,'target_resource':None if operation=='create' else target}
            validated=post('visual_admin_validate',payload);assert validated['valid'],validated['errors']
            planned=post('visual_admin_plan',payload)
            assert planned['state']=='ready' and planned['execution_available'],planned
            request={key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            result=post('visual_admin_apply',request);assert result['provider_result']['accepted']
            replay=post.raw('visual_admin_apply',request);assert replay.status_code!=200 or not replay.get_json().get('success')
        q.execute('SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',(name,));assert q.fetchone()==(0,)
        results.append({'use_pure':pure,'authenticated_descriptor_inputs_and_native_effect':True,'consumed_plan_refused':True})
    return {'complete':True,'interfaces':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    result=qualify(parser.parse_args().output);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))
