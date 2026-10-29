export { createRuntime, STANDARD_VERSIONS } from './runtime.js';
export { createCommandService, createNativeCommandPack, createCompleteCommandPack } from './commands.js';
export { registrations } from './registry.js';
import { createNativePack, createCompletePack } from '../../profiles/src/index.js';
import { STANDARD_VERSIONS } from './runtime.js';
import { createNativeCommandPack, createCompleteCommandPack } from './commands.js';
export function createNativeRuntimeOptions() {
    return { versions: STANDARD_VERSIONS, packs: [createNativePack(), createNativeCommandPack()] };
}
export function createCompleteRuntimeOptions() {
    return { versions: STANDARD_VERSIONS, packs: [createCompletePack(), createCompleteCommandPack()] };
}
//# sourceMappingURL=index.js.map