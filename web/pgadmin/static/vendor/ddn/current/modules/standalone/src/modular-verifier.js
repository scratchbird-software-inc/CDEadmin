import { loadedProfilePacks } from '../../profiles/src/family-packs.js';
import { createBrowserVerifier } from '../../execution/src/browser-verifier.js';
import { canonical } from '../../execution/src/index.js';
import { withBrowserExecutor } from './browser-options.js';
import { createModularRuntimeOptions, ensureProfileInput, HostStopped, loadingDiagnostic, remainingTask, scanUnits, verificationFailure } from './modular-loading.js';
function mergePacks(options) {
    const result = [...options.packs], ids = new Set(result.map(pack => pack.manifest.id));
    const profiles = new Set(result.flatMap(pack => pack.registrations.profiles?.map(profile => profile.id) ?? []));
    for (const pack of loadedProfilePacks()) {
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
export function createModularVerifier(options = createModularRuntimeOptions()) {
    const verifiers = new Map();
    let destroyed = false, providedUsed = false;
    const initial = canonical(options.packs.map(pack => pack.manifest));
    const effective = (task = {}) => ({ ...(options.limits ? { budget: options.limits } : {}), ...task });
    const current = () => {
        if (destroyed)
            throw new HostStopped('disposed', 'Verifier is disposed.');
        const packs = mergePacks(options), signature = canonical(packs.map(pack => pack.manifest));
        let verifier = verifiers.get(signature);
        if (!verifier) {
            const { executor, ...base } = options;
            // Keep outstanding jobs alive. An opaque supplied executor is used
            // for its original packs; later packs use cooperative local handlers.
            const next = executor ? { ...base, packs, ...(signature === initial ? { executor } : {}) } : withBrowserExecutor({ ...base, packs });
            if (executor && signature === initial)
                providedUsed = true;
            verifier = createBrowserVerifier(next);
            verifiers.set(signature, verifier);
        }
        return verifier;
    };
    return {
        async verifySources(input, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new HostStopped('disposed', 'Verifier is disposed.');
                await ensureProfileInput(input, false, budget);
                return current().verifySources(input, { ...task, ...remainingTask(budget, started, scanUnits(input)) });
            }
            catch (error) {
                return verificationFailure(input, task, options.versions, error, started);
            }
        },
        async verifyModel(input, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new HostStopped('disposed', 'Verifier is disposed.');
                await ensureProfileInput(input, false, budget);
                return current().verifyModel(input, { ...task, ...remainingTask(budget, started, scanUnits(input)) });
            }
            catch (error) {
                return verificationFailure(input, task, options.versions, error, started);
            }
        },
        async checkTransition(input, transition, task) {
            const started = Date.now(), budget = effective(task);
            try {
                if (destroyed)
                    throw new HostStopped('disposed', 'Verifier is disposed.');
                await ensureProfileInput(input, false, budget);
                return current().checkTransition(input, transition, remainingTask(budget, started, scanUnits(input)));
            }
            catch (error) {
                return { allowed: false, diagnostics: [loadingDiagnostic(error, 'DDN-PROFILE-LOAD')] };
            }
        },
        destroy() { if (destroyed)
            return; destroyed = true; for (const verifier of verifiers.values())
            verifier.destroy(); verifiers.clear(); if (!providedUsed)
            options.executor?.destroy(); },
    };
}
//# sourceMappingURL=modular-verifier.js.map