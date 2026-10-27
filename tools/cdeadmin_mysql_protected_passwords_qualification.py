"""Native generated-password authentication and retained catalog diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import sys
import secrets
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client,MYSQL_PROFILE
    from pgadmin.cdeadmin.providers.mysql_family import mysql_accounts as accounts
    from pgadmin.cdeadmin.security import SecretLease,SecretReference
    from pgadmin.cdeadmin.sdk import RelationalClientError
    import mysql.connector
    class Receiver:
        def __init__(self):self.binding_id=str(uuid4());self.values={};self.leases=[];self.reserved=False
        def reserve(self,user,host,factors):self.reserved=True;return (user,host,factors)
        def publish(self,reservation,factor,lease):
            assert self.reserved and factor in reservation[2];self.leases.append(lease)
            ref=SecretReference(str(uuid4()),str(uuid4()),'legacy_native','password','memory','owned','private',frozenset({'authenticate'}))
            self.values[ref.reference_id]=lease.use(bytes)
            if getattr(self,'fail_publish',False):raise RuntimeError(self.values[ref.reference_id].decode())
            return ref
        def release(self,reservation):self.reserved=False
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in
        ('mysql_accounts.py','mysql_passwords.py','mysql_completion.py','provider.py','administration.py')]
    paths.append(str(Path(__file__).relative_to(ROOT)))
    proof={'complete':False,'interfaces':[],'owned_servers_stopped':False,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    owned=[]
    try:
        with server(output/'fixture') as (route,_name,fixture):
            owned.append(fixture);oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_protected');q.execute('CREATE TABLE sr_protected.pending(id INT PRIMARY KEY)')
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    receiver=Receiver();client.protected_password_receiver=receiver
                    def operation(mode):
                        draft={'authentication_mode':'RANDOM_PASSWORD'}
                        if mode=='create':draft.update(name='generated_owned',host='%')
                        target={'native':{'user':'generated_owned','host':'%'}}
                        compiled=accounts.compile_operation(mode,draft,target)
                        planned={'provider_payload':{'compiled':compiled,'route':{**route,'use_pure':pure}},'command_preview':{}}
                        accounts.bind_review(client,planned);result=accounts.apply(client,planned)
                        ref=result['protected_password_results'][0]['secret_reference_id'];secret=receiver.values[ref]
                        assert secret.decode() not in json.dumps(result)+json.dumps(planned['command_preview'])
                        assert all(lease.closed for lease in receiver.leases)
                        with SecretLease(secret) as lease:
                            authenticated=lease.use(lambda value:mysql.connector.connect(host='127.0.0.1',port=route['port'],
                                user='generated_owned',password=bytes(value).decode(),use_pure=pure))
                        try:
                            check=authenticated.cursor();check.execute('SELECT CURRENT_USER()');assert check.fetchone()==('generated_owned@%',);check.close()
                        finally:authenticated.close()
                        return result
                    try:
                        operation('create')
                        noop=accounts.compile_operation('create',{'name':'generated_owned','host':'%',
                            'authentication_mode':'RANDOM_PASSWORD','if_not_exists':True})
                        reviewed={'provider_payload':{'compiled':noop,'route':{**route,'use_pure':pure}},'command_preview':{}}
                        accounts.bind_review(client,reviewed);unchanged=accounts.apply(client,reviewed)
                        assert unchanged['protected_password_results']==[]
                        assert unchanged['account_observation']['before']==unchanged['account_observation']['after']
                        operation('alter')
                        receiver.fail_publish=True
                        failed=accounts.compile_operation('alter',{'authentication_mode':'RANDOM_PASSWORD'},{'native':{'user':'generated_owned','host':'%'}})
                        reviewed={'provider_payload':{'compiled':failed,'route':{**route,'use_pure':pure}},'command_preview':{}}
                        accounts.bind_review(client,reviewed)
                        try:accounts.apply(client,reviewed)
                        except RelationalClientError as error:
                            assert error.native_dispatched and error.native_acknowledged and not error.automatic_retry
                            assert all(value.decode() not in str(error) for value in receiver.values.values())
                            assert all(lease.closed for lease in receiver.leases)
                        else:raise AssertionError('Failed protected publication was reported as success')
                        receiver.fail_publish=False
                        client.protected_password_receiver=None
                        compiled=accounts.compile_operation('alter',{'authentication_mode':'RANDOM_PASSWORD'},{'native':{'user':'generated_owned','host':'%'}})
                        try:accounts.bind_review(client,{'provider_payload':{'compiled':compiled,'route':route}})
                        except RelationalClientError:pass
                        else:raise AssertionError('Unprotected generation was admitted')
                        original=client.open_session({'route':{**route,'database':'sr_protected','use_pure':pure,'autocommit':False}})
                        work=original.cursor()
                        try:
                            work.execute('SAVEPOINT owned_catalog_guard');work.execute('INSERT INTO pending VALUES(1)')
                            rows=client.list_resources({'route':{'database':'sr_protected'},'_provider_session_handle':original})
                            assert any(row['resource_kind']=='table' and row['display_name']=='pending' for row in rows)
                            work.execute('SELECT ROW_COUNT()');assert work.fetchone()==(1,)
                            work.execute('ROLLBACK TO SAVEPOINT owned_catalog_guard');original.rollback()
                            work.execute("SELECT CAST('owned-warning' AS UNSIGNED)");work.fetchall();work.execute('SHOW WARNINGS');warnings=work.fetchall();assert warnings
                            rows=client.list_resources({'route':{'database':'sr_protected'},'_provider_session_handle':original})
                            work.execute('SHOW WARNINGS');assert work.fetchall()==warnings
                            native=next(row for row in rows if row['resource_kind']=='server')['native']
                            assert native['metadata_observation']['original_session_commands_sent']==0
                        finally:work.close();client.close_session(original)
                        proof['interfaces'].append({'use_pure':pure,'native_create_and_rotate_authentication':True,'native_existing_account_noop_has_no_password_result':True,
                            'missing_delivery_refused_before_dcl':True,'only_secret_references_returned':True,'leases_closed':True,
                            'post_ack_delivery_failure_sanitized_and_not_replayed':True,
                            'retained_catalog_warnings_row_count_and_savepoint_preserved':True,'shared_delivery_and_ui_qualified':False})
                    finally:
                        client.close();q.execute('DROP USER IF EXISTS %s@%s',('generated_owned','%'))
                # A normal authenticated application has no receiver until the front-end
                # stream wires the protected result service. It must refuse before DCL.
                q.execute('CREATE DATABASE sr_osc');password=secrets.token_urlsafe(24)
                q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                from cdeadmin_mysql_online_ddl_qualification import registration
                for pure in (True,False):
                    _sid,_target,post=registration(app,route,password,not pure)
                    request={'resource_kind':'user','operation_id':'create',
                        'draft':{'name':'api_unprotected','host':'%','authentication_mode':'RANDOM_PASSWORD'}}
                    reply=post.raw('visual_admin_validate',request);result=reply.get_json()
                    assert reply.status_code==200 and result['success'] and not result['data']['valid']
                    assert result['data']['errors'][0]['code']=='protected_password_delivery_unavailable'
                    assert reply.headers['Cache-Control']=='no-store'
                    reply=post.raw('visual_admin_plan',request);result=reply.get_json()
                    assert reply.status_code!=200 or not result.get('success') or not result.get('data',{}).get('execution_available')
                    # The shared route currently maps VisualAdminValidationError to
                    # its generic failure envelope. Do not claim that UI/error bridge.
                    q.execute('SELECT COUNT(*) FROM mysql.user WHERE User=%s',('api_unprotected',));assert q.fetchone()==(0,)
                proof['authenticated_missing_bridge_refused_before_dcl']=True
                proof['authenticated_structured_validation_no_store']=True
                proof['shared_invalid_plan_error_envelope_qualified']=False
            finally:q.close();oracle.close()
        proof['complete']=True
    finally:
        proof['owned_servers_stopped']=bool(owned) and all(value['owned_server_stopped'] for value in owned)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(json.dumps({'complete':qualify(parser.parse_args().output)['complete']}))
