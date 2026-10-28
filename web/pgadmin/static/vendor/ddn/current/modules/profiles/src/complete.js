import './generated.js';
import { codex } from './schema-core.js';
import { contractVersion, completeProfileIds, profileDescriptor, freezeProfileData } from './core.js';
import { rulesFor } from './rules.js';
import { completeProfileDiagnostics } from './semantic.js';
export const completeRules = rulesFor(completeProfileIds, completeProfileDiagnostics);
/** All adopted profiles with exact descriptors and executable semantic rules. */
export function createCompletePack(registrations = {}) {
    return freezeProfileData({ manifest: freezeProfileData({ id: 'ddn-complete', version: '1.0.0', api: '1.0', hash: codex.sourceHashes['ddn.schema.json'] ?? '', languages: [contractVersion], defaults: [contractVersion], profiles: [...completeProfileIds], dependencies: [], capabilities: ['ddn.complete.descriptors', 'ddn.complete.verification'] }), registrations: { ...registrations, profiles: completeProfileIds.map(id => profileDescriptor(id)), rules: [...completeRules, ...(registrations.rules ?? [])] } });
}
//# sourceMappingURL=complete.js.map