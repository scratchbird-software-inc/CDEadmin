import { decodeSources } from '../../language/src/index.js';
import { indexRecords } from '../../profiles/src/core.js';
import { profileCatalogueShard } from '../../profiles/src/generated-shards.js';
import { catalogueShards } from '../../profiles/src/generated-shards.js';
import { loadedProfilePacks } from '../../profiles/src/family-packs.js';
import { STANDARD_VERSIONS } from '../../runtime/src/versions.js';
import { withBrowserExecutor } from './browser-options.js';
import { ComputationStopped, createContext, fingerprint } from '../../execution/src/index.js';
const loader = () => {
    const value = globalThis.DDN_LOADER;
    if (!value)
        throw new Error('The local DDN pack loader is unavailable.');
    return value;
};
export function requiredProfiles(input, task = {}) {
    if (Array.isArray(input))
        return [...new Set(input)];
    const value = input;
    const normalized = 'normalized' in value ? value.normalized : decodeSources(value, task).normalized;
    return [...new Set(indexRecords(normalized).filter(record => record.owner === 'view_definition' || record.owner === 'document').map(record => typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1'))];
}
export const scanUnits = (input) => Array.isArray(input) ? input.length : 'files' in input ? input.files.reduce((total, file) => total + file.text.length, 0) : indexRecords(input.normalized).length;
export function remainingTask(task, started, units) {
    return task.budget ? { ...task, budget: { ...task.budget, elapsedMs: Math.max(0, task.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, task.budget.workUnits - units) } } : task;
}
/** Cancelling one caller leaves the shared module request usable by other hosts. */
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
        unsubscribe = task.cancel?.onAbort(() => finish(new ComputationStopped('cancelled', 'Profile loading was cancelled.')));
        if (settled)
            unsubscribe?.();
        if (task.cancel?.aborted)
            finish(new ComputationStopped('cancelled', 'Profile loading was cancelled.'));
        if (!settled && task.budget) {
            const remaining = task.budget.elapsedMs - (Date.now() - started);
            if (remaining <= 0)
                finish(new ComputationStopped('budget-exceeded', 'Profile loading exhausted the operation budget.'));
            else
                timer = setTimeout(() => finish(new ComputationStopped('budget-exceeded', 'Profile loading exhausted the operation budget.')), remaining);
        }
        pending.then(value => finish(undefined, value), error => finish(error));
    });
}
/** Profile IDs are mapped through the installed distribution's trusted manifest. */
export async function ensureProfileInput(input, drawing, task = {}) {
    const started = Date.now(), context = createContext(STANDARD_VERSIONS, task);
    context.check();
    const units = scanUnits(input);
    if (!Array.isArray(input) && 'files' in input)
        context.accountMemory(units * 2);
    await context.checkpoint(units);
    await waitForPack(loader().loadEntry('schema:native'), task, started);
    await waitForPack(loader().prepareEntry('worker'), task, started);
    const families = [...new Set(requiredProfiles(input, task).map(profileCatalogueShard).filter((family) => !!family && family !== 'native'))];
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
            if (error instanceof ComputationStopped)
                throw error;
            throw new Error('Unable to load the local DDN ' + family + ' pack: ' + (error instanceof Error ? error.message : String(error)));
        }
    }));
    context.check();
}
export function createModularRuntimeOptions() { return { versions: STANDARD_VERSIONS, packs: loadedProfilePacks() }; }
export function createModularBrowserOptions() { return withBrowserExecutor(createModularRuntimeOptions()); }
export function installModularWorkerFactory() {
    Object.defineProperty(globalThis, '__ddnCreateWorker', { configurable: true, value: (options) => {
            const packs = options?.packs ?? loadedProfilePacks();
            const initializers = packs.filter(pack => pack.manifest.id !== 'ddn-native' && !pack.manifest.id.endsWith('-commands')).map(pack => {
                const family = pack.manifest.id.slice(4);
                if (!Object.hasOwn(catalogueShards, family))
                    throw new Error('No local compute initializer for pack ' + pack.manifest.id);
                return 'verify:' + family;
            });
            return loader().worker('worker', initializers);
        } });
}
export class HostStopped extends Error {
    reason;
    constructor(reason, message) {
        super(message);
        this.reason = reason;
    }
}
export function loadingDiagnostic(error, prefix = 'runtime') {
    const reason = error instanceof ComputationStopped ? error.outcome : error instanceof HostStopped ? error.reason : 'pack';
    return { code: prefix + '.' + reason, severity: reason === 'cancelled' || reason === 'stale' ? 'info' : 'error', message: error instanceof Error ? error.message : 'Unable to load required profile packs.' };
}
let verificationSequence = 0;
export function verificationFailure(input, task, versions, error, started) {
    const model = 'normalized' in input;
    const outcome = error instanceof ComputationStopped ? error.outcome : error instanceof HostStopped ? 'cancelled' : 'unsupported';
    return { requestId: 'profile-loading-' + (++verificationSequence), outcome,
        revision: model ? input.revision : { model: '0', sources: Object.fromEntries(input.files.map(file => [file.id, file.revision])), data: {} }, versions,
        dependencyFingerprint: model ? input.semanticFingerprint : fingerprint(input.files.map(file => [file.id, file.revision, file.text])),
        scope: task.scope, purpose: task.purpose, level: task.level, coverage: { scope: task.scope, complete: false, checked: [], unavailable: ['profile-loading'] },
        diagnostics: [loadingDiagnostic(error, 'DDN-PROFILE-LOAD')], missing: ['profile-loading'], ruleVersions: {}, reviewEligible: false,
        stats: { elapsedMs: Date.now() - started, workUnits: 0, cacheHits: 0 },
    };
}
//# sourceMappingURL=modular-loading.js.map