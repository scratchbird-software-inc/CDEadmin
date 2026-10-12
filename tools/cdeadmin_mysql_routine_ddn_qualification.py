"""Qualify native stored-routine DDN CREATE/characteristic ALTER/confirmed DROP."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture,identifier
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor();reader=None
    database='sr_routine_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    def document():
        current=capture(connection,database)
        return read_catalog(json.dumps(build_export(current['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=current['generation'])['snapshot']),engine='mysql')
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            for kind in ('procedure','function'):
                connection.sql_mode=mode
                cursor.execute('CREATE '+kind.upper()+' r() '+('RETURNS INT DETERMINISTIC BEGIN RETURN 42; END' if kind=='function' else 'BEGIN SELECT 42 AS value; END'))
                desired=document();key=next(key for key,row in desired['rows'].items() if row['kind']==kind)
                cursor.execute('DROP '+kind.upper()+' r');baseline=document()
                for action in ('create','alter','drop'):
                    if action!='create':
                        baseline=document();desired=deepcopy(baseline)
                        desired['rows'][key]['native']['mysql_change']=({'action':'alter-characteristics','sql_security':'INVOKER','data_access':'READS SQL DATA','comment':"a'b\\c"} if action=='alter' else {'action':'drop','confirmation':'r'})
                    preview=plan(baseline,desired,baseline);assert preview['ready_for_review'],preview
                    preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
                    if action=='create':
                        invalid=deepcopy(preview);invalid['operations'][0]['source']=invalid['operations'][0]['source'].replace('42','FROM')
                        rejected=validate(reader,invalid);assert not rejected['native_grammar_validated'],rejected
                    cursor.execute('SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',(database,'r'))
                    assert cursor.fetchone()[0]==(0 if action=='create' else 1)
                    receipt=applications.review(preview,baseline,desired,'owner','binding','target')
                    request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                    result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                    assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                    assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                    if action=='alter':
                        cursor.execute('SELECT SECURITY_TYPE,SQL_DATA_ACCESS,ROUTINE_COMMENT FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s AND ROUTINE_NAME=%s',(database,'r'))
                        assert cursor.fetchone()==('INVOKER','READS SQL DATA',"a'b\\c")
                    if action!='drop':
                        cursor.execute('SELECT r()' if kind=='function' else 'CALL r()');assert cursor.fetchall()==[(42,)]
                        while cursor.nextset():pass
                    proof['checks'].append({'sql_mode':mode,'kind':kind,'operation':action,'native_validation':preview['native_validation'],
                        'native_body_preserved':True,'restart_no_replay':True})
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)
