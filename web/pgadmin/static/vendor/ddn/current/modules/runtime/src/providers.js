import { asArray, asRecord, asString, isRecord, listRecords, resolveReference } from '../../model/src/index.js';
import { canonical, clone } from '../../execution/src/index.js';
const identity = (ref) => ref.file + '\0' + ref.id;
function bindings(normalized, source) {
    return listRecords(normalized).flatMap(entry => {
        const data = entry.kind === 'data' ? entry.record : entry.kind === 'definition' ? asRecord(entry.record.data) : undefined;
        if (!data)
            return [];
        const target = resolveReference(normalized, entry.file, data.source);
        return target?.kind === 'source' && identity(target.ref) === identity(source) ? [{ entry, data }] : [];
    });
}
function columnsOf(schema) {
    const values = Array.isArray(schema) ? schema : asRecord(schema).columns;
    if (!Array.isArray(values) || !values.length || values.some(value => !isRecord(value) || typeof value.id !== 'string' || !value.id))
        throw Error('Provider schema requires nonempty column descriptors.');
    const columns = clone(values);
    if (new Set(columns.map(column => column.id)).size !== columns.length)
        throw Error('Provider column identities must be unique.');
    return columns;
}
function rowOf(row, columns) {
    if (Array.isArray(row)) {
        if (row.length > columns.length)
            throw Error('Provider row has more cells than its schema.');
        return columns.map((_, index) => clone(row[index] ?? null));
    }
    if (isRecord(row)) {
        if (Object.keys(row).some(key => !columns.some(column => column.id === key)))
            throw Error('Provider row contains an undeclared column.');
        return columns.map(column => clone(row[asString(column.id)] ?? null));
    }
    throw Error('Provider rows must be positional arrays or objects keyed by declared columns.');
}
function sourceKeys(targets, columns) {
    const keys = targets.map(({ data }) => asArray(data.key).map(value => asString(asRecord(data.mapping)[asString(value)], asString(value))));
    if (!keys[0]?.length)
        throw Error('Keyed updates require declared dataset key columns.');
    if (keys.some(value => canonical(value) !== canonical(keys[0])))
        throw Error('Datasets bound to one keyed source must agree on its source keys.');
    if (keys[0].some(key => !columns.some(column => column.id === key)))
        throw Error('A keyed update names an unavailable key column.');
    return keys[0];
}
function rowKey(row, columns, keys) {
    const values = keys.map(key => row[columns.findIndex(column => column.id === key)]);
    if (values.some(value => value === null || value === undefined || typeof value === 'object' || value === ''))
        throw Error('Provider keys must be nonempty scalar values.');
    return values.length === 1 ? String(values[0]) : canonical(values);
}
/** Applies to a private candidate only; callers publish the entire candidate after verification. */
export function applyProviderOverlays(normalized, overlays) {
    for (const overlay of overlays.values())
        for (const { data } of bindings(normalized, overlay.ref)) {
            const mapping = asRecord(data.mapping);
            if (Object.keys(mapping).length) {
                const columns = Array.isArray(data.columns) && data.columns.length ? clone(data.columns) : Object.keys(mapping).map(id => ({ id }));
                const indices = columns.map(column => overlay.columns.findIndex(source => source.id === asString(mapping[asString(column.id)], asString(column.id))));
                if (indices.some(index => index < 0))
                    throw Error('A dataset mapping names a missing provider column.');
                data.columns = columns;
                data.rows = overlay.rows.map(row => indices.map(index => clone(row[index] ?? null)));
            }
            else {
                data.columns = clone(overlay.columns);
                data.rows = clone(overlay.rows);
            }
            data.revision = overlay.revision;
        }
}
export async function stageProviderChanges(normalized, prior, dataRevisions, changes, context) {
    const overlays = new Map(prior), revisions = { ...dataRevisions };
    const changed = new Set();
    applyProviderOverlays(normalized, overlays);
    for (const change of changes) {
        await context.checkpoint(1);
        const matches = listRecords(normalized).filter(entry => entry.kind === 'source' && (entry.record.name === change.source || entry.record.id === change.source || entry.record.channel === change.source || entry.file + '::' + entry.record.name === change.source || entry.file + '::' + entry.ref.id === change.source));
        if (matches.length !== 1)
            throw Error('Unknown or ambiguous provider source: ' + change.source);
        const producer = matches[0], id = identity(producer.ref), previous = overlays.get(id), revisionKey = previous?.revisionKey ?? change.source;
        if (changed.has(id))
            throw Error('A coherent update contains one change per provider source.');
        changed.add(id);
        if (!change.next || change.next === (previous?.revision ?? revisions[revisionKey]))
            throw Error('Provider update must advance its revision.');
        const targets = bindings(normalized, producer.ref);
        if (!targets.length)
            throw Error('No dataset is bound to this provider source.');
        let columns, rows;
        if (change.kind === 'replace') {
            columns = columnsOf(change.schema);
            rows = [];
            for (const row of change.rows) {
                await context.checkpoint(1);
                rows.push(rowOf(row, columns));
            }
        }
        else {
            if (change.base !== (previous?.revision ?? revisions[revisionKey]))
                throw Error('Keyed update base does not match the provider data revision.');
            if (!previous && Object.keys(asRecord(targets[0].data.mapping)).length)
                throw Error('A mapped keyed source requires an initial provider replacement.');
            columns = previous?.columns ?? columnsOf(targets[0].data.columns ?? []);
            const keys = sourceKeys(targets, columns), existing = previous?.rows ?? asArray(targets[0].data.rows).map(row => rowOf(row, columns));
            const keyed = new Map();
            for (const row of existing) {
                const key = rowKey(row, columns, keys);
                if (keyed.has(key))
                    throw Error('Provider rows contain duplicate keys.');
                keyed.set(key, clone(row));
            }
            const operated = new Set();
            for (const operation of change.operations) {
                await context.checkpoint(1);
                if (operated.has(operation.key))
                    throw Error('A keyed batch repeats an operation key.');
                operated.add(operation.key);
                if (operation.op === 'delete')
                    keyed.delete(operation.key);
                else {
                    const row = rowOf(operation.row, columns);
                    if (rowKey(row, columns, keys) !== operation.key)
                        throw Error('Upsert key differs from its row key.');
                    keyed.set(operation.key, row);
                }
            }
            rows = [...keyed.values()];
        }
        if (targets.some(({ data }) => asArray(data.key).length)) {
            const keys = sourceKeys(targets, columns), seen = new Set();
            for (const row of rows) {
                const key = rowKey(row, columns, keys);
                if (seen.has(key))
                    throw Error('Provider rows contain duplicate keys.');
                seen.add(key);
            }
        }
        overlays.set(id, { ref: producer.ref, revisionKey, revision: change.next, columns: clone(columns), rows });
        revisions[revisionKey] = change.next;
    }
    applyProviderOverlays(normalized, overlays);
    context.check();
    return { overlays, revisions };
}
//# sourceMappingURL=providers.js.map