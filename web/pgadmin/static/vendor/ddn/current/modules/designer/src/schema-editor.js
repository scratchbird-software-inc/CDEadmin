import { codex, validateSchema } from '../../profiles/src/schema-core.js';
import { numberField, syncNumberField } from './dialogs.js';
import { choiceField, choicePreview } from '../../viewer/src/choice-field.js';
import { notifyLiveSettings } from './live-settings.js';
export function schemaNode(id) {
    const seen = new Set();
    while (id !== undefined && !seen.has(id)) {
        seen.add(id);
        const node = codex.nodes[id];
        if (!node || typeof node === 'boolean')
            return {};
        if (node.ref === undefined)
            return node;
        id = node.ref;
    }
    return {};
}
export function childSchema(id, field) {
    return schemaNode(id).properties?.[field];
}
const isObject = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
const matches = (schema, value) => {
    if (schema.enum)
        return schema.enum.some(v => JSON.stringify(v) === JSON.stringify(value));
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    return types.some(t => t === undefined || t === 'array' && Array.isArray(value) || t === 'object' && isObject(value) || t === 'null' && value === null || t === 'integer' && typeof value === 'number' && Number.isInteger(value) || t === typeof value);
};
/** Schema-driven controls keep omission distinct from an authored empty value. */
export function createFieldEditor(parent, id, value, refs, label, depth = 0, forcedType) {
    if (id === undefined || Object.keys(schemaNode(id)).length === 0)
        id = codex.roots.json_value;
    const document = parent.ownerDocument, schema = schemaNode(id);
    const button = (text, fn) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', () => { fn(); notifyLiveSettings(parent); }); return b; };
    const input = (type, value) => { const e = document.createElement('input'); e.type = type; e.value = value; e.setAttribute('aria-label', label); parent.append(e); return e; };
    if (depth > 12) {
        const retained = document.createElement('p');
        retained.textContent = 'Deeply nested value retained. Use the DDN source editor to change this section.';
        parent.append(retained);
        return { read: () => value ?? null };
    }
    if (Array.isArray(schema.type) && !forcedType) {
        const types = schema.type, select = document.createElement('select'), body = document.createElement('div');
        select.setAttribute('aria-label', label + ' scalar type');
        for (const type of types) {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            select.append(option);
        }
        select.value = types.find(type => matches({ type }, value)) ?? types[0];
        parent.append(select, body);
        let editor = createFieldEditor(body, id, value, refs, label, depth + 1, select.value);
        select.addEventListener('change', () => {
            let previous;
            try {
                previous = editor.read();
            }
            catch {
                previous = undefined;
            }
            body.replaceChildren();
            editor = createFieldEditor(body, id, matches({ type: select.value }, previous) ? previous : undefined, refs, label, depth + 1, select.value);
        });
        return { read: () => editor.read() };
    }
    if (schema.properties?.file !== undefined && schema.properties?.id !== undefined) {
        const select = document.createElement('select');
        select.setAttribute('aria-label', label + ' reference');
        const choices = [...refs];
        if (isObject(value) && typeof value.file === 'string' && typeof value.id === 'string' && !choices.some(c => c.ref.file === value.file && c.ref.id === value.id))
            choices.push({ ref: { file: value.file, id: value.id }, label: `${value.file} :: ${value.id} (unresolved)` });
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'Choose a reference';
        select.append(empty);
        choices.forEach((choice, i) => { const option = document.createElement('option'); option.value = String(i); option.textContent = choice.label; select.append(option); });
        const found = choices.findIndex(c => isObject(value) && c.ref.file === value.file && c.ref.id === value.id);
        select.value = found < 0 ? '' : String(found);
        parent.append(select);
        return { read: () => {
                const choice = choices[Number(select.value)];
                if (select.value === '' || !choice)
                    throw Error('Choose a reference for ' + label);
                return { ...choice.ref };
            } };
    }
    const variants = schema.oneOf ?? schema.anyOf;
    if (variants?.length) {
        const select = document.createElement('select'), body = document.createElement('div');
        select.setAttribute('aria-label', label + ' value type');
        variants.forEach((variant, i) => { const node = schemaNode(variant), option = document.createElement('option'); option.value = String(i); option.textContent = node.enum ? node.enum.map(String).join(' / ') : Array.isArray(node.type) ? node.type.join(' / ') : node.type ?? 'value'; select.append(option); });
        const exact = value === undefined ? -1 : variants.findIndex(v => validateSchema(v, value).length === 0);
        const selected = exact >= 0 ? exact : Math.max(0, variants.findIndex(v => matches(schemaNode(v), value)));
        select.value = String(selected);
        parent.append(select, body);
        let editor = createFieldEditor(body, variants[selected], value, refs, label, depth + 1);
        select.addEventListener('change', () => {
            let previous;
            try {
                previous = editor.read();
            }
            catch {
                previous = undefined;
            }
            body.replaceChildren();
            const next = variants[Number(select.value)];
            editor = createFieldEditor(body, next, matches(schemaNode(next), previous) ? previous : undefined, refs, label, depth + 1);
        });
        return { read: () => editor.read() };
    }
    if (schema.enum || Object.hasOwn(schema, 'const')) {
        const values = [...(schema.enum ?? [schema.const])];
        if (value !== undefined && !values.some(v => JSON.stringify(v) === JSON.stringify(value)))
            values.push(value);
        const index = values.findIndex(v => JSON.stringify(v) === JSON.stringify(value));
        const select = choiceField(parent, label, values.map((v, i) => ({ value: String(i), label: String(v), preview: document => choicePreview(document, String(v), label) })), String(Math.max(0, index)));
        return { read: () => values[Number(select.value)] };
    }
    const type = forcedType ?? (Array.isArray(schema.type) ? schema.type.find(t => matches({ type: t }, value)) ?? schema.type[0] : schema.type ?? (Array.isArray(value) ? 'array' : isObject(value) ? 'object' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'string'));
    if (type === 'object') {
        const initial = isObject(value) ? value : {}, fields = new Map();
        const addField = (key, child, initialValue) => {
            const group = document.createElement('details'), summary = document.createElement('summary'), enabled = document.createElement('input'), body = document.createElement('div');
            enabled.type = 'checkbox';
            enabled.checked = initialValue !== undefined;
            enabled.setAttribute('aria-label', 'Set ' + label + '.' + key);
            summary.append(enabled, document.createTextNode(key + (schema.required?.includes(key) ? ' (required when complete)' : '')));
            group.append(summary, body);
            parent.append(group);
            const state = { enabled };
            fields.set(key, state);
            const render = () => {
                body.replaceChildren();
                if (enabled.checked) {
                    state.editor = createFieldEditor(body, child, initialValue, refs, label + '.' + key, depth + 1);
                    group.open = true;
                }
                else {
                    delete state.editor;
                    group.open = false;
                }
            };
            if (enabled.checked)
                state.editor = createFieldEditor(body, child, initialValue, refs, label + '.' + key, depth + 1);
            enabled.addEventListener('change', render);
        };
        for (const key of new Set([...Object.keys(schema.properties ?? {}), ...Object.keys(initial)]))
            addField(key, schema.properties?.[key] ?? (typeof schema.additionalProperties === 'number' ? schema.additionalProperties : undefined), initial[key]);
        if (schema.additionalProperties !== false) {
            const row = document.createElement('div'), name = document.createElement('input');
            name.placeholder = 'New field name';
            name.setAttribute('aria-label', label + ' new field name');
            row.append(name, button('Add field', () => {
                const key = name.value.trim();
                if (!key || fields.has(key) || ['__proto__', 'constructor', 'prototype'].includes(key))
                    return;
                addField(key, typeof schema.additionalProperties === 'number' ? schema.additionalProperties : undefined, '');
                name.value = '';
            }));
            parent.append(row);
        }
        return { read: () => {
                const result = {};
                for (const [key, state] of fields)
                    if (state.enabled.checked && state.editor)
                        result[key] = state.editor.read();
                return result;
            } };
    }
    if (type === 'array') {
        const list = document.createElement('div');
        parent.append(list);
        const rows = [];
        const add = (initial) => {
            const element = document.createElement('fieldset'), legend = document.createElement('legend'), body = document.createElement('div');
            legend.textContent = 'Item';
            element.append(legend, body);
            const row = { element, editor: createFieldEditor(body, schema.items, initial, refs, label + ' item', depth + 1) };
            const move = (offset) => {
                const index = rows.indexOf(row), next = index + offset;
                if (next < 0 || next >= rows.length)
                    return;
                rows.splice(index, 1);
                rows.splice(next, 0, row);
                list.replaceChildren(...rows.map(r => r.element));
            };
            element.append(button('Move up', () => move(-1)), button('Move down', () => move(1)), button('Remove item', () => { rows.splice(rows.indexOf(row), 1); element.remove(); }));
            rows.push(row);
            list.append(element);
        };
        if (Array.isArray(value))
            value.forEach(add);
        parent.append(button('Add item', () => add(undefined)));
        return { read: () => rows.map(row => row.editor.read()) };
    }
    if (type === 'boolean') {
        const e = input('checkbox', '');
        e.checked = value === true;
        return { read: () => e.checked };
    }
    if (type === 'null') {
        const text = document.createElement('span');
        text.textContent = 'Empty (null)';
        parent.append(text);
        return { read: () => null };
    }
    if (type === 'number' || type === 'integer') {
        // Slider bounds are convenient editing ranges, not additional schema limits.
        const current = typeof value === 'number' && Number.isFinite(value) ? value : 0;
        const min = typeof schema.minimum === 'number' ? schema.minimum : Math.min(-100, current * 2);
        const max = typeof schema.maximum === 'number' ? schema.maximum : Math.max(100, current * 2);
        const span = max - min, step = type === 'integer' ? 1 : span <= 1 ? .01 : span <= 100 ? .1 : 1;
        const e = Number.isFinite(min) && Number.isFinite(max) && max > min
            ? numberField(parent, label, typeof value === 'number' ? value : '', { min, max, step })
            : input('number', typeof value === 'number' ? String(value) : '');
        e.step = type === 'integer' ? '1' : 'any';
        if (schema.minimum !== undefined)
            e.min = String(schema.minimum);
        else
            e.removeAttribute('min');
        if (schema.maximum !== undefined)
            e.max = String(schema.maximum);
        else
            e.removeAttribute('max');
        syncNumberField(e);
        return { read: () => {
                const n = Number(e.value);
                if (e.value.trim() === '' || !Number.isFinite(n) || !e.checkValidity() || type === 'integer' && !Number.isInteger(n))
                    throw Error(label + ' needs a finite ' + type);
                return n;
            } };
    }
    const e = document.createElement('textarea');
    e.value = value === undefined || value === null ? '' : String(value);
    e.rows = 2;
    e.style.minHeight = '3em';
    e.setAttribute('aria-label', label);
    parent.append(e);
    return { read: () => e.value };
}
//# sourceMappingURL=schema-editor.js.map