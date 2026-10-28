import { array, object, pathValue, records, resolveRecord, refKey, str, num, titleOf } from './model.js';
import { decoratePaper } from './stationery.js';
export const colors = ['#337DB7', '#34976E', '#AC6538', '#8259B1', '#967421', '#347D8E', '#AC5573'];
export const valueAt = (record, key) => Object.hasOwn(record, key) ? record[key] : pathValue(record, key);
export const finite = (value) => typeof value === 'number' && Number.isFinite(value);
export const unique = (values) => [...new Set(values)];
export const sum = (values) => values.reduce((a, b) => a + b, 0);
export const interpolate = (a, b, fraction) => a * (1 - fraction) + b * fraction;
export function extent(values, zero = false) {
    const low = Math.min(...values, ...(zero || !values.length ? [0] : [])), high = Math.max(...values, ...(zero || !values.length ? [0] : []));
    if (low !== high)
        return [low, high];
    const delta = Math.max(.5, Math.abs(low) * .01);
    return [zero && low === 0 ? 0 : Math.max(-Number.MAX_VALUE, low - delta), zero && high === 0 ? 1 : Math.min(Number.MAX_VALUE, high + delta)];
}
export const scale = (domain, range) => {
    const magnitude = Math.max(Math.abs(domain[0]), Math.abs(domain[1]), 1), low = domain[0] / magnitude, span = domain[1] / magnitude - low;
    return (value) => range[0] + (value / magnitude - low) / span * (range[1] - range[0]);
};
export const numberLabel = (n) => Number(n.toPrecision(5)).toString();
export const box = (bounds, fill = '#fff', stroke = '#cbd5e1', extra = {}) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': 1, rx: 0, ry: 0, ...extra } });
export const ellipse = (x, y, r, fill = colors[0], extra = {}) => ({ kind: 'ellipse', bounds: { x: x - r, y: y - r, width: r * 2, height: r * 2 }, paint: { fill, stroke: '#fff', 'stroke-width': 1, ...extra } });
export const path = (d, stroke = '#64748b', fill = 'none', extra = {}) => ({ kind: 'path', d, paint: { fill, stroke, 'stroke-width': 1.5, ...extra } });
export const label = (text, x, y, size = 12, extra = {}) => ({ kind: 'text', runs: [{ text, x, y, fontKey: 'sans', style: { 'font-size': size, fill: '#243449', ...extra } }] });
export const pointsPath = (points, close = false) => points.length ? 'M' + points.map(p => `${p[0]},${p[1]}`).join('L') + (close ? 'Z' : '') : '';
export function boundsOf(points, padding = 0) { const xs = points.map(p => p[0]), ys = points.map(p => p[1]); const [x, right] = extent(xs), [y, bottom] = extent(ys); return { x: x - padding, y: y - padding, width: right - x + padding * 2, height: bottom - y + padding * 2 }; }
export function colorScale(value, domain) { const t = Math.max(0, Math.min(1, domain[0] === domain[1] ? .5 : scale(domain, [0, 1])(value))); return `rgb(${Math.round(240 - 189 * t)},${Math.round(245 - 120 * t)},${Math.round(250 - 67 * t)})`; }
export function arcPath(cx, cy, radius, start, end, inner = 0) {
    if (end - start >= Math.PI * 2 - 1e-8)
        end = start + Math.PI * 2 - 1e-8;
    const p = (r, a) => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
    return `M${p(radius, start)}A${radius},${radius} 0 ${end - start > Math.PI ? 1 : 0} 1 ${p(radius, end)}` + (inner > 0 ? `L${p(inner, end)}A${inner},${inner} 0 ${end - start > Math.PI ? 1 : 0} 0 ${p(inner, start)}Z` : `L${cx},${cy}Z`);
}
export class DataScene {
    snapshot;
    view;
    bounds;
    effective;
    options;
    all;
    result;
    settings;
    count = 0;
    allowTextOverride;
    extrusionDepths = new Map();
    constructor(snapshot, view, bounds, effective, options) {
        this.snapshot = snapshot;
        this.view = view;
        this.bounds = bounds;
        this.effective = effective;
        this.options = options;
        this.all = records(snapshot);
        this.settings = { ...object(pathValue(effective, 'projection.options')), ...object(pathValue(view.record, 'projection.options')) };
        this.result = { entries: [], bounds: { ...bounds }, diagnostics: [], unavailable: [] };
        const text = options.resolve?.(view.ref, { view: view.ref }).properties.find(property => property.path === 'text.color');
        this.allowTextOverride = !options.resolve || !!text && !text.origin.startsWith('standard:');
    }
    issue(message, code = 'DDN-DATA-PROJECTION', severity = 'error', target = this.view.ref) {
        this.result.diagnostics.push({ code, severity, message, target });
        if (severity === 'error')
            this.result.unavailable.push(`${code}:${refKey(target)}`);
    }
    add(name, bounds, primitives, source = this.view, contributors = [source.ref], description = '', paperSurface = false) {
        const validBounds = (value) => Object.values(value).every(finite) && value.width >= 0 && value.height >= 0;
        const invalid = !validBounds(bounds) || primitives.some(primitive => primitive.kind === 'path' ? /NaN|Infinity/.test(primitive.d) : primitive.kind === 'text' ? primitive.runs.some(run => !finite(run.x) || !finite(run.y)) : !validBounds(primitive.bounds));
        if (invalid) {
            this.issue('Projection calculations exceeded finite geometry bounds.', 'DDN-PROJECTION-RANGE', 'error', source.ref);
            return;
        }
        const occurrence = `data:${refKey(this.view.ref)}:${this.count++}`;
        const font = str(pathValue(this.effective, 'style.font'), 'sans'), sizeRatio = num(pathValue(this.effective, 'style.font_size'), 16) / 16, textColor = pathValue(this.effective, 'text.color');
        primitives = primitives.map(primitive => primitive.kind === 'text' ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, fontKey: font, style: { ...run.style, 'font-size': num(run.style['font-size'], 12) * sizeRatio, ...(typeof textColor === 'string' && (this.allowTextOverride || run.style.fill === '#243449') ? { fill: textColor } : {}) } })) } : primitive);
        for (const primitive of primitives)
            if (primitive.kind === 'text')
                for (const run of primitive.runs) {
                    const size = num(run.style['font-size'], 12), width = this.options.measure?.(run.text, size, font) ?? run.text.length * size * .6, anchor = run.style['text-anchor'], left = run.x - (anchor === 'middle' ? width / 2 : anchor === 'end' ? width : 0), top = run.y - size;
                    const x = Math.min(bounds.x, left), y = Math.min(bounds.y, top);
                    bounds = { x, y, width: Math.max(bounds.x + bounds.width, left + width) - x, height: Math.max(bounds.y + bounds.height, run.y + size * .25) - y };
                }
        const item = { occurrence, target: source.ref, view: this.view.ref, layer: 'content', bounds, transform: [1, 0, 0, 1, 0, 0], primitives, hitTargets: unique(contributors.map(refKey)).map((key, i) => ({ id: `${occurrence}:${i}`, target: JSON.parse(key) })).map(hit => ({ id: hit.id, target: { file: hit.target[0], id: hit.target[1] }, bounds })), accessible: { role: 'graphics-symbol', label: name, description }, evidence: 'current' };
        const resolved = paperSurface && this.options.resolve ? this.options.resolve(source.ref, { view: this.view.ref }) : undefined;
        const effective = resolved?.values ?? this.effective;
        const background = resolved?.properties.find(p => p.path === 'background.color');
        if (background && typeof background.value === 'string' && (!background.origin.startsWith('standard:') || background.origin === 'standard:paper')) {
            const outer = item.primitives.findIndex(p => p.kind === 'rect');
            if (outer >= 0)
                item.primitives = item.primitives.map((p, i) => i === outer && p.kind === 'rect' ? { ...p, paint: { ...p.paint, fill: background.value } } : p);
        }
        const entry = { item, definition: source, view: this.view, effective };
        const decorated = paperSurface ? decoratePaper(entry) : entry;
        this.result.entries.push(decorated);
        bounds = decorated.item.bounds;
        this.result.bounds = { ...this.result.bounds,
            width: Math.max(this.result.bounds.width, bounds.x + bounds.width - this.bounds.x),
            height: Math.max(this.result.bounds.height, bounds.y + bounds.height - this.bounds.y) };
    }
    finish() {
        if (!this.result.entries.length)
            this.add(this.result.diagnostics.length ? 'Projection needs valid data' : 'No records', this.bounds, [label(this.result.diagnostics[0]?.message ?? 'No records', this.bounds.x + 8, this.bounds.y + 24)]);
        if (this.result.unavailable.length)
            this.result.entries = this.result.entries.map(entry => ({ ...entry, item: { ...entry.item, evidence: 'partial' } }));
        return this.result;
    }
    /** Legend/caption entries belong to the view, never to measured records. */
    legend(items, x = this.bounds.x + 64, y = this.bounds.y + 18, vertical = false) {
        let left = x, top = y;
        const primitives = [];
        for (const item of items) {
            const width = this.measure(item.label, 11) + 32;
            if (!vertical && left > x && left + width > this.bounds.x + this.bounds.width - 12) {
                left = x;
                top += 20;
            }
            primitives.push(box({ x: left, y: top - 9, width: 10, height: 10 }, item.color, 'none'), label(item.label, left + 16, top, 11));
            if (vertical)
                top += 22;
            else
                left += width;
        }
        this.add('Legend', { x, y: y - 12, width: Math.max(0, left - x), height: top - y + 18 }, primitives);
    }
    caption(text) {
        const x = this.bounds.x + 16, y = Math.max(this.bounds.y + this.bounds.height - 10, ...this.result.entries.map(entry => entry.item.bounds.y + entry.item.bounds.height + 20));
        const width = Math.max(16, this.bounds.width - 32), lines = [];
        let current = '';
        for (const word of text.split(/\s+/)) {
            const next = current ? current + ' ' + word : word;
            if (current && this.measure(next, 11) > width) {
                lines.push(current);
                current = word;
            }
            else
                current = next;
        }
        if (current)
            lines.push(current);
        this.add('Chart explanation', { x, y: y - 12, width: 0, height: lines.length * 16 }, lines.map((line, i) => label(line, x, y + i * 16, 11, { fill: '#53657D' })), this.view, [this.view.ref], text);
    }
    intensity(domain, unit = '', x = this.bounds.x + 64, y = this.bounds.y + 18, ramp = (value) => colorScale(value, domain)) {
        const primitives = [];
        for (let i = 0; i < 20; i++)
            primitives.push(box({ x: x + i * 6, y: y - 10, width: 6, height: 10 }, ramp(interpolate(domain[0], domain[1], i / 19)), 'none'));
        primitives.push(label(`${numberLabel(domain[0])} → ${numberLabel(domain[1])}${unit ? ' ' + unit : ''}`, x + 130, y, 11));
        this.add('Intensity scale', { x, y: y - 12, width: 120, height: 16 }, primitives);
    }
    selection() {
        const selection = array(pathValue(this.view.record, 'selection.include'));
        return selection.map(ref => resolveRecord(this.all, ref, this.view.file)).filter((v) => !!v);
    }
    data() {
        const refs = this.settings.records === undefined ? array(pathValue(this.view.record, 'selection.include')) : Array.isArray(this.settings.records) ? this.settings.records : [this.settings.records];
        let rows = [];
        for (const ref of refs) {
            const source = resolveRecord(this.all, ref, this.view.file);
            if (!source) {
                this.issue('A selected record does not resolve.');
                continue;
            }
            let data = source.owner === 'data' ? source.record : object(source.record.data);
            if (data.source) {
                const target = resolveRecord(this.all, data.source, source.file);
                if (target?.owner === 'data')
                    data = target.record;
                else
                    this.issue('The record data binding does not resolve.', undefined, 'error', source.ref);
            }
            if (!Array.isArray(data.columns) && Array.isArray(object(data.snapshot).columns))
                data = object(data.snapshot);
            if (Array.isArray(data.columns)) {
                const columns = array(data.columns).map(object);
                for (const [row, values] of array(data.rows).entries())
                    rows.push({ values: Object.fromEntries(columns.map((column, index) => [str(column.id), array(values)[index] ?? null])), source, contributors: [source.ref], ordinal: rows.length, row });
            }
            else
                rows.push({ values: { ...source.record, ...object(pathValue(source.record, 'metadata.x_record')) }, source, contributors: [source.ref], ordinal: rows.length });
        }
        const count = rows.length;
        for (const filter of array(this.settings.filter).map(object))
            rows = rows.filter(d => filter.op === 'in' ? array(filter.value).some(v => Object.is(v, valueAt(d.values, str(filter.key)))) : Object.is(filter.value, valueAt(d.values, str(filter.key))));
        if (count && !rows.length)
            this.issue('Filtering removed every selected record.');
        const order = array(this.settings.order).map(object);
        rows.sort((a, b) => {
            for (const term of order) {
                const av = valueAt(a.values, str(term.key)), bv = valueAt(b.values, str(term.key));
                const diff = av === bv ? 0 : finite(av) && finite(bv) ? av - bv : String(av) < String(bv) ? -1 : 1;
                if (diff)
                    return term.direction === 'desc' ? -diff : diff;
            }
            return a.ordinal - b.ordinal;
        });
        if (rows.length > 10000) {
            this.issue('The projection exceeds the 10,000-record bound.');
            return [];
        }
        return rows;
    }
    wrap(text, width, size = 11) {
        const lines = [];
        let current = '';
        for (const segment of text.split(/(?<=[\s/-])/)) {
            if (current && this.measure(current + segment, size) > width) {
                lines.push(current.trimEnd());
                current = '';
            }
            for (const character of segment) {
                if (current && this.measure(current + character, size) > width) {
                    lines.push(current.trimEnd());
                    current = '';
                }
                current += character;
            }
        }
        if (current)
            lines.push(current.trimEnd());
        return lines;
    }
    measure(text, size = 12) { const actual = size * num(pathValue(this.effective, 'style.font_size'), 16) / 16; return this.options.measure?.(text, actual, str(pathValue(this.effective, 'style.font'), 'sans')) ?? text.length * actual * .6; }
}
export function mergedDatum(values, rows) { const first = rows[0]; return { ...first, values, contributors: rows.flatMap(row => row.contributors) }; }
export function quantile(values, p) {
    const sorted = [...values].sort((a, b) => a - b);
    if (!sorted.length)
        return NaN;
    const i = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * p)), low = Math.floor(i);
    return sorted[low] + (sorted[Math.ceil(i)] - sorted[low]) * (i - low);
}
export function numericDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value))
        return;
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed))
        return;
    if (value.length === 10 && new Date(parsed).toISOString().slice(0, 10) !== value)
        return;
    return parsed;
}
//# sourceMappingURL=data-common.js.map