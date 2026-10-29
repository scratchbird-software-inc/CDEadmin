/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"worker-f621ec472de9","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-e89a1c8e2b2d","shared-f98a38a4da4d"],"modules":[{"id":"execution/src/worker-entry.js","bytes":2810,"sha256":"c0f22663320cb570aed9c2cb108e9bc00f8b3fdad685273a1cb27a22047eb186","dependencies":["execution/src/compute.js","execution/src/index.js"]},{"id":"standalone/src/modular-worker.js","bytes":395,"sha256":"6f8af12f049da8a4d59687faa232365ca7204bbe0943b948c2a2dc63143e87cf","dependencies":["execution/src/worker-entry.js","profiles/src/family-packs.js"]}],"hash":"f79008172d50c608127ef92c62f9a17c26ba4850da530947665edb7a889446de"},{"execution/src/worker-entry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WORKER_CHANNEL = void 0;
exports.installWorkerServer = installWorkerServer;
exports.bootComputeWorker = bootComputeWorker;
const compute_js_1 = require("execution/src/compute.js");
const index_js_1 = require("execution/src/index.js");
exports.WORKER_CHANNEL = 'ddn.compute.v1';
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function token() {
    let aborted = false;
    const listeners = new Set();
    return { value: { get aborted() { return aborted; }, onAbort(fn) { listeners.add(fn); return () => { listeners.delete(fn); }; } }, abort() {
            if (aborted)
                return;
            aborted = true;
            for (const fn of listeners)
                fn();
            listeners.clear();
        } };
}
function installWorkerServer(port, executor) {
    let closed = false;
    const active = new Map();
    const receive = (event) => {
        const message = event.data;
        if (!record(message) || message.channel !== exports.WORKER_CHANNEL || !Number.isSafeInteger(message.id))
            return;
        const id = message.id;
        if (message.type === 'cancel') {
            active.get(id)?.abort();
            return;
        }
        if (message.type !== 'run' || !record(message.request) || active.has(id) || closed)
            return;
        const request = message.request;
        if (request.protocol !== 1 || typeof request.sessionId !== 'string' || typeof request.jobId !== 'string')
            return;
        try {
            (0, index_js_1.fingerprint)(request);
        }
        catch {
            return;
        }
        const cancellation = token();
        active.set(id, cancellation);
        void executor.run(request, { cancel: cancellation.value, ...(record(message.budget) ? { budget: message.budget } : {}) }).then(result => {
            if (!closed)
                port.postMessage({ channel: exports.WORKER_CHANNEL, type: 'result', id, result });
        }).catch(error => {
            if (!closed)
                port.postMessage({ channel: exports.WORKER_CHANNEL, type: 'failure', id, message: error instanceof Error ? error.message : 'Worker computation failed' });
        }).finally(() => { active.delete(id); });
    };
    port.addEventListener('message', receive);
    return () => {
        if (closed)
            return;
        closed = true;
        port.removeEventListener('message', receive);
        for (const job of active.values())
            job.abort();
        active.clear();
        executor.destroy();
    };
}
function bootComputeWorker(options, port = globalThis) {
    return installWorkerServer(port, (0, compute_js_1.createComputeExecutor)(options));
}

},
"standalone/src/modular-worker.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const worker_entry_js_1 = require("execution/src/worker-entry.js");
const family_packs_js_1 = require("profiles/src/family-packs.js");
(0, worker_entry_js_1.bootComputeWorker)({ versions: { api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} }, packs: (0, family_packs_js_1.loadedProfilePacks)() });

}});})();
