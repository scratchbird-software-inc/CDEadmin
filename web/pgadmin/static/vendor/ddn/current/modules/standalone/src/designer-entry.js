import { createRuntime, createNativeRuntimeOptions as readOnlyOptions } from '../../runtime/src/native.js';
import { createCommandService, createNativeCommandPack } from '../../runtime/src/commands.js';
const createNativeRuntimeOptions = () => { const options = readOnlyOptions(); return { ...options, packs: [...options.packs, createNativeCommandPack()] }; };
import { createViewer, getViewerHandle } from '../../viewer/src/native.js';
import { createDesigner } from '../../designer/src/index.js';
import { newDiagramDialog } from '../../designer/src/new-diagram.js';
import { createVerifier } from '../../verifier/src/index.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
const createBrowserRuntimeOptions = () => withBrowserExecutor(createNativeRuntimeOptions());
export const api = { createRuntime, createNativeRuntimeOptions, createBrowserRuntimeOptions, createCommandService, createViewer, createDesigner, createVerifier, getViewerHandle };
Object.defineProperty(globalThis, 'DDN', { value: Object.freeze(api), configurable: true });
mountShell({
    mode: 'designer', options: () => withBrowserExecutor(createNativeRuntimeOptions()), verifier: createVerifier,
    viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime,
    newDiagram: newDiagramDialog,
    designer: viewer => createDesigner(viewer, {
        authority: { async authorize(action) {
                const grants = ['model.edit', 'model.verify', 'lifecycle.review', 'lifecycle.accept', 'lifecycle.reopen'];
                return { allowed: grants.includes(action), principal: 'local-user', grants };
            } },
    }),
});
//# sourceMappingURL=designer-entry.js.map