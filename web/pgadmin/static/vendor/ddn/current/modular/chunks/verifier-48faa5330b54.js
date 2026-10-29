/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"verifier-48faa5330b54","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-a67aa111fa97","shared-e37dea31afcf"],"modules":[{"id":"standalone/src/modular-verifier-entry.js","bytes":446,"sha256":"08375a6c8f5c789d9d7c660a7bb459f710f3fd3ec0276688b0b624f5e357c742","dependencies":["standalone/src/modular-verifier-api.js","standalone/src/modular-shell.js"]}],"hash":"6b8cbc3e720214676ced4e10fea00845feb0e0749febe80b0c5c146c9df75afa"},{"standalone/src/modular-verifier-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-verifier-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createModularRuntimeOptions, createVerifier } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'verifier', options: createModularRuntimeOptions, verifier: createVerifier }, api);

}});})();
