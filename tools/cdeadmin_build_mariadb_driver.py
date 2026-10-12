"""Build the pinned opt-in MariaDB connector extension outside the source tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

SOURCE_SHA256 = (
    'e6d702a53eccf20922e47f2f45cfb5c7a0c2c6c0a46e4ee2d8a80d0ff4a52f34')


def build(archive, output):
    archive, output = archive.resolve(), output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if output == repository or repository in output.parents:
        raise ValueError('Build output must be outside the repository')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('MariaDB 1.1.14 source archive hash does not match')
    output.mkdir(parents=True, exist_ok=False)
    patch = repository / (
        'tools/driver_patches/mariadb-1.1.14-exact-temporals.patch')
    with tarfile.open(archive) as source:
        source.extractall(output / 'source', filter='data')
    tree = output / 'source/mariadb-1.1.14'
    temporary = output / 'tmp'
    temporary.mkdir()
    env = dict(os.environ, TMPDIR=str(temporary), TEMP=str(temporary),
               TMP=str(temporary), PIP_CACHE_DIR=str(output / 'pip-cache'),
               PYTHONDONTWRITEBYTECODE='1')
    with (output / 'build.log').open('wb') as log:
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree,
                       check=True, stdout=log,
                       stderr=subprocess.STDOUT, env=env)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True,
                       stdout=log, stderr=subprocess.STDOUT, env=env)
        subprocess.run([sys.executable, '-B', '-m', 'pip', 'wheel',
                        '--no-deps', '--no-build-isolation', str(tree),
                        '--wheel-dir', str(output / 'wheels')], cwd=tree,
                       check=True, stdout=log,
                       stderr=subprocess.STDOUT, env=env)
    wheels = list((output / 'wheels').glob('*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one native connector wheel')
    receipt = {'source_sha256': SOURCE_SHA256,
               'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
               'python': sys.version, 'platform': sys.platform,
               'wheel': wheels[0].name,
               'wheel_sha256': hashlib.sha256(
                   wheels[0].read_bytes()).hexdigest(),
               'runtime_qualified': False}
    (output / 'build.json').write_text(json.dumps(receipt, indent=2))
    return wheels[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.archive, args.output))
