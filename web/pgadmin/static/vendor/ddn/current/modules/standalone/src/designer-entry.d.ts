import { createRuntime } from '../../runtime/src/native.js';
import { createCommandService } from '../../runtime/src/commands.js';
import { createViewer, getViewerHandle } from '../../viewer/src/native.js';
import { createDesigner } from '../../designer/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
export declare const api: {
    createRuntime: typeof createRuntime;
    createNativeRuntimeOptions: () => {
        packs: import("@ddn/types").Pack[];
        versions: import("@ddn/types").VersionSet;
        executor?: import("@ddn/types").Executor;
        limits?: import("@ddn/types").Budget;
    };
    createBrowserRuntimeOptions: () => import("@ddn/types").RuntimeOptions;
    createCommandService: typeof createCommandService;
    createViewer: typeof createViewer;
    createDesigner: typeof createDesigner;
    createVerifier: typeof createVerifier;
    getViewerHandle: typeof getViewerHandle;
};
