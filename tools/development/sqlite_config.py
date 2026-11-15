"""Build and qualify the public native SQLite configuration component."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def build(root, python, sqlite, work, prefix):
    root,python,sqlite,work,prefix=map(lambda p:Path(p).resolve(),(root,python,sqlite,work,prefix))
    work.mkdir(parents=True,exist_ok=True);prefix.mkdir(parents=True,exist_ok=True)
    abi=json.loads(subprocess.check_output([str(python),'-B','-c',
        'import sysconfig,json;print(json.dumps({k:sysconfig.get_config_var(k) for k in ("SOABI","EXT_SUFFIX")}))'],text=True))
    name='_cdeadmin_dbconfig'+abi['EXT_SUFFIX'];target=prefix/name;marker=prefix/'sqlite-config-install.json'
    sources=[root/'tools/native/sqlite_config/api.c',root/'tools/native/sqlite_config/CMakeLists.txt',
             root/'tools/native/sqlite_recovery/provenance.cmake']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={'source_sha256':{str(p.relative_to(root)):sha(p)for p in sources},'interpreter':str(python),
            'abi':abi,'sqlite_library_sha256':sha(sqlite/'lib/libsqlite3.so.0'),
            'sqlite_header_sha256':sha(sqlite/'include/sqlite3.h')}
    if marker.exists():
        previous=json.loads(marker.read_text())
        if (previous.get('inputs')==inputs and target.is_file() and previous.get('sha256')==sha(target)
            and Path(str(target)+'.json').is_file() and previous.get('manifest_sha256')==sha(Path(str(target)+'.json'))):
            return target
        raise RuntimeError('Preserved changed native configuration installation; stop applications and select a fresh owned prefix')
    if target.exists() or Path(str(target)+'.json').exists():raise RuntimeError('Preserved unknown native configuration installation')
    with tempfile.TemporaryDirectory(prefix='sqlite-config-',dir=work)as area:
        area=Path(area)
        for source in sources:
            destination=area/source.relative_to(root);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        if inputs['source_sha256']!={str(p.relative_to(root)):sha(p)for p in sources}:
            raise RuntimeError('Native configuration source changed during capture; retry capture')
        commands=[['cmake','-S',str(area/'tools/native/sqlite_config'),'-B',str(area/'build'),
            '-DCMAKE_BUILD_TYPE=Release','-DPython3_EXECUTABLE='+str(python),
            '-DSQLite3_INCLUDE_DIR='+str(sqlite/'include'),'-DSQLite3_LIBRARY='+str(sqlite/'lib/libsqlite3.so.0')],
            ['cmake','--build',str(area/'build'),'--parallel','2']]
        for index,command in enumerate(commands):
            with(work/f'sqlite-config-build-{index}.log').open('w')as log:
                subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
        binary=area/'build'/name
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(root/'web'),TMPDIR=str(work))
        probe='''import sqlite_native_component as component,sys
loaded=component.load(sys.argv[1]);loaded.retain()
import sqlite3
class Probe(sqlite3.Connection):pass
capsule=loaded.module.begin();source=sqlite3.connect(':memory:',factory=Probe,cached_statements=0)
loaded.module.finish(capsule,source)
assert loaded.module.usage(capsule)==(0,0,0)
source.close();loaded.module.closed(capsule,source);loaded.release()
print('Original interpreter library instance captured and closed')
'''
        with(work/'sqlite-config-native-probe.log').open('w')as log:
            subprocess.run([str(python),'-B','-c',probe,str(binary)],env=environment,check=True,stdout=log,stderr=subprocess.STDOUT)
        # Exclusive creation never overwrites another runtime's module. Clean
        # only files successfully created by this attempt on publication failure.
        created=[]
        try:
            for source,destination in [(binary,target),(Path(str(binary)+'.json'),Path(str(target)+'.json'))]:
                with destination.open('xb')as output:
                    created.append(destination);output.write(source.read_bytes());output.flush();os.fsync(output.fileno())
            receipt={'inputs':inputs,'filename':name,'sha256':sha(target),'manifest_sha256':sha(Path(str(target)+'.json')),
                     'original_interpreter_instance_qualified':True}
            with marker.open('x')as output:
                created.append(marker);json.dump(receipt,output,indent=2);output.write('\n')
        except BaseException:
            for destination in reversed(created):destination.unlink(missing_ok=True)
            raise
    return target
