import * as api from './modular-viewer-api.js';
import { bootModularShell } from './modular-shell.js';
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle } = api;
export { api };
bootModularShell({ mode: 'viewer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime }, api);
//# sourceMappingURL=modular-viewer-entry.js.map