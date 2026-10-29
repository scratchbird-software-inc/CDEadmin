import type { Runtime, RuntimeOptions } from '../../types/src/core.js';
/** Decorate only the host facade; the model, parser and language remain unchanged. */
export declare function createModularRuntime(options?: RuntimeOptions, drawing?: boolean): Runtime;
export declare function attachModularRuntime(runtime: Runtime, drawing?: boolean): Runtime;
