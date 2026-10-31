/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"verifier-9bc8faf36f88","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-4bf188bec7e8","shared-98f4118492a6"],"modules":[{"id":"standalone/src/modular-verifier-entry.js","bytes":446,"sha256":"08375a6c8f5c789d9d7c660a7bb459f710f3fd3ec0276688b0b624f5e357c742","dependencies":["standalone/src/modular-verifier-api.js","standalone/src/modular-shell.js"]}],"hash":"90ecec94c94027bea6a21d3394aec775d431402f2884db1371db4a4c4a7480ef"},{"standalone/src/modular-verifier-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-verifier-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createModularRuntimeOptions, createVerifier } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'verifier', options: createModularRuntimeOptions, verifier: createVerifier }, api);

}});})();
