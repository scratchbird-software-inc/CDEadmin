/** Lean read-only runtime entry. Editing commands and optional profiles load separately. */
export { createRuntime, STANDARD_VERSIONS } from './runtime.js';
export { registrations } from './registry.js';
import type { RuntimeOptions } from '../../types/src/core.js';
export declare function createNativeRuntimeOptions(): RuntimeOptions;
