import { codex } from './schema-core.js';
import { contractVersion, nativeProfileIds, profileDescriptor, freezeProfileData } from './core.js';
import { catalogueFamilies } from './generated-families.js';
import { createNativePack } from './native.js';
import { rulesFor } from './rules.js';
const families = new Map();
const evaluators = new Map();
/** Trusted compiled family entry points install data before their executable rules. */
export function registerProfileFamily(id, profiles, evaluate) {
    const packId = 'ddn-' + id;
    const expected = catalogueFamilies[id];
    if (!expected || id === 'native' || profiles.length !== expected.profiles.length || new Set(profiles).size !== profiles.length || profiles.some(profile => !expected.profiles.includes(profile)))
        throw new Error('Invalid profile family manifest: ' + id);
    if (families.has(packId)) {
        if (evaluators.get(packId) !== evaluate)
            throw new Error('Conflicting profile family: ' + id);
        return;
    }
    if (!profiles.length || new Set(profiles).size !== profiles.length || profiles.some(profile => nativeProfileIds.includes(profile) || !profileDescriptor(profile)))
        throw new Error('Missing or invalid catalogue data for family: ' + id);
    const occupied = new Set([...families.values()].flatMap(pack => pack.manifest.profiles));
    if (profiles.some(profile => occupied.has(profile)))
        throw new Error('Duplicate profile family: ' + id);
    evaluators.set(packId, evaluate);
    families.set(packId, freezeProfileData({
        manifest: freezeProfileData({ id: packId, version: '1.0.0', api: '1.0', hash: expected.hash, languages: [contractVersion], defaults: [contractVersion], profiles: [...expected.profiles], dependencies: ['ddn-native'], capabilities: ['ddn.family.descriptors', 'ddn.family.verification'] }),
        registrations: freezeProfileData({ profiles: expected.profiles.map(profile => profileDescriptor(profile)), rules: rulesFor(expected.profiles, evaluate) }),
    }));
}
export function loadedProfilePacks() { return [createNativePack(), ...families.values()]; }
//# sourceMappingURL=family-packs.js.map