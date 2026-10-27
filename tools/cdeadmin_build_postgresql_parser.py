"""Build the pinned PostgreSQL parser with native string-context options.

The patch exposes libpg_query's existing SQL parse flags and applies the same
flags to its offline PL/pgSQL compiler. Builds and wheels stay outside the repo.
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile

SOURCE_SHA256 = '3c560e38c28dc868b5a6efa9fd9e5dc83725dd21d7262968a7f9fa3f7446f31a'
LIBRARY_SHA256 = '2d8755e8544f65e3fe66c06be9bf658e1ba1c004765d332037e046332690b410'
LIBRARY_COMMIT = '776c2ac5efa2a736f45bc7f18e1fd06cb9c6504e'


def build(archive, library_archive, output):
    archive, output = archive.resolve(), output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if output == repository or repository in output.parents:
        raise ValueError('Parser build output must be outside the repository')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('pglast 8.5 source archive hash does not match')
    if hashlib.sha256(library_archive.read_bytes()).hexdigest() != LIBRARY_SHA256:
        raise ValueError('Pinned libpg_query source archive hash does not match')
    output.mkdir(parents=True, exist_ok=False)
    patch = repository / 'tools/driver_patches/pglast-8.5-native-options.patch'
    with tarfile.open(archive) as source:
        source.extractall(output / 'source', filter='data')
    tree = output / 'source/pglast-8.5'
    # Upstream's 8.5 sdist omits UPB generated headers and Makefile.msvc.
    # Restore only its exact git submodule revision, checking every overlapping
    # file before copying. This also makes the same build usable on Windows.
    with tarfile.open(library_archive) as source:
        source.extractall(output / 'library', filter='data')
    library = output / 'library' / ('libpg_query-' + LIBRARY_COMMIT)
    for path in library.rglob('*'):
        target = tree / 'libpg_query' / path.relative_to(library)
        if path.is_file() and target.is_file() and path.read_bytes() != target.read_bytes():
            raise ValueError('pglast sdist and pinned library sources differ: ' + str(path.relative_to(library)))
    shutil.copytree(library, tree / 'libpg_query', dirs_exist_ok=True)
    temporary = output / 'tmp'; temporary.mkdir()
    env = dict(os.environ, TMPDIR=str(temporary), TEMP=str(temporary), TMP=str(temporary),
               PIP_CACHE_DIR=str(output / 'pip-cache'), PYTHONDONTWRITEBYTECODE='1')
    with (output / 'build.log').open('wb') as log:
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True,
                       stdout=log, stderr=subprocess.STDOUT, env=env)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True,
                       stdout=log, stderr=subprocess.STDOUT, env=env)
        subprocess.run([sys.executable, '-B', '-m', 'pip', 'wheel', '--no-deps', str(tree),
                        '--wheel-dir', str(output / 'wheels')], cwd=tree, check=True,
                       stdout=log, stderr=subprocess.STDOUT, env=env)
    wheels = list((output / 'wheels').glob('*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one native PostgreSQL parser wheel')
    receipt = {'source_sha256': SOURCE_SHA256,
               'library_commit': LIBRARY_COMMIT, 'library_sha256': LIBRARY_SHA256,
               'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
               'python': sys.version, 'platform': sys.platform,
               'wheel': wheels[0].name, 'wheel_sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
               'runtime_qualified': False}
    (output / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return wheels[0]


def qualify(wheel, output):
    """Install the built wheel into an owned environment and exercise its ABI."""
    output.mkdir(parents=True, exist_ok=False)
    environment = output / 'environment'
    with (output / 'qualification.log').open('wb') as log:
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
        interpreter = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(interpreter), '-m', 'pip', 'install', '--no-deps', str(wheel)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([str(interpreter), '-B', str(Path(__file__).with_name('cdeadmin_postgresql_parser_runtime_gate.py')),
                        '--output', str(output / 'summary.json')], check=True, stdout=log, stderr=subprocess.STDOUT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--library-archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qualify', action='store_true', help='Qualify the built wheel in a new owned Python environment')
    args = parser.parse_args()
    wheel = build(args.archive, args.library_archive, args.output)
    if args.qualify:
        qualify(wheel, args.output.resolve() / 'qualification')
    print(wheel)
