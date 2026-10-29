import { asArray, asRecord, asString, listRecords, resolveReference, normalizedFiles, recordRef } from '../../model/src/index.js';
import { validateSchema } from '../../profiles/src/schema-core.js';
import { canonical } from '../../execution/src/index.js';
const key = (ref) => ref.file + '\0' + ref.id;
const status = (record) => asString(asRecord(record.design).state, 'draft');
const paint = new Set(['style', 'text', 'background', 'border', 'shadow', 'padding', 'opacity', 'position', 'size', 'min_size', 'max_size', 'aspect_ratio', 'layer', 'order', 'visible', 'locked', 'include_in_output', 'pinned', 'rotation', 'route', 'body', 'sections', 'section_order', 'columns', 'column_visibility', 'stroke', 'symbol', 'table', 'layout', 'display', 'legend', 'grid', 'snap', 'guides', 'rulers', 'navigation', 'chrome', 'animation', 'title']);
const semantic = (record) => Object.fromEntries(Object.entries(record).filter(([name]) => (!paint.has(name) || name === 'title' && record.role !== undefined) && !['acceptance', 'acceptance_history', 'design'].includes(name)));
/** Only schema-declared references form dependencies; arbitrary JSON data never does. */
export function referenceGraph(normalized) {
    const graph = new Map();
    for (const file of normalizedFiles(normalized))
        validateSchema('file', file.document, { maxIssues: 0, reference(value, path) {
                const segments = path.split('/');
                const collection = segments[1];
                const owner = collection === 'workarea' ? asRecord(file.document.workarea) : asRecord(asArray(file.document[collection ?? ''])[Number(segments[2])]);
                if (typeof owner.id !== 'string')
                    return;
                const target = resolveReference(normalized, file.location, value);
                if (!target)
                    return;
                const id = key(recordRef(file.location, owner)), references = graph.get(id) ?? new Set();
                references.add(key(target.ref));
                graph.set(id, references);
            } });
    return graph;
}
/** Source edits and provider updates cannot manufacture lifecycle transitions or attribution. */
export function checkLifecycleMutation(beforeNormalized, afterNormalized) {
    const previous = new Map(listRecords(beforeNormalized).map(entry => [key(entry.ref), entry]));
    const result = [];
    for (const entry of listRecords(afterNormalized)) {
        const before = previous.get(key(entry.ref));
        const changed = before
            ? status(before.record) !== status(entry.record) || canonical(before.record.acceptance) !== canonical(entry.record.acceptance) || canonical(before.record.acceptance_history) !== canonical(entry.record.acceptance_history)
            : status(entry.record) !== 'draft' || entry.record.acceptance !== undefined || entry.record.acceptance_history !== undefined;
        if (changed)
            result.push({ code: 'runtime.lifecycle', severity: 'error', message: 'Use an authorized lifecycle command to change status or acceptance evidence.', target: entry.ref });
    }
    return result;
}
/** Protect accepted/reviewed definitions and every accepted scope that depends on them. */
export function affectedProtected(snapshot, afterNormalized) {
    const before = listRecords(snapshot.normalized), after = listRecords(afterNormalized);
    const previous = new Map(before.map(entry => [key(entry.ref), entry]));
    const next = new Map(after.map(entry => [key(entry.ref), entry]));
    const changed = new Set();
    for (const id of new Set([...previous.keys(), ...next.keys()])) {
        if (canonical(semantic(previous.get(id)?.record ?? {})) !== canonical(semantic(next.get(id)?.record ?? {})))
            changed.add(id);
    }
    const dependencies = referenceGraph(snapshot.normalized);
    let grew = true;
    while (grew) {
        grew = false;
        for (const entry of before)
            if (!changed.has(key(entry.ref)) && [...(dependencies.get(key(entry.ref)) ?? [])].some(id => changed.has(id))) {
                changed.add(key(entry.ref));
                grew = true;
            }
    }
    return before.filter(entry => {
        if (!['accepted', 'in-review'].includes(status(entry.record)))
            return false;
        if (entry.kind === 'workarea' && entry.file !== snapshot.rootFile)
            return false;
        const acceptance = asRecord(entry.record.acceptance);
        const explicitlyScoped = asArray(acceptance.scope).some(reference => { const target = resolveReference(snapshot.normalized, entry.file, reference); return !!target && changed.has(key(target.ref)); });
        const presentationProtected = typeof acceptance.presentation_digest === 'string' && canonical(entry.record) !== canonical(next.get(key(entry.ref))?.record);
        return entry.kind === 'workarea' && changed.size > 0 || changed.has(key(entry.ref)) || explicitlyScoped || presentationProtected;
    }).map(entry => entry.ref);
}
//# sourceMappingURL=guards.js.map