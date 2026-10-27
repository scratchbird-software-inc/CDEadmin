"""Owned wide replication integers, reviewed dispatch and API qualification."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep qualification evidence outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from cdeadmin_mysql_replication_qualification import qualify as replication
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import relay_positions as relay
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.security import SecretLease
    from ui_descriptor_roundtrip import backend_draft,engine_operations,operation_draft
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ['relay_positions.py','provider.py','administration.py']]
    paths+=['web/pgadmin/cdeadmin/providers/mysql_replication.py','web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'application':[],'history_testing':'ScratchBird history not run',
           'actual_operation_dialog_qualified':False,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    owned=[];network='sr-relay-'+secrets.token_hex(8);network_created=False
    try:
        _run(['docker','network','create',network]);network_created=True
        with ExitStack() as stack:
            origin,origin_name,source_proof=stack.enter_context(server(output/'source',network=network,server_id=601));owned.append(source_proof)
            route,replica_name,replica_proof=stack.enter_context(server(output/'replica',network=network,server_id=602,restartable=True));owned.append(replica_proof)
            for pure in (True,False):
                options=lambda selected:{**selected,'use_pure':pure}
                replication(options(origin),options(route),origin_name,output/('replication-'+str(pure)),descriptor_inputs=True)
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute(relay.QUERY);server_uuid,maximum,native_version=q.fetchone();assert native_version=='9.7.0' and maximum==str(2**64-1)
                def status(channel):
                    q.execute('SHOW REPLICA STATUS FOR CHANNEL %s',(channel,));names=[row[0] for row in q.description]
                    return dict(zip(names,q.fetchone()))
                def configure(channel):
                    q.execute("CHANGE REPLICATION SOURCE TO SOURCE_HOST='127.0.0.1',SOURCE_AUTO_POSITION=0,SOURCE_LOG_FILE='sr-owned.000001',SOURCE_LOG_POS=4 FOR CHANNEL %s",(channel,))
                    return status(channel)['Relay_Log_File']
                def clear(channel):
                    q.execute('STOP REPLICA FOR CHANNEL %s',(channel,));q.execute('RESET REPLICA ALL FOR CHANNEL %s',(channel,))
                def selected(channel,operation,draft):
                    return {'resource_kind':'replication-channel','operation_id':operation,'target_resource':{
                        'resource_kind':'replication-channel','display_name':'Channel '+channel,'native':{'channel_name':channel}},
                        'draft':draft,'_provider_route':route}
                def retry_state(channel,value):
                    assert str(status(channel)['Source_Retry_Count'])==value
                    q.execute('SELECT CONNECTION_RETRY_COUNT FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,))
                    assert tuple(map(str,q.fetchone()))==(value,)
                    q.execute('SELECT Retry_count FROM mysql.slave_master_info WHERE Channel_name=%s',(channel,))
                    assert tuple(map(str,q.fetchone()))==(value,)
                for pure in (True,False):
                    channel='wide_'+str(pure)+'_雪';file=configure(channel)
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    connect=client._connect;classes=[]
                    def tracked(request):
                        handle=connect({**request,'route':{**request['route'],'use_pure':pure}});classes.append(type(handle).__name__);return handle
                    client._connect=tracked
                    try:
                        for value in (2**32,2**53+1,2**63-1,2**64-1):
                            request=selected(channel,'alter',{'source_options':{'RELAY_LOG_FILE':file,'RELAY_LOG_POS':str(value)}})
                            oracle.autocommit=False;q.execute('SAVEPOINT relay_guard');q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                            planned=client.plan_admin_operation(request)
                            assert planned['command_preview']['native_relay_position']=={'server_uuid':server_uuid,'maximum':maximum,'requested':str(value)}
                            assert client.apply_admin_operation(planned)['native_acknowledged']
                            q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                            q.execute('ROLLBACK TO SAVEPOINT relay_guard');oracle.rollback();oracle.autocommit=True
                            assert str(status(channel)['Relay_Log_Pos'])==str(value)
                        # UNTIL is configured independently of the current relay
                        # read position; START acknowledgement is not delivery.
                        q.execute('CHANGE REPLICATION SOURCE TO RELAY_LOG_FILE=%s,RELAY_LOG_POS=4 FOR CHANNEL %s',(file,channel))
                        planned=client.plan_admin_operation(selected(channel,'start',{'thread':'SQL_THREAD','until':{'RELAY_LOG_FILE':file,'RELAY_LOG_POS':str(2**53+1)}}))
                        assert client.apply_admin_operation(planned)['native_acknowledged']
                        observed=status(channel);assert observed['Until_Condition']=='Relay' and str(observed['Until_Log_Pos'])==str(2**53+1)
                        q.execute('STOP REPLICA FOR CHANNEL %s',(channel,))
                        # A different real native instance at apply cannot reuse
                        # this review, even though both targets have 64-bit ULONG.
                        planned=client.plan_admin_operation(selected(channel,'alter',{'source_options':{'RELAY_LOG_POS':str(2**53+2)}}))
                        with patch.object(client,'_connect',lambda request:tracked({**request,'route':{**origin,'use_pure':pure}})):
                            try:client.apply_admin_operation(planned)
                            except RelationalClientError as error:assert not error.native_dispatched
                            else:raise AssertionError('Replacement native instance was not refused')
                        assert status(channel)['Relay_Log_Pos']==4
                        # Native option conflicts remain native errors; no
                        # retry or position/coercion fallback is permitted.
                        planned=client.plan_admin_operation(selected(channel,'alter',{'source_options':{'SOURCE_AUTO_POSITION':True,'RELAY_LOG_POS':str(2**53+3)}}))
                        try:client.apply_admin_operation(planned)
                        except RelationalClientError as error:
                            assert error.native_dispatched and not error.native_acknowledged and error.errno and not error.automatic_retry
                            native_error=error.errno
                        else:raise AssertionError('Native coordinate/GTID conflict was accepted')
                        assert status(channel)['Relay_Log_Pos']==4
                        # Losing cleanup after the native reply retains ACK.
                        planned=client.plan_admin_operation(selected(channel,'alter',{'source_options':{'RELAY_LOG_POS':str(2**53+4)}}))
                        forget=client._forget_and_close
                        def lost(handle):
                            forget(handle);raise OSError('Owned post-ACK cleanup fault')
                        with patch.object(client,'_forget_and_close',lost):
                            try:client.apply_admin_operation(planned)
                            except RelationalClientError as error:assert error.native_acknowledged and not error.automatic_retry
                            else:raise AssertionError('Owned cleanup fault was not retained')
                        assert str(status(channel)['Relay_Log_Pos'])==str(2**53+4)
                        for value in (2**32,2**53+1,2**63-1,2**64-1):
                            planned=client.plan_admin_operation(selected(channel,'alter',{'source_options':{'SOURCE_RETRY_COUNT':str(value)}}))
                            assert planned['command_preview']['native_unsigned_long']=={'server_uuid':server_uuid,'maximum':maximum,'requested':str(value)}
                            result=client.apply_admin_operation(planned);assert result['native_acknowledged'] and not result['automatic_retry']
                            retry_state(channel,str(value))
                        # A mixed request checks the largest value regardless
                        # of order while retaining both exact native effects.
                        planned=client.plan_admin_operation(selected(channel,'alter',{'source_options':{'RELAY_LOG_POS':str(2**64-1),'SOURCE_RETRY_COUNT':str(2**53+1)}}))
                        assert planned['command_preview']['native_unsigned_long']['requested']==str(2**64-1)
                        assert client.apply_admin_operation(planned)['native_acknowledged']
                        retry_state(channel,str(2**53+1));assert str(status(channel)['Relay_Log_Pos'])==str(2**64-1)
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'complete':True,
                            'values':[str(value) for value in (2**32,2**53+1,2**63-1,2**64-1)],'native_until_position':str(2**53+1),
                            'replacement_instance_refused_before_dispatch':True,'native_conflict_error':native_error,
                            'ack_retained_after_cleanup_loss':True,'original_diagnostics_and_savepoint_preserved':True,
                            'retry_values':[str(value) for value in (2**32,2**53+1,2**63-1,2**64-1)],
                            'retry_show_status_performance_schema_and_repository_exact':True,'mixed_wide_options_exact':True})
                        print('Native wide coordinates',pure,'passed',flush=True)
                    finally:client.close();clear(channel)
                # Native repository restoration, not just in-memory exposure.
                retained='retry_persistence';configure(retained)
                q.execute('CHANGE REPLICATION SOURCE TO SOURCE_RETRY_COUNT=18446744073709551615 FOR CHANNEL %s',(retained,))
                retry_state(retained,str(2**64-1));q.close();oracle.close()
                _run(['docker','restart',replica_name])
                from cdeadmin_mysql_family_object_live_orchestrator import _wait_until_ready
                assert _wait_until_ready('mysql',replica_name,300)==route['port']
                oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
                q.execute('SELECT @@server_uuid');assert q.fetchone()==(server_uuid,)
                retry_state(retained,str(2**64-1));clear(retained)
                proof['native_retry_repository_restart_preserved']=True
                password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                declarations=engine_operations('mysql')
                for pure in (True,False):
                    channel='api_wide_'+str(pure);file=configure(channel);_,_,post=registration(app,route,password,not pure)
                    target={'resource_kind':'replication-channel','display_name':'Channel '+channel,'native':{'channel_name':channel}}
                    def run(operation,draft):
                        payload={'resource_kind':'replication-channel','operation_id':operation,'target_resource':target,'draft':draft}
                        validated=post('visual_admin_validate',payload);assert validated['valid'],validated['errors']
                        planned=post('visual_admin_plan',payload);assert planned['state']=='ready' and planned['execution_available']
                        ceiling=planned['command_preview'].get('native_unsigned_long',planned['command_preview'].get('native_relay_position'))
                        assert ceiling['maximum']==maximum
                        apply={key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
                        result=post('visual_admin_apply',apply);assert result['provider_result']['native_acknowledged']
                        replay=post.raw('visual_admin_apply',apply);assert replay.status_code!=200 or not replay.get_json().get('success')
                    try:
                        run('alter',{'source_options':{'RELAY_LOG_FILE':file,'RELAY_LOG_POS':str(2**64-1)},'confirmation':target['display_name']})
                        assert str(status(channel)['Relay_Log_Pos'])==str(2**64-1)
                        q.execute('CHANGE REPLICATION SOURCE TO RELAY_LOG_FILE=%s,RELAY_LOG_POS=4 FOR CHANNEL %s',(file,channel))
                        declaration=declarations['start@replication-channel']
                        draft=backend_draft({'tabs':[{'fields':declaration['fields']}]},operation_draft(declaration,
                            {'thread':'SQL_THREAD','until_kind':'RELAY','relay_file':file,'relay_pos':str(2**53+1)},target['display_name']))
                        run('start',draft);observed=status(channel);assert str(observed['Until_Log_Pos'])==str(2**53+1)
                        q.execute('STOP REPLICA FOR CHANNEL %s',(channel,))
                        run('alter',{'source_options':{'SOURCE_RETRY_COUNT':str(2**64-1)},'confirmation':target['display_name']})
                        retry_state(channel,str(2**64-1))
                        proof['application'].append({'use_pure':pure,'complete':True,'native_maximum_position_preserved':True,
                            'typed_until_projection_preserved':True,'consumed_plans_refused':True,'maximum_retry_count_exact':True})
                    finally:clear(channel)
                reader_password=secrets.token_urlsafe(24)
                q.execute('CREATE USER `relay_operator`@`%` IDENTIFIED BY %s',(reader_password,))
                q.execute('GRANT REPLICATION_SLAVE_ADMIN, REPLICATION CLIENT ON *.* TO `relay_operator`@`%`')
                channel='limited_wide';file=configure(channel);restricted=[]
                try:
                    for pure in (True,False):
                        client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=lambda *_:SecretLease(reader_password.encode())),SimpleNamespace())
                        request=selected(channel,'alter',{'source_options':{'RELAY_LOG_POS':str(2**53+1)}})
                        request['_provider_route']={**route,'user':'relay_operator','use_pure':pure,'credential_reference_id':'owned','principal_reference':'owner'}
                        try:
                            planned=client.plan_admin_operation(request)
                            assert planned['command_preview']['native_relay_position']['maximum']==maximum
                            assert client.apply_admin_operation(planned)['native_acknowledged']
                            assert str(status(channel)['Relay_Log_Pos'])==str(2**53+1)
                            request['draft']={'source_options':{'SOURCE_RETRY_COUNT':str(2**64-1)}}
                            planned=client.plan_admin_operation(request)
                            assert planned['command_preview']['native_unsigned_long']['maximum']==maximum
                            assert client.apply_admin_operation(planned)['native_acknowledged']
                            retry_state(channel,str(2**64-1))
                            restricted.append({'use_pure':pure,'native_metadata_publicly_readable':True,'native_effect_without_metadata_select_grant':True,'wide_retry_count_exact':True})
                        finally:client.close()
                finally:clear(channel)
                proof.update(native_unsigned_long_maximum=maximum,restricted=restricted)
            finally:q.close();oracle.close()
            disabled_route,_,disabled_proof=stack.enter_context(server(output/'disabled',server_id=603,performance_schema=False));owned.append(disabled_proof)
            disabled=[];disabled_oracle=_root_connection('mysql',disabled_route['port']);disabled_oracle.autocommit=True;dc=disabled_oracle.cursor()
            try:
                dc.execute("CHANGE REPLICATION SOURCE TO SOURCE_HOST='127.0.0.1',SOURCE_AUTO_POSITION=0,SOURCE_LOG_FILE='sr-owned.000001',SOURCE_LOG_POS=4 FOR CHANNEL 'without_instrumentation'")
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    request={'resource_kind':'replication-channel','operation_id':'alter','target_resource':{
                        'display_name':'Without instrumentation','native':{'channel_name':'without_instrumentation'}},
                        'draft':{'source_options':{'RELAY_LOG_POS':str(2**53+1)}},'_provider_route':{**disabled_route,'use_pure':pure}}
                    try:
                        planned=client.plan_admin_operation(request)
                        assert planned['command_preview']['native_relay_position']['maximum']==str(2**64-1)
                        assert client.apply_admin_operation(planned)['native_acknowledged']
                        dc.execute("SHOW REPLICA STATUS FOR CHANNEL 'without_instrumentation'")
                        observed=dict(zip([row[0] for row in dc.description],dc.fetchone()))
                        assert str(observed['Relay_Log_Pos'])==str(2**53+1)
                        request['draft']={'source_options':{'SOURCE_RETRY_COUNT':str(2**64-1)}}
                        planned=client.plan_admin_operation(request);assert planned['command_preview']['native_unsigned_long']['maximum']==str(2**64-1)
                        assert client.apply_admin_operation(planned)['native_acknowledged']
                        dc.execute("SHOW REPLICA STATUS FOR CHANNEL 'without_instrumentation'")
                        observed=dict(zip([row[0] for row in dc.description],dc.fetchone()))
                        assert str(observed['Source_Retry_Count'])==str(2**64-1)
                        disabled.append({'use_pure':pure,'native_metadata_available_without_performance_schema':True,'native_wide_effect_verified':True,'wide_retry_count_exact':True})
                    finally:client.close()
                dc.execute("RESET REPLICA ALL FOR CHANNEL 'without_instrumentation'")
            finally:dc.close();disabled_oracle.close()
            proof.update(complete=True,disabled=disabled)
    finally:
        proof['owned_servers_stopped']=bool(owned) and all(item['owned_server_stopped'] for item in owned)
        if network_created:_run(['docker','network','rm',network]);proof['owned_network_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    result=qualify(parser.parse_args().output);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))
