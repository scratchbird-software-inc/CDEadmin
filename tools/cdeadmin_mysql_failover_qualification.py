"""Native asynchronous candidate lifecycle, independent grants and DDN effects."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,application=False):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family import mysql_failover as module
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.providers.mysql_family.mysql_parser import library,native
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
    from pgadmin.cdeadmin.providers.mysql_server_application import apply_operation
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.security import SecretLease
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in
        ['mysql_failover.py','administration.py','provider.py','installed_catalog.py','mysql_server_catalog.py']]
    paths+=['web/pgadmin/cdeadmin/workspace/mysql_server_plan.py','web/pgadmin/cdeadmin/providers/mysql_server_application.py',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'disabled':[],'application':[],'native_denials':[],
        'full_product_inventory_complete':False,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=[]
    def oracle(cursor):
        result={}
        for key,table in [('failover_sources','replication_asynchronous_connection_failover'),('failover_managed','replication_asynchronous_connection_failover_managed')]:
            cursor.execute('SELECT * FROM performance_schema.'+table+' ORDER BY CHANNEL_NAME'+(',HOST,PORT,NETWORK_NAMESPACE,MANAGED_NAME' if key=='failover_sources' else ',MANAGED_NAME'))
            names=[row[0].lower() for row in cursor.description];rows=[dict(zip(names,row)) for row in cursor.fetchall()]
            assert len(names)==(6 if key=='failover_sources' else 4)
            result[key]=rows
        return result
    def document(handle):
        value=capture(handle)
        exported=build_export(value['resources'],endpoint_id='owned',target_id='server:'+value['server_uuid'],generation=value['generation'],engine='mysql')
        return read_catalog(json.dumps(exported['snapshot']),engine='mysql')
    try:
        with server(output/'fixture',restartable=True) as (route,container,fixture):
            owned.append(fixture);handle=_root_connection('mysql',route['port']);handle.autocommit=True;q=handle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute('SELECT @@server_uuid');instance=q.fetchone()[0]
                server_target={'resource_kind':'server','resource_id':'server:MySQL','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':instance}}
                name="failover 'quoted";channel={'resource_kind':'replication-channel','display_name':'Selected channel','native':{'channel_name':name,'server_uuid':instance}}
                q.execute("CHANGE REPLICATION SOURCE TO SOURCE_HOST='example.invalid',SOURCE_AUTO_POSITION=1 FOR CHANNEL %s",(name,))
                q.execute('SELECT asynchronous_connection_failover_add_source(%s,%s,3307,%s,50)',('native_probe','probe.example',''));q.fetchall()
                q.execute('SELECT asynchronous_connection_failover_reset()');q.fetchall()
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    selected={**route,'database':'sr_osc','use_pure':pure}
                    original=client.open_session({'route':selected});work=original.cursor();templates={};operations=[]
                    def review(op,draft):
                        target=server_target if op=='reset_failover_sources' else channel
                        return client.plan_admin_operation({'resource_kind':target['resource_kind'],'operation_id':op,
                            'draft':{'confirmation':target['display_name'],**draft},'target_resource':target,'_provider_route':selected})
                    def execute(op,draft):
                        request=review(op,draft)
                        try:result=MYSQL_ADMINISTRATION.apply(client,request)
                        except RelationalClientError as error:
                            proof['failure']={'operation':op,'type':type(error).__name__,'errno':getattr(error,'errno',None),'sqlstate':getattr(error,'sqlstate',None)}
                            raise
                        assert result['native_acknowledged'] and result['failover_observation']['source_selection_or_delivery_attested'] is False
                        operations.append(op);templates[op]=request['provider_payload']['compiled']['statements'][0]
                        return result
                    def metadata():
                        wanted=oracle(q);peer=client._connect({'route':selected})
                        try:
                            peer.autocommit=True;rows=_resources(peer,{'route':{'database':'sr_osc'}},MYSQL_PROFILE)
                            item=next(row['native'] for row in rows if row['resource_kind']=='replication-channel' and row['native']['channel_name']==name)
                            for key in wanted:assert item[key]==[row for row in wanted[key] if row['channel_name']==name]
                            model=document(peer)
                        finally:client._forget_and_close(peer)
                        item=next(row['native'] for row in model['rows'].values() if row['kind']=='replication-channel' and row['native']['catalog_row']['channel_name']==name)
                        for key in wanted:assert item[key]==[row for row in wanted[key] if row['channel_name']==name]
                        return model
                    try:
                        unsupported=deepcopy(channel);unsupported['native']['channel_name']='unicode 雪'
                        request=client.plan_admin_operation({'resource_kind':'replication-channel','operation_id':'add_failover_source',
                            'draft':{'host':'unicode.example','port':3307,'confirmation':unsupported['display_name']},'target_resource':unsupported,'_provider_route':selected})
                        try:MYSQL_ADMINISTRATION.apply(client,request)
                        except RelationalClientError as error:assert error.errno==3854 and error.sqlstate=='HY000' and not error.native_acknowledged
                        else:raise AssertionError('Native Latin1 conversion refusal was lost')
                        for port in (0,2**32-1):
                            execute('add_failover_source',{'host':'range.example','port':port,'weight':1})
                            q.execute('SELECT PORT FROM mysql.replication_asynchronous_connection_failover WHERE CHANNEL_NAME=%s AND HOST=%s',(name,'range.example'))
                            assert q.fetchone()==(port,)
                            execute('remove_failover_source',{'host':'range.example','port':port})
                        work.execute('SAVEPOINT failover_guard');work.execute('INSERT INTO pending VALUES(1)')
                        execute('add_failover_source',{'host':"host'bound",'port':3307,'weight':100});metadata()
                        try:MYSQL_ADMINISTRATION.apply(client,review('add_failover_source',{'host':"host'bound",'port':3307,'weight':100}))
                        except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and error.errno
                        else:raise AssertionError('Duplicate source did not produce native refusal')
                        stale=review('remove_failover_source',{'host':"host'bound",'port':3307})
                        q.execute('SELECT asynchronous_connection_failover_add_source(%s,%s,3308,%s,1)',(name,'external',''));q.fetchall()
                        try:MYSQL_ADMINISTRATION.apply(client,stale)
                        except RelationalClientError as error:assert not error.native_dispatched and not error.automatic_retry
                        else:raise AssertionError('Changed candidate list was admitted')
                        execute('remove_failover_source',{'host':'external','port':3308})
                        execute('remove_failover_source',{'host':"host'bound",'port':3307})
                        group=str(uuid4()).upper()
                        execute('add_managed_failover',{'managed_name':group,'host':'seed.example','port':3309,'primary_weight':100,'secondary_weight':1});metadata()
                        execute('remove_managed_failover',{'managed_name':group});metadata()
                        # Post-ACK observation failure must preserve the native mutation.
                        request=review('add_failover_source',{'host':'post-ack.example','port':3307})
                        observed=module.observe;calls=0
                        def lost(*args):
                            nonlocal calls
                            calls+=1
                            if calls==2:raise OSError('Owned observation loss')
                            return observed(*args)
                        with patch.object(module,'observe',lost):
                            try:MYSQL_ADMINISTRATION.apply(client,request)
                            except RelationalClientError as error:assert error.native_acknowledged and not error.automatic_retry
                            else:raise AssertionError('Post-ACK loss was hidden')
                        assert any(row['host']=='post-ack.example' for row in oracle(q)['failover_sources'])
                        execute('reset_failover_sources',{'all_channels':True});assert not any(oracle(q).values())
                        # DDN explicit intent reuses the same compiler and verifies native effects.
                        for action,draft in [('add_failover_source',{'host':'ddn.example','port':3310,'weight':17}),
                            ('remove_failover_source',{'host':'ddn.example','port':3310}),
                            ('add_managed_failover',{'managed_name':group,'host':'ddn.seed','port':3311,'primary_weight':99,'secondary_weight':2}),
                            ('remove_managed_failover',{'managed_name':group})]:
                            baseline=metadata();desired=deepcopy(baseline)
                            row=next(row for row in desired['rows'].values() if row['kind']=='replication-channel' and row['native']['catalog_row']['channel_name']==name)
                            row['native']['mysql_change']={'action':action,'draft':draft,'confirmation':row['name']}
                            preview=plan(baseline,desired,baseline);assert preview['ready_for_review'],preview
                            preview['endpoint_id']='owned'
                            record={'plan':preview,'baseline':baseline,'desired':desired}
                            outcome=apply_operation(original,record,preview['operations'][0])
                            # The source has a pending transaction: this must refuse ownership.
                            assert outcome['state']=='not_dispatched'
                            peer=client._connect({'route':selected})
                            try:
                                peer.autocommit=True;outcome=apply_operation(peer,record,preview['operations'][0])
                                assert outcome['state']=='acknowledged' and outcome['rediscovery_verified'],outcome
                            finally:client._forget_and_close(peer)
                        # All native operations and discovery leave the original transaction intact.
                        work.execute('SELECT ROW_COUNT()');assert work.fetchone()==(1,)
                        work.execute('ROLLBACK TO SAVEPOINT failover_guard');original.rollback()
                        work.execute("SELECT CAST('warning' AS UNSIGNED)");work.fetchall();work.execute('SHOW WARNINGS');warnings=work.fetchall();assert warnings
                        execute('add_failover_source',{'host':'warning.example','port':3307});execute('reset_failover_sources',{'all_channels':True})
                        work.execute('SHOW WARNINGS');assert work.fetchall()==warnings
                        samples=['SELECT asynchronous_connection_failover_add_source(\'ch\',\'host\',3306,\'\',50)',
                            "SELECT asynchronous_connection_failover_delete_source('ch','host',3306,'')",
                            "SELECT asynchronous_connection_failover_add_managed('ch','GroupReplication','01234567-89ab-cdef-0123-456789abcdef','host',3306,'',80,60)",
                            "SELECT asynchronous_connection_failover_delete_managed('ch','01234567-89ab-cdef-0123-456789abcdef')",
                            'SELECT asynchronous_connection_failover_reset()']
                        parser=native(library(client),[{'source':source,'sql_mode':''} for source in samples])
                        assert all(row['sql_syntax_valid'] for row in parser['statements'])
                        proof['parser']={key:parser[key] for key in ['library_sha256','worker_sha256','parser_version']}
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':type(original).__name__,
                            'operations':sorted(set(operations)),'templates':templates,'native_effects':True,'ddn_plan_apply_effects':True,
                            'stale_review_and_post_ack_loss':True,'warnings_and_savepoint_preserved':True,'native_latin1_conversion_3854_preserved':True,'native_unsigned32_port_storage_verified':True})
                    finally:work.close();client.close_session(original);client.close()
                # Source-only grants must be enough for unmanaged candidate changes.
                password=secrets.token_urlsafe(24);q.execute('CREATE USER failover_reader IDENTIFIED BY %s',(password,))
                q.execute('GRANT SELECT ON performance_schema.replication_asynchronous_connection_failover TO failover_reader')
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=lambda *_:SecretLease(password)),SimpleNamespace())
                    selected={**route,'user':'failover_reader','use_pure':pure,'credential_reference_id':'owned','principal_reference':'owner'}
                    request={'resource_kind':'replication-channel','operation_id':'add_failover_source','target_resource':channel,
                        'draft':{'confirmation':channel['display_name'],'host':'limited.example','port':3312},'_provider_route':selected}
                    try:
                        planned=client.plan_admin_operation(request)
                        try:MYSQL_ADMINISTRATION.apply(client,planned)
                        except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and error.errno
                        else:raise AssertionError('Native privilege denial was hidden')
                        q.execute('GRANT REPLICATION_SLAVE_ADMIN ON *.* TO failover_reader')
                        planned=client.plan_admin_operation(request);assert MYSQL_ADMINISTRATION.apply(client,planned)['native_acknowledged']
                        current=oracle(q);assert any(row['host']=='limited.example' for row in current['failover_sources'])
                        peer=client._connect({'route':selected})
                        try:
                            peer.autocommit=True;baseline=document(peer);desired=deepcopy(baseline)
                            row=next(row for row in desired['rows'].values() if row['kind']=='replication-channel' and row['native']['catalog_row']['channel_name']==name)
                            row['native']['mysql_change']={'action':'remove_failover_source','draft':{'host':'limited.example','port':3312},'confirmation':row['name']}
                            preview=plan(baseline,desired,baseline);assert preview['ready_for_review'],preview
                            preview['endpoint_id']='owned';outcome=apply_operation(peer,{'plan':preview,'baseline':baseline,'desired':desired},preview['operations'][0])
                            assert outcome['state']=='acknowledged' and outcome['rediscovery_verified'],outcome
                        finally:client._forget_and_close(peer)
                        q.execute('SELECT asynchronous_connection_failover_reset()');q.fetchall()
                        q.execute('REVOKE REPLICATION_SLAVE_ADMIN ON *.* FROM failover_reader')
                        proof['native_denials'].append({'use_pure':pure,'native_mutation_grant_enforced':True,'source_only_select_grant_sufficient':True,'source_only_ddn_plan_apply':True})
                    finally:client.close()
                q.execute('SELECT asynchronous_connection_failover_add_source(%s,%s,3316,%s,17)',(name,'persistent.example',''));q.fetchall()
                group=str(uuid4());q.execute('SELECT asynchronous_connection_failover_add_managed(%s,%s,%s,%s,3317,%s,98,3)',(name,'GroupReplication',group,'persistent.seed',''));q.fetchall()
                persisted=oracle(q);q.close();handle.close()
                subprocess.run(['docker','restart',container],check=True,capture_output=True)
                deadline=time.monotonic()+60
                while True:
                    try:handle=_root_connection('mysql',route['port']);break
                    except Exception:
                        if time.monotonic()>deadline:raise
                        time.sleep(.1)
                handle.autocommit=True;q=handle.cursor();assert oracle(q)==persisted
                q.execute('SELECT asynchronous_connection_failover_reset()');q.fetchall()
                proof['native_configuration_restart_durable']=True
                if application:
                    password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    from cdeadmin_mysql_online_ddl_qualification import registration
                    for pure in (True,False):
                        _sid,_target,post=registration(app,route,password,not pure)
                        api_group=str(uuid4())
                        for op,draft in [('add_failover_source',{'host':'api.example','port':3313}),('remove_failover_source',{'host':'api.example','port':3313}),
                            ('add_managed_failover',{'managed_name':api_group,'host':'api.seed','port':3314}),
                            ('remove_managed_failover',{'managed_name':api_group}),('reset_failover_sources',{'all_channels':True})]:
                            target=server_target if op=='reset_failover_sources' else channel
                            request={'resource_kind':target['resource_kind'],'operation_id':op,'target_resource':target,'draft':{'confirmation':target['display_name'],**draft}}
                            result=post('visual_admin_validate',request);assert result['valid'],result
                            reviewed=post('visual_admin_plan',request);assert reviewed['state']=='ready' and reviewed['execution_available'],reviewed
                            apply={key:reviewed[key] for key in ['plan_id','plan_digest']}|{'confirmed':True}
                            result=post('visual_admin_apply',apply);assert result['provider_result']['native_acknowledged']
                            replay=post.raw('visual_admin_apply',apply);assert replay.status_code!=200 or not replay.get_json().get('success')
                        proof['application'].append({'use_pure':pure,'authenticated_typed_plan_apply':True,'single_use_plans':True})
            finally:
                try:q.close()
                except Exception:pass
                handle.close()
        with server(output/'disabled',performance_schema=False) as (route,_name,fixture):
            owned.append(fixture);handle=_root_connection('mysql',route['port']);handle.autocommit=True;q=handle.cursor()
            try:
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    q.execute('SELECT @@server_uuid');instance=q.fetchone()[0]
                    target={'resource_kind':'replication-channel','display_name':'Unconfigured default','native':{'channel_name':'','server_uuid':instance}}
                    selected={**route,'use_pure':pure}
                    try:
                        for op in ['add_failover_source','remove_failover_source']:
                            request=client.plan_admin_operation({'resource_kind':'replication-channel','operation_id':op,'target_resource':target,
                                'draft':{'host':'disabled.example','port':3315,'confirmation':target['display_name']},'_provider_route':selected})
                            assert MYSQL_ADMINISTRATION.apply(client,request)['native_acknowledged']
                            oracle(q)
                        proof['disabled'].append({'use_pure':pure,'native_perpetual_catalog_and_mutation':True})
                    finally:client.close()
            finally:
                try:q.close()
                except Exception:pass
                handle.close()
        proof['complete']=True
    except Exception as error:
        proof.setdefault('failure',{'type':type(error).__name__,'errno':getattr(error,'errno',None),'sqlstate':getattr(error,'sqlstate',None)})
        raise
    finally:
        proof['owned_servers_stopped']=bool(owned) and all(value['owned_server_stopped'] for value in owned)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--application',action='store_true')
    args=parser.parse_args();print(json.dumps({'complete':qualify(args.output,args.application)['complete']}))
