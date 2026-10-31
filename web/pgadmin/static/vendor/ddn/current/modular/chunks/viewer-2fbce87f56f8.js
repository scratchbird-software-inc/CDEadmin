/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"viewer-2fbce87f56f8","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-4bf188bec7e8","shared-81115fead3d4"],"modules":[{"id":"standalone/src/modular-viewer-entry.js","bytes":550,"sha256":"6a9bc916f20d0ef41e9f3d2c38bdf8e26e74422df02efdfc1d75ea0980b71bfc","dependencies":["standalone/src/modular-viewer-api.js","standalone/src/modular-shell.js"]}],"hash":"bb2e9edf86873285b5bab2a4889564b83b119da0d302be188701ddf6158cc676"},{"standalone/src/modular-viewer-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-viewer-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'viewer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime }, api);

}});})();
