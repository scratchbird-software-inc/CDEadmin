"""Native procedural/header preflight, without executing submitted SQL or history."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(engine,output):
    from cdeadmin_native_editor_gate import provider
    from mysql_qualification_support import server,_root_connection
    if engine=='mariadb':
        from mariadb_qualification_support import server
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside application source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=['web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/cdeadmin/providers/mysql_family/prepare_classification.py',
        'web/pgadmin/cdeadmin/data_studio/language_tools.py',
        'tools/mysql_qualification_support.py','tools/mariadb_qualification_support.py',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'engine':engine,'interfaces':[],'failures':[],'history_testing':'not run',
        'qualification_scope':'native core profile and recorded modes; not additional parser/rewrite plugins or all procedural completion',
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            root=_root_connection(engine,route['port']);root.autocommit=True;oracle=root.cursor()
            database='sr_prepare_'+secrets.token_hex(6);q=lambda name:'`'+name.replace('`','``')+'`'
            try:
                oracle.execute('CREATE DATABASE '+q(database));oracle.execute('USE '+q(database))
                oracle.execute('CREATE TABLE pending(id INT PRIMARY KEY)');oracle.execute('INSERT INTO pending VALUES(1)')
                oracle.execute('CREATE VIEW original_view AS SELECT id FROM pending')
                oracle.execute('SHOW CREATE VIEW original_view');view_before=oracle.fetchone()
                oracle.execute('SELECT @@sql_mode');original_mode=oracle.fetchone()[0]
                denied_user='sr_denied_'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
                oracle.execute('CREATE TABLE allowed_probe(id INT)')
                oracle.execute('CREATE USER '+q(denied_user)+"@'%' IDENTIFIED BY %s",(password,))
                oracle.execute('GRANT SELECT ON '+q(database)+'.allowed_probe TO '+q(denied_user)+"@'%'")
                for pure in ([True,False] if engine=='mysql' else [None]):
                    label='pure' if pure else 'c' if pure is False else 'mariadb-c';instance=None
                    try:
                        instance,native_route=provider(engine,{**route,'database':database,**({'use_pure':pure} if pure is not None else {})})
                        session=instance.open_session({'route':native_route});handle=instance._sessions[session['session_id']].handle
                        instance.client.control_transaction(handle,'autocommit_off');work=handle.cursor()
                        try:
                            work.execute('INSERT INTO pending VALUES(2)');checks=[]
                            work.execute('SAVEPOINT sr_pending')
                            modes=['','ANSI_QUOTES','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES',''] if engine=='mysql' else ['', 'ORACLE']
                            for mode in modes:
                                work.execute('SET SESSION sql_mode=%s',(mode,));oracle.execute('SET SESSION sql_mode=%s',(mode,))
                                text="quote' slash\\ NUL\x00 Unicode 雪😀";binary=b"\x00\xff'\\\r\n"
                                work.execute('SELECT %s,HEX(%s)',(text,binary))
                                assert work.fetchone()==(text,binary.hex().upper())
                                if engine=='mysql':
                                    from pgadmin.cdeadmin.providers.mysql_family.mysql_values import Cursor
                                    query=Cursor(handle)
                                    try:
                                        query.execute('SELECT %s,HEX(%s)',(text,binary));assert query.fetchone()==(text,binary.hex().upper())
                                    finally:query.close()
                                checks.append({'name':'live-mode-typed-parameter-values','mode':mode,'unicode_quote_backslash_nul_and_binary_preserved':True})
                                p=q(database)+'.'+q('not_created');body='() BEGIN DECLARE v INT DEFAULT 1; SELECT v; END'
                                cases=[('plain-procedure','CREATE PROCEDURE '+p+body),
                                    ('line-comment-crlf','# Native comment\r\nCREATE PROCEDURE '+p+body),
                                    ('commented-out-invalid-body','# Native comment\rCREATE PROCEDURE '+p+'() BEGIN SELEC 1; END'),
                                    ('header-comment','CREATE /* native header */ PROCEDURE '+p+body),
                                    ('current-definer','CREATE DEFINER=CURRENT_USER() PROCEDURE '+p+body),
                                    ('quoted-definer',"CREATE DEFINER='odd''user'@'host.example' PROCEDURE "+p+body),
                                    ('quoted-identifier-definer','CREATE DEFINER=`odd``user`@`host.example` PROCEDURE '+p+body),
                                    ('definer-function','CREATE DEFINER=CURRENT_USER FUNCTION '+p+'() RETURNS INT DETERMINISTIC RETURN 1'),
                                    ('definer-trigger','CREATE DEFINER=CURRENT_USER TRIGGER '+p+' BEFORE INSERT ON pending FOR EACH ROW SET @v=1'),
                                    ('alter-view','ALTER ALGORITHM=MERGE DEFINER=CURRENT_USER SQL SECURITY INVOKER VIEW original_view AS SELECT 7 AS id'),
                                    ('invalid-body','CREATE DEFINER=CURRENT_USER PROCEDURE '+p+'() BEGIN SELEC 1; END'),
                                    ('missing-catalog','SELECT * FROM not_present'),
                                    ('drop-without-execution','DROP TABLE pending')]
                                if engine=='mysql':cases += [
                                    ('active-version-definer','CREATE /*!90700 DEFINER=CURRENT_USER() */ PROCEDURE '+p+body),
                                    ('ignored-version-header','/*!99999 SELECT invalid */ CREATE PROCEDURE '+p+body),
                                    ('aggregate-udf',"CREATE AGGREGATE FUNCTION "+q('sr_missing_udf')+" RETURNS INTEGER SONAME 'sr-do-not-load.so'"),
                                    ('transactional-ddl','CREATE TABLE '+q('sr_not_created')+'(v INT) START TRANSACTION')]
                                if engine=='mysql':
                                    controls=[
                                        ('create-resource-group','CREATE RESOURCE GROUP sr_rg TYPE=USER VCPU=0 THREAD_PRIORITY=0 DISABLE'),
                                        ('alter-resource-group','ALTER RESOURCE GROUP sr_rg THREAD_PRIORITY=0'),
                                        ('drop-resource-group','DROP RESOURCE GROUP sr_rg'),
                                        ('create-tablespace',"CREATE TABLESPACE sr_ts ADD DATAFILE 'sr_ts.ibd' ENGINE=InnoDB"),
                                        ('alter-tablespace','ALTER TABLESPACE sr_ts AUTOEXTEND_SIZE=1048576'),
                                        ('drop-tablespace','DROP TABLESPACE sr_ts ENGINE=InnoDB'),
                                        ('create-undo-tablespace',"CREATE UNDO TABLESPACE sr_undo ADD DATAFILE 'sr_undo.ibu'"),
                                        ('alter-undo-tablespace','ALTER UNDO TABLESPACE sr_undo SET INACTIVE'),
                                        ('drop-undo-tablespace','DROP UNDO TABLESPACE sr_undo'),
                                        ('create-logfile-group',"CREATE LOGFILE GROUP sr_lg ADD UNDOFILE 'sr_undo.dat' ENGINE=NDB"),
                                        ('alter-logfile-group',"ALTER LOGFILE GROUP sr_lg ADD UNDOFILE 'sr_undo2.dat' ENGINE=NDB"),
                                        ('drop-logfile-group','DROP LOGFILE GROUP sr_lg ENGINE=NDB'),
                                        ('create-role',"CREATE ROLE 'sr_role'"),('drop-role',"DROP ROLE 'sr_role'"),
                                        ('create-srs',"CREATE SPATIAL REFERENCE SYSTEM 999999 NAME 'sr_srs' DEFINITION 'invalid-wkt'"),
                                        ('drop-srs','DROP SPATIAL REFERENCE SYSTEM 999999'),
                                        ('install-component',"INSTALL COMPONENT 'file://sr_absent'"),
                                        ('uninstall-component',"UNINSTALL COMPONENT 'file://sr_absent'"),
                                        ('begin','START TRANSACTION'),('begin-work','BEGIN WORK'),
                                        ('savepoint','SAVEPOINT sr_probe'),('release-savepoint','RELEASE SAVEPOINT sr_probe'),
                                        ('rollback-savepoint','ROLLBACK TO SAVEPOINT sr_probe'),
                                        ('xa-start',"XA START 'sr_xa'"),('xa-begin',"XA BEGIN 'sr_xa'"),
                                        ('xa-end',"XA END 'sr_xa'"),('xa-prepare',"XA PREPARE 'sr_xa'"),
                                        ('xa-commit',"XA COMMIT 'sr_xa'"),('xa-rollback',"XA ROLLBACK 'sr_xa'"),('xa-recover','XA RECOVER'),
                                        ('lock-tables','LOCK TABLES pending READ'),('unlock-tables','UNLOCK TABLES'),
                                        ('use','USE information_schema'),('help',"HELP 'SELECT'"),
                                        ('get-diagnostics','GET CURRENT DIAGNOSTICS @sr_count=NUMBER'),
                                        ('signal',"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='probe'"),('resignal','RESIGNAL'),
                                        ('prepare',"PREPARE sr_nested FROM 'SELECT 1'"),('execute','EXECUTE sr_nested'),
                                        ('deallocate','DEALLOCATE PREPARE sr_nested'),('drop-prepare','DROP PREPARE sr_nested'),
                                        ('import-table',"IMPORT TABLE FROM 'sr_missing.sdi'"),
                                        ('clone',"CLONE LOCAL DATA DIRECTORY='/tmp/sr-do-not-create'"),
                                        ('alter-database','ALTER DATABASE '+q(database)+' READ ONLY=1')]
                                    cases += controls+[(name+'-invalid',source+' SR_TRAILING_INVALID +') for name,source in controls]
                                elif mode=='ORACLE':cases += [
                                    ('oracle-procedure','CREATE OR REPLACE PROCEDURE '+p+' AS v INTEGER := 1; BEGIN NULL; END'),
                                    ('oracle-anonymous','BEGIN NULL; END')]
                                for name,source in cases:
                                    # Independent native PREPARE records the release's
                                    # actual code; no oracle statement is EXECUTEd.
                                    prepared=False;native_code=0
                                    try:
                                        oracle.execute('SET @sr_oracle_source=CONVERT(%s USING utf8mb4)',(source.encode('utf8'),))
                                        oracle.execute('PREPARE sr_oracle FROM @sr_oracle_source');prepared=True
                                    except Exception as error:native_code=error.errno
                                    finally:
                                        if prepared:oracle.execute('DEALLOCATE PREPARE sr_oracle')
                                        oracle.execute('SET @sr_oracle_source=NULL')
                                    expected=False if native_code in {1064,1149} else True if native_code==0 or engine=='mysql' and native_code==1295 and name not in {'missing-catalog','commented-out-invalid-body'} else None
                                    if name in {'oracle-procedure','oracle-anonymous'} and expected is not True:
                                        raise AssertionError('Native Oracle-mode fixture did not prepare its valid procedural source: '+name+' '+str(native_code))
                                    result=instance.validate_source_without_execution({'session_id':session['session_id'],'language_profile':engine+'-sql','source':source})
                                    checked={'name':name,'mode':mode,'native_code':native_code,'grammar_valid':result['grammar_valid'],
                                        'syntax_valid':result.get('syntax_valid'),'native_statements':result.get('native_statements'),
                                        'parser_version':result['parser_version'],'native_sql_mode':result['sql_mode']}
                                    checks.append(checked)
                                    if result['grammar_valid'] is not expected or result.get('syntax_valid') is not expected:
                                        proof['failures'].append({'interface':label,'name':name,'mode':mode,'expected':expected,'observed':checked})
                                # Identifiers never use backslash escaping. ANSI
                                # double quotes follow the observed native mode.
                                for quote in (['`','"'] if 'ANSI_QUOTES' in mode or mode=='ORACLE' else ['`']):
                                    source='SELECT 1 AS '+quote+'back\\'+quote+'; # ignored ;\r\nSELECT 2;'
                                    framed=instance.validate_source_without_execution({'session_id':session['session_id'],
                                        'language_profile':engine+'-sql','source':source,'script':True})
                                    assert framed['script_ready'] and framed['grammar_valid'] is True and len(framed['statements'])==2, framed
                                    marker_source='SELECT 1 AS '+quote+'back\\'+quote+', %s'
                                    marked=instance.validate_source_without_execution({'session_id':session['session_id'],
                                        'language_profile':engine+'-sql','source':marker_source})
                                    assert marked['grammar_valid'] is True, marked
                                    checks.append({'name':'native-backslash-identifier-script-and-parameter','mode':mode,
                                        'quote':quote,'native_statement_count':2,'grammar_valid':True})
                                oracle.execute('SELECT COUNT(*) FROM pending');assert oracle.fetchone()[0]==1
                                work.execute('SELECT COUNT(*) FROM pending');assert work.fetchone()[0]==2
                                oracle.execute('SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s',(database,));assert oracle.fetchone()[0]==0
                                oracle.execute('SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s',(database,));assert oracle.fetchone()[0]==0
                                oracle.execute('SET SESSION sql_mode=%s',(original_mode,))
                                oracle.execute('SHOW CREATE VIEW original_view');assert oracle.fetchone()==view_before
                                oracle.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ('sr_not_created','not_created')",(database,));assert oracle.fetchone()[0]==0
                                work.execute('SELECT DATABASE()');assert work.fetchone()==(database,)
                                work.execute('ROLLBACK TO SAVEPOINT sr_pending')
                                work.execute('SELECT COUNT(*) FROM pending');assert work.fetchone()[0]==2
                            instance.client.control_transaction(handle,'rollback');work.execute('SELECT COUNT(*) FROM pending');assert work.fetchone()[0]==1
                            denied_instance=None
                            try:
                                denied_instance,denied_route=provider(engine,{**route,'user':denied_user,'database':database,**({'use_pure':pure} if pure is not None else {})},password)
                                denied_session=denied_instance.open_session({'route':denied_route})
                                refused=denied_instance.validate_source_without_execution({'session_id':denied_session['session_id'],'language_profile':engine+'-sql','source':'SELECT * FROM pending'})
                                assert refused['grammar_valid'] is None and refused['syntax_valid'] is None
                                assert refused['native_statements'][0]['native_code']==1142
                                checks.append({'name':'native-privilege-denial-not-syntax-success','native_code':1142,'grammar_valid':None,'syntax_valid':None})
                            finally:
                                if denied_instance is not None:denied_instance.client.close()
                            if engine=='mysql':
                                previous_id=None
                                for lease_number in range(2):
                                    lease=instance.client._connect({'route':{**native_route,'pool_name':'preflight-modes','pool_size':1,'pool_reset_session':True}})
                                    query=lease.cursor()
                                    try:
                                        query.execute('SELECT CONNECTION_ID()');connection_id=query.fetchone()[0]
                                        if previous_id is not None:assert connection_id==previous_id
                                        previous_id=connection_id
                                        for selected_mode in ('NO_BACKSLASH_ESCAPES',''):
                                            query.execute('SET SESSION sql_mode=%s',(selected_mode,))
                                            query.execute('SELECT %s,HEX(%s)',(text,binary));assert query.fetchone()==(text,binary.hex().upper())
                                    finally:query.close();lease.close()
                                checks.append({'name':'native-pool-reset-and-reborrow-retain-correct-live-mode-conversion','leases':2,'same_native_connection':True})
                            proof['interfaces'].append({'label':label,'native_client':type(handle).__name__,
                                'driver_version':str(getattr(instance.client.module,'__version__','unavailable')),'checks':checks,
                                'pending_work_preserved':True,'submitted_sql_not_executed':True,'rollback_verified':True})
                        finally:work.close()
                    except Exception as error:
                        proof['failures'].append({'interface':label,'error_type':type(error).__name__});(output/('failure-'+label+'.log')).write_text(traceback.format_exc())
                    finally:
                        if instance is not None:instance.client.close()
            finally:oracle.close();root.close()
        proof.update(owned_server_stopped=owned['owned_server_stopped'],complete=not proof['failures'] and owned['owned_server_stopped'])
    finally:(output/'summary.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native preflight qualification failed; retained every interface/case failure')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--engine',choices=('mysql','mariadb'),required=True)
    parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args();qualify(args.engine,args.evidence)
