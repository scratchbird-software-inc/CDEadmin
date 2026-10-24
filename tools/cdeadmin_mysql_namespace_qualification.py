"""Actual captured native filesystem and original-process qualification.

This gate exercises kernel isolation and process descriptors. Separate MySQL
physical API/desktop gates qualify SQL recovery and native engine behavior.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PROVIDER=ROOT/'web/pgadmin/cdeadmin/providers/mysql_family'


def captured_sources():
    sources={'fileio':(ROOT/'web/pgadmin/cdeadmin/operations/fileio.py').read_text()}
    for key,name in {'services':'mysql_host_services.py','host':'mysql_host_worker.py','physical':'mysql_physical_worker.py',
            'keyring':'mysql_physical_keyring.py','paths':'mysql_physical_paths.py','recovery':'mysql_recovery_worker.py',
            'geometry':'mysql_physical_geometry.py',
            'stream':'mysql_recovery_stream.py','retention':'mysql_physical_retention_worker.py'}.items():
        sources[key]=(PROVIDER/name).read_text()
    tree=ast.parse((PROVIDER/'mysql_physical_transport.py').read_text())
    bootstrap=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id=='BOOTSTRAP' for target in node.targets))
    return bootstrap+'\nload('+repr(sources)+')\n',{key:hashlib.sha256(value.encode()).hexdigest() for key,value in sources.items()}


START='''from pathlib import Path
import json,os,subprocess,sys
paths=sys.modules['_cdeadmin_physical_paths'];recovery=sys.modules['_cdeadmin_recovery_worker'];physical=sys.modules['_cdeadmin_physical_worker']
workspace=Path('/var/backups/sr-namespace');directory=workspace/'job';roots=[]
for index,name in enumerate(ALIASES):
 data=directory/('runtime-data' if index==0 else 'runtime-extra-'+str(index));data.mkdir(parents=True)
 (data/'value').write_text('private recovered bytes')
 roots.append({'source_root':name,'private_root':str(data),'initial_alias_exists':Path(name).exists()})
canary=Path('/tmp/sr-namespace-canary');canary.write_text('original host bytes')
program={'path':str(Path(sys.executable).resolve()),'sha256':physical.host.file_hash(Path(sys.executable))}
controller=recovery.birth(os.getpid(),program)
capability=paths.capability(projection=any(not row['initial_alias_exists'] for row in roots),root_projection=ROOT_PROJECTION)
view=paths.activate(workspace,[{key:row[key] for key in ('source_root','private_root')} for row in roots],directory=directory)
assert recovery.present(controller)
try:canary.write_text('must not overwrite the host')
except OSError as error:assert error.errno==30
else:raise RuntimeError('Native host view unexpectedly writable')
for index,row in enumerate(roots):
 (Path(row['source_root'])/'value').write_text('private alias write '+str(index))
 assert (Path(row['private_root'])/'value').read_text()=='private alias write '+str(index)
child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
try:
 process=recovery.birth(child.pid,program)
 print(json.dumps({'roots':roots,'view':view,'process':process,'capability':capability,'controller_survives_root_projection':True}))
except BaseException:
 child.kill();child.wait(timeout=10);raise
'''


OBSERVE='''from pathlib import Path
import json,time
paths=sys.modules['_cdeadmin_physical_paths'];recovery=sys.modules['_cdeadmin_recovery_worker']
record=RECORD;process=record['process']
for index,row in enumerate(record['roots']):
 assert Path(row['source_root']).exists()==row['initial_alias_exists']
 assert (Path(row['private_root'])/'value').read_text()=='private alias write '+str(index)
assert Path('/tmp/sr-namespace-canary').read_text()=='original host bytes'
assert recovery.present(process)
observed=paths.observe(process['pid'],record['view'])
assert observed['native_filesystem_isolation_observed']
assert recovery.stop(process)
deadline=time.monotonic()+10
while recovery.present(process) and time.monotonic()<deadline:time.sleep(.05)
assert not recovery.present(process)
assert all(Path(row['source_root']).exists()==row['initial_alias_exists'] for row in record['roots'])
print(json.dumps({'native_isolation_observed':observed,'original_process_stopped':True,'base_alias_existence_unchanged':True,'host_canary_unchanged':True,'private_bytes_persist':True}))
'''


def qualify(output,image,*,prepare=False):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep private native qualification outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    bootstrap,hashes=captured_sources()
    proof={'complete':False,'scope':'Captured native filesystem and original-process facts only; no SQL/history qualification',
        'source_sha256':hashes,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'transport_sha256':hashlib.sha256((PROVIDER/'mysql_physical_transport.py').read_bytes()).hexdigest(),
        'cases':[],'history_testing':'not run'}
    if prepare:
        from cdeadmin_mysql_physical_qualification import prepare_fixture
        key=prepare_fixture(output,image)
        key.unlink();key.with_suffix('.pub').unlink()
    details=json.loads(subprocess.check_output(['docker','image','inspect',image],text=True))[0]
    proof['fixture_image']={'requested_reference':image,'image_id':details['Id'],'architecture':details['Architecture'],'os':details['Os']}
    for variant,aliases,root_projection in [('existing',['/var/lib/mysql'],False),
            ('missing-parent',['/var/lib/sr-namespace-missing/data'],False),('missing-root',['/sr-namespace-missing/data'],True),
            ('mixed-missing-roots',['/sr-main-missing/data','/var/lib/sr-external-missing/data'],True)]:
        name='sr-namespace-'+secrets.token_hex(8);volumes=[];case={'variant':variant,'complete':False}
        try:
            subprocess.run(['docker','run','--rm','-d','--cap-add=SYS_ADMIN','--name',name,'--entrypoint','/bin/sleep',image,'3600'],capture_output=True,check=True)
            volumes=[row['Name'] for row in json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}',name],text=True)) if row['Type']=='volume']
            code=bootstrap+'ALIASES='+repr(aliases)+'\nROOT_PROJECTION='+repr(root_projection)+'\n'+START
            result=subprocess.run(['docker','exec','-i',name,'python3','-'],input=code,capture_output=True,text=True,timeout=30)
            (output/(variant+'-start.log')).write_text(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError('Native namespace startup failed; inspect '+variant+'-start.log')
            record=json.loads(result.stdout)
            code=bootstrap+'RECORD='+repr(record)+'\n'+OBSERVE
            result=subprocess.run(['docker','exec','-i',name,'python3','-'],input=code,capture_output=True,text=True,timeout=30)
            (output/(variant+'-observe.log')).write_text(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError('Native independent observation failed; inspect '+variant+'-observe.log')
            case.update(complete=True,start=record,observed=json.loads(result.stdout))
        except BaseException as error:
            case['error_type']=type(error).__name__;case['error_message']=str(error)
        finally:
            subprocess.run(['docker','rm','-f',name],capture_output=True)
            remaining=[]
            for volume in volumes:
                subprocess.run(['docker','volume','rm',volume],capture_output=True)
                if subprocess.run(['docker','volume','inspect',volume],capture_output=True).returncode==0:remaining.append(volume)
            container_exists=subprocess.run(['docker','inspect',name],capture_output=True).returncode==0
            case['owned_container_and_data_removed']=not container_exists and not remaining
            if remaining:case['remaining_owned_volumes']=remaining
            proof['cases'].append(case);(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    proof['complete']=all(case['complete'] and case['owned_container_and_data_removed'] for case in proof['cases'])
    (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native namespace qualification has failures; inspect complete summary.json')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',required=True)
    parser.add_argument('--prepare-fixture',action='store_true');args=parser.parse_args()
    qualify(args.output,args.fixture_image,prepare=args.prepare_fixture)
