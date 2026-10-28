import { fingerprint, clone, freeze, createContext, ComputationStopped } from './index.js';
// Keep the transport string local: importing worker-entry would pull headless verification into the UI adapter.
const channel = 'ddn.compute.v1';
function failure(request, outcome, message) {
    const echo = Object.fromEntries(Object.entries(Object.getOwnPropertyDescriptors(request)).filter(([key, descriptor]) => key !== 'payload' && descriptor.enumerable && 'value' in descriptor).map(([key, descriptor]) => [key, descriptor.value]));
    return { request: echo, outcome, payload: null, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: typeof echo.kind === 'string' ? [echo.kind] : [] }, diagnostics: [{ code: 'execution.' + outcome, severity: 'error', message }] };
}
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
/** One lazy worker per executor. The caller controls creation; this module never fetches code. */
export function createWorkerExecutor(options) {
    let worker, unavailable = false, destroyed = false, serial = 0;
    const jobs = new Map();
    const finish = (id, result) => {
        const job = jobs.get(id);
        if (!job)
            return;
        jobs.delete(id);
        job.unlisten?.();
        if (job.timer !== undefined)
            clearTimeout(job.timer);
        job.resolve(result);
    };
    const detach = () => {
        if (!worker)
            return;
        worker.removeEventListener('message', receive);
        worker.removeEventListener('error', crashed);
        worker.removeEventListener('messageerror', crashed);
        worker.terminate();
        worker = undefined;
    };
    const retry = (id) => {
        const job = jobs.get(id);
        if (!job || job.fallbackStarted)
            return;
        job.fallbackStarted = true;
        void (async () => {
            try {
                finish(id, await options.fallback.run(job.request, job.options));
            }
            catch (error) {
                finish(id, failure(job.request, 'invalid', String(error)));
            }
        })();
    };
    const crashed = () => {
        detach();
        unavailable = true;
        for (const id of jobs.keys())
            retry(id);
    };
    const receive = (event) => {
        const message = event.data;
        if (!record(message) || message.channel !== channel || !Number.isSafeInteger(message.id))
            return;
        const id = message.id, job = jobs.get(id);
        if (!job || job.fallbackStarted)
            return;
        if (message.type === 'failure') {
            retry(id);
            return;
        }
        if (message.type !== 'result' || !record(message.result))
            return;
        const result = message.result;
        try {
            if (fingerprint(result.request) !== job.echo)
                return;
        }
        catch {
            return;
        }
        finish(id, result);
    };
    const ensureWorker = () => {
        if (worker)
            return true;
        if (unavailable)
            return false;
        try {
            worker = options.createWorker();
            worker.addEventListener('message', receive);
            worker.addEventListener('error', crashed);
            worker.addEventListener('messageerror', crashed);
            return true;
        }
        catch {
            worker = undefined;
            unavailable = true;
            return false;
        }
    };
    return {
        async run(request, task = {}) {
            try {
                request = freeze(clone(request));
                const context = createContext(request.versions, task);
                context.check();
                task = context.task;
            }
            catch (error) {
                return failure(request, error instanceof ComputationStopped ? error.outcome : 'invalid', error instanceof Error ? error.message : 'Invalid computation input');
            }
            if (destroyed || task.cancel?.aborted)
                return Promise.resolve(failure(request, 'cancelled', 'Computation cancelled'));
            const { payload: _, ...echo } = request;
            return new Promise(resolve => {
                const id = ++serial, job = { request, options: task, resolve, echo: fingerprint(echo) };
                jobs.set(id, job);
                const stop = (outcome) => {
                    if (!jobs.has(id))
                        return;
                    try {
                        worker?.postMessage({ channel, type: 'cancel', id });
                    }
                    catch { /* An already failed worker cannot delay cancellation. */ }
                    finish(id, failure(request, outcome, outcome === 'cancelled' ? 'Computation cancelled' : 'Worker elapsed-time budget exhausted'));
                    if (jobs.size === 0)
                        detach();
                };
                if (task.cancel)
                    job.unlisten = task.cancel.onAbort(() => stop('cancelled'));
                if (task.budget && Number.isFinite(task.budget.elapsedMs) && task.budget.elapsedMs >= 0)
                    job.timer = setTimeout(() => stop('budget-exceeded'), task.budget.elapsedMs);
                if (task.cancel?.aborted) {
                    stop('cancelled');
                    return;
                }
                if (!ensureWorker()) {
                    retry(id);
                    return;
                }
                try {
                    worker.postMessage({ channel, type: 'run', id, request, ...(task.budget ? { budget: task.budget } : {}) });
                }
                catch {
                    crashed();
                }
            });
        },
        destroy() {
            if (destroyed)
                return;
            destroyed = true;
            detach();
            for (const [id, job] of jobs)
                finish(id, failure(job.request, 'cancelled', 'Executor destroyed'));
            options.fallback.destroy();
        },
    };
}
//# sourceMappingURL=worker-host.js.map