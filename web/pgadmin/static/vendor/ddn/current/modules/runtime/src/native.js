/** Lean read-only runtime entry. Editing commands and optional profiles load separately. */
export { createRuntime, STANDARD_VERSIONS } from './runtime.js';
export { registrations } from './registry.js';
import { createNativePack } from '../../profiles/src/native.js';
import { STANDARD_VERSIONS } from './runtime.js';
export function createNativeRuntimeOptions() {
    return { versions: STANDARD_VERSIONS, packs: [createNativePack()] };
}
//# sourceMappingURL=native.js.map