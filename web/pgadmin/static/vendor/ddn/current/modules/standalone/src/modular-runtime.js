import { completeProfileIds, knownProfile } from '../../profiles/src/core.js';
import { loadedProfilePacks } from '../../profiles/src/family-packs.js';
import { createRuntime as createCoreRuntime, runtimeState } from '../../runtime/src/runtime.js';
import { registrations } from '../../runtime/src/registry.js';
import { attachProfileLoadingHost } from '../../runtime/src/profile-loading.js';
import { normalizeLocation } from '../../model/src/index.js';
import { createModularBrowserOptions, ensureProfileInput, HostStopped, loadingDiagnostic, remainingTask, scanUnits, verificationFailure } from './modular-loading.js';
/** Decorate only the host facade; the model, parser and language remain unchanged. */
export function createModularRuntime(options = createModularBrowserOptions(), drawing = true) {
    return attachModularRuntime(createCoreRuntime(options), drawing);
}
function openFailure(runtime, error) {
    const snapshot = runtime.snapshot();
    return { ...(snapshot ? { snapshot } : {}), revision: snapshot?.revision ?? { model: '0', sources: {}, data: {} }, diagnostics: [loadingDiagnostic(error)], coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: ['profile-loading'] } };
}
const managed = new WeakMap();
export function attachModularRuntime(runtime, drawing = true) {
    const previous = managed.get(runtime);
    if (previous) {
        previous.drawing ||= drawing;
        return runtime;
    }
    const state = { drawing, disposed: false, sequence: 0 }, modelState = runtimeState(runtime), options = modelState.options;
    managed.set(runtime, state);
    const effective = (task = {}) => ({ ...(options.limits ? { budget: options.limits } : {}), ...task });
    const live = () => { if (state.disposed)
        throw new HostStopped('disposed', 'Runtime is disposed.'); };
    const ensure = async (input, task = {}, guard = live) => {
        live();
        guard();
        const drawingBefore = state.drawing;
        await ensureProfileInput(input, drawingBefore, task);
        live();
        guard();
        if (state.drawing && !drawingBefore)
            await ensureProfileInput(input, true, task);
        live();
        guard();
        const installed = runtime.registry.describe(), ids = new Set(installed.map(pack => pack.id));
        const profiles = new Set((registrations(runtime.registry).profiles ?? []).map(profile => profile.id));
        for (const pack of loadedProfilePacks()) {
            if (ids.has(pack.manifest.id) || pack.manifest.profiles.every(profile => profiles.has(profile)))
                continue;
            runtime.registry.install(pack);
        }
    };
    attachProfileLoadingHost(runtime, { profiles: completeProfileIds.map(id => ({ id, method: knownProfile(id).method })), ensure: (input, task) => ensure(input, effective(task)) });
    const open = runtime.open.bind(runtime), ingest = runtime.ingest.bind(runtime), destroy = runtime.destroy.bind(runtime);
    const operation = () => {
        const sequence = ++state.sequence;
        // Reserve invocation order before asynchronous pack discovery, including
        // an older operation already running inside the core runtime.
        if (!state.disposed)
            modelState.generation++;
        return () => { live(); if (sequence !== state.sequence)
            throw new HostStopped('stale', 'A newer operation superseded profile loading.'); };
    };
    runtime.open = async (input, task) => {
        const guard = operation(), started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget, guard);
            guard();
            return open(input, remainingTask(budget, started, scanUnits(input)));
        }
        catch (error) {
            return openFailure(runtime, error);
        }
    };
    runtime.ingest = async (update, task) => {
        const guard = operation(), started = Date.now(), budget = effective(task);
        try {
            guard();
            const source = runtime.sources();
            let units = 0;
            if (update.sources?.length && source) {
                const changes = new Map(update.sources.map(file => [normalizeLocation(file.id), { ...file, id: normalizeLocation(file.id) }]));
                const merged = { ...source, files: source.files.map(file => changes.get(file.id) ?? file) };
                units = scanUnits(merged);
                await ensure(merged, budget, guard);
            }
            guard();
            return ingest(update, remainingTask(budget, started, units));
        }
        catch (error) {
            return openFailure(runtime, error);
        }
    };
    const sourceVerify = runtime.verifier.verifySources.bind(runtime.verifier), modelVerify = runtime.verifier.verifyModel.bind(runtime.verifier), transition = runtime.verifier.checkTransition.bind(runtime.verifier);
    runtime.verifier.verifySources = async (input, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return sourceVerify(input, { ...task, ...remainingTask(budget, started, scanUnits(input)) });
        }
        catch (error) {
            return verificationFailure(input, task, options.versions, error, started);
        }
    };
    runtime.verifier.verifyModel = async (input, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return modelVerify(input, { ...task, ...remainingTask(budget, started, scanUnits(input)) });
        }
        catch (error) {
            return verificationFailure(input, task, options.versions, error, started);
        }
    };
    runtime.verifier.checkTransition = async (input, request, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return transition(input, request, remainingTask(budget, started, scanUnits(input)));
        }
        catch (error) {
            return { allowed: false, diagnostics: [loadingDiagnostic(error, 'DDN-PROFILE-LOAD')] };
        }
    };
    runtime.destroy = () => { if (state.disposed)
        return; state.disposed = true; state.sequence++; destroy(); };
    return runtime;
}
//# sourceMappingURL=modular-runtime.js.map