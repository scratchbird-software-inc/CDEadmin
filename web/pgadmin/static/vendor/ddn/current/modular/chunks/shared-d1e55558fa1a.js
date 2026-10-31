/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-d1e55558fa1a","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-4788c79b979a","shared-9019e1da906d"],"modules":[{"id":"presentation/src/data-adapter.js","bytes":1122,"sha256":"fee05bc3a8e58313e893ba3ff2f76c32a827dd9a39e574f363ff91dfd14da3c0","dependencies":["presentation/src/data-common.js","presentation/src/model.js"]},{"id":"presentation/src/data-catalogue.js","bytes":1273,"sha256":"87d04bdb26b48ccd781492deac8550e8d3548a355e45c19bb5e25fb67cd035a8","dependencies":[]},{"id":"presentation/src/data-common.js","bytes":17384,"sha256":"44365872904e8be827a58a3105f3102e1e98ff25f8d43b3e60b8c1e6d562ea88","dependencies":["presentation/src/model.js","presentation/src/stationery.js"]}],"hash":"ec2d45b6021f6b79f3fd622675f59a7f2d3c55aea1ecf67a5c87f60aa48d7fc9"},{"presentation/src/data-adapter.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createDataProjector = createDataProjector;
const data_common_js_1 = require("presentation/src/data-common.js");
const model_js_1 = require("presentation/src/model.js");
function createDataProjector(profiles, draw, finish) {
    return (snapshot, view, bounds, effective, options = {}) => {
        const profile = (0, model_js_1.str)(view.record.profile);
        if (!profiles.includes(profile))
            return;
        const settings = { ...(0, model_js_1.object)((0, model_js_1.pathValue)(effective, 'projection.options')), ...(0, model_js_1.object)((0, model_js_1.pathValue)(view.record, 'projection.options')) };
        const allocated = { ...bounds, width: (0, model_js_1.num)(settings.width, bounds.width), height: (0, model_js_1.num)(settings.height, bounds.height) };
        const scene = new data_common_js_1.DataScene(snapshot, view, allocated, effective, options);
        draw(scene, options.geography);
        const result = scene.finish();
        return finish ? finish(result, settings, scene) : result;
    };
}

},
"presentation/src/data-catalogue.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.dataProfileIds = exports.surfaceProfileIds = exports.geographyProfileIds = exports.chartProfileIds = void 0;
exports.chartProfileIds = Object.freeze(['basic', 'radar', 'funnel', 'quality', 'gauge', 'candlestick', 'treemap', 'sankey', 'histogram', 'density', 'qq', 'quantiledot', 'dotplot', 'boxplot', 'violin', 'beeswarm', 'topk', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble', 'heatmap', 'densityheatmap', 'calendar', 'parallelcoords', 'wordcloud', 'arc', 'force', 'edgebundle'].map(name => `chart.${name}@1`));
exports.geographyProfileIds = Object.freeze(['choropleth', 'symbols', 'outline'].map(name => `geo.${name}@1`));
exports.surfaceProfileIds = Object.freeze([
    ...['raci', 'crud', 'relations', 'heatmap', 'bcg', 'ansoff', 'tows', 'storymap'].map(name => `matrix.${name}@1`),
    ...['basic', 'composed', 'journey', 'pyramid', 'venn'].map(name => `panels.${name}@1`),
    ...['bmc', 'lean', 'pest', 'pestle', 'porter5', 'empathy', 'scorecard'].map(name => `canvas.${name}@1`),
    'timeline.basic@1', 'decision.rules@1'
]);
exports.dataProfileIds = Object.freeze([...exports.chartProfileIds, ...exports.surfaceProfileIds, ...exports.geographyProfileIds]);

},
"presentation/src/data-common.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DataScene = exports.pointsPath = exports.label = exports.path = exports.ellipse = exports.box = exports.numberLabel = exports.scale = exports.interpolate = exports.sum = exports.unique = exports.finite = exports.valueAt = exports.colors = void 0;
exports.extent = extent;
exports.boundsOf = boundsOf;
exports.colorScale = colorScale;
exports.arcPath = arcPath;
exports.mergedDatum = mergedDatum;
exports.quantile = quantile;
exports.numericDate = numericDate;
const model_js_1 = require("presentation/src/model.js");
const stationery_js_1 = require("presentation/src/stationery.js");
exports.colors = ['#337DB7', '#34976E', '#AC6538', '#8259B1', '#967421', '#347D8E', '#AC5573'];
const valueAt = (record, key) => Object.hasOwn(record, key) ? record[key] : (0, model_js_1.pathValue)(record, key);
exports.valueAt = valueAt;
const finite = (value) => typeof value === 'number' && Number.isFinite(value);
exports.finite = finite;
const unique = (values) => [...new Set(values)];
exports.unique = unique;
const sum = (values) => values.reduce((a, b) => a + b, 0);
exports.sum = sum;
const interpolate = (a, b, fraction) => a * (1 - fraction) + b * fraction;
exports.interpolate = interpolate;
function extent(values, zero = false) {
    const low = Math.min(...values, ...(zero || !values.length ? [0] : [])), high = Math.max(...values, ...(zero || !values.length ? [0] : []));
    if (low !== high)
        return [low, high];
    const delta = Math.max(.5, Math.abs(low) * .01);
    return [zero && low === 0 ? 0 : Math.max(-Number.MAX_VALUE, low - delta), zero && high === 0 ? 1 : Math.min(Number.MAX_VALUE, high + delta)];
}
const scale = (domain, range) => {
    const magnitude = Math.max(Math.abs(domain[0]), Math.abs(domain[1]), 1), low = domain[0] / magnitude, span = domain[1] / magnitude - low;
    return (value) => range[0] + (value / magnitude - low) / span * (range[1] - range[0]);
};
exports.scale = scale;
const numberLabel = (n) => Number(n.toPrecision(5)).toString();
exports.numberLabel = numberLabel;
const box = (bounds, fill = '#fff', stroke = '#cbd5e1', extra = {}) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': 1, rx: 0, ry: 0, ...extra } });
exports.box = box;
const ellipse = (x, y, r, fill = exports.colors[0], extra = {}) => ({ kind: 'ellipse', bounds: { x: x - r, y: y - r, width: r * 2, height: r * 2 }, paint: { fill, stroke: '#fff', 'stroke-width': 1, ...extra } });
exports.ellipse = ellipse;
const path = (d, stroke = '#64748b', fill = 'none', extra = {}) => ({ kind: 'path', d, paint: { fill, stroke, 'stroke-width': 1.5, ...extra } });
exports.path = path;
const label = (text, x, y, size = 12, extra = {}) => ({ kind: 'text', runs: [{ text, x, y, fontKey: 'sans', style: { 'font-size': size, fill: '#243449', ...extra } }] });
exports.label = label;
const pointsPath = (points, close = false) => points.length ? 'M' + points.map(p => `${p[0]},${p[1]}`).join('L') + (close ? 'Z' : '') : '';
exports.pointsPath = pointsPath;
function boundsOf(points, padding = 0) { const xs = points.map(p => p[0]), ys = points.map(p => p[1]); const [x, right] = extent(xs), [y, bottom] = extent(ys); return { x: x - padding, y: y - padding, width: right - x + padding * 2, height: bottom - y + padding * 2 }; }
function colorScale(value, domain) { const t = Math.max(0, Math.min(1, domain[0] === domain[1] ? .5 : (0, exports.scale)(domain, [0, 1])(value))); return `rgb(${Math.round(240 - 189 * t)},${Math.round(245 - 120 * t)},${Math.round(250 - 67 * t)})`; }
function arcPath(cx, cy, radius, start, end, inner = 0) {
    if (end - start >= Math.PI * 2 - 1e-8)
        end = start + Math.PI * 2 - 1e-8;
    const p = (r, a) => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
    return `M${p(radius, start)}A${radius},${radius} 0 ${end - start > Math.PI ? 1 : 0} 1 ${p(radius, end)}` + (inner > 0 ? `L${p(inner, end)}A${inner},${inner} 0 ${end - start > Math.PI ? 1 : 0} 0 ${p(inner, start)}Z` : `L${cx},${cy}Z`);
}
class DataScene {
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
        this.all = (0, model_js_1.records)(snapshot);
        this.settings = { ...(0, model_js_1.object)((0, model_js_1.pathValue)(effective, 'projection.options')), ...(0, model_js_1.object)((0, model_js_1.pathValue)(view.record, 'projection.options')) };
        this.result = { entries: [], bounds: { ...bounds }, diagnostics: [], unavailable: [] };
        const text = options.resolve?.(view.ref, { view: view.ref }).properties.find(property => property.path === 'text.color');
        this.allowTextOverride = !options.resolve || !!text && !text.origin.startsWith('standard:');
    }
    issue(message, code = 'DDN-DATA-PROJECTION', severity = 'error', target = this.view.ref) {
        this.result.diagnostics.push({ code, severity, message, target });
        if (severity === 'error')
            this.result.unavailable.push(`${code}:${(0, model_js_1.refKey)(target)}`);
    }
    add(name, bounds, primitives, source = this.view, contributors = [source.ref], description = '', paperSurface = false) {
        const validBounds = (value) => Object.values(value).every(exports.finite) && value.width >= 0 && value.height >= 0;
        const invalid = !validBounds(bounds) || primitives.some(primitive => primitive.kind === 'path' ? /NaN|Infinity/.test(primitive.d) : primitive.kind === 'text' ? primitive.runs.some(run => !(0, exports.finite)(run.x) || !(0, exports.finite)(run.y)) : !validBounds(primitive.bounds));
        if (invalid) {
            this.issue('Projection calculations exceeded finite geometry bounds.', 'DDN-PROJECTION-RANGE', 'error', source.ref);
            return;
        }
        const occurrence = `data:${(0, model_js_1.refKey)(this.view.ref)}:${this.count++}`;
        const font = (0, model_js_1.str)((0, model_js_1.pathValue)(this.effective, 'style.font'), 'sans'), sizeRatio = (0, model_js_1.num)((0, model_js_1.pathValue)(this.effective, 'style.font_size'), 16) / 16, textColor = (0, model_js_1.pathValue)(this.effective, 'text.color');
        primitives = primitives.map(primitive => primitive.kind === 'text' ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, fontKey: font, style: { ...run.style, 'font-size': (0, model_js_1.num)(run.style['font-size'], 12) * sizeRatio, ...(typeof textColor === 'string' && (this.allowTextOverride || run.style.fill === '#243449') ? { fill: textColor } : {}) } })) } : primitive);
        for (const primitive of primitives)
            if (primitive.kind === 'text')
                for (const run of primitive.runs) {
                    const size = (0, model_js_1.num)(run.style['font-size'], 12), width = this.options.measure?.(run.text, size, font) ?? run.text.length * size * .6, anchor = run.style['text-anchor'], left = run.x - (anchor === 'middle' ? width / 2 : anchor === 'end' ? width : 0), top = run.y - size;
                    const x = Math.min(bounds.x, left), y = Math.min(bounds.y, top);
                    bounds = { x, y, width: Math.max(bounds.x + bounds.width, left + width) - x, height: Math.max(bounds.y + bounds.height, run.y + size * .25) - y };
                }
        const item = { occurrence, target: source.ref, view: this.view.ref, layer: 'content', bounds, transform: [1, 0, 0, 1, 0, 0], primitives, hitTargets: (0, exports.unique)(contributors.map(model_js_1.refKey)).map((key, i) => ({ id: `${occurrence}:${i}`, target: JSON.parse(key) })).map(hit => ({ id: hit.id, target: { file: hit.target[0], id: hit.target[1] }, bounds })), accessible: { role: 'graphics-symbol', label: name, description }, evidence: 'current' };
        const resolved = paperSurface && this.options.resolve ? this.options.resolve(source.ref, { view: this.view.ref }) : undefined;
        const effective = resolved?.values ?? this.effective;
        const background = resolved?.properties.find(p => p.path === 'background.color');
        if (background && typeof background.value === 'string' && (!background.origin.startsWith('standard:') || background.origin === 'standard:paper')) {
            const outer = item.primitives.findIndex(p => p.kind === 'rect');
            if (outer >= 0)
                item.primitives = item.primitives.map((p, i) => i === outer && p.kind === 'rect' ? { ...p, paint: { ...p.paint, fill: background.value } } : p);
        }
        const entry = { item, definition: source, view: this.view, effective };
        const decorated = paperSurface ? (0, stationery_js_1.decoratePaper)(entry) : entry;
        this.result.entries.push(decorated);
        bounds = decorated.item.bounds;
        this.result.bounds = { ...this.result.bounds,
            width: Math.max(this.result.bounds.width, bounds.x + bounds.width - this.bounds.x),
            height: Math.max(this.result.bounds.height, bounds.y + bounds.height - this.bounds.y) };
    }
    finish() {
        if (!this.result.entries.length)
            this.add(this.result.diagnostics.length ? 'Projection needs valid data' : 'No records', this.bounds, [(0, exports.label)(this.result.diagnostics[0]?.message ?? 'No records', this.bounds.x + 8, this.bounds.y + 24)]);
        if (this.result.unavailable.length)
            this.result.entries = this.result.entries.map(entry => ({ ...entry, item: { ...entry.item, evidence: 'partial' } }));
        return this.result;
    }
    legend(items, x = this.bounds.x + 64, y = this.bounds.y + 18, vertical = false) {
        let left = x, top = y;
        const primitives = [];
        for (const item of items) {
            const width = this.measure(item.label, 11) + 32;
            if (!vertical && left > x && left + width > this.bounds.x + this.bounds.width - 12) {
                left = x;
                top += 20;
            }
            primitives.push((0, exports.box)({ x: left, y: top - 9, width: 10, height: 10 }, item.color, 'none'), (0, exports.label)(item.label, left + 16, top, 11));
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
        this.add('Chart explanation', { x, y: y - 12, width: 0, height: lines.length * 16 }, lines.map((line, i) => (0, exports.label)(line, x, y + i * 16, 11, { fill: '#53657D' })), this.view, [this.view.ref], text);
    }
    intensity(domain, unit = '', x = this.bounds.x + 64, y = this.bounds.y + 18, ramp = (value) => colorScale(value, domain)) {
        const primitives = [];
        for (let i = 0; i < 20; i++)
            primitives.push((0, exports.box)({ x: x + i * 6, y: y - 10, width: 6, height: 10 }, ramp((0, exports.interpolate)(domain[0], domain[1], i / 19)), 'none'));
        primitives.push((0, exports.label)(`${(0, exports.numberLabel)(domain[0])} → ${(0, exports.numberLabel)(domain[1])}${unit ? ' ' + unit : ''}`, x + 130, y, 11));
        this.add('Intensity scale', { x, y: y - 12, width: 120, height: 16 }, primitives);
    }
    selection() {
        const selection = (0, model_js_1.array)((0, model_js_1.pathValue)(this.view.record, 'selection.include'));
        return selection.map(ref => (0, model_js_1.resolveRecord)(this.all, ref, this.view.file)).filter((v) => !!v);
    }
    data() {
        const refs = this.settings.records === undefined ? (0, model_js_1.array)((0, model_js_1.pathValue)(this.view.record, 'selection.include')) : Array.isArray(this.settings.records) ? this.settings.records : [this.settings.records];
        let rows = [];
        for (const ref of refs) {
            const source = (0, model_js_1.resolveRecord)(this.all, ref, this.view.file);
            if (!source) {
                this.issue('A selected record does not resolve.');
                continue;
            }
            let data = source.owner === 'data' ? source.record : (0, model_js_1.object)(source.record.data);
            if (data.source) {
                const target = (0, model_js_1.resolveRecord)(this.all, data.source, source.file);
                if (target?.owner === 'data')
                    data = target.record;
                else
                    this.issue('The record data binding does not resolve.', undefined, 'error', source.ref);
            }
            if (!Array.isArray(data.columns) && Array.isArray((0, model_js_1.object)(data.snapshot).columns))
                data = (0, model_js_1.object)(data.snapshot);
            if (Array.isArray(data.columns)) {
                const columns = (0, model_js_1.array)(data.columns).map(model_js_1.object);
                for (const [row, values] of (0, model_js_1.array)(data.rows).entries())
                    rows.push({ values: Object.fromEntries(columns.map((column, index) => [(0, model_js_1.str)(column.id), (0, model_js_1.array)(values)[index] ?? null])), source, contributors: [source.ref], ordinal: rows.length, row });
            }
            else
                rows.push({ values: { ...source.record, ...(0, model_js_1.object)((0, model_js_1.pathValue)(source.record, 'metadata.x_record')) }, source, contributors: [source.ref], ordinal: rows.length });
        }
        const count = rows.length;
        for (const filter of (0, model_js_1.array)(this.settings.filter).map(model_js_1.object))
            rows = rows.filter(d => filter.op === 'in' ? (0, model_js_1.array)(filter.value).some(v => Object.is(v, (0, exports.valueAt)(d.values, (0, model_js_1.str)(filter.key)))) : Object.is(filter.value, (0, exports.valueAt)(d.values, (0, model_js_1.str)(filter.key))));
        if (count && !rows.length)
            this.issue('Filtering removed every selected record.');
        const order = (0, model_js_1.array)(this.settings.order).map(model_js_1.object);
        rows.sort((a, b) => {
            for (const term of order) {
                const av = (0, exports.valueAt)(a.values, (0, model_js_1.str)(term.key)), bv = (0, exports.valueAt)(b.values, (0, model_js_1.str)(term.key));
                const diff = av === bv ? 0 : (0, exports.finite)(av) && (0, exports.finite)(bv) ? av - bv : String(av) < String(bv) ? -1 : 1;
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
    measure(text, size = 12) { const actual = size * (0, model_js_1.num)((0, model_js_1.pathValue)(this.effective, 'style.font_size'), 16) / 16; return this.options.measure?.(text, actual, (0, model_js_1.str)((0, model_js_1.pathValue)(this.effective, 'style.font'), 'sans')) ?? text.length * actual * .6; }
}
exports.DataScene = DataScene;
function mergedDatum(values, rows) { const first = rows[0]; return { ...first, values, contributors: rows.flatMap(row => row.contributors) }; }
function quantile(values, p) {
    const sorted = [...values].sort((a, b) => a - b);
    if (!sorted.length)
        return NaN;
    const i = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * p)), low = Math.floor(i);
    return sorted[low] + (sorted[Math.ceil(i)] - sorted[low]) * (i - low);
}
function numericDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value))
        return;
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed))
        return;
    if (value.length === 10 && new Date(parsed).toISOString().slice(0, 10) !== value)
        return;
    return parsed;
}

}});})();
