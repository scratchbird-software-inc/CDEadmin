"""Native denied/disabled editor and execution observation admission.

Fixture diagnostic baselines use the unbound native cursor method, keeping
diagnostic baselines outside the application paths under qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in
        ['mysql_session_variables.py','mysql_completion.py','mysql_native_validation.py',
         'mysql_values.py','mysql_charsets.py','mysql_execution.py','mysql_query_attributes.py','provider.py']]
    paths+=['web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/browser/server_groups/servers/__init__.py',str(Path(__file__).relative_to(ROOT)),'tools/mysql_qualification_support.py']
    proof={'complete':False,'history_testing':'ScratchBird history not run','interfaces':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_native_editor_gate import provider
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint
    from pgadmin.model import Server
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from pgadmin.cdeadmin.providers.mysql_family.mysql_values import Cursor, MySQLParameterAdmissionError
    from pgadmin.cdeadmin.providers.mysql_family.mysql_query_attributes import Scope
    try:
        for enabled in (True,False):
            with server(output/('denied' if enabled else 'disabled'),performance_schema=enabled) as (route,_name,owned):
                oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
                try:
                    q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY,value INT)')
                    q.execute('INSERT INTO sr_osc.pending VALUES(1,1)')
                    q.execute("SET GLOBAL log_output='TABLE'");q.execute('SET GLOBAL general_log=ON')
                    def traffic(identity):
                        q.execute('SELECT COUNT(*) FROM mysql.general_log WHERE thread_id=%s',(identity,));return q.fetchone()[0]
                    for pure in (True,False):
                        user='sr_editor_'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
                        q.execute('CREATE USER '+user+"@'%' IDENTIFIED BY %s",(password,))
                        q.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON sr_osc.* TO '+user+"@'%'")
                        selected={**route,'user':user,'database':'sr_osc','use_pure':pure}
                        instance,native_route=provider('mysql',selected,password=password)
                        api_session=None;post=None
                        try:
                            session=instance.open_session({'route':native_route});handle=instance._sessions[session['session_id']].handle
                            identity=handle.connection_id;work=handle.cursor()
                            def sql(source):
                                type(work).execute(work,source)
                                return work.fetchall() if work.description else []
                            try:
                                status=handle._cdeadmin_session_variable_observer_status
                                assert not status['admitted'],status
                                assert status['reason']==('native-observer-admission-denied' if enabled else 'performance-schema-disabled')
                                if enabled:assert status['native_errno']==1142,status
                                def refuse():
                                    before=traffic(identity)
                                    for operation in [lambda:instance.complete({'session_id':session['session_id']}),
                                            lambda:instance.validate_source_without_execution({'session_id':session['session_id'],'language_profile':'mysql-sql','source':'DROP TABLE pending'})]:
                                        try:operation()
                                        except RelationalClientError as error:
                                            assert error.original_diagnostics_preserved and error.original_session_commands_sent==0
                                            assert 'No original-session metadata command' in str(error)
                                        else:raise AssertionError('Unavailable editor context used an original-session fallback')
                                    assert traffic(identity)==before
                                    cursor=Cursor(handle)
                                    try:
                                        commands=[lambda:cursor.execute('SELECT %s',['private parameter']),
                                            lambda:cursor.execute('SET @owned_admission=1'),
                                            lambda:cursor.execute('DELIMITER //\nSELECT 1//')]
                                        if not pure:
                                            commands.append(lambda:work.execute('SELECT 1'))
                                        for operation in commands:
                                            try:operation()
                                            except MySQLParameterAdmissionError as error:
                                                assert error.commands_dispatched==0 and error.original_diagnostics_preserved
                                                assert error.original_session_commands_sent==0
                                            else:raise AssertionError('Unavailable execution context used intrusive metadata')
                                    finally:cursor.close()
                                    scope=Scope(handle,{'owned_attribute':'private attribute'})
                                    scope.install()
                                    try:
                                        try:scope.bind()
                                        except MySQLParameterAdmissionError as error:
                                            assert error.commands_dispatched==0 and error.original_diagnostics_preserved
                                        else:raise AssertionError('Query attributes used intrusive metadata')
                                    finally:scope.restore()
                                    assert traffic(identity)==before
                                sql('START TRANSACTION');sql('SAVEPOINT editor_guard');sql('UPDATE pending SET value=value+1')
                                refuse();assert sql('SELECT ROW_COUNT()')==[(1,)]
                                sql("SELECT CAST('owned native warning' AS SIGNED)");refuse()
                                assert any(row[1]==1292 for row in sql('SHOW WARNINGS'))
                                try:sql('SELECT owned_missing_column FROM pending')
                                except Exception as error:assert getattr(error,'errno',None)==1054
                                else:raise AssertionError('Native error fixture did not fail')
                                refuse();assert any(row[1]==1054 for row in sql('SHOW ERRORS'))
                                sql('ROLLBACK TO SAVEPOINT editor_guard');assert sql('SELECT value FROM pending')==[(1,)]
                                sid,target,_registered=registration(app,route,password,not pure,username=user)
                                url=endpoint(app,sid);http=app.test_client()
                                with app.test_request_context('/'):owner=Server.query.get(sid).user_id
                                with http.session_transaction() as state:state['_user_id'],state['_fresh']=str(owner),True
                                def post(action,body):
                                    response=post.raw(action,body);value=response.get_json()
                                    assert response.status_code==200 and value.get('success'),value
                                    return value['data']
                                post.raw=lambda action,body:http.post(url,json={'action':action,'database_target_id':target,**body})
                                api_session=post('open_session',{'language_profile':'mysql-sql'})['session_id']
                                def execute(source,parameters=None,refused=False,attributes=None):
                                    ticket=post('execute',{'session_id':api_session,'source':source,'parameters':parameters or [],
                                        'mysql_query_attributes':attributes or {},'history_sensitive':True})
                                    deadline=time.monotonic()+30
                                    while time.monotonic()<deadline:
                                        value=post('poll',{'occurrence_id':ticket['occurrence_id']})['occurrence']
                                        if value['operation']['terminal']:
                                            result=(value.get('result') or {}).get('extensions',{}).get('mysql',{}).get('payload',{})
                                            if refused:
                                                error=result.get('error') or {}
                                                assert error.get('commands_dispatched')==0 and error.get('original_diagnostics_preserved'),result
                                                assert 'No original-session metadata command' in error['message_primary'],error
                                                return error
                                            assert not result.get('error'),result
                                            return result['rows']
                                        time.sleep(.01)
                                    raise TimeoutError('Owned API SQL did not finish')
                                q.execute('SELECT ID FROM information_schema.PROCESSLIST WHERE USER=%s AND DB=%s ORDER BY ID DESC',(user,'sr_osc'))
                                api_identity=q.fetchone()[0];q.fetchall()
                                before=traffic(api_identity)
                                execute('SELECT %s',['private API parameter'],refused=True)
                                execute('SET @owned_admission=1',refused=True)
                                execute('DELIMITER //\nSELECT 1//',refused=True)
                                execute('SELECT 1',refused=True,attributes={'owned_attribute':'private API attribute'})
                                if not pure:execute('SELECT 1',refused=True)
                                for action in ('source_complete','source_validate'):
                                    response=post.raw(action,{'session_id':api_session,'source':'SELECT pending.', 'source_before_cursor':'SELECT pending.'})
                                    value=response.get_json();assert not value.get('success'),value
                                    assert response.status_code==409 and value['info']=='MYSQL_EDITOR_OBSERVER_UNAVAILABLE'
                                    assert value['data']['original_session_commands_sent']==0 and value['data']['original_diagnostics_preserved']
                                    assert 'No original-session metadata command' in value['errormsg'],value
                                    assert response.headers['Cache-Control']=='no-store'
                                assert traffic(api_identity)==before
                                checks=['native-denied-or-disabled-admission','completion-and-syntax-check-source-command-count-unchanged',
                                    'native-row-count-warning-error-and-pending-savepoint-preserved','authenticated-editor-API-refusal-without-source-queries']
                                checks+=['native-parameter-binding-script-framing-and-C-encoding-refuse-before-dispatch',
                                    'query-attribute-encoding-refuses-without-source-metadata-and-restores-client-state',
                                    'authenticated-execution-refusals-preserve-native-source-command-count']
                                if enabled:
                                    for table in ('variables_by_thread','session_account_connect_attrs','threads'):
                                        q.execute('GRANT SELECT ON performance_schema.'+table+' TO '+user+"@'%'")
                                    assert execute('SELECT %s',['readmitted 雪'])==[['readmitted 雪']]
                                    assert execute('SELECT CONNECTION_ID()')==[[api_identity]]
                                    sql('UPDATE pending SET value=value+1');before=traffic(identity)
                                    result=instance.complete({'session_id':session['session_id']})['editor_context']
                                    parsed=instance.validate_source_without_execution({'session_id':session['session_id'],'language_profile':'mysql-sql','source':'SELECT id FROM pending'})
                                    assert result['original_diagnostics_preserved'] and parsed['original_diagnostics_preserved'] and parsed['grammar_valid']
                                    assert any(row['display_path']==['sr_osc','pending','id'] for row in result['resources'])
                                    assert traffic(identity)==before and sql('SELECT ROW_COUNT()')==[(1,)]
                                    assert handle.connection_id==identity and handle._cdeadmin_session_variable_observer_status['readmitted_without_source_commands']
                                    before=traffic(api_identity)
                                    result=post('source_complete',{'session_id':api_session,'source':'SELECT pending.','source_before_cursor':'SELECT pending.'})['editor_context']
                                    assert result['original_diagnostics_preserved'] and traffic(api_identity)==before
                                    checks.append('native-access-restoration-readmits-execution-and-editor-without-reconnecting-original-core-and-API-sessions')
                                sql('ROLLBACK')
                                expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert type(handle).__name__==expected
                                proof['interfaces'].append({'performance_schema':enabled,'native_connection_class':expected,'complete':True,'checks':checks})
                            finally:work.close()
                        finally:
                            if api_session is not None:post('close_session',{'session_id':api_session})
                            instance.client.close()
                    q.execute('SET GLOBAL general_log=OFF')
                finally:q.close();oracle.close()
            assert owned['owned_server_stopped']
        proof.update(complete=True,owned_servers_stopped=True)
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();value=qualify(args.output);print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))
