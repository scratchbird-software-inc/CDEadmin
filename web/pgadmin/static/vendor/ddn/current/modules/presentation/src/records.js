import { array, object, pathValue, records, resolveRecord, str, tableData, titleOf } from './model.js';
/** Field-key table projection. References stay qualified; missing cells stay distinct from null. */
export function recordTableData(snapshot, view) {
    const all = records(snapshot), options = object(pathValue(view.record, 'projection.options'));
    const references = Array.isArray(options.records) ? options.records : options.records ? [options.records] : [];
    let descriptors = [];
    let values = [];
    const diagnostics = [];
    const issue = (message) => diagnostics.push({ code: 'table-projection', severity: 'warning', message, target: view.ref });
    for (const reference of references) {
        const target = resolveRecord(all, reference, view.file);
        if (!target) {
            issue('A table record reference is unavailable.');
            continue;
        }
        if (target.owner === 'view') {
            issue('A record table cannot use another view as a scalar record.');
            continue;
        }
        let data = target.owner === 'data' ? target.record : object(target.record.data);
        if (data.source) {
            const bound = resolveRecord(all, data.source, target.file);
            if (bound?.owner === 'data')
                data = bound.record;
        }
        if (!Array.isArray(data.columns) && Array.isArray(object(data.snapshot).columns))
            data = object(data.snapshot);
        if (Array.isArray(data.columns)) {
            const columns = array(data.columns).map(object);
            if (!descriptors.length)
                descriptors = columns;
            values.push(...array(data.rows).map(row => ({ record: Object.fromEntries(columns.map((column, index) => [str(column.id), array(row)[index] ?? null])), target: target.ref })));
        }
        else
            values.push({ record: target.record, target: target.ref });
    }
    let columns;
    if (Array.isArray(options.columns) && options.columns.length) {
        columns = options.columns.map(value => {
            const descriptor = object(value);
            if (descriptor.file || descriptor.name && !descriptor.id) {
                const field = resolveRecord(all, descriptor, view.file);
                if (!field) {
                    issue('A table column reference is unavailable.');
                    return { id: str(descriptor.id, str(descriptor.name)) };
                }
                return { id: str(field.record.name, field.ref.id), path: str(pathValue(field.record, 'content.path'), str(field.record.name)), label: titleOf(field.record) };
            }
            return { ...descriptor };
        });
    }
    else if (descriptors.length)
        columns = descriptors;
    else
        columns = [...new Set(values.flatMap(({ record }) => Object.keys(record).filter(key => record[key] === null || typeof record[key] !== 'object')))].map(id => ({ id }));
    if (typeof options.columns === 'number')
        columns = columns.slice(0, Math.max(0, Math.floor(options.columns)));
    columns = columns.filter(column => column.visibility !== 'hidden' && column.visibility !== 'on_demand');
    const read = (record, key) => Object.hasOwn(record, key) ? record[key] : pathValue(record, key);
    for (const filter of array(options.filter).map(object))
        values = values.filter(({ record }) => {
            const actual = read(record, str(filter.key));
            return filter.op === 'in' ? array(filter.value).some(value => Object.is(value, actual)) : Object.is(filter.value, actual);
        });
    const order = array(options.order).map(object);
    if (order.length)
        values = values.map((value, index) => ({ ...value, index })).sort((a, b) => {
            for (const term of order) {
                const left = read(a.record, str(term.key)), right = read(b.record, str(term.key));
                let compared = 0;
                if (left === right)
                    continue;
                if (left === undefined || left === null)
                    compared = -1;
                else if (right === undefined || right === null)
                    compared = 1;
                else if (typeof left === 'number' && typeof right === 'number')
                    compared = left - right;
                else
                    compared = String(left) < String(right) ? -1 : 1;
                if (compared)
                    return term.direction === 'desc' ? -compared : compared;
            }
            return a.index - b.index;
        });
    const missing = str(options.missing, 'error'), rows = [], targets = [];
    for (const value of values) {
        const row = columns.map(column => read(value.record, str(column.path, str(column.id))));
        if (row.some(cell => cell === undefined)) {
            if (missing === 'skip')
                continue;
            if (missing === 'error')
                issue('A record is missing a declared table column.');
        }
        rows.push(row.map(cell => cell ?? null));
        targets.push(value.target);
    }
    if (!columns.length)
        issue('Choose table columns to display records.');
    return { columns, rows, targets, diagnostics };
}
//# sourceMappingURL=records.js.map