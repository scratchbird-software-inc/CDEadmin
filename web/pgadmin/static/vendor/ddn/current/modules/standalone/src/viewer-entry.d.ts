import { createRuntime, createNativeRuntimeOptions } from '../../runtime/src/native.js';
import { createViewer, getViewerHandle } from '../../viewer/src/native.js';
import { createVerifier } from '../../verifier/src/index.js';
export declare const api: {
    createRuntime: typeof createRuntime;
    createNativeRuntimeOptions: typeof createNativeRuntimeOptions;
    createBrowserRuntimeOptions: () => import("@ddn/types").RuntimeOptions;
    createViewer: typeof createViewer;
    createVerifier: typeof createVerifier;
    getViewerHandle: typeof getViewerHandle;
};
