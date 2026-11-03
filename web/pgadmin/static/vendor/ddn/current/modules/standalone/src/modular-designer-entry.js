import * as api from './modular-designer-api.js';
import { bootModularShell } from './modular-shell.js';
import { newDiagramDialog } from './lazy-new-diagram.js';
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle, createDesigner } = api;
export { api };
bootModularShell({ mode: 'designer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime,
    newDiagram: newDiagramDialog,
    designer: viewer => createDesigner(viewer, { authority: { async authorize(action) {
                const grants = ['model.edit', 'model.verify', 'lifecycle.review', 'lifecycle.accept', 'lifecycle.reopen'];
                return { allowed: grants.includes(action), principal: 'local-user', grants };
            } } }),
}, api);
//# sourceMappingURL=modular-designer-entry.js.map