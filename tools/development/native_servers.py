"""Exact native server/tool kits for owned Windows and macOS test fixtures."""
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import zipfile

from native import STATE, command
from native_assets import ASSETS, download

SERVER_ASSETS = {
    'mysql-windows': ('https://downloads.mysql.com/archives/get/p/23/file/mysql-9.7.0-winx64.zip',
                       '7fd8559058e6e132f275971a6a0a058c7a6705f14112df84fcf2617067ec5358'),
    'mysql-macos-arm64': ('https://downloads.mysql.com/archives/get/p/23/file/mysql-9.7.0-macos15-arm64.tar.gz',
                           '81d0c55227093e2ebdffb424452c458b0b4a39ddff76c5bcc25e93085ab7a912'),
    'mysql-macos-x64': ('https://downloads.mysql.com/archives/get/p/23/file/mysql-9.7.0-macos15-x86_64.tar.gz',
                         '56ac831e1a281f2eb9c0c3c938ca45977be78c5af11a8880f6b3d3132e199e43'),
    'mysql-shell-windows': ('https://downloads.mysql.com/archives/get/p/43/file/mysql-shell-9.7.0-windows-x86-64bit.zip',
                             '1362c31da0123b916fd9dc9bce2b862835e89addf7a72b851bea584e9b1eeb3f'),
    'mysql-shell-macos-arm64': ('https://downloads.mysql.com/archives/get/p/43/file/mysql-shell-9.7.0-macos15-arm64.tar.gz',
                                 'b6d9a02904045417ddba92ae42b27b360080b94831196785a811d7cba32f202b'),
    'mysql-shell-macos-x64': ('https://downloads.mysql.com/archives/get/p/43/file/mysql-shell-9.7.0-macos15-x86-64bit.tar.gz',
                               'bace0a655e9a4e932b5a29f181abbb3193a3fa362f7a63eb76531dadc0fbef8b'),
    'mariadb-windows': ('https://archive.mariadb.org/mariadb-12.2.2/winx64-packages/mariadb-12.2.2-winx64.zip',
                         'b34bb91f0dd4bd184f420288a12aace2b5fcb20734f2b880075c36150d4641c6'),
    'mariadb-source': ('https://archive.mariadb.org/mariadb-12.2.2/source/mariadb-12.2.2.tar.gz',
                        'fe82fe2e9af98dfcad8c0266a283ca349b78fd46989fff0d5e1ffca644b514bd'),
    'postgres-source': ('https://ftp.postgresql.org/pub/source/v18.3/postgresql-18.3.tar.bz2',
                         'd95663fbbf3a80f81a9d98d895266bdcb74ba274bcc04ef6d76630a72dee016f'),
}


def binary(root, name):
    return root / 'bin' / (name + '.exe' if os.name == 'nt' else name)


def unpack(asset, target):
    if (target / '.cdeadmin-server-complete').exists():
        return
    if target.exists():
        raise RuntimeError(f'Incomplete native server kit: inspect {target}')
    archive = download(asset)
    with tempfile.TemporaryDirectory(prefix='server-kit-', dir=STATE) as temporary:
        root = Path(temporary)
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as source:
                source.extractall(root)
        else:
            with tarfile.open(archive) as source:
                source.extractall(root, filter='data')
        directories = list(root.iterdir())
        if len(directories) != 1 or not directories[0].is_dir():
            raise RuntimeError('Expected one root in the verified native server archive')
        directories[0].rename(target)
    (target / '.cdeadmin-server-complete').write_text(ASSETS[asset][1], encoding='utf-8')


def brew_prefix(formula):
    return subprocess.check_output(['brew', '--prefix', formula], text=True).strip()


def postgres(evidence, env):
    if platform.system() == 'Windows':
        root = STATE / 'postgres/pgsql'
        if not binary(root, 'postgres').is_file():
            raise RuntimeError('Run clients to provision PostgreSQL on Windows')
        return
    root = STATE / 'postgres'
    if (root / '.cdeadmin-server-complete').exists():
        return
    source = STATE / 'postgres-source'
    source.mkdir(exist_ok=True)
    tree = source / 'postgresql-18.3'
    if not tree.exists():
        with tarfile.open(download('postgres-source')) as archive:
            archive.extractall(source, filter='data')
    openssl = brew_prefix('openssl@3')
    icu = brew_prefix('icu4c')
    prefixes = [openssl, icu, *(brew_prefix(p) for p in ('libxml2', 'lz4', 'zstd', 'readline'))]
    selected = dict(env, PKG_CONFIG_PATH=os.pathsep.join([
        *(p + '/lib/pkgconfig' for p in prefixes), env.get('PKG_CONFIG_PATH', '')]),
        CPPFLAGS=' '.join('-I' + p + '/include' for p in prefixes),
        LDFLAGS=' '.join('-L' + p + '/lib -Wl,-rpath,' + p + '/lib' for p in prefixes))
    build = STATE / 'postgres-build'
    build.mkdir(exist_ok=True)
    command([tree / 'configure', '--prefix=' + str(root), '--with-ssl=openssl',
             '--with-icu', '--with-libxml', '--with-lz4', '--with-zstd'],
            cwd=build, env=selected, log=evidence / 'postgres-configure.log')
    command(['make', '-j3'], cwd=build, env=selected, log=evidence / 'postgres-build.log')
    command(['make', 'install'], cwd=build, env=selected, log=evidence / 'postgres-install.log')
    (root / '.cdeadmin-server-complete').write_text(ASSETS['postgres-source'][1], encoding='utf-8')


def mariadb(evidence, env):
    root = STATE / 'mariadb'
    if platform.system() == 'Windows':
        unpack('mariadb-windows', root)
        return
    if (root / '.cdeadmin-server-complete').exists():
        return
    source = STATE / 'mariadb-source'
    source.mkdir(exist_ok=True)
    tree = source / 'mariadb-12.2.2'
    if not tree.exists():
        with tarfile.open(download('mariadb-source')) as archive:
            archive.extractall(source, filter='data')
    build = STATE / 'mariadb-build'
    bison = brew_prefix('bison')
    selected = dict(env, PATH=bison + '/bin' + os.pathsep + env['PATH'])
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    cc = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    cxx = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
    for variable in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH'):
        selected.pop(variable, None)
    selected.update(SDKROOT=sdk, CC=cc, CXX=cxx)
    command(['cmake', '-S', tree, '-B', build, '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_OSX_SYSROOT=' + sdk, '-DCMAKE_C_COMPILER=' + cc,
             '-DCMAKE_CXX_COMPILER=' + cxx,
             '-DCMAKE_INSTALL_PREFIX=' + str(root), '-DWITH_UNIT_TESTS=OFF',
             '-DWITH_SSL=system', '-DOPENSSL_ROOT_DIR=' + brew_prefix('openssl@3'),
             '-DDEFAULT_CHARSET=utf8mb4', '-DDEFAULT_COLLATION=utf8mb4_general_ci'],
            env=selected, log=evidence / 'mariadb-configure.log')
    command(['cmake', '--build', build, '--parallel', '2'], env=selected,
            log=evidence / 'mariadb-server-build.log', timeout=7200)
    command(['cmake', '--install', build], env=selected, log=evidence / 'mariadb-server-install.log')
    (root / '.cdeadmin-server-complete').write_text(ASSETS['mariadb-source'][1], encoding='utf-8')


def servers(evidence, env):
    ASSETS.update(SERVER_ASSETS)
    suffix = ('windows' if platform.system() == 'Windows' else
              'macos-' + ('arm64' if platform.machine() == 'arm64' else 'x64'))
    tasks = {
        'postgresql': lambda: postgres(evidence, env),
        'mysql': lambda: unpack('mysql-' + suffix, STATE / 'mysql'),
        'mysql-shell': lambda: unpack('mysql-shell-' + suffix, STATE / 'mysql-shell'),
        'mariadb': lambda: mariadb(evidence, env),
    }
    checks = []
    for name, action in tasks.items():
        result = {'component': name, 'status': 'failed'}
        try:
            action()
            result['status'] = 'passed'
        except Exception as error:
            result['error'] = str(error)
        checks.append(result)
    receipt = {'checks': checks, 'complete': all(c['status'] == 'passed' for c in checks),
               'admitted_assets': SERVER_ASSETS}
    (evidence / 'server-kits.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    if not receipt['complete']:
        raise RuntimeError('Native server/tool provisioning failed; see server-kits.json')
