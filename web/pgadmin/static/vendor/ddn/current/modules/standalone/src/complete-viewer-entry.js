import { analyzeProfile } from '../../profiles/src/index.js';
import { createCompletePresentationPack } from '../../presentation/src/pack.js';
import { createRuntime, createCompleteRuntimeOptions } from '../../runtime/src/index.js';
import { createViewer, getViewerHandle } from '../../viewer/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
const completeOptions = () => { const options = createCompleteRuntimeOptions(); return { ...options, packs: [...options.packs, createCompletePresentationPack()] }; };
const createBrowserRuntimeOptions = () => withBrowserExecutor(completeOptions());
export const api = { analyzeProfile, createCompletePresentationPack, createRuntime, createCompleteRuntimeOptions, createBrowserRuntimeOptions, createViewer, createVerifier, getViewerHandle };
Object.defineProperty(globalThis, 'DDN', { value: Object.freeze(api), configurable: true });
mountShell({ edition: 'complete', mode: 'viewer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime });
//# sourceMappingURL=complete-viewer-entry.js.map