import { applySourcePatches, decodeSources, patchProperty } from '../../language/src/index.js';
import { asRecord, asString, getPath, listRecords, resolveReference } from '../../model/src/index.js';
import { resolve, resolveProperties } from '../../defaults/src/index.js';
import { getProfile } from '../../profiles/src/core.js';
import { copySources, runtimeState } from './runtime.js';
const key = (ref) => ref.file + '\0' + ref.id;
export function automaticLayoutAlgorithm(profile) {
    const standard = asString(getPath(resolve({}, 'view_definition', { profile }).values, 'layout.algorithm'), 'auto');
    return standard === 'manual' ? 'auto' : standard;
}
/** Plan one undoable, view-local edit. The caller commits through the normal
 * command service so lifecycle, source revisions and authority remain enforced.
 * An optional effective algorithm includes viewer-supplied CSS defaults. */
export function reflowViewPatches(runtime, view, effectiveAlgorithm) {
    const state = runtimeState(runtime), before = state.source, snapshot = state.current;
    if (!before || !snapshot || !state.decoded)
        throw Error('Editable sources are unavailable.');
    if (!before.files.find(file => file.id === view.file)?.writable)
        throw Error('This view belongs to a read-only file.');
    if (state.decoded.documents.some(document => before.files.find(file => file.id === document.file.id)?.text !== document.file.text))
        throw Error('Finish the invalid source edit before reflowing.');
    const records = listRecords(state.decoded.normalized), target = records.find(record => key(record.ref) === key(view));
    if (target?.kind !== 'view')
        throw Error('Reflow requires a view.');
    const profile = asString(target.record.profile);
    if (getProfile(profile)?.projection !== 'graph')
        throw Error('This view derives its arrangement from its data and projection settings.');
    let source = copySources(before), decoded = state.decoded;
    const set = (ref, path, value) => {
        const patches = patchProperty(decoded, ref, path, value);
        if (!patches.length)
            return;
        source = applySourcePatches(source, patches);
        decoded = state.materialize(decodeSources(source, { previous: decoded }));
        if (!decoded.syntaxValid)
            throw Error(decoded.diagnostics.map(diagnostic => diagnostic.message).join('; '));
    };
    for (const entry of records) {
        if (entry.kind !== 'appearance' || key(resolveReference(state.decoded.normalized, entry.file, entry.record.parent)?.ref ?? { file: '', id: '' }) !== key(view))
            continue;
        if (entry.record.position !== undefined)
            set(entry.ref, 'position', undefined);
        if (entry.record.pinned !== undefined)
            set(entry.ref, 'pinned', undefined);
        // Geometry is recalculated; semantic endpoint/port hints and routing
        // style stay authored. Only the old bend coordinates are discarded.
        if (asRecord(entry.record.route).via !== undefined)
            set(entry.ref, 'route.via', undefined);
    }
    const algorithm = effectiveAlgorithm ?? asString(getPath(resolveProperties(snapshot, view).values, 'layout.algorithm'));
    if (algorithm === 'manual') {
        set(view, 'layout.algorithm', automaticLayoutAlgorithm(profile));
    }
    return source.files.flatMap(file => {
        const previous = before.files.find(candidate => candidate.id === file.id);
        return file.text === previous.text ? [] : [{ file: file.id, base: previous.revision, start: 0, end: previous.text.length, text: file.text }];
    });
}
//# sourceMappingURL=layout-edit.js.map