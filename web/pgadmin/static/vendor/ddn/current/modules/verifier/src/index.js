import { allNodes, decodeSources } from '../../language/src/index.js';
import { fingerprint, createContext, ComputationStopped, clone, freeze } from '../../execution/src/index.js';
import { normalizeLocation } from '../../model/src/index.js';
import { bundleFiles, getProfile, indexRecords, enclosingDefinitions, nativeProfileDiagnostics, normalizedReference, resolveRecord as resolveUnindexedRecord, roleDescriptor, coreTypeDescriptor, coreDescriptor, safeLocation } from '../../profiles/src/core.js';
import { codex, getPath, isRecord, stableStringify, validateSchema } from '../../profiles/src/schema-core.js';
import { resolveProperties } from '../../defaults/src/index.js';
const levelOrder = ['decode', 'structural', 'semantic', 'review', 'publication'];
const decodedVerifiers = new WeakMap();
/** Internal worker bridge: retain decoder diagnostics without decoding a second time. */
export function verifyDecoded(verifier, input, options, diagnostics) {
    const run = decodedVerifiers.get(verifier);
    if (!run)
        throw new TypeError('Expected an instance created by createVerifier');
    return run(input, options, diagnostics);
}
const refKey = (r) => r.file + '\0' + r.id;
const equal = (a, b) => stableStringify(a) === stableStringify(b);
const severity = (diagnostics) => diagnostics.some(d => d.severity === 'error');
function issue(code, message, target) { return { code, severity: 'error', message, ...(target ? { target } : {}) }; }
const recordIndexes = new WeakMap();
function indexCapturedRecords(records) {
    const result = { ids: new Map(), names: new Map(), paths: new Map(), collections: new Map() };
    const append = (map, key, record) => {
        const found = map.get(key);
        if (found)
            found.push(record);
        else
            map.set(key, [record]);
    };
    for (const record of records) {
        append(result.ids, refKey(record.ref), record);
        if (typeof record.record.name === 'string')
            append(result.names, record.file + '\0' + record.record.name, record);
        const path = record.file + '\0' + record.path;
        if (record.path && !result.paths.has(path))
            result.paths.set(path, record);
        const collection = record.file + '\0' + record.collection + '\0' + (record.collection === 'workarea' ? 0 : record.index);
        if (!result.collections.has(collection))
            result.collections.set(collection, record);
    }
    recordIndexes.set(records, result);
    return result;
}
function resolveRecord(records, file, reference) {
    const index = recordIndexes.get(records);
    if (!index)
        return resolveUnindexedRecord(records, file, reference);
    if (!isRecord(reference))
        return undefined;
    const targetFile = typeof reference.file === 'string' ? reference.file : file;
    const id = typeof reference.id === 'string', name = typeof reference.name === 'string';
    const candidates = id ? index.ids.get(targetFile + '\0' + reference.id) : name ? index.names.get(targetFile + '\0' + reference.name) : undefined;
    const matches = id && name ? candidates?.filter(record => record.record.name === reference.name) : candidates;
    return matches?.length === 1 ? matches[0] : undefined;
}
function containingRecord(records, file, path) {
    const lookup = recordIndexes.get(records);
    if (lookup) {
        let parent = path;
        while (parent) {
            const found = lookup.paths.get(file + '\0' + parent);
            if (found)
                return found;
            parent = parent.slice(0, parent.lastIndexOf('/'));
        }
        const parts = path.split('/'), collection = parts[1];
        return lookup.collections.get(file + '\0' + collection + '\0' + (collection === 'workarea' ? 0 : Number(parts[2])));
    }
    const nested = records.filter(r => r.file === file && r.path && (path === r.path || path.startsWith(r.path + '/'))).sort((a, b) => (b.path?.length ?? 0) - (a.path?.length ?? 0))[0];
    if (nested)
        return nested;
    const parts = path.split('/');
    const collection = parts[1], index = Number(parts[2]);
    if (collection === 'workarea')
        return records.find(x => x.file === file && x.collection === 'workarea');
    return records.find(x => x.file === file && x.collection === collection && x.index === index);
}
function status(record) { const value = getPath(record, 'design.state'); return typeof value === 'string' ? value : 'draft'; }
function captureOptions(input) {
    if (!input || typeof input !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(input)))
        throw Error('Expected plain verification options');
    const descriptors = Object.getOwnPropertyDescriptors(input);
    if (Object.values(descriptors).some(descriptor => !('value' in descriptor)))
        throw Error('Verification options cannot contain accessors');
    const { cancel, ...data } = input;
    return Object.freeze({ ...freeze(clone(data)), ...(cancel ? { cancel } : {}) });
}
function validRef(value) { return isRecord(value) && typeof value.file === 'string' && !!value.file && typeof value.id === 'string' && !!value.id; }
function validScope(value) { return isRecord(value) && (value.kind === 'workarea' || ['item', 'view', 'document'].includes(String(value.kind)) && validRef(value.target)); }
function boundedClone(value, context, account = () => { }) {
    const active = new Set(), stack = [{ value, depth: 0 }];
    let bytes = 0, units = 0;
    while (stack.length) {
        context.check();
        const item = stack.pop(), current = item.value;
        if (item.exit) {
            active.delete(current);
            continue;
        }
        units++;
        if (item.depth > 136 || context.task.budget && units + context.stats.workUnits > context.task.budget.workUnits)
            throw new ComputationStopped('budget-exceeded', 'Verification input exceeds the bounded capture budget');
        if (current && typeof current === 'object') {
            if (active.has(current))
                throw Error('Cyclic verification input');
            if (!Array.isArray(current) && ![Object.prototype, null].includes(Object.getPrototypeOf(current)))
                throw Error('Expected plain verification data');
            active.add(current);
            stack.push({ value: current, depth: item.depth, exit: true });
            for (const [key, descriptor] of Object.entries(Object.getOwnPropertyDescriptors(current))) {
                if (!descriptor.enumerable)
                    continue;
                if (!('value' in descriptor))
                    throw Error('Verification data cannot contain accessors');
                bytes += key.length * 2;
                stack.push({ value: descriptor.value, depth: item.depth + 1 });
            }
        }
        else
            bytes += typeof current === 'string' ? current.length * 2 : 8;
        context.accountMemory(bytes);
    }
    const copy = clone(value);
    account(units);
    return copy;
}
function captureSources(input, context) {
    const data = (value) => {
        if (!value || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
            throw Error('Expected plain source records');
        const fields = Object.getOwnPropertyDescriptors(value);
        if (Object.values(fields).some(field => !('value' in field)))
            throw Error('Source records cannot contain accessors');
        return fields;
    };
    const root = data(input), entry = normalizeLocation(root.entry?.value);
    const values = root.files?.value;
    if (!Array.isArray(values))
        throw Error('Source files must be an array');
    const fields = Object.getOwnPropertyDescriptors(values);
    const files = [];
    let bytes = 0;
    for (let i = 0; i < values.length; i++) {
        const item = fields[String(i)];
        if (!item || !('value' in item))
            throw Error('Source files must be dense data');
        const file = data(item.value), id = normalizeLocation(file.id?.value), text = file.text?.value, revision = file.revision?.value;
        if (typeof text !== 'string' || typeof revision !== 'string' || !revision || file.encoding?.value !== 'utf-8' || typeof file.writable?.value !== 'boolean')
            throw Error('Malformed source file');
        bytes += text.length * 2;
        context.accountMemory(bytes);
        context.check();
        const original = file.originalBytes?.value;
        if (original !== undefined) {
            if (!(original instanceof Uint8Array))
                throw Error('Source bytes must be Uint8Array');
            context.accountMemory(bytes + original.byteLength);
            const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(original);
            if (decoded !== text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === text))
                throw Error('Source bytes do not match decoded text');
        }
        files.push({ id, text, revision, encoding: 'utf-8', writable: file.writable.value });
    }
    return { entry, files };
}
function reachedFiles(input) {
    const files = new Map(bundleFiles(input.normalized).map(file => [file.location, file]));
    const reached = new Set(), pending = [input.rootFile];
    while (pending.length) {
        const next = pending.pop();
        if (reached.has(next) || !files.has(next))
            continue;
        reached.add(next);
        const includes = files.get(next).document.includes;
        for (const value of Array.isArray(includes) ? includes : [])
            if (typeof value === 'string') {
                const location = files.has(value) ? value : safeLocation(next, value);
                if (location)
                    pending.push(location);
            }
    }
    return reached;
}
function ruleResult(value, options, input, records, selected) {
    const result = freeze(clone(value));
    const reference = (ref) => validRef(ref) && selected.has(refKey(ref)) && !!resolveRecord(records, ref.file, ref);
    const span = (value) => isRecord(value) && typeof value.file === 'string' && typeof value.revision === 'string' && input.revision.sources[value.file] === value.revision && records.some(record => record.file === value.file && selected.has(refKey(record.ref))) && Number.isSafeInteger(value.start) && Number.isSafeInteger(value.end) && Number(value.start) >= 0 && Number(value.end) >= Number(value.start);
    if (!result || !['valid', 'invalid', 'incomplete', 'unsupported', 'budget-exceeded', 'cancelled', 'stale'].includes(result.outcome)
        || !Array.isArray(result.diagnostics) || !Array.isArray(result.dependencies) || !isRecord(result.coverage)
        || !equal(result.coverage.scope, options.scope) || typeof result.coverage.complete !== 'boolean'
        || !Array.isArray(result.coverage.checked) || !result.coverage.checked.every(reference)
        || !Array.isArray(result.coverage.unavailable) || result.coverage.unavailable.some(item => typeof item !== 'string' || !item)
        || result.coverage.complete && result.coverage.unavailable.length)
        throw Error('Rule returned malformed or inconsistent coverage/outcome');
    for (const diagnostic of result.diagnostics) {
        if (!isRecord(diagnostic) || typeof diagnostic.code !== 'string' || !diagnostic.code || typeof diagnostic.message !== 'string' || !['info', 'warning', 'error'].includes(String(diagnostic.severity))
            || diagnostic.target !== undefined && !reference(diagnostic.target) || diagnostic.source !== undefined && !span(diagnostic.source)
            || diagnostic.related !== undefined && (!Array.isArray(diagnostic.related) || !diagnostic.related.every(span)))
            throw Error('Rule returned an invalid diagnostic');
    }
    for (const dependency of result.dependencies)
        if (!isRecord(dependency) || !reference(dependency.target) || typeof dependency.path !== 'string' || typeof dependency.fingerprint !== 'string' || !dependency.fingerprint)
            throw Error('Rule returned an unavailable or malformed dependency');
    return result;
}
/** Staged verification is headless; source decoding and presentation remain separate. */
export function createVerifier(runtimeOptions) {
    let destroyed = false, serial = 0;
    const packs = runtimeOptions.packs.map(pack => ({ manifest: freeze(clone(pack.manifest)), registrations: {
            profiles: freeze(clone(pack.registrations.profiles ?? [])),
            rules: (pack.registrations.rules ?? []).map(rule => { const { evaluate, ...data } = rule; return freeze({ ...clone(data), evaluate }); }),
        } }));
    const profileDescriptors = new Map(packs.flatMap(p => p.registrations.profiles ?? []).map(p => [p.id, p]));
    const rules = packs.flatMap(p => p.registrations.rules ?? []);
    const versions = freeze(clone(runtimeOptions.versions));
    const limits = runtimeOptions.limits ? freeze(clone(runtimeOptions.limits)) : undefined;
    const destroyListeners = new Set();
    const liveTask = (options) => ({ ...options, cancel: {
            get aborted() { return destroyed || !!options.cancel?.aborted; },
            onAbort(handler) { destroyListeners.add(handler); const stop = options.cancel?.onAbort(handler); return () => { destroyListeners.delete(handler); stop?.(); }; },
        } });
    const capabilities = [];
    if (versions.api !== '1.0' || versions.language !== 'ddn-next-1' || versions.defaults !== 'ddn-next-1')
        capabilities.push(issue('DDN-VERSION', 'Unsupported utility API, language or defaults version'));
    const ids = new Set();
    for (const pack of packs) {
        if (ids.has(pack.manifest.id))
            capabilities.push(issue('DDN-PACK-DUPLICATE', 'Duplicate pack ' + pack.manifest.id));
        ids.add(pack.manifest.id);
        if (versions.packs[pack.manifest.id] !== undefined && versions.packs[pack.manifest.id] !== pack.manifest.version)
            capabilities.push(issue('DDN-PACK-VERSION', 'Installed pack differs from selected version: ' + pack.manifest.id));
        if (pack.manifest.api !== versions.api || !pack.manifest.languages.includes(versions.language) || !pack.manifest.defaults.includes(versions.defaults))
            capabilities.push(issue('DDN-PACK-VERSION', 'Incompatible pack ' + pack.manifest.id));
    }
    for (const id of Object.keys(versions.packs))
        if (!ids.has(id))
            capabilities.push(issue('DDN-PACK-MISSING', 'Selected pack is unavailable: ' + id));
    for (const pack of packs)
        for (const dependency of pack.manifest.dependencies)
            if (!ids.has(dependency))
                capabilities.push(issue('DDN-PACK-DEPENDENCY', 'Missing pack dependency ' + dependency));
    const graph = new Map(packs.map(p => [p.manifest.id, p.manifest.dependencies]));
    const walked = new Set(), active = new Set();
    function checkPack(id) {
        if (active.has(id)) {
            capabilities.push(issue('DDN-PACK-CYCLE', 'Pack dependency cycle at ' + id));
            return;
        }
        if (walked.has(id))
            return;
        active.add(id);
        for (const next of graph.get(id) ?? [])
            checkPack(next);
        active.delete(id);
        walked.add(id);
    }
    for (const id of graph.keys())
        checkPack(id);
    const seenRules = new Set(['ddn.structure', 'ddn.lifecycle']);
    for (const rule of rules) {
        if (seenRules.has(rule.id))
            capabilities.push(issue('DDN-RULE-DUPLICATE', 'Duplicate rule ' + rule.id));
        seenRules.add(rule.id);
        if (!rule.id || !rule.version || typeof rule.evaluate !== 'function' || !Array.isArray(rule.readPaths) || rule.readPaths.some(path => typeof path !== 'string') || !Array.isArray(rule.levels) || rule.levels.some(level => !levelOrder.includes(level)) || !Array.isArray(rule.purposes) || !Array.isArray(rule.profiles))
            capabilities.push(issue('DDN-RULE-REGISTRATION', 'Malformed rule registration: ' + rule.id));
    }
    const seenProfiles = new Set();
    for (const pack of packs)
        for (const profile of pack.registrations.profiles) {
            if (seenProfiles.has(profile.id))
                capabilities.push(issue('DDN-PROFILE-DUPLICATE', 'Duplicate profile ' + profile.id));
            seenProfiles.add(profile.id);
            if (!pack.manifest.profiles.includes(profile.id) || !Array.isArray(profile.ruleIds) || profile.ruleIds.some(id => typeof id !== 'string' || !id))
                capabilities.push(issue('DDN-PROFILE-REGISTRATION', 'Malformed or undeclared profile ' + profile.id));
        }
    const cache = new Map();
    const ruleCache = new Map();
    async function verify(inputArgument, optionsArgument, decodeDiagnostics = []) {
        const requestId = 'verify-' + (++serial);
        const started = Date.now();
        let input = { contract: 'ddn-next-1', rootFile: '', revision: { model: '', sources: {}, data: {} }, versions, semanticFingerprint: '', normalized: null, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: [] } };
        let options = { scope: { kind: 'workarea' }, purpose: '', level: 'decode' };
        const diagnostics = [];
        const missing = new Set();
        const checked = [];
        let task = {};
        let context = createContext(versions);
        let outcome = 'valid';
        let complete = true;
        let pendingWork = 0;
        const ruleVersions = { 'ddn.structure': '1.0.0', 'ddn.lifecycle': '1.0.0' };
        const schemaAccount = (units) => {
            pendingWork += units;
            context.check();
            if (task.budget && context.stats.workUnits + pendingWork > task.budget.workUnits)
                throw new ComputationStopped('budget-exceeded', 'Schema work budget exhausted');
        };
        let reviewEligible = false;
        let cacheHits = 0;
        const report = () => freeze({ requestId, outcome, revision: input.revision, versions: input.versions, dependencyFingerprint: input.semanticFingerprint, scope: options.scope, purpose: options.purpose, level: options.level, coverage: { scope: options.scope, complete, checked: [...new Map(checked.map(r => [refKey(r), r])).values()], unavailable: [...missing] }, diagnostics, missing: [...missing], ruleVersions, reviewEligible, stats: { elapsedMs: Date.now() - started, workUnits: context.stats.workUnits + pendingWork, cacheHits } });
        try {
            options = captureOptions(optionsArgument);
            task = { ...options, ...(!options.budget && limits ? { budget: limits } : {}) };
            const cacheAllowed = !task.budget && !task.cancel;
            context = createContext(versions, liveTask(task));
            context.check();
            const captured = boundedClone(inputArgument, context, units => pendingWork += units);
            if (!isRecord(captured) || typeof captured.rootFile !== 'string' || typeof captured.semanticFingerprint !== 'string' || !isRecord(captured.revision)
                || typeof captured.revision.model !== 'string' || !isRecord(captured.revision.sources) || !isRecord(captured.revision.data)
                || Object.values(captured.revision.sources).some(value => typeof value !== 'string') || Object.values(captured.revision.data).some(value => typeof value !== 'string')
                || !isRecord(captured.versions) || !isRecord(captured.coverage) || !validScope(captured.coverage.scope) || typeof captured.coverage.complete !== 'boolean'
                || !Array.isArray(captured.coverage.checked) || !captured.coverage.checked.every(validRef) || !Array.isArray(captured.coverage.unavailable)
                || captured.coverage.unavailable.some(value => typeof value !== 'string'))
                throw Error('Malformed model snapshot envelope');
            input = freeze(captured);
            diagnostics.push(...clone(decodeDiagnostics));
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            if (destroyed)
                throw new ComputationStopped('cancelled', 'Verifier has been destroyed');
            context.check();
            if (!levelOrder.includes(options.level))
                throw new Error('Unknown verification level');
            if (!validScope(options.scope) || typeof options.purpose !== 'string' || !options.purpose)
                throw Error('Verification requires an explicit valid scope and purpose');
            if (capabilities.length || input.contract !== 'ddn-next-1' || !equal(input.versions, versions)) {
                diagnostics.push(...capabilities, issue('DDN-VERSION', 'Snapshot version set must match this verifier'));
                outcome = 'unsupported';
                complete = false;
                missing.add('compatible-version-set');
                return report();
            }
            const activeValues = new Set();
            const scan = [{ value: input.normalized, depth: 0 }];
            let bytes = 0;
            while (scan.length) {
                const item = scan.pop();
                const value = item.value;
                context.check();
                if (item.exit) {
                    activeValues.delete(value);
                    continue;
                }
                if (item.depth > 128)
                    throw new ComputationStopped('budget-exceeded', 'Structured input depth exceeds the verifier bound');
                if (value && typeof value === 'object') {
                    if (activeValues.has(value))
                        throw new Error('Cyclic input is not JSON');
                    if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)
                        throw new Error('Only plain JSON records are permitted');
                    activeValues.add(value);
                    scan.push({ value, depth: item.depth, exit: true });
                    for (const [key, child] of Object.entries(value)) {
                        bytes += key.length * 2;
                        scan.push({ value: child, depth: item.depth + 1 });
                    }
                }
                else if (value === null || typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value))
                    bytes += typeof value === 'string' ? value.length * 2 : 8;
                else
                    throw new Error('Non-JSON value');
                context.accountMemory(bytes);
            }
            if (input.semanticFingerprint !== fingerprint(input.normalized)) {
                diagnostics.push(issue('DDN-SNAPSHOT-FINGERPRINT', 'Snapshot semantic fingerprint does not match its data'));
                outcome = 'invalid';
                complete = false;
                return report();
            }
            const key = fingerprint([input.rootFile, input.normalized, input.revision, input.coverage, options.scope, options.level, options.purpose, options.measurement ?? null, versions, packs.map(p => p.manifest)]);
            if (!decodeDiagnostics.length && cacheAllowed) {
                const previous = cache.get(key);
                if (previous)
                    return freeze({ ...previous, requestId, stats: { elapsedMs: Date.now() - started, workUnits: context.stats.workUnits + pendingWork, cacheHits: 1 } });
            }
            if (diagnostics.some(d => d.code === 'version.unsupported')) {
                outcome = 'unsupported';
                complete = false;
                missing.add('language-version');
                return report();
            }
            if (severity(diagnostics)) {
                outcome = 'invalid';
                complete = false;
                return report();
            }
            if (options.level === 'decode') {
                reviewEligible = false;
                complete = input.coverage.complete && !input.coverage.unavailable.length;
                for (const value of input.coverage.unavailable)
                    missing.add(value);
                return report();
            }
            const fileRows = bundleFiles(input.normalized);
            const records = indexRecords(input.normalized);
            const recordIndex = indexCapturedRecords(records);
            context.accountMemory(stableStringify(input.normalized).length * 2);
            const schemaReferences = [];
            const files = new Map(fileRows.map(f => [f.location, f]));
            if (!isRecord(input.normalized) || input.normalized.entry !== input.rootFile)
                diagnostics.push(issue('DDN-ENTRY', 'Snapshot root must match the normalized entry file'));
            if (files.size !== fileRows.length)
                diagnostics.push(issue('DDN-FILE-DUPLICATE', 'Physical file locations must be unique'));
            if (!files.has(input.rootFile))
                diagnostics.push(issue('DDN-ENTRY', 'The entry file is unavailable'));
            const reachable = new Set(), pending = [input.rootFile];
            while (pending.length) {
                const name = pending.pop();
                if (reachable.has(name))
                    continue;
                reachable.add(name);
                const file = files.get(name);
                if (!file) {
                    missing.add(name);
                    continue;
                }
                await context.checkpoint(1);
                const includes = file.document.includes;
                if (Array.isArray(includes))
                    for (const value of includes) {
                        if (typeof value !== 'string')
                            continue;
                        const location = files.has(value) ? value : safeLocation(name, value);
                        if (location)
                            pending.push(location);
                        else
                            diagnostics.push(issue('DDN-INCLUDE-PATH', 'Invalid include location ' + value));
                    }
            }
            // Ignore inactive file-owned data before applying the diagnostic cap,
            // so errors in unincluded files cannot hide an active schema error.
            const validationFiles = isRecord(input.normalized) && Array.isArray(input.normalized.files) ? input.normalized.files.filter(file => !isRecord(file) || typeof file.location !== 'string' || reachable.has(file.location)) : undefined;
            const activeNormalized = isRecord(input.normalized) ? { ...input.normalized, ...(validationFiles ? { files: validationFiles } : {}) } : input.normalized;
            const bundleIssues = validateSchema('bundle', activeNormalized, { checkpoint: schemaAccount, maxIssues: 200 });
            if (bundleIssues.some(issue => issue.keyword === 'depth'))
                throw new ComputationStopped('budget-exceeded', 'Schema recursion bound exceeded');
            if (bundleIssues.length >= 200)
                throw new ComputationStopped('budget-exceeded', 'Schema diagnostic limit prevents proving complete scoped validation');
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            const root = files.get(input.rootFile)?.document;
            const wa = isRecord(root?.workarea) ? root.workarea : {};
            const standaloneViews = wa.mode === 'standalone' ? records.filter(record => reachable.has(record.file) && (record.owner === 'view_definition' || record.owner === 'document')) : undefined;
            const activeWorkarea = records.find(record => record.file === input.rootFile && record.owner === 'workarea');
            if (standaloneViews && standaloneViews.length > 1)
                diagnostics.push(issue('DDN-STANDALONE-VIEWS', 'A standalone workarea can contain only one view or document across its included files', activeWorkarea?.ref));
            const method = typeof wa.method === 'string' ? wa.method : 'ddn';
            const allowedForeign = typeof wa.allow_foreign_views === 'boolean' ? wa.allow_foreign_views : method === 'ddn';
            const methodNames = { MT01: 'ddn', MT02: 'uml', MT03: 'chen', MT04: 'flowchart', MT05: 'bpmn', MT06: 'cmmn', MT07: 'dmn', MT08: 'c4', MT09: 'dfd', MT10: 'sysml', MT11: 'archimate', MT12: 'epc', MT13: 'idef0', MT14: 'petri', MT15: 'orm', MT16: 'vsm', MT17: 'sdl', MT18: 'msc', MT19: 'soaml', MT20: 'uaf', MT21: 'electrical' };
            const byIdentity = new Set(), byName = new Set();
            for (const record of records) {
                if (!reachable.has(record.file))
                    continue;
                await context.checkpoint(1);
                const k = refKey(record.ref);
                if (byIdentity.has(k))
                    diagnostics.push(issue('DDN-ID-DUPLICATE', 'Stable identity is repeated in its physical file', record.ref));
                byIdentity.add(k);
                if (typeof record.record.name === 'string') {
                    const nk = record.file + '\0' + record.record.name.normalize('NFC');
                    if (byName.has(nk))
                        diagnostics.push(issue('DDN-NAME-DUPLICATE', 'Declared names must be unique within a physical file', record.ref));
                    byName.add(nk);
                }
            }
            for (const file of fileRows) {
                if (!reachable.has(file.location))
                    continue;
                validateSchema('file', file.document, { maxIssues: 0, checkpoint: schemaAccount, reference: (value, path) => schemaReferences.push({ file: file.location, path, value }) });
            }
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            const dependencies = new Map();
            const target = options.scope.kind === 'workarea' ? undefined : resolveRecord(records, options.scope.target.file, options.scope.target);
            const selected = new Set();
            if (options.scope.kind === 'workarea') {
                for (const record of records)
                    if (reachable.has(record.file) && !(record.owner === 'workarea' && record.file !== input.rootFile))
                        selected.add(refKey(record.ref));
            }
            else if (target && reachable.has(target.file) && (options.scope.kind !== 'view' || target.owner === 'view_definition') && (options.scope.kind !== 'document' || target.owner === 'document') && (target.owner !== 'workarea' || target.file === input.rootFile)) {
                selected.add(refKey(target.ref));
                if (target.owner === 'view_definition' || target.owner === 'document')
                    for (const record of records) {
                        if (record.owner !== 'appearance')
                            continue;
                        const parent = resolveRecord(records, record.file, record.record.parent);
                        if (parent && refKey(parent.ref) === refKey(target.ref))
                            selected.add(refKey(record.ref));
                    }
            }
            else {
                diagnostics.push(issue('DDN-SCOPE', 'Requested scope does not resolve'));
                complete = false;
            }
            const referenceDiagnostics = [];
            for (const reference of schemaReferences) {
                const fragmentMatch = /^\/templates\/(\d+)\/fragment(?:\/|$)/.exec(reference.path);
                if (fragmentMatch) {
                    const template = records.find(r => r.file === reference.file && r.collection === 'templates' && r.index === Number(fragmentMatch[1]));
                    const fragment = template?.record.fragment;
                    if (isRecord(fragment)) {
                        const local = indexRecords({ files: [{ location: reference.file, document: fragment }] });
                        if (resolveRecord(local, reference.file, reference.value))
                            continue;
                    }
                }
                const owner = containingRecord(records, reference.file, reference.path);
                const destination = resolveRecord(records, reference.file, reference.value);
                const file = typeof reference.value.file === 'string' ? reference.value.file : reference.file;
                if (!reachable.has(file) || !destination) {
                    referenceDiagnostics.push({ owner, diagnostic: issue('DDN-REFERENCE', 'Reference does not resolve within the supplied include closure' + (reference.path ? ' at ' + reference.path : ''), owner?.ref) });
                    continue;
                }
                if (owner) {
                    const set = dependencies.get(refKey(owner.ref)) ?? new Set();
                    set.add(refKey(destination.ref));
                    dependencies.set(refKey(owner.ref), set);
                }
                if (typeof reference.value.revision === 'string' && reference.value.revision !== input.revision.sources[file])
                    referenceDiagnostics.push({ owner, diagnostic: issue('DDN-REFERENCE-REVISION', 'Pinned reference revision is unavailable', owner?.ref) });
            }
            // Item checks include containing views so their graph-wide constraints participate.
            if (target && target.owner === 'definition') {
                const owners = new Set(enclosingDefinitions(records, target).map(r => refKey(r.ref)));
                for (const owner of owners)
                    selected.add(owner);
                for (const occurrence of records.filter(r => r.owner === 'appearance')) {
                    const definition = resolveRecord(records, occurrence.file, occurrence.record.target);
                    if (definition && owners.has(refKey(definition.ref))) {
                        selected.add(refKey(occurrence.ref));
                        const parent = resolveRecord(records, occurrence.file, occurrence.record.parent);
                        if (parent)
                            selected.add(refKey(parent.ref));
                    }
                }
            }
            const children = new Map();
            const addChild = (parent, child) => {
                const key = refKey(parent.ref), values = children.get(key);
                if (values)
                    values.push(refKey(child.ref));
                else
                    children.set(key, [refKey(child.ref)]);
            };
            for (const record of records) {
                if (record.owner === 'appearance') {
                    const parent = resolveRecord(records, record.file, record.record.parent);
                    if (parent && (parent.owner === 'view_definition' || parent.owner === 'document'))
                        addChild(parent, record);
                }
                else if (record.owner === 'note' && record.path) {
                    for (let at = record.path.indexOf('/notes/'); at >= 0; at = record.path.indexOf('/notes/', at + 1)) {
                        const parent = recordIndex.paths.get(record.file + '\0' + record.path.slice(0, at));
                        if (parent)
                            addChild(parent, record);
                    }
                }
            }
            const expanded = new Set();
            const expandClosure = () => {
                const closure = [...selected];
                for (let i = 0; i < closure.length; i++) {
                    const current = closure[i];
                    if (expanded.has(current))
                        continue;
                    expanded.add(current);
                    for (const key of [...children.get(current) ?? [], ...dependencies.get(current) ?? []])
                        if (!selected.has(key)) {
                            selected.add(key);
                            closure.push(key);
                        }
                }
            };
            expandClosure();
            // Dynamic rule reads extend the real scope before completeness is checked.
            const reachableRecords = new Set(records.filter(record => reachable.has(record.file) && (record.owner !== 'workarea' || record.file === input.rootFile)).map(record => refKey(record.ref)));
            const ruleNormalized = activeNormalized;
            const ruleInput = freeze({ ...input, normalized: ruleNormalized, semanticFingerprint: fingerprint(ruleNormalized), coverage: { ...input.coverage, checked: input.coverage.checked.filter(ref => reachableRecords.has(refKey(ref))) } });
            const evaluated = new Map();
            let discovered = true;
            const evaluate = async (rule, callOptions) => {
                const invocation = rule.id + '\0' + fingerprint(callOptions.scope);
                if (evaluated.has(invocation))
                    return;
                await context.checkpoint(1);
                const semanticKey = fingerprint([input.rootFile, input.semanticFingerprint, input.revision.model, input.revision.data, input.versions, input.coverage, callOptions.scope, callOptions.level, callOptions.purpose, callOptions.measurement ?? null, packs.map(pack => pack.manifest), rule.id, rule.version, rule.readPaths, rule.globalScope]);
                const canReuse = cacheAllowed && input.coverage.complete && levelOrder.indexOf(options.level) >= 2 && !rule.readPaths.some(path => /^(?:revision|source|sources)(?:[./]|$)/.test(path));
                const reused = canReuse ? ruleCache.get(semanticKey) : undefined;
                const callbackOptions = Object.freeze({ ...callOptions, scope: freeze(clone(callOptions.scope)) });
                const raw = reused ?? await rule.evaluate(ruleInput, callbackOptions, context);
                context.check();
                const result = ruleResult(raw, callOptions, ruleInput, records, reachableRecords);
                if (reused)
                    cacheHits++;
                evaluated.set(invocation, { rule, result });
                for (const reference of [...result.coverage.checked, ...result.dependencies.map(dependency => dependency.target)]) {
                    if (!selected.has(refKey(reference))) {
                        selected.add(refKey(reference));
                        discovered = true;
                    }
                }
                expandClosure();
                if (!reused && canReuse && result.coverage.complete && ['valid', 'invalid'].includes(result.outcome) && !result.diagnostics.some(d => d.source || d.related?.length) && !result.dependencies.some(d => /^(?:revision|source|sources)(?:[./]|$)/.test(d.path)) && ruleCache.size < 128)
                    ruleCache.set(semanticKey, result);
            };
            while (discovered) {
                discovered = false;
                for (const rule of rules) {
                    if (!rule.levels.includes(options.level) || rule.purposes.length && !rule.purposes.includes('*') && !rule.purposes.includes(options.purpose))
                        continue;
                    if (rule.profiles.length && !records.some(record => selected.has(refKey(record.ref)) && record.owner === 'view_definition' && rule.profiles.includes(typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1')))
                        continue;
                    await evaluate(rule, options);
                    for (const view of records.filter(record => selected.has(refKey(record.ref)) && record.owner === 'view_definition')) {
                        const descriptor = profileDescriptors.get(typeof view.record.profile === 'string' ? view.record.profile : 'ddn@1');
                        if (descriptor?.ruleIds.includes(rule.id) && ![...evaluated.values()].some(entry => entry.rule.id === rule.id && entry.result.coverage.checked.some(ref => refKey(ref) === refKey(view.ref))))
                            await evaluate(rule, { ...options, scope: { kind: 'view', target: view.ref } });
                    }
                }
            }
            for (const { owner, diagnostic } of referenceDiagnostics)
                if (options.scope.kind === 'workarea' || !owner || selected.has(refKey(owner.ref)))
                    diagnostics.push(diagnostic);
            for (const error of bundleIssues) {
                const path = /^\/files\/(\d+)\/document(.*)$/.exec(error.path);
                const sourceFile = path ? validationFiles?.[Number(path[1])] : undefined;
                const file = isRecord(sourceFile) && typeof sourceFile.location === 'string' ? { location: sourceFile.location } : undefined;
                if (file && !reachable.has(file.location))
                    continue;
                const owner = file && path ? containingRecord(records, file.location, path[2]) : undefined;
                if (options.scope.kind === 'workarea' || !owner || selected.has(refKey(owner.ref)))
                    diagnostics.push(issue('DDN-SCHEMA-' + error.keyword.toUpperCase(), error.path + ': ' + error.message, owner?.ref));
            }
            const scopeRecords = records.filter(r => selected.has(refKey(r.ref)));
            const requiredRules = new Map();
            for (const record of scopeRecords) {
                await context.checkpoint(1);
                checked.push(record.ref);
                const state = status(record.record);
                if (state === 'accepted') {
                    const acceptance = record.record.acceptance;
                    if (!isRecord(acceptance) || validateSchema('acceptance_entry', acceptance).length)
                        diagnostics.push(issue('DDN-ACCEPTANCE', 'Accepted content requires valid acceptance time and user attribution', record.ref));
                }
                else if (record.record.acceptance !== undefined)
                    diagnostics.push(issue('DDN-ACCEPTANCE-STATE', 'Only accepted content may have a current acceptance event', record.ref));
                if (record.owner === 'definition' && record.record.category === 'relation') {
                    const ends = Array.isArray(record.record.endpoints) ? record.record.endpoints.filter(isRecord) : [];
                    for (const end of ends) {
                        if (end.pending_name !== undefined) {
                            missing.add('endpoint:' + refKey(record.ref));
                            continue;
                        }
                        const owner = resolveRecord(records, record.file, end.definition);
                        if (end.member !== undefined && owner) {
                            const member = resolveRecord(records, record.file, end.member);
                            const members = Array.isArray(owner.record.members) ? owner.record.members : [];
                            if (!member || !members.some(ref => resolveRecord(records, owner.file, ref) === member))
                                diagnostics.push(issue('DDN-MEMBER-ENDPOINT', 'Endpoint member must belong to its endpoint definition', record.ref));
                        }
                    }
                }
                if (record.owner === 'view_definition') {
                    const profileId = typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1';
                    const descriptor = profileDescriptors.get(profileId);
                    const native = getProfile(profileId);
                    if (!descriptor) {
                        missing.add('profile:' + profileId);
                        continue;
                    }
                    if (!allowedForeign && methodNames[descriptor.method] !== method)
                        diagnostics.push(issue('DDN-WORKAREA-METHOD', 'View profile is not admitted by the active workarea method', record.ref));
                    if (Array.isArray(wa.allowed_profiles) && wa.allowed_profiles.length && !wa.allowed_profiles.includes(profileId))
                        diagnostics.push(issue('DDN-WORKAREA-PROFILE', 'View profile is excluded by workarea allowed_profiles', record.ref));
                    if (!descriptor.ruleIds.length || !descriptor.ruleIds.every(id => rules.some(rule => rule.id === id)))
                        missing.add('rules:' + profileId);
                    if (levelOrder.indexOf(options.level) >= 2)
                        for (const id of descriptor.ruleIds) {
                            const required = requiredRules.get(id) ?? new Set();
                            required.add(refKey(record.ref));
                            requiredRules.set(id, required);
                        }
                }
                const resolved = resolveProperties(input, record.ref);
                diagnostics.push(...resolved.diagnostics.map(d => ({ ...d, target: record.ref })));
            }
            const ownership = new Map();
            for (const record of scopeRecords) {
                if (record.owner !== 'definition')
                    continue;
                const members = Array.isArray(record.record.members) ? record.record.members : [];
                for (const ref of members) {
                    const child = resolveRecord(records, record.file, ref);
                    if (child) {
                        const k = refKey(child.ref);
                        ownership.set(k, [...(ownership.get(k) ?? []), refKey(record.ref)]);
                    }
                }
            }
            for (const [child, owners] of ownership)
                if (new Set(owners).size > 1)
                    diagnostics.push(issue('DDN-MEMBER-OWNER', 'A semantic member has more than one owner', scopeRecords.find(x => refKey(x.ref) === child)?.ref));
            // Ownership cycles are independent of where occurrences happen to be placed.
            for (const start of ownership.keys()) {
                const path = new Set();
                let current = start;
                while (current) {
                    if (path.has(current)) {
                        diagnostics.push(issue('DDN-OWNERSHIP-CYCLE', 'Semantic ownership cannot be cyclic'));
                        break;
                    }
                    path.add(current);
                    current = ownership.get(current)?.[0];
                }
            }
            let incomplete = false;
            if (standaloneViews?.length === 0 && (levelOrder.indexOf(options.level) >= 3 || ['in-review', 'accepted'].includes(status(wa)))) {
                incomplete = true;
                missing.add('standalone-view');
                diagnostics.push({ code: 'DDN-STANDALONE-VIEW-MISSING', severity: 'warning', message: 'A standalone workarea needs one view or document before review', ...(activeWorkarea ? { target: activeWorkarea.ref } : {}) });
            }
            for (const record of scopeRecords) {
                const pending = record.record.incomplete;
                const reviewRequested = levelOrder.indexOf(options.level) >= 3 || ['in-review', 'accepted'].includes(status(record.record));
                if (!reviewRequested)
                    continue;
                if (Array.isArray(pending) && pending.length) {
                    incomplete = true;
                    missing.add('content:' + refKey(record.ref));
                }
                const hasStructuredData = Array.isArray(getPath(record.record, 'data.columns')) && Array.isArray(getPath(record.record, 'data.rows'));
                if (!hasStructuredData && typeof getPath(record.record, 'draft.text') === 'string' && String(getPath(record.record, 'draft.text')).trim()) {
                    incomplete = true;
                    missing.add('draft:' + refKey(record.ref));
                }
                if (record.owner === 'definition') {
                    const name = typeof record.record.role === 'string' ? record.record.role : 'object', category = record.record.category === 'relation' ? 'relation' : 'element';
                    const role = roleDescriptor(name, category) ?? coreTypeDescriptor(name, category);
                    const core = role ? coreDescriptor(role.core) : undefined;
                    if (core) {
                        const checks = validateSchema(core.complete, record.record.content ?? {});
                        if (checks.length) {
                            incomplete = true;
                            missing.add('complete:' + refKey(record.ref));
                            diagnostics.push({ code: 'DDN-COMPLETENESS', severity: 'warning', message: checks.map(c => c.message).join('; '), target: record.ref });
                        }
                    }
                    if (options.purpose === 'physical-schema' && (record.record.role === 'entity' || record.record.role === 'table')) {
                        const fields = Array.isArray(record.record.members) ? record.record.members.map(ref => resolveRecord(records, record.file, ref)).filter((r) => !!r) : [];
                        const columns = getPath(record.record, 'data.columns'), rows = getPath(record.record, 'data.rows');
                        const typeIndex = Array.isArray(columns) ? columns.findIndex(c => isRecord(c) && c.id === 'type') : -1;
                        const fieldType = (field) => {
                            const explicit = getPath(field.record, 'content.datatype') ?? getPath(field.record, 'properties.datatype');
                            if (explicit !== undefined)
                                return explicit;
                            const ordinal = getPath(field.record, 'content.ordinal');
                            const row = Array.isArray(rows) && typeof ordinal === 'number' ? rows[ordinal] : undefined;
                            return Array.isArray(row) && typeIndex >= 0 ? row[typeIndex] : undefined;
                        };
                        if (!fields.length || fields.some(field => { const value = fieldType(field); return value === undefined || value === null || typeof value === 'string' && !value.trim(); })) {
                            incomplete = true;
                            missing.add('physical-schema:' + refKey(record.ref));
                        }
                    }
                }
            }
            if (levelOrder.indexOf(options.level) >= 3 && !['design', 'review', 'display', 'conceptual', 'documentation', 'physical-schema'].includes(options.purpose) && !rules.some(r => r.purposes.includes(options.purpose))) {
                missing.add('purpose:' + options.purpose);
                outcome = 'unsupported';
            }
            const executed = new Set();
            for (const { rule, result } of evaluated.values()) {
                executed.add(rule.id);
                ruleVersions[rule.id] = rule.version;
                diagnostics.push(...result.diagnostics);
                checked.push(...result.coverage.checked);
                for (const item of result.coverage.unavailable)
                    missing.add(item);
                if (!result.coverage.complete) {
                    complete = false;
                }
                if (result.outcome === 'cancelled' || result.outcome === 'budget-exceeded')
                    throw new ComputationStopped(result.outcome, 'Rule ' + rule.id + ' stopped');
                if (result.outcome === 'unsupported') {
                    missing.add('rule:' + rule.id);
                    outcome = 'unsupported';
                }
                if (result.outcome === 'stale')
                    outcome = 'stale';
                if (result.outcome === 'incomplete')
                    incomplete = true;
                if (result.outcome === 'invalid' && !severity(result.diagnostics))
                    diagnostics.push(issue('DDN-RULE-INVALID', 'Rule ' + rule.id + ' rejected the scope'));
            }
            for (const id of requiredRules.keys())
                if (!executed.has(id))
                    missing.add('rules:' + id + ':not-executed');
            for (const [id, required] of requiredRules)
                for (const target of required)
                    if (![...evaluated.values()].some(entry => entry.rule.id === id && entry.result.coverage.checked.some(ref => refKey(ref) === target)))
                        missing.add('rules:' + id + ':coverage');
            const providerScope = input.coverage.scope;
            const coversScope = providerScope.kind === 'workarea' || equal(providerScope, options.scope) || options.scope.kind === 'item' && ['view', 'document'].includes(providerScope.kind);
            // A complete workarea input supplies its whole model for fresh
            // checking; a narrower provider must name the required closure.
            const coversReads = providerScope.kind === 'workarea' || checked.every(ref => input.coverage.checked.some(provided => equal(provided, ref)));
            if (!coversScope || !coversReads) {
                missing.add('input-scope-coverage');
                complete = false;
            }
            if (!input.coverage.complete || input.coverage.unavailable.length) {
                complete = false;
                for (const item of input.coverage.unavailable)
                    missing.add(item);
                if (input.coverage.unavailable.length === 0)
                    missing.add('complete-input-coverage');
            }
            if (options.level === 'publication') {
                const documents = scopeRecords.filter(record => record.owner === 'document');
                if (!documents.length) {
                    missing.add('publication-output-format');
                    incomplete = true;
                }
                for (const document of documents) {
                    const format = typeof document.record.format === 'string' ? document.record.format : codex.properties.find(p => p.owner === 'document' && p.path === 'format')?.default.value;
                    if (typeof format !== 'string') {
                        missing.add('publication-output-format');
                        incomplete = true;
                    }
                    else if (!['svg', 'png', 'json', 'markdown', 'csv'].includes(format)) {
                        missing.add('output:' + format);
                        outcome = 'unsupported';
                        diagnostics.push({ code: 'DDN-PUBLICATION-OUTPUT', severity: 'warning', message: 'No native publication adapter evidence is available for ' + format, target: document.ref });
                    }
                }
                if (!options.measurement) {
                    missing.add('publication-measurement');
                    incomplete = true;
                }
                else if (!equal(options.measurement.revision, input.revision) || !equal(options.measurement.versions, input.versions)) {
                    outcome = 'stale';
                    diagnostics.push(issue('DDN-MEASUREMENT-STALE', 'Publication measurements do not belong to this snapshot'));
                }
                else if (typeof options.measurement.fingerprint !== 'string' || !options.measurement.fingerprint.trim() || typeof options.measurement.fontGeneration !== 'string' || !options.measurement.fontGeneration
                    || options.measurement.measurements === undefined || !options.measurement.coverage || !equal(options.measurement.coverage.scope, options.scope) || !options.measurement.coverage.complete
                    || !Array.isArray(options.measurement.coverage.unavailable) || options.measurement.coverage.unavailable.length
                    || !Array.isArray(options.measurement.coverage.checked) || !checked.every(ref => options.measurement.coverage.checked.some(provided => equal(provided, ref)))) {
                    incomplete = true;
                    missing.add('publication-measurement-coverage');
                }
            }
            if (severity(diagnostics) && outcome !== 'stale' && outcome !== 'unsupported')
                outcome = 'invalid';
            else if (outcome !== 'stale' && outcome !== 'unsupported')
                outcome = [...missing].some(x => x.startsWith('profile:') || x.startsWith('rules:')) ? 'unsupported' : incomplete || missing.size || !complete ? 'incomplete' : 'valid';
            if (missing.size || incomplete)
                complete = false;
            reviewEligible = outcome === 'valid' && complete && levelOrder.indexOf(options.level) >= 3;
            context.check();
            const result = report();
            if (cacheAllowed && complete && cache.size < 128)
                cache.set(key, result);
            return result;
        }
        catch (error) {
            complete = false;
            reviewEligible = false;
            if (error instanceof ComputationStopped) {
                outcome = error.outcome;
                missing.add(options.level);
                diagnostics.push(issue('DDN-' + outcome.toUpperCase(), error.message));
            }
            else {
                outcome = 'invalid';
                diagnostics.push(issue('DDN-VERIFY-INPUT', error instanceof Error ? error.message : 'Invalid verification input'));
            }
            return report();
        }
    }
    async function checkTransition(inputArgument, transitionArgument, optionsArgument = {}) {
        const diagnostics = [];
        try {
            const started = Date.now(), capturedOptions = captureOptions(optionsArgument);
            const options = { ...capturedOptions, ...(!capturedOptions.budget && limits ? { budget: limits } : {}) };
            const context = createContext(versions, liveTask(options));
            context.check();
            let units = 0;
            const input = freeze(boundedClone(inputArgument, context, count => units += count));
            const transition = freeze(boundedClone(transitionArgument, context, count => units += count));
            await context.checkpoint(units + 1);
            if (!input || input.contract !== 'ddn-next-1' || !equal(input.versions, versions) || !isRecord(input.normalized) || input.normalized.entry !== input.rootFile || input.semanticFingerprint !== fingerprint(input.normalized))
                throw Error('Transition requires a current consistent snapshot');
            if (!transition || !validRef(transition.target) || !Array.isArray(transition.grants) || transition.grants.some(grant => typeof grant !== 'string'))
                throw Error('Malformed transition request');
            const record = resolveRecord(indexRecords(input.normalized), transition.target.file, transition.target);
            if (!record || !['definition', 'view_definition', 'document', 'workarea'].includes(record.owner) || !reachedFiles(input).has(record.file) || record.owner === 'workarea' && record.file !== input.rootFile)
                return { allowed: false, diagnostics: [issue('DDN-TRANSITION-TARGET', 'Transition target does not resolve', transition.target)] };
            if (status(record.record) !== transition.from)
                diagnostics.push(issue('DDN-TRANSITION-STALE', 'Current lifecycle state differs from the supplied base', transition.target));
            if (!['draft', 'in-progress', 'in-review', 'accepted'].includes(transition.from) || !['draft', 'in-progress', 'in-review', 'accepted'].includes(transition.to))
                return freeze({ allowed: false, diagnostics: [issue('DDN-TRANSITION', 'Unknown lifecycle state', transition.target)] });
            if (transition.from === transition.to)
                return { allowed: diagnostics.length === 0, diagnostics };
            const matrix = { 'draft': ['in-progress'], 'in-progress': ['in-review'], 'in-review': ['in-progress', 'accepted'], 'accepted': ['in-review', 'in-progress'] };
            if (!matrix[transition.from]?.includes(transition.to))
                diagnostics.push(issue('DDN-TRANSITION', 'Requested lifecycle transition is not permitted', transition.target));
            if (transition.from === 'accepted' && !transition.grants.includes('lifecycle.reopen'))
                diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Reopening accepted content requires lifecycle.reopen authority', transition.target));
            if (transition.to === 'in-review' && !transition.grants.includes('lifecycle.review'))
                diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Review transition requires lifecycle.review authority', transition.target));
            if (transition.to === 'in-review' || transition.to === 'accepted') {
                const report = transition.report;
                if (!report || report.outcome !== 'valid' || !report.reviewEligible || !['review', 'publication'].includes(report.level) || !validScope(report.scope)
                    || !report.coverage?.complete || !equal(report.coverage.scope, report.scope) || !Array.isArray(report.coverage.unavailable) || report.coverage.unavailable.length
                    || !Array.isArray(report.missing) || report.missing.length || !Array.isArray(report.diagnostics) || severity(report.diagnostics)
                    || !equal(report.revision, input.revision) || report.dependencyFingerprint !== input.semanticFingerprint || !equal(report.versions, input.versions)
                    || !Array.isArray(report.coverage.checked) || !report.coverage.checked.some(r => equal(r, transition.target)))
                    diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'Current complete review verification covering the target is required', transition.target));
                if (report) {
                    const remaining = options.budget ? { ...options.budget, elapsedMs: Math.max(0, options.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, options.budget.workUnits - context.stats.workUnits) } : undefined;
                    const actual = await verify(input, { ...options, ...(remaining ? { budget: remaining } : {}), scope: report.scope, purpose: report.purpose, level: 'review' });
                    await context.checkpoint(actual.stats.workUnits);
                    if (!actual.reviewEligible || actual.outcome !== 'valid' || !actual.coverage.checked.some(r => equal(r, transition.target)))
                        diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'The current model does not pass independently recomputed review verification', transition.target));
                    const known = new Map([['ddn.structure', '1.0.0'], ['ddn.lifecycle', '1.0.0'], ...rules.map(rule => [rule.id, rule.version])]);
                    if (!isRecord(report.ruleVersions) || Object.entries(report.ruleVersions).some(([id, version]) => known.get(id) !== version)
                        || Object.entries(actual.ruleVersions).some(([id, version]) => report.ruleVersions?.[id] !== version))
                        diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'Review rule versions do not match the current required rules', transition.target));
                }
            }
            if (transition.to === 'accepted') {
                const event = transition.acceptance;
                if (!event || typeof event.user !== 'string' || !event.user.trim() || typeof event.authorityContext !== 'string' || !event.authorityContext.trim() || typeof event.timestamp !== 'string' || validateSchema('instant', event.timestamp).length)
                    diagnostics.push(issue('DDN-TRANSITION-ACCEPTANCE', 'Acceptance requires user, offset-qualified timestamp and authority context', transition.target));
                if (!transition.grants.includes('lifecycle.accept'))
                    diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Acceptance requires lifecycle.accept authority', transition.target));
            }
            context.check();
            return freeze({ allowed: diagnostics.length === 0, diagnostics });
        }
        catch (error) {
            return freeze({ allowed: false, diagnostics: [...diagnostics, issue(error instanceof ComputationStopped ? 'DDN-' + error.outcome.toUpperCase() : 'DDN-TRANSITION-INPUT', error instanceof Error ? error.message : 'Invalid transition input')] });
        }
    }
    const verifier = {
        async verifySources(inputArgument, optionsArgument) {
            const started = Date.now();
            let input = { entry: 'unavailable.ddn', files: [] };
            let options = { scope: { kind: 'workarea' }, level: 'decode', purpose: '' };
            let normalized = { version: 'ddn-next-1', entry: input.entry, files: [] };
            let sourceUnits = 0;
            let diagnostics = [];
            let coverage = { scope: options.scope, complete: false, checked: [], unavailable: [] };
            let stopped;
            let task = options;
            const spans = new Map();
            try {
                options = captureOptions(optionsArgument);
                task = { ...options, ...(!options.budget && limits ? { budget: limits } : {}) };
                if (destroyed)
                    throw new ComputationStopped('cancelled', 'Verifier has been destroyed');
                const context = createContext(versions, liveTask(task));
                context.check();
                input = captureSources(inputArgument, context);
                sourceUnits = input.files.reduce((n, f) => n + f.text.length, 0);
                context.accountMemory(sourceUnits * 2);
                await context.checkpoint(sourceUnits);
                const decoded = decodeSources(input, task);
                context.check();
                normalized = decoded.normalized;
                diagnostics = decoded.diagnostics;
                coverage = decoded.coverage;
                for (const node of allNodes(decoded))
                    if (node.ref && !spans.has(refKey(node.ref)))
                        spans.set(refKey(node.ref), { file: node.file, revision: input.files.find(file => file.id === node.file).revision, start: node.start, end: node.end });
            }
            catch (error) {
                stopped = error instanceof ComputationStopped ? error.outcome : 'invalid';
                diagnostics = [issue('DDN-DECODE-' + stopped.toUpperCase(), error instanceof Error ? error.message : 'Source decoding failed')];
            }
            const digest = fingerprint(normalized);
            const snapshot = { contract: 'ddn-next-1', rootFile: input.entry, revision: { model: digest, sources: Object.fromEntries(input.files.map(f => [f.id, f.revision])), data: {} }, versions, semanticFingerprint: digest, normalized, coverage };
            const remaining = task.budget ? { ...task.budget, elapsedMs: Math.max(0, task.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, task.budget.workUnits - sourceUnits) } : undefined;
            const result = await verify(snapshot, { ...task, ...(remaining ? { budget: remaining } : {}) }, diagnostics);
            const located = result.diagnostics.map(diagnostic => {
                if (diagnostic.source)
                    return diagnostic;
                const span = diagnostic.target ? spans.get(refKey(diagnostic.target)) : undefined;
                const root = input.files.find(file => file.id === input.entry);
                return span ? { ...diagnostic, source: span } : root ? { ...diagnostic, source: { file: root.id, revision: root.revision, start: 0, end: root.text.length } } : diagnostic;
            });
            return freeze({ ...result, diagnostics: located, ...(stopped ? { outcome: stopped, reviewEligible: false, coverage: { ...result.coverage, complete: false } } : {}), stats: { ...result.stats, elapsedMs: Date.now() - started, workUnits: sourceUnits + result.stats.workUnits } });
        },
        verifyModel: verify, checkTransition, destroy() { destroyed = true; cache.clear(); ruleCache.clear(); for (const listener of destroyListeners) {
            try {
                listener();
            }
            catch { /* Host cancellation callbacks do not interrupt disposal. */ }
        } destroyListeners.clear(); },
    };
    decodedVerifiers.set(verifier, verify);
    return verifier;
}
//# sourceMappingURL=index.js.map