import type { DesignerOptions, Viewer } from '../../types/src/browser.js';
import { createCommandService } from '../../runtime/src/commands.js';
import { createViewer, getViewerHandle } from './modular-viewer.js';
import { createModularRuntime as createRuntime } from './modular-runtime.js';
import { createModularRuntimeOptions } from './modular-loading.js';
import { createModularVerifier as createVerifier } from './modular-verifier.js';
export declare const createBrowserRuntimeOptions: () => import("@ddn/types").RuntimeOptions;
export declare const createDesigner: (viewer: Viewer, options: DesignerOptions) => import("../../types/src/browser.js").Designer;
export { createRuntime, createModularRuntimeOptions, createCommandService, createViewer, getViewerHandle, createVerifier };
