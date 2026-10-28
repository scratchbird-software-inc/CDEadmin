/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-b954ff0d3573","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-9eb6624f1d40","shared-c0332320f91a"],"modules":[{"id":"standalone/src/modular-viewer-api.js","bytes":1572,"sha256":"b0927638764cf173a7f635f51f74d0e77d066eb6e582ecf90403891a18e01ec9","dependencies":["standalone/src/modular-viewer.js","standalone/src/modular-runtime.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js"]}],"hash":"9a5b937d6c0ecfdf3b9dc53be7f0c99fcce489f8a58cdd044ba400725f43d074"},{"standalone/src/modular-viewer-api.js":function(module,exports,require){
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
