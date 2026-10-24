"""Qualify native duplicate undo names without changing catalog or source bytes.

Use an owned disposable fixture only. Run the repository DDN prerequisite first.
This gate never promotes the candidate; the builder combines all native gates.
"""
from pathlib import Path
import argparse,json,secrets,subprocess,time
from cdeadmin_mysql_namespace_qualification import captured_sources
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
parser.add_argument('--fixture-image',required=True)
args=parser.parse_args();out=args.output.resolve();pkg=args.package.resolve(strict=True)
if out==ROOT or ROOT in out.parents:raise ValueError('Keep qualification outside source')
out.mkdir(mode=0o700,parents=True);name='sr-undo-recovery-'+secrets.token_hex(6);volumes=[];runtime=None
bootstrap,hashes=captured_sources()
proof={'complete':False,'history_testing':'not run','native_package':json.loads((pkg/'PROVENANCE.json').read_text()),'namespace_source_sha256':hashes};root='/var/backups/undo232';binary='/opt/sr-undo232/bin/xtrabackup'
def run(a,check=True,timeout=240):return subprocess.run(a,capture_output=True,text=True,timeout=timeout,check=check)
def host(*a,check=True):return run(['docker','exec',name,*a],check)
def python(code):
 r=subprocess.run(['docker','exec','-i',name,'/usr/bin/python3','-'],input=code,capture_output=True,text=True,timeout=240)
 if r.returncode:(out/'python-failure.log').write_text(r.stdout+r.stderr);raise RuntimeError('Owned native host step failed')
 return json.loads(r.stdout)
def sql(statement,socket='/var/run/mysqld/mysqld.sock'):
 return host('/usr/bin/mysql','--user=root','--socket='+socket,'--default-character-set=utf8mb4','--batch','--skip-column-names','-e',statement).stdout
def native(stage,args):
 r=host(binary,'--no-defaults',*args,check=False);(out/(stage+'.log')).write_text(r.stdout+r.stderr);proof[stage+'_return_code']=r.returncode
 if r.returncode:raise RuntimeError('Native '+stage+' failed')
def source_hashes():
 return python("from pathlib import Path;import hashlib,json;roots=[Path('/var/lib/mysql'),Path('/var/lib/sr-undo-a'),Path('/var/lib/sr-undo-b')];print(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for root in roots for f in sorted(root.rglob('*')) if f.is_file()}))")
try:
 run(['docker','run','--rm','-d','--cap-add=SYS_ADMIN','--name',name,'--mount',f'type=bind,source={pkg},target=/opt/sr-undo232,readonly','-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','--entrypoint','/bin/bash',args.fixture_image,'-c','mkdir -p /var/lib/sr-undo-a /var/lib/sr-undo-b && chown mysql:mysql /var/lib/sr-undo-a /var/lib/sr-undo-b && exec /bin/bash /opt/physical-start.sh "$@"','--','mysqld','--server-id=232','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin=undo-source','--innodb-directories=/var/lib/sr-undo-a;/var/lib/sr-undo-b'])
 volumes=[m['Name'] for m in json.loads(run(['docker','inspect','--format','{{json .Mounts}}',name]).stdout) if m['Type']=='volume']
 for _ in range(180):
  if host('/usr/bin/mysqladmin','--user=root','--protocol=TCP','--host=127.0.0.1','ping',check=False).returncode==0:break
  time.sleep(1)
 else:raise RuntimeError('Owned native source not ready')
 sql("CREATE UNDO TABLESPACE sr_duplicate_a ADD DATAFILE '/var/lib/sr-undo-a/same.ibu';CREATE UNDO TABLESPACE sr_duplicate_b ADD DATAFILE '/var/lib/sr-undo-b/same.ibu';CREATE DATABASE duplicate232;CREATE TABLE duplicate232.t(id INT PRIMARY KEY,note VARCHAR(80),b LONGBLOB);INSERT INTO duplicate232.t VALUES(1,'native duplicate undo 雪',X'00FF')")
 proof['source_undo_catalog']=sql("SELECT FILE_ID,FILE_NAME,TABLESPACE_NAME FROM information_schema.FILES WHERE FILE_TYPE='UNDO LOG' ORDER BY FILE_ID DESC")
 source_rows=[line.split('\t') for line in proof['source_undo_catalog'].strip().splitlines()]
 storage_request={'binding':{'datadir':'/var/lib/mysql'},'isolate_external_paths':True,'source_storage':{
  'variables':{'innodb_data_home_dir':'','innodb_data_file_path':'ibdata1:12M:autoextend','innodb_undo_directory':'./','innodb_directories':'/var/lib/sr-undo-a;/var/lib/sr-undo-b'},
  'files':[{'file_name':'./ibdata1','tablespace_name':'innodb_system','file_type':'TABLESPACE'}]+[
   {'file_name':row[1],'tablespace_name':row[2],'file_type':'UNDO LOG','undo_number':(0xFFFFFFEF-int(row[0]))%127+1} for row in source_rows]}}
 host('mkdir','-p',root)
 native('backup',['--backup','--host=127.0.0.1','--user=root','--ssl-mode=REQUIRED','--datadir=/var/lib/mysql','--target-dir='+root+'/full','--parallel=2'])
 proof['backed_up_undo_files']=python("from pathlib import Path;import json;p=Path('"+root+"/full');print(json.dumps(sorted(f.name for f in p.iterdir() if f.name.startswith(('undo_','sr-undo-')))))")
 assert proof['backed_up_undo_files']==['sr-undo-3.ibu','sr-undo-4.ibu','undo_001','undo_002']
 proof['storage_geometry']=python(bootstrap+"\nfrom pathlib import Path\np=sys.modules['_cdeadmin_physical_worker'];g=p.geometry_module();value=g.from_source("+repr(storage_request)+",filesystem=True,undo_naming=g.UNDO_NAMING);g.capture("+repr(storage_request)+",Path('"+root+"/full'),reviewed=value);print(json.dumps(value))")
 python("import shutil,json;shutil.copytree('"+root+"/full','"+root+"/prepared');print(json.dumps(True))")
 python(bootstrap+"\nfrom pathlib import Path\ng=sys.modules['_cdeadmin_physical_worker'].geometry_module();g.stage_prepare(Path('"+root+"'),Path('"+root+"/prepared'));print(json.dumps(True))")
 native('prepare',['--prepare','--target-dir='+root+'/prepared','--use-memory=268435456','--innodb-data-file-path=ibdata1:12M:autoextend','--innodb-data-home-dir='+root+'/prepared','--innodb-undo-directory='+root+'/prepared'])
 python(bootstrap+"\nfrom pathlib import Path\ng=sys.modules['_cdeadmin_physical_worker'].geometry_module();g.restore_prepare(Path('"+root+"'),Path('"+root+"/prepared'));print(json.dumps(True))")
 host('mkdir','-p',root+'/copied')
 native('copy-back',['--copy-back','--target-dir='+root+'/prepared','--datadir='+root+'/copied','--innodb-data-home-dir='+root+'/copied','--innodb-data-file-path='+root+'/copied/ibdata1:12M:autoextend','--innodb-undo-directory='+root+'/undo-copy-back','--innodb-log-group-home-dir='+root+'/copied'])
 proof['copied_undo_files']=python("from pathlib import Path;import json;p=Path('"+root+"/undo-copy-back');print(json.dumps(sorted(f.name for f in p.iterdir() if f.name.startswith(('undo_','sr-undo-')))))")
 context=python(bootstrap+"\nfrom pathlib import Path\np=sys.modules['_cdeadmin_physical_worker'];g=p.geometry_module();paths=p.paths_module();value="+repr(proof['storage_geometry'])+";request="+repr(storage_request)+";request['phase']='copy_back';context=paths.admission(request,[],storage=value);g.finish_copy_back(Path('"+root+"'),Path('"+root+"/prepared'),Path('"+root+"/copied'),value,context);print(json.dumps(context))")
 host('/usr/bin/mysqladmin','--user=root','--socket=/var/run/mysqld/mysqld.sock','shutdown');before=source_hashes()
 runtime_plan=python(bootstrap+"\nfrom pathlib import Path\np=sys.modules['_cdeadmin_physical_worker'];aliases,options=p.paths_module().runtime(Path('"+root+"'),Path('"+root+"/copied'),"+repr(context)+");print(json.dumps({'aliases':aliases,'options':options}))")
 aliases=runtime_plan['aliases']
 args=['/usr/sbin/mysqld','--no-defaults','--persisted-globals-load=OFF','--upgrade=NONE','--datadir=/var/lib/mysql','--innodb-data-home-dir=/var/lib/mysql','--innodb-data-file-path=ibdata1:12M:autoextend','--innodb-undo-directory=/var/lib/mysql','--innodb-directories=/var/lib/sr-undo-a;/var/lib/sr-undo-b','--socket='+root+'/recovered.sock','--pid-file='+root+'/recovered.pid','--log-error='+root+'/recovered-error.log','--tmpdir='+root,'--user=root','--mysqlx=OFF','--skip-networking','--skip-replica-start','--event-scheduler=DISABLED','--server-id=2321','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin='+root+'/private-bin','--innodb-buffer-pool-size=67108864']
 runtime=python(bootstrap+"\nfrom pathlib import Path\np=sys.modules['_cdeadmin_physical_worker'];r=sys.modules['_cdeadmin_recovery_worker'];ns=sys.modules['_cdeadmin_physical_paths'];directory=Path('"+root+"');view=ns.activate(directory,"+repr(aliases)+",directory=directory)\nwith (directory/'recovered.stdout').open('w') as out:\n child=p.subprocess.Popen("+repr(args)+",stdout=out,stderr=p.subprocess.STDOUT,start_new_session=True)\ntry:process=r.birth(child.pid,{'path':'/usr/sbin/mysqld','sha256':p.host.file_hash(Path('/usr/sbin/mysqld'))})\nexcept BaseException:child.kill();child.wait();raise\nprint(json.dumps({'process':process,'view':view}))")
 for _ in range(120):
  if host('/usr/bin/mysqladmin','--user=root','--socket='+root+'/recovered.sock','ping',check=False).returncode==0:break
  time.sleep(.25)
 else:(out/'recovered-error.log').write_text(host('cat',root+'/recovered-error.log',check=False).stdout);raise RuntimeError('Owned recovered instance not ready')
 proof['recovered_rows']=sql('SELECT id,note,HEX(b) FROM duplicate232.t',root+'/recovered.sock');assert proof['recovered_rows']=='1\tnative duplicate undo 雪\t00FF\n'
 proof['recovered_undo_catalog']=sql("SELECT FILE_ID,FILE_NAME,TABLESPACE_NAME FROM information_schema.FILES WHERE FILE_TYPE='UNDO LOG' ORDER BY FILE_ID DESC",root+'/recovered.sock');assert proof['recovered_undo_catalog']==proof['source_undo_catalog']
 sql("INSERT INTO duplicate232.t VALUES(2,'private duplicate recovered write',X'0001');COMMIT",root+'/recovered.sock');assert sql('SELECT COUNT(*) FROM duplicate232.t',root+'/recovered.sock')=='2\n'
 proof['independent_filesystem_observation']=python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_physical_paths'].observe("+str(runtime['process']['pid'])+','+repr(runtime['view'])+')))' )
 assert source_hashes()==before;proof['original_source_files_unchanged']=True
 assert python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].stop("+repr(runtime['process'])+')))' )
 for _ in range(120):
  if not python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].present("+repr(runtime['process'])+')))'):break
  time.sleep(.1)
 else:raise RuntimeError('Original recovery did not end')
 runtime=None;proof['original_recovery_end_observed']=True;proof['complete']=True
finally:
 if runtime:
  try:python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].stop("+repr(runtime['process'])+')))')
  except Exception:pass
 r=run(['docker','logs',name],False);(out/'source.log').write_text(r.stdout+r.stderr)
 run(['docker','rm','-fv',name],False)
 for volume in volumes:run(['docker','volume','rm',volume],False)
 proof['owned_container_and_data_removed']=run(['docker','inspect',name],False).returncode!=0 and all(run(['docker','volume','inspect',v],False).returncode!=0 for v in volumes)
 (out/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k not in {'native_package','namespace_source_sha256'}},indent=2))
