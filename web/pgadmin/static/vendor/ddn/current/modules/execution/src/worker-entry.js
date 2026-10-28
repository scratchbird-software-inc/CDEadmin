import { createComputeExecutor } from './compute.js';
import { fingerprint } from './index.js';
export const WORKER_CHANNEL = 'ddn.compute.v1';
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
/** Explicit installation keeps imports inert in browsers, workers and headless hosts. */
export function installWorkerServer(port, executor) {
    let closed = false;
    const active = new Map();
    const receive = (event) => {
        const message = event.data;
        if (!record(message) || message.channel !== WORKER_CHANNEL || !Number.isSafeInteger(message.id))
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
        // JSON-only request validation also rejects functions and nonfinite payloads before execution.
        try {
            fingerprint(request);
        }
        catch {
            return;
        }
        const cancellation = token();
        active.set(id, cancellation);
        void executor.run(request, { cancel: cancellation.value, ...(record(message.budget) ? { budget: message.budget } : {}) }).then(result => {
            if (!closed)
                port.postMessage({ channel: WORKER_CHANNEL, type: 'result', id, result });
        }).catch(error => {
            if (!closed)
                port.postMessage({ channel: WORKER_CHANNEL, type: 'failure', id, message: error instanceof Error ? error.message : 'Worker computation failed' });
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
export function bootComputeWorker(options, port = globalThis) {
    return installWorkerServer(port, createComputeExecutor(options));
}
//# sourceMappingURL=worker-entry.js.map