import { allNodes, appendDeclaration, applySourcePatches, decodeSources, encodeDefinition, findNode, patchProperty, quoteText, serializeProperties } from '../../language/src/index.js';
import { listRecords, resolveReference, asString } from '../../model/src/index.js';
import { runtimeState } from '../../runtime/src/runtime.js';
import { canonical } from '../../execution/src/index.js';
const key = (ref) => ref.file + '\0' + ref.id;
const without = (value, keys) => Object.fromEntries(Object.entries(value).filter(([name]) => !keys.includes(name)));
const relativeFile = (from, target) => {
    const parent = from.split('/').slice(0, -1), parts = target.split('/');
    while (parent.length && parts.length && parent[0] === parts[0]) {
        parent.shift();
        parts.shift();
    }
    return [...parent.map(() => '..'), ...parts].join('/');
};
/** A local source transaction. Generated recipe content is made explicit only
 * inside its own block, using the existing dialect and preserving identities. */
export function mindmapSource(runtime, view) {
    const state = runtimeState(runtime), original = state.source;
    if (!original || !state.decoded)
        throw Error('Editable sources are unavailable.');
    let source = original, decoded = state.decoded;
    const used = new Map();
    for (const item of listRecords(decoded.normalized)) {
        const names = used.get(item.file) ?? new Set();
        names.add(item.ref.id);
        names.add(asString(item.record.name));
        used.set(item.file, names);
    }
    const unique = (stem, file = view.file) => { const names = used.get(file) ?? new Set(); let name = stem, serial = 2; while (names.has(name))
        name = stem + ' ' + serial++; names.add(name); used.set(file, names); return name; };
    const apply = (patches) => {
        source = applySourcePatches(source, patches);
        decoded = decodeSources(source, { previous: decoded });
        if (!decoded.syntaxValid)
            throw Error(decoded.diagnostics.map(item => item.message).join('\n'));
    };
    const record = (ref) => {
        const found = listRecords(decoded.normalized).find(item => key(item.ref) === key(ref));
        if (!found)
            throw Error('Mind-map source item is unavailable.');
        return found;
    };
    const append = (file, text, parent) => apply(appendDeclaration(decoded, file, text, parent));
    const set = (ref, path, value) => apply(patchProperty(decoded, ref, path, value));
    const reference = (ref) => { const found = record(ref); return (ref.file === view.file ? '' : quoteText(relativeFile(view.file, ref.file)) + '::') + quoteText(asString(found.record.name, ref.id)); };
    const materialize = () => {
        const viewNode = findNode(decoded, view);
        if (!viewNode)
            throw Error('Mind-map view source is unavailable.');
        const nodes = allNodes(decoded), root = nodes.find(node => node.kind === 'mindmaproot' && node.file === view.file && node.start === viewNode.start);
        if (!root)
            return;
        const previous = decoded, file = source.files.find(item => item.id === view.file);
        const owned = listRecords(previous.normalized).filter(item => item.file === view.file && (() => {
            const node = findNode(previous, item.ref);
            return !!node && node.start >= viewNode.start && node.end <= viewNode.end;
        })());
        if (owned.some(item => !['view', 'placement', 'definition', 'appearance', 'note'].includes(item.kind)) || owned.some(item => {
            const node = findNode(previous, item.ref);
            return item.kind === 'definition' && node?.generated && !['mindmaproot', 'branch'].includes(node.kind);
        }))
            throw Error('This mind-map recipe contains generated data that cannot be safely expanded. Edit that data through its owning editor first.');
        const definitions = owned.filter(item => item.kind === 'definition');
        const names = new Map(definitions.map(item => [key(item.ref), asString(item.record.name) || unique(item.ref.id === root.ref?.id ? 'Central topic' : item.record.category === 'relation' ? 'Branch' : 'Topic')]));
        const sourceValue = (value) => {
            if (Array.isArray(value))
                return value.map(sourceValue);
            if (!value || typeof value !== 'object')
                return value;
            const object = value;
            if (typeof object.file === 'string' && typeof object.id === 'string') {
                const target = listRecords(previous.normalized).find(item => item.file === object.file && item.ref.id === object.id);
                const name = names.get(object.file + '\0' + object.id) ?? target?.record.name;
                if (typeof name === 'string')
                    return { ...without(object, ['id']), file: relativeFile(view.file, object.file), name };
                return { ...object, file: relativeFile(view.file, object.file) };
            }
            return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, sourceValue(item)]));
        };
        const refText = (ref) => {
            const target = listRecords(previous.normalized).find(item => key(item.ref) === key(ref));
            if (!target)
                throw Error('A mind-map reference cannot be preserved.');
            return (ref.file === view.file ? '' : quoteText(relativeFile(view.file, ref.file)) + '::') + quoteText(names.get(key(ref)) ?? asString(target.record.name, ref.id));
        };
        const viewRecord = record(view).record, appearances = owned.filter(item => item.kind === 'appearance');
        const newline = previous.documents.find(doc => doc.file.id === view.file).newline;
        // Comments remain present in their original order; all note/draft/body
        // values are serialized from the model, including their own identities.
        const comments = file.text.slice(viewNode.start, viewNode.end).split(/\r?\n/).filter(line => line.trimStart().startsWith('//')).map(line => line.trimStart());
        const chunks = [comments.join('\n'), `view ${quoteText(asString(viewRecord.name))} as mindmap.basic@1\n    with\n${serializeProperties(sourceValue(without(viewRecord, ['name', 'profile'])), '        ')}`];
        for (const appearance of appearances) {
            const target = resolveReference(previous.normalized, appearance.file, appearance.record.target);
            if (!target)
                throw Error('A mind-map appearance cannot be preserved.');
            chunks.push('    use ' + refText(target.ref) + (appearance.record.name ? ' named ' + quoteText(asString(appearance.record.name)) : '') + '\n        with\n' + serializeProperties(sourceValue(without(appearance.record, ['name', 'target', 'parent'])), '            '));
        }
        for (const item of definitions) {
            const value = sourceValue({ ...item.record, name: names.get(key(item.ref)) });
            chunks.push(item.record.category === 'relation'
                ? `relation ${quoteText(asString(value.name))} as ${quoteText(asString(value.role))}\n    with\n${serializeProperties(without(value, ['name', 'role', 'category']), '        ')}`
                : encodeDefinition(value));
        }
        const text = chunks.filter(Boolean).map(chunk => chunk.replace(/\n+$/, '')).join('\n') + '\n';
        apply([{ file: file.id, base: file.revision, start: viewNode.start, end: viewNode.end, text: text.replace(/\n/g, newline) }]);
        const normalize = (value, root = false) => {
            if (Array.isArray(value))
                return value.map(item => normalize(item));
            if (!value || typeof value !== 'object')
                return value;
            const entries = Object.entries(value);
            const reference = 'file' in value && 'id' in value;
            return Object.fromEntries(entries.filter(([name]) => name !== 'name' || !root && !reference).map(([name, item]) => [name, normalize(item)]));
        };
        const current = new Map(listRecords(decoded.normalized).map(item => [key(item.ref), item]));
        for (const item of listRecords(previous.normalized)) {
            const next = current.get(key(item.ref));
            if (!next || canonical(normalize(item.record, true)) !== canonical(normalize(next.record, true)))
                throw Error('The compact mind map cannot be expanded without changing ' + asString(item.record.name, item.ref.id) + '. No changes were saved.');
        }
        // Generated IDs outside the edited block are session-local. Reject an
        // expansion if an authored ID reference to one would change on reload.
        const fresh = decodeSources(source), reloaded = new Map(listRecords(fresh.normalized).map(item => [key(item.ref), item]));
        const persistent = new Set([...owned.filter(item => item.kind !== 'placement').map(item => key(item.ref)), ...previous.references.filter(site => site.spelling === 'id' && site.target).map(site => key(site.target))]);
        for (const item of listRecords(previous.normalized).filter(item => persistent.has(key(item.ref)))) {
            const next = reloaded.get(key(item.ref));
            if (!next || canonical(normalize(item.record, true)) !== canonical(normalize(next.record, true)))
                throw Error('An authored identity reference cannot be preserved when expanding this recipe. No changes were saved.');
        }
    };
    const patches = () => original.files.flatMap(file => {
        const next = source.files.find(item => item.id === file.id);
        if (file.text === next.text)
            return [];
        let start = 0, end = file.text.length, nextEnd = next.text.length;
        while (start < end && start < nextEnd && file.text[start] === next.text[start])
            start++;
        while (end > start && nextEnd > start && file.text[end - 1] === next.text[nextEnd - 1]) {
            end--;
            nextEnd--;
        }
        return [{ file: file.id, base: file.revision, start, end, text: next.text.slice(start, nextEnd) }];
    });
    return { get source() { return source; }, get decoded() { return decoded; }, record, unique, reference, append, set, apply, materialize, patches };
}
//# sourceMappingURL=mindmap-source.js.map