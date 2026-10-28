import { createRuntime, createNativeRuntimeOptions } from '../../runtime/src/native.js';
import { createViewer, getViewerHandle } from '../../viewer/src/native.js';
import { createVerifier } from '../../verifier/src/index.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
const createBrowserRuntimeOptions = () => withBrowserExecutor(createNativeRuntimeOptions());
export const api = { createRuntime, createNativeRuntimeOptions, createBrowserRuntimeOptions, createViewer, createVerifier, getViewerHandle };
Object.defineProperty(globalThis, 'DDN', { value: Object.freeze(api), configurable: true });
mountShell({ mode: 'viewer', options: () => withBrowserExecutor(createNativeRuntimeOptions()), verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime });
//# sourceMappingURL=viewer-entry.js.map