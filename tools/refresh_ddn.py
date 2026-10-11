#!/usr/bin/env python3
"""Capture and rebuild the current sister-project SDK/tool without editing it.

Run before builds and commit-validation tests. A verified input/artifact match
reuses the immutable bundle; changed inputs rebuild both runtime and tool.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(os.environ.get('SCRATCHROBIN_DDN_SOURCE',
                                    '/home/dcalford/Sandbox/Diagram-Design-Notation'))
DEFAULT_WORK = Path(os.environ.get('SCRATCHROBIN_DDN_WORK',
                                  '/home/dcalford/SandBox/temp-workarea/ddn-intake'))
DEST = ROOT / 'web/pgadmin/static/vendor/ddn/current'


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(source):
    # Include uncommitted and untracked source, never ignored caches/dependencies.
    paths = git(source, 'ls-files', '-z', '--cached', '--others',
                '--exclude-standard').decode().split('\0')
    files = {}
    for name in sorted(set(paths) - {''}):
        path = source / name
        if path.is_symlink():
            raise RuntimeError(f'Source symlink requires intake review: {name}')
        if path.is_file():
            files[name] = digest(path)
    return {'revision': git(source, 'rev-parse', 'HEAD').decode().strip(),
            'status': git(source, 'status', '--porcelain').decode(),
            'files': files}


def refresh(source, work):
    work.mkdir(parents=True, exist_ok=True)
    before = inventory(source)
    manifest_path = DEST / 'resource-manifest.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if (previous.get('intake_tool_sha256') == digest(Path(__file__)) and
            previous.get('source') == before and all(
            (DEST / name).is_file() and digest(DEST / name) == sha
            for name, sha in previous.get('artifacts', {}).items()
        ) and previous.get('artifacts')):
            print('DDN current snapshot verified:', before['revision'])
            return
    with tempfile.TemporaryDirectory(prefix='capture-', dir=work) as scratch:
        snapshot = Path(scratch) / 'source'
        snapshot.mkdir()
        for name in before['files']:
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
            if digest(target) != before['files'][name]:
                raise RuntimeError('DDN changed during capture; retry intake')
        if inventory(source) != before:
            raise RuntimeError('DDN changed during capture; retry intake')
        # Build tools consume pinned installed dependencies without modifying them.
        (snapshot / 'node_modules').symlink_to(source / 'node_modules',
                                             target_is_directory=True)
        env = {**os.environ, 'TMPDIR': str(work)}
        env.pop('DDN_SDK_OUT', None)
        env.pop('DDN_SDK_MANIFEST', None)
        log = work / 'build.log'
        with log.open('w') as output:
            for tool in ('build-sdk.js', 'build-tool.js'):
                subprocess.run(['node', 'tools/' + tool], cwd=snapshot,
                               env=env, stdout=output,
                               stderr=subprocess.STDOUT, check=True)
        stage = Path(scratch) / 'vendor'
        stage.mkdir()
        for name in ('ddn.global.js', 'ddn.global.min.js', 'ddn.global.min.js.map',
                     'ddn.mjs', 'ddn.d.ts', 'ddn.d.mts', 'ddn.css', 'README.md'):
            shutil.copy2(snapshot / 'notation/dist' / name, stage / name)
        shutil.copy2(snapshot / 'notation/tool/ddn-tool.html', stage)
        shutil.copy2(snapshot / 'release/validation/sdk-build.json',
                     stage / 'sdk-build.json')
        for name in ('LICENSE', 'NOTICE'):
            matches = list(snapshot.glob(name + '*'))
            for path in matches:
                if path.is_file():
                    shutil.copy2(path, stage / path.name)
        package = json.loads((snapshot / 'package.json').read_text())
        manifest = {'version': package['version'], 'license': package['license'],
                    'intake_tool_sha256': digest(Path(__file__)),
                    'source': before,
                    'artifacts': {p.name: digest(p) for p in sorted(stage.iterdir())}}
        (stage / 'resource-manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n')
        DEST.parent.mkdir(parents=True, exist_ok=True)
        # Capture/build failures never overwrite the last admitted bundle.
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.copytree(stage, DEST)
        print('DDN runtime and unified tool refreshed:', package['version'],
              before['revision'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    args = parser.parse_args()
    refresh(args.source.resolve(), args.work.resolve())
