import { allNodes, appendDeclaration, applySourcePatches, decodeSources, decodeText, deleteDeclaration, encodeDefinition, findNode, patchProperty, quoteText, renameDeclaration, replaceDataBody, replaceRecordData, serializeProperties, splitDelimited, replaceDraftBody, replaceNoteBody } from '../../language/src/index.js';
import { asArray, asRecord, asString, findRecord, getPath, isRecord, listRecords, normalizeLocation, resolveReference } from '../../model/src/index.js';
import { validateProperty, resolveProperties } from '../../defaults/src/index.js';
import { automaticLayoutAlgorithm } from './layout-edit.js';
import { createContext, clone, canonical, fingerprint, freeze, ComputationStopped } from '../../execution/src/index.js';
import { runtimeState, copySources } from './runtime.js';
import { registrations } from './registry.js';
import { prepareRuntimeProfiles, profileLoadingHost } from './profile-loading.js';
import { completeProfileIds, standardCommandIds, getProfile } from '../../profiles/src/core.js';
import { checkLifecycleMutation, affectedProtected, referenceGraph } from './guards.js';
const nativeProfiles = ['ddn@1', 'mindmap.basic@1', 'concept.map@1', 'table.records@1'];
const nativeIds = standardCommandIds;
const stringSchema = { type: 'string' }, numberSchema = { type: 'number' }, arraySchema = { type: 'array' }, referenceSchema = { type: 'object', required: ['file', 'id'], additionalProperties: false, properties: { file: stringSchema, id: stringSchema } };
const argumentDefinitions = {
    'ddn.add-dataset': { required: ['name', 'columns', 'rows'], properties: { name: stringSchema, columns: arraySchema, rows: arraySchema } },
    'ddn.set-records': { required: ['columns', 'rows'], properties: { columns: arraySchema, rows: arraySchema } },
    'ddn.add-view': { required: ['name', 'profile'], properties: { name: stringSchema, profile: { enum: completeProfileIds }, subtype: arraySchema } },
    'ddn.create-element': { required: ['role'], properties: { view: referenceSchema, role: stringSchema, name: stringSchema, position: { type: 'object', required: ['x', 'y'], additionalProperties: false, properties: { x: numberSchema, y: numberSchema } } } },
    'ddn.set-position': { required: ['x', 'y'], properties: { x: numberSchema, y: numberSchema } },
    'ddn.set-size': { required: ['width', 'height'], properties: { width: numberSchema, height: numberSchema } },
    'ddn.set-cell': { required: ['row', 'column', 'value'], properties: { row: { type: 'integer', minimum: 0 }, column: { type: ['integer', 'string'] }, value: {} } },
    'ddn.add-row': { required: [], properties: {} },
    'ddn.remove-row': { required: ['row'], properties: { row: { type: 'integer', minimum: 0 } } },
    'ddn.set-columns': { required: ['columns'], properties: { columns: arraySchema } },
    'ddn.add-note': { required: ['text'], properties: { text: stringSchema } },
    'ddn.set-note': { required: ['text'], properties: { text: stringSchema } },
    'ddn.set-draft': { required: ['text'], properties: { text: stringSchema, format: { enum: ['text', 'fields', 'table'] } } },
    'ddn.set-table': { required: ['columns', 'rows'], properties: { columns: arraySchema, rows: arraySchema } },
};
const argumentSchema = (id) => ({ type: 'object', additionalProperties: false, ...argumentDefinitions[id] });
function checkedArguments(command, value) {
    function check(schema, input, path) {
        const types = Array.isArray(schema.type) ? schema.type : typeof schema.type === 'string' ? [schema.type] : [];
        if (types.length && !types.some(type => type === 'array' ? Array.isArray(input) : type === 'object' ? isRecord(input) : type === 'integer' ? typeof input === 'number' && Number.isSafeInteger(input) : typeof input === type))
            throw Error('Invalid command argument ' + path);
        if (Array.isArray(schema.enum) && !schema.enum.some(item => canonical(item) === canonical(input)))
            throw Error('Invalid command choice ' + path);
        if (typeof schema.minimum === 'number' && typeof input === 'number' && input < schema.minimum)
            throw Error('Argument is below its minimum: ' + path);
        if (isRecord(input)) {
            const properties = asRecord(schema.properties);
            for (const name of asArray(schema.required))
                if (typeof name === 'string' && !(name in input))
                    throw Error('Missing command argument ' + path + '.' + name);
            for (const [name, item] of Object.entries(input)) {
                if (!(name in properties) && schema.additionalProperties === false)
                    throw Error('Unknown command argument ' + path + '.' + name);
                if (isRecord(properties[name]))
                    check(properties[name], item, path + '.' + name);
            }
        }
    }
    check(asRecord(argumentSchema(command)), value, command);
    return asRecord(value);
}
const ownerOf = (entry) => ({ view: entry.record.kind === 'document' ? 'document' : 'view_definition', placement: 'view_placement', data: 'data', source: 'source', asset: 'asset', template: 'template', publication: 'publication', note: 'note', workarea: 'workarea', definition: 'definition', appearance: 'appearance' })[entry.kind];
const key = (ref) => ref.file + '\0' + ref.id;
const status = (record) => asString(asRecord(record?.design).state, 'draft');
const ref = (value) => {
    if (!isRecord(value) || typeof value.file !== 'string' || typeof value.id !== 'string')
        throw Error('Expected a qualified reference');
    return { file: value.file, id: value.id };
};
const issue = (code, message, target) => ({ code, severity: 'error', message, ...(target ? { target } : {}) });
const failure = (code, diagnostics) => ({ ok: false, failure: { code, diagnostics } });
function sameSources(a, b) {
    return !!a && a.entry === b.entry && a.files.length === b.files.length && a.files.every(file => {
        const other = b.files.find(value => value.id === file.id);
        return !!other && file.text === other.text && file.revision === other.revision && file.writable === other.writable && file.encoding === other.encoding
            && (file.originalBytes === undefined ? other.originalBytes === undefined : !!other.originalBytes && file.originalBytes.length === other.originalBytes.length && file.originalBytes.every((byte, index) => byte === other.originalBytes[index]));
    });
}
function sourceQualifier(from, to) {
    if (from === to)
        return '';
    if (/^[a-z][a-z0-9+.-]*:/i.test(to))
        return quoteText(to) + '::';
    if (/^[a-z][a-z0-9+.-]*:/i.test(from) || from.startsWith('/') !== to.startsWith('/'))
        throw Error('The selected source namespaces do not have a representable relative reference');
    if (to.startsWith('/'))
        return quoteText(to) + '::';
    const parent = from.split('/').slice(0, -1), destination = to.split('/');
    while (parent.length && destination.length && parent[0] === destination[0]) {
        parent.shift();
        destination.shift();
    }
    return quoteText([...parent.map(() => '..'), ...destination].join('/')) + '::';
}
function difference(before, after) {
    return before.files.flatMap(file => {
        const next = after.files.find(f => f.id === file.id);
        if (!next)
            throw Error('Source files cannot disappear in an edit');
        if (next.text === file.text)
            return [];
        let start = 0;
        while (start < file.text.length && start < next.text.length && file.text[start] === next.text[start])
            start++;
        let end = file.text.length, nextEnd = next.text.length;
        while (end > start && nextEnd > start && file.text[end - 1] === next.text[nextEnd - 1]) {
            end--;
            nextEnd--;
        }
        return [{ file: file.id, base: file.revision, start, end, text: next.text.slice(start, nextEnd) }];
    });
}
function changedRecords(before, after) {
    const old = new Map(listRecords(before.normalized).map(e => [key(e.ref), e])), current = new Map(listRecords(after.normalized).map(e => [key(e.ref), e]));
    return [...new Set([...old.keys(), ...current.keys()])].sort().flatMap(k => canonical(old.get(k)?.record) === canonical(current.get(k)?.record) ? [] : [(current.get(k) ?? old.get(k)).ref]);
}
function liveRevision(runtime) {
    const state = runtimeState(runtime), snapshot = state.current;
    if (!snapshot)
        throw Error('No model is open');
    return { ...snapshot.revision, sources: Object.fromEntries(state.source?.files.map(f => [f.id, f.revision]) ?? Object.entries(snapshot.revision.sources)) };
}
const historyFactories = new WeakMap();
const activeHistoryGroups = new WeakMap();
export function createCommandHistoryGroup(service) {
    const create = historyFactories.get(service);
    if (!create)
        throw Error('History grouping is unavailable for this command service.');
    return create();
}
/** Capture before awaiting preparation; async continuations do not inherit this scope. */
export function currentCommandHistoryGroup(service) { return activeHistoryGroups.get(service); }
export function createCommandService(runtime, authority, limits = { maxCommands: 200, maxBytes: 32 * 1024 * 1024 }) {
    if (!Number.isSafeInteger(limits.maxCommands) || limits.maxCommands < 0 || !Number.isSafeInteger(limits.maxBytes) || limits.maxBytes < 0)
        throw Error('History limits must be nonnegative safe integers');
    limits = { ...limits };
    const pending = new Map(), undo = [], redo = [];
    let serial = 0, historyBytes = 0, expectedHistory = '';
    let historySources;
    let committing = false, travelling = false;
    function freshSource(source, before) { return { entry: source.entry, files: source.files.map(file => before.files.find(old => old.id === file.id)?.text === file.text ? file : ({ ...file, revision: 'source-' + fingerprint([file.id, file.text, ++serial]).slice(0, 24) })) }; }
    function find(decoded, target) {
        const entry = listRecords(decoded.normalized).find(e => key(e.ref) === key(target));
        if (!entry)
            throw Error('Target is unavailable: ' + target.id);
        return entry;
    }
    async function prepare(intentInput, task = {}) {
        try {
            canonical(intentInput);
            const intent = freeze(clone(intentInput));
            task = { ...task, ...(task.budget ? { budget: freeze(clone(task.budget)) } : {}) };
            const loadingStarted = Date.now();
            let loadingUnits = 0;
            if (intent.kind === 'profile-command') {
                const profiles = [intent.profile];
                if (intent.command === 'ddn.add-view') {
                    const selected = asString(asRecord(intent.arguments).profile);
                    if (selected)
                        profiles.push(selected);
                }
                loadingUnits += profiles.length;
                await prepareRuntimeProfiles(runtime, profiles, task);
            }
            if (intent.kind === 'set-property' && intent.path === 'profile' && typeof intent.value === 'string')
                await prepareRuntimeProfiles(runtime, [intent.value], task);
            if (intent.kind === 'edit-source') {
                const current = runtime.sources();
                if (current) {
                    const proposed = applySourcePatches(current, intent.patches);
                    loadingUnits += proposed.files.reduce((sum, file) => sum + file.text.length, 0);
                    await prepareRuntimeProfiles(runtime, proposed, task);
                }
            }
            if (task.budget && profileLoadingHost(runtime)) {
                const elapsedMs = task.budget.elapsedMs - (Date.now() - loadingStarted);
                if (elapsedMs < 0)
                    throw new ComputationStopped('budget-exceeded', 'Profile loading exceeded the command budget');
                task = { ...task, budget: { ...task.budget, elapsedMs, workUnits: Math.max(0, task.budget.workUnits - loadingUnits) } };
            }
            const state = runtimeState(runtime), before = state.source, snapshot = state.current;
            const generation = state.generation;
            const registryFingerprint = fingerprint(runtime.registry.describe());
            if (!before || !snapshot || !state.decoded)
                return failure('unsupported', [issue('command.sources', 'Editable sources must be open before preparing a command')]);
            if (intent.kind !== 'edit-source' && state.decoded.documents.some(d => before.files.find(f => f.id === d.file.id)?.text !== d.file.text))
                return failure('invalid', [issue('command.source-pending', 'Finish the invalid source edit before visual editing')]);
            const context = createContext(snapshot.versions, task);
            context.accountMemory(before.files.reduce((n, f) => n + f.text.length * 2, 0));
            const base = freeze(clone(liveRevision(runtime)));
            let source = copySources(before), decoded = state.decoded;
            let identityOrdinal = 0;
            const unique = (file) => {
                let id;
                do {
                    id = 'ddn-' + fingerprint([base, intent, file, ++identityOrdinal]).slice(0, 20);
                } while (listRecords(decoded.normalized).some(entry => entry.file === file && (entry.ref.id === id || entry.record.name === id)));
                return id;
            };
            const apply = (patches) => {
                if (patches.some(p => !source.files.some(f => f.id === p.file)))
                    throw Error('A source patch targets an unavailable file');
                source = applySourcePatches(source, patches);
                decoded = state.materialize(decodeSources(source, { previous: decoded, ...task }));
                if (!decoded.syntaxValid)
                    throw Error(decoded.diagnostics.map(d => d.message).join('; '));
            };
            const set = (target, path, value) => {
                const entry = find(decoded, target);
                if (entry.kind === 'appearance' && ['position', 'size', 'route'].includes(path.split('.')[0])) {
                    const view = resolveReference(decoded.normalized, entry.file, entry.record.parent);
                    if (getProfile(asString(view?.record.profile))?.projection !== 'graph')
                        throw Error('This profile derives item geometry from its projection settings');
                }
                if (['id', 'name', 'role', 'category', 'profile', 'design.state', 'acceptance', 'acceptance_history'].some(p => path === p || path.startsWith(p + '.')))
                    throw Error('Use the dedicated identity/lifecycle command for ' + path);
                if (value !== undefined) {
                    const errors = validateProperty(ownerOf(entry), path, value, { role: asString(entry.record.role), profile: asString(entry.record.profile), category: asString(entry.record.category, 'element') });
                    if (errors.some(e => e.severity === 'error'))
                        throw Error(errors.map(e => e.message).join('; '));
                }
                apply(patchProperty(decoded, target, path, value));
            };
            const setInternal = (target, path, value) => apply(patchProperty(decoded, target, path, value));
            const append = (file, text, parent) => apply(appendDeclaration(decoded, file, text, parent));
            const appearance = (target) => listRecords(decoded.normalized).find(e => e.kind === 'appearance' && key(resolveReference(decoded.normalized, e.file, e.record.target)?.ref ?? { file: '', id: '' }) === key(target))?.ref;
            const table = (target, columns, rows) => {
                if (!Array.isArray(columns) || !Array.isArray(rows) || columns.some(c => !isRecord(c) || typeof c.id !== 'string') || rows.some(r => !Array.isArray(r)))
                    throw Error('Table requires column descriptors and physical row arrays');
                const entry = find(decoded, target);
                if (asRecord(entry.record.data).source)
                    throw Error('Provider-bound data is read-only; change its provider or create an authored copy');
                const ds = { columns: columns, rows: rows };
                // A typed domain label creates a reusable provisional identity, never a physical type.
                const domainIndex = ds.columns.findIndex(c => c.id === 'domain');
                if (domainIndex >= 0)
                    for (const row of ds.rows) {
                        const name = row[domainIndex];
                        if (typeof name === 'string' && name) {
                            const parts = splitDelimited(name, '::');
                            if (parts.length > 2)
                                throw Error('A domain reference has one file qualifier');
                            const file = parts.length === 2 ? normalizeLocation(decodeText(parts[0]), target.file) : target.file;
                            const label = decodeText(parts.at(-1)).normalize('NFC');
                            const records = listRecords(decoded.normalized).filter(e => e.file === file);
                            const named = records.find(e => e.record.name === label) ?? records.find(e => e.ref.id === label);
                            if (named && named.record.role !== 'domain')
                                throw Error('Domain name belongs to another declaration: ' + name);
                            if (!named && parts.length === 2)
                                throw Error('Qualified domain is unavailable: ' + name);
                            if (!named)
                                append(target.file, encodeDefinition({ id: unique(target.file), name: label, role: 'domain' }));
                        }
                    }
                apply(replaceDataBody(decoded, target, ds));
                const occurrence = appearance(target);
                if (occurrence)
                    setInternal(occurrence, 'body', 'columns');
            };
            const addElement = (view, role, name, position) => {
                const parent = find(decoded, view);
                if (parent.kind !== 'view')
                    throw Error('Creation requires a view');
                const profile = getProfile(asString(parent.record.profile));
                if (!profile || !profile.primary_palette.includes(role))
                    throw Error('This role is not admitted by the selected profile: ' + role);
                // Decode creation and placement together so implicit occurrence identities are
                // derived from the same source at preparation and commit.
                const id = unique(view.file), record = { id, role, ...(name ? { name } : {}), ...(position && profile.projection === 'graph' ? { position, pinned: false } : {}) };
                append(view.file, encodeDefinition(record), view);
            };
            let action = 'model.edit';
            if (intent.kind === 'status')
                action = intent.transition.to === 'accepted' ? 'lifecycle.accept' : intent.transition.from === 'accepted' ? 'lifecycle.reopen' : intent.transition.to === 'in-review' ? 'lifecycle.review' : 'model.edit';
            let authorization;
            switch (intent.kind) {
                case 'create-definition': {
                    const properties = intent.properties ?? {};
                    if (Object.keys(properties).some(path => ['id', 'role', 'category', 'acceptance', 'acceptance_history', 'design'].some(p => path === p || path.startsWith(p + '.'))))
                        throw Error('Creation properties cannot override identity or lifecycle metadata');
                    append(intent.file, encodeDefinition({ ...properties, id: unique(intent.file), role: intent.role }));
                    break;
                }
                case 'create-occurrence': {
                    let target = find(decoded, intent.target);
                    if (!target.record.name) {
                        setInternal(target.ref, 'id', target.ref.id);
                        target = find(decoded, intent.target);
                    }
                    const name = unique(intent.view.file);
                    append(intent.view.file, 'use ' + sourceQualifier(intent.view.file, intent.target.file) + quoteText(asString(target.record.name, target.ref.id)) + ' named ' + quoteText(name), intent.view);
                    const occurrence = listRecords(decoded.normalized).find(e => e.kind === 'appearance' && e.file === intent.view.file && e.record.name === name);
                    if (!occurrence)
                        throw Error('Created occurrence is unavailable');
                    for (const [path, value] of Object.entries(intent.properties ?? {}))
                        set(occurrence.ref, path, value);
                    break;
                }
                case 'rename':
                    apply(renameDeclaration(decoded, intent.target, intent.name));
                    break;
                case 'set-property':
                    set(intent.target, intent.path, intent.value);
                    break;
                case 'reset-property':
                    set(intent.target, intent.path, undefined);
                    break;
                case 'edit-source':
                    apply(intent.patches);
                    break;
                case 'remove': {
                    if (!['retain-diagnostic', 'remove-dependents'].includes(intent.references))
                        throw Error('Choose an explicit reference-removal policy');
                    const selected = find(decoded, intent.target), selectedNode = findNode(decoded, intent.target);
                    if ((selected.kind === 'appearance' || selected.kind === 'placement') && selectedNode?.implicit)
                        throw Error('This occurrence is implicit; remove its inline declaration or author an explicit use before removing only this occurrence');
                    if (intent.references === 'remove-dependents') {
                        const removed = new Set([key(intent.target)]);
                        const dependencies = referenceGraph(decoded.normalized);
                        const mentions = (value, file) => { const referenced = resolveReference(decoded.normalized, file, value); return !!referenced && removed.has(key(referenced.ref)); };
                        let grew = true;
                        while (grew) {
                            grew = false;
                            for (const entry of listRecords(decoded.normalized))
                                if (!removed.has(key(entry.ref)) && (entry.kind === 'appearance' || entry.kind === 'placement' || entry.kind === 'definition') && [...(dependencies.get(key(entry.ref)) ?? [])].some(id => removed.has(id))) {
                                    removed.add(key(entry.ref));
                                    grew = true;
                                }
                        }
                        // Explicit selection lists survive; remove only their deleted references.
                        for (const entry of listRecords(decoded.normalized).filter(e => e.kind === 'view'))
                            for (const path of ['selection.include', 'selection.items', 'sources']) {
                                const value = getPath(entry.record, path);
                                if (Array.isArray(value) && value.some(v => mentions(v, entry.file)))
                                    setInternal(entry.ref, path, value.filter(v => !mentions(v, entry.file)));
                            }
                        const deletions = listRecords(decoded.normalized).filter(e => removed.has(key(e.ref)) && key(e.ref) !== key(intent.target));
                        for (const entry of deletions) {
                            const node = findNode(decoded, entry.ref);
                            if (!node || node.implicit)
                                continue;
                            if (selectedNode && entry.file === selected.file && node.start >= selectedNode.start && node.end <= selectedNode.end)
                                continue;
                            apply(deleteDeclaration(decoded, entry.ref));
                        }
                    }
                    apply(deleteDeclaration(decoded, intent.target));
                    break;
                }
                case 'connect': {
                    for (const target of [intent.from, intent.to])
                        if (!find(decoded, target).record.name)
                            setInternal(target, 'id', target.id);
                    const from = find(decoded, intent.from), to = find(decoded, intent.to);
                    const reference = (entry) => sourceQualifier(intent.view.file, entry.file) + quoteText(asString(entry.record.name, entry.ref.id));
                    const name = unique(intent.view.file);
                    append(intent.view.file, `connect ${reference(from)} to ${reference(to)}${intent.relation ? ' as ' + quoteText(intent.relation) : ''} named ${quoteText(name)}`, intent.view);
                    const relation = listRecords(decoded.normalized).find(e => e.file === intent.view.file && e.record.name === name);
                    if (relation)
                        for (const [path, value] of Object.entries(intent.properties ?? {}))
                            set(relation.ref, path, value);
                    // A palette drop is provisional until connected. Release only the
                    // selected occurrence in this view, in the same undoable edit as
                    // its relation; unrelated or deliberately pinned items stay put.
                    let released = false;
                    for (const endpoint of [intent.from, intent.to]) {
                        const selected = find(decoded, endpoint);
                        const occurrence = selected.kind === 'appearance' ? selected : listRecords(decoded.normalized).find(entry => entry.kind === 'appearance' && key(resolveReference(decoded.normalized, entry.file, entry.record.parent)?.ref ?? { file: '', id: '' }) === key(intent.view) &&
                            key(resolveReference(decoded.normalized, entry.file, entry.record.target)?.ref ?? { file: '', id: '' }) === key(endpoint));
                        if (occurrence?.record.pinned === false && key(resolveReference(decoded.normalized, occurrence.file, occurrence.record.parent)?.ref ?? { file: '', id: '' }) === key(intent.view)) {
                            set(occurrence.ref, 'position', undefined);
                            set(occurrence.ref, 'pinned', undefined);
                            released = true;
                        }
                    }
                    if (released && getPath(resolveProperties(snapshot, intent.view).values, 'layout.algorithm') === 'manual')
                        set(intent.view, 'layout.algorithm', automaticLayoutAlgorithm(asString(find(decoded, intent.view).record.profile)));
                    // Derive generated occurrence identities from the final source and
                    // original revision, exactly as commit does. Intermediate parses
                    // can otherwise retain identities for the just-removed pin blocks.
                    if (released)
                        decoded = state.materialize(decodeSources(source, { previous: state.decoded, ...task }));
                    break;
                }
                case 'convert-body': {
                    if (!['field-list', 'header-table'].includes(intent.interpretation))
                        throw Error('Choose an explicit draft interpretation');
                    const entry = find(decoded, intent.target), draft = asRecord(entry.record.draft), text = asString(draft.text), lines = text.split(/\r?\n/).filter(line => line.trim());
                    if (intent.interpretation === 'field-list')
                        table(intent.target, ['field', 'type', 'domain', 'constraint', 'key', 'comment'].map(id => ({ id })), lines.map(line => [line, null, null, null, null, null]));
                    else {
                        const temporary = decodeSources({ entry: 'conversion.ddn', files: [{ id: 'conversion.ddn', text: 'data Body\n' + lines.map(l => '    ' + l).join('\n'), revision: '1', encoding: 'utf-8', writable: true }] });
                        if (!temporary.syntaxValid)
                            throw Error(temporary.diagnostics.map(d => d.message).join('; '));
                        const data = listRecords(temporary.normalized).find(e => e.kind === 'data');
                        if (!data)
                            throw Error('A table draft needs a header');
                        table(intent.target, data.record.columns ?? [], data.record.rows ?? []);
                    }
                    const remaining = asArray(find(decoded, intent.target).record.incomplete).filter(value => asRecord(value).path !== 'draft');
                    setInternal(intent.target, 'incomplete', remaining.length ? remaining : undefined);
                    break;
                }
                case 'status': {
                    const target = find(decoded, intent.transition.target);
                    authorization = await authority.authorize(action, [target.ref], base);
                    if (!authorization.allowed)
                        return failure('unauthorized', [issue('command.authority', 'Status change is not authorized')]);
                    const transition = { ...intent.transition, grants: authorization.grants };
                    if (transition.acceptance && transition.acceptance.user !== authorization.principal)
                        return failure('unauthorized', [issue('command.attribution', 'Acceptance must name the authorized principal')]);
                    const eligibility = await runtime.verifier.checkTransition(snapshot, transition, task);
                    if (!eligibility.allowed)
                        return failure('invalid', eligibility.diagnostics);
                    if (transition.from !== transition.to) {
                        if (target.record.acceptance) {
                            setInternal(target.ref, 'acceptance_history', [...asArray(target.record.acceptance_history), target.record.acceptance]);
                            setInternal(target.ref, 'acceptance', undefined);
                        }
                        setInternal(target.ref, 'design.state', transition.to);
                        if (transition.to === 'accepted' && transition.acceptance)
                            setInternal(target.ref, 'acceptance', { at: transition.acceptance.timestamp, by: transition.acceptance.user, semantic_digest: snapshot.semanticFingerprint });
                    }
                    break;
                }
                case 'profile-command': {
                    const descriptor = registrations(runtime.registry).commands?.find(d => d.id === intent.command && d.profiles.includes(intent.profile));
                    if (!descriptor)
                        return failure('unsupported', [issue('command.unsupported', 'No registered command: ' + intent.command)]);
                    if (!nativeIds.includes(intent.command)) {
                        const prepared = await descriptor.prepare(snapshot, intent, context);
                        if (!prepared.ok)
                            return prepared;
                        apply(prepared.command.patches);
                        break;
                    }
                    if (!completeProfileIds.includes(intent.profile))
                        throw Error('Editing is unavailable for this profile');
                    const args = checkedArguments(intent.command, intent.arguments), target = ['ddn.add-view', 'ddn.add-dataset'].includes(intent.command) ? undefined : find(decoded, intent.target);
                    switch (intent.command) {
                        case 'ddn.add-dataset': {
                            if (!asString(args.name).trim())
                                throw Error('A dataset needs a unique name');
                            append(snapshot.rootFile, 'data ' + quoteText(asString(args.name)) + '\n    with\n' + serializeProperties({ id: unique(snapshot.rootFile), columns: args.columns, rows: args.rows }, '        '));
                            break;
                        }
                        case 'ddn.set-records':
                            apply(replaceRecordData(decoded, target.ref, args.columns, args.rows));
                            break;
                        case 'ddn.add-view': {
                            const profile = asString(args.profile);
                            if (!descriptor.profiles.includes(profile) || !asString(args.name).trim())
                                throw Error('Choose an installed profile and a unique view name');
                            if (asArray(args.subtype).some(value => value !== 'erd') || asArray(args.subtype).length > 1)
                                throw Error('Only the native ERD view subtype is registered for this command');
                            const text = profile === 'ddn@1' && asArray(args.subtype).includes('erd') ? 'erd ' + quoteText(asString(args.name)) : 'view ' + quoteText(asString(args.name)) + ' as ' + quoteText(profile);
                            append(snapshot.rootFile, text);
                            break;
                        }
                        case 'ddn.create-element':
                            addElement(ref(args.view ?? intent.target), asString(args.role), typeof args.name === 'string' ? args.name : undefined, args.position);
                            break;
                        case 'ddn.set-position':
                            set(target.ref, 'position', { x: args.x, y: args.y });
                            // Keep unconnected palette items provisional even after moving
                            // them. Moving an existing item is an explicit manual pin.
                            if (target.kind === 'appearance' && target.record.pinned !== false)
                                set(target.ref, 'pinned', true);
                            break;
                        case 'ddn.set-size':
                            set(target.ref, 'size', { width: args.width, height: args.height });
                            break;
                        case 'ddn.set-draft': {
                            apply(replaceDraftBody(decoded, target.ref, asString(args.text), asString(args.format, 'text')));
                            const pending = asArray(find(decoded, target.ref).record.incomplete).filter(value => asRecord(value).path !== 'draft');
                            if (asString(args.text).trim())
                                pending.push({ path: 'draft', raw: '', reason: 'Draft editing is pending' });
                            setInternal(target.ref, 'incomplete', pending.length ? pending : undefined);
                            const occurrence = appearance(target.ref);
                            if (occurrence)
                                setInternal(occurrence, 'body', 'draft');
                            break;
                        }
                        case 'ddn.set-table':
                            table(target.ref, args.columns, args.rows);
                            break;
                        case 'ddn.set-columns':
                            table(target.ref, args.columns, asRecord(target.record.data).rows ?? []);
                            break;
                        case 'ddn.set-cell':
                        case 'ddn.add-row':
                        case 'ddn.remove-row': {
                            const data = asRecord(target.record.data), columns = asArray(data.columns), rows = clone(asArray(data.rows));
                            if (intent.command === 'ddn.add-row')
                                rows.push(columns.map(() => null));
                            else {
                                const row = Number(args.row);
                                if (!Number.isInteger(row) || row < 0 || row >= rows.length)
                                    throw Error('Row is unavailable');
                                if (intent.command === 'ddn.remove-row')
                                    rows.splice(row, 1);
                                else {
                                    const column = typeof args.column === 'number' ? args.column : columns.findIndex(c => asRecord(c).id === args.column);
                                    if (!Number.isInteger(column) || column < 0 || column >= columns.length)
                                        throw Error('Column is unavailable');
                                    rows[row][column] = args.value ?? null;
                                }
                            }
                            table(target.ref, columns, rows);
                            break;
                        }
                        case 'ddn.add-note':
                            append(target.file, 'notes : Notes\n' + asString(args.text).split('\n').map(line => '    ' + line).join('\n'), target.ref);
                            break;
                        case 'ddn.set-note':
                            apply(replaceNoteBody(decoded, target.ref, asString(args.text)));
                            break;
                    }
                    break;
                }
                default:
                    return failure('unsupported', [issue('command.unsupported', 'Unknown command intent')]);
            }
            await context.checkpoint(listRecords(decoded.normalized).length);
            const writeSet = changedRecords(snapshot, decoded), protectedScopes = affectedProtected(snapshot, decoded.normalized);
            if (intent.kind !== 'status' && protectedScopes.length)
                return failure('invalid', protectedScopes.map(target => issue('command.protected', 'Reopen this protected scope before semantic editing', target)));
            if (intent.kind !== 'status') {
                const lifecycle = checkLifecycleMutation(snapshot.normalized, decoded.normalized);
                if (lifecycle.length)
                    return failure('invalid', lifecycle);
            }
            authorization = await authority.authorize(action, writeSet, base);
            if (!authorization.allowed)
                return failure('unauthorized', [issue('command.authority', 'The affected scope is not authorized')]);
            const candidate = { ...snapshot, normalized: decoded.normalized, semanticFingerprint: fingerprint(decoded.normalized), coverage: decoded.coverage };
            const report = await runtime.verifier.verifyModel(candidate, { scope: { kind: 'workarea' }, purpose: 'design', level: 'semantic', ...task });
            if (['invalid', 'cancelled', 'budget-exceeded', 'stale', 'unsupported'].includes(report.outcome))
                return failure(report.outcome === 'cancelled' ? 'cancelled' : report.outcome === 'budget-exceeded' ? 'budget-exceeded' : 'invalid', report.diagnostics);
            if (registryFingerprint !== fingerprint(runtime.registry.describe()))
                return failure('conflict', [issue('command.capabilities', 'Registered rules changed while preparing the command')]);
            context.check();
            if (generation !== state.generation || canonical(liveRevision(runtime)) !== canonical(base))
                return failure('conflict', [issue('command.conflict', 'Revision changed while preparing the command')]);
            const patches = difference(before, source), id = 'command-' + (++serial);
            // Preparation currently performs workarea-wide semantic verification.
            // Report that conservative dependency scope, including unchanged reads.
            const readSet = listRecords(snapshot.normalized).sort((a, b) => key(a.ref) < key(b.ref) ? -1 : key(a.ref) > key(b.ref) ? 1 : 0).map(entry => ({ target: entry.ref, path: '', fingerprint: fingerprint(entry.record) }));
            const prepared = freeze({ id, base, intent, readSet, writeSet, patches, modelDelta: writeSet.map(target => ({ target: target, before: (findRecord(snapshot.normalized, target) ?? null), after: (findRecord(decoded.normalized, target) ?? null) })), summary: [intent.kind === 'profile-command' ? intent.command : intent.kind, `${patches.length} source file(s), ${writeSet.length} record(s)`], diagnostics: [...decoded.diagnostics, ...report.diagnostics], protectedScopes, eligible: true });
            pending.set(id, { public: prepared, before: copySources(before), after: source, decoded, action, principal: authorization.principal, registryFingerprint, generation });
            return { ok: true, command: prepared };
        }
        catch (error) {
            const code = error instanceof ComputationStopped ? error.outcome === 'cancelled' ? 'cancelled' : 'budget-exceeded' : 'invalid';
            return failure(code, [issue('command.prepare', error instanceof Error ? error.message : 'Command preparation failed')]);
        }
    }
    async function commit(preparedId, task = {}, group, groupBefore, history) {
        if (committing || travelling && !history)
            return failure('conflict', [issue('command.busy', 'Another command or history operation is committing')]);
        const prepared = pending.get(preparedId);
        if (!prepared)
            return failure('invalid', [issue('command.missing', 'Prepared command is missing or discarded')]);
        committing = true;
        try {
            const state = runtimeState(runtime), before = liveRevision(runtime);
            task = { ...task, ...(task.budget ? { budget: freeze(clone(task.budget)) } : {}) };
            const context = createContext(state.current.versions, task);
            if (group && prepared.public.intent.kind === 'status')
                return failure('invalid', [issue('history.group-lifecycle', 'Lifecycle changes must remain separate from live settings.')]);
            if (group && !group.current)
                return failure('conflict', [issue('history.group-conflict', 'The diagram changed outside this settings session. Reopen the editor to continue.')]);
            let rejected;
            const reject = (code, diagnostics) => { rejected = { code, diagnostics }; return diagnostics; };
            const unchanged = (publication) => {
                context.check();
                if (pending.get(preparedId) !== prepared)
                    return reject('cancelled', [issue('command.discarded', 'Prepared command was discarded')]);
                if (prepared.registryFingerprint !== fingerprint(runtime.registry.describe()))
                    return reject('conflict', [issue('command.capabilities', 'Registered rules changed; prepare again')]);
                if (state.generation !== prepared.generation + (publication ? 1 : 0) || !sameSources(state.source, prepared.before) || canonical(liveRevision(runtime)) !== canonical(prepared.public.base))
                    return reject('conflict', [issue('command.conflict', 'The source context or model/source/data revision changed; prepare again')]);
                return [];
            };
            const check = async (publication = false) => {
                const changed = unchanged(publication);
                if (changed.length)
                    return changed;
                const authorized = await authority.authorize(prepared.action, prepared.public.writeSet, before);
                if (!authorized.allowed || authorized.principal !== prepared.principal)
                    return reject('unauthorized', [issue('command.revoked', 'Authority or principal changed since preparation')]);
                if (prepared.public.intent.kind === 'status') {
                    const eligibility = await runtime.verifier.checkTransition(state.current, { ...prepared.public.intent.transition, grants: authorized.grants }, task);
                    if (!eligibility.allowed)
                        return reject('invalid', eligibility.diagnostics);
                    const latest = await authority.authorize(prepared.action, prepared.public.writeSet, before);
                    if (!latest.allowed || latest.principal !== authorized.principal || canonical(latest.grants) !== canonical(authorized.grants))
                        return reject('unauthorized', [issue('command.revoked', 'Authority changed while validating the transition')]);
                }
                return unchanged(publication);
            };
            if ((await check()).length)
                return { ok: false, failure: rejected };
            if (!prepared.public.patches.length) {
                pending.delete(preparedId);
                return { ok: true, receipt: { commandId: preparedId, before, after: before, changed: [] } };
            }
            const next = freshSource(prepared.after, prepared.before), baseline = groupBefore ?? prepared.before;
            const forward = difference(baseline, next), inverse = difference(next, baseline);
            const opened = await state.commitSources(next, task, fingerprint(prepared.decoded.normalized), { check: () => check(true), published(result) {
                    // Finalize bookkeeping inside the publication boundary, before
                    // revision listeners can attempt another command or undo.
                    pending.delete(preparedId);
                    historySources = next;
                    if (history) {
                        const from = history.direction === 'undo' ? undo : redo, to = history.direction === 'undo' ? redo : undo;
                        from.pop();
                        to.push(history.entry);
                        expectedHistory = canonical(result.revision);
                    }
                    else if (prepared.public.intent.kind !== 'status') {
                        historyBytes -= redo.reduce((sum, entry) => sum + entry.bytes, 0);
                        redo.length = 0;
                        const previous = undo.at(-1);
                        if (group && previous?.group === group) {
                            undo.pop();
                            historyBytes -= previous.bytes;
                        }
                        const entry = { forward, inverse, bytes: [...forward, ...inverse].reduce((n, p) => n + p.text.length * 2, 0), expected: canonical(result.revision), ...(group ? { group } : {}) };
                        if (forward.length) {
                            undo.push(entry);
                            historyBytes += entry.bytes;
                        }
                        expectedHistory = entry.expected;
                        let trimmed = false;
                        while (undo.length > limits.maxCommands || historyBytes > limits.maxBytes) {
                            const removed = undo.shift();
                            if (!removed)
                                break;
                            historyBytes -= removed.bytes;
                            trimmed = true;
                        }
                        if (trimmed)
                            state.diagnostics = freeze([...state.diagnostics, { code: 'history.checkpoint', severity: 'info', message: 'Undo history reached its configured limit. Older edits are no longer undoable; current source is retained.' }]);
                    }
                    else {
                        undo.length = 0;
                        redo.length = 0;
                        historyBytes = 0;
                        expectedHistory = '';
                        historySources = undefined;
                    }
                } });
            if (!opened.committed)
                return rejected ? { ok: false, failure: rejected } : failure(opened.diagnostics.some(d => d.code === 'runtime.stale') ? 'conflict' : opened.diagnostics.some(d => d.code === 'runtime.cancelled') ? 'cancelled' : opened.diagnostics.some(d => d.code === 'runtime.budget-exceeded') ? 'budget-exceeded' : 'invalid', opened.diagnostics);
            return { ok: true, receipt: { commandId: preparedId, before, after: opened.revision, changed: prepared.public.writeSet } };
        }
        catch (error) {
            return failure(error instanceof ComputationStopped ? error.outcome : 'invalid', [issue('command.commit', error instanceof Error ? error.message : 'Commit failed')]);
        }
        finally {
            committing = false;
        }
    }
    async function travel(direction, task = {}) {
        if (committing || travelling)
            return failure('conflict', [issue('history.busy', 'Another command or history operation is committing')]);
        travelling = true;
        try {
            const from = direction === 'undo' ? undo : redo, entry = from.at(-1);
            if (!entry)
                return failure('invalid', [issue('history.empty', 'Nothing to ' + direction)]);
            if (!historySources || !sameSources(runtime.sources(), historySources) || canonical(liveRevision(runtime)) !== expectedHistory)
                return failure('conflict', [issue('history.conflict', 'External changes require a history checkpoint')]);
            const source = runtime.sources();
            const patches = (direction === 'undo' ? entry.inverse : entry.forward).map(p => ({ ...p, base: source.files.find(f => f.id === p.file).revision }));
            const prepared = await prepare({ kind: 'edit-source', patches }, task);
            if (!prepared.ok)
                return prepared;
            return await commit(prepared.command.id, task, undefined, undefined, { direction, entry });
        }
        catch (error) {
            return failure('invalid', [issue('history.failed', error instanceof Error ? error.message : 'History operation failed')]);
        }
        finally {
            travelling = false;
        }
    }
    const service = { prepare, commit, undo: task => travel('undo', task), redo: task => travel('redo', task), discard(id) { pending.delete(id); } };
    historyFactories.set(service, () => {
        const before = runtime.sources();
        if (!before)
            throw Error('Open editable sources before editing settings.');
        let baseline = copySources(before);
        const abort = new AbortController();
        let expected = canonical(liveRevision(runtime)), generation = runtimeState(runtime).generation, closed = false, changed = false;
        const group = {
            get current() { return !closed && !runtimeState(runtime).disposed && generation === runtimeState(runtime).generation && expected === canonical(liveRevision(runtime)); },
            get changed() { return changed; },
            signal: { get aborted() { return abort.signal.aborted; }, onAbort(handler) { abort.signal.addEventListener('abort', handler); return () => abort.signal.removeEventListener('abort', handler); } },
            run(action) {
                if (!group.current)
                    throw Error('The diagram changed outside this settings session. Reopen the editor to continue.');
                const previous = activeHistoryGroups.get(service);
                activeHistoryGroups.set(service, group);
                try {
                    return action();
                }
                finally {
                    if (previous)
                        activeHistoryGroups.set(service, previous);
                    else
                        activeHistoryGroups.delete(service);
                }
            },
            async commit(id, task = {}) {
                if (!baseline)
                    return failure('cancelled', [issue('history.group-closed', 'This settings session is closed.')]);
                const result = await commit(id, { ...task, cancel: group.signal }, group, baseline);
                if (result.ok) {
                    expected = canonical(result.receipt.after);
                    generation = runtimeState(runtime).generation;
                    changed = !!undo.find(entry => entry.group === group);
                }
                return result;
            },
            async revert() {
                if (!group.current || undo.at(-1)?.group !== group)
                    return failure('conflict', [issue('history.group-conflict', 'Only the latest settings session can be reverted. Use Undo to review later edits first.')]);
                const result = await travel('undo', { cancel: group.signal });
                if (result.ok) {
                    expected = canonical(result.receipt.after);
                    generation = runtimeState(runtime).generation;
                    changed = false;
                }
                return result;
            },
            close() { closed = true; baseline = undefined; abort.abort(); },
        };
        return group;
    });
    return service;
}
/** Descriptors disclose the native edit vocabulary; the runtime materializes its source-aware plans. */
export function createNativeCommandPack() { return commandPack(nativeProfiles, 'ddn-native'); }
export function createCompleteCommandPack() { return commandPack(completeProfileIds, 'ddn-complete'); }
export function createModularCommandPack() { return commandPack(completeProfileIds, 'ddn-native', 'ddn-modular-commands'); }
function commandPack(profiles, dependency, id = dependency + '-commands') {
    return { manifest: { id, version: '1.0.0', api: '1.0', hash: fingerprint([nativeIds, profiles]), languages: ['ddn-next-1'], defaults: ['ddn-next-1'], profiles, dependencies: [dependency], capabilities: ['native.edit'] }, registrations: {
            schemas: Object.fromEntries(nativeIds.map(id => [id + '.arguments', argumentSchema(id)])),
            commands: nativeIds.map(id => ({ id, profiles, argumentSchemaId: id + '.arguments', propertyPaths: id === 'ddn.set-position' ? ['position'] : id === 'ddn.set-size' ? ['size'] : id === 'ddn.set-draft' ? ['draft', 'body'] : ['data', 'definitions', 'appearances'], editor: 'specialized', async prepare(input, intent) {
                    if (intent.kind !== 'profile-command' || intent.command !== id || !isRecord(intent.arguments))
                        return failure('invalid', [issue('command.arguments', 'Invalid native command arguments')]);
                    try {
                        checkedArguments(id, intent.arguments);
                    }
                    catch (error) {
                        return failure('invalid', [issue('command.arguments', String(error))]);
                    }
                    return { ok: true, command: { id: 'native-plan-' + fingerprint(intent), base: input.revision, intent, readSet: [], writeSet: [intent.target], patches: [], modelDelta: { kind: 'native-intent', command: id, arguments: intent.arguments }, summary: [id], diagnostics: [], protectedScopes: [], eligible: true } };
                } })),
        } };
}
//# sourceMappingURL=commands.js.map