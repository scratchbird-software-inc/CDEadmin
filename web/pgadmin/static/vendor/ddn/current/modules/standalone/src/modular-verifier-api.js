export { createModularRuntimeOptions, createModularBrowserOptions as createBrowserRuntimeOptions } from './modular-loading.js';
export { createModularVerifier as createVerifier } from './modular-verifier.js';
export { verifySourcesWithModel } from '../../verifier/src/index.js';
import { installModularWorkerFactory } from './modular-loading.js';
installModularWorkerFactory();
//# sourceMappingURL=modular-verifier-api.js.map