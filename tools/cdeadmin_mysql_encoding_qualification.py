"""Round-trip mixed native creation encodings through the matching mysql client."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture,identifier
from pgadmin.cdeadmin.providers.mysql_native_encoding import encode_metadata
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata


def qualify(options,container,output):
    output.mkdir(parents=True,exist_ok=True);connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor()
    database='sr_encoding_'+secrets.token_hex(5)+'漢';reader=None;proof={'passed':False}
    command=['docker','exec','-i','-e','MYSQL_PWD',container,'mysql','--user='+options['user'],'--protocol=socket','--default-character-set=utf8mb4','--binary-mode','--batch','--skip-column-names']
    environment={**os.environ,'MYSQL_PWD':options['password']}
    def client(data):
        result=subprocess.run(command,input=data,capture_output=True,env=environment,timeout=30)
        (output/'native-client-stdout.log').write_bytes(result.stdout);(output/'native-client-stderr.log').write_bytes(result.stderr)
        assert result.returncode==0,'Native mysql client failed; see retained diagnostics'
        return result.stdout
    try:
        cursor.execute('SELECT @@server_uuid');server=cursor.fetchone()[0]
        assert client(b'SELECT @@server_uuid;\n').decode().strip()==server
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        cursor.execute('CREATE TABLE t(id int PRIMARY KEY) ENGINE=InnoDB')
        for charset,codec,collation,name,literal in [('latin1','cp1252','latin1_swedish_ci','p_latin', 'é€'),('latin1','cp1252','utf8mb4_bin','p_latin_mixed','é€'),('sjis','shift_jis','sjis_japanese_ci','p_sjis','ソ日本'),('gbk','gbk','gbk_chinese_ci','p_gbk','中文')]:
            connection.sql_mode='NO_BACKSLASH_ESCAPES'
            cursor.execute('SET SESSION character_set_client=%s',(charset,));cursor.execute('SET SESSION collation_connection=%s',(collation,))
            cursor.execute(("CREATE PROCEDURE "+identifier(name)+"() SELECT '"+literal+"' AS native_value").encode(codec))
            connection.set_charset_collation(charset='utf8mb4',collation='utf8mb4_0900_ai_ci')
        observed=capture(connection,database)
        document=build_export(observed['resources'],endpoint_id='ep',target_id='db',generation=observed['generation'],engine='mysql',native_model=True)
        metadata=build_metadata(document);assert metadata['native_encoding_required'] and not metadata['blockers'],metadata['blockers']
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        encoded=encode_metadata(reader,metadata);data=base64.b64decode(encoded['encoded_script']['data_base64']);(output/'native-mixed-encodings.sql').write_bytes(data)
        assert b"'\xe9\x80'" in data and 'ソ日本'.encode('shift_jis') in data and '中文'.encode('gbk') in data
        from copy import deepcopy
        lossy=deepcopy(metadata)
        next(block for block in lossy['statements'] if block['name']=='p_latin')['statement']+=" COMMENT '😀'"
        try:encode_metadata(reader,lossy)
        except ValueError as error:assert 'lose' in str(error)
        else:raise AssertionError('Lossy native encoding produced a downloadable script')
        reader.close();reader=None
        cursor.execute('DROP DATABASE '+identifier(database))
        client(data)
        connection.database=database
        for name,expected in [('p_latin','é€'),('p_latin_mixed','é€'),('p_sjis','ソ日本'),('p_gbk','中文')]:
            cursor.execute('CALL '+identifier(name)+'()');assert cursor.fetchone()==(expected,)
            while cursor.nextset():
                if cursor.description:cursor.fetchall()
        cursor.execute('SELECT ROUTINE_NAME,CHARACTER_SET_CLIENT,COLLATION_CONNECTION FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s ORDER BY ROUTINE_NAME',(database,))
        facts=cursor.fetchall();assert {(row[0],row[1]) for row in facts}=={('p_latin','latin1'),('p_latin_mixed','latin1'),('p_sjis','sjis'),('p_gbk','gbk')}
        proof.update(passed=True,checks=['native encoding/decoding round-trip without imported DDL execution','exact cp1252 Euro, Shift-JIS and GBK bytes in downloaded artifact','fresh matching mysql CLI consumes original binary bytes','Unicode database selected before stored non-UTF8 context','restored routine results retain exact Unicode values','stored client charset and independent collation restored by native script','lossy native conversion refuses artifact generation'],restored_creation_contexts=facts,artifact_sha256=encoded['encoded_script']['sha256'])
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close();proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--mysql-container',required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.mysql_container,args.output_root)
