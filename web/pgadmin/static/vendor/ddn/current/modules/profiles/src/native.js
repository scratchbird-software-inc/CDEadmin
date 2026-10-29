import { codex } from './schema-core.js';
import { contractVersion, nativeProfileIds, profileDescriptor, freezeProfileData } from './core.js';
import { rulesFor } from './rules.js';
export const nativeRules = rulesFor(nativeProfileIds);
/** Exact native descriptors and executable rules; presentation adapters register separately. */
export function createNativePack(registrations = {}) {
    return freezeProfileData({ manifest: freezeProfileData({ id: 'ddn-native', version: '1.0.0', api: '1.0', hash: codex.sourceHashes['ddn.schema.json'] ?? '', languages: [contractVersion], defaults: [contractVersion], profiles: [...nativeProfileIds], dependencies: [], capabilities: ['ddn.native.descriptors', 'ddn.native.verification'] }), registrations: { ...registrations, profiles: nativeProfileIds.map(id => profileDescriptor(id)), rules: [...nativeRules, ...(registrations.rules ?? [])] } });
}
//# sourceMappingURL=native.js.map