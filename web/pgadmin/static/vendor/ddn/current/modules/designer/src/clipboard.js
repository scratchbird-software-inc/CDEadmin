import { decodeSources, encodeDefinition, quoteText } from '../../language/src/index.js';
import { listRecords } from '../../model/src/index.js';
/** Identity and lifecycle never travel with a copy: the pasted element is new and starts as a draft. */
const NOT_COPIED = ['id', 'category', 'acceptance', 'acceptance_history', 'design'];
export function clipRecord(record) {
    const copy = {};
    for (const [key, value] of Object.entries(record))
        if (!NOT_COPIED.includes(key) && value !== undefined)
            copy[key] = value;
    return copy;
}
/** DDN text for the system clipboard; it pastes into the source panel, a text file, or another designer. */
export function clipboardText(items) {
    return items.map(item => encodeDefinition({ ...item.record, ...(item.position ? { position: { x: item.position.x, y: item.position.y } } : {}) }).replace(/\n?$/, '\n')).join('');
}
/** Reads DDN element declarations copied as text (from another tab or a file). */
export function parseClipboardText(text) {
    const body = text.replace(/\r\n/g, '\n').replace(/^\n+|\n+$/g, '');
    if (!/^\s*element\b/.test(body))
        return [];
    const minimum = Math.min(...body.split('\n').filter(line => line.trim()).map(line => line.length - line.trimStart().length));
    const wrapped = 'view clipboard as "ddn@1"\n' + body.split('\n').map(line => '    ' + line.slice(minimum)).join('\n') + '\n';
    const decoded = decodeSources({ entry: 'clipboard.ddn', files: [{ id: 'clipboard.ddn', text: wrapped, revision: '0', encoding: 'utf-8', writable: true }] });
    if (decoded.diagnostics.some(d => d.severity === 'error'))
        return [];
    const all = listRecords(decoded.normalized);
    return all.filter(entry => entry.kind === 'definition' && entry.record.category !== 'relation' && !Array.isArray(entry.record.endpoints)).map(entry => {
        const appearance = all.find(other => other.kind === 'appearance' && other.record.target?.id === entry.ref.id);
        const position = appearance?.record.position;
        return { record: clipRecord(entry.record), ...(position && typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) };
    });
}
/** A name not yet used in the file: "Order", then "Order 2", "Order 3", … */
export function uniqueName(name, taken) {
    if (!taken.has(name))
        return name;
    // Identifier-like names (dotted, namespaced or snake_case) keep that shape: "model.api_2".
    const identifier = !/\s/.test(name) && /[._:]/.test(name), separator = identifier ? '_' : ' ';
    const base = name.replace(identifier ? /_\d+$/ : /\s+\d+$/, '');
    for (let index = 2;; index++)
        if (!taken.has(base + separator + index))
            return base + separator + index;
}
/** The declarations to append to a view: names made unique, positions moved by the offset. */
export function pasteRecords(items, taken, offset) {
    return clipboardText(items.map(item => {
        const record = { ...item.record };
        if (typeof record.name === 'string') {
            record.name = uniqueName(record.name, taken);
            taken.add(record.name);
        }
        return { record, ...(item.position ? { position: { x: Math.max(0, item.position.x + offset.x), y: Math.max(0, item.position.y + offset.y) } } : {}) };
    }));
}
/** RFC 4180 CSV: quoted fields, doubled quotes, CRLF or LF rows. The first row is the header. */
export function parseCsv(text) {
    const rows = [];
    let row = [], field = '', quoted = false;
    for (let index = 0; index < text.length; index++) {
        const character = text[index];
        if (quoted) {
            if (character === '"' && text[index + 1] === '"') {
                field += '"';
                index++;
            }
            else if (character === '"')
                quoted = false;
            else
                field += character;
        }
        else if (character === '"')
            quoted = true;
        else if (character === ',') {
            row.push(field);
            field = '';
        }
        else if (character === '\n' || character === '\r') {
            if (character === '\r' && text[index + 1] === '\n')
                index++;
            row.push(field);
            field = '';
            if (row.some(cell => cell !== ''))
                rows.push(row);
            row = [];
        }
        else
            field += character;
    }
    row.push(field);
    if (row.some(cell => cell !== ''))
        rows.push(row);
    const [header = [], ...body] = rows;
    if (!header.length)
        throw Error('The CSV file has no header row.');
    const used = new Set();
    const columns = header.map((label, index) => {
        let id = label.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'column_' + (index + 1);
        if (/^\d/.test(id))
            id = 'c_' + id;
        while (used.has(id))
            id += '_' + (index + 1);
        used.add(id);
        const numeric = body.length > 0 && body.every(cells => { const value = (cells[index] ?? '').trim(); return value === '' || Number.isFinite(Number(value)); });
        return { id, label: label.trim() || id, type: numeric ? 'number' : 'text' };
    });
    return { columns, rows: body.map(cells => columns.map((column, index) => { const value = (cells[index] ?? '').trim(); return value === '' ? null : column.type === 'number' ? Number(value) : value; })) };
}
export { quoteText };
//# sourceMappingURL=clipboard.js.map