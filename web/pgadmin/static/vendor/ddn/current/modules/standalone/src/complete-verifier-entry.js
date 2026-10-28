import { analyzeProfile } from '../../profiles/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
import { createCompletePack } from '../../profiles/src/index.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
import { createBrowserVerifier } from '../../execution/src/browser-verifier.js';
const createCompleteRuntimeOptions = () => ({
    versions: { api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} },
    packs: [createCompletePack()],
});
export const api = { analyzeProfile, createVerifier, createCompleteRuntimeOptions };
Object.defineProperty(globalThis, 'DDN', { value: Object.freeze(api), configurable: true });
mountShell({ edition: 'complete', mode: 'verifier', options: () => withBrowserExecutor(createCompleteRuntimeOptions()), verifier: createBrowserVerifier });
//# sourceMappingURL=complete-verifier-entry.js.map