export { createViewer, getViewerHandle } from './modular-viewer.js';
export { createModularRuntime as createRuntime } from './modular-runtime.js';
export { createModularRuntimeOptions, createModularBrowserOptions as createBrowserRuntimeOptions } from './modular-loading.js';
export { createModularVerifier as createVerifier } from './modular-verifier.js';
import { installModularWorkerFactory } from './modular-loading.js';
installModularWorkerFactory();
//# sourceMappingURL=modular-viewer-api.js.map