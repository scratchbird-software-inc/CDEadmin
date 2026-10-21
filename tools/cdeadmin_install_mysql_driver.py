"""Install the pinned corrected MySQL C connector in a Linux virtual environment.

The temporary SDK is extracted without package installation or server startup.
Only a current receipt survives; source build intermediates are disposable.
Windows and macOS use tools/development/native.py instead.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from tools.cdeadmin_build_mysql_driver import SOURCE_SHA256, SOURCE_URL

ROOT = Path(__file__).resolve().parents[1]
SDK_BASE = 'https://repo.mysql.com/apt/ubuntu/pool/mysql-9.7-lts/m/mysql-community/'
SDK_PACKAGES = (
    ('libmysqlclient-dev', 'fe5eb99be424317e066827c522e23defd256169b8870bd853e3cc4155b871d54'),
    ('libmysqlclient24', '482b2493d0e202cd82e382a644666d48d16de15d35c0da0caa4540dfb4df46bc'),
    ('mysql-community-client-plugins', '90611034d90670d3bd316095ae82e0eec26a2c96a33a15ebe55a6867438dbe39'),
)
PROBE = '''import hashlib,json,sys
import mysql.connector,_mysql_connector
path=_mysql_connector.__file__
print(json.dumps({'connector_version':mysql.connector.__version__,
 'native_query_attributes_abi':getattr(_mysql_connector,'CDEADMIN_QUERY_ATTRIBUTES_ABI',None),
 'native_client_version':_mysql_connector.MySQL().get_client_info(),
 'extension_sha256':hashlib.sha256(open(path,'rb').read()).hexdigest(),
 'python_cache_tag':sys.implementation.cache_tag}))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url, checksum, path):
    with urllib.request.urlopen(url, timeout=120) as response, path.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    if sha(path) != checksum:
        raise ValueError('Pinned MySQL source or SDK download hash differs: ' + path.name)


def acquire_sdk(directory):
    family, version = platform.libc_ver()
    if (platform.system() != 'Linux' or platform.machine().lower() not in {'x86_64', 'amd64'} or
            family != 'glibc' or tuple(int(p) for p in version.split('.')[:2]) < (2, 39) or
            not shutil.which('dpkg-deb')):
        raise ValueError('Automatic MySQL SDK extraction requires Linux x86_64, glibc2.39+ and dpkg-deb; select --mysql-capi for another matching native SDK')
    records = []
    for package, checksum in SDK_PACKAGES:
        name = package + '_9.7.0-1ubuntu24.04_amd64.deb'
        url = SDK_BASE + name; archive = directory / name
        download(url, checksum, archive)
        metadata = subprocess.check_output(['dpkg-deb', '-f', str(archive), 'Package', 'Version', 'Architecture'], text=True)
        if ('Package: ' + package + '\n' not in metadata or 'Version: 9.7.0-1ubuntu24.04\n' not in metadata or
                'Architecture: amd64\n' not in metadata):
            raise ValueError('Pinned native MySQL SDK package metadata differs')
        subprocess.run(['dpkg-deb', '-x', str(archive), str(directory / 'sdk')], check=True)
        records.append({'url': url, 'sha256': checksum, 'metadata': metadata})
    return directory / 'sdk/usr', records


def probe(target=None):
    env = dict(os.environ)
    if target is not None:
        env['PYTHONPATH'] = str(target) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, '-B', '-c', PROBE], capture_output=True, text=True, env=env)
    if result.returncode:
        return None
    value = json.loads(result.stdout)
    if (value.get('connector_version') != '26.7.0' or value.get('native_query_attributes_abi') != 1 or
            value.get('native_client_version') != '9.7.0'):
        return None
    return value


def install(receipt, *, mysql_capi=None, archive=None, target=None):
    if platform.system() != 'Linux':
        raise ValueError('Use native.py for the Windows/macOS connector build')
    if target is None and sys.prefix == sys.base_prefix:
        raise ValueError('Install in a virtual environment or select an isolated --target')
    receipt = receipt.resolve(); target = target.resolve() if target is not None else None
    if archive is not None and sha(archive.resolve()) != SOURCE_SHA256:
        raise ValueError('Connector/Python 26.7.0 source archive hash differs')
    patch = ROOT / 'tools/driver_patches/mysql-connector-python-26.7.0-query-attributes.patch'
    patch_sha = sha(patch); current = probe(target)
    if receipt.is_file():
        saved = json.loads(receipt.read_text())
        if (saved.get('source_sha256') == SOURCE_SHA256 and saved.get('patch_sha256') == patch_sha and
                saved.get('installed') == current and current is not None):
            return saved
    # Builds and SDK packages never accumulate under the working checkout.
    with tempfile.TemporaryDirectory(prefix='scratchrobin-mysql-driver-') as temporary:
        directory = Path(temporary)
        sdk_records = []
        if mysql_capi is None:
            mysql_capi, sdk_records = acquire_sdk(directory)
        else:
            mysql_capi = mysql_capi.resolve()
        if archive is None:
            archive = directory / 'mysql_connector_python-26.7.0.tar.gz'
            download(SOURCE_URL, SOURCE_SHA256, archive)
        else:
            archive = archive.resolve()
        output = directory / 'build'
        try:
            subprocess.run([sys.executable, '-B', '-m', 'tools.cdeadmin_build_mysql_driver',
                '--archive', str(archive), '--mysql-capi', str(mysql_capi), '--output', str(output)], cwd=ROOT, check=True)
        except subprocess.CalledProcessError:
            log = output / 'build.log'
            if log.is_file():
                # Retain one bounded current failure, not a build history.
                receipt.parent.mkdir(parents=True, exist_ok=True)
                with log.open('rb') as stream:
                    stream.seek(max(0, log.stat().st_size - 128 * 1024))
                    receipt.with_suffix('.failure.log').write_bytes(stream.read(128 * 1024))
            raise
        wheels = list((output / 'wheels').glob('*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected exactly one corrected native MySQL wheel')
        command = [sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall']
        if target is not None:
            command += ['--target', str(target), '--upgrade']
        subprocess.run([*command, str(wheels[0])], check=True)
        installed = probe(target)
        if installed is None:
            raise RuntimeError('The installed MySQL connector lacks the admitted native ABI/client version')
        built = json.loads((output / 'build.json').read_text())
        value = {'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256, 'patch_sha256': patch_sha,
            'wheel_sha256': built['wheel_sha256'], 'patched_source_sha256': built['patched_source_sha256'],
            'sdk_packages': sdk_records, 'sdk_version_header_sha256': built['mysql_capi_version_header_sha256'],
            'installed': installed, 'native_runtime_import_qualified': True,
            'engine_functionality_qualified_by_this_installation': False,
            'temporary_build_and_sdk_retained': False}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary_receipt = receipt.with_suffix('.tmp')
    temporary_receipt.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary_receipt, receipt)
    receipt.with_suffix('.failure.log').unlink(missing_ok=True)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--mysql-capi', type=Path, default=os.environ.get('SCRATCHROBIN_MYSQL_CAPI'))
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    result = install(args.receipt, mysql_capi=args.mysql_capi, archive=args.archive, target=args.target)
    print(json.dumps({'native_runtime_import_qualified': result['native_runtime_import_qualified'],
        'native_query_attributes_abi': result['installed']['native_query_attributes_abi']}))
