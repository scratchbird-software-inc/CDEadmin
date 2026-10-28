/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"designer-f0c69783274d","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-7ffdd3196bf7","shared-9d235030a726"],"modules":[{"id":"standalone/src/modular-designer-entry.js","bytes":1012,"sha256":"a75890f56164b360b69f6b61e2e575ea72b990351dfe08c5d1281d0b3fa098ee","dependencies":["standalone/src/modular-designer-api.js","standalone/src/modular-shell.js","designer/src/new-diagram.js"]}],"hash":"c90d75ff823fb606aec8ac6dc7d86c62cc5c30c3d97fa13ea22875be7daabd5e"},{"standalone/src/modular-designer-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-designer-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const new_diagram_js_1 = require("designer/src/new-diagram.js");
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle, createDesigner } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'designer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime,
    newDiagram: new_diagram_js_1.newDiagramDialog,
    designer: viewer => createDesigner(viewer, { authority: { async authorize(action) {
                const grants = ['model.edit', 'model.verify', 'lifecycle.review', 'lifecycle.accept', 'lifecycle.reopen'];
                return { allowed: grants.includes(action), principal: 'local-user', grants };
            } } }),
}, api);

}});})();
