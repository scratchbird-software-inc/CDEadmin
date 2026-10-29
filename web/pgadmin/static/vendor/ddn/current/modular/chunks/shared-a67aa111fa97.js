/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-a67aa111fa97","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-ebd47c4e1fef"],"modules":[{"id":"standalone/src/modular-verifier-api.js","bytes":940,"sha256":"9347cf5d7a9c201750ebcbc36e15a0a7f0b8f13be8831eca08c0f5cbce81f170","dependencies":["standalone/src/modular-loading.js","standalone/src/modular-verifier.js"]}],"hash":"b0d29295831d218fb9baef4f48bb0bec2934b214fa03232ab4a0d65fa98c539b"},{"standalone/src/modular-verifier-api.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createVerifier = exports.createBrowserRuntimeOptions = exports.createModularRuntimeOptions = void 0;
var modular_loading_js_1 = require("standalone/src/modular-loading.js");
Object.defineProperty(exports, "createModularRuntimeOptions", { enumerable: true, get: function () { return modular_loading_js_1.createModularRuntimeOptions; } });
Object.defineProperty(exports, "createBrowserRuntimeOptions", { enumerable: true, get: function () { return modular_loading_js_1.createModularBrowserOptions; } });
var modular_verifier_js_1 = require("standalone/src/modular-verifier.js");
Object.defineProperty(exports, "createVerifier", { enumerable: true, get: function () { return modular_verifier_js_1.createModularVerifier; } });
const modular_loading_js_2 = require("standalone/src/modular-loading.js");
(0, modular_loading_js_2.installModularWorkerFactory)();

}});})();
