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
from ddn_toolchain import optimizer as resolve_optimizer, resolve as resolve_tools

CONTRACT = 'ddn-next-1'
INPUT_TREES = ('project/ddn/', 'project/tests/ddn/')
BUILD_TOOLS = ('context', 'run', 'ddn-boundary', 'ddn-distribution',
               'ddn-bundle', 'ddn-modular', 'ddn-fonts', 'ddn-license',
               'runtime-packages', 'ddn-optimize', 'ddn-shells')
# Owner direction 2026-11-03: DDN comes only from the public
# Diagram-Design-Notation repository, in its public contract layout.
INPUT_FILES = {'package.json', 'tsconfig.base.json',
    'tooling/bootstrap/library-lock.json',
    *(f'standard/codex/{name}.json' for name in ('profile-contracts','property-codex','ddn.schema','role-contracts','core-contracts','relation-contracts','css-map')),
    'tooling/optimizer/package.json', 'tooling/optimizer/package-lock.json',
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
        raise RuntimeError('Unsupported public DDN source: ' + ', '.join(sorted(missing)))
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
        raise RuntimeError('The bundled DDN contract is obsolete; refresh from the public DDN repository')
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
        raise RuntimeError('Builds require the current public DDN source; offline checks are inspection only')
    before = inventory(source)
    patch = Path(__file__).parent / 'dependency_patches/ddn_next_native_geometry.py'
    review = patch.with_name('ddn-next-native-geometry.md')
    # Owner direction 2026-11-07: ScratchRobin may extend its DDN capture
    # without changing the public DDN repository; each extension is a
    # reviewed consumer patch recorded in the manifest.
    cache_patch = patch.with_name('ddn_registry_pack_cache.py')
    cache_review = patch.with_name('ddn-registry-pack-cache.md')
    cube_patch = patch.with_name('ddn_cube_dimensional.py')
    cube_review = patch.with_name('ddn-cube-dimensional.md')
    bi_patch = patch.with_name('ddn_bi_analytics.py')
    bi_review = patch.with_name('ddn-bi-analytics.md')
    screen_patch = patch.with_name('ddn_screen_mesh.py')
    screen_review = patch.with_name('ddn-screen-mesh.md')
    tool_files = (
        Path(__file__), intake_tool, patch, review,
        cache_patch, cache_review, cube_patch, cube_review,
        bi_patch, bi_review, screen_patch, screen_review,
        Path(__file__).with_name('ddn_toolchain.py'),
    )
    tool_hashes = {p.name: digest(p) for p in tool_files}
    pinned_node, typescript, tool_receipts = resolve_tools(source, work)
    optimizer_modules, optimizer_receipts = resolve_optimizer(source, work)
    tool_receipts = [*tool_receipts, *optimizer_receipts]
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
        subprocess.run(
            [
                sys.executable, '-B',
                'project/ddn/packages/profiles/tools/generate.py',
            ],
            cwd=snapshot, check=True, capture_output=True,
        )
        patched = {
            name: digest(snapshot / name)
            for name in before['files']
            if digest(snapshot / name) != before['files'][name]
        }
        cube_spec = importlib.util.spec_from_file_location(
            'ddn_cube_dimensional', cube_patch
        )
        cube_module = importlib.util.module_from_spec(cube_spec)
        cube_spec.loader.exec_module(cube_module)
        cube_module.apply(snapshot)
        subprocess.run(
            [
                sys.executable, '-B',
                'project/ddn/packages/profiles/tools/generate.py',
            ],
            cwd=snapshot, check=True, capture_output=True,
        )
        cube_patched = {
            name: digest(snapshot / name)
            for name in before['files']
            if digest(snapshot / name) != patched.get(
                name, before['files'][name]
            )
        }
        bi_spec = importlib.util.spec_from_file_location(
            'ddn_bi_analytics', bi_patch
        )
        bi_module = importlib.util.module_from_spec(bi_spec)
        bi_spec.loader.exec_module(bi_module)
        bi_module.apply(snapshot)
        subprocess.run(
            [
                sys.executable, '-B',
                'project/ddn/packages/profiles/tools/generate.py',
            ],
            cwd=snapshot, check=True, capture_output=True,
        )
        bi_patched = {
            name: digest(snapshot / name)
            for name in before['files']
            if digest(snapshot / name) != cube_patched.get(
                name, patched.get(name, before['files'][name])
            )
        }
        screen_spec = importlib.util.spec_from_file_location(
            'ddn_screen_mesh', screen_patch
        )
        screen_module = importlib.util.module_from_spec(screen_spec)
        screen_spec.loader.exec_module(screen_module)
        screen_module.apply(snapshot)
        subprocess.run(
            [
                sys.executable, '-B',
                'project/ddn/packages/profiles/tools/generate.py',
            ],
            cwd=snapshot, check=True, capture_output=True,
        )
        screen_patched = {
            name: digest(snapshot / name)
            for name in before['files']
            if digest(snapshot / name) != bi_patched.get(
                name,
                cube_patched.get(
                    name, patched.get(name, before['files'][name])
                ),
            )
        }
        spec = importlib.util.spec_from_file_location(
            'ddn_registry_pack_cache', cache_patch
        )
        cache_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache_module)
        cache_module.apply(snapshot)
        cached = {
            name: digest(snapshot / name)
            for name in before['files']
            if digest(snapshot / name) != screen_patched.get(
                name,
                bi_patched.get(
                    name,
                    cube_patched.get(
                        name, patched.get(name, before['files'][name])
                    ),
                ),
            )
        }
        isolated_tools = snapshot / '.work/tools/toolchain'
        node = _copy_tool(pinned_node, isolated_tools / node_name)
        shutil.copytree(typescript, isolated_tools / 'typescript', copy_function=_copy_tool)
        shutil.copytree(optimizer_modules, snapshot / '.work/tools/optimizer/node_modules', copy_function=_copy_tool)
        env = dict(os.environ)
        for key in ('DDN_ROOT', 'DDN_TEMP_ROOT', 'DDN_BUILD_WORKAREA', 'DDN_BUILD_ROOT', 'ARTIFACT_ROOT',
                    'WEAVER_ROOT', 'WEAVER_WORKAREA', 'WEAVER_BUILD_ROOT', 'WEAVER_DDN_BUILD_ROOT'):
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
                    'consumer_patches': {
                        'native_geometry': {
                            'tool': digest(patch),
                            'review': digest(review),
                            'changed_inputs': patched,
                        },
                        'cube_dimensional': {
                            'tool': digest(cube_patch),
                            'review': digest(cube_review),
                            'changed_inputs': cube_patched,
                        },
                        'bi_analytics': {
                            'tool': digest(bi_patch),
                            'review': digest(bi_review),
                            'changed_inputs': bi_patched,
                        },
                        'screen_mesh': {
                            'tool': digest(screen_patch),
                            'review': digest(screen_review),
                            'changed_inputs': screen_patched,
                        },
                        'registry_pack_cache': {
                            'tool': digest(cache_patch),
                            'review': digest(cache_review),
                            'changed_inputs': cached,
                        },
                    },
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
