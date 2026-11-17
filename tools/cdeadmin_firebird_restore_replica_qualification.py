"""Owned encrypted-network qualification of native one-byte restore replica modes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(runtime, evidence):
    from tools.cdeadmin_firebird_local_fixture import run_local
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.firebird.provider import _create_client
    from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration,VisualAdminAccessError
    result={'complete':False,'cases':[],'history_tests':'not run'}
    files=['web/pgadmin/cdeadmin/providers/firebird/'+name for name in ('provider.py','query_client.py','restore_files.py')]
    files.append('tools/cdeadmin_firebird_restore_replica_qualification.py')
    result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in files}
    def check(native, admin, route, accounts, output, root):
        result['driver_core_sha256']=hashlib.sha256(Path(native.core.__file__).read_bytes()).hexdigest()
        from tools.cdeadmin_firebird_password_gate import _route_arguments
        username,credential=accounts['Srp'][0]
        owned={**route,'user':username,'database':str(root/'replica-source.fdb'),'wire_crypt':'Required'}
        with native.create_database(password=credential,**_route_arguments(owned,native)) as setup:
            setup.execute_immediate('CREATE TABLE REPLICA_RESTORE_KEEP(ID INTEGER)')
            setup.commit()
            setup.execute_immediate('INSERT INTO REPLICA_RESTORE_KEEP VALUES(17)');setup.commit()
        selected,permissions=provider_access(owned,credential)
        permissions.require=lambda *_:None;permissions.allows=lambda *_:True
        client=_create_client(permissions,attachment_mode='network')
        visual=ProviderVisualAdministration(SimpleNamespace(endpoint_id='owned-network-replica-restore',mode='provider_native',
            runtime_verification_state='verified',declared_runtime_family='firebird',verified_runtime_family='firebird'),
            permissions,'firebird','5.0.4',client)
        def apply(operation,draft):
            request={'resource_kind':'database','operation_id':operation,'_provider_route':selected,'draft':draft}
            if operation=='backup_logical':request['target_resource']={'resource_kind':'database','display_name':'Owned source'}
            assert visual.validate(request)['valid']
            plan=visual.plan(request);review={'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'confirmed':True}
            value=visual.apply(review)['provider_result']['driver_observation'];assert value['server_completed']
            assert value['service_release']['connection_released']
            try:visual.apply(review)
            except VisualAdminAccessError:pass
            else:raise AssertionError('Native restore review replayed')
        try:
            backup=root/'replica modes.fbk';apply('backup_logical',{'backup_file':str(backup)})
            for mode,expected in (('NONE',0),('READ_ONLY',1),('READ_WRITE',2)):
                target=root/(mode+' restored.fdb')
                apply('restore_logical',{'backup_file':str(backup),'restore_database':str(target),'replica_mode':mode,'access_mode':'READ_ONLY'})
                handle=client._connect({'route':{**selected,'database':str(target)}})
                try:
                    q=handle.cursor();q.execute('SELECT ID FROM REPLICA_RESTORE_KEEP');assert q.fetchall()==[(17,)];q.close();handle.rollback()
                    q=handle.cursor();q.execute('SELECT MON$READ_ONLY,MON$REPLICA_MODE FROM MON$DATABASE');assert q.fetchone()==(1,expected);q.close();handle.rollback()
                    q=handle.cursor();q.execute('SELECT MON$REMOTE_PROTOCOL,MON$WIRE_ENCRYPTED FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                    protocol,encrypted=q.fetchone();q.close();handle.rollback();assert protocol=='TCPv4' and encrypted
                finally:client._forget_and_close(handle)
                result['cases'].append({'replica_mode':mode,'native_mode_observed':expected,'read_only_observed':True,'row17_preserved':True,'wire_encrypted':True})
        finally:client.close()
    try:
        fixture=run_local(runtime,evidence,check)
        result['fixture']=fixture
        result['complete']=fixture['complete'] and len(result['cases'])==3
    finally:
        evidence.mkdir(parents=True,exist_ok=True)
        (evidence/'replica-restore.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args();value=qualify(args.runtime,args.evidence)
    print(json.dumps({'complete':value['complete']}));raise SystemExit(0 if value['complete'] else 1)
