import { clone, freeze } from '../../execution/src/index.js';
const registryData = new WeakMap();
const packData = new WeakMap();
export function registryPacks(registry) { return packData.get(registry)?.() ?? []; }
export function registrations(registry) {
    const read = registryData.get(registry);
    if (!read)
        throw new Error('Registry does not belong to this DDN implementation');
    return read();
}
export function createRegistry(versions, onChange = () => { }) {
    const installed = new Map();
    function merged() {
        const packs = [...installed.values()];
        return freeze({
            profiles: packs.flatMap(p => p.registrations.profiles ?? []),
            rules: packs.flatMap(p => p.registrations.rules ?? []),
            commands: packs.flatMap(p => p.registrations.commands ?? []),
            projections: packs.flatMap(p => p.registrations.projections ?? []),
            schemas: Object.assign({}, ...packs.map(p => p.registrations.schemas ?? {})),
        });
    }
    const registry = {
        install(pack) {
            const m = pack.manifest;
            if (!m || !m.id || !m.version || !m.hash || m.api !== '1.0' || !Array.isArray(m.languages) || !Array.isArray(m.defaults) || !Array.isArray(m.dependencies) || !Array.isArray(m.profiles) || !Array.isArray(m.capabilities))
                throw new TypeError('Malformed pack manifest');
            if (!m.languages.includes(versions.language) || !m.defaults.includes(versions.defaults))
                throw new Error('Unsupported pack contract: ' + m.id);
            const expected = versions.packs[m.id];
            if (expected !== undefined && expected !== m.version)
                throw new Error('Pack version differs from selected version: ' + m.id);
            const existing = installed.get(m.id);
            if (existing) {
                if (existing.manifest.version === m.version && existing.manifest.hash === m.hash)
                    return;
                throw new Error('Incompatible duplicate pack: ' + m.id);
            }
            for (const dependency of m.dependencies)
                if (dependency === m.id || !installed.has(dependency))
                    throw new Error('Missing or cyclic pack dependency: ' + dependency);
            const current = merged(), incoming = pack.registrations;
            for (const key of ['profiles', 'rules', 'commands', 'projections']) {
                const identities = new Set((current[key] ?? []).map(v => v.id));
                for (const value of incoming[key] ?? []) {
                    if (!value.id || identities.has(value.id))
                        throw new Error('Duplicate ' + key + ' registration: ' + value.id);
                    identities.add(value.id);
                    if (key === 'profiles' && !m.profiles.includes(value.id))
                        throw new Error('Undeclared profile registration: ' + value.id);
                }
            }
            for (const name of Object.keys(incoming.schemas ?? {}))
                if (Object.hasOwn(current.schemas ?? {}, name))
                    throw new Error('Duplicate schema registration: ' + name);
            // Trusted callbacks stay code; all declarative registration data becomes immutable.
            const copy = { manifest: freeze(clone(m)), registrations: freeze({
                    ...(incoming.profiles ? { profiles: incoming.profiles.map(p => freeze(clone(p))) } : {}),
                    ...(incoming.rules ? { rules: incoming.rules.map(p => freeze({ ...p, profiles: [...p.profiles], levels: [...p.levels], purposes: [...p.purposes], readPaths: [...p.readPaths] })) } : {}),
                    ...(incoming.commands ? { commands: incoming.commands.map(p => freeze({ ...p, profiles: [...p.profiles], propertyPaths: [...p.propertyPaths] })) } : {}),
                    ...(incoming.projections ? { projections: incoming.projections.map(p => freeze({ ...p, profiles: [...p.profiles], readPaths: [...p.readPaths] })) } : {}),
                    ...(incoming.schemas ? { schemas: freeze(clone(incoming.schemas)) } : {}),
                }) };
            installed.set(m.id, copy);
            onChange();
        },
        describe() { return freeze([...installed.values()].map(p => p.manifest)); },
        supports(capability, profile) { return [...installed.values()].some(p => p.manifest.capabilities.includes(capability) && (!profile || p.manifest.profiles.includes(profile))); },
    };
    registryData.set(registry, merged);
    packData.set(registry, () => [...installed.values()]);
    return registry;
}
//# sourceMappingURL=registry.js.map