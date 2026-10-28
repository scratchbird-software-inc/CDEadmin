/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-c0332320f91a","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-27149a72b67b","shared-90accf46a20e","shared-da593b1d80b5"],"modules":[{"id":"execution/src/browser-verifier.js","bytes":8393,"sha256":"a699b49ac4dbdfbf493ab345afd15fe824a4b2f83d366faa23ff996b2da64162","dependencies":["verifier/src/index.js","execution/src/compute.js","execution/src/index.js","model/src/index.js","language/src/index.js"]},{"id":"execution/src/worker-host.js","bytes":6026,"sha256":"b0569b105f10e2170aa340828b9fc95177952db8781327fb31dd1d8648b470e6","dependencies":["execution/src/index.js"]},{"id":"runtime/src/versions.js","bytes":294,"sha256":"4375f5857d16261cbf03179e360105c841c3d6cd6554443516b0e7e943df4485","dependencies":["execution/src/index.js"]},{"id":"standalone/src/browser-options.js","bytes":705,"sha256":"debb6d9dc7871d52729d7b033a0544cc394c2adeab1058c87db5047aec10c2ee","dependencies":["execution/src/compute.js","execution/src/worker-host.js"]},{"id":"standalone/src/modular-loading.js","bytes":7384,"sha256":"efba083657845df10aa32996cbf8df099eeb7397fda06d766266610d9389b366","dependencies":["language/src/index.js","profiles/src/core.js","profiles/src/generated-families.js","profiles/src/family-packs.js","runtime/src/versions.js","standalone/src/browser-options.js","execution/src/index.js"]},{"id":"standalone/src/modular-verifier.js","bytes":4924,"sha256":"ba6e21968d9978b3d436fcf5ce8a77cbdf7df87a5cc83582db92098a94e480e5","dependencies":["profiles/src/family-packs.js","execution/src/browser-verifier.js","execution/src/index.js","standalone/src/browser-options.js","standalone/src/modular-loading.js"]}],"hash":"dff85034dc07e9c032138b9e45a1a0c4fe52d421c16b29c63d68f0ab05ab557f"},{"execution/src/browser-verifier.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createBrowserVerifier = createBrowserVerifier;
const index_js_1 = require("verifier/src/index.js");
const compute_js_1 = require("execution/src/compute.js");
const index_js_2 = require("execution/src/index.js");
const index_js_3 = require("model/src/index.js");
const index_js_4 = require("language/src/index.js");
function plainData(value) {
    if (!value || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value)) || Object.values(Object.getOwnPropertyDescriptors(value)).some(d => !('value' in d)))
        throw Error('Expected plain data without accessors');
}
function captureTask(input) {
    plainData(input);
    const { cancel, ...data } = input;
    return Object.freeze({ ...(0, index_js_2.freeze)((0, index_js_2.clone)(data)), ...(cancel ? { cancel } : {}) });
}
function captureSources(input) {
    plainData(input);
    if (!Array.isArray(input.files) || Object.values(Object.getOwnPropertyDescriptors(input.files)).some(d => !('value' in d)))
        throw Error('Expected source files');
    const files = Array.prototype.map.call(input.files, (file) => {
        plainData(file);
        if (typeof file.text !== 'string' || typeof file.revision !== 'string' || !file.revision || file.encoding !== 'utf-8' || typeof file.writable !== 'boolean')
            throw Error('Malformed source file');
        const { originalBytes, ...data } = file;
        if (originalBytes !== undefined) {
            if (!(originalBytes instanceof Uint8Array))
                throw Error('Source bytes must be Uint8Array');
            const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(originalBytes);
            if (decoded !== file.text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === file.text))
                throw Error('Source bytes do not match decoded text');
        }
        return { ...(0, index_js_2.clone)(data), id: (0, index_js_3.normalizeLocation)(file.id) };
    });
    return (0, index_js_2.freeze)((0, index_js_2.clone)({ entry: (0, index_js_3.normalizeLocation)(input.entry), files }));
}
let sessions = 0;
function createBrowserVerifier(inputOptions) {
    const options = { ...inputOptions, versions: (0, index_js_2.freeze)((0, index_js_2.clone)(inputOptions.versions)), ...(inputOptions.limits ? { limits: (0, index_js_2.freeze)((0, index_js_2.clone)(inputOptions.limits)) } : {}) };
    const { executor: provided, ...localOptions } = options;
    const executor = provided ?? (0, compute_js_1.createComputeExecutor)(localOptions), local = (0, index_js_1.createVerifier)(localOptions);
    const sessionId = 'ddn-verifier-' + (++sessions);
    let serial = 0, destroyed = false;
    const task = (value) => ({ ...(options.limits ? { budget: options.limits } : {}), ...value });
    const request = (kind, payload, revision, dependencyFingerprint) => ({ protocol: 1, sessionId, jobId: String(++serial), kind, payload, revision, versions: options.versions, dependencyFingerprint, fontGeneration: '0', styleGeneration: '0' });
    const interrupted = (result, verifyOptions, revision, digest) => (0, index_js_2.freeze)({ requestId: result.request.jobId, outcome: result.outcome, revision, versions: options.versions, dependencyFingerprint: digest, scope: verifyOptions.scope, purpose: verifyOptions.purpose, level: verifyOptions.level, coverage: { ...result.coverage, scope: verifyOptions.scope, complete: false }, diagnostics: result.diagnostics, missing: result.coverage.unavailable, ruleVersions: {}, reviewEligible: false, stats: { elapsedMs: 0, workUnits: 0, cacheHits: 0 } });
    async function verifyModel(snapshotInput, optionsInput, diagnostics = []) {
        let snapshot, verifyOptions;
        try {
            snapshot = (0, index_js_2.freeze)((0, index_js_2.clone)(snapshotInput));
            plainData(snapshot);
            plainData(snapshot.revision);
            if (typeof snapshot.semanticFingerprint !== 'string')
                throw Error('Expected snapshot fingerprint');
            verifyOptions = captureTask(optionsInput);
        }
        catch {
            return local.verifyModel(snapshotInput, optionsInput);
        }
        if (destroyed)
            return local.verifyModel(snapshot, verifyOptions);
        const payload = { snapshot, options: { scope: verifyOptions.scope, purpose: verifyOptions.purpose, level: verifyOptions.level, ...(verifyOptions.measurement ? { measurement: verifyOptions.measurement } : {}) }, ...(diagnostics.length ? { diagnostics } : {}) };
        const result = await executor.run(request('verify', payload, snapshot.revision, snapshot.semanticFingerprint), task(verifyOptions));
        if (result.payload && typeof result.payload === 'object' && !Array.isArray(result.payload) && 'requestId' in result.payload)
            return (0, index_js_2.freeze)((0, index_js_2.clone)(result.payload));
        return interrupted(result, verifyOptions, snapshot.revision, snapshot.semanticFingerprint);
    }
    return {
        async verifySources(inputArgument, optionsArgument) {
            let input, verifyOptions;
            try {
                input = captureSources(inputArgument);
                verifyOptions = captureTask(optionsArgument);
            }
            catch {
                return local.verifySources(inputArgument, optionsArgument);
            }
            if (destroyed)
                return local.verifySources(input, verifyOptions);
            const started = Date.now(), sourceUnits = input.files.reduce((n, f) => n + f.text.length, 0), sourceTask = task(verifyOptions);
            const revision = { model: '0', sources: Object.fromEntries(input.files.map(f => [f.id, f.revision])), data: {} };
            const result = await executor.run(request('decode', (0, compute_js_1.decodePayload)(input), revision, (0, index_js_2.fingerprint)(input.files.map(f => [f.id, f.revision, f.text]))), sourceTask);
            const payload = result.payload;
            if (!payload?.decoded)
                return interrupted(result, verifyOptions, revision, result.request.dependencyFingerprint);
            const snapshot = { contract: 'ddn-next-1', rootFile: input.entry, revision: { ...revision, model: payload.fingerprint }, versions: options.versions, semanticFingerprint: payload.fingerprint, normalized: payload.decoded.normalized, coverage: payload.decoded.coverage };
            const remaining = sourceTask.budget ? { ...sourceTask.budget, elapsedMs: Math.max(0, sourceTask.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, sourceTask.budget.workUnits - sourceUnits) } : undefined;
            const report = await verifyModel(snapshot, { ...verifyOptions, ...(remaining ? { budget: remaining } : {}) }, payload.decoded.diagnostics);
            const spans = new Map();
            const refKey = (ref) => JSON.stringify([ref.file, ref.id]);
            for (const node of (0, index_js_4.allNodes)(payload.decoded))
                if (node.ref && !spans.has(refKey(node.ref)))
                    spans.set(refKey(node.ref), { file: node.file, revision: input.files.find(file => file.id === node.file).revision, start: node.start, end: node.end });
            const root = input.files.find(file => file.id === input.entry);
            const diagnostics = report.diagnostics.map(diagnostic => {
                if (diagnostic.source)
                    return diagnostic;
                const span = diagnostic.target ? spans.get(refKey(diagnostic.target)) : undefined;
                return span ? { ...diagnostic, source: span } : root ? { ...diagnostic, source: { file: root.id, revision: root.revision, start: 0, end: root.text.length } } : diagnostic;
            });
            return (0, index_js_2.freeze)({ ...report, diagnostics, stats: { ...report.stats, elapsedMs: Date.now() - started, workUnits: sourceUnits + report.stats.workUnits } });
        },
        verifyModel: (snapshot, verifyOptions) => verifyModel(snapshot, verifyOptions),
        checkTransition: (snapshot, transition, verifyOptions) => local.checkTransition(snapshot, transition, verifyOptions),
        destroy() {
            if (destroyed)
                return;
            destroyed = true;
            executor.destroy();
            local.destroy();
        },
    };
}

},
"execution/src/worker-host.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createWorkerExecutor = createWorkerExecutor;
const index_js_1 = require("execution/src/index.js");
const channel = 'ddn.compute.v1';
function failure(request, outcome, message) {
    const echo = Object.fromEntries(Object.entries(Object.getOwnPropertyDescriptors(request)).filter(([key, descriptor]) => key !== 'payload' && descriptor.enumerable && 'value' in descriptor).map(([key, descriptor]) => [key, descriptor.value]));
    return { request: echo, outcome, payload: null, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: typeof echo.kind === 'string' ? [echo.kind] : [] }, diagnostics: [{ code: 'execution.' + outcome, severity: 'error', message }] };
}
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function createWorkerExecutor(options) {
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
            if ((0, index_js_1.fingerprint)(result.request) !== job.echo)
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
                request = (0, index_js_1.freeze)((0, index_js_1.clone)(request));
                const context = (0, index_js_1.createContext)(request.versions, task);
                context.check();
                task = context.task;
            }
            catch (error) {
                return failure(request, error instanceof index_js_1.ComputationStopped ? error.outcome : 'invalid', error instanceof Error ? error.message : 'Invalid computation input');
            }
            if (destroyed || task.cancel?.aborted)
                return Promise.resolve(failure(request, 'cancelled', 'Computation cancelled'));
            const { payload: _, ...echo } = request;
            return new Promise(resolve => {
                const id = ++serial, job = { request, options: task, resolve, echo: (0, index_js_1.fingerprint)(echo) };
                jobs.set(id, job);
                const stop = (outcome) => {
                    if (!jobs.has(id))
                        return;
                    try {
                        worker?.postMessage({ channel, type: 'cancel', id });
                    }
                    catch { }
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

},
"runtime/src/versions.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STANDARD_VERSIONS = void 0;
const index_js_1 = require("execution/src/index.js");
exports.STANDARD_VERSIONS = (0, index_js_1.freeze)({ api: '1.0', language: 'ddn-next-1', defaults: 'ddn-next-1', packs: {} });

},
"standalone/src/browser-options.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.withBrowserExecutor = withBrowserExecutor;
const compute_js_1 = require("execution/src/compute.js");
const worker_host_js_1 = require("execution/src/worker-host.js");
function withBrowserExecutor(options) {
    const host = globalThis;
    const executor = (0, worker_host_js_1.createWorkerExecutor)({
        createWorker: () => {
            if (!host.__ddnCreateWorker)
                throw new Error('No local worker factory supplied');
            return host.__ddnCreateWorker(options);
        },
        fallback: (0, compute_js_1.createComputeExecutor)(options),
    });
    return { ...options, executor };
}

},
"standalone/src/modular-loading.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.HostStopped = exports.scanUnits = void 0;
exports.requiredProfiles = requiredProfiles;
exports.remainingTask = remainingTask;
exports.ensureProfileInput = ensureProfileInput;
exports.createModularRuntimeOptions = createModularRuntimeOptions;
exports.createModularBrowserOptions = createModularBrowserOptions;
exports.installModularWorkerFactory = installModularWorkerFactory;
exports.loadingDiagnostic = loadingDiagnostic;
exports.verificationFailure = verificationFailure;
const index_js_1 = require("language/src/index.js");
const core_js_1 = require("profiles/src/core.js");
const generated_families_js_1 = require("profiles/src/generated-families.js");
const family_packs_js_1 = require("profiles/src/family-packs.js");
const versions_js_1 = require("runtime/src/versions.js");
const browser_options_js_1 = require("standalone/src/browser-options.js");
const index_js_2 = require("execution/src/index.js");
const loader = () => {
    const value = globalThis.DDN_LOADER;
    if (!value)
        throw new Error('The local DDN pack loader is unavailable.');
    return value;
};
function requiredProfiles(input, task = {}) {
    if (Array.isArray(input))
        return [...new Set(input)];
    const value = input;
    const normalized = 'normalized' in value ? value.normalized : (0, index_js_1.decodeSources)(value, task).normalized;
    return [...new Set((0, core_js_1.indexRecords)(normalized).filter(record => record.owner === 'view_definition' || record.owner === 'document').map(record => typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1'))];
}
const scanUnits = (input) => Array.isArray(input) ? input.length : 'files' in input ? input.files.reduce((total, file) => total + file.text.length, 0) : (0, core_js_1.indexRecords)(input.normalized).length;
exports.scanUnits = scanUnits;
function remainingTask(task, started, units) {
    return task.budget ? { ...task, budget: { ...task.budget, elapsedMs: Math.max(0, task.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, task.budget.workUnits - units) } } : task;
}
function waitForPack(pending, task, started) {
    return new Promise((resolve, reject) => {
        let settled = false, timer, unsubscribe;
        const finish = (error, value) => {
            if (settled)
                return;
            settled = true;
            if (timer !== undefined)
                clearTimeout(timer);
            unsubscribe?.();
            error === undefined ? resolve(value) : reject(error);
        };
        unsubscribe = task.cancel?.onAbort(() => finish(new index_js_2.ComputationStopped('cancelled', 'Profile loading was cancelled.')));
        if (settled)
            unsubscribe?.();
        if (task.cancel?.aborted)
            finish(new index_js_2.ComputationStopped('cancelled', 'Profile loading was cancelled.'));
        if (!settled && task.budget) {
            const remaining = task.budget.elapsedMs - (Date.now() - started);
            if (remaining <= 0)
                finish(new index_js_2.ComputationStopped('budget-exceeded', 'Profile loading exhausted the operation budget.'));
            else
                timer = setTimeout(() => finish(new index_js_2.ComputationStopped('budget-exceeded', 'Profile loading exhausted the operation budget.')), remaining);
        }
        pending.then(value => finish(undefined, value), error => finish(error));
    });
}
async function ensureProfileInput(input, drawing, task = {}) {
    const started = Date.now(), context = (0, index_js_2.createContext)(versions_js_1.STANDARD_VERSIONS, task);
    context.check();
    const units = (0, exports.scanUnits)(input);
    if (!Array.isArray(input) && 'files' in input)
        context.accountMemory(units * 2);
    await context.checkpoint(units);
    const families = [...new Set(requiredProfiles(input, task).map(generated_families_js_1.profileCatalogueFamily).filter((family) => !!family && family !== 'native'))];
    await Promise.all(families.map(async (family) => {
        try {
            context.check();
            await waitForPack(loader().loadEntry('verify:' + family), task, started);
            if (drawing) {
                context.check();
                await waitForPack(loader().loadEntry('render:' + family), task, started);
            }
        }
        catch (error) {
            if (error instanceof index_js_2.ComputationStopped)
                throw error;
            throw new Error('Unable to load the local DDN ' + family + ' pack: ' + (error instanceof Error ? error.message : String(error)));
        }
    }));
    context.check();
}
function createModularRuntimeOptions() { return { versions: versions_js_1.STANDARD_VERSIONS, packs: (0, family_packs_js_1.loadedProfilePacks)() }; }
function createModularBrowserOptions() { return (0, browser_options_js_1.withBrowserExecutor)(createModularRuntimeOptions()); }
function installModularWorkerFactory() {
    Object.defineProperty(globalThis, '__ddnCreateWorker', { configurable: true, value: (options) => {
            const packs = options?.packs ?? (0, family_packs_js_1.loadedProfilePacks)();
            const initializers = packs.filter(pack => pack.manifest.id !== 'ddn-native' && !pack.manifest.id.endsWith('-commands')).map(pack => {
                const family = pack.manifest.id.slice(4);
                if (!['graphs', 'charts', 'geography', 'surfaces'].includes(family))
                    throw new Error('No local compute initializer for pack ' + pack.manifest.id);
                return 'verify:' + family;
            });
            return loader().worker('worker', initializers);
        } });
}
class HostStopped extends Error {
    reason;
    constructor(reason, message) {
        super(message);
        this.reason = reason;
    }
}
exports.HostStopped = HostStopped;
function loadingDiagnostic(error, prefix = 'runtime') {
    const reason = error instanceof index_js_2.ComputationStopped ? error.outcome : error instanceof HostStopped ? error.reason : 'pack';
    return { code: prefix + '.' + reason, severity: reason === 'cancelled' || reason === 'stale' ? 'info' : 'error', message: error instanceof Error ? error.message : 'Unable to load required profile packs.' };
}
let verificationSequence = 0;
function verificationFailure(input, task, versions, error, started) {
    const model = 'normalized' in input;
    const outcome = error instanceof index_js_2.ComputationStopped ? error.outcome : error instanceof HostStopped ? 'cancelled' : 'unsupported';
    return { requestId: 'profile-loading-' + (++verificationSequence), outcome,
        revision: model ? input.revision : { model: '0', sources: Object.fromEntries(input.files.map(file => [file.id, file.revision])), data: {} }, versions,
        dependencyFingerprint: model ? input.semanticFingerprint : (0, index_js_2.fingerprint)(input.files.map(file => [file.id, file.revision, file.text])),
        scope: task.scope, purpose: task.purpose, level: task.level, coverage: { scope: task.scope, complete: false, checked: [], unavailable: ['profile-loading'] },
        diagnostics: [loadingDiagnostic(error, 'DDN-PROFILE-LOAD')], missing: ['profile-loading'], ruleVersions: {}, reviewEligible: false,
        stats: { elapsedMs: Date.now() - started, workUnits: 0, cacheHits: 0 },
    };
}

},
"standalone/src/modular-verifier.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createModularVerifier = createModularVerifier;
const family_packs_js_1 = require("profiles/src/family-packs.js");
const browser_verifier_js_1 = require("execution/src/browser-verifier.js");
const index_js_1 = require("execution/src/index.js");
const browser_options_js_1 = require("standalone/src/browser-options.js");
const modular_loading_js_1 = require("standalone/src/modular-loading.js");
function mergePacks(options) {
    const result = [...options.packs], ids = new Set(result.map(pack => pack.manifest.id));
    const profiles = new Set(result.flatMap(pack => pack.registrations.profiles?.map(profile => profile.id) ?? []));
    for (const pack of (0, family_packs_js_1.loadedProfilePacks)()) {
        if (ids.has(pack.manifest.id) || pack.manifest.profiles.every(profile => profiles.has(profile)))
            continue;
        if (pack.manifest.profiles.some(profile => profiles.has(profile)))
            throw new Error('Conflicting host profile registrations: ' + pack.manifest.id);
        result.push(pack);
        ids.add(pack.manifest.id);
        for (const profile of pack.manifest.profiles)
            profiles.add(profile);
    }
    return result;
}
function createModularVerifier(options = (0, modular_loading_js_1.createModularRuntimeOptions)()) {
    const verifiers = new Map();
    let destroyed = false, providedUsed = false;
    const initial = (0, index_js_1.canonical)(options.packs.map(pack => pack.manifest));
    const effective = (task = {}) => ({ ...(options.limits ? { budget: options.limits } : {}), ...task });
    const current = () => {
        if (destroyed)
            throw new modular_loading_js_1.HostStopped('disposed', 'Verifier is disposed.');
        const packs = mergePacks(options), signature = (0, index_js_1.canonical)(packs.map(pack => pack.manifest));
        let verifier = verifiers.get(signature);
        if (!verifier) {
            const { executor, ...base } = options;
            const next = executor ? { ...base, packs, ...(signature === initial ? { executor } : {}) } : (0, browser_options_js_1.withBrowserExecutor)({ ...base, packs });
            if (executor && signature === initial)
                providedUsed = true;
            verifier = (0, browser_verifier_js_1.createBrowserVerifier)(next);
            verifiers.set(signature, verifier);
        }
        return verifier;
    };
    return {
        async verifySources(input, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new modular_loading_js_1.HostStopped('disposed', 'Verifier is disposed.');
                await (0, modular_loading_js_1.ensureProfileInput)(input, false, budget);
                return current().verifySources(input, { ...task, ...(0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)) });
            }
            catch (error) {
                return (0, modular_loading_js_1.verificationFailure)(input, task, options.versions, error, started);
            }
        },
        async verifyModel(input, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new modular_loading_js_1.HostStopped('disposed', 'Verifier is disposed.');
                await (0, modular_loading_js_1.ensureProfileInput)(input, false, budget);
                return current().verifyModel(input, { ...task, ...(0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)) });
            }
            catch (error) {
                return (0, modular_loading_js_1.verificationFailure)(input, task, options.versions, error, started);
            }
        },
        async checkTransition(input, transition, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new modular_loading_js_1.HostStopped('disposed', 'Verifier is disposed.');
                await (0, modular_loading_js_1.ensureProfileInput)(input, false, budget);
                return current().checkTransition(input, transition, (0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)));
            }
            catch (error) {
                return { allowed: false, diagnostics: [(0, modular_loading_js_1.loadingDiagnostic)(error, 'DDN-PROFILE-LOAD')] };
            }
        },
        destroy() {
            if (destroyed)
                return;
            destroyed = true;
            for (const verifier of verifiers.values())
                verifier.destroy();
            verifiers.clear();
            if (!providedUsed)
                options.executor?.destroy();
        },
    };
}

}});})();
