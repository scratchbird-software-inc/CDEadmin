import { analyzeProfile } from '../../profiles/src/index.js';
import { createCompletePresentationPack } from '../../presentation/src/pack.js';
import { createRuntime, createCompleteRuntimeOptions, createCommandService } from '../../runtime/src/index.js';
import { createViewer, getViewerHandle } from '../../viewer/src/index.js';
import { createDesigner } from '../../designer/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
export declare const api: {
    analyzeProfile: typeof analyzeProfile;
    createCompletePresentationPack: typeof createCompletePresentationPack;
    createRuntime: typeof createRuntime;
    createCompleteRuntimeOptions: typeof createCompleteRuntimeOptions;
    createBrowserRuntimeOptions: () => import("@ddn/types").RuntimeOptions;
    createCommandService: typeof createCommandService;
    createViewer: typeof createViewer;
    createDesigner: typeof createDesigner;
    createVerifier: typeof createVerifier;
    getViewerHandle: typeof getViewerHandle;
};
