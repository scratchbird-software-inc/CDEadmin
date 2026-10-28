export const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {};
export const array = (value) => Array.isArray(value) ? value : [];
export const str = (value, fallback = '') => typeof value === 'string' ? value : fallback;
export const num = (value, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
export function pathValue(value, path) { return path.split('.').reduce((v, key) => object(v)[key], value); }
export function refKey(ref) { return JSON.stringify([ref.file, ref.id]); }
export function records(snapshot) {
    const result = [];
    for (const raw of array(object(snapshot.normalized).files)) {
        const item = object(raw);
        const file = str(item.location);
        const document = object(item.document);
        if (document.workarea) {
            const record = object(document.workarea);
            result.push({ file, record, owner: 'workarea', ref: { file, id: str(record.id, str(record.name, 'workarea')) } });
        }
        for (const [plural, owner] of Object.entries({ definitions: 'definition', views: 'view', appearances: 'appearance', placements: 'placement', data: 'data', sources: 'source', assets: 'asset', templates: 'template', publications: 'publication' }))
            for (const rawRecord of array(document[plural])) {
                const record = object(rawRecord);
                result.push({ file, record, owner, ref: { file, id: str(record.id, str(record.name)) } });
            }
    }
    return result;
}
export function resolveRecord(all, reference, declaringFile) {
    const ref = object(reference);
    const file = str(ref.file, declaringFile);
    const id = str(ref.id);
    const name = str(ref.name);
    return all.find(item => item.file === file && (id ? item.ref.id === id : name ? item.record.name === name : false));
}
export function findRecord(snapshot, ref) { return records(snapshot).find(item => item.file === ref.file && item.ref.id === ref.id); }
export function titleOf(record) { return str(record.title) || str(record.name) || (str(record.role) === 'entity' || str(record.role) === 'table' ? '<table>' : `<${str(record.role, 'item')}>`); }
export function tableData(snapshot, item) {
    const all = records(snapshot);
    const definition = item.record;
    let data = object(definition.data), dataFile = item.file;
    if (data.source) {
        const source = resolveRecord(all, data.source, item.file);
        if (source?.owner === 'data') {
            data = source.record;
            dataFile = source.file;
        }
    }
    const displayed = (source) => {
        const columns = array(source.columns).map(object);
        const rows = array(source.rows).map(row => array(row).map((cell, index) => {
            if (columns[index]?.id !== 'domain')
                return cell;
            const domain = typeof cell === 'string' ? all.find(record => record.file === dataFile && (record.ref.id === cell || record.record.name === cell)) : resolveRecord(all, cell, dataFile);
            return domain?.record.role === 'domain' ? titleOf(domain.record) : cell;
        }));
        return { columns, rows };
    };
    if (Array.isArray(data.columns))
        return displayed(data);
    const captured = object(data.snapshot);
    if (Array.isArray(captured.columns))
        return displayed(captured);
    const members = array(definition.members).map(ref => resolveRecord(all, ref, item.file)).filter((value) => !!value);
    return { columns: ['field', 'type', 'domain', 'constraint', 'key', 'comment'].map(id => ({ id })), rows: members.map(member => {
            const content = object(member.record.content);
            const properties = object(member.record.properties);
            const domain = member.record.domain ?? content.domain;
            const domainRecord = resolveRecord(all, domain, member.file);
            return [titleOf(member.record), content.datatype ?? content.type ?? properties.datatype ?? properties.type ?? '', domainRecord ? titleOf(domainRecord.record) : str(domain), array(member.record.constraints).map(value => typeof value === 'string' ? value : JSON.stringify(value)).join(', '), content.key ?? properties.key ?? '', content.comment ?? member.record.description ?? ''];
        }) };
}
export function asJson(value) { return value; }
//# sourceMappingURL=model.js.map