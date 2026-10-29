#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Build every tracked SQLite version and the native helpers it supports.

Owner direction, 2026-10-29: SQLite is supported from a declared floor.
``sqlite_tracked_versions.json`` lists the tracked versions with their
sqlite.org archives, check-ins and hashes. For each version this downloads
(or reuses) the archives, verifies SHA-256 of the archive and SHA3-256 of
the amalgamation, builds a runtime with the shared recipe
(``build_sqlite_tracked_runtime.sh``) under ``runtime/sqlite-tracked/<v>``,
and builds each native helper whose minimum the version meets.

Opt-in: ``bootstrap.py --sqlite-tracked`` or run this file directly. The
default bootstrap reference build (``runtime/sqlite-3.53.0``) is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
RUNTIME = ROOT / 'runtime'
TRACKED = RUNTIME / 'sqlite-tracked'
MANIFEST = ROOT / 'sqlite_tracked_versions.json'
RECIPE = ROOT / 'build_sqlite_tracked_runtime.sh'


def manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def version_key(text):
    return tuple(int(part) for part in str(text).split('.'))


def run(command, *, cwd=None):
    print('+', ' '.join(str(item) for item in command), flush=True)
    subprocess.run([str(item) for item in command], cwd=cwd, check=True)


def require(*programs):
    missing = [name for name in programs if not shutil.which(name)]
    if missing:
        raise RuntimeError(
            'required programs are not installed: ' + ', '.join(missing))


def _fetch(url, digest, cache):
    """Return a cached or downloaded archive whose SHA-256 is ``digest``."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / url.rsplit('/', 1)[-1]
    if not path.is_file():
        print(f'+ download {url}', flush=True)
        urllib.request.urlretrieve(url, path)
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != digest:
        raise RuntimeError(f'{path.name} SHA-256 mismatch: {observed}')
    return path


def _source_tree(entry, work, cache):
    archive = _fetch(entry['source_archive'],
                     entry['source_archive_sha256'], cache)
    with zipfile.ZipFile(archive) as source:
        source.extractall(work / 'source')
    root = next((work / 'source').iterdir())
    # Zip extraction drops mode bits; the configure wrappers run directly.
    for name in ('configure', 'autosetup/autosetup',
                 'autosetup/autosetup-find-tclsh'):
        if (root / name).exists():
            (root / name).chmod(0o755)
    if (root / 'manifest.uuid').read_text().strip() != entry['check_in']:
        raise RuntimeError(f'{archive.name} is not check-in '
                           f'{entry["check_in"]}')
    return root


def _amalgamation(version, entry, work, cache):
    """Directory holding sqlite3.c, shell.c, sqlite3.h and sqlite3ext.h."""
    if entry.get('amalgamation_archive'):
        archive = _fetch(entry['amalgamation_archive'],
                         entry['amalgamation_archive_sha256'], cache)
        with tarfile.open(archive) as source:
            source.extractall(work / 'amalgamation', filter='data')
        directory = next((work / 'amalgamation').iterdir())
    else:
        require('tclsh', 'make', 'cc')
        root = _source_tree(entry, work, cache)
        directory = work / 'amalgamation'
        directory.mkdir()
        run([root / 'configure'], cwd=directory)
        run(['make', 'sqlite3.c', 'shell.c'], cwd=directory)
    observed = hashlib.sha3_256(
        (directory / 'sqlite3.c').read_bytes()).hexdigest()
    if observed != entry['sqlite3_c_sha3_256']:
        raise RuntimeError(f'SQLite {version} sqlite3.c SHA3-256 mismatch')
    return directory


def _runtime_ready(version, prefix):
    cli = prefix / 'bin/sqlite3'
    if not (cli.is_file() and (prefix / 'lib/libsqlite3.so').exists()):
        return False
    reported = subprocess.check_output([str(cli), '--version'], text=True)
    return reported.split()[0] == version


def _build_helpers(version, prefix, helpers, recover_source, work):
    built = {}
    for component, spec in sorted(helpers.items()):
        if version_key(version) < version_key(spec['minimum']):
            continue
        target = prefix / 'helpers' / component
        if (target / spec['library']).is_file():
            built[component] = str(target / spec['library'])
            continue
        build = work / ('helper-' + component)
        command = [
            'cmake', '-S', REPOSITORY / 'tools/native' / spec['directory'],
            '-B', build, '-DCMAKE_BUILD_TYPE=Release',
            f'-DSQLite3_INCLUDE_DIR={prefix / "include"}',
            f'-DSQLite3_LIBRARY={prefix / "lib/libsqlite3.so"}',
        ]
        if spec.get('recover_source_version'):
            command.append(f'-DSCRATCHROBIN_SQLITE_SOURCE={recover_source}')
        run(command)
        run(['cmake', '--build', build])
        target.mkdir(parents=True, exist_ok=True)
        for name in (spec['library'], spec['library'] + '.json'):
            shutil.copy2(build / name, target / name)
        built[component] = str(target / spec['library'])
    return built


def build_tracked(versions=None, cache=None):
    """Build the requested tracked versions (default: all) and helpers."""
    data = manifest()
    selected = sorted(versions or data['versions'], key=version_key)
    unknown = set(selected) - set(data['versions'])
    if unknown:
        raise RuntimeError('not tracked: ' + ', '.join(sorted(unknown)))
    require('cc', 'cmake')
    cache = Path(cache) if cache else TRACKED / 'archives'
    receipts = {}
    with tempfile.TemporaryDirectory(prefix='cdeadmin-sqlite-tracked-') as tmp:
        work = Path(tmp)
        recover_version = {
            spec['recover_source_version']
            for spec in data['helpers'].values()
            if spec.get('recover_source_version')}.pop()
        recover_source = _source_tree(
            data['versions'][recover_version], work / 'recover', cache)
        for version in selected:
            entry = data['versions'][version]
            prefix = TRACKED / version
            if not _runtime_ready(version, prefix):
                amalgamation = _amalgamation(
                    version, entry, work / version, cache)
                run(['bash', RECIPE, version, amalgamation, prefix])
            if not _runtime_ready(version, prefix):
                raise RuntimeError(f'SQLite {version} runtime did not build')
            helpers = _build_helpers(
                version, prefix, data['helpers'], recover_source,
                work / version)
            receipts[version] = {
                'prefix': str(prefix), 'check_in': entry['check_in'],
                'helpers': helpers}
            (prefix / 'BUILD.json').write_text(
                json.dumps(receipts[version], indent=2, sort_keys=True) +
                '\n', encoding='utf-8')
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='append', dest='versions',
                        help='tracked version to build (repeatable)')
    parser.add_argument('--archive-cache', type=Path,
                        help='directory of already downloaded archives')
    options = parser.parse_args()
    receipts = build_tracked(options.versions, options.archive_cache)
    print(json.dumps(receipts, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
