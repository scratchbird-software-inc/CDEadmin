"""Build the pinned native MySQL query-attribute correction outside the repo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

SOURCE_SHA256 = 'd8ff5ee236ea46661ee639336323e124ed868e37f3ea991bdc5de5a146f39fd5'
SOURCE_URL = ('https://files.pythonhosted.org/packages/f2/ce/'
    'a53b169388f8c6a595cfa9a653138381f3afef1d2af60f5c1972d015f52f/'
    'mysql_connector_python-26.7.0.tar.gz')


def build(archive, mysql_capi, output):
    archive, mysql_capi, output = archive.resolve(), mysql_capi.resolve(), output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if output == repository or repository in output.parents:
        raise ValueError('Build output must be outside the repository')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Connector/Python 26.7.0 source archive hash differs')
    header = mysql_capi / 'include/mysql_version.h'
    if not header.is_file():
        header = mysql_capi / 'include/mysql/mysql_version.h'
    if not header.is_file() or not re.search(r'^#define\s+MYSQL_VERSION_ID\s+90700\s*$', header.read_text(), re.M):
        raise ValueError('Select the matching native MySQL 9.7.0 C API development kit')
    output.mkdir(parents=True, exist_ok=False)
    patch = repository / 'tools/driver_patches/mysql-connector-python-26.7.0-query-attributes.patch'
    with tarfile.open(archive) as source:
        source.extractall(output / 'source', filter='data')
    tree = output / 'source/mysql_connector_python-26.7.0'
    temporary = output / 'tmp'
    temporary.mkdir()
    env = dict(os.environ, MYSQL_CAPI=str(mysql_capi), TMPDIR=str(temporary),
        TEMP=str(temporary), TMP=str(temporary), PIP_CACHE_DIR=str(output / 'pip-cache'),
        PYTHONDONTWRITEBYTECODE='1', GIT_CEILING_DIRECTORIES=str(output / 'source'))
    with (output / 'build.log').open('wb') as log:
        for args in (['git', 'apply', '--check', str(patch)], ['git', 'apply', str(patch)],
                [sys.executable, '-B', '-m', 'pip', 'wheel', '--no-deps',
                 '--no-build-isolation', str(tree), '--wheel-dir', str(output / 'wheels')]):
            subprocess.run(args, cwd=tree, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
    wheels = list((output / 'wheels').glob('*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one patched native MySQL connector wheel')
    with zipfile.ZipFile(wheels[0]) as wheel:
        if not any(Path(name).name.startswith('_mysql_connector.') and name.endswith(('.so', '.pyd'))
                for name in wheel.namelist()):
            raise RuntimeError('The wheel lacks the native C extension')
    sources = ['src/mysql_capi.c', 'src/include/mysql_capi.h', 'src/mysql_connector.c']
    receipt = {'source_url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
        'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'patched_source_sha256': {name: hashlib.sha256((tree / name).read_bytes()).hexdigest() for name in sources},
        'mysql_capi_root': str(mysql_capi), 'mysql_capi_version': '9.7.0',
        'mysql_capi_version_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
        'python': sys.version, 'platform': sys.platform, 'wheel': wheels[0].name,
        'wheel_sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
        'expected_native_query_attributes_abi': 1, 'runtime_qualified': False}
    (output / 'build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return wheels[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--mysql-capi', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.archive, args.mysql_capi, args.output))
