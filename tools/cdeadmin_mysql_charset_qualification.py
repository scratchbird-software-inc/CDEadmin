"""Native MySQL client/source/parameter/result charset changes; no history."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(output):
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_native_editor_gate import provider
    from pgadmin.cdeadmin.providers.mysql_family.mysql_values import Cursor
    output=Path(output).resolve()
    if ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'failures':[],'history_testing':'not run','source_sha256':{
        str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),
            ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_connections.py',ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_values.py',ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_charsets.py']}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            observer=_root_connection('mysql',route['port']);observer.autocommit=True;oracle=observer.cursor()
            oracle.execute('CREATE DATABASE sr_charsets');oracle.execute('CREATE TABLE sr_charsets.pending(id INTEGER PRIMARY KEY)');oracle.execute('CREATE TABLE sr_charsets.bulk(id INTEGER PRIMARY KEY,body TEXT CHARACTER SET utf8mb4)')
            for pure in (True,False):
                for charset,text in [('utf8mb4','Unicode 雪😀'),('latin1','é £ €'),('cp1251','Ж Ю'),('gb18030','雪😀'),('utf8mb4','Unicode 雪😀')]:
                    for operation in ('literal','parameter'):
                        instance=connection=cursor=None
                        try:
                            instance,native_route=provider('mysql',{**route,'use_pure':pure});connection=instance.client._connect({'route':native_route})
                            cursor=Cursor(connection);cursor.execute('SET NAMES '+charset)
                            statement="SELECT '"+text+"'" if operation=='literal' else 'SELECT %s'
                            cursor.execute(statement,*(() if operation=='literal' else ((text,),)))
                            actual=cursor.fetchone()[0];assert actual==text,(actual,text)
                            proof['checks'].append({'interface':'pure' if pure else 'c','charset':charset,'operation':operation,'passed':True})
                        except Exception as error:
                            proof['failures'].append({'interface':'pure' if pure else 'c','charset':charset,'operation':operation,'error_type':type(error).__name__,'detail':str(error)})
                        finally:
                            if cursor is not None:
                                try:cursor.close()
                                except Exception:pass
                            if connection is not None:connection.close()
                            if instance is not None:instance.client.close()
            for pure in (True,False):
                instance=connection=cursor=None
                label='pure' if pure else 'c'
                try:
                    instance,native_route=provider('mysql',{**route,'use_pure':pure});connection=instance.client._connect({'route':native_route})
                    cursor=Cursor(connection);cursor.execute('INSERT INTO sr_charsets.pending VALUES(%s)',(1,))
                    for charset,text in [('latin1','é £ €'),('cp1251','Ж Ю'),('gb18030','雪😀'),('utf8mb4','雪😀')]:
                        for mode in ('NO_BACKSLASH_ESCAPES',''):
                            cursor.execute('SET SESSION sql_mode=%s',(mode,));cursor.execute('SET NAMES '+charset)
                            value=text+" ' \\ "+'\x00';binary=b"\x00\xff'\\\r\n"
                            alias=text.replace('😀','')
                            cursor.execute('SELECT %s AS `'+alias+'`,CAST(%s AS BINARY) AS payload',(value,binary));row=cursor.fetchone()
                            assert row[0]==value,(charset,mode,row[0]);assert base64.b64decode(row[1]['data'])==binary,row
                            assert cursor.description[0][0]==text.replace('😀',''),cursor.description
                            proof['checks'].append({'interface':label,'charset':charset,'mode':mode,'operation':'retained-native-mode-literals-parameters-and-result-names','passed':True})
                        cursor.execute('SET character_set_results=NULL')
                        cursor.execute('SELECT _latin1 0x80e9 AS a,_utf8mb4 0xe99baaf09f9880 AS b')
                        assert cursor.fetchone()==('€é','雪😀')
                        proof['checks'].append({'interface':label,'charset':charset,'operation':'native-results-null-preserves-per-column-charsets','passed':True})
                        cursor.execute("SET character_set_results='utf8mb4'")
                        cursor.execute('SELECT %s AS `'+text.replace('😀','')+'`',(text,));assert cursor.fetchone()==(text,)
                        assert cursor.description[0][0]==text.replace('😀',''),cursor.description
                        proof['checks'].append({'interface':label,'charset':charset,'operation':'different-native-source-and-result-charsets','passed':True})
                        oracle.execute('SELECT COUNT(*) FROM sr_charsets.pending');assert oracle.fetchone()[0]==0
                    cursor.execute('SET NAMES utf8mb4')
                    all_bytes=bytes(range(256))
                    cursor.execute('SELECT CONVERT(_latin1 0x'+all_bytes.hex()+' USING utf8mb4) AS native_latin1')
                    native_latin=cursor.fetchone()[0]
                    assert native_latin.encode('cdeadmin_mysql_latin1')==all_bytes
                    assert all_bytes.decode('cdeadmin_mysql_latin1')==native_latin
                    proof['checks'].append({'interface':label,'operation':'all-256-native-latin1-code-points-roundtrip','passed':True})
                    cursor.execute('SET NAMES latin1')
                    bulk=connection.cursor()
                    try:
                        bulk.executemany('INSERT INTO sr_charsets.bulk VALUES(%s,%s)',[(1,'€é'),(2,'£')])
                        bulk.execute('SELECT body FROM sr_charsets.bulk ORDER BY id');assert bulk.fetchall()==[('€é',),('£',)]
                    finally:bulk.close()
                    proof['checks'].append({'interface':label,'operation':'native-latin1-euro-bulk-binding','passed':True})
                    cursor.execute('SET NAMES utf8mb4')
                    prepared=connection.cursor(prepared=True)
                    try:
                        prepared.execute('SELECT %s AS native_prepared',('雪😀',));assert prepared.fetchone()==('雪😀',)
                    finally:prepared.close()
                    proof['checks'].append({'interface':label,'operation':'native-binary-prepared-cursor-preserved','passed':True})
                    connection.rollback();oracle.execute('SELECT COUNT(*) FROM sr_charsets.pending');assert oracle.fetchone()[0]==0
                    proof['checks'].append({'interface':label,'operation':'pending-work-and-rollback-preserved','passed':True})
                    previous=None
                    for lease_index in range(2):
                        lease=instance.client._connect({'route':{**native_route,'pool_name':'charset-reset','pool_size':1,'pool_reset_session':True}})
                        try:
                            query=Cursor(lease);query.execute('SELECT CONNECTION_ID()');identity=query.fetchone()[0]
                            if previous is not None:assert identity==previous
                            previous=identity
                            for charset,text in [('latin1','€é'),('gb18030','雪😀')]:
                                query.execute('SET NAMES '+charset);query.execute('SELECT %s AS result',(text,));assert query.fetchone()==(text,)
                            query.close()
                        finally:lease.close()
                    proof['checks'].append({'interface':label,'operation':'native-pool-reset-and-reborrow-keeps-charset-observations','passed':True})
                except Exception as error:
                    proof['failures'].append({'interface':label,'operation':'retained-and-pooled-charsets','error_type':type(error).__name__,'detail':str(error)})
                    (output/(label+'-retained-failure.log')).write_text(traceback.format_exc())
                finally:
                    if cursor is not None:
                        try:cursor.close()
                        except Exception:pass
                    if connection is not None:connection.close()
                    if instance is not None:instance.client.close()
            oracle.close();observer.close()
        proof['owned_server_stopped']=owned['owned_server_stopped'];proof['complete']=not proof['failures'] and owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
    if not proof['complete']:raise RuntimeError('Native charset checks failed; every case retained')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args();qualify(args.evidence)
