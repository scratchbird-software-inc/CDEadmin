/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"viewer-defe0ef52de3","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-1d7e2e746c2a","shared-e37dea31afcf"],"modules":[{"id":"standalone/src/modular-viewer-entry.js","bytes":550,"sha256":"6a9bc916f20d0ef41e9f3d2c38bdf8e26e74422df02efdfc1d75ea0980b71bfc","dependencies":["standalone/src/modular-viewer-api.js","standalone/src/modular-shell.js"]}],"hash":"19c2694753882f76000f39a6292db4e05abfa548e4c8ee27ecc8b3c148244d62"},{"standalone/src/modular-viewer-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-viewer-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createBrowserRuntimeOptions, createVerifier, createViewer, getViewerHandle } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'viewer', options: createBrowserRuntimeOptions, verifier: createVerifier, viewer: createViewer, getRuntime: viewer => getViewerHandle(viewer).runtime }, api);

}});})();
