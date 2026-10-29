import { createViewer as createNativeViewer, getViewerHandle } from '../../viewer/src/native.js';
import { attachModularRuntime, createModularRuntime } from './modular-runtime.js';
import { createModularBrowserOptions } from './modular-loading.js';
export { getViewerHandle };
export function createViewer(element, options = { runtimeOptions: createModularBrowserOptions() }) {
    const owned = !options.runtime;
    const runtime = options.runtime ? attachModularRuntime(options.runtime) : createModularRuntime(options.runtimeOptions ?? createModularBrowserOptions());
    const { runtime: _, runtimeOptions: __, ...settings } = options;
    const viewer = createNativeViewer(element, { ...settings, runtime });
    if (owned) {
        const destroy = viewer.destroy.bind(viewer);
        viewer.destroy = () => { destroy(); runtime.destroy(); };
    }
    return viewer;
}
//# sourceMappingURL=modular-viewer.js.map