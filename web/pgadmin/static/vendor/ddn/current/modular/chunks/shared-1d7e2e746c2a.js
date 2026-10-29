/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-1d7e2e746c2a","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-822f2cb38cc6","shared-ebd47c4e1fef"],"modules":[{"id":"standalone/src/modular-viewer-api.js","bytes":1572,"sha256":"b0927638764cf173a7f635f51f74d0e77d066eb6e582ecf90403891a18e01ec9","dependencies":["standalone/src/modular-viewer.js","standalone/src/modular-runtime.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js"]}],"hash":"1e99a6850dbb53e23c3f3f417c9189c08ada06a59d8af7e50ff60f533af20274"},{"standalone/src/modular-viewer-api.js":function(module,exports,require){
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
