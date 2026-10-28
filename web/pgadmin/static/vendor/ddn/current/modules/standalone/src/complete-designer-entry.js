import { analyzeProfile } from '../../profiles/src/index.js';
import { createCompletePresentationPack } from '../../presentation/src/pack.js';
import { createRuntime, createCompleteRuntimeOptions, createCommandService } from '../../runtime/src/index.js';
import { createViewer, getViewerHandle } from '../../viewer/src/index.js';
import { createDesigner } from '../../designer/src/index.js';
import { newDiagramDialog } from '../../designer/src/new-diagram.js';
import { createVerifier } from '../../verifier/src/index.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
const completeOptions = () => { const options = createCompleteRuntimeOptions(); return { ...options, packs: [...options.packs, createCompletePresentationPack()] }; };
const createBrowserRuntimeOptions = () => withBrowserExecutor(completeOptions());
export const api = { analyzeProfile, createCompletePresentationPack, createRuntime, createCompleteRuntimeOptions, createBrowserRuntimeOptions, createCommandService, createViewer, createDesigner, createVerifier, getViewerHandle };
Object.defineProperty(globalThis, 'DDN', { value: Object.freeze(api), configurable: true });
mountShell({
    edition: 'complete', mode: 'designer', options: createBrowserRuntimeOptions, verifier: createVerifier,
    viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime,
    newDiagram: newDiagramDialog,
    designer: viewer => createDesigner(viewer, {
        authority: { async authorize(action) {
                const grants = ['model.edit', 'model.verify', 'lifecycle.review', 'lifecycle.accept', 'lifecycle.reopen'];
                return { allowed: grants.includes(action), principal: 'local-user', grants };
            } },
    }),
});
//# sourceMappingURL=complete-designer-entry.js.map