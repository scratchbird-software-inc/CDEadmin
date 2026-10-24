"""Actual native option-file installation on the parent gate's owned SSH host."""
import base64
import hashlib
import json
from pathlib import Path


def qualify(review,http,admitted,wait,config,remote,root,output,selected):
    def replacement(data):return {'base64':base64.b64encode(data.encode('utf8')).decode('ascii')}
    def read(path):return remote('from pathlib import Path;print(Path('+repr(path)+').read_text())').stdout.strip()
    config('[mysqld]\nmax_connections=151\n')
    remote("import os,pwd,struct;p='/tmp/selected.cnf';uid=pwd.getpwnam('mysql').pw_uid;entries=[(1,6,0xffffffff),(2,4,uid),(4,0,0xffffffff),(16,4,0xffffffff),(32,0,0xffffffff)];os.setxattr(p,'system.posix_acl_access',struct.pack('<I',2)+b''.join(struct.pack('<HHI',*row) for row in entries));os.setxattr(p,'user.scratchrobin-config',b'native\\x00\\xff')")
    proposed='[mysqld]\n!include /tmp/sr-install-include.cnf\nmax_connections=155\n'
    remote("from pathlib import Path;Path('/tmp/sr-install-include.cnf').write_text('[mysqld]\\nmax_allowed_packet=33554432\\n')")
    def options(text=proposed):return {**selected,'configuration_file':'/tmp/selected.cnf','operation':'deploy_config','configuration_replacement':replacement(text)}
    planned=review(options());deployment=planned['remote_observation']['configuration_deployment']
    assert deployment['replacement_sha256']==hashlib.sha256(proposed.encode()).hexdigest()
    assert deployment['original']['extended_attributes']['user.scratchrobin-config']==hashlib.sha256(b'native\x00\xff').hexdigest()
    assert 'base64' not in planned['options']['configuration_replacement']
    assert read('/tmp/selected.cnf')=='[mysqld]\nmax_connections=151'
    remote("from pathlib import Path;Path('/tmp/sr-install-include.cnf').write_text('[mysqld]\\nmax_allowed_packet=67108864\\n')")
    http('start',admitted(planned),refused=True);http('cancel',{'job_id':planned['job_id']})
    with root.cursor() as cursor:
        cursor.execute('SELECT @@global.max_connections');original_runtime=cursor.fetchone()[0]
    planned=review(options());receipt=wait(http('start',admitted(planned)))
    result=receipt['remote_receipt'];installed=result['configuration_deployment_result']
    assert installed['installed'] and not installed['restart_issued'] and installed['native_validation']['return_code']==0
    assert result['configuration_after_process']['matches_review']
    permissions=json.loads(remote("import os,stat,hashlib,json;p='/tmp/selected.cnf';s=os.lstat(p);print(json.dumps({'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'extended_attributes':{n:hashlib.sha256(os.getxattr(p,n)).hexdigest() for n in os.listxattr(p)}}))").stdout)
    assert permissions=={key:value for key,value in result['observation']['configuration_deployment']['original'].items() if key not in {'device','inode'}}
    assert read('/tmp/selected.cnf')==proposed.strip()
    remote("import os,pwd,subprocess,sys;entry=pwd.getpwnam('mysql');assert os.getxattr('/tmp/selected.cnf','user.scratchrobin-config')==b'native\\x00\\xff';subprocess.run([sys.executable,'-c',\"from pathlib import Path;assert b'max_connections=155' in Path('/tmp/selected.cnf').read_bytes()\"],user=entry.pw_uid,group=entry.pw_gid,extra_groups=[],check=True)")
    assert http('start',admitted(receipt,{}))['remote_receipt']==result
    bad=proposed+'unknown_scratchrobin_install_option=1\n'
    refused=wait(http('start',admitted(review(options(bad)))))
    assert not refused['remote_receipt']['configuration_deployment_result']['installed']
    assert refused['remote_receipt']['result']['return_code']!=0 and read('/tmp/selected.cnf')==proposed.strip()
    # Native includes must see the proposed bytes at the original pathname.
    # The old root is deliberately invalid; validating a differently named
    # temporary file against it would produce a different native result.
    config('[mysqld]\nunknown_scratchrobin_old_root=1\n')
    circular='[mysqld]\n!include /tmp/selected.cnf\nmax_connections=157\n'
    planned=review(options(circular));rows=planned['remote_observation']['configuration_deployment']['prospective_configuration_graph']['entries']
    assert len([row for row in rows if row.get('sha256')==hashlib.sha256(circular.encode()).hexdigest()])>1
    circular_receipt=wait(http('start',admitted(planned)))
    assert circular_receipt['remote_receipt']['configuration_deployment_result']['installed']
    assert circular_receipt['remote_receipt']['result']['return_code']==0
    assert read('/tmp/selected.cnf')==circular.strip()
    with root.cursor() as cursor:
        cursor.execute('SELECT @@global.max_connections');assert cursor.fetchone()[0]==original_runtime
    (Path(output)/'configuration-installation.json').write_text(json.dumps({'complete':True,
        'installed':installed,'preserved_native_file_metadata':permissions,'native_invalid_file_preserved_original':True,'circular_original_filename_projection_verified':True,
        'source_runtime_unchanged':True,'native_POSIX_ACL_mysql_user_read_and_opaque_xattrs_preserved':True,'history_testing':'not run'},indent=2)+'\n')
    return ['reviewed-prospective-native-include-graph-and-stale-include-refusal-before-file-installation',
        'native-private-original-filename-validation-atomic-option-file-installation-no-restart-and-no-duplicate-dispatch',
        'native-invalid-proposal-preserves-current-file-and-native-circular-includes-see-proposed-original-root']
