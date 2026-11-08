"""Reviewed consumer patch, applied only to an isolated standalone DDN capture.

Every DDN runtime installed the same profile packs by deep-cloning and
freezing about 480 KB of profile data, and its verifier cloned and froze the
same data again; the pack factories also rebuilt every profile descriptor.
This patch keeps one frozen copy per deep-frozen source object, lets freeze()
skip objects already known to be deep-frozen, and memoizes the pure profile
descriptors, so later runtimes reuse them without walking them again. No
grammar, API, default or verification change. See ddn-registry-pack-cache.md;
the source checkout is never modified.
"""
from pathlib import Path

PACKAGES = 'project/ddn/packages'
MARK = 'ScratchRobin consumer patch (registry pack cache)'


def _edit(root, relative, replacements):
    path = Path(root) / PACKAGES / relative
    text = path.read_text(encoding='utf-8')
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError('DDN source changed; review the registry pack '
                               'cache patch: ' + relative + ': ' + old[:80])
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')


FREEZE = '''export function freeze<T>(value: T): T {
    const seen = new Set<object>();
    const visit = (item: unknown): void => {
        if (!item || typeof item !== 'object' || ArrayBuffer.isView(item) || seen.has(item)) return;
        seen.add(item);
        Object.freeze(item);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(item))) if ('value' in descriptor) visit(descriptor.value);
    };
    visit(value);
    return value;
}
'''

PATCHED_FREEZE = '''// ''' + MARK + ''': objects known to be deep-frozen
// (shared copies, and sources proven deep-frozen) cannot change, so freezing
// a new wrapper around them does not walk them again.
const deeplyFrozen = new WeakSet<object>();
export function freeze<T>(value: T): T {
    const seen = new Set<object>();
    const visit = (item: unknown): void => {
        if (!item || typeof item !== 'object' || ArrayBuffer.isView(item) || seen.has(item) || deeplyFrozen.has(item)) return;
        seen.add(item);
        Object.freeze(item);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(item))) if ('value' in descriptor) visit(descriptor.value);
    };
    visit(value);
    return value;
}
// ''' + MARK + ''': a deep-frozen source cannot change, so one
// frozen plain-JSON copy of it serves every later runtime and verifier. The
// first copy still validates the data; anything not deep-frozen is copied anew.
// Every copy is plain JSON frozen throughout, so it is itself deep-frozen.
const frozenCopies = new WeakMap<object, unknown>();
function isDeeplyFrozen(value: unknown, seen: Set<object>): boolean {
    if (!value || typeof value !== 'object' || deeplyFrozen.has(value) || seen.has(value)) return true;
    if (ArrayBuffer.isView(value) || !Object.isFrozen(value)) return false;
    seen.add(value);
    for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(value)))
        if (!('value' in descriptor) || !isDeeplyFrozen(descriptor.value, seen)) return false;
    return true;
}
export function frozenCopy<T>(value: T): T {
    if (!value || typeof value !== 'object') return freeze(clone(value));
    const cached = frozenCopies.get(value);
    if (cached !== undefined) return cached as T;
    const copy = freeze(clone(value));
    deeplyFrozen.add(copy as object);
    const seen = new Set<object>();
    if (isDeeplyFrozen(value, seen)) {
        for (const item of seen) deeplyFrozen.add(item);
        frozenCopies.set(value, copy);
    }
    return copy;
}
'''


def apply(root):
    _edit(root, 'execution/src/index.ts', [(FREEZE, PATCHED_FREEZE)])
    _edit(root, 'runtime/src/registry.ts', [
        ("import { clone, freeze } from '../../execution/src/index.js';",
         "import { freeze, frozenCopy } from '../../execution/src/index.js';"),
        ('const copy: Pack = { manifest: freeze(clone(m)), registrations: freeze({',
         '// ' + MARK + ': shared frozen copies.\n'
         '            const copy: Pack = { manifest: frozenCopy(m), registrations: freeze({'),
        ('profiles: incoming.profiles.map(p => freeze(clone(p)))',
         'profiles: incoming.profiles.map(p => frozenCopy(p))'),
        ('schemas: freeze(clone(incoming.schemas))',
         'schemas: frozenCopy(incoming.schemas)'),
    ])
    _edit(root, 'verifier/src/index.ts', [
        ('import { fingerprint, createContext, ComputationStopped, clone, freeze, type AccountingContext }',
         'import { fingerprint, createContext, ComputationStopped, clone, freeze, frozenCopy, type AccountingContext }'),
        ('const packs = runtimeOptions.packs.map(pack => ({ manifest: freeze(clone(pack.manifest)), registrations: {\n'
         '        profiles: freeze(clone(pack.registrations.profiles ?? [])),',
         '// ' + MARK + ': shared frozen copies.\n'
         '    const packs = runtimeOptions.packs.map(pack => ({ manifest: frozenCopy(pack.manifest), registrations: {\n'
         '        profiles: freeze((pack.registrations.profiles ?? []).map(profile => frozenCopy(profile))),'),
    ])
    _edit(root, 'profiles/src/core.ts', [
        ('export function profileDescriptor(id: string): ProfileDescriptor | undefined {\n'
         '    const p = getProfile(id);\n'
         '    if (!p)\n'
         '        return undefined;\n'
         '    return freezeProfileData({',
         '// ' + MARK + ': a descriptor is a pure function of the frozen\n'
         '// codex and its id, so every pack shares one deep-frozen descriptor per id.\n'
         'const descriptors = new Map<string, ProfileDescriptor>();\n'
         'export function profileDescriptor(id: string): ProfileDescriptor | undefined {\n'
         '    const known = descriptors.get(id);\n'
         '    if (known)\n'
         '        return known;\n'
         '    const p = getProfile(id);\n'
         '    if (!p)\n'
         '        return undefined;\n'
         '    const descriptor: ProfileDescriptor = freezeProfileData({'),
    ])
    # The descriptor literal ends the function; store it before returning.
    path = Path(root) / PACKAGES / 'profiles/src/core.ts'
    text = path.read_text(encoding='utf-8')
    tail = "exclusions: [...p.exclusions] });\n}"
    if text.count(tail) != 1:
        raise RuntimeError('DDN profile descriptor changed; review the registry '
                           'pack cache patch')
    text = text.replace(tail, "exclusions: [...p.exclusions] });\n"
                              "    descriptors.set(id, descriptor);\n"
                              "    return descriptor;\n}")
    path.write_text(text, encoding='utf-8')
