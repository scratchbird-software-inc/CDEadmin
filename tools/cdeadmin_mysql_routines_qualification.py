"""Qualify typed native routines and descriptor-backed authenticated workflows."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MYSQL_ADMINISTRATION, _create_client, _resources
    from pgadmin.cdeadmin.providers.mysql_family import mysql_routines as routines
    from pgadmin.cdeadmin.sdk import RelationalClientError
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_routines.py','administration.py','provider.py','descriptor_contracts.py','mysql_triggers.py')]
    paths += ['web/pgadmin/cdeadmin/providers/'+name for name in ('mysql_events.py','mysql_object_changes.py','relational_admin.py')]
    paths += ['web/pgadmin/cdeadmin/ui_descriptors/mysql/'+name for name in ('capabilities.json','operations.json','forms/routine.form.json','forms/routine-function.form.json','forms/routine-scheduled.form.json','forms/trigger.form.json')]
    paths += ['web/pgadmin/cdeadmin/visual_admin/provider.py', str(Path(__file__).relative_to(ROOT))]
    proof = {'complete':False,'history_testing':'ScratchBird history not run','interfaces':[],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output/'fixture') as (route,_container,owned):
            oracle = _root_connection('mysql',route['port']); oracle.autocommit=True; q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_routines CHARACTER SET utf8mb4');q.execute('CREATE TABLE sr_routines.pending(id INT PRIMARY KEY)')
                # The shared authenticated-registration fixture selects sr_osc.
                # Explicit routine identities deliberately target another DB.
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_routines.t(id INT AUTO_INCREMENT PRIMARY KEY,value INT)');q.execute('CREATE TABLE sr_routines.audit(value INT)')
                q.execute('SELECT @@GLOBAL.sql_mode');original_mode=q.fetchone()[0]
                for pure in (True,False):
                    q.execute('SET GLOBAL sql_mode=%s',(original_mode if pure else 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES',))
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    selected={**route,'database':'sr_routines','use_pure':pure};prefix='typed_'+str(int(pure))+'_'
                    classes=[];connect=client._connect
                    def tracked(request):
                        handle=connect(request);classes.append(type(handle).__name__);return handle
                    client._connect=tracked
                    def review(kind,draft):return client.plan_admin_operation({'resource_kind':kind,'operation_id':'create','draft':draft,'_provider_route':selected})
                    def create(kind,draft):return MYSQL_ADMINISTRATION.apply(client,review(kind,draft))
                    procedure={'name':prefix+'p','database':'sr_routines','parameters':[
                        {'name':'input','type':'BIGINT UNSIGNED','mode':'IN'},
                        {'name':'output','type':'DECIMAL(30,0)','mode':'OUT'},
                        {'name':'both','type':'BIGINT UNSIGNED','mode':'INOUT'}],
                        'body':'BEGIN SET `output`=`input`; SET `both`=`both`+1; END',
                        'deterministic':True,'data_access':'NO SQL','sql_security':'INVOKER',
                        'language':'SQL','comment':"native quote' 雪",'definer_user':'root','definer_host':'%'}
                    try:
                        planned=review('procedure',procedure)
                        oracle.autocommit=False;q.execute('SAVEPOINT routine_guard');q.execute('INSERT INTO sr_routines.pending VALUES(%s)',(int(pure)+1,))
                        try:result=MYSQL_ADMINISTRATION.apply(client,planned)
                        except RelationalClientError as error:
                            import traceback
                            context=error.__context__
                            proof['failure']={'native_dispatched':getattr(error,'native_dispatched',None),'native_acknowledged':getattr(error,'native_acknowledged',None),
                                'native_error':getattr(error,'errno',None),'context_type':type(context).__name__,
                                'frames':[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
                                          for frame in traceback.extract_tb(context.__traceback__)] if context else []}
                            raise
                        assert result['accepted'] and result['routine_observation']['native_acknowledged']
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        q.execute('ROLLBACK TO SAVEPOINT routine_guard');oracle.rollback();oracle.autocommit=True
                        q.execute('SET @both=7');q.execute('CALL sr_routines.`'+prefix+'p`(%s,@output,@both)',(18446744073709551615,))
                        while q.nextset():pass
                        q.execute('SELECT @output,@both');assert q.fetchone()==(18446744073709551615,8)
                        function={'name':prefix+'f','database':'sr_routines','parameters':[{'name':'value','type':'VARCHAR(80)','character_set':'utf8mb4','collation':'utf8mb4_bin'}],
                            'returns':'VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin','body':"RETURN CONCAT(`value`, ' /*! literal %s 雪')",'deterministic':True,'data_access':'NO SQL','sql_security':'INVOKER'}
                        assert create('function',function)['accepted']
                        q.execute('SELECT sr_routines.`'+prefix+'f`(%s)',('native',));assert q.fetchone()==('native /*! literal %s 雪',)
                        enum={'name':prefix+'enum','database':'sr_routines','parameters':[{'name':'value','type':"ENUM('x,y','z)')"}],
                              'returns':"ENUM('x,y','z)')",'body':'RETURN `value`','deterministic':True,'data_access':'NO SQL'}
                        assert create('function',enum)['accepted']
                        q.execute('SELECT sr_routines.`'+prefix+'enum`(%s)',('x,y',));assert q.fetchone()==('x,y',)
                        duplicate=create('procedure',{**procedure,'if_not_exists':True,'body':'BEGIN SIGNAL SQLSTATE \'45000\'; END'})
                        assert duplicate['accepted'] and duplicate['native_warnings']
                        q.execute('SELECT ROUTINE_COMMENT,IS_DETERMINISTIC,SQL_DATA_ACCESS,SECURITY_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',('sr_routines',prefix+'p'))
                        assert q.fetchone()==("native quote' 雪",'YES','NO SQL','INVOKER')
                        handle=client._connect({'route':selected})
                        try:
                            resources=_resources(handle,{'route':selected},MYSQL_PROFILE)
                            node=next(row for row in resources if row['resource_kind']=='procedure' and row['display_name']==prefix+'p')
                            facts=node['native'];assert facts['routine_definition_state']=='visible' and facts['parameter_catalog_state']=='observed'
                            assert [row['mode'] for row in facts['parameter_records']]==['IN','OUT','INOUT']
                            assert facts['parameter_records'][0]['type']=='bigint unsigned'
                            node=next(row for row in resources if row['resource_kind']=='function' and row['display_name']==prefix+'f')
                            assert node['native']['returns']=='varchar(100)' and node['native']['parameter_records'][0]['collation']=='utf8mb4_bin'
                        finally:client._forget_and_close(handle)
                        stale={'name':prefix+'stale','database':'sr_routines','body':'BEGIN SELECT 1; END'}
                        planned=review('procedure',stale);q.execute('CREATE PROCEDURE sr_routines.`'+prefix+'stale`() BEGIN SELECT 2; END')
                        try:MYSQL_ADMINISTRATION.apply(client,planned)
                        except RelationalClientError as error:assert not error.native_dispatched
                        else:raise AssertionError('Stale routine admitted')
                        try:review('procedure',{'name':prefix+'injected','database':'sr_routines','body':'BEGIN SELECT 1; END; DROP TABLE sr_routines.pending'})
                        except RelationalClientError:pass
                        else:raise AssertionError('Native grammar admitted multiple commands')
                        q.execute('SELECT COUNT(*) FROM sr_routines.pending');assert q.fetchone()==(0,)
                        try:create('function',{'name':prefix+'bad','database':'sr_routines','returns':'INT','body':'SELECT 1'})
                        except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and error.errno>=1000
                        else:raise AssertionError('Native routine error lost')
                        planned=review('procedure',{'name':prefix+'lost','database':'sr_routines','body':'BEGIN SELECT 1; END'})
                        original=routines.observe;calls=0
                        def lost(*args):
                            nonlocal calls
                            calls+=1
                            if calls==2:raise OSError('Owned post-ack observation loss')
                            return original(*args)
                        with patch.object(routines,'observe',lost):
                            try:MYSQL_ADMINISTRATION.apply(client,planned)
                            except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and error.automatic_retry is False
                            else:raise AssertionError('Post-ack observation loss hidden')
                        q.execute('SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',('sr_routines',prefix+'lost'));assert q.fetchone()==(1,)
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'native_connection_class':expected,'complete':True,
                            'unsigned64_in_out_inout_execution':True,'native_function_charset_and_literal_markers':True,'enum_type_punctuation':True,
                            'native_create_characteristics':True,'if_not_exists_preserves_existing_body':True,'ordered_catalog_parameters_and_returns':True,
                            'source_row_count_transaction_and_savepoint_preserved':True,'stale_review_refused':True,'native_grammar_rejected_appended_command_without_execution':True,'native_error_preserved':True,'post_ack_observation_loss_not_replayed':True})
                        proof['interfaces'][-1]['triggers']=trigger_profile(client,selected,q,pure)
                    finally:client.close()
                q.execute('SET GLOBAL sql_mode=%s',(original_mode,))
                password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                proof['application']=workspace(app,route,password,q);proof['complete']=True
            finally:q.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def trigger_profile(client,route,q,pure):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_triggers as triggers
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources
    from pgadmin.cdeadmin.sdk import RelationalClientError
    prefix='trg_'+str(int(pure))+'_';names=[]
    def review(suffix,**values):
        name=prefix+suffix
        return client.plan_admin_operation({'resource_kind':'trigger','operation_id':'create',
            'draft':{'name':name,'table':['sr_routines','t'],'body':'SET NEW.value=NEW.value',**values},'_provider_route':route})
    def create(suffix,**values):
        planned=review(suffix,**values);result=MYSQL_ADMINISTRATION.apply(client,planned);names.append(prefix+suffix)
        assert result['accepted'] and result['trigger_observation']['native_acknowledged'];return result
    try:
        create('a',body='SET NEW.value=NEW.value*10',definer_user='root',definer_host='%')
        create('b',order='FOLLOWS',other_trigger=prefix+'a',body='SET NEW.value=NEW.value+3')
        planned=review('c',order='PRECEDES',other_trigger=prefix+'a',body='BEGIN SET NEW.value=NEW.value+2; END')
        # A pending writer/savepoint on the original session survives separate DDL.
        q.execute('SET autocommit=0');q.execute('SAVEPOINT trigger_guard');q.execute('INSERT INTO sr_routines.pending VALUES(%s)',(20+int(pure),))
        result=MYSQL_ADMINISTRATION.apply(client,planned);names.append(prefix+'c');assert result['accepted']
        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
        q.execute('ROLLBACK TO SAVEPOINT trigger_guard');q.execute('ROLLBACK');q.execute('SET autocommit=1')
        duplicate=MYSQL_ADMINISTRATION.apply(client,review('b',if_not_exists=True,body='SET NEW.value=0'));assert duplicate['accepted'] and duplicate['native_warnings']
        q.execute('INSERT INTO sr_routines.t(value) VALUES(1)');q.execute('SELECT value FROM sr_routines.t WHERE id=LAST_INSERT_ID()');assert q.fetchone()==(33,)
        create('update',event='UPDATE',body='SET NEW.value=NEW.value+1')
        q.execute('UPDATE sr_routines.t SET value=5 WHERE id=LAST_INSERT_ID()');q.execute('SELECT value FROM sr_routines.t WHERE id=LAST_INSERT_ID()');assert q.fetchone()==(6,)
        create('delete',events=['DELETE'],timing='AFTER',body='INSERT INTO sr_routines.audit VALUES(OLD.value)')
        q.execute('DELETE FROM sr_routines.t WHERE id=LAST_INSERT_ID()');q.execute('SELECT value FROM sr_routines.audit ORDER BY value');assert (6,) in q.fetchall()
        handle=client._connect({'route':route})
        try:
            rows=_resources(handle,{'route':route},MYSQL_PROFILE)
            row=next(row for row in rows if row['resource_kind']=='trigger' and row['display_name']==prefix+'b')
            assert row['display_path']==['sr_routines','t',prefix+'b']
            facts=row['native'];assert facts['action_order']==3 and facts['action_statement']=='SET NEW.value=NEW.value+3'
            assert facts['event']=='INSERT' and facts['timing']=='BEFORE' and isinstance(facts['sql_mode'],str)
        finally:client._forget_and_close(handle)
        planned=review('stale',order='FOLLOWS',other_trigger=prefix+'a')
        q.execute('CREATE TRIGGER sr_routines.`'+prefix+'external` BEFORE INSERT ON sr_routines.t FOR EACH ROW SET NEW.value=NEW.value');names.append(prefix+'external')
        try:MYSQL_ADMINISTRATION.apply(client,planned)
        except RelationalClientError as error:assert not error.native_dispatched
        else:raise AssertionError('Stale trigger order admitted')
        try:create('missing',order='FOLLOWS',other_trigger=prefix+'missing_anchor')
        except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and error.errno>=1000
        else:raise AssertionError('Native ordering error hidden')
        try:review('injected',body='BEGIN SET NEW.value=1; END; DROP TABLE sr_routines.pending')
        except RelationalClientError:pass
        else:raise AssertionError('Native grammar admitted appended trigger command')
        planned=review('lost');original=triggers.observe;calls=0
        def lost(*args):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Owned observation loss')
            return original(*args)
        with patch.object(triggers,'observe',lost):
            try:MYSQL_ADMINISTRATION.apply(client,planned)
            except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and error.automatic_retry is False
            else:raise AssertionError('Trigger ACK disappeared')
        names.append(prefix+'lost')
        q.execute('SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME=%s',('sr_routines',prefix+'lost'));assert q.fetchone()==(1,)
        return {'complete':True,'native_insert_update_delete_execution':True,'follows_precedes_order_verified':True,
            'native_definer_and_if_not_exists':True,'pending_writer_and_savepoint_preserved':True,
            'full_committed_catalog_fields':True,'stale_order_refused':True,'native_missing_anchor_error_preserved':True,
            'appended_command_refused_without_execution':True,'post_ack_loss_never_replayed':True}
    finally:
        for name in names:q.execute('DROP TRIGGER IF EXISTS sr_routines.`'+name+'`')


def workspace(app,route,password,oracle):
    from cdeadmin_mysql_online_ddl_qualification import registration
    results=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure);prefix='api_'+str(int(pure))+'_'
        def run(kind,operation,draft,target=None):
            value={'resource_kind':kind,'operation_id':operation,'draft':draft}
            if target:value['target_resource']=target
            planned=post('visual_admin_plan',value);assert planned['state']=='ready' and planned['execution_available']
            result=post('visual_admin_apply',{key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
            assert result['provider_result']['accepted'];return result
        def target(kind,name):return {'resource_kind':kind,'resource_id':kind+':sr_routines:'+name,'display_path':['sr_routines',name],'display_name':name,'generation':'current'}
        for kind in ('procedure','function'):
            name=prefix+kind
            draft={'name':name,'parent':'sr_routines','parameters':[{'name':'input','type':'INT'}],
                'body':'BEGIN SELECT `input`; END' if kind=='procedure' else 'RETURN `input`+1',
                'data_access':'NO SQL','sql_security':'INVOKER','deterministic':True,'comment':'initial'}
            if kind=='function':draft['returns']='INT'
            run(kind,'create',draft)
            run(kind,'alter',{'comment':'changed','confirmation':name},target(kind,name))
            oracle.execute('SELECT SQL_DATA_ACCESS,SECURITY_TYPE,ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',('sr_routines',name));assert oracle.fetchone()==('NO SQL','INVOKER','changed')
        name=prefix+'event'
        run('event','create',{'name':name,'database':'sr_routines','body':'SELECT 1','schedule':'EVERY 1 DAY','status':'DISABLE','completion':'PRESERVE','time_zone':'+00:00','comment':'initial'})
        run('event','alter',{'comment':'changed','confirmation':name},target('event',name))
        oracle.execute('SELECT STATUS,ON_COMPLETION,EVENT_COMMENT,TIME_ZONE FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s AND EVENT_NAME=%s',('sr_routines',name));assert oracle.fetchone()==('DISABLED','PRESERVE','changed','+00:00')
        run('event','rename',{'new_name':name+'_renamed','confirmation':name},target('event',name))
        oracle.execute('SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s AND EVENT_NAME=%s',('sr_routines',name+'_renamed'));assert oracle.fetchone()==(1,)
        name=prefix+'trigger';anchor=name+'_anchor'
        oracle.execute('CREATE TRIGGER sr_routines.`'+anchor+'` BEFORE INSERT ON sr_routines.t FOR EACH ROW SET NEW.value=NEW.value*2')
        run('trigger','create',{'name':name,'table':['sr_routines','t'],'event':'INSERT','timing':'BEFORE','order':'PRECEDES','other_trigger':anchor,'body':'SET NEW.value=NEW.value+1'})
        oracle.execute('INSERT INTO sr_routines.t(value) VALUES(3)');oracle.execute('SELECT value FROM sr_routines.t WHERE id=LAST_INSERT_ID()');assert oracle.fetchone()==(8,)
        trigger_target={'resource_kind':'trigger','resource_id':'trigger:sr_routines:t:'+name,'display_path':['sr_routines','t',name],'display_name':name,'generation':'current'}
        run('trigger','drop',{'confirmation':name},trigger_target);oracle.execute('DROP TRIGGER sr_routines.`'+anchor+'`')
        results.append({'typed_trigger_order_execution_and_drop':True,'use_pure':pure,'typed_create_alter_routine_bindings':True,'comment_only_preserves_security_and_data_access':True,'scheduled_event_preservation_and_rename':True})
    return {'complete':True,'interfaces':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=qualify(args.output);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))
