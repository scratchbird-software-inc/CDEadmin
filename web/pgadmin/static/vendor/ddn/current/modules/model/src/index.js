export const isRecord = (value) => value !== null && typeof value === 'object' && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
export const asRecord = (value) => isRecord(value) ? value : {};
export const asArray = (value) => Array.isArray(value) ? value : [];
export const asString = (value, fallback = '') => typeof value === 'string' ? value : fallback;
export const recordRef = (file, record) => ({ file, id: asString(record.id) });
export function normalizedFiles(value) {
    if (!isRecord(value) || !Array.isArray(value.files))
        return [];
    return value.files.filter(x => isRecord(x) && typeof x.location === 'string' && isRecord(x.document));
}
const scheme = /^[a-z][a-z0-9+.-]*:/i;
const hierarchical = /^[a-z][a-z0-9+.-]*:\//i;
function urlPath(value) {
    const remainder = value.replace(scheme, '');
    return (remainder.startsWith('//') ? remainder.slice(2).replace(/^[^/?#]*/, '') : remainder).split(/[?#]/, 1)[0];
}
function checkUrlNamespace(path) {
    let depth = 0;
    for (const part of path.split('/').slice(path.startsWith('/') ? 1 : 0)) {
        // URL resolution recognizes encoded dots, but must not silently clamp an escape at the root.
        const dot = part.replace(/%2e/gi, '.');
        if (dot === '.')
            continue;
        if (dot === '..') {
            if (!depth)
                throw new Error('Location escapes selected file namespace');
            depth--;
        }
        else
            depth++;
    }
}
/** Canonical identity only: selecting or fetching a location remains the host's responsibility. */
export function normalizeLocation(value, fromFile = '') {
    if (typeof value !== 'string' || !value || typeof fromFile !== 'string' || /[\u0000-\u001f\u007f]/.test(value + fromFile))
        throw new Error('Location must be nonempty text without control characters');
    value = value.replaceAll('\\', '/');
    fromFile = fromFile.replaceAll('\\', '/');
    if (scheme.test(value) && !hierarchical.test(value))
        return value;
    if (hierarchical.test(value) || scheme.test(fromFile)) {
        if (!scheme.test(value) && !hierarchical.test(fromFile))
            throw new Error('Relative reference needs a hierarchical file location');
        const base = scheme.test(value) ? undefined : new URL(normalizeLocation(fromFile));
        const path = urlPath(value);
        const resolvedPath = scheme.test(value) || value.startsWith('/') || !base ? path
            : path ? base.pathname.slice(0, base.pathname.lastIndexOf('/') + 1) + path : base.pathname;
        checkUrlNamespace(resolvedPath);
        // URL() trims surrounding ASCII spaces; quoted location spaces are authored path data.
        const resolved = new URL(value.replaceAll(' ', '%20'), base);
        if (resolved.host && (scheme.test(value) || value.startsWith('//')) && !/^(?:[a-z][a-z0-9+.-]*:)?\/\/[^/?#]+/i.test(value))
            throw new Error('Hierarchical URL authority must be explicit');
        if (resolved.hostname)
            resolved.hostname = resolved.hostname.toLowerCase();
        return resolved.href;
    }
    const base = fromFile.includes('/') ? fromFile.slice(0, fromFile.lastIndexOf('/') + 1) : '';
    const parts = [];
    for (const part of (value.startsWith('/') ? value : base + value).split('/')) {
        if (!part || part === '.')
            continue;
        if (part === '..') {
            if (!parts.length)
                throw new Error('Location escapes selected file namespace');
            parts.pop();
        }
        else
            parts.push(part.normalize('NFC'));
    }
    if (!parts.length)
        throw new Error('Location must not be empty');
    return (value.startsWith('/') || base.startsWith('/') ? '/' : '') + parts.join('/');
}
const collections = [['definitions', 'definition'], ['views', 'view'], ['placements', 'placement'], ['appearances', 'appearance'], ['data', 'data'], ['sources', 'source'], ['assets', 'asset'], ['templates', 'template'], ['publications', 'publication']];
let recordScope;
/** Run a phase that adds, removes and renames no records of `bundle`.
 *  Inside it, record listing and reference resolution for that bundle use
 *  one lazily built index instead of rescanning every record per lookup. */
export function withRecordIndex(bundle, run) {
    const previous = recordScope;
    recordScope = { bundle };
    try {
        return run();
    }
    finally {
        recordScope = previous;
    }
}
function scopedRecords(bundle) {
    if (!recordScope || recordScope.bundle !== bundle)
        return undefined;
    return recordScope.records ??= collectRecords(bundle);
}
function scopedFile(bundle, file) {
    const records = scopedRecords(bundle);
    if (!records || !recordScope)
        return undefined;
    if (!recordScope.files) {
        const files = new Map();
        const add = (map, key, entry) => { const list = map.get(key); if (list)
            list.push(entry);
        else
            map.set(key, [entry]); };
        for (const entry of records) {
            let index = files.get(entry.file);
            if (!index)
                files.set(entry.file, index = { records: [], byId: new Map(), byName: new Map() });
            index.records.push(entry);
            if (typeof entry.record.id === 'string')
                add(index.byId, entry.record.id, entry);
            if (typeof entry.record.name === 'string')
                add(index.byName, entry.record.name.normalize('NFC'), entry);
        }
        recordScope.files = files;
    }
    return recordScope.files.get(file) ?? { records: [], byId: new Map(), byName: new Map() };
}
export function listRecords(bundle) {
    const scoped = scopedRecords(bundle);
    return scoped ? scoped.slice() : collectRecords(bundle);
}
function collectRecords(bundle) {
    const records = [];
    for (const { location: file, document } of normalizedFiles(bundle)) {
        const add = (record, kind) => {
            records.push({ file, kind, record, ref: recordRef(file, record) });
            for (const note of asArray(record.notes))
                if (isRecord(note))
                    records.push({ file, kind: 'note', record: note, ref: recordRef(file, note) });
        };
        if (isRecord(document.workarea))
            add(document.workarea, 'workarea');
        for (const [key, kind] of collections)
            for (const record of asArray(document[key]))
                if (isRecord(record))
                    add(record, kind);
    }
    return records;
}
export function resolveReference(bundle, fromFile, reference) {
    if (!isRecord(reference))
        return undefined;
    const file = asString(reference.file, fromFile);
    const id = asString(reference.id), name = asString(reference.name).normalize('NFC');
    if (!file || (!id && !name) || (reference.id !== undefined && !id) || (reference.name !== undefined && !name)
        || (reference.file !== undefined && typeof reference.file !== 'string'))
        return undefined;
    const indexed = scopedFile(bundle, file);
    const records = indexed ? indexed.records : listRecords(bundle).filter(x => x.file === file);
    const withId = (value) => indexed ? indexed.byId.get(value) ?? [] : records.filter(x => x.record.id === value);
    const byId = id ? withId(id) : [];
    const byName = name ? (indexed ? indexed.byName.get(name) ?? [] : records.filter(x => typeof x.record.name === 'string' && x.record.name.normalize('NFC') === name)) : [];
    if ((id && byId.length !== 1) || (name && byName.length !== 1))
        return undefined;
    if (id && name && byId[0] !== byName[0])
        return undefined;
    const target = id ? byId[0] : byName[0];
    if (!target?.ref.id || (!id && withId(target.ref.id).length !== 1))
        return undefined;
    return target;
}
export function findRecord(bundle, ref) {
    return resolveReference(bundle, ref.file, { file: ref.file, id: ref.id })?.record;
}
export function getPath(value, path) {
    let current = value;
    for (const key of safePath(path))
        current = isRecord(current) ? current[key] : undefined;
    return current;
}
export function safePath(path) {
    const parts = path.split('.');
    if (parts.some(x => !x || ['__proto__', 'constructor', 'prototype'].includes(x)))
        throw new Error('Unsafe or empty property path');
    return parts;
}
export function setPath(record, path, value) {
    const parts = safePath(path);
    let current = record;
    for (const key of parts.slice(0, -1)) {
        if (!isRecord(current[key]))
            current[key] = {};
        current = current[key];
    }
    const key = parts[parts.length - 1];
    if (value === undefined)
        delete current[key];
    else
        current[key] = value;
}
export function canonicalJson(value) {
    if (Array.isArray(value))
        return '[' + value.map(canonicalJson).join(',') + ']';
    if (isRecord(value))
        return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonicalJson(value[k])).join(',') + '}';
    return JSON.stringify(value) ?? 'null';
}
//# sourceMappingURL=index.js.map