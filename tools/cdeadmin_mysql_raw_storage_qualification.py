"""Qualify the pinned native raw reader against an owned, autocleared loop device.

Requires a disposable MySQL physical fixture with SSH startup support. Never
select an existing host device. The native server initializes only this script's
atomically allocated loop device; backup descriptors must be read-only.
"""
from pathlib import Path
import argparse,hashlib,json,secrets,subprocess,time
from cdeadmin_mysql_namespace_qualification import captured_sources
ROOT=Path(__file__).resolve().parents[1]
CONTROLLER=r'''
import ctypes,fcntl,json,os,pathlib,pwd,signal,stat,subprocess,time
class Info(ctypes.Structure):
 _fields_=[('device',ctypes.c_uint64),('inode',ctypes.c_uint64),('rdevice',ctypes.c_uint64),('offset',ctypes.c_uint64),('sizelimit',ctypes.c_uint64),('number',ctypes.c_uint32),('encryption_type',ctypes.c_uint32),('key_size',ctypes.c_uint32),('flags',ctypes.c_uint32),('filename',ctypes.c_char*64),('cryptname',ctypes.c_char*64),('key',ctypes.c_ubyte*32),('init',ctypes.c_uint64*2)]
class Config(ctypes.Structure):_fields_=[('fd',ctypes.c_uint32),('block_size',ctypes.c_uint32),('info',Info),('reserved',ctypes.c_uint64*8)]
assert ctypes.sizeof(Info)==232 and ctypes.sizeof(Config)==304
root=pathlib.Path('/var/backups/raw231');root.mkdir(parents=True)
control=block=backing=None;attached=False;child=None
signal.signal(signal.SIGTERM,lambda *_args:(_ for _ in ()).throw(SystemExit(0)))
try:
 os.mknod('/dev/sr-loop-control',stat.S_IFCHR|0o600,os.makedev(10,237));control=os.open('/dev/sr-loop-control',os.O_RDWR)
 index=fcntl.ioctl(control,0x4C82,0);os.mknod('/dev/sr-owned-loop',stat.S_IFBLK|0o600,os.makedev(7,index));block=os.open('/dev/sr-owned-loop',os.O_RDWR)
 backing=os.open('/tmp/sr-owned-system.img',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(backing,48*1024*1024)
 value=Config();value.fd=backing;value.info.flags=4;value.info.filename=b'/tmp/sr-owned-system.img'
 fcntl.ioctl(block,0x4C0A,bytes(value));attached=True
 account=pwd.getpwnam('mysql');os.chown('/dev/sr-owned-loop',account.pw_uid,account.pw_gid);os.chmod('/dev/sr-owned-loop',0o660)
 (root/'loop.json').write_text(json.dumps({'loop_index':index,'autoclear':True,'owned_backing_file':'/tmp/sr-owned-system.img','bytes':48*1024*1024}))
 child=subprocess.Popen(['/bin/bash','/opt/physical-start.sh','mysqld','--datadir=/sr-source225/mysql','--innodb-data-home-dir=','--innodb-data-file-path=/dev/sr-owned-loop:32Mnewraw','--server-id=231','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin=raw'])
 while child.poll() is None:time.sleep(.5)
finally:
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=15)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 if attached:
  try:fcntl.ioctl(block,0x4C01,0)
  except OSError:pass  # AUTOCLEAR also releases the owned loop on last close.
 for fd in (backing,block,control):
  if fd is not None:os.close(fd)
'''


def controller_source(specification,*,multiple=False):
    prefix='/dev/sr-owned-first:12Mnewraw;' if multiple else ''
    value=CONTROLLER.replace('/dev/sr-owned-loop:32Mnewraw',prefix+'/dev/sr-owned-loop:'+specification+'newraw')
    if not multiple:return value
    value=value.replace('control=block=backing=None;', 'extra_block=extra_backing=None;extra_attached=False\ncontrol=block=backing=None;')
    extra='''
 extra_index=fcntl.ioctl(control,0x4C82,0)
 os.mknod('/dev/sr-owned-first',stat.S_IFBLK|0o600,os.makedev(7,extra_index))
 extra_block=os.open('/dev/sr-owned-first',os.O_RDWR)
 extra_backing=os.open('/tmp/sr-owned-first.img',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
 os.ftruncate(extra_backing,20*1024*1024)
 first_config=Config();first_config.fd=extra_backing;first_config.info.flags=4;first_config.info.filename=b'/tmp/sr-owned-first.img'
 fcntl.ioctl(extra_block,0x4C0A,bytes(first_config));extra_attached=True
 os.chown('/dev/sr-owned-first',account.pw_uid,account.pw_gid);os.chmod('/dev/sr-owned-first',0o660)
 metadata=json.loads((root/'loop.json').read_text())
 metadata['additional_loops']=[{'loop_index':extra_index,'bytes':20*1024*1024,'owned_backing_file':'/tmp/sr-owned-first.img'}]
 (root/'loop.json').write_text(json.dumps(metadata))
'''
    cleanup='''
 if extra_attached:
  try:fcntl.ioctl(extra_block,0x4C01,0)
  except OSError:pass
 for fd in (extra_backing,extra_block):
  if fd is not None:os.close(fd)
'''
    return value.replace(' child=subprocess.Popen',extra+' child=subprocess.Popen').replace(' if attached:',cleanup+' if attached:')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixture-image',required=True)
    parser.add_argument('--admit-package',action='store_true')
    parser.add_argument('--autoextend',action='store_true')
    parser.add_argument('--fixed-receipt',type=Path)
    parser.add_argument('--auto-receipt',type=Path)
    parser.add_argument('--multiple',action='store_true')
    options=parser.parse_args();pkg=options.package.resolve(strict=True);out=options.output.resolve()
    if out==ROOT or ROOT in out.parents:raise ValueError('Keep qualification output outside source')
    assert (pkg/'PROVENANCE.json').is_file(),'Package the completed native candidate first'
    out.mkdir(mode=0o700,parents=True,exist_ok=False);name='sr-native-raw-'+secrets.token_hex(6)
    specification='32M'+(':autoextend:max:48M' if options.autoextend else '')
    controller=controller_source(specification,multiple=options.multiple)
    backup_specification=('sr-owned-first:12M;' if options.multiple else '')+'sr-owned-loop:'+specification
    recovered_specification=('/dev/sr-owned-first:12M;' if options.multiple else '')+'/dev/sr-owned-loop:'+specification
    bootstrap,hashes=captured_sources()
    proof={'complete':False,'history_testing':'not run','scope':'Native raw reader extent/capacity, prepare/copy-back, SQL recovery, process isolation and unchanged original source qualification','owned_container_and_data_removed':False,'native_package':json.loads((pkg/'PROVENANCE.json').read_text()),'namespace_source_sha256':hashes,'controller_sha256':hashlib.sha256(controller.encode()).hexdigest()};loop=None;runtime=None;volumes=[]
    def run(args,check=True,timeout=240):
     r=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
     if check and r.returncode:raise RuntimeError(r.stderr[-2500:])
     return r
    def host(*args,check=True,timeout=240):return run(['docker','exec',name,*args],check,timeout)
    def python(code):
     r=subprocess.run(['docker','exec','-i',name,'python3','-'],input=code,text=True,capture_output=True,timeout=240)
     if r.returncode:(out/'python-failure.log').write_text(r.stdout+r.stderr);raise RuntimeError('Native owned host step failed')
     return json.loads(r.stdout)
    def sql(statement,sock='/var/run/mysqld/mysqld.sock'):
     return host('/usr/bin/mysql','--user=root','--socket='+sock,'--default-character-set=utf8mb4','--batch','--skip-column-names','-e',statement).stdout
    utility='/opt/sr-raw231/bin/xtrabackup';root='/var/backups/raw231'
    def native(stage,args):
     r=host(utility,*args,check=False);(out/(stage+'.log')).write_text(r.stdout+r.stderr)
     proof[stage+'_return_code']=r.returncode
     if r.returncode:raise RuntimeError('Native '+stage+' failed')
    def source_hashes():
     return python("from pathlib import Path;import hashlib,json;p=Path('/sr-source225/mysql');print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file()}))")
    def block_hash():
     files=['/tmp/sr-owned-system.img']+(['/tmp/sr-owned-first.img'] if options.multiple else [])
     return python("from pathlib import Path;import hashlib,json;files="+repr(files)+";print(json.dumps({name:{'bytes':Path(name).stat().st_size,'sha256':hashlib.sha256(Path(name).read_bytes()).hexdigest()} for name in files}))")
    try:
     run(['docker','run','--rm','-d','--cap-add=SYS_ADMIN','--device-cgroup-rule=c 10:237 rwm','--device-cgroup-rule=b 7:* rwm','--mount',f'type=bind,source={pkg},target=/opt/sr-raw231,readonly','--name',name,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','--entrypoint','/usr/bin/python3',options.fixture_image,'-c',controller])
     volumes=[m['Name'] for m in json.loads(run(['docker','inspect','--format','{{json .Mounts}}',name]).stdout) if m['Type']=='volume']
     for _ in range(180):
      if host('/usr/bin/mysqladmin','--user=root','--protocol=TCP','--host=127.0.0.1','ping',check=False).returncode==0:break
      if run(['docker','inspect','--format','{{.State.Running}}',name],False).stdout.strip()!='true':raise RuntimeError('Owned raw source exited')
      time.sleep(1)
     else:raise RuntimeError('Owned raw source not ready')
     loop=json.loads(host('cat',root+'/loop.json').stdout);proof['owned_loop']=loop
     proof['source_variables']=sql('SELECT @@version,@@innodb_data_file_path,@@datadir,@@gtid_mode')
     sql("CREATE DATABASE raw231;CREATE TABLE raw231.t(id INT PRIMARY KEY,note VARCHAR(80),b LONGBLOB) TABLESPACE=innodb_system;INSERT INTO raw231.t VALUES(1,'native raw extent 雪',X'00FF')")
     if options.autoextend:
      payload_mib=50 if options.multiple else 40
      sql("INSERT INTO raw231.t VALUES(3,'native grown extent',REPEAT('x',"+str(payload_mib)+"*1024*1024))")
      proof['source_system_payload']=sql('SELECT LENGTH(b),SHA2(b,256) FROM raw231.t WHERE id=3')
      assert proof['source_system_payload'].startswith(str(payload_mib*1024*1024)+'\t')
     sql('SET GLOBAL innodb_max_dirty_pages_pct=0')
     for _ in range(300):
      if int(sql("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_dirty'").split('\t')[-1])==0:break
      time.sleep(.1)
     else:raise RuntimeError('Owned raw source did not flush its system-space data')
     proof['source_system_total_extent_bytes']=int(sql("SELECT TOTAL_EXTENTS*EXTENT_SIZE FROM information_schema.FILES WHERE TABLESPACE_NAME='innodb_system' AND FILE_NAME='/dev/sr-owned-loop'"))
     proof['source_system_extent_bytes']=proof['source_system_total_extent_bytes']-(12*1024*1024 if options.multiple else 0)
     assert (32*1024*1024<proof['source_system_extent_bytes']<=48*1024*1024) if options.autoextend else proof['source_system_extent_bytes']==32*1024*1024
     backup=[utility,'--backup','--host=127.0.0.1','--user=root','--ssl-mode=REQUIRED','--datadir=/sr-source225/mysql','--target-dir='+root+'/full','--parallel=1','--read-buffer-size=1048576','--throttle=8']
     proof['backup']=python("from pathlib import Path;import json,os,stat,subprocess,time\ncommand="+repr(backup)+"\np=Path('"+root+"/backup.log');modes=set()\nwith p.open('w') as out:\n child=subprocess.Popen(command,stdout=out,stderr=subprocess.STDOUT)\n while child.poll() is None:\n  folder=Path('/proc')/str(child.pid)/'fd'\n  for fd in list(folder.iterdir()) if folder.exists() else []:\n   try:\n    if stat.S_ISBLK(fd.stat().st_mode):\n     flags=next(x.split()[1] for x in (fd.parent.parent/'fdinfo'/fd.name).read_text().splitlines() if x.startswith('flags:'));modes.add(int(flags,8)&os.O_ACCMODE)\n   except (FileNotFoundError,ProcessLookupError):pass\n  time.sleep(.02)\nprint(json.dumps({'return_code':child.returncode,'source_block_fd_access_modes':sorted(modes)}))")
     (out/'backup.log').write_text(host('cat',root+'/backup.log').stdout);assert proof['backup']['return_code']==0 and proof['backup']['source_block_fd_access_modes']==[0]
     proof['backup_system_bytes']=python("from pathlib import Path;import json;print(json.dumps(Path('"+root+"/full/sr-owned-loop').stat().st_size))")
     assert proof['backup_system_bytes']==proof['source_system_extent_bytes']
     if options.multiple:
      assert python("from pathlib import Path;import json;print(json.dumps(Path('"+root+"/full/sr-owned-first').stat().st_size))")==12*1024*1024
     proof['source_device_capacity_bytes']=loop['bytes'];assert loop['bytes']==48*1024*1024
     proof['backup_configuration']=host('cat',root+'/full/backup-my.cnf').stdout
     python("import shutil,json;shutil.copytree('"+root+"/full','"+root+"/prepared');print(json.dumps(True))")
     native('prepare',['--no-defaults','--prepare','--target-dir='+root+'/prepared','--use-memory=268435456','--innodb-data-file-path='+backup_specification,'--innodb-data-home-dir='+root+'/prepared','--innodb-undo-directory='+root+'/prepared'])
     host('mkdir','-p',root+'/system',root+'/copied')
     private_specification=(root+'/system/sr-owned-first:12M;' if options.multiple else '')+root+'/system/sr-owned-loop:'+specification
     native('copy-back',['--no-defaults','--copy-back','--target-dir='+root+'/prepared','--datadir='+root+'/copied','--innodb-data-home-dir='+root+'/copied','--innodb-data-file-path='+private_specification,'--innodb-undo-directory='+root+'/copied','--innodb-log-group-home-dir='+root+'/copied'])
     host('/usr/bin/mysqladmin','--user=root','--socket=/var/run/mysqld/mysqld.sock','shutdown');before=block_hash();source_before=source_hashes();proof['source_block_after_clean_shutdown']=before
     aliases=[{'source_root':'/sr-source225/mysql','private_root':root+'/copied'},{'source_root':'/dev/sr-owned-loop','private_root':root+'/system/sr-owned-loop','kind':'file'}]
     if options.multiple:
      aliases.append({'source_root':'/dev/sr-owned-first','private_root':root+'/system/sr-owned-first','kind':'file'})
      host('rm','/dev/sr-owned-first','/dev/sr-owned-loop')
     args=['/usr/sbin/mysqld','--no-defaults','--persisted-globals-load=OFF','--upgrade=NONE','--datadir=/sr-source225/mysql','--innodb-data-home-dir=','--innodb-data-file-path=/dev/sr-owned-loop:'+specification,'--innodb-undo-directory=/sr-source225/mysql','--socket='+root+'/recovered.sock','--pid-file='+root+'/recovered.pid','--log-error='+root+'/recovered-error.log','--tmpdir='+root,'--user=root','--mysqlx=OFF','--skip-networking','--skip-replica-start','--event-scheduler=DISABLED','--server-id=2311','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin='+root+'/private-bin','--innodb-buffer-pool-size=67108864']
     args=[('--innodb-data-file-path='+recovered_specification if arg.startswith('--innodb-data-file-path=') else arg) for arg in args]
     runtime=python(bootstrap+"\nfrom pathlib import Path\np=sys.modules['_cdeadmin_physical_worker'];r=sys.modules['_cdeadmin_recovery_worker'];ns=sys.modules['_cdeadmin_physical_paths'];directory=Path('"+root+"');view=ns.activate(directory,"+repr(aliases)+",directory=directory)\nwith (directory/'recovered.stdout').open('w') as out:\n child=p.subprocess.Popen("+repr(args)+",stdout=out,stderr=p.subprocess.STDOUT,start_new_session=True)\ntry:process=r.birth(child.pid,{'path':'/usr/sbin/mysqld','sha256':p.host.file_hash(Path('/usr/sbin/mysqld'))})\nexcept BaseException:child.kill();child.wait();raise\nprint(json.dumps({'process':process,'view':view}))")
     for _ in range(120):
      r=host('/usr/bin/mysqladmin','--user=root','--socket='+root+'/recovered.sock','ping',check=False)
      if r.returncode==0:break
      time.sleep(.25)
     else:(out/'recovered-error.log').write_text(host('cat',root+'/recovered-error.log',check=False).stdout);raise RuntimeError('Owned raw recovery not ready')
     proof['recovered_rows']=sql('SELECT id,note,HEX(b) FROM raw231.t WHERE id=1',root+'/recovered.sock');assert proof['recovered_rows']=='1\tnative raw extent 雪\t00FF\n'
     if options.autoextend:
      assert sql('SELECT LENGTH(b),SHA2(b,256) FROM raw231.t WHERE id=3',root+'/recovered.sock')==proof['source_system_payload']
      proof['autoextended_payload_verified']=True
     sql("INSERT INTO raw231.t VALUES(2,'private recovered write',X'0102');COMMIT",root+'/recovered.sock')
     assert sql('SELECT COUNT(*) FROM raw231.t',root+'/recovered.sock')==('3\n' if options.autoextend else '2\n')
     proof['independent_filesystem_observation']=python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_physical_paths'].observe("+str(runtime['process']['pid'])+','+repr(runtime['view'])+')))' )
     assert proof['independent_filesystem_observation']['external_file_aliases']==(2 if options.multiple else 1)
     if options.multiple:
      assert not python("from pathlib import Path;import json;print(json.dumps(any(Path(p).exists() for p in ['/dev/sr-owned-first','/dev/sr-owned-loop'])))")
      proof['multiple_raw_files_and_missing_device_aliases_verified']=True
     assert block_hash()==before and source_hashes()==source_before;proof['original_source_block_and_files_unchanged']=True
     assert python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].stop("+repr(runtime['process'])+')))' )
     for _ in range(120):
      if not python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].present("+repr(runtime['process'])+')))'):break
      time.sleep(.1)
     else:raise RuntimeError('Original native recovery process did not stop')
     proof['original_recovery_end_observed']=True;runtime=None;proof['complete']=True
    finally:
     if runtime:
      try:python(bootstrap+"\nprint(json.dumps(sys.modules['_cdeadmin_recovery_worker'].stop("+repr(runtime['process'])+')))')
      except Exception:pass
     r=run(['docker','logs',name],False);(out/'source.log').write_text(r.stdout+r.stderr)
     run(['docker','rm','-fv',name],False)
     for v in volumes:run(['docker','volume','rm',v],False)
     proof['owned_container_and_data_removed']=run(['docker','inspect',name],False).returncode!=0 and all(run(['docker','volume','inspect',v],False).returncode!=0 for v in volumes)
     if loop:
      indices=[loop['loop_index'],*[item['loop_index'] for item in loop.get('additional_loops',[])]]
      r=run(['docker','run','--rm','--entrypoint','/usr/bin/python3',options.fixture_image,'-c',"from pathlib import Path;import json;indices="+repr(indices)+";print(json.dumps({'owned_loop_detached':all(not Path('/sys/block/loop'+str(index)+'/loop/backing_file').exists() for index in indices)}))"],False);proof['loop_cleanup_observation']=json.loads(r.stdout) if r.returncode==0 else {'unknown':True}
     (out/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k not in {'native_package','namespace_source_sha256','backup_configuration'}},indent=2))

    if options.admit_package:
     assert proof['complete'] and proof['owned_container_and_data_removed'] and proof['loop_cleanup_observation'].get('owned_loop_detached')
     original=(pkg/'PROVENANCE.json').read_bytes();value=json.loads(original)
     assert options.autoextend and options.fixed_receipt,'Qualify fixed and autoextended native extents before package admission'
     assert options.multiple and options.auto_receipt,'Qualify multiple raw system files before package admission'
     fixed=json.loads(options.fixed_receipt.read_text())
     assert fixed['complete'] and fixed['owned_container_and_data_removed'] and fixed['loop_cleanup_observation'].get('owned_loop_detached')
     assert fixed['native_package']['binary_sha256']==value['binary_sha256'] and fixed['original_source_block_and_files_unchanged']
     assert fixed['backup']['source_block_fd_access_modes']==[0] and fixed['backup_system_bytes']==32*1024*1024
     auto=json.loads(options.auto_receipt.read_text())
     assert auto['complete'] and auto['owned_container_and_data_removed'] and auto['loop_cleanup_observation'].get('owned_loop_detached')
     assert auto['native_package']['binary_sha256']==value['binary_sha256'] and auto['autoextended_payload_verified'] and auto['original_source_block_and_files_unchanged']
     value.update(research_candidate_only=False,capabilities=['raw-system-files-v1'],application_raw_admission=True)
     value['qualification']={'scope':'native raw system files','binary_sha256':value['binary_sha256'],'qualified_extents':['fixed','autoextended'],'multiple_system_files':True,'source_block_fd_access_modes':proof['backup']['source_block_fd_access_modes'],'source_bytes_unchanged':True,'configured_extent_bytes':proof['backup_system_bytes'],'device_capacity_bytes':proof['source_device_capacity_bytes']}
     (pkg/'PROVENANCE.json').write_text(json.dumps(value,indent=2)+'\n')
     try:
      scope={};exec(bootstrap,scope)
      native=scope['sys'].modules['_cdeadmin_physical_worker']
      admitted=native.raw_storage_backend({'path':str(pkg/'bin/xtrabackup'),'sha256':native.host.file_hash(pkg/'bin/xtrabackup')})
     except BaseException:
      (pkg/'PROVENANCE.json').write_bytes(original);raise
     proof['admitted_native_package']=admitted
     (out/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    main()
