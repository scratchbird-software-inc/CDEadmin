"""Pinned native client acquisition. Never extract clients from Linux images."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

from native import ROOT, STATE, command

ASSETS = {
    'python': ('https://www.python.org/ftp/python/3.14.8/Python-3.14.8.tar.xz',
               'c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73'),
    'sqlite': ('https://www.sqlite.org/2026/sqlite-amalgamation-3530000.zip',
               'bf3733d7c71b3ab0f6fd8a9ea0052ad87fa037d94333e14ce09878ba3492c3b0'),
    'mariadb-c': ('https://github.com/mariadb-corporation/mariadb-connector-c/archive/refs/tags/v3.4.8.tar.gz',
                  'ced7e5063c91fe2bfafd9d63a759490fe53e81df80599a9abad01c570c202f0c'),
    'mariadb-python': ('https://files.pythonhosted.org/packages/c4/ba/cedef19833be88e07bfff11964441cda8a998f1628dd3b2fa3e7751d36e0/mariadb-1.1.14.tar.gz',
                       'e6d702a53eccf20922e47f2f45cfb5c7a0c2c6c0a46e4ee2d8a80d0ff4a52f34'),
    'postgres-windows': ('https://get.enterprisedb.com/postgresql/postgresql-18.3-1-windows-x64-binaries.zip',
                         '4da1a93cbc69e99936616d53c34466f79e4295fc56134ce4a395e88351213d60'),
    'kerberos-windows': ('https://web.mit.edu/kerberos/dist/kfw/4.1/kfw-4.1-amd64.msi',
                         'cdcb7ec4addd9716c0e0c74fe0944cb97c83bfeebc2c267e63e8cac2ad3dc872'),
    'firebird-windows': ('https://github.com/FirebirdSQL/firebird/releases/download/v5.0.4/Firebird-5.0.4.1812-0-windows-x64.zip',
                         '01e844fce4d5f53272a76205dbc3a1ba4b782ab8e8eadcd808cdbccd9ce13b72'),
    'firebird-macos-x64': ('https://github.com/FirebirdSQL/firebird/releases/download/v5.0.4/Firebird-5.0.4.1812-0-macos-x64.pkg',
                           'f6b587d8d16f528b9ce94bf006e204cc171620fbb64b90730790e7af612c2325'),
    'firebird-macos-arm64': ('https://github.com/FirebirdSQL/firebird/releases/download/v5.0.4/Firebird-5.0.4.1812-0-macos-arm64.pkg',
                             '0c3495ec457720f3b3b51e1be0f36485f589732d6af38c9b04f1eb171d8d5509'),
}


def download(name):
    url, expected = ASSETS[name]
    cache = STATE / 'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / url.rsplit('/', 1)[1]
    if not target.exists():
        temporary = target.with_suffix(target.suffix + '.partial')
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as output:
            shutil.copyfileobj(source, output)
        temporary.replace(target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(f'{name} SHA-256 differs from the admitted native asset')
    return target


def msvc(env):
    """Import the developer compiler environment without printing its contents."""
    if platform.system() != 'Windows' or shutil.which('cl.exe', path=env['PATH']):
        return env
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    root = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
                                    '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                                    '-property', 'installationPath'], text=True).strip()
    if not root:
        raise RuntimeError('Install Visual Studio C++ Build Tools and Windows SDK')
    bat = Path(root) / 'Common7/Tools/VsDevCmd.bat'
    # Supply cmd.exe its complete command line: list2cmdline's extra escaping
    # of embedded quotes otherwise breaks a path under Program Files.
    result = subprocess.check_output(f'cmd.exe /d /s /c ""{bat}" -arch=x64 >nul && set"',
                                    text=True, errors='replace', env=env)
    selected = dict(env)
    for line in result.splitlines():
        key, sep, value = line.partition('=')
        if sep and key:
            selected[key.upper() if key.lower() == 'path' else key] = value
    return selected


def paths(env):
    selected = dict(env)
    additions = [STATE / 'mariadb-c/bin', STATE / 'mariadb-c/lib',
                 STATE / 'postgres/pgsql/bin', STATE / 'firebird']
    kerberos = STATE / 'kerberos'
    if kerberos.exists():
        additions += list({p.parent for p in kerberos.rglob('gssapi64.dll')})
    selected['PATH'] = os.pathsep.join([*(str(p) for p in additions), env['PATH']])
    selected['MARIADB_CC_INSTALL_DIR'] = str(STATE / 'mariadb-c')
    selected['PG_CONFIG'] = str(STATE / 'postgres/pgsql/bin/pg_config.exe') if os.name == 'nt' else selected.get('PG_CONFIG', 'pg_config')
    firebird = STATE / 'firebird'
    if platform.system() == 'Windows':
        selected['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(firebird / 'fbclient.dll')
    else:
        framework = Path('/Library/Frameworks/Firebird.framework/Versions/A')
        selected['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(framework / 'Libraries/libfbclient.dylib')
        selected['FIREBIRD'] = str(framework / 'Resources')
        selected['DYLD_LIBRARY_PATH'] = os.pathsep.join([
            str(STATE / 'sqlite'), str(STATE / 'mariadb-c/lib'),
            selected.get('DYLD_LIBRARY_PATH', '')])
    return selected


def clients(evidence, env):
    if platform.system() not in ('Windows', 'Darwin'):
        raise RuntimeError('Native client provisioning supports Windows and macOS')
    STATE.mkdir(exist_ok=True)
    env = msvc(env)
    if platform.system() == 'Windows':
        for asset, destination in [('postgres-windows', STATE / 'postgres'),
                                    ('firebird-windows', STATE / 'firebird')]:
            if not destination.exists():
                destination.mkdir()
                with zipfile.ZipFile(download(asset)) as archive:
                    archive.extractall(destination)
        kerberos = STATE / 'kerberos'
        if not kerberos.exists():
            command(['msiexec.exe', '/a', download('kerberos-windows'), '/qn',
                     'TARGETDIR=' + str(kerberos)], env=env,
                    log=evidence / 'kerberos-extract.log')
    else:
        # Installing the vendor framework runs package scripts and requires
        # administrator rights. Developers install the verified package once;
        # CI permits this only in its disposable GitHub-hosted VM.
        framework = Path('/Library/Frameworks/Firebird.framework')
        if not framework.exists():
            key = 'arm64' if platform.machine() == 'arm64' else 'x64'
            package = download('firebird-macos-' + key)
            if os.environ.get('GITHUB_ACTIONS') != 'true':
                raise RuntimeError(f'Install the verified Firebird package {package}, then rerun clients')
            command(['sudo', 'installer', '-pkg', package, '-target', '/'],
                    log=evidence / 'firebird-install.log')
    source = STATE / 'connector-source'
    prefix = STATE / 'mariadb-c'
    if not (prefix / '.cdeadmin-complete').is_file():
        if not source.exists():
            source.mkdir()
            with tarfile.open(download('mariadb-c')) as archive:
                archive.extractall(source, filter='data')
        tree = source / 'mariadb-connector-c-3.4.8'
        build = STATE / 'connector-build'
        command(['cmake', '-S', tree, '-B', build,
                 '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DWITH_UNIT_TESTS=OFF',
                 '-DWITH_SSL=' + ('SCHANNEL' if os.name == 'nt' else 'OPENSSL')],
                env=env, log=evidence / 'connector-configure.log')
        command(['cmake', '--build', build, '--config', 'Release', '--parallel', '3'],
                env=env, log=evidence / 'connector-build.log')
        command(['cmake', '--install', build, '--config', 'Release'],
                env=env, log=evidence / 'connector-install.log')
        (prefix / '.cdeadmin-complete').write_text(ASSETS['mariadb-c'][1], encoding='utf-8')
    sqlite = STATE / 'sqlite'
    sqlite.mkdir(exist_ok=True)
    if not (sqlite / 'sqlite3.c').exists():
        with zipfile.ZipFile(download('sqlite')) as archive:
            for name in ('sqlite3.c', 'sqlite3.h', 'sqlite3ext.h'):
                (sqlite / name).write_bytes(archive.read('sqlite-amalgamation-3530000/' + name))
    defines = ['SQLITE_THREADSAFE=1', 'SQLITE_ENABLE_FTS5', 'SQLITE_ENABLE_RTREE',
               'SQLITE_ENABLE_COLUMN_METADATA']
    if platform.system() == 'Windows':
        command(['cl.exe', '/nologo', '/O2', '/MD', '/LD',
                 '/DSQLITE_API=__declspec(dllexport)', *('/D' + d for d in defines),
                 'sqlite3.c', '/link', '/OUT:sqlite3.dll'], cwd=sqlite, env=env,
                log=evidence / 'sqlite-build.log')
    else:
        command(['cc', '-O2', '-dynamiclib', *('-D' + d for d in defines),
                 'sqlite3.c', '-o', 'libsqlite3.0.dylib',
                 '-install_name', '@rpath/libsqlite3.0.dylib'],
                cwd=sqlite, env=env, log=evidence / 'sqlite-build.log')
        alias = sqlite / 'libsqlite3.dylib'
        if not alias.exists():
            alias.symlink_to('libsqlite3.0.dylib')
    (evidence / 'assets.json').write_text(json.dumps(ASSETS, indent=2), encoding='utf-8')
    if platform.system() == 'Darwin':
        build_macos_python(evidence, env)


def build_macos_python(evidence, env):
    """Own CPython build links the required SQLite, never Apple's system copy."""
    prefix = STATE / 'python'
    if (prefix / '.cdeadmin-complete').is_file():
        return
    source = STATE / 'python-source'
    source.mkdir(exist_ok=True)
    if not (source / 'Python-3.14.8/configure').exists():
        with tarfile.open(download('python')) as archive:
            archive.extractall(source, filter='data')
    openssl = subprocess.check_output(['brew', '--prefix', 'openssl@3'], text=True).strip()
    sqlite = STATE / 'sqlite'
    selected = dict(env, LIBSQLITE3_CFLAGS='-I' + str(sqlite),
                    LIBSQLITE3_LIBS='-L' + str(sqlite) + ' -lsqlite3',
                    LDFLAGS='-Wl,-rpath,' + str(sqlite))
    build = STATE / 'python-build'
    build.mkdir(exist_ok=True)
    command([source / 'Python-3.14.8/configure', '--prefix=' + str(prefix),
             '--with-openssl=' + openssl, '--with-openssl-rpath=auto',
             '--with-ensurepip=install'], cwd=build, env=selected,
            log=evidence / 'python-configure.log')
    command(['make', '-j3'], cwd=build, env=selected, log=evidence / 'python-build.log')
    command(['make', 'install'], cwd=build, env=selected, log=evidence / 'python-install.log')
    command([prefix / 'bin/python3.14', '-c',
             'import sqlite3,ssl; assert sqlite3.sqlite_version == "3.53.0"; print(ssl.OPENSSL_VERSION)'],
            env=selected, log=evidence / 'python-runtime.log')
    (prefix / '.cdeadmin-complete').write_text(ASSETS['python'][1], encoding='utf-8')


def install_python_runtime_hook(python, env):
    """Load the owned Windows SQLite DLL before CPython imports _sqlite3."""
    if platform.system() != 'Windows':
        return
    if not (STATE / 'sqlite/sqlite3.dll').is_file():
        raise RuntimeError('Run clients successfully before installing Python dependencies')
    site = Path(subprocess.check_output([str(python), '-c',
                'import sysconfig;print(sysconfig.get_path("purelib"))'],
                env=env, text=True).strip())
    directories = [str(STATE / 'mariadb-c/lib'), str(STATE / 'mariadb-c/bin'),
                   str(STATE / 'postgres/pgsql/bin'),
                   str(STATE / 'firebird')]
    kerberos = STATE / 'kerberos'
    directories += [str(p.parent) for p in kerberos.rglob('gssapi64.dll')]
    source = ('# Generated by CDEadmin native development setup.\n'
              'import ctypes, os\n'
              f'_directories = {directories!r}\n'
              '_handles = [os.add_dll_directory(p) for p in _directories if os.path.isdir(p)]\n'
              f'_sqlite = ctypes.WinDLL({str(STATE / "sqlite/sqlite3.dll")!r})\n')
    target = site / '_cdeadmin_native_runtime.py'
    if target.exists() and not target.read_text(encoding='utf-8').startswith(
            '# Generated by CDEadmin native development setup.'):
        raise RuntimeError('Refusing to overwrite an unknown native runtime hook')
    target.write_text(source, encoding='utf-8')
    (site / 'cdeadmin_native_runtime.pth').write_text('import _cdeadmin_native_runtime\n', encoding='utf-8')
