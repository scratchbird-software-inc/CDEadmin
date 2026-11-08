"""ScratchRobin's DDN capture shares frozen profile data between runtimes.

Owner direction 2026-11-07: ScratchRobin extends its own DDN capture through
reviewed consumer patches in tools/dependency_patches and pushes nothing back
to the DDN repository. The registry pack cache patch keeps one frozen copy
of each deep-frozen profile, lets freeze() skip what is already deep-frozen,
and builds each profile descriptor once, so the DDN surfaces of every engine
(catalogs, diagrams, dashboards) stop copying and re-freezing about 480 KB of
profile data for each runtime and verifier.

These tests check the vendored distribution that ScratchRobin ships: the
modules the browser loads and the single-file bundles the jest suite loads.
They also check that the patch refuses a changed DDN source instead of
skipping an edit.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'web/pgadmin/static/vendor/ddn/current'
PATCHES = ROOT / 'tools/dependency_patches'
NODE = shutil.which('node')
CHANGED = {
    'project/ddn/packages/execution/src/index.ts',
    'project/ddn/packages/profiles/src/core.ts',
    'project/ddn/packages/runtime/src/registry.ts',
    'project/ddn/packages/verifier/src/index.ts',
}

SHARING = r'''
import { pathToFileURL } from 'node:url';
const base = pathToFileURL(process.argv[1]).href;
const load = path => import(base + '/' + path);
const runtime = await load('modules/runtime/src/index.js');
const execution = await load('modules/execution/src/index.js');
function shared(make) {
  const first = make(), second = make();
  let profiles = 0, same = 0;
  first.packs.forEach((pack, i) => (pack.registrations.profiles ?? []).forEach((profile, j) => {
    profiles++;
    if (profile === second.packs[i].registrations.profiles[j]) same++;
  }));
  return { profiles, same };
}
const out = { complete: shared(runtime.createCompleteRuntimeOptions),
              native: shared(runtime.createNativeRuntimeOptions) };
for (const name of ['ddn-viewer.js', 'ddn-verifier.js', 'ddn-visual-designer.js'])
  out[name] = shared((await load('complete/' + name)).createCompleteRuntimeOptions);
const copy = execution.frozenCopy;
const profile = runtime.createCompleteRuntimeOptions().packs[0].registrations.profiles[0];
const mutable = { a: { b: 1 } }, partly = Object.freeze({ a: { b: 1 } });
const deep = Object.freeze({ a: Object.freeze({ b: 1 }) });
const accessor = Object.freeze(Object.defineProperty({}, 'x', { get: () => 1, enumerable: true }));
const rejects = value => { try { copy(value); return false; } catch { return true; } };
out.copies = {
  profileShared: copy(profile) === copy(profile),
  profileCopyIsNotSource: copy(profile) !== profile,
  profileCopyEqual: JSON.stringify(copy(profile)) === JSON.stringify(profile),
  deepShared: copy(deep) === copy(deep),
  mutableNotShared: copy(mutable) !== copy(mutable),
  mutableCopyFrozen: Object.isFrozen(copy(mutable)) && Object.isFrozen(copy(mutable).a),
  partlyFrozenNotShared: copy(partly) !== copy(partly),
  accessorRejectedTwice: rejects(accessor) && rejects(accessor),
};
// freeze() skips only what is already deep-frozen; everything else reachable
// is still frozen, as before.
const freeze = execution.freeze;
const sharedCopy = copy(deep);
const wrapper = freeze({ shared: [sharedCopy], own: { c: [1] } });
const topOnly = Object.freeze({ child: { n: 1 } });
copy(topOnly);
freeze({ topOnly });
out.freezing = {
  wrapperFrozen: Object.isFrozen(wrapper) && Object.isFrozen(wrapper.shared) && Object.isFrozen(wrapper.own.c),
  sharedUnchanged: wrapper.shared[0] === sharedCopy && Object.isFrozen(sharedCopy.a),
  partlyFrozenChildFrozen: Object.isFrozen(topOnly.child),
};
console.log(JSON.stringify(out));
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_patch():
    spec = importlib.util.spec_from_file_location(
        'ddn_registry_pack_cache', PATCHES / 'ddn_registry_pack_cache.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_manifest_records_the_reviewed_cache_patch():
    manifest = json.loads((VENDOR / 'resource-manifest.json').read_text())
    record = manifest['consumer_patches']['registry_pack_cache']
    assert record['tool'] == digest(PATCHES / 'ddn_registry_pack_cache.py')
    assert record['review'] == digest(PATCHES / 'ddn-registry-pack-cache.md')
    assert set(record['changed_inputs']) == CHANGED
    # Both reviewed documents are intake inputs, so editing either rebuilds.
    assert {'ddn_registry_pack_cache.py', 'ddn-registry-pack-cache.md'} <= set(manifest['intake_tools'])


@pytest.mark.skipif(NODE is None, reason='node is required')
def test_every_runtime_shares_one_frozen_copy_of_the_profiles():
    result = subprocess.run([NODE, '--input-type=module', '-e', SHARING, str(VENDOR)],
                            capture_output=True, text=True, timeout=120, check=True)
    out = json.loads(result.stdout)
    # The modules the browser loads and each single-file bundle.
    for name in ('complete', 'native', 'ddn-viewer.js', 'ddn-verifier.js', 'ddn-visual-designer.js'):
        assert out[name]['profiles'] > 0 and out[name]['same'] == out[name]['profiles'], name
    # Only a deep-frozen source is shared; anything else is copied and
    # validated anew every time.
    assert out['copies'] == {key: True for key in out['copies']}
    assert len(out['copies']) == 8
    assert out['freezing'] == {key: True for key in out['freezing']}
    assert len(out['freezing']) == 3


def test_the_patch_refuses_a_changed_ddn_source(tmp_path):
    for name in CHANGED:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('// a DDN source this patch was not reviewed against\n')
    with pytest.raises(RuntimeError, match='review the registry pack cache patch'):
        load_patch().apply(tmp_path)
