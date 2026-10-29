"""Rebuild standalone GPL DDN in isolation, excluding commercial Weaver code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import importlib.util
from ddn_toolchain import resolve as resolve_tools

CONTRACT = 'ddn-next-1'
INPUT_TREES = ('project/ddn/', 'project/tests/ddn/')
BUILD_TOOLS = ('context', 'run', 'ddn-boundary', 'ddn-distribution',
               'ddn-bundle', 'ddn-modular', 'ddn-fonts', 'ddn-license',
               'runtime-packages')
INPUT_FILES = {'package.json', 'tsconfig.base.json',
    'docs/Weaver-Specifications/implementation/contracts/library-lock.json',
    *(f'docs/Weaver-Specifications/reference/planning/2026-10-property-codex/{name}.json' for name in ('profile-contracts','property-codex','ddn.schema','role-contracts','core-contracts','relation-contracts','css-map')),
    *(f'tooling/workspace/{name}.mjs' for name in BUILD_TOOLS)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def inventory(source):
    paths = git(source, 'ls-files', '-z', '--cached', '--others',
                '--exclude-standard').decode().split('\0')
    files = {}
    for name in sorted(set(paths) - {''}):
        if name not in INPUT_FILES and not name.startswith(INPUT_TREES):
            continue
        path = source / name
        if path.is_symlink():
            raise RuntimeError(f'DDN input symlink requires review: {name}')
        if path.is_file():
            files[name] = digest(path)
    missing = INPUT_FILES - files.keys()
    if missing:
        raise RuntimeError('Unsupported ScratchWeaver DDN source: ' + ', '.join(sorted(missing)))
    return {'revision': git(source, 'rev-parse', 'HEAD').decode().strip(),
            'subtree': 'project/ddn',
            'status': git(source, 'status', '--porcelain', '--',
                          *INPUT_TREES, *sorted(INPUT_FILES)).decode(),
            'files': files}


def artifact_paths(root):
    return sorted(p for p in root.rglob('*')
                  if p.is_file() and p.name != 'resource-manifest.json')


def verify_artifacts(root, manifest):
    artifacts = manifest.get('artifacts') or {}
    if manifest.get('contract') != CONTRACT or not artifacts:
        raise RuntimeError('The bundled DDN contract is obsolete; refresh from ScratchWeaver')
    for name, sha in artifacts.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise RuntimeError('Invalid DDN artifact path')
        actual = root / path
        if actual.is_symlink() or not actual.is_file() or digest(actual) != sha:
            raise RuntimeError(f'DDN artifact missing or stale: {name}')
    if {p.relative_to(root).as_posix() for p in artifact_paths(root)} != set(artifacts):
        raise RuntimeError('DDN distribution contains unrecorded artifacts')


def _copy_tool(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
    return target


def refresh(source, work, destination, intake_tool):
    if os.environ.get('SCRATCHROBIN_DDN_OFFLINE', '').lower() in ('1', 'true', 'yes'):
        raise RuntimeError('Builds require current ScratchWeaver source; offline checks are inspection only')
    before = inventory(source)
    patch = Path(__file__).parent / 'dependency_patches/ddn_next_native_geometry.py'
    review = patch.with_name('ddn-next-native-geometry.md')
    tool_hashes = {p.name: digest(p) for p in (Path(__file__), intake_tool, patch, review, Path(__file__).with_name('ddn_toolchain.py'))}
    pinned_node, typescript, tool_receipts = resolve_tools(source, work)
    node_name = 'node/node.exe' if os.name == 'nt' else 'node/bin/node'
    compiler = {'node': digest(pinned_node), 'typescript': digest(typescript / 'lib/typescript.js')}
    manifest_path = destination / 'resource-manifest.json'
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if (previous.get('source') == before and previous.get('intake_tools') == tool_hashes
                and previous.get('compiler') == compiler):
            verify_artifacts(destination, previous)
            print('DDN current standalone snapshot verified:', before['revision'])
            return previous
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='capture-', dir=work) as temporary:
        snapshot = Path(temporary) / 'source'
        for name, sha in before['files'].items():
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
            if digest(target) != sha:
                raise RuntimeError('DDN changed during capture; retry intake')
        if inventory(source) != before:
            raise RuntimeError('DDN changed during capture; retry intake')
        spec = importlib.util.spec_from_file_location('ddn_geometry_patch', patch)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.apply(snapshot)
        subprocess.run([sys.executable, '-B', 'project/ddn/packages/profiles/tools/generate.py'], cwd=snapshot, check=True, capture_output=True)
        patched = {name: digest(snapshot / name) for name in before['files'] if digest(snapshot / name) != before['files'][name]}
        isolated_tools = snapshot / '.work/tools/toolchain'
        node = _copy_tool(pinned_node, isolated_tools / node_name)
        shutil.copytree(typescript, isolated_tools / 'typescript', copy_function=_copy_tool)
        env = dict(os.environ)
        for key in ('WEAVER_ROOT', 'WEAVER_WORKAREA', 'ARTIFACT_ROOT',
                    'WEAVER_BUILD_ROOT', 'WEAVER_DDN_BUILD_ROOT'):
            env.pop(key, None)
        env.update(TMPDIR=str(snapshot / '.work/tmp'), TMP=str(snapshot / '.work/tmp'),
                   TEMP=str(snapshot / '.work/tmp'), PYTHONDONTWRITEBYTECODE='1')
        log = work / 'build.log'
        try:
            with log.open('w', encoding='utf-8') as output:
                subprocess.run([str(node), 'tooling/workspace/run.mjs', 'build:ddn'],
                               cwd=snapshot, env=env, stdout=output,
                               stderr=subprocess.STDOUT, check=True)
        except subprocess.CalledProcessError:
            print(log.read_text(encoding='utf-8', errors='replace'))
            raise
        built = snapshot / '.work/builds/ddn-distribution'
        stage = Path(temporary) / 'distribution'
        for name in ('modules', 'modular'):
            shutil.copytree(built / name, stage / name)
        (stage / 'package.json').write_text(json.dumps({
            'type': 'module', 'private': True, 'license': 'GPL-2.0-or-later'}) + '\n')
        (stage / 'complete').mkdir()
        for name in ('ddn-viewer.js', 'ddn-visual-designer.js', 'ddn-verifier.js'):
            shutil.copy2(built / 'complete' / name, stage / 'complete' / name)
        for name in ('LICENSE', 'NOTICE.md'):
            shutil.copy2(snapshot / 'project/ddn' / name, stage / name)
        modular = json.loads((stage / 'modular/manifest.json').read_text())
        (stage / 'integration.json').write_text(json.dumps({
            'contract': CONTRACT, 'api': '1.0', 'release': modular['releaseHash']}) + '\n')
        manifest = {'contract': CONTRACT, 'api': '1.0', 'version': CONTRACT,
                    'license': 'GPL-2.0-or-later', 'source': before,
                    'intake_tools': tool_hashes, 'compiler': compiler,
                    'tool_artifacts': tool_receipts,
                    'release_hash': modular['releaseHash'],
                    'consumer_patches': {'native_geometry': {'tool': digest(patch), 'review': digest(review), 'changed_inputs': patched}},
                    'artifacts': {p.relative_to(stage).as_posix(): digest(p)
                                  for p in artifact_paths(stage)}}
        (stage / 'resource-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        verify_artifacts(stage, manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(stage, destination)
        print('DDN standalone runtime, verifier and designer refreshed:', CONTRACT, before['revision'])
        return manifest
