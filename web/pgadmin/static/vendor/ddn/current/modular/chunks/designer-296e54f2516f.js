/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"designer-296e54f2516f","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-673390dbad9b","shared-e37dea31afcf"],"modules":[{"id":"standalone/src/modular-designer-entry.js","bytes":1012,"sha256":"a75890f56164b360b69f6b61e2e575ea72b990351dfe08c5d1281d0b3fa098ee","dependencies":["standalone/src/modular-designer-api.js","standalone/src/modular-shell.js","designer/src/new-diagram.js"]}],"hash":"a4e5a7c2e294a94965ab441454b54dde70513d0fee8aa1f25a1459a4ed320e56"},{"standalone/src/modular-designer-entry.js":function(module,exports,require){
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
