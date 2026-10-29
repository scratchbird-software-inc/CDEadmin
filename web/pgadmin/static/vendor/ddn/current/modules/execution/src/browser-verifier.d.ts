import type { RuntimeOptions, Verifier } from '../../types/src/core.js';
/** Optional worker-backed facade. Worker construction and CSP fallback remain host responsibilities. */
export declare function createBrowserVerifier(inputOptions: RuntimeOptions): Verifier;
