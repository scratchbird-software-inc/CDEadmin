"""Build and qualify the pinned GPL native MySQL raw-storage backup reader.

All source/build output belongs in the selected external work area. An optional
already patched source and build directory allow an interrupted native build to
resume. Neither a donor source clone nor the application checkout is modified.
Run the repository DDN freshness prerequisite before invoking this build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REVISION='b1c9c34183de95316d8889ea3d4cb31e31ffddc5'
KMIP='82988b2de6a0687791a3ae549fc2bd5cbeb457ab'
PATCH=ROOT/'tools/native/mysql_physical/raw-reader.patch'
PATCHELF='patchelf-0.19.1.0-py3-none-manylinux1_x86_64.manylinux_2_5_x86_64.musllinux_1_1_x86_64.whl'
PATCHELF_SHA='a8f6331ccf40c345507279f755f4a38c2cb00b9efda746fd43c17713cce0aba4'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build(args):
    work=args.work.resolve();source=(args.patched_source or work/'source').resolve();output=(args.build_directory or work/'build').resolve()
    for path in (work,source,output):
        if path==ROOT or ROOT in path.parents:raise ValueError('Keep native source/build work outside the application checkout')
    work.mkdir(mode=0o700,parents=True,exist_ok=False);output.mkdir(mode=0o700,parents=True,exist_ok=args.resume)
    def run(command,check=True):return subprocess.run(command,capture_output=True,text=True,check=check)
    def logged(command,name):
        with (work/name).open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    if not args.patched_source:
        source.mkdir();run(['git','-C',str(source),'init','--quiet'])
        run(['git','-C',str(source),'remote','add','origin','https://github.com/percona/percona-xtrabackup'])
        run(['git','-C',str(source),'fetch','--depth','1','origin',REVISION]);run(['git','-C',str(source),'checkout','--detach','FETCH_HEAD'])
        logged(['git','-C',str(source),'submodule','update','--init','--depth','1','extra/libkmip'],'submodule.log')
        run(['git','-C',str(source),'apply',str(PATCH)])
    assert run(['git','-C',str(source),'rev-parse','HEAD']).stdout.strip()==REVISION
    assert run(['git','-C',str(source/'extra/libkmip'),'rev-parse','HEAD']).stdout.strip()==KMIP
    diff=subprocess.check_output(['git','-C',str(source),'diff','--binary']);assert hashlib.sha256(diff).hexdigest()==sha(PATCH),'Select the exact admitted native source patch'
    image=args.toolchain_image
    if image is None:
        if run(['docker','image','inspect',args.base_image],False).returncode:logged(['docker','pull',args.base_image],'base-image.log')
        base_info=json.loads(run(['docker','image','inspect',args.base_image]).stdout)[0]
        base=next(iter(base_info.get('RepoDigests') or []),args.base_image)
        context=work/'toolchain';context.mkdir()
        (context/'Dockerfile').write_text('FROM '+base+'\nUSER root\nRUN microdnf --disablerepo="mysql*" --enablerepo=ol9_codeready_builder install -y gcc-toolset-14-gcc gcc-toolset-14-gcc-c++ cmake make ninja-build bison libaio-devel libgcrypt-devel libgpg-error-devel libcurl-devel libev-devel procps-ng-devel openssl-devel zlib-devel ncurses-devel libtirpc-devel rpcgen git diffutils patch tar gzip xz unzip perl findutils && microdnf clean all\nENTRYPOINT ["/bin/sleep"]\n')
        image='sr-mysql-backup-build:'+secrets.token_hex(8);logged(['docker','build','--progress=plain','-t',image,str(context)],'toolchain.log')
    image_info=json.loads(run(['docker','image','inspect',image]).stdout)[0];container='sr-mysql-backup-build-'+secrets.token_hex(8);volumes=[]
    receipt={'complete':False,'upstream_revision':REVISION,'submodule_revision':KMIP,'patch_sha256':sha(PATCH),
        'toolchain_image_id':image_info['Id'],'history_testing':'not run','source_read_only':True}
    fixture=args.fixture_image
    try:
        run(['docker','run','--rm','-d','--name',container,'--user',str(os.getuid())+':'+str(os.getgid()),
            '--mount',f'type=bind,source={source},target=/src,readonly','--mount',f'type=bind,source={output},target=/build',
            '-e','CC=/opt/rh/gcc-toolset-14/root/usr/bin/gcc','-e','CXX=/opt/rh/gcc-toolset-14/root/usr/bin/g++',
            '-e','GIT_CONFIG_COUNT=1','-e','GIT_CONFIG_KEY_0=safe.directory','-e','GIT_CONFIG_VALUE_0=/src',image,'86400'])
        volumes=[m['Name'] for m in json.loads(run(['docker','inspect','--format','{{json .Mounts}}',container]).stdout) if m['Type']=='volume']
        (work/'packages.txt').write_text(run(['docker','exec',container,'rpm','-qa','--qf','%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\n']).stdout)
        logged(['docker','exec',container,'cmake','-S','/src','-B','/build','-G','Ninja','-DBUILD_CONFIG=xtrabackup_release','-DCMAKE_BUILD_TYPE=Release',
            '-DMYSQL_MAINTAINER_MODE=OFF','-DWITH_UNIT_TESTS=OFF','-DWITH_ROUTER=OFF','-DWITH_SSL=system','-DWITH_ZLIB=bundled','-DWITH_LZ4=bundled',
            '-DWITH_ZSTD=bundled','-DWITH_ICU=bundled','-DWITH_PROTOBUF=bundled','-DWITH_NUMA=OFF','-DCMAKE_INSTALL_PREFIX=/opt/scratchrobin-xtrabackup'],'configure.log')
        logged(['docker','exec',container,'cmake','--build','/build','--parallel',str(args.workers),'--target','xtrabackup','--','-k','0'],'compile.log')
        candidates=[p for p in output.rglob('xtrabackup') if p.is_file() and p.open('rb').read(4)==b'\x7fELF' and not any(part.startswith('package') for part in p.parts)]
        assert len(candidates)==1,candidates
        binary=candidates[0];package=output/('package-'+secrets.token_hex(6));(package/'bin').mkdir(parents=True);(package/'lib').mkdir()
        shutil.copy2(binary,package/'bin/xtrabackup')
        ldd=run(['docker','exec',container,'ldd','/build/'+str(binary.relative_to(output))]).stdout;(work/'ldd.txt').write_text(ldd);assert 'not found' not in ldd
        system={'libc.so.6','libpthread.so.0','libm.so.6','libdl.so.2','librt.so.1','libresolv.so.2','ld-linux-x86-64.so.2'}
        for line in ldd.splitlines():
            match=re.match(r'\s*(\S+)\s+=>\s+(/\S+)',line)
            if match and match[1] not in system:run(['docker','cp','-L',container+':'+match[2],str(package/'lib'/match[1])])
        wheel=work/PATCHELF;metadata=json.load(urllib.request.urlopen('https://pypi.org/pypi/patchelf/0.19.1.0/json'))
        artifact=next(v for v in metadata['urls'] if v['filename']==PATCHELF and v['digests']['sha256']==PATCHELF_SHA and not v['yanked'])
        with urllib.request.urlopen(artifact['url']) as response,wheel.open('xb') as stream:shutil.copyfileobj(response,stream)
        assert sha(wheel)==PATCHELF_SHA
        patcher=output/('patchelf-'+secrets.token_hex(6))
        with zipfile.ZipFile(wheel) as archive:
            member=next(n for n in archive.namelist() if n.endswith('/scripts/patchelf'));patcher.write_bytes(archive.read(member));patcher.chmod(0o755)
        prefix='/build/'+str(package.relative_to(output));tool='/build/'+patcher.name
        run(['docker','exec',container,tool,'--set-rpath','$ORIGIN/../lib',prefix+'/bin/xtrabackup'])
        for library in (package/'lib').iterdir():run(['docker','exec',container,tool,'--set-rpath','$ORIGIN',prefix+'/lib/'+library.name])
        patcher.unlink();wheel.unlink();shutil.copy2(source/'LICENSE',package/'LICENSE');shutil.copy2(PATCH,package/'native-raw.patch')
        (package/'SOURCE.txt').write_text('Percona XtraBackup9.7.1-rc1; GPL-2.0\nhttps://github.com/percona/percona-xtrabackup\nRevision '+REVISION+'\nApply native-raw.patch; build with tools/build_mysql_raw_backend.py.\n')
        value={'schema':'scratchrobin.native-backup-build.v1','upstream_revision':REVISION,'patch_sha256':sha(PATCH),'binary_sha256':sha(package/'bin/xtrabackup'),
            'libraries':{p.name:sha(p) for p in sorted((package/'lib').iterdir())},'package_files':{str(p.relative_to(package)):sha(p) for p in sorted(package.rglob('*')) if p.is_file()},
            'toolchain_image_id':image_info['Id'],'research_candidate_only':True,'application_raw_admission':False}
        (package/'PROVENANCE.json').write_text(json.dumps(value,indent=2)+'\n')
        logged(['docker','exec',container,prefix+'/bin/xtrabackup','--no-defaults','--version'],'version.log')
        receipt.update(package=str(package),binary_sha256=value['binary_sha256'])
        if fixture is None:
            from cdeadmin_mysql_physical_qualification import prepare_fixture
            fixture='sr-mysql-raw-fixture:'+secrets.token_hex(8)
            prepare_fixture(work,fixture,missing_paths='root')
        logged([sys.executable,'-B',str(ROOT/'tools/cdeadmin_mysql_raw_storage_qualification.py'),'--package',str(package),
            '--fixture-image',fixture,'--output',str(work/'qualification-fixed')],'qualification-fixed.log')
        logged([sys.executable,'-B',str(ROOT/'tools/cdeadmin_mysql_raw_storage_qualification.py'),'--package',str(package),
            '--fixture-image',fixture,'--output',str(work/'qualification-autoextended'),'--autoextend'],'qualification-autoextended.log')
        logged([sys.executable,'-B',str(ROOT/'tools/cdeadmin_mysql_raw_storage_qualification.py'),'--package',str(package),
            '--fixture-image',fixture,'--output',str(work/'qualification-multiple'),'--autoextend','--multiple','--fixed-receipt',
            str(work/'qualification-fixed/summary.json'),'--auto-receipt',str(work/'qualification-autoextended/summary.json'),
            '--admit-package'],'qualification-multiple.log')
        final=work/'package';shutil.move(str(package),final);receipt['package']=str(final)
        receipt['complete']=True
    finally:
        run(['docker','rm','-fv',container],False)
        for volume in volumes:run(['docker','volume','rm',volume],False)
        if args.fixture_image is None and fixture:run(['docker','image','rm',fixture],False)
        if args.toolchain_image is None:run(['docker','image','rm',image],False)
        if receipt['complete'] and not args.keep_build:
            if not args.build_directory:shutil.rmtree(output)
            if not args.patched_source:shutil.rmtree(source)
        shutil.rmtree(work/'fixture-build',ignore_errors=True)
        receipt['owned_builder_removed']=run(['docker','inspect',container],False).returncode!=0
        (work/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--patched-source',type=Path);parser.add_argument('--build-directory',type=Path)
    parser.add_argument('--resume',action='store_true');parser.add_argument('--toolchain-image')
    parser.add_argument('--base-image',default='mysql:9.7.0');parser.add_argument('--fixture-image')
    parser.add_argument('--keep-build',action='store_true')
    parser.add_argument('--workers',type=int,choices=(1,2),default=2)
    print(json.dumps(build(parser.parse_args()),indent=2))
