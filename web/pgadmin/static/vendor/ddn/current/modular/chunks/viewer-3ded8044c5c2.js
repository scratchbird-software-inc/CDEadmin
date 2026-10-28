/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"viewer-3ded8044c5c2","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-9d235030a726","shared-b954ff0d3573"],"modules":[{"id":"standalone/src/modular-viewer-entry.js","bytes":550,"sha256":"6a9bc916f20d0ef41e9f3d2c38bdf8e26e74422df02efdfc1d75ea0980b71bfc","dependencies":["standalone/src/modular-viewer-api.js","standalone/src/modular-shell.js"]}],"hash":"af158e0efcd93829b69abe95c22360066f5c3bb62d66493fcbb26dfca11b5c0e"},{"standalone/src/modular-viewer-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-viewer-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'viewer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime }, api);

}});})();
