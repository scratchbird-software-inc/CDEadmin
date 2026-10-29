import { createDesigner as createNativeDesigner } from '../../designer/src/index.js';
import { createModularCommandPack, createCommandService } from '../../runtime/src/commands.js';
import { createViewer, getViewerHandle } from './modular-viewer.js';
import { createModularRuntime as createRuntime } from './modular-runtime.js';
import { createModularRuntimeOptions } from './modular-loading.js';
import { createModularVerifier as createVerifier } from './modular-verifier.js';
import { withBrowserExecutor } from './browser-options.js';
import { installModularWorkerFactory } from './modular-loading.js';
installModularWorkerFactory();
export const createBrowserRuntimeOptions = () => { const options = createModularRuntimeOptions(); return withBrowserExecutor({ ...options, packs: [...options.packs, createModularCommandPack()] }); };
export const createDesigner = (viewer, options) => {
    const runtime = getViewerHandle(viewer).runtime;
    if (!runtime.registry.describe().some(pack => pack.id.endsWith('-commands')))
        runtime.registry.install(createModularCommandPack());
    return createNativeDesigner(viewer, options);
};
export { createRuntime, createModularRuntimeOptions, createCommandService, createViewer, getViewerHandle, createVerifier };
//# sourceMappingURL=modular-designer-api.js.map