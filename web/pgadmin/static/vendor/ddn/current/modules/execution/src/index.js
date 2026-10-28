/** Portable, deterministic SHA-256; no browser, Node or asynchronous IO dependency. */
export function sha256(text) {
    const bytes = [];
    for (const character of text) {
        let n = character.codePointAt(0);
        if (n >= 0xd800 && n <= 0xdfff)
            n = 0xfffd;
        if (n < 128)
            bytes.push(n);
        else if (n < 2048)
            bytes.push(192 | n >> 6, 128 | n & 63);
        else if (n < 65536)
            bytes.push(224 | n >> 12, 128 | n >> 6 & 63, 128 | n & 63);
        else
            bytes.push(240 | n >> 18, 128 | n >> 12 & 63, 128 | n >> 6 & 63, 128 | n & 63);
    }
    const bits = bytes.length * 8;
    bytes.push(128);
    while (bytes.length % 64 !== 56)
        bytes.push(0);
    for (let i = 7; i >= 0; i--)
        bytes.push(Math.floor(bits / 2 ** (8 * i)) & 255);
    const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const k = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    const rotate = (n, b) => n >>> b | n << 32 - b;
    for (let offset = 0; offset < bytes.length; offset += 64) {
        const w = new Int32Array(64);
        for (let i = 0; i < 16; i++) {
            const p = offset + i * 4;
            w[i] = bytes[p] << 24 | bytes[p + 1] << 16 | bytes[p + 2] << 8 | bytes[p + 3];
        }
        for (let i = 16; i < 64; i++) {
            const a = w[i - 15], b = w[i - 2];
            w[i] = w[i - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ a >>> 3) + w[i - 7] + (rotate(b, 17) ^ rotate(b, 19) ^ b >>> 10) | 0;
        }
        let [a, b, c, d, e, f, g, j] = h;
        for (let i = 0; i < 64; i++) {
            const t1 = j + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + (e & f ^ ~e & g) + k[i] + w[i] | 0;
            const t2 = (rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + (a & b ^ a & c ^ b & c) | 0;
            j = g;
            g = f;
            f = e;
            e = d + t1 | 0;
            d = c;
            c = b;
            b = a;
            a = t1 + t2 | 0;
        }
        const parts = [a, b, c, d, e, f, g, j];
        for (let i = 0; i < 8; i++)
            h[i] = h[i] + parts[i] | 0;
    }
    return h.map(n => (n >>> 0).toString(16).padStart(8, '0')).join('');
}
/** Serialize data without calling getters/toJSON or silently filling sparse cells. */
function jsonData(value, sorted) {
    const active = new Set();
    const encode = (item) => {
        if (item === null || typeof item === 'string' || typeof item === 'boolean')
            return JSON.stringify(item);
        if (typeof item === 'number') {
            if (!Number.isFinite(item))
                throw new TypeError('DDN values must be finite');
            return JSON.stringify(item);
        }
        if (!item || typeof item !== 'object' || (!Array.isArray(item) && Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null))
            throw new TypeError('Expected plain JSON data');
        if (active.has(item))
            throw new TypeError('Cyclic JSON data');
        active.add(item);
        try {
            const descriptors = Object.getOwnPropertyDescriptors(item);
            if (Object.getOwnPropertySymbols(item).some(key => Object.getOwnPropertyDescriptor(item, key)?.enumerable))
                throw new TypeError('JSON data cannot have symbol keys');
            if (Array.isArray(item)) {
                const cells = [];
                for (let index = 0; index < item.length; index++) {
                    const descriptor = descriptors[String(index)];
                    if (!descriptor || !('value' in descriptor))
                        throw new TypeError('Expected dense JSON array data');
                    cells.push(encode(descriptor.value));
                }
                if (Object.keys(item).some(key => !/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= item.length))
                    throw new TypeError('JSON arrays cannot have named data properties');
                return '[' + cells.join(',') + ']';
            }
            const keys = Object.keys(item);
            if (sorted)
                keys.sort();
            const fields = [];
            for (const key of keys) {
                const descriptor = descriptors[key];
                if (!('value' in descriptor))
                    throw new TypeError('JSON data cannot contain accessors');
                // Optional API fields retain their established omission convention.
                if (descriptor.value !== undefined)
                    fields.push(JSON.stringify(key) + ':' + encode(descriptor.value));
            }
            return '{' + fields.join(',') + '}';
        }
        finally {
            active.delete(item);
        }
    };
    return encode(value);
}
export function canonical(value) { return value === undefined ? 'null' : jsonData(value, true); }
export const fingerprint = (value) => sha256(canonical(value));
export function clone(value) { return JSON.parse(jsonData(value, false)); }
export function freeze(value) {
    const seen = new Set();
    const visit = (item) => {
        if (!item || typeof item !== 'object' || ArrayBuffer.isView(item) || seen.has(item))
            return;
        seen.add(item);
        Object.freeze(item);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(item)))
            if ('value' in descriptor)
                visit(descriptor.value);
    };
    visit(value);
    return value;
}
export class ComputationStopped extends Error {
    outcome;
    constructor(outcome, message) {
        super(message);
        this.outcome = outcome;
    }
}
const schedule = () => new Promise(resolve => {
    const host = globalThis;
    if (host.setTimeout)
        host.setTimeout(resolve, 0);
    else
        resolve();
});
export function createContext(versions, task = {}) {
    const start = Date.now();
    let units = 0, memory = 0, slice = start;
    const budget = task.budget ? { ...task.budget } : undefined;
    if (budget && [budget.elapsedMs, budget.workUnits, budget.memoryBytes].some(n => !Number.isFinite(n) || n < 0))
        throw new RangeError('Invalid operation budget');
    if (budget)
        Object.freeze(budget);
    const capturedTask = Object.freeze({ ...(task.cancel ? { cancel: task.cancel } : {}), ...(budget ? { budget } : {}) });
    const capturedVersions = freeze(clone(versions));
    function check() {
        if (capturedTask.cancel?.aborted)
            throw new ComputationStopped('cancelled', 'Operation cancelled');
        if (budget && (Date.now() - start > budget.elapsedMs || units > budget.workUnits || memory > budget.memoryBytes))
            throw new ComputationStopped('budget-exceeded', 'Operation budget exhausted');
    }
    return {
        versions: capturedVersions, task: capturedTask, check,
        get stats() { return { elapsedMs: Date.now() - start, workUnits: units, memoryBytes: memory }; },
        accountMemory(bytes) { if (!Number.isFinite(bytes) || bytes < 0)
            throw new RangeError('Invalid memory accounting'); memory = bytes; check(); },
        async checkpoint(count) {
            if (!Number.isFinite(count) || count < 0)
                throw new RangeError('Invalid work accounting');
            units += count;
            check();
            if (Date.now() - slice >= 4) {
                await schedule();
                slice = Date.now();
                check();
            }
        },
    };
}
export function createExecutor(handlers) {
    let disposed = false;
    const active = new Set();
    return {
        async run(request, options = {}) {
            const local = { aborted: disposed, listeners: new Set() };
            active.add(local);
            const upstreamCancel = options.cancel;
            const unlisten = upstreamCancel?.onAbort(() => {
                local.aborted = true;
                for (const fn of local.listeners)
                    fn();
            });
            const cancel = { get aborted() { return local.aborted || !!upstreamCancel?.aborted; }, onAbort(fn) { local.listeners.add(fn); return () => { local.listeners.delete(fn); }; } };
            try {
                request = freeze(clone(request));
                const context = createContext(request.versions, { ...options, cancel });
                context.check();
                const handler = ['decode', 'verify', 'project', 'layout', 'route', 'capture'].includes(request.kind) && Object.prototype.hasOwnProperty.call(handlers, request.kind) ? handlers[request.kind] : undefined;
                if (!handler)
                    return failed(request, 'unsupported', 'No handler for ' + request.kind);
                const result = await handler(request, context);
                context.check();
                return result;
            }
            catch (error) {
                if (error instanceof ComputationStopped)
                    return failed(request, error.outcome, error.message);
                return failed(request, 'invalid', error instanceof Error ? error.message : 'Computation failed');
            }
            finally {
                unlisten?.();
                active.delete(local);
            }
        },
        destroy() {
            disposed = true;
            for (const job of active) {
                job.aborted = true;
                for (const fn of job.listeners)
                    fn();
            }
            active.clear();
        },
    };
}
function failed(request, outcome, message) {
    // A rejected payload must not execute an accessor while building diagnostics.
    const echo = Object.fromEntries(Object.entries(Object.getOwnPropertyDescriptors(request)).filter(([key, descriptor]) => key !== 'payload' && descriptor.enumerable && 'value' in descriptor).map(([key, descriptor]) => [key, descriptor.value]));
    return { request: echo, outcome, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: typeof echo.kind === 'string' ? [echo.kind] : [] }, diagnostics: [{ code: 'execution.' + outcome, severity: 'error', message }], payload: null };
}
//# sourceMappingURL=index.js.map