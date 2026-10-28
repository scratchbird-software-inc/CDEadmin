/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"verifier-a92aa39dd4bd","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-9d235030a726","shared-cc6b5c75a915"],"modules":[{"id":"standalone/src/modular-verifier-entry.js","bytes":446,"sha256":"08375a6c8f5c789d9d7c660a7bb459f710f3fd3ec0276688b0b624f5e357c742","dependencies":["standalone/src/modular-verifier-api.js","standalone/src/modular-shell.js"]}],"hash":"b6a88f109453f3bc5e46093aa812c14f5e551affbfb09dd1cb8fa1bc447b45ef"},{"standalone/src/modular-verifier-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = void 0;
const api = require("standalone/src/modular-verifier-api.js");
exports.api = api;
const modular_shell_js_1 = require("standalone/src/modular-shell.js");
const { createModularRuntimeOptions, createVerifier } = api;
(0, modular_shell_js_1.bootModularShell)({ mode: 'verifier', options: createModularRuntimeOptions, verifier: createVerifier }, api);

}});})();
