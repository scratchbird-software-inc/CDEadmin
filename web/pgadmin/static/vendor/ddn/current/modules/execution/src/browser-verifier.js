import { createVerifier } from '../../verifier/src/index.js';
import { createComputeExecutor, decodePayload } from './compute.js';
import { fingerprint, freeze, clone } from './index.js';
import { normalizeLocation } from '../../model/src/index.js';
import { allNodes } from '../../language/src/index.js';
function plainData(value) {
    if (!value || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value)) || Object.values(Object.getOwnPropertyDescriptors(value)).some(d => !('value' in d)))
        throw Error('Expected plain data without accessors');
}
function captureTask(input) {
    plainData(input);
    const { cancel, ...data } = input;
    return Object.freeze({ ...freeze(clone(data)), ...(cancel ? { cancel } : {}) });
}
function captureSources(input) {
    plainData(input);
    if (!Array.isArray(input.files) || Object.values(Object.getOwnPropertyDescriptors(input.files)).some(d => !('value' in d)))
        throw Error('Expected source files');
    const files = Array.prototype.map.call(input.files, (file) => {
        plainData(file);
        if (typeof file.text !== 'string' || typeof file.revision !== 'string' || !file.revision || file.encoding !== 'utf-8' || typeof file.writable !== 'boolean')
            throw Error('Malformed source file');
        // Bytes remain with the host; worker verification consumes decoded text.
        const { originalBytes, ...data } = file;
        if (originalBytes !== undefined) {
            if (!(originalBytes instanceof Uint8Array))
                throw Error('Source bytes must be Uint8Array');
            const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(originalBytes);
            if (decoded !== file.text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === file.text))
                throw Error('Source bytes do not match decoded text');
        }
        return { ...clone(data), id: normalizeLocation(file.id) };
    });
    return freeze(clone({ entry: normalizeLocation(input.entry), files }));
}
let sessions = 0;
/** Optional worker-backed facade. Worker construction and CSP fallback remain host responsibilities. */
export function createBrowserVerifier(inputOptions) {
    const options = { ...inputOptions, versions: freeze(clone(inputOptions.versions)), ...(inputOptions.limits ? { limits: freeze(clone(inputOptions.limits)) } : {}) };
    const { executor: provided, ...localOptions } = options;
    const executor = provided ?? createComputeExecutor(localOptions), local = createVerifier(localOptions);
    const sessionId = 'ddn-verifier-' + (++sessions);
    let serial = 0, destroyed = false;
    const task = (value) => ({ ...(options.limits ? { budget: options.limits } : {}), ...value });
    const request = (kind, payload, revision, dependencyFingerprint) => ({ protocol: 1, sessionId, jobId: String(++serial), kind, payload, revision, versions: options.versions, dependencyFingerprint, fontGeneration: '0', styleGeneration: '0' });
    const interrupted = (result, verifyOptions, revision, digest) => freeze({ requestId: result.request.jobId, outcome: result.outcome, revision, versions: options.versions, dependencyFingerprint: digest, scope: verifyOptions.scope, purpose: verifyOptions.purpose, level: verifyOptions.level, coverage: { ...result.coverage, scope: verifyOptions.scope, complete: false }, diagnostics: result.diagnostics, missing: result.coverage.unavailable, ruleVersions: {}, reviewEligible: false, stats: { elapsedMs: 0, workUnits: 0, cacheHits: 0 } });
    async function verifyModel(snapshotInput, optionsInput, diagnostics = []) {
        let snapshot, verifyOptions;
        try {
            snapshot = freeze(clone(snapshotInput));
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
            return freeze(clone(result.payload));
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
            const result = await executor.run(request('decode', decodePayload(input), revision, fingerprint(input.files.map(f => [f.id, f.revision, f.text]))), sourceTask);
            const payload = result.payload;
            if (!payload?.decoded)
                return interrupted(result, verifyOptions, revision, result.request.dependencyFingerprint);
            const snapshot = { contract: 'ddn-next-1', rootFile: input.entry, revision: { ...revision, model: payload.fingerprint }, versions: options.versions, semanticFingerprint: payload.fingerprint, normalized: payload.decoded.normalized, coverage: payload.decoded.coverage };
            const remaining = sourceTask.budget ? { ...sourceTask.budget, elapsedMs: Math.max(0, sourceTask.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, sourceTask.budget.workUnits - sourceUnits) } : undefined;
            const report = await verifyModel(snapshot, { ...verifyOptions, ...(remaining ? { budget: remaining } : {}) }, payload.decoded.diagnostics);
            const spans = new Map();
            const refKey = (ref) => JSON.stringify([ref.file, ref.id]);
            for (const node of allNodes(payload.decoded))
                if (node.ref && !spans.has(refKey(node.ref)))
                    spans.set(refKey(node.ref), { file: node.file, revision: input.files.find(file => file.id === node.file).revision, start: node.start, end: node.end });
            const root = input.files.find(file => file.id === input.entry);
            const diagnostics = report.diagnostics.map(diagnostic => {
                if (diagnostic.source)
                    return diagnostic;
                const span = diagnostic.target ? spans.get(refKey(diagnostic.target)) : undefined;
                return span ? { ...diagnostic, source: span } : root ? { ...diagnostic, source: { file: root.id, revision: root.revision, start: 0, end: root.text.length } } : diagnostic;
            });
            return freeze({ ...report, diagnostics, stats: { ...report.stats, elapsedMs: Date.now() - started, workUnits: sourceUnits + report.stats.workUnits } });
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
//# sourceMappingURL=browser-verifier.js.map