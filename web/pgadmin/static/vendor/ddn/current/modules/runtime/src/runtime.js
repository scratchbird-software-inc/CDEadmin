import { decodeSources } from '../../language/src/index.js';
import { asArray, asRecord, asString, findRecord, isRecord, listRecords, normalizeLocation, normalizedFiles } from '../../model/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
import { clone, createContext, fingerprint, freeze, ComputationStopped, canonical } from '../../execution/src/index.js';
import { createRegistry, registryPacks } from './registry.js';
import { affectedProtected, checkLifecycleMutation } from './guards.js';
import { applyProviderOverlays, stageProviderChanges } from './providers.js';
import { decodePayload } from '../../execution/src/compute.js';
import { STANDARD_VERSIONS } from './versions.js';
export { STANDARD_VERSIONS } from './versions.js';
const states = new WeakMap();
export function runtimeState(runtime) {
    const state = states.get(runtime);
    if (!state || state.disposed)
        throw new Error('Runtime is disposed or belongs to another implementation');
    return state;
}
export function copySources(input) {
    return { entry: normalizeLocation(input.entry), files: input.files.map(file => {
            if (typeof file.text !== 'string' || typeof file.revision !== 'string' || !file.revision || file.encoding !== 'utf-8' || typeof file.writable !== 'boolean')
                throw Error('Malformed source file');
            const bytes = file.originalBytes === undefined ? undefined : new Uint8Array(file.originalBytes);
            if (bytes) {
                const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
                if (decoded !== file.text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === file.text))
                    throw Error('Source bytes do not match the decoded text');
            }
            return { ...file, id: normalizeLocation(file.id), ...(bytes ? { originalBytes: bytes } : {}) };
        }) };
}
const emptyCoverage = () => ({ scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: [] });
const diagnostic = (code, message) => ({ code, severity: 'error', message });
let sessionSequence = 0;
export function createRuntime(inputOptions) {
    const options = { ...inputOptions, versions: freeze(clone(inputOptions.versions)), packs: [...inputOptions.packs], ...(inputOptions.limits ? { limits: freeze(clone(inputOptions.limits)) } : {}) };
    const listeners = new Set();
    let verifier;
    let overlays = new Map();
    let pendingSourceDiagnostics = [];
    const sessionId = 'ddn-runtime-' + (++sessionSequence);
    let jobSequence = 0;
    const state = { options, diagnostics: [], disposed: false, generation: 0, counter: 0, emit, materialize, async commitSources(source, task, expected, boundary) {
            let committed = false;
            const result = await openSources(source, task, false, true, expected, { check: () => boundary.check(), published(result) { committed = true; boundary.published(result); } });
            return { ...result, committed };
        } };
    function emit(event) {
        for (const listener of [...listeners]) {
            try {
                listener(freeze(event));
            }
            catch { /* A host listener cannot roll back an already committed revision. */ }
        }
    }
    const registry = createRegistry(options.versions, () => {
        state.generation++;
        verifier?.destroy();
        verifier = undefined;
        if (!state.disposed)
            emit({ kind: 'capabilities' });
    });
    for (const pack of options.packs)
        registry.install(pack);
    const getVerifier = () => {
        if (state.disposed)
            throw new Error('Runtime is disposed');
        verifier ??= createVerifier({ ...options, packs: registryPacks(registry) });
        return verifier;
    };
    const facade = { verifySources: (...args) => getVerifier().verifySources(...args), verifyModel: (snapshot, settings) => verify(snapshot, settings), checkTransition: (...args) => getVerifier().checkTransition(...args), destroy() { verifier?.destroy(); verifier = undefined; } };
    function failure(diagnostics, unavailable = [], publish = true) {
        const values = freeze([...diagnostics]);
        if (publish && !state.disposed) {
            state.diagnostics = values;
            emit({ kind: 'diagnostics', diagnostics: values });
        }
        return { revision: state.current?.revision ?? { model: '0', sources: {}, data: {} }, ...(state.current ? { snapshot: state.current } : {}), diagnostics: values, coverage: { ...emptyCoverage(), unavailable } };
    }
    function materialize(decoded) {
        if (!overlays.size)
            return decoded;
        const normalized = clone(decoded.normalized);
        applyProviderOverlays(normalized, overlays);
        return { ...decoded, normalized };
    }
    function retainedEvidence(normalized) {
        return state.diagnostics.filter(item => {
            if (item.code !== 'runtime.acceptance-stale' || !item.target)
                return false;
            const record = findRecord(normalized, item.target), previous = state.current ? findRecord(state.current.normalized, item.target) : undefined;
            return !!record && ['accepted', 'in-review'].includes(asString(asRecord(record.design).state)) && canonical(record.acceptance) === canonical(previous?.acceptance);
        });
    }
    function effectiveTask(task) { return { ...(options.limits ? { budget: options.limits } : {}), ...task }; }
    async function decode(source, task) {
        if (!options.executor)
            return decodeSources(source, { ...task, ...(state.decoded ? { previous: state.decoded } : {}) });
        const request = { protocol: 1, sessionId, jobId: String(++jobSequence), kind: 'decode', revision: state.current?.revision ?? { model: '0', sources: {}, data: {} }, versions: options.versions, dependencyFingerprint: fingerprint(source.files.map(({ originalBytes: _, ...file }) => file)), fontGeneration: '0', styleGeneration: '0', payload: decodePayload(source, state.decoded) };
        const result = await options.executor.run(request, task), { payload: _, ...echo } = request;
        if (canonical(result.request) !== canonical(echo))
            throw Error('Executor returned a mismatched request envelope.');
        if (result.outcome === 'cancelled' || result.outcome === 'budget-exceeded')
            throw new ComputationStopped(result.outcome, result.diagnostics.map(d => d.message).join('; '));
        const value = asRecord(result.payload);
        if (!isRecord(value.decoded))
            throw Error(result.diagnostics.map(d => d.message).join('; ') || 'Executor returned no decoded source.');
        const decoded = value.decoded;
        if (value.fingerprint !== fingerprint(decoded.normalized))
            throw Error('Executor returned an inconsistent decoded fingerprint.');
        return decoded;
    }
    async function verify(snapshot, settings) {
        const currentPacks = registryPacks(registry);
        if (!options.executor || canonical(currentPacks.map(pack => pack.manifest)) !== canonical(options.packs.map(pack => pack.manifest)))
            return getVerifier().verifyModel(snapshot, settings);
        const { cancel, budget, ...plain } = settings;
        const request = { protocol: 1, sessionId, jobId: String(++jobSequence), kind: 'verify', revision: snapshot.revision, versions: snapshot.versions, dependencyFingerprint: snapshot.semanticFingerprint, fontGeneration: settings.measurement?.fontGeneration ?? '0', styleGeneration: '0', payload: { snapshot: snapshot, options: plain } };
        const result = await options.executor.run(request, { ...(cancel ? { cancel } : {}), ...(budget ? { budget } : {}) }), { payload: _, ...echo } = request;
        if (canonical(result.request) !== canonical(echo))
            throw Error('Executor returned a mismatched verification envelope.');
        const payload = asRecord(result.payload);
        if (!payload.requestId)
            return freeze({ requestId: 'execution-' + request.jobId, outcome: result.outcome, revision: snapshot.revision, versions: snapshot.versions, dependencyFingerprint: snapshot.semanticFingerprint, scope: settings.scope, purpose: settings.purpose, level: settings.level, coverage: result.coverage, diagnostics: result.diagnostics, missing: result.coverage.unavailable, ruleVersions: {}, reviewEligible: false, stats: { elapsedMs: 0, workUnits: 0, cacheHits: 0 } });
        const report = payload;
        if (canonical(report.revision) !== canonical(snapshot.revision) || report.dependencyFingerprint !== snapshot.semanticFingerprint || canonical(report.versions) !== canonical(snapshot.versions) || canonical(report.scope) !== canonical(settings.scope) || report.purpose !== settings.purpose || report.level !== settings.level || report.outcome !== result.outcome)
            throw Error('Executor verification evidence does not match the requested snapshot.');
        return freeze(report);
    }
    function supported() { return options.versions.api === '1.0' && options.versions.language === 'ddn-next-1' && options.versions.defaults === 'ddn-next-1'; }
    async function openSources(input, task = {}, retainBrokenBuffer = true, preserveData = false, expectedFingerprint, boundary) {
        if (state.disposed)
            return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
        if (!supported())
            return failure([diagnostic('runtime.contract', 'Unsupported language/default contract')]);
        const generation = ++state.generation;
        try {
            const context = createContext(options.versions, effectiveTask(task));
            context.check();
            context.accountMemory(input.files.reduce((n, f) => n + f.text.length * 2, 0));
            const source = copySources(input);
            if (new Set(source.files.map(f => f.id)).size !== source.files.length)
                return failure([diagnostic('runtime.files', 'Ambiguous duplicate logical file identities')]);
            const raw = await decode(source, effectiveTask(task));
            const parsed = preserveData ? materialize(raw) : raw;
            await context.checkpoint(source.files.length);
            if (generation !== state.generation)
                return failure([diagnostic('runtime.stale', 'A newer source operation superseded this request')], [], false);
            // Broken editing buffers stay available; they never replace the last valid model.
            if (!parsed.syntaxValid) {
                if (retainBrokenBuffer) {
                    state.source = source;
                    pendingSourceDiagnostics = freeze([...parsed.diagnostics]);
                }
                return failure(parsed.diagnostics, parsed.coverage.unavailable);
            }
            const digest = fingerprint(parsed.normalized);
            const modelRevision = state.current?.semanticFingerprint === digest ? state.current.revision.model : String(state.counter + 1);
            const candidate = freeze({ contract: 'ddn-next-1', rootFile: parsed.normalized.entry, normalized: parsed.normalized, versions: options.versions, semanticFingerprint: digest, revision: { model: modelRevision, sources: Object.fromEntries(source.files.map(f => [f.id, f.revision])), data: preserveData ? state.current?.revision.data ?? {} : {} }, coverage: parsed.coverage });
            if (expectedFingerprint && candidate.semanticFingerprint !== expectedFingerprint)
                return failure([diagnostic('runtime.prepared-mismatch', 'Prepared model differs from the candidate; no edit was committed.')]);
            const report = await verify(candidate, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...effectiveTask(task) });
            context.check();
            if (generation !== state.generation)
                return failure([diagnostic('runtime.stale', 'A newer source operation superseded this request')], [], false);
            const diagnostics = [...parsed.diagnostics, ...report.diagnostics, ...(preserveData ? retainedEvidence(candidate.normalized) : [])];
            if (report.outcome === 'cancelled' || report.outcome === 'budget-exceeded' || report.outcome === 'invalid' || report.outcome === 'stale') {
                if (retainBrokenBuffer && report.outcome === 'invalid') {
                    state.source = source;
                    pendingSourceDiagnostics = freeze(diagnostics);
                }
                return failure(diagnostics, report.missing);
            }
            if (boundary) {
                const rejected = await boundary.check();
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'A newer operation superseded command publication')], [], false);
                if (rejected.length)
                    return failure(rejected);
            }
            if (!preserveData)
                overlays.clear();
            pendingSourceDiagnostics = [];
            state.source = source;
            state.counter = Math.max(state.counter, Number(modelRevision) || 0);
            state.decoded = parsed;
            state.current = candidate;
            state.diagnostics = freeze(diagnostics);
            const result = { snapshot: candidate, revision: candidate.revision, diagnostics: state.diagnostics, coverage: candidate.coverage };
            boundary?.published(result);
            emit({ kind: 'revision', revision: candidate.revision });
            emit({ kind: 'diagnostics', diagnostics: state.diagnostics, revision: candidate.revision });
            return result;
        }
        catch (error) {
            return failure([diagnostic(error instanceof ComputationStopped ? 'runtime.' + error.outcome : 'runtime.open', error instanceof Error ? error.message : 'Unable to open source')], [], generation === state.generation && !state.disposed);
        }
    }
    const runtime = {
        registry, verifier: facade,
        async open(input, task = {}) {
            if ('entry' in input)
                return openSources(input, task);
            if (state.disposed)
                return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
            const generation = ++state.generation;
            try {
                if (!supported() || input.contract !== 'ddn-next-1' || input.versions.language !== options.versions.language || input.versions.defaults !== options.versions.defaults)
                    return failure([diagnostic('runtime.contract', 'Snapshot version is unsupported')]);
                const context = createContext(options.versions, effectiveTask(task));
                context.check();
                context.accountMemory(canonical(input.normalized).length * 2);
                const snapshot = freeze({ ...clone(input), semanticFingerprint: fingerprint(input.normalized) });
                const report = await verify(snapshot, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...effectiveTask(task) });
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'A newer operation superseded this snapshot')], [], false);
                if (['invalid', 'cancelled', 'budget-exceeded', 'stale'].includes(report.outcome))
                    return failure(report.diagnostics, report.missing);
                overlays.clear();
                pendingSourceDiagnostics = [];
                state.counter = Math.max(state.counter, Number(snapshot.revision.model) || 0);
                state.current = snapshot;
                delete state.source;
                delete state.decoded;
                state.diagnostics = report.diagnostics;
                emit({ kind: 'revision', revision: snapshot.revision });
                emit({ kind: 'diagnostics', diagnostics: report.diagnostics });
                return { snapshot, revision: snapshot.revision, diagnostics: report.diagnostics, coverage: snapshot.coverage };
            }
            catch (error) {
                return failure([diagnostic(error instanceof ComputationStopped ? 'runtime.' + error.outcome : 'runtime.snapshot', error instanceof Error ? error.message : 'Invalid snapshot')], [], generation === state.generation && !state.disposed);
            }
        },
        snapshot() { return state.current; },
        sources() { return state.source ? freeze(copySources(state.source)) : undefined; },
        async ingest(input, task = {}) {
            if (state.disposed)
                return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
            let update;
            try {
                const { sources, ...data } = input;
                canonical(data);
                update = { ...clone(data), ...(sources ? { sources: copySources({ entry: state.source?.entry ?? '', files: sources }).files } : {}) };
            }
            catch (error) {
                return failure([diagnostic('data.update', error instanceof Error ? error.message : 'Invalid provider update')]);
            }
            const previous = state.current;
            if (!previous || canonical(update.base) !== canonical(previous.revision))
                return failure([diagnostic('runtime.conflict', 'External update does not match the current revision vector')]);
            if (!update.origin)
                return failure([diagnostic('runtime.origin', 'External update must identify its provider')]);
            const generation = ++state.generation;
            task = effectiveTask(task);
            try {
                const context = createContext(options.versions, task);
                context.check();
                let source = state.source ? copySources(state.source) : undefined, decoded = state.decoded;
                const pendingBuffer = !update.sources?.length && !!source && !!decoded && decoded.documents.some(document => source.files.find(file => file.id === document.file.id)?.text !== document.file.text);
                if (update.sources?.length) {
                    if (!source)
                        throw Error('No editable source set is loaded.');
                    const replacements = new Map();
                    for (const file of update.sources) {
                        const id = normalizeLocation(file.id);
                        if (replacements.has(id))
                            throw Error('External update repeats a source file.');
                        const old = source.files.find(value => value.id === id);
                        if (!old)
                            throw Error('External update targets an unavailable file: ' + id);
                        if (!file.revision || file.text !== old.text && file.revision === old.revision)
                            throw Error('Changed source text requires a new revision.');
                        replacements.set(id, { ...file, id });
                    }
                    source = copySources({ entry: source.entry, files: source.files.map(file => replacements.get(file.id) ?? file) });
                    context.accountMemory(source.files.reduce((size, file) => size + file.text.length * 2, 0));
                    decoded = await decode(source, task);
                    if (generation !== state.generation || state.disposed)
                        return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                    if (!decoded.syntaxValid)
                        return failure(decoded.diagnostics, decoded.coverage.unavailable);
                }
                const normalized = clone(decoded ? decoded.normalized : previous.normalized);
                context.accountMemory(canonical(normalized).length * 2 + canonical(update.data ?? []).length * 2);
                // Authored edits require reopening protected scopes. Supplied live data instead
                // invalidates prior evidence while preserving the user's stored lifecycle state.
                applyProviderOverlays(normalized, overlays);
                const lifecycle = checkLifecycleMutation(previous.normalized, normalized);
                if (lifecycle.length)
                    return failure(lifecycle);
                const protectedScopes = affectedProtected(previous, normalized);
                if (protectedScopes.length)
                    return failure(protectedScopes.map(target => ({ ...diagnostic('runtime.protected', 'Reopen this protected scope before changing its authored dependencies.'), target })));
                const staged = await stageProviderChanges(normalized, overlays, previous.revision.data, update.data ?? [], context);
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                const staleEvidence = affectedProtected(previous, normalized).map(target => ({ code: 'runtime.acceptance-stale', severity: 'warning', message: 'Live data changed. Stored design status is retained; review or acceptance evidence requires fresh verification.', target }));
                const digest = fingerprint(normalized), model = previous.semanticFingerprint === digest ? previous.revision.model : String(state.counter + 1);
                const next = freeze({ ...previous, normalized, semanticFingerprint: digest, coverage: decoded?.coverage ?? previous.coverage, revision: { model, sources: source && !pendingBuffer ? Object.fromEntries(source.files.map(file => [file.id, file.revision])) : previous.revision.sources, data: staged.revisions } });
                const report = await verify(next, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...task });
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                if (['invalid', 'cancelled', 'budget-exceeded', 'stale'].includes(report.outcome))
                    return failure(report.diagnostics, report.missing);
                const retained = retainedEvidence(normalized);
                overlays = staged.overlays;
                state.counter = Math.max(state.counter, Number(model) || 0);
                state.current = next;
                if (!pendingBuffer)
                    pendingSourceDiagnostics = [];
                if (source)
                    state.source = source;
                if (decoded)
                    state.decoded = { ...decoded, normalized: normalized };
                state.diagnostics = freeze([...(decoded?.diagnostics ?? []), ...pendingSourceDiagnostics, ...report.diagnostics, ...retained.filter(old => !staleEvidence.some(current => canonical(current.target) === canonical(old.target))), ...staleEvidence]);
                emit({ kind: 'revision', revision: next.revision });
                emit({ kind: 'diagnostics', ...(!pendingBuffer ? { revision: next.revision } : {}), diagnostics: state.diagnostics });
                return { snapshot: next, revision: next.revision, coverage: next.coverage, diagnostics: state.diagnostics };
            }
            catch (error) {
                return failure([diagnostic(error instanceof ComputationStopped ? 'runtime.' + error.outcome : 'data.update', error instanceof Error ? error.message : 'Provider update failed')], [], generation === state.generation && !state.disposed);
            }
        },
        subscribe(listener) {
            if (state.disposed)
                return () => { };
            listeners.add(listener);
            return () => { listeners.delete(listener); };
        },
        destroy() {
            if (state.disposed)
                return;
            state.disposed = true;
            state.generation++;
            verifier?.destroy();
            options.executor?.destroy();
            emit({ kind: 'disposed' });
            listeners.clear();
            overlays.clear();
            delete state.source;
            delete state.decoded;
            delete state.current;
        },
    };
    states.set(runtime, state);
    return runtime;
}
//# sourceMappingURL=runtime.js.map