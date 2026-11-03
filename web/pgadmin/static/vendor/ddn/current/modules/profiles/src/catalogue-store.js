function freeze(value) {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
        Object.freeze(value);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(value)))
            if ('value' in descriptor)
                freeze(descriptor.value);
    }
    return value;
}
/** Stable read-only facade; deferred schema access fails explicitly until installed. */
export function createCatalogue(base, manifests, expectedCoreHash) {
    const known = base.knownProfiles, index = { ...base };
    let core = expectedCoreHash ? undefined : base;
    let profiles = freeze(base.profiles);
    const installed = new Map([['native', manifests.native.hash]]);
    const facade = {};
    const keys = new Set([...Object.keys(base), 'nodes', 'roots', 'properties', 'core', 'cssMap']);
    for (const key of keys)
        Object.defineProperty(facade, key, { enumerable: true, get: () => {
                if (key === 'profiles')
                    return profiles;
                if (core && Object.hasOwn(core, key))
                    return core[key];
                if (Object.hasOwn(index, key))
                    return index[key];
                throw Error('Native schema data is not loaded: ' + key);
            } });
    freeze(facade);
    freeze(index);
    if (core)
        freeze(core);
    function installCore(value, hash) {
        if (!expectedCoreHash) {
            if (value !== core)
                throw Error('Conflicting native catalogue.');
            return;
        }
        if (hash !== expectedCoreHash || value.version !== index.version || JSON.stringify(value.sourceHashes) !== JSON.stringify(index.sourceHashes) || !Array.isArray(value.nodes) || !value.roots || !Array.isArray(value.properties))
            throw Error('Incompatible native schema data.');
        if (core)
            return;
        for (const [id, descriptor] of Object.entries(value.profiles))
            if (!known[id] || !descriptor)
                throw Error('Unknown native profile ' + id);
        core = freeze(value);
        profiles = freeze({ ...profiles, ...value.profiles });
    }
    function install(family) {
        const expected = manifests[family.id];
        if (!expected || family.version !== expected.version || family.contract !== expected.contract || family.codexHash !== expected.codexHash || family.hash !== expected.hash)
            throw Error('Unsupported catalogue family version or hash: ' + family.id);
        const ids = Object.keys(family.profiles ?? {});
        if (ids.length !== expected.profiles.length || ids.some(id => !expected.profiles.includes(id) || !known[id] || !family.profiles[id] || typeof family.profiles[id] !== 'object' || family.profiles[id].id !== id))
            throw Error('Catalogue family profile identities differ from manifest: ' + family.id);
        if (installed.has(family.id))
            return;
        if (ids.some(id => Object.hasOwn(profiles, id)))
            throw Error('Duplicate catalogue profile registration: ' + family.id);
        const combined = { ...profiles, ...family.profiles };
        profiles = freeze(Object.fromEntries(Object.keys(known).filter(id => Object.hasOwn(combined, id)).map(id => [id, combined[id]])));
        installed.set(family.id, family.hash);
    }
    return { compiledCodex: facade, installCatalogueFamily: install, installedCatalogueFamilies: () => Object.freeze([...installed.keys()]), installCore };
}
//# sourceMappingURL=catalogue-store.js.map