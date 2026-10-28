import { analyzeProfile } from '../../profiles/src/index.js';
import { createCompletePresentationPack } from '../../presentation/src/pack.js';
import { createRuntime, createCompleteRuntimeOptions } from '../../runtime/src/index.js';
import { createViewer, getViewerHandle } from '../../viewer/src/index.js';
import { createDesigner } from '../../designer/src/index.js';
import { newDiagramDialog } from '../../designer/src/new-diagram.js';
import { createVerifier } from '../../verifier/src/index.js';
import { installWebsiteNavigation } from './website-navigation.js';
import { mountShell } from './shell.js';
import { withBrowserExecutor } from './browser-options.js';
/** A local website host. Its data is bundled as text, never executed as DDN code. */
const host = globalThis;
const parameters = new URLSearchParams(location.search);
const mode = parameters.get('mode') === 'design' ? 'designer' : parameters.get('mode') === 'verify' ? 'verifier' : 'viewer';
const options = () => {
    const core = createCompleteRuntimeOptions();
    return withBrowserExecutor({ ...core, packs: [...core.packs, createCompletePresentationPack()] });
};
Object.defineProperty(globalThis, 'DDN', { configurable: true, value: Object.freeze({ createRuntime, createCompleteRuntimeOptions, createBrowserRuntimeOptions: options, createViewer, getViewerHandle, createDesigner, createVerifier, analyzeProfile }) });
mountShell({
    edition: 'complete', mode, options, verifier: createVerifier,
    ...(mode === 'verifier' ? {} : { viewer: createViewer, getRuntime: (viewer) => getViewerHandle(viewer).runtime }),
    ...(mode === 'designer' ? { newDiagram: newDiagramDialog, designer: (viewer) => createDesigner(viewer, { authority: { async authorize(action) {
                    const grants = ['model.edit', 'model.verify', 'lifecycle.review', 'lifecycle.accept', 'lifecycle.reopen'];
                    return { allowed: grants.includes(action), principal: 'local-user', grants };
                } } }) } : {}),
    ...(host.DDN_SITE_INITIAL ? { initial: { ...host.DDN_SITE_INITIAL, view: parameters.get('view') ?? undefined } } : {}),
    ready: state => { Object.defineProperty(globalThis, 'DDN_SITE_STATE', { configurable: true, value: state }); document.documentElement.dataset.ready = 'true'; },
});
installWebsiteNavigation(mode);
//# sourceMappingURL=website-entry.js.map