const installed = new Map();
const owners = new Map();
const nativeProfiles = ['ddn@1', 'mindmap.basic@1', 'concept.map@1', 'table.records@1'];
/** A live read-only view of installed implementations, not catalogue promises. */
const available = new Set(nativeProfiles);
export const availableProjectionProfiles = available;
/** Trusted local code registration. Assets are authenticated/version-selected by the host loader. */
export function installPresentationFamily(family) {
    if (!['graphs', 'charts', 'geography', 'surfaces'].includes(family.id) || family.version !== '1.0.0' || family.language !== 'ddn-next-1' || !family.profiles.length || new Set(family.profiles).size !== family.profiles.length || (family.kind === 'graph' ? typeof family.graph !== 'function' || !!family.data : family.kind === 'data' ? typeof family.data !== 'function' || !!family.graph : true))
        throw new TypeError('Unsupported presentation family: ' + family.id);
    const previous = installed.get(family.id);
    if (previous) {
        if (previous.version === family.version && previous.language === family.language && previous.graph === family.graph && previous.data === family.data && previous.analyze === family.analyze && previous.profiles.join('\0') === family.profiles.join('\0'))
            return;
        throw new Error('Conflicting presentation family: ' + family.id);
    }
    for (const profile of family.profiles)
        if (available.has(profile))
            throw new Error('Duplicate presentation profile: ' + profile);
    const copy = Object.freeze({ ...family, profiles: Object.freeze([...family.profiles]) });
    installed.set(family.id, copy);
    for (const profile of copy.profiles) {
        available.add(profile);
        owners.set(profile, copy);
    }
}
export function installedPresentationFamilies() { return Object.freeze([...installed.values()]); }
export const isGraphProfile = (profile) => owners.get(profile)?.kind === 'graph';
export const isDataProfile = (profile) => owners.get(profile)?.kind === 'data';
export const graphProjector = (profile) => owners.get(profile)?.graph;
export const dataProjector = (profile) => owners.get(profile)?.data;
export function analyzePresentedProfile(normalized, target, values) {
    // Each optional family may share the bounded analyser. No analyser is loaded
    // merely to draw an ordinary native DDN card.
    const analyzer = [...installed.values()].find(family => family.analyze)?.analyze;
    return analyzer ? analyzer(normalized, target, values) : { kind: 'none', outcome: 'not-applicable' };
}
//# sourceMappingURL=adapters.js.map