"""Native retained-session extension sources, installation, loading and receipts."""
import argparse
import functools
import gzip
import hashlib
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,signed_extension):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
    from pgadmin.cdeadmin.providers.duckdb import extension_actions as module
    output=Path(output).resolve();signed_extension=Path(signed_extension).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    if duckdb.__version__!='1.5.2' or not signed_extension.is_file():raise ValueError('Native DuckDB 1.5.2 and an actual signed httpfs binary are required')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    binary=signed_extension.read_bytes();proof={'complete':False,'history_testing':'not run','full_product_complete':False,
        'native_version':duckdb.__version__,'signed_extension_sha256':hashlib.sha256(binary).hexdigest(),'checks':[],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            'tools/cdeadmin_duckdb_extension_actions_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/extension_actions.py',
            'web/pgadmin/cdeadmin/providers/duckdb/driver.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py']}}
    repository=output/'repository';repository.mkdir();(repository/'qualified.txt').write_text('native httpfs execution verified')
    platform=duckdb.connect().execute('PRAGMA platform').fetchone()[0]
    compressed=gzip.compress(binary,compresslevel=1)
    for prefix in [Path('v1.5.2')/platform,Path('httpfs')/'13e18b3'/'v1.5.2'/platform]:
        directory=repository/prefix;directory.mkdir(parents=True)
        (directory/'httpfs.duckdb_extension').write_bytes(binary);(directory/'httpfs.duckdb_extension.gz').write_bytes(compressed)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            proof.setdefault('repository_requests',[]).append(self.path)
            super().do_GET()
    http=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(repository)))
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(http.server_port)
    try:
        for memory in [False,True]:
            directory=output/('memory' if memory else 'file');directory.mkdir();source=directory/'httpfs.duckdb_extension';source.write_bytes(binary)
            configuration={'extension_directory':str(directory/'cache'),'autoload_known_extensions':False,'autoinstall_known_extensions':False}
            route={'database':':memory:' if memory else str(directory/'owned.duckdb'),'filesystem_root':str(output),'allow_memory':memory,'config':configuration}
            client=_create_client();handle=client.open_session({'route':route})
            def review(**draft):return module.action(client,handle,route,{'operation':'review','draft':{'action':'install','extension_name':'httpfs',**draft}})
            def apply(record):
                request={'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],'confirmation':record['extension_name'],'confirmed':True}
                result=module.action(client,handle,route,request)
                with patch.object(module,'inventory',side_effect=AssertionError('completed mutation replayed')):
                    assert module.action(client,handle,route,request)==result
                return result
            try:
                handle.execute('CREATE TABLE pending(id INT)');client.control_transaction(handle,'commit')
                handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private(id INT)')
                installed=apply(review(source_kind='FILE',source=str(source)))
                assert installed['state']=='acknowledged' and installed['rediscovery_verified'],installed
                replaced=apply(review(force=True,repository_kind='URL',repository=url,version='13e18b3'))
                assert replaced['state']=='acknowledged' and replaced['rediscovery_verified'] and replaced['loaded_code_replaced'] is False,replaced
                loaded=apply(review(action='load',extension_name='http'))
                assert loaded['extension_name']=='httpfs'
                assert loaded['state']=='acknowledged' and loaded['rediscovery_verified'],loaded
                assert handle.execute('SELECT content FROM read_text(?)',(url+'/qualified.txt',)).fetchall()==[('native httpfs execution verified',)]
                assert handle.execute('SELECT * FROM pending').fetchall()==[(42,)]
                assert handle.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary AND table_name='private'").fetchone()==(1,)
                handle.rollback();assert handle.execute('SELECT * FROM pending').fetchall()==[]
                assert next(row for row in module.inventory(handle) if row['extension_name']=='httpfs')['loaded']
                local_repository=apply(review(force=True,repository_kind='DIRECTORY',repository=str(repository)))
                assert local_repository['state']=='acknowledged' and local_repository['rediscovery_verified'],local_repository
                stale=review(action='load');handle.execute('SET autoload_known_extensions=true')
                assert apply(stale)['native_dispatched'] is False;handle.execute('SET autoload_known_extensions=false')
                stale=review(action='load',source_kind='FILE',source=str(source));source.write_bytes(b'changed source')
                assert apply(stale)['native_dispatched'] is False;source.write_bytes(binary)
                corrupt=directory/'broken.duckdb_extension';corrupt.write_bytes(b'invalid native extension')
                refused=apply(review(action='load',extension_name='broken',source_kind='FILE',source=str(corrupt)))
                assert not refused['native_acknowledged'] and refused['state'] in {'refused','unknown_outcome'},refused
                proof['checks'].append({'root':'memory' if memory else 'file','signed_local_install_and_original_session_load_verified':True,
                    'native_httpfs_execution_verified':True,'public_repository_version_force_and_directory_verified':True,
                    'pending_rows_and_temporary_objects_preserved':True,'loaded_code_and_installed_files_survive_database_rollback':True,
                    'stale_source_and_native_policy_refused_before_dispatch':True,'native_corrupt_binary_refusal_state':refused['state'],
                    'one_use_receipts_never_replay':True})
            finally:client.close()
        proof['complete']=True
    finally:
        http.shutdown();thread.join(timeout=10);http.server_close()
        (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--signed-extension',required=True,type=Path);args=parser.parse_args();qualify(args.evidence,args.signed_extension)
