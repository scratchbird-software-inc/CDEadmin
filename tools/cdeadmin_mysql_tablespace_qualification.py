"""Native InnoDB storage qualification using only owned tablespaces/datafiles."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MYSQL_PROFILE, _resources
from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier


def qualify(options, output, require_encryption=False):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True})
    cursor=connection.cursor();token=secrets.token_hex(6)
    database='sr_storage_'+token;general='sr_space_'+token+'`é';undo='sr_undo_'+token
    general_created=undo_created=False
    proof={'passed':False,'statements':{},'checks':[]}
    def execute(operation,draft,name,space_type='General'):
        target={'display_name':name,'native':{'engine':'InnoDB','space_type':space_type}}
        request={'resource_kind':'tablespace','operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':{'host':options.get('host','localhost')}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        cursor.execute(statement['source'],statement['parameters'] or None)
        proof['statements'].setdefault(operation,statement['source'])
    def state():
        cursor.execute('SELECT STATE FROM information_schema.INNODB_TABLESPACES WHERE NAME=%s',(undo,))
        row=cursor.fetchone()
        return row[0] if row else None
    def empty_undo():
        for attempt in range(300):
            if state()=='empty':return
            time.sleep(0.1)
        raise AssertionError('Owned undo tablespace did not become natively droppable within observation budget')
    try:
        cursor.execute('SELECT VERSION(),@@innodb_page_size');version,page=cursor.fetchone()
        assert str(version).split('-')[0]=='9.7.0'
        cursor.execute('CREATE DATABASE '+identifier(database))
        for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode=mode
            execute('create',{'name':general,'datafile':"sr_owned_"+token+"_'é.ibd",'file_block_size':int(page),'autoextend_size':4194304,'encryption':'N','engine_attribute':'{"owner":"ScratchRobin qualification"}'},general)
            general_created=True
            cursor.execute('CREATE TABLE '+identifier(database)+'.t(id int PRIMARY KEY) TABLESPACE '+identifier(general)+' ENGINE=InnoDB')
            cursor.execute('INSERT INTO '+identifier(database)+'.t VALUES(42)')
            try:execute('drop',{},general)
            except mysql.connector.Error as error:proof['nonempty_drop_error_code']=error.errno
            else:raise AssertionError('Native nonempty general tablespace unexpectedly dropped')
            execute('alter',{'change':'AUTOEXTEND_SIZE','autoextend_size':8388608},general)
            try:
                execute('alter',{'change':'ENCRYPTION','encryption':'Y'},general)
                cursor.execute('SELECT ENCRYPTION FROM information_schema.INNODB_TABLESPACES WHERE NAME=%s',(general,))
                assert cursor.fetchone()[0]=='Y'
                execute('alter',{'change':'ENCRYPTION','encryption':'N'},general)
                cursor.execute('SELECT ENCRYPTION FROM information_schema.INNODB_TABLESPACES WHERE NAME=%s',(general,))
                assert cursor.fetchone()[0]=='N'
                proof['encryption_qualified']=True
            except mysql.connector.Error as error:
                if require_encryption or error.errno!=3185:raise
                proof['encryption_qualified']=False
                proof['encryption_unavailable_native_error_code']=error.errno
            execute('alter',{'change':'ENGINE_ATTRIBUTE','engine_attribute':'{"owner":"ScratchRobin rediscovered"}'},general)
            renamed=general+'_renamed';execute('rename',{'new_name':renamed},general);general=renamed
            cursor.execute('SELECT AUTOEXTEND_SIZE,SPACE_TYPE FROM information_schema.INNODB_TABLESPACES WHERE NAME=%s',(general,))
            assert cursor.fetchone()==(8388608,'General')
            cursor.execute('SELECT ENGINE_ATTRIBUTE FROM information_schema.TABLESPACES_EXTENSIONS WHERE TABLESPACE_NAME=%s',(general,))
            assert json.loads(cursor.fetchone()[0])=={'owner':'ScratchRobin rediscovered'}
            cursor.execute('SELECT id FROM '+identifier(database)+'.t');assert cursor.fetchone()==(42,)
            resources=_resources(connection,{'route':{}},MYSQL_PROFILE)
            observed = next(row['native'] for row in resources if row['resource_kind']=='tablespace' and row['display_name']==general)
            assert observed['space_type']=='General'
            assert observed['administration']['allowed_operations']==['inspect','alter','rename','drop']
            assert ('ENCRYPTION' in observed['available_tablespace_changes']) == observed['keyring_observed_active']
            assert observed['keyring_observed_active'] == proof['encryption_qualified']
            defaults = [row for row in resources if row['resource_kind']=='tablespace' and row['display_name'] in {'innodb_undo_001','innodb_undo_002'}]
            assert len(defaults)==2 and all(row['native']['administration']['allowed_operations']==['inspect'] for row in defaults)
            cursor.execute('DROP TABLE '+identifier(database)+'.t')
            execute('drop',{},general);general_created=False
        execute('create',{'name':undo,'space_type':'Undo','datafile':'sr_owned_'+token+'.ibu'},undo,'Undo');undo_created=True
        assert state()=='active'
        execute('alter',{'change':'INACTIVE'},undo,'Undo');empty_undo()
        execute('alter',{'change':'ACTIVE'},undo,'Undo');assert state()=='active'
        execute('alter',{'change':'INACTIVE'},undo,'Undo');empty_undo()
        execute('drop',{},undo,'Undo');undo_created=False;assert state() is None
        proof.update(passed=True,checks=['native generated InnoDB create/alter/rename/drop plans','bound Unicode/quoted native datafile path',
            'default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES','native nonempty general-space drop refusal','table data survives native tablespace rename',
            'native autoextension and engine-attribute rediscovery','exact native storage catalog observations','owned undo ACTIVE/INACTIVE/empty/drop lifecycle'])
    finally:
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database))
        if general_created:cursor.execute('DROP TABLESPACE '+identifier(general))
        if undo_created:
            cursor.execute('ALTER UNDO TABLESPACE '+identifier(undo)+' SET INACTIVE ENGINE=InnoDB');empty_undo()
            cursor.execute('DROP UNDO TABLESPACE '+identifier(undo)+' ENGINE=InnoDB')
        cursor.close();connection.close()
        proof['owned_native_tablespaces_and_datafiles_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--require-encryption',action='store_true')
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root,args.require_encryption)
