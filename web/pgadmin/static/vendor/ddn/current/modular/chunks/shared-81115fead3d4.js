/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-81115fead3d4","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-8776885c04b2","shared-cca37dc67bcd"],"modules":[{"id":"standalone/src/modular-viewer-api.js","bytes":1572,"sha256":"b0927638764cf173a7f635f51f74d0e77d066eb6e582ecf90403891a18e01ec9","dependencies":["standalone/src/modular-viewer.js","standalone/src/modular-runtime.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js"]}],"hash":"94f8d25cb28f14cf9c3435296ab890a68850461d1af8fe80fdc2da3985dcb223"},{"standalone/src/modular-viewer-api.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createVerifier = exports.createBrowserRuntimeOptions = exports.createModularRuntimeOptions = exports.createRuntime = exports.getViewerHandle = exports.createViewer = void 0;
var modular_viewer_js_1 = require("standalone/src/modular-viewer.js");
Object.defineProperty(exports, "createViewer", { enumerable: true, get: function () { return modular_viewer_js_1.createViewer; } });
Object.defineProperty(exports, "getViewerHandle", { enumerable: true, get: function () { return modular_viewer_js_1.getViewerHandle; } });
var modular_runtime_js_1 = require("standalone/src/modular-runtime.js");
Object.defineProperty(exports, "createRuntime", { enumerable: true, get: function () { return modular_runtime_js_1.createModularRuntime; } });
var modular_loading_js_1 = require("standalone/src/modular-loading.js");
Object.defineProperty(exports, "createModularRuntimeOptions", { enumerable: true, get: function () { return modular_loading_js_1.createModularRuntimeOptions; } });
Object.defineProperty(exports, "createBrowserRuntimeOptions", { enumerable: true, get: function () { return modular_loading_js_1.createModularBrowserOptions; } });
var modular_verifier_js_1 = require("standalone/src/modular-verifier.js");
Object.defineProperty(exports, "createVerifier", { enumerable: true, get: function () { return modular_verifier_js_1.createModularVerifier; } });
const modular_loading_js_2 = require("standalone/src/modular-loading.js");
(0, modular_loading_js_2.installModularWorkerFactory)();

}});})();
