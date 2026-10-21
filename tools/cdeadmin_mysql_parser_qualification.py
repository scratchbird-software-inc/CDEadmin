"""Owned MySQL9.7 versioned grammar, retained diagnostics and desktop proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output, library, *, use_c=False, browser_binary=None, driver_binary=None):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native qualification outside source')
    output.mkdir(parents=True,exist_ok=False)
    library=Path(library).resolve(strict=True)
    os.environ['CDEADMIN_MYSQL_PARSER_LIBRARY']=str(library)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from mysql_qualification_support import server,_root_connection
    client=app.test_client();session_id=None
    paths=['tools/cdeadmin_mysql_parser_qualification.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_parser.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_parser_worker.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_native_validation.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_session_variables.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/cdeadmin/data_studio/language_tools.py']
    proof={'complete':False,'history_testing':'not run','checks':[],'mysql_interface':'c' if use_c else 'pure',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        'library_sha256':hashlib.sha256(library.read_bytes()).hexdigest()}
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                password='parser-'+secrets.token_urlsafe(24)
                query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                query.execute('CREATE DATABASE sr_workspace CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_workspace.t(id INT PRIMARY KEY,value INT)')
                query.execute('INSERT INTO sr_workspace.t VALUES(1,1),(2,1)')
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    item=Server(user_id=uid,servergroup_id=group.id,name='Owned MySQL grammar',host=route['host'],
                        port=route['port'],username='root',maintenance_db='sr_workspace',save_password=0)
                    item._cde_endpoint_registration=registration_profile('mysql-native')
                    item._cde_endpoint_route_configuration={**route,'database':'sr_workspace','user':'root',
                        'use_pure':not use_c,'autocommit':True,'credential_kinds':['database_password']}
                    db.session.add(item);db.session.commit();sid=item.id
                    target=str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,
                        display_name='sr_workspace',database='sr_workspace',configuration='{}',active=1));db.session.commit()
                    url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
                    verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(verify,json={'password':password}).get_json()['success']
                def post(action,**data):
                    response=client.post(url,json={'action':action,'database_target_id':target,**data});value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                        raise AssertionError('Native grammar application request failed: '+action)
                    return value['data']
                session_id=post('open_session',language_profile='mysql-sql')['session_id']
                admitted=post('transaction',session_id=session_id)['provider_payload']['session_variable_observer']
                assert admitted['admitted'] and admitted['original_session_commands_sent']==0
                connection_id=int(admitted['connection_id'])
                query.execute("SELECT ATTR_NAME,ATTR_VALUE FROM performance_schema.session_connect_attrs WHERE PROCESSLIST_ID=%s AND ATTR_NAME IN ('_client_name','_connector_name','_connector_version')",(connection_id,))
                proof['native_client_attributes']=dict(query.fetchall())
                query.execute("SET GLOBAL log_output='TABLE'");query.execute('SET GLOBAL general_log=ON')
                def traffic_count():
                    query.execute('SELECT COUNT(*) FROM mysql.general_log WHERE thread_id=%s',(connection_id,));return query.fetchone()[0]
                def sql(source, *, refused=False):
                    occurrence=post('execute',session_id=session_id,source=source,parameters=[],history_sensitive=True)
                    deadline=time.monotonic()+30
                    while True:
                        item=post('poll',occurrence_id=occurrence['occurrence_id'])['occurrence']
                        if item['operation']['terminal']:break
                        if time.monotonic()>deadline:raise TimeoutError('Native grammar source SQL deadline')
                        time.sleep(.01)
                    value=(item.get('result') or {}).get('extensions',{}).get('mysql',{}).get('payload',{})
                    if not refused:assert not value.get('error'),value
                    return value.get('rows') or []
                def check(source,expected, *, script=False):
                    before=traffic_count()
                    value=post('source_validate',session_id=session_id,source=source,script=script)
                    assert traffic_count()==before,'Validation sent a hidden command to the source'
                    assert value['grammar_valid'] is expected,value
                    assert value['authority']=='mysql-native-versioned-server-grammar' and value['original_diagnostics_preserved']
                    assert value['original_session_commands_sent']==0 and not value['original_session_catalog_binding_validated']
                    assert not value['sql_executed']
                    if not value['diagnostics'] or expected is not None:
                        assert value.get('native_parser',{}).get('parser_version')=='9.7.0',value
                    return value
                decisions=[]
                for mode in ('','ANSI_QUOTES','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES','ANSI','PIPES_AS_CONCAT,HIGH_NOT_PRECEDENCE,IGNORE_SPACE'):
                    sql("SET SESSION sql_mode='"+mode+"'")
                    sql('UPDATE t SET value=value+1')
                    grammar=check('SELECT id FROM future_not_created',True)
                    assert sql('SELECT ROW_COUNT()')==[[2]]
                    assert grammar['native_parser']['database_connection_opened'] is False
                    check('CREATE PROCEDURE not_created() BEGIN DECLARE n INT; SET n=1; SELECT n; END',True)
                    check('CREATE PROCEDURE not_created() BEGIN SELEC 1; END',False)
                    sql("SELECT CAST('owned-warning' AS SIGNED)")
                    check('SELEC 1',False)
                    assert any(row[1]==1292 for row in sql('SHOW WARNINGS'))
                    sql('SELECT absent_column FROM t',refused=True)
                    check('DROP TABLE t',True)
                    assert any(row[1]==1054 for row in sql('SHOW ERRORS'))
                    quotes='ANSI' in mode or 'ANSI_QUOTES' in mode
                    check('CREATE TABLE not_created("two words" INT)',quotes)
                    backslash=check("SELECT 'a\\'b'",'NO_BACKSLASH_ESCAPES' not in mode)
                    check('SELECT $$not_a_general_literal$$',False)
                    check('CREATE LIBRARY not_created LANGUAGE JAVASCRIPT AS $body$not valid JavaScript; 雪$body$',True)
                    hint=check('SELECT /*+ UNKNOWN_HINT(1) */ 1',True)
                    assert hint['diagnostics'][0]['code']=='NATIVE_OPTIMIZER_HINT' and hint['diagnostics'][0]['severity']=='warning'
                    framed=check('DELIMITER //\nCREATE PROCEDURE not_created() BEGIN SELECT 1; END//\nSELECT id FROM future_not_created//',True,script=True)
                    assert framed['script_ready'] and len(framed['statements'])==2
                    decisions.append({'mode':mode,'native_mode':grammar['sql_mode'],'original_source_commands_added':0,
                        'native_parser_version':grammar['parser_version']})
                proof['checks'].append('actual-native-9.7-server-grammar-through-authenticated-HTTP-across-six-live-SQL-modes-with-zero-original-session-commands')
                proof['checks'].append('compound-procedure-and-future-catalog-syntax-without-execution-privilege-or-catalog-binding-claims')
                proof['checks'].append('actual-original-ROW_COUNT-warning-and-error-areas-survive-valid-invalid-and-procedural-native-checks')
                proof['checks'].append('exact-native-ANSI-backslash-and-expanded-mode-behavior-with-separate-native-optimizer-hint-warnings')
                sql("SET SESSION sql_mode=''")
                unknown=check("SET sql_mode='ANSI_QUOTES'; SELECT 1",None,script=True)
                assert not unknown['script_ready'] and any(row['code']=='SESSION_FRAMING_CHANGE' for row in unknown['diagnostics'])
                proof['checks'].append('script-language-mode-transition-remains-explicitly-unconfirmed-without-using-the-wrong-grammar-mode')
                sql('SET autocommit=0');sql('INSERT INTO t VALUES(3,1)');sql('SAVEPOINT sr_parser')
                check('COMMIT',True);check('ROLLBACK',True);check('ALTER TABLE t ADD COLUMN not_added INT',True)
                query.execute('SELECT COUNT(*) FROM sr_workspace.t');assert query.fetchone()[0]==2
                sql('ROLLBACK TO SAVEPOINT sr_parser');sql('ROLLBACK');sql('SET autocommit=1')
                query.execute("SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA='sr_workspace' AND ROUTINE_NAME='not_created'");assert query.fetchone()[0]==0
                query.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='sr_workspace' AND COLUMN_NAME='not_added'");assert query.fetchone()[0]==0
                proof['checks'].append('pending-native-transaction-savepoint-and-live-database-definitions-preserved-without-executing-DDL-or-decisions')
                query.execute('SET GLOBAL general_log=OFF')
                if browser_binary:
                    from cdeadmin_mysql_family_editor_workspace_qualification import browser
                    proof['browser']=browser(app,output,'mysql',sid,browser_binary,driver_binary,password)
                    proof['checks'].append('built-native-editor-source-tools-valid-invalid-procedural-and-library-checks-with-zero-browser-errors')
                post('close_session',session_id=session_id);session_id=None
                proof.update(complete=True,modes=decisions,independent_observer=admitted)
            finally:
                try:query.execute('SET GLOBAL general_log=OFF')
                except Exception:pass
                query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--library',required=True);parser.add_argument('--use-c',action='store_true')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    value=qualify(args.output,args.library,use_c=args.use_c,browser_binary=args.browser_binary,driver_binary=args.driver_binary)
    print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
