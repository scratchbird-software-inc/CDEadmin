/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"render-charts-875491bc3a3b","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-6502a4606789","shared-6cf9d24a4527","shared-98e37fe0f266"],"modules":[{"id":"presentation/src/data-charts.js","bytes":61305,"sha256":"854ed0f6db95dd45ee7cb21be9db7c27fbbf708ce38f4f402d71ef6b21e25cb5","dependencies":["presentation/src/model.js","presentation/src/data-common.js","presentation/src/data-statistics.js","profiles/src/projection-rules.js","presentation/src/data-quality.js","presentation/src/data-hierarchy.js"]},{"id":"presentation/src/data-hierarchy.js","bytes":26743,"sha256":"17154e1ec5e40eed157c5d785b09dd45312d616d669f837f242ab404a8bb1983","dependencies":["presentation/src/model.js","presentation/src/data-common.js"]},{"id":"presentation/src/data-isometric.js","bytes":5011,"sha256":"ae9f0a1e238cab03ea623da0b8e6b91553c6aead98b2b50f4fdb5f52d9dd0ea8","dependencies":["presentation/src/model.js"]},{"id":"presentation/src/data-quality.js","bytes":13945,"sha256":"fa4af6c67073a6d266d340ea0690814876631d5a389bcfdbad0f5a7bf24fe1f9","dependencies":["presentation/src/model.js","presentation/src/data-common.js"]},{"id":"presentation/src/data-statistics.js","bytes":9205,"sha256":"0ac8919152ccf928316651836219dca004c509a93596b0517dcb7fa26b59a749","dependencies":["presentation/src/data-common.js"]},{"id":"presentation/src/family-charts.js","bytes":1367,"sha256":"70f1b3ded87200797a878a3dc9f9a90c8078d9b36a781429c246e88e79e6a6c6","dependencies":["presentation/src/adapters.js","presentation/src/data-catalogue.js","presentation/src/data-adapter.js","presentation/src/data-charts.js","presentation/src/data-isometric.js","presentation/src/model.js"]},{"id":"standalone/src/families/charts.js","bytes":203,"sha256":"2f0669ae4ad1b5d7123354373ef1b050cf743565b320d862b78fd06f3e1a23df","dependencies":["presentation/src/family-charts.js"]}],"hash":"2a9e05d23acda8c123cacef0d55e0238b975ad2e7ba54a70501fcdbbc09fa303"},{"presentation/src/data-charts.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.drawChart = drawChart;
const model_js_1 = require("presentation/src/model.js");
const data_common_js_1 = require("presentation/src/data-common.js");
const data_statistics_js_1 = require("presentation/src/data-statistics.js");
const projection_rules_js_1 = require("profiles/src/projection-rules.js");
const data_quality_js_1 = require("presentation/src/data-quality.js");
const data_hierarchy_js_1 = require("presentation/src/data-hierarchy.js");
const sampleMarks = new Set(['histogram', 'density', 'qq', 'quantiledot']);
const hierarchyMarks = new Set(['treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble']);
const linkMarks = new Set(['sankey', 'arc', 'force', 'edgebundle']);
function drawChart(scene) {
    const settings = scene.settings, profile = (0, model_js_1.str)(scene.view.record.profile), specialized = profile.slice(6).split('@')[0], mark = (0, model_js_1.str)(settings.mark, ['basic', 'quality'].includes(specialized) ? 'bar' : specialized);
    const layers = (0, model_js_1.array)(settings.layers).map(model_js_1.object), qualityTransform = (0, model_js_1.str)(settings.transform, 'identity'), retainedTransform = ['histogram', 'pareto', 'waterfall', 'boxplot'].includes(qualityTransform);
    const authored = (0, model_js_1.object)((0, model_js_1.object)(scene.view.record.projection).options);
    for (const message of (0, projection_rules_js_1.chartOptionErrors)(profile, { ...authored, mark, ...(settings.transform !== undefined ? { transform: settings.transform } : {}) }))
        scene.issue(message, 'DDN-CHART-OPTION');
    if (settings.aggregate !== undefined && settings.aggregate !== 'none' && !['bar', 'pie', 'donut', 'topk'].includes(mark))
        scene.issue(`Aggregation does not apply to ${mark}.`);
    if (settings.aggregate === 'count' && settings.unit !== undefined)
        scene.issue('Count has no physical unit.');
    if (qualityTransform !== 'waterfall' && settings.baseline !== undefined && settings.baseline !== 0)
        scene.issue('Area-encoded marks require a zero baseline.');
    const data = scene.data(), xKey = (0, model_js_1.str)(settings.x, (0, model_js_1.str)(layers[0]?.x)), yKey = (0, model_js_1.str)(settings.y, (0, model_js_1.str)(layers[0]?.y)), seriesKey = (0, model_js_1.str)(settings.series), xType = (0, model_js_1.str)(settings.x_type, sampleMarks.has(mark) || mark === 'densityheatmap' ? 'number' : mark === 'calendar' ? 'date' : 'category');
    if (settings.iso === true && typeof settings.depth === 'string')
        for (const datum of data) {
            const depth = (0, data_common_js_1.valueAt)(datum.values, settings.depth);
            if (!(0, data_common_js_1.finite)(depth) || depth < 0 || depth > 2000)
                scene.issue('Every extrusion depth must be finite and between 0 and 2000', 'DDN-CHART-DEPTH');
        }
    if (retainedTransform && qualityTransform !== 'boxplot') {
        (0, data_quality_js_1.drawQuality)(scene, mark, qualityTransform, data);
        return;
    }
    if (qualityTransform === 'boxplot') {
        if (mark !== 'boxplot' || settings.quartiles !== undefined && settings.quartiles !== 'linear' || settings.whiskers !== undefined && !['iqr', 'minmax', 1.5].includes(settings.whiskers))
            scene.issue('Boxplot transform requires boxplot mark, linear quartiles and iqr/1.5 or minmax whiskers.');
        for (const key of ['series', 'layers', 'arrangement', 'aggregate'])
            if (Object.hasOwn(authored, key))
                scene.issue(`Boxplot transform does not admit authored ${key}.`);
    }
    if (!xKey || !yKey && !sampleMarks.has(mark) && mark !== 'candlestick') {
        scene.issue('Choose the required x and y channel bindings.');
        return;
    }
    if (sampleMarks.has(mark) && (yKey || seriesKey)) {
        scene.issue(`${mark} accepts raw x samples without y or series.`);
        return;
    }
    let points = [];
    for (const datum of data) {
        const rawX = (0, data_common_js_1.valueAt)(datum.values, xKey), rawY = sampleMarks.has(mark) || mark === 'candlestick' ? 0 : (0, data_common_js_1.valueAt)(datum.values, yKey);
        const x = xType === 'date' ? (0, data_common_js_1.numericDate)(rawX) : rawX;
        const missing = rawX === null || rawX === undefined || rawY === null || rawY === undefined;
        if (missing && settings.missing === 'skip')
            continue;
        const gap = (rawY === null || rawY === undefined) && settings.missing === 'gap' && ['bar', 'line', 'area', 'point'].includes(mark) && !layers.length;
        if (!(0, data_common_js_1.finite)(rawY) && !gap || (xType === 'number' || xType === 'date' ? !(0, data_common_js_1.finite)(x) : typeof x !== 'string' && !(0, data_common_js_1.finite)(x))) {
            scene.issue(`Record ${datum.source.ref.id} has an invalid ${!(0, data_common_js_1.finite)(rawY) ? 'y' : 'x'} value; numeric strings are not coerced.`, 'DDN-CHART-DATA', 'error', datum.source.ref);
            continue;
        }
        const series = seriesKey ? (0, data_common_js_1.valueAt)(datum.values, seriesKey) : '';
        if (seriesKey && typeof series !== 'string' && !(0, data_common_js_1.finite)(series)) {
            scene.issue('Series labels must be present scalar values.');
            continue;
        }
        if (settings.unit && datum.values.unit !== undefined && datum.values.unit !== settings.unit) {
            scene.issue('Record unit differs from the declared chart unit.');
            continue;
        }
        points.push({ datum, x: x, y: gap ? 0 : rawY, series: String(series), ...(gap ? { gap: true } : {}) });
    }
    if (layers.length) {
        if ((0, model_js_1.str)(settings.transform, 'identity') !== 'identity' || layers.some(layer => !['bar', 'point', 'line', 'area'].includes((0, model_js_1.str)(layer.mark, mark)))) {
            scene.issue('Layers require the identity transform and bar/point/line/area marks.');
            return;
        }
        const names = (0, data_common_js_1.unique)(points.map(point => point.series));
        if (seriesKey && layers.length !== names.length) {
            scene.issue('Declare one layer per series in series order.');
            return;
        }
        const layered = [];
        for (const [index, layer] of layers.entries())
            for (const original of points.filter(point => !seriesKey || point.series === names[index])) {
                const rawX = (0, data_common_js_1.valueAt)(original.datum.values, (0, model_js_1.str)(layer.x, xKey)), rawY = (0, data_common_js_1.valueAt)(original.datum.values, (0, model_js_1.str)(layer.y, yKey)), x = xType === 'date' ? (0, data_common_js_1.numericDate)(rawX) : rawX;
                if (!(0, data_common_js_1.finite)(rawY) || (xType === 'category' ? typeof x !== 'string' && !(0, data_common_js_1.finite)(x) : !(0, data_common_js_1.finite)(x))) {
                    scene.issue('A layer channel is missing or has the wrong type.');
                    continue;
                }
                layered.push({ ...original, x: x, y: rawY, series: seriesKey ? original.series : `Layer ${index + 1}`, mark: (0, model_js_1.str)(layer.mark, mark), color: (0, model_js_1.str)(layer.color, data_common_js_1.colors[index % data_common_js_1.colors.length]), opacity: (0, model_js_1.num)(layer.opacity, 1) });
            }
        points = layered;
    }
    if (scene.result.unavailable.length)
        return;
    if (!['bar', 'line', 'area', 'point', 'pie', 'donut', 'radar', 'heatmap', 'parallelcoords'].includes(mark) && seriesKey) {
        scene.issue(`${mark} does not accept a series channel.`);
        return;
    }
    if ((hierarchyMarks.has(mark) || linkMarks.has(mark) || ['radar', 'funnel', 'gauge', 'dotplot', 'boxplot', 'violin', 'beeswarm', 'topk', 'heatmap', 'parallelcoords', 'wordcloud'].includes(mark)) && xType !== 'category') {
        scene.issue(`${mark} requires categorical x.`);
        return;
    }
    if (mark === 'candlestick' && xType === 'number') {
        scene.issue('Candlestick x must be category or UTC date.');
        return;
    }
    if (mark === 'calendar' && xType !== 'date' || (sampleMarks.has(mark) || mark === 'densityheatmap') && xType !== 'number') {
        scene.issue(`${mark} has an incompatible x-axis type.`);
        return;
    }
    if (['heatmap', 'parallelcoords'].includes(mark) && !seriesKey) {
        scene.issue(`${mark} requires a series binding.`);
        return;
    }
    if (mark === 'funnel' && (0, data_common_js_1.unique)(points.map(p => p.x)).length < 2) {
        scene.issue('Funnel requires at least two distinct stages.');
        return;
    }
    const uniqueCoordinates = ['bar', 'line', 'area', 'pie', 'donut', 'funnel', 'candlestick', 'topk'].includes(mark);
    if (uniqueCoordinates && (0, model_js_1.str)(settings.aggregate, 'none') === 'none' && (0, data_common_js_1.unique)(points.map(p => JSON.stringify([p.x, p.series]))).length !== points.length) {
        scene.issue('Duplicate coordinates require an applicable explicit aggregation.');
        return;
    }
    if (!points.length && !['bar', 'line', 'area', 'point'].includes(mark)) {
        scene.issue(`${mark} requires at least one record.`);
        return;
    }
    if (hierarchyMarks.has(mark)) {
        (0, data_hierarchy_js_1.drawHierarchy)(scene, mark, points.map(p => ({ ...p.datum, values: { ...p.datum.values, label: String(p.x), value: p.y } })));
        return;
    }
    if (linkMarks.has(mark)) {
        (0, data_hierarchy_js_1.drawLinks)(scene, mark, points.map(p => ({ ...p.datum, values: { ...p.datum.values, source: String(p.x), value: p.y, target: (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.target, 'target')) } })));
        return;
    }
    const plot = { x: scene.bounds.x + 64, y: scene.bounds.y + 50, width: Math.max(80, (0, model_js_1.num)(settings.width, scene.bounds.width) - 96), height: Math.max(80, (0, model_js_1.num)(settings.height, scene.bounds.height) - 122) };
    const xLabel = (value) => xType === 'date' && typeof value === 'number' ? new Date(value).toISOString().slice(0, 10) : String(value);
    const addPoint = (p, bounds, primitives, description = '') => {
        scene.add(`${xLabel(p.x)}: ${(0, data_common_js_1.numberLabel)(p.y)}${p.series ? ` (${p.series})` : ''}`, bounds, primitives, p.datum.source, p.datum.contributors, description);
        const entry = scene.result.entries.at(-1), depth = typeof settings.depth === 'string' ? (0, data_common_js_1.valueAt)(p.datum.values, settings.depth) : undefined;
        if (entry && (0, data_common_js_1.finite)(depth))
            scene.extrusionDepths.set(entry.item.occurrence, depth);
    };
    const axes = (xDomain, yDomain, categories) => {
        const primitive = [(0, data_common_js_1.label)(mark === 'histogram' ? (0, model_js_1.str)(settings.normalize, 'count') : mark === 'density' ? 'Density' : (0, model_js_1.str)(settings.unit, (0, model_js_1.str)(settings.y)), plot.x, plot.y - 12, 11), (0, data_common_js_1.path)(`M${plot.x},${plot.y}V${plot.y + plot.height}H${plot.x + plot.width}`)];
        for (let i = 0; i <= 5; i++) {
            const y = plot.y + plot.height * (1 - i / 5);
            primitive.push((0, data_common_js_1.path)(`M${plot.x},${y}H${plot.x + plot.width}`, '#e2e8f0'), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(yDomain[0], yDomain[1], i / 5)), plot.x - 6, y + 4, 10, { 'text-anchor': 'end' }));
        }
        if (categories)
            categories.forEach((name, i) => primitive.push((0, data_common_js_1.label)(name, plot.x + (i + .5) * plot.width / Math.max(1, categories.length), plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' })));
        else
            for (let i = 0; i <= 5; i++)
                primitive.push((0, data_common_js_1.label)(xType === 'date' ? xLabel((0, data_common_js_1.interpolate)(xDomain[0], xDomain[1], i / 5)) : (0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(xDomain[0], xDomain[1], i / 5)), plot.x + plot.width * i / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
        if (mark === 'histogram' || mark === 'density')
            primitive.push((0, data_common_js_1.label)((0, model_js_1.str)(settings.unit, xKey), plot.x + plot.width / 2, plot.y + plot.height + 38, 11, { 'text-anchor': 'middle' }));
        scene.add('Chart axes', { ...plot, x: plot.x - 48, width: plot.width + 48, height: plot.height + 28 }, primitive);
    };
    if (mark === 'gauge') {
        if (points.length !== 1 || points[0].y < 0 || points[0].y > 100 || settings.target !== undefined && (!(0, data_common_js_1.finite)(settings.target) || settings.target < 0 || settings.target > 100)) {
            scene.issue('Gauge requires one value and optional target in 0..100.');
            return;
        }
        const p = points[0], radius = Math.min(plot.width / 2 - 35, plot.height - 50), cx = plot.x + plot.width / 2, cy = plot.y + radius + 12, inner = radius * .78;
        const primitives = [];
        for (let i = 0; i < 4; i++)
            primitives.push((0, data_common_js_1.path)((0, data_common_js_1.arcPath)(cx, cy, radius, Math.PI + Math.PI * i / 4, Math.PI + Math.PI * (i + 1) / 4, inner), '#fff', data_common_js_1.colors[i]));
        for (let i = 0; i <= 4; i++) {
            const angle = Math.PI + Math.PI * i / 4;
            primitives.push((0, data_common_js_1.label)(String(i * 25), cx + (radius + 22) * Math.cos(angle), cy + (radius + 22) * Math.sin(angle) + 4, 11, { 'text-anchor': 'middle' }));
        }
        const angle = Math.PI + Math.PI * p.y / 100;
        primitives.push((0, data_common_js_1.path)(`M${cx},${cy}L${cx + (inner - 10) * Math.cos(angle)},${cy + (inner - 10) * Math.sin(angle)}`, '#1E2D43', 'none', { 'stroke-width': 3 }), (0, data_common_js_1.ellipse)(cx, cy, 5, '#1E2D43'), (0, data_common_js_1.label)(`${(0, data_common_js_1.numberLabel)(p.y)}%`, cx, cy - radius * .28, 26, { 'text-anchor': 'middle' }), (0, data_common_js_1.label)(String(p.x), cx, cy + 34, 14, { 'text-anchor': 'middle' }));
        if ((0, data_common_js_1.finite)(settings.target)) {
            const a = Math.PI + Math.PI * settings.target / 100;
            primitives.push((0, data_common_js_1.path)(`M${cx + (radius + 2) * Math.cos(a)},${cy + (radius + 2) * Math.sin(a)}L${cx + (radius + 16) * Math.cos(a)},${cy + (radius + 16) * Math.sin(a)}`, '#1E2D43', 'none', { 'stroke-width': 3 }));
        }
        addPoint(p, plot, primitives);
        scene.caption(`Gauge: 0–100%; needle encodes value${(0, data_common_js_1.finite)(settings.target) ? '; outer tick marks target ' + settings.target + '%' : ''}.`);
        return;
    }
    if (mark === 'funnel') {
        if (seriesKey || points.some(p => p.y < 0)) {
            scene.issue('Funnel requires nonnegative values without series.');
            return;
        }
        const maximum = Math.max(...points.map(p => p.y), 1), height = Math.max(20, plot.height / points.length), center = plot.x + plot.width / 2;
        points.forEach((p, i) => {
            const top = plot.width * p.y / maximum, bottom = plot.width * (points[i + 1]?.y ?? p.y) / maximum, y = plot.y + i * height, text = `${p.x}: ${p.y.toLocaleString('en-US')}${settings.unit ? ' ' + settings.unit : ''}`, inside = scene.measure(text) < Math.min(top, bottom) - 16;
            const shape = [[center - top / 2, y], [center + top / 2, y], [center + bottom / 2, y + height], [center - bottom / 2, y + height]];
            addPoint(p, (0, data_common_js_1.boundsOf)(shape), [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(shape, true), '#fff', data_common_js_1.colors[i % data_common_js_1.colors.length]), (0, data_common_js_1.label)(text, inside ? center : center + Math.max(top, bottom) / 2 + 12, y + height / 2 + 4, 12, { 'text-anchor': inside ? 'middle' : 'start', fill: inside ? '#ffffff' : '#243449' })]);
        });
        scene.caption(`Stage widths encode values; ${points.length} stages; total ${(0, data_common_js_1.sum)(points.map(p => p.y)).toLocaleString('en-US')}${settings.unit ? ' ' + settings.unit : ''}.`);
        return;
    }
    if (mark === 'pie' || mark === 'donut') {
        const grouped = aggregate(points, (0, model_js_1.str)(settings.aggregate, 'none'), scene);
        if (grouped.some(p => p.y < 0) || !((0, data_common_js_1.sum)(grouped.map(p => p.y)) > 0) || seriesKey) {
            scene.issue('Arc shares require nonnegative values and a positive total without series.');
            return;
        }
        const total = (0, data_common_js_1.sum)(grouped.map(p => p.y)), legendWidth = Math.min(240, plot.width * .35), cx = plot.x + (plot.width - legendWidth) / 2, cy = plot.y + plot.height / 2, radius = Math.min(plot.width - legendWidth - 24, plot.height) / 2;
        let angle = -Math.PI / 2;
        grouped.forEach((p, i) => {
            const end = angle + p.y / total * Math.PI * 2;
            if (end > angle)
                addPoint(p, { x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, [(0, data_common_js_1.path)((0, data_common_js_1.arcPath)(cx, cy, radius, angle, end, mark === 'donut' ? Math.min(radius * .9, (0, model_js_1.num)(settings.inner_radius, radius * .55)) : 0), '#fff', data_common_js_1.colors[i % data_common_js_1.colors.length]), ...(p.y / total > .05 ? [(0, data_common_js_1.label)(`${(0, data_common_js_1.numberLabel)(p.y / total * 100)}%`, cx + Math.cos((angle + end) / 2) * radius * .72, cy + Math.sin((angle + end) / 2) * radius * .72, 11, { 'text-anchor': 'middle', fill: '#ffffff' })] : [])]);
            angle = end;
        });
        scene.legend(grouped.map((p, i) => ({ label: `${p.x}: ${(0, data_common_js_1.numberLabel)(p.y)}${settings.unit ? ' ' + settings.unit : ''}`, color: data_common_js_1.colors[i % data_common_js_1.colors.length] })), plot.x + plot.width - legendWidth, plot.y + 20, true);
        scene.caption(`Shares of total ${(0, data_common_js_1.numberLabel)(total)}${settings.unit ? ' ' + settings.unit : ''}; angles encode values.`);
        return;
    }
    if (mark === 'radar' || mark === 'parallelcoords') {
        const categories = (0, data_common_js_1.unique)(points.map(p => String(p.x))), series = (0, data_common_js_1.unique)(points.map(p => p.series));
        if (categories.length < (mark === 'radar' ? 3 : 2) || categories.length > (mark === 'radar' ? 40 : 24) || points.length !== new Set(points.map(p => JSON.stringify([p.x, p.series]))).size) {
            scene.issue('Axes and series must have unique samples and stay within the axis bound.');
            return;
        }
        const byCategory = categories.map(c => points.filter(p => String(p.x) === c)), domains = byCategory.map(values => (0, data_common_js_1.extent)(values.map(p => p.y))), max = Math.max(...points.map(p => p.y), 1), center = [plot.x + plot.width / 2, plot.y + plot.height / 2], radius = Math.min(plot.width, plot.height) * .42;
        const point = (index, value) => mark === 'radar' ? [center[0] + Math.cos(index * 2 * Math.PI / categories.length - Math.PI / 2) * radius * (value ?? 0) / max, center[1] + Math.sin(index * 2 * Math.PI / categories.length - Math.PI / 2) * radius * (value ?? 0) / max] : [plot.x + index * plot.width / (categories.length - 1), value === undefined || byCategory[index].every(p => p.y === byCategory[index][0].y) ? plot.y + plot.height / 2 : (0, data_common_js_1.scale)(domains[index], [plot.y + plot.height, plot.y])(value)];
        if (mark === 'radar' && points.some(p => p.y < 0)) {
            scene.issue('Radar values must be nonnegative.');
            return;
        }
        scene.legend(series.map((name, i) => ({ label: name || (0, model_js_1.str)(settings.y), color: data_common_js_1.colors[i % data_common_js_1.colors.length] })));
        if (mark === 'radar')
            for (let ring = 1; ring <= 4; ring++)
                scene.add('Radar scale', plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(categories.map((_, i) => point(i, max * ring / 4)), true), '#D9E3EF'), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)(max * ring / 4), center[0] + 6, center[1] - radius * ring / 4, 10)]);
        categories.forEach((category, i) => {
            const end = mark === 'radar' ? point(i, max) : [plot.x + i * plot.width / (categories.length - 1), plot.y], start = mark === 'radar' ? center : [end[0], plot.y + plot.height];
            scene.add(category, plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)([start, end]), '#cbd5e1'), (0, data_common_js_1.label)(category, end[0], end[1] - 6, 11, { 'text-anchor': 'middle' }), ...(mark === 'parallelcoords' ? [(0, data_common_js_1.label)((0, data_common_js_1.numberLabel)(domains[i][1]), end[0] + 6, end[1] + 14, 10), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)(domains[i][0]), end[0] + 6, plot.y + plot.height - 4, 10)] : [])]);
        });
        series.forEach((name, si) => {
            const members = points.filter(p => p.series === name), coordinates = [];
            let unknown = false;
            categories.forEach((category, i) => {
                const p = members.find(v => String(v.x) === category);
                if (!p) {
                    if (mark === 'radar') {
                        scene.issue('Radar requires a declared value at every series/axis intersection.');
                        return;
                    }
                    unknown = true;
                }
                if (mark === 'parallelcoords' && byCategory[i].every(v => v.y === byCategory[i][0].y))
                    unknown = true;
                coordinates.push(point(i, p?.y));
            });
            if (coordinates.length !== categories.length)
                return;
            if (unknown)
                scene.issue('Constant or missing axes are UNKNOWN at mid-height.', 'DDN-PJW04', 'warning');
            scene.add(name || mark, plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(coordinates, mark === 'radar'), data_common_js_1.colors[si % data_common_js_1.colors.length], mark === 'radar' ? data_common_js_1.colors[si % data_common_js_1.colors.length] : 'none', { 'fill-opacity': .12 }), ...coordinates.map(([x, y]) => (0, data_common_js_1.ellipse)(x, y, 3, data_common_js_1.colors[si % data_common_js_1.colors.length]))], members[0].datum.source, members.flatMap(p => p.datum.contributors));
        });
        scene.caption(mark === 'radar' ? `Shared radial scale: 0–${(0, data_common_js_1.numberLabel)(max)}${settings.unit ? ' ' + settings.unit : ''}.` : 'Each axis is normalized independently; constant or missing values are UNKNOWN at mid-height.');
        return;
    }
    if (mark === 'candlestick') {
        const rows = points.map(p => ({ p, open: (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.open, 'open')), high: (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.high, 'high')), low: (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.low, 'low')), close: (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.close, 'close')) }));
        if (rows.some(r => ![r.open, r.high, r.low, r.close].every(data_common_js_1.finite) || (0, model_js_1.num)(r.low) > Math.min((0, model_js_1.num)(r.open), (0, model_js_1.num)(r.close)) || (0, model_js_1.num)(r.high) < Math.max((0, model_js_1.num)(r.open), (0, model_js_1.num)(r.close)))) {
            scene.issue('OHLC values must be finite and enclosed by low/high.');
            return;
        }
        const domain = (0, data_common_js_1.extent)(rows.flatMap(r => [(0, model_js_1.num)(r.low), (0, model_js_1.num)(r.high)])), ys = (0, data_common_js_1.scale)(domain, [plot.y + plot.height, plot.y]), step = plot.width / Math.max(1, rows.length);
        axes([0, rows.length], domain, rows.map(r => xLabel(r.p.x)));
        rows.forEach((r, i) => { const x = plot.x + (i + .5) * step, top = ys(Math.max((0, model_js_1.num)(r.open), (0, model_js_1.num)(r.close))), bottom = ys(Math.min((0, model_js_1.num)(r.open), (0, model_js_1.num)(r.close))), fill = (0, model_js_1.num)(r.close) >= (0, model_js_1.num)(r.open) ? data_common_js_1.colors[1] : data_common_js_1.colors[2]; addPoint(r.p, { x: x - step * .22, y: ys((0, model_js_1.num)(r.high)), width: step * .44, height: ys((0, model_js_1.num)(r.low)) - ys((0, model_js_1.num)(r.high)) }, [(0, data_common_js_1.path)(`M${x},${ys((0, model_js_1.num)(r.high))}V${ys((0, model_js_1.num)(r.low))}`, fill), (0, data_common_js_1.box)({ x: x - step * .22, y: top, width: step * .44, height: Math.max(1, bottom - top) }, fill)], `Open ${r.open}; high ${r.high}; low ${r.low}; close ${r.close}`); });
        scene.caption('OHLC: bodies span open to close; wicks span low to high; green indicates close at or above open, brown indicates a fall.');
        return;
    }
    if (sampleMarks.has(mark)) {
        drawSamples(scene, points, mark, plot, axes);
        return;
    }
    if (['dotplot', 'beeswarm', 'boxplot', 'violin'].includes(mark)) {
        drawDistributions(scene, points, mark, plot, axes);
        return;
    }
    if (['heatmap', 'densityheatmap', 'calendar', 'wordcloud'].includes(mark)) {
        drawDense(scene, points, mark, plot);
        return;
    }
    if (!['bar', 'point', 'line', 'area', 'topk'].includes(mark)) {
        scene.issue(`No quantitative algorithm is registered for ${mark}.`);
        return;
    }
    let plotted = aggregate(points, (0, model_js_1.str)(settings.aggregate, 'none'), scene);
    if (mark === 'topk') {
        const k = (0, model_js_1.num)(settings.k, 10);
        if (!Number.isInteger(k) || k < 1 || k > 100) {
            scene.issue('Top-k requires k in 1..100.');
            return;
        }
        plotted = [...plotted].sort((a, b) => b.y - a.y || (String(a.x) < String(b.x) ? -1 : String(a.x) > String(b.x) ? 1 : a.datum.ordinal - b.datum.ordinal));
        const remainder = plotted.slice(k);
        plotted = plotted.slice(0, k);
        if (remainder.length && settings.others !== false)
            plotted.push({ x: 'Others', y: (0, data_common_js_1.sum)(remainder.map(p => p.y)), series: '', datum: (0, data_common_js_1.mergedDatum)({}, remainder.map(p => p.datum)) });
    }
    const transform = (0, model_js_1.str)(settings.transform, 'identity');
    if (transform !== 'identity') {
        const maximum = Math.max(...plotted.map(p => Math.abs(p.y)), 0);
        if (plotted.some(p => !p.gap && (transform === 'log' && p.y <= 0 || transform === 'sqrt' && p.y < 0)) || transform === 'normalize' && maximum === 0) {
            scene.issue('The selected transformation is undefined for supplied values.');
            return;
        }
        plotted = plotted.map(p => ({ ...p, y: p.gap ? 0 : transform === 'log' ? Math.log(p.y) : transform === 'sqrt' ? Math.sqrt(p.y) : transform === 'normalize' ? p.y / maximum : p.y }));
    }
    const categories = (0, data_common_js_1.unique)(plotted.map(p => String(p.x))), series = (0, data_common_js_1.unique)(plotted.map(p => p.series)), arrangement = (0, model_js_1.str)(settings.arrangement, 'group');
    if (series.length > 20 || seriesKey && categories.length > 200) {
        scene.issue('Series charts permit at most 20 series and 200 coordinates.');
        return;
    }
    if (!layers.length && (mark === 'bar' || mark === 'topk') && xType !== 'category') {
        scene.issue('Bar/top-k require categorical x.');
        return;
    }
    if (arrangement === 'stack' || arrangement === 'percent') {
        if (plotted.some(p => p.gap) && settings.series_missing !== 'zero') {
            scene.issue('Missing stacked values require explicit zero filling.');
            return;
        }
        if (categories.some(category => series.some(name => !plotted.some(p => String(p.x) === category && p.series === name))) && settings.series_missing !== 'zero') {
            scene.issue('Stacks require complete data or explicit zero-filled series.');
            return;
        }
        if (arrangement === 'percent' && (plotted.some(p => p.y < 0) || categories.some(category => (0, data_common_js_1.sum)(plotted.filter(p => String(p.x) === category).map(p => p.y)) <= 0))) {
            scene.issue('Percent stacks require nonnegative values and positive totals.');
            return;
        }
    }
    const percentTotals = new Map(categories.map(category => [category, (0, data_common_js_1.sum)(plotted.filter(p => String(p.x) === category).map(p => p.y))]));
    if (arrangement === 'percent' && [...percentTotals.values()].some(value => !(0, data_common_js_1.finite)(value))) {
        scene.issue('Category totals exceed the finite numeric range.');
        return;
    }
    const offsets = new Map(), totals = new Map();
    for (const p of plotted) {
        const total = totals.get(String(p.x)) ?? [0, 0], y = arrangement === 'percent' ? p.y / percentTotals.get(String(p.x)) * 100 : p.y;
        p.y = y;
        offsets.set(p, arrangement === 'stack' || arrangement === 'percent' ? total[y < 0 ? 0 : 1] : 0);
        total[y < 0 ? 0 : 1] += y;
        totals.set(String(p.x), total);
    }
    const errors = (0, model_js_1.object)(settings.error), errorValues = plotted.filter(p => !p.gap).flatMap(p => {
        const amount = (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(errors.value)), low = errors.low ? (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(errors.low)) : (0, data_common_js_1.finite)(amount) ? p.y - amount : undefined, high = errors.high ? (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(errors.high)) : (0, data_common_js_1.finite)(amount) ? p.y + amount : undefined;
        return [low, high].filter(data_common_js_1.finite);
    });
    const yDomain = (0, data_common_js_1.extent)([...plotted.filter(p => !p.gap).flatMap(p => [offsets.get(p) + p.y]), ...errorValues], true), xDomain = xType === 'category' ? [0, categories.length] : (0, data_common_js_1.extent)(plotted.map(p => Number(p.x))), ys = (0, data_common_js_1.scale)(yDomain, [plot.y + plot.height, plot.y]), xs = (p) => xType === 'category' ? plot.x + (categories.indexOf(String(p.x)) + .5) * plot.width / Math.max(1, categories.length) : (0, data_common_js_1.scale)(xDomain, [plot.x, plot.x + plot.width])(Number(p.x));
    axes(xDomain, yDomain, xType === 'category' ? categories : undefined);
    const markFor = (p) => p.mark ?? mark, colorFor = (p) => p.color ?? (mark === 'topk' && p.x === 'Others' ? '#C6D5E6' : data_common_js_1.colors[(series.length === 1 && ['bar', 'topk', 'point'].includes(markFor(p)) ? categories.indexOf(String(p.x)) : series.indexOf(p.series)) % data_common_js_1.colors.length]);
    if (series.some(Boolean))
        scene.legend(series.map(name => ({ label: name, color: colorFor(plotted.find(p => p.series === name)) })));
    if (mark === 'topk')
        scene.caption(`Top ${(0, model_js_1.num)(settings.k, 10)} categories by value${settings.others !== false ? '; remaining values grouped as Others' : ''}.`);
    if (plotted.some(p => ['bar', 'topk'].includes(markFor(p)) && xType !== 'category')) {
        scene.issue('Layer marks must match the shared x-axis type.');
        return;
    }
    for (const p of plotted) {
        if (p.gap) {
            scene.add(`${xLabel(p.x)}: missing`, { x: xs(p) - 24, y: plot.y + plot.height + 22, width: 48, height: 18 }, [(0, data_common_js_1.label)('missing', xs(p), plot.y + plot.height + 34, 10, { 'text-anchor': 'middle' })], p.datum.source, p.datum.contributors);
            continue;
        }
        const shape = markFor(p), opacity = p.opacity ?? 1;
        if (shape === 'bar' || shape === 'topk') {
            const i = series.indexOf(p.series), band = plot.width / Math.max(1, categories.length), width = band * .8 / (arrangement === 'group' ? series.length : 1), x = xs(p) - band * .4 + (arrangement === 'group' ? i * width : 0), base = offsets.get(p), y = ys(Math.max(base, base + p.y)), height = Math.max(0, ys(Math.min(base, base + p.y)) - y), bounds = { x, y, width: Math.max(1, width - 1), height };
            addPoint(p, bounds, [(0, data_common_js_1.box)(bounds, colorFor(p), 'none', { opacity })], `Contributors: ${p.datum.contributors.map(r => r.id).join(', ')}`);
        }
        else if (shape === 'point') {
            const rawSize = settings.size ? (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(settings.size)) : 25;
            if (!(0, data_common_js_1.finite)(rawSize) || rawSize < 0) {
                scene.issue('Point size requires a finite nonnegative value.');
                continue;
            }
            const radius = Math.sqrt(rawSize);
            addPoint(p, { x: xs(p) - radius, y: ys(p.y) - radius, width: radius * 2, height: radius * 2 }, [(0, data_common_js_1.ellipse)(xs(p), ys(p.y), radius, colorFor(p), { opacity })]);
        }
    }
    for (const name of series) {
        const rows = plotted.filter(p => p.series === name), shape = rows[0] ? markFor(rows[0]) : mark;
        if (shape !== 'line' && shape !== 'area')
            continue;
        if (new Set(rows.map(p => p.x)).size !== rows.length) {
            scene.issue('Line and area series require unique x coordinates.');
            continue;
        }
        const segments = [[]];
        for (const category of xType === 'category' ? categories : rows.map(p => String(p.x))) {
            const p = rows.find(p => String(p.x) === category);
            if (p && !p.gap)
                segments.at(-1).push(p);
            else if (p?.gap)
                segments.push([]);
            else if (settings.series_missing === 'zero') {
                const template = rows[0];
                segments.at(-1).push({ ...template, x: category, y: 0 });
            }
            else if (settings.series_missing === 'error')
                scene.issue(`Series ${name} is missing ${category}.`);
            else
                segments.push([]);
        }
        for (const segment of segments.filter(s => s.length)) {
            const coordinates = segment.map(p => [xs(p), ys(p.y + (offsets.get(p) ?? 0))]), bottom = [...segment].reverse().map(p => [xs(p), ys(offsets.get(p) ?? 0)]);
            scene.add(name || shape, plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(shape === 'area' ? [...coordinates, ...bottom] : coordinates, shape === 'area'), colorFor(segment[0]), shape === 'area' ? colorFor(segment[0]) : 'none', { 'fill-opacity': .2, opacity: segment[0].opacity ?? 1, 'stroke-width': 2, ...(series.indexOf(name) % 2 ? { 'stroke-dasharray': '6 3' } : {}) }), ...(shape === 'line' && !layers.some(layer => layer.mark === 'point') ? coordinates.map(([x, y]) => (0, data_common_js_1.ellipse)(x, y, 3, colorFor(segment[0]))) : [])], segment[0].datum.source, segment.flatMap(p => p.datum.contributors));
        }
    }
    if (settings.trend && (0, model_js_1.object)(settings.trend).show !== false) {
        try {
            const method = (0, model_js_1.str)((0, model_js_1.object)(settings.trend).method, 'linear');
            if (!['linear', 'loess'].includes(method))
                throw new Error('Trend method must be linear or loess.');
            const values = plotted.filter(p => !p.gap).map(p => [Number(p.x), p.y]);
            if (xType !== 'number')
                throw new Error('Trend requires numeric x.');
            const fit = method === 'linear' ? (0, data_statistics_js_1.linearTrend)(values) : undefined;
            const trend = fit ? [xDomain[0], xDomain[1]].map(x => [x, fit.slope * x + fit.intercept]) : (0, data_statistics_js_1.loessTrend)(values);
            const ends = trend.map(([x, y]) => [(0, data_common_js_1.scale)(xDomain, [plot.x, plot.x + plot.width])(x), ys(y)]);
            scene.add(method === 'linear' ? 'Linear trend' : 'LOESS trend', plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(ends), '#dc2626', 'none', { 'stroke-dasharray': '6 3' })], scene.view, plotted.flatMap(p => p.datum.contributors), method === 'loess' ? 'Local linear fit; tricube weights; 2/3 span; no robust iterations' : 'Least-squares linear fit');
        }
        catch (error) {
            scene.issue(String(error), 'DDN-PJW04', 'warning');
        }
    }
    const error = (0, model_js_1.object)(settings.error);
    if (Object.keys(error).length)
        for (const p of plotted.filter(p => !p.gap)) {
            const amount = (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(error.value)), lo = error.low ? (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(error.low)) : (0, data_common_js_1.finite)(amount) ? p.y - amount : undefined, hi = error.high ? (0, data_common_js_1.valueAt)(p.datum.values, (0, model_js_1.str)(error.high)) : (0, data_common_js_1.finite)(amount) ? p.y + amount : undefined;
            if (!(0, data_common_js_1.finite)(lo) || !(0, data_common_js_1.finite)(hi) || lo > hi) {
                scene.issue('Error bounds must be finite and increasing.');
                continue;
            }
            const x = xs(p);
            scene.add('Error interval', (0, data_common_js_1.boundsOf)([[x, ys(lo)], [x, ys(hi)]], 4), [(0, data_common_js_1.path)(`M${x},${ys(lo)}V${ys(hi)}M${x - 4},${ys(lo)}h8M${x - 4},${ys(hi)}h8`, '#334155')], p.datum.source, p.datum.contributors);
        }
    if (settings.iso === true)
        scene.caption('Top faces preserve the value scale; depth is a presentation setting.');
}
function aggregate(points, operation, scene) {
    if (operation === 'none')
        return [...points];
    if (points.some(p => p.gap)) {
        scene.issue('Aggregation cannot silently replace missing measurements with zero.');
        return [];
    }
    if (!['sum', 'count', 'min', 'max', 'average', 'median'].includes(operation)) {
        scene.issue('Unknown aggregation.');
        return [];
    }
    const groups = new Map();
    for (const p of points) {
        const key = JSON.stringify([p.x, p.series]);
        groups.set(key, [...groups.get(key) ?? [], p]);
    }
    return [...groups.values()].map(group => { const values = group.map(p => p.y), sorted = [...values].sort((a, b) => a - b), first = group[0]; return { ...first, y: operation === 'sum' ? (0, data_common_js_1.sum)(values) : operation === 'count' ? values.length : operation === 'min' ? Math.min(...values) : operation === 'max' ? Math.max(...values) : operation === 'average' ? (0, data_common_js_1.sum)(values) / values.length : sorted.length % 2 ? sorted[Math.floor(sorted.length / 2)] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2, datum: (0, data_common_js_1.mergedDatum)(first.datum.values, group.map(p => p.datum)) }; });
}
function drawSamples(scene, points, mark, plot, axes) {
    const samples = points.map(p => Number(p.x));
    if (points.length < 2) {
        scene.issue(`${mark} requires at least two observations.`);
        return;
    }
    if (mark === 'histogram') {
        const settings = scene.settings, descriptor = (0, model_js_1.object)(settings.bins), authored = (0, model_js_1.object)((0, model_js_1.object)(scene.view.record.projection).options);
        const count = typeof settings.bins === 'number' ? settings.bins : typeof descriptor.count === 'number' ? descriptor.count : settings.bin_count === 'auto' || settings.bin_count === undefined ? undefined : (0, model_js_1.num)(settings.bin_count);
        if (Array.isArray(settings.bins)) {
            scene.issue('Direct histogram uses equal-width bins; explicit boundaries belong to the histogram transform.');
            return;
        }
        if (settings.bins !== undefined && authored.bin_count !== undefined && authored.bin_count !== 'auto' && count !== authored.bin_count) {
            scene.issue('Explicit bins and bin_count disagree.');
            return;
        }
        let bins;
        try {
            bins = (0, data_statistics_js_1.histogramPlan)(samples, {
                ...(count !== undefined ? { count } : {}),
                ...((0, data_common_js_1.finite)(descriptor.min) ? { minimum: descriptor.min } : {}),
                ...((0, data_common_js_1.finite)(descriptor.max) ? { maximum: descriptor.max } : {}),
                ...((0, data_common_js_1.finite)(settings.step) ? { step: settings.step } : (0, data_common_js_1.finite)(descriptor.step) ? { step: descriptor.step } : {}),
                outside: (0, model_js_1.str)(settings.outside, 'error'),
                normalize: settings.normalize === true ? true : settings.normalize === false ? false : (0, model_js_1.str)(settings.normalize, 'count')
            });
        }
        catch (error) {
            scene.issue(String(error));
            return;
        }
        const xd = [bins[0].low, bins.at(-1).high], yd = (0, data_common_js_1.extent)(bins.map(bin => bin.value), true), xs = (0, data_common_js_1.scale)(xd, [plot.x, plot.x + plot.width]), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]);
        axes(xd, yd);
        bins.forEach(bin => { const b = { x: xs(bin.low), y: ys(bin.value), width: Math.max(.1, xs(bin.high) - xs(bin.low) - Math.min(1, (xs(bin.high) - xs(bin.low)) * .1)), height: plot.y + plot.height - ys(bin.value) }; const members = bin.indices.map(i => points[i].datum); scene.add(`${(0, data_common_js_1.numberLabel)(bin.low)}–${(0, data_common_js_1.numberLabel)(bin.high)}: ${(0, data_common_js_1.numberLabel)(bin.value)}`, b, [(0, data_common_js_1.box)(b, data_common_js_1.colors[0], 'none')], members[0]?.source ?? scene.view, members.flatMap(d => d.contributors), `${bin.count} contributing observations; normalization ${String(settings.normalize ?? 'count')}`); });
        scene.caption(`n=${samples.length}; ${bins.length} equal-width bins; left inclusive, right exclusive except final bin; ${String(settings.normalize ?? 'count')}.`);
        return;
    }
    if (mark === 'density') {
        try {
            const kde = (0, data_statistics_js_1.kernelDensity)(samples), xd = (0, data_common_js_1.extent)(kde.points.map(p => p[0])), yd = (0, data_common_js_1.extent)(kde.points.map(p => p[1]), true), xs = (0, data_common_js_1.scale)(xd, [plot.x, plot.x + plot.width]), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]);
            axes(xd, yd);
            const coordinates = kde.points.map(p => [xs(p[0]), ys(p[1])]);
            scene.add('Gaussian density estimate', plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)([...coordinates, [plot.x + plot.width, plot.y + plot.height], [plot.x, plot.y + plot.height]], true), data_common_js_1.colors[0], data_common_js_1.colors[0], { 'fill-opacity': .18 })], points[0].datum.source, points.flatMap(p => p.datum.contributors), `Bandwidth ${kde.bandwidth}; 81 evaluation points`);
            scene.caption(`Gaussian KDE; n=${samples.length}; bandwidth ${(0, data_common_js_1.numberLabel)(kde.bandwidth)}; area under curve ≈ 1.`);
        }
        catch (error) {
            scene.issue(String(error), 'DDN-PJ132');
        }
        return;
    }
    if (mark === 'qq' && samples.every(value => value === samples[0])) {
        scene.issue('Normal QQ comparison is UNKNOWN for zero-variance samples.', 'DDN-PJ132');
        return;
    }
    if (mark === 'qq') {
        const ordered = [...points].sort((a, b) => Number(a.x) - Number(b.x) || a.datum.ordinal - b.datum.ordinal), pairs = ordered.map((p, i) => [(0, data_statistics_js_1.inverseNormal)((i + .5) / ordered.length), Number(p.x)]), xd = (0, data_common_js_1.extent)(pairs.map(p => p[0])), yd = (0, data_common_js_1.extent)(samples), xs = (0, data_common_js_1.scale)(xd, [plot.x, plot.x + plot.width]), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]);
        axes(xd, yd);
        scene.add('Theoretical normal quantiles', plot, [(0, data_common_js_1.label)('Theoretical normal quantiles', plot.x + plot.width / 2, plot.y + plot.height + 40, 11, { 'text-anchor': 'middle' })]);
        ordered.forEach((p, i) => { const xy = pairs[i], x = xs(xy[0]), y = ys(xy[1]); scene.add(`Rank ${i + 1}: ${xy[1]}`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [(0, data_common_js_1.ellipse)(x, y, 4)], p.datum.source, p.datum.contributors); });
        const q1 = (0, data_statistics_js_1.quantileContributors)(samples, .25).value, q3 = (0, data_statistics_js_1.quantileContributors)(samples, .75).value, slope = (q3 - q1) / ((0, data_statistics_js_1.inverseNormal)(.75) - (0, data_statistics_js_1.inverseNormal)(.25)), intercept = q1 - slope * (0, data_statistics_js_1.inverseNormal)(.25);
        scene.add('Quartile reference', plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(xd.map(x => [xs(x), ys(intercept + slope * x)])), '#64748b', 'none', { 'stroke-dasharray': '5 3' })]);
        scene.caption(`Normal Q–Q: theoretical normal quantiles against sample${scene.settings.unit ? ' (' + scene.settings.unit + ')' : ''}; quartile reference line; n=${samples.length}.`);
        return;
    }
    const xd = (0, data_common_js_1.extent)(samples), xs = (0, data_common_js_1.scale)(xd, [plot.x, plot.x + plot.width]), count = Math.min(20, samples.length), previous = [];
    const axis = [(0, data_common_js_1.path)(`M${plot.x},${plot.y + plot.height}H${plot.x + plot.width}`)];
    for (let i = 0; i <= 4; i++) {
        const x = plot.x + plot.width * i / 4;
        axis.push((0, data_common_js_1.path)(`M${x},${plot.y}V${plot.y + plot.height}`, '#E2E8F0'), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(xd[0], xd[1], i / 4)), x, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
    }
    axis.push((0, data_common_js_1.label)(`${count} quantiles of ${(0, model_js_1.str)(scene.settings.unit, (0, model_js_1.str)(scene.settings.x))}`, plot.x, plot.y - 12, 11));
    scene.add('Quantile sample axis', plot, axis);
    scene.caption(`${count} equal-probability quantiles${scene.settings.unit ? '; ' + scene.settings.unit : ''}; vertical displacement avoids overlap and has no quantitative meaning.`);
    for (let i = 0; i < count; i++) {
        const q = (0, data_statistics_js_1.quantileContributors)(samples, (i + .5) / count), x = xs(q.value);
        let lane = 0;
        while (previous.some(p => Math.abs(p[0] - x) < 16.8 && Math.abs(p[1] - lane) < 1))
            lane++;
        previous.push([x, lane]);
        const y = plot.y + plot.height - lane * 16.8 - 7, contributors = q.indices.flatMap(index => points[index].datum.contributors);
        scene.add(`Quantile ${(i + .5) / count}: ${q.value}`, { x: x - 7, y: y - 7, width: 14, height: 14 }, [(0, data_common_js_1.ellipse)(x, y, 7)], points[q.indices[0]].datum.source, contributors, `R-7 interpolated value; source indices ${q.indices.join(', ')}; weights ${q.weights.join(', ')}`);
    }
}
function drawDistributions(scene, points, mark, plot, axes) {
    const categories = (0, data_common_js_1.unique)(points.map(p => String(p.x)));
    if (categories.length > 40) {
        scene.issue('Distribution charts are bounded to 40 categories.');
        return;
    }
    const groups = categories.map(name => points.filter(p => String(p.x) === name));
    const densities = mark === 'violin' ? groups.map(group => {
        try {
            return (0, data_statistics_js_1.kernelDensity)(group.map(p => p.y), 61);
        }
        catch (error) {
            scene.issue(String(error), 'DDN-PJ132');
            return undefined;
        }
    }) : [];
    if (scene.result.unavailable.length)
        return;
    const yd = (0, data_common_js_1.extent)(mark === 'violin' ? densities.flatMap(d => d.points.map(p => p[0])) : points.map(p => p.y)), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]), band = plot.width / Math.max(1, categories.length);
    axes([0, categories.length], yd, categories);
    scene.caption(mark === 'boxplot' ? 'R-7 quartiles; median; Tukey 1.5-IQR whiskers and outliers.' : mark === 'violin' ? 'Gaussian KDE; common density scale; median and interquartile range.' : 'Each dot is one observation; horizontal displacement has no quantitative meaning.');
    groups.forEach((group, index) => {
        const x = plot.x + (index + .5) * band, color = data_common_js_1.colors[index % data_common_js_1.colors.length];
        if (mark === 'boxplot' || mark === 'violin') {
            const f = (0, data_statistics_js_1.fiveNumber)(group.map(p => p.y)), primitives = [];
            if (mark === 'boxplot' && scene.settings.transform === 'boxplot' && scene.settings.whiskers === 'minmax') {
                f.low = Math.min(...group.map(p => p.y));
                f.high = Math.max(...group.map(p => p.y));
                f.outliers = [];
            }
            if (mark === 'violin') {
                const density = densities[index], maximum = Math.max(...densities.flatMap(d => d.points.map(p => p[1]))), half = band * .42, coordinates = [...density.points.map(p => [x - p[1] / maximum * half, ys(p[0])]), ...[...density.points].reverse().map(p => [x + p[1] / maximum * half, ys(p[0])])];
                primitives.push((0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(coordinates, true), color, color, { 'fill-opacity': .2, 'stroke-width': 2 }), (0, data_common_js_1.path)(`M${x},${ys(f.q1)}V${ys(f.q3)}`, '#334155', 'none', { 'stroke-width': 5 }), (0, data_common_js_1.ellipse)(x, ys(f.median), 4, '#fff', { stroke: '#334155' }));
            }
            else {
                const w = Math.min(70, band * .45);
                primitives.push((0, data_common_js_1.path)(`M${x},${ys(f.low)}V${ys(f.q1)}M${x},${ys(f.q3)}V${ys(f.high)}M${x - w / 3},${ys(f.low)}h${w * 2 / 3}M${x - w / 3},${ys(f.high)}h${w * 2 / 3}`, color), (0, data_common_js_1.box)({ x: x - w / 2, y: ys(f.q3), width: w, height: Math.max(1, ys(f.q1) - ys(f.q3)) }, color, color, { 'fill-opacity': .22, 'stroke-width': 2 }), (0, data_common_js_1.path)(`M${x - w / 2},${ys(f.median)}h${w}`, color, 'none', { 'stroke-width': 3 }));
            }
            primitives.push((0, data_common_js_1.label)(`n=${group.length}`, x, plot.y + plot.height + 34, 10, { 'text-anchor': 'middle' }));
            scene.add(`${categories[index]}: median ${f.median}`, { x: x - band * .45, y: plot.y, width: band * .9, height: plot.height }, primitives, group[0].datum.source, group.flatMap(p => p.datum.contributors), `R-7 quartiles ${f.q1}, ${f.median}, ${f.q3}; ${scene.settings.whiskers === 'minmax' ? 'Min/max' : 'Tukey'} whiskers ${f.low}, ${f.high}`);
            if (mark === 'boxplot')
                f.outliers.forEach(outlier => { const p = group[outlier.index], y = ys(outlier.value); scene.add(`Outlier ${outlier.value}`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [(0, data_common_js_1.ellipse)(x, y, 4, '#fff', { stroke: color })], p.datum.source, p.datum.contributors); });
        }
        else {
            const placed = [];
            const radius = Math.min(9, band / 8), separation = 2.3 * radius;
            const ordered = [...group].sort((a, b) => a.y - b.y || a.datum.ordinal - b.datum.ordinal);
            for (const p of ordered) {
                const y = ys(p.y);
                const ties = mark === 'dotplot' ? ordered.filter(other => other.y === p.y) : [];
                let offset = mark === 'dotplot' ? (ties.indexOf(p) - (ties.length - 1) / 2) * separation : 0, candidate = 0;
                while (mark === 'beeswarm' && placed.some(pt => (pt[0] - (x + offset)) ** 2 + (pt[1] - y) ** 2 < separation ** 2)) {
                    candidate++;
                    offset = Math.ceil(candidate / 2) * separation * (candidate % 2 ? 1 : -1);
                    if (Math.abs(offset) > band * .45) {
                        scene.issue('Swarm extends beyond its category lane; enlarge the view.', 'DDN-PJW04', 'warning');
                        break;
                    }
                }
                placed.push([x + offset, y]);
                scene.add(`${p.x}: ${p.y}`, { x: x + offset - radius, y: y - radius, width: radius * 2, height: radius * 2 }, [(0, data_common_js_1.ellipse)(x + offset, y, radius, color, { 'fill-opacity': .85 })], p.datum.source, p.datum.contributors, 'Horizontal displacement is collision avoidance only.');
            }
        }
    });
}
function drawDense(scene, points, mark, plot) {
    if (mark === 'wordcloud') {
        if (points.length > 120 || points.some(p => p.y <= 0) || new Set(points.map(p => p.x)).size !== points.length) {
            scene.issue('Word clouds require at most 120 unique labels with positive weights.');
            return;
        }
        const maximum = Math.max(...points.map(p => p.y)), occupied = [];
        for (const [index, p] of [...points].sort((a, b) => b.y - a.y || (String(a.x) < String(b.x) ? -1 : String(a.x) > String(b.x) ? 1 : 0) || a.datum.ordinal - b.datum.ordinal).entries()) {
            const size = 15 + (Math.max(30, Math.min(58, plot.width / 9)) - 15) * Math.sqrt(p.y / maximum), width = scene.measure(String(p.x), size) * 1.08 + 10, height = size * 1.3 * (0, model_js_1.num)((0, model_js_1.pathValue)(scene.effective, 'style.font_size'), 16) / 16;
            let found;
            for (let step = 0; step < 410; step++) {
                const angle = step * .22, radius = angle * 5, b = { x: plot.x + plot.width / 2 + radius * Math.cos(angle) - width / 2, y: plot.y + plot.height / 2 + radius * Math.sin(angle) * .72 - height / 2, width, height };
                if (b.x < plot.x || b.y < plot.y || b.x + width > plot.x + plot.width || b.y + height > plot.y + plot.height)
                    continue;
                if (!occupied.some(a => a.x < b.x + b.width + 3 && a.x + a.width + 3 > b.x && a.y < b.y + b.height + 3 && a.y + a.height + 3 > b.y)) {
                    found = b;
                    break;
                }
            }
            if (!found) {
                scene.issue(`Word ${p.x} does not fit and is omitted.`, 'DDN-PJW04', 'warning', p.datum.source.ref);
                continue;
            }
            occupied.push(found);
            scene.add(`${p.x}: ${p.y}`, found, [(0, data_common_js_1.label)(String(p.x), found.x + width / 2, found.y + height / 2 + size * .35, size, { 'text-anchor': 'middle', fill: data_common_js_1.colors[index % data_common_js_1.colors.length], 'font-weight': 700 })], p.datum.source, p.datum.contributors);
        }
        scene.caption('Word size encodes weight; placement is deterministic and has no quantitative meaning.');
        return;
    }
    if (mark === 'densityheatmap' && (points.every(p => p.x === points[0]?.x) || points.every(p => p.y === points[0]?.y))) {
        scene.issue('Density heatmap is UNKNOWN when either coordinate has zero range.', 'DDN-PJ132');
        return;
    }
    if (mark === 'densityheatmap') {
        const count = (0, model_js_1.num)(scene.settings.bin_count, 20);
        if (!Number.isInteger(count) || count < 2 || count > 60) {
            scene.issue('Density heatmap requires 2..60 bins per axis.');
            return;
        }
        const xd = (0, data_common_js_1.extent)(points.map(p => Number(p.x))), yd = (0, data_common_js_1.extent)(points.map(p => p.y)), groups = new Map();
        for (const p of points) {
            const ix = Math.min(count - 1, Math.floor((Number(p.x) - xd[0]) / (xd[1] - xd[0]) * count)), iy = Math.min(count - 1, Math.floor((p.y - yd[0]) / (yd[1] - yd[0]) * count)), key = `${ix}:${iy}`;
            groups.set(key, [...groups.get(key) ?? [], p]);
        }
        const maximum = Math.max(...[...groups.values()].map(p => p.length));
        scene.intensity([0, maximum], 'observations / bin');
        const axes = [];
        for (let i = 0; i <= 5; i++)
            axes.push((0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(xd[0], xd[1], i / 5)), plot.x + plot.width * i / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(yd[0], yd[1], i / 5)), plot.x - 7, plot.y + plot.height * (1 - i / 5) + 4, 10, { 'text-anchor': 'end' }));
        scene.add('Density heatmap axes', plot, axes);
        scene.caption(`${count} × ${count} bins; color encodes observation count; empty bins are blank.`);
        for (const [key, values] of groups) {
            const [ix, iy] = key.split(':').map(Number), b = { x: plot.x + ix * plot.width / count, y: plot.y + (count - 1 - iy) * plot.height / count, width: plot.width / count, height: plot.height / count };
            scene.add(`Bin ${key}: ${values.length}`, b, [(0, data_common_js_1.box)(b, (0, data_common_js_1.colorScale)(values.length, [0, maximum]), '#fff')], values[0].datum.source, values.flatMap(p => p.datum.contributors));
        }
        return;
    }
    const domain = (0, data_common_js_1.extent)(points.map(p => p.y));
    scene.intensity(domain, (0, model_js_1.str)(scene.settings.unit));
    if (mark === 'calendar') {
        if (new Set(points.map(p => new Date(Number(p.x)).toISOString().slice(0, 10))).size !== points.length) {
            scene.issue('Calendar has more than one value for a UTC day.');
            return;
        }
        const minimum = Math.min(...points.map(p => Number(p.x))), maximum = Math.max(...points.map(p => Number(p.x))), day = 86400000, midnight = Math.floor(minimum / day) * day, start = midnight - ((new Date(midnight).getUTCDay() + 6) % 7) * day, weeks = Math.floor((maximum - start) / (7 * day)) + 1, cell = Math.min(28, plot.width / weeks, plot.height / 7);
        if (weeks > 5220) {
            scene.issue('Calendar span exceeds 100 years.');
            return;
        }
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].forEach((dayName, i) => scene.add(dayName, { x: plot.x - 32, y: plot.y + i * cell, width: 30, height: cell }, [(0, data_common_js_1.label)(dayName, plot.x - 6, plot.y + (i + .65) * cell, 10, { 'text-anchor': 'end' })]));
        let month = '';
        for (let week = 0; week < weeks; week++) {
            const date = new Date(start + week * 7 * day), name = date.toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
            if (name !== month) {
                scene.add(name, { x: plot.x + week * cell, y: plot.y - 24, width: cell, height: 20 }, [(0, data_common_js_1.label)(name, plot.x + week * cell, plot.y - 10, 10)]);
                month = name;
            }
        }
        scene.caption('Monday-first calendar; UTC days; color encodes value; missing days are blank.');
        if (scene.settings.iso)
            for (let week = 0; week < weeks; week++) {
                const monday = start + week * 7 * day, thursday = new Date(monday + 3 * day), year = thursday.getUTCFullYear(), january4 = Date.UTC(year, 0, 4), weekOne = january4 - ((new Date(january4).getUTCDay() + 6) % 7) * day, number = 1 + Math.round((monday - weekOne) / (7 * day));
                scene.add(`ISO week ${year}-W${String(number).padStart(2, '0')}`, { x: plot.x + week * cell, y: plot.y - 18, width: cell, height: 18 }, [(0, data_common_js_1.label)(`W${number}`, plot.x + (week + .5) * cell, plot.y - 5, 9, { 'text-anchor': 'middle' })]);
            }
        points.forEach(p => { const index = Math.floor((Number(p.x) - start) / day), b = { x: plot.x + Math.floor(index / 7) * cell, y: plot.y + index % 7 * cell, width: cell - 1, height: cell - 1 }; scene.add(`${new Date(Number(p.x)).toISOString().slice(0, 10)}: ${p.y}`, b, [(0, data_common_js_1.box)(b, (0, data_common_js_1.colorScale)(p.y, domain), '#fff')], p.datum.source, p.datum.contributors); });
        return;
    }
    const columns = (0, data_common_js_1.unique)(points.map(p => String(p.x))), rows = (0, data_common_js_1.unique)(points.map(p => p.series));
    if (columns.length > 60 || rows.length > 60) {
        scene.issue('Heatmap is bounded to 60 by 60 cells.');
        return;
    }
    if (new Set(points.map(p => JSON.stringify([p.x, p.series]))).size !== points.length) {
        scene.issue('Heatmap has duplicate category/series cells.');
        return;
    }
    scene.caption('Color encodes cell value; missing category/series pairs are blank.');
    const width = plot.width / Math.max(1, columns.length), height = plot.height / Math.max(1, rows.length);
    columns.forEach((c, i) => scene.add(c, plot, [(0, data_common_js_1.label)(c, plot.x + (i + .5) * width, plot.y + plot.height + 16, 11, { 'text-anchor': 'middle' })]));
    rows.forEach((r, i) => scene.add(r, plot, [(0, data_common_js_1.label)(r, plot.x - 6, plot.y + (i + .5) * height, 11, { 'text-anchor': 'end' })]));
    points.forEach(p => { const b = { x: plot.x + columns.indexOf(String(p.x)) * width, y: plot.y + rows.indexOf(p.series) * height, width, height }; scene.add(`${p.x}, ${p.series}: ${p.y}`, b, [(0, data_common_js_1.box)(b, (0, data_common_js_1.colorScale)(p.y, domain), '#fff'), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)(p.y), b.x + width / 2, b.y + height / 2 + 4, 11, { 'text-anchor': 'middle' })], p.datum.source, p.datum.contributors); });
}

},
"presentation/src/data-hierarchy.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.hierarchy = hierarchy;
exports.drawHierarchy = drawHierarchy;
exports.forcePositions = forcePositions;
exports.drawLinks = drawLinks;
exports.radialHierarchyPositions = radialHierarchyPositions;
const model_js_1 = require("presentation/src/model.js");
const data_common_js_1 = require("presentation/src/data-common.js");
function hierarchy(records) {
    const root = { key: '', name: '', children: [], value: 0, records: [], depth: 0, slot: 0, radius: 0, x: 0, y: 0 };
    for (const record of records) {
        const name = (0, model_js_1.str)(record.values.label), value = record.values.value;
        if (!name || name.split('.').some(part => !part) || !(0, data_common_js_1.finite)(value) || value < 0)
            throw new Error('Hierarchy needs nonempty dotted paths and nonnegative finite leaf weights.');
        let node = root;
        const parts = name.split('.');
        if (parts.length > 3)
            throw new Error('Hierarchy depth exceeds three levels.');
        for (const part of parts) {
            if (node.records.length)
                throw new Error('A declared hierarchy leaf cannot also be a parent.');
            const key = node.key ? `${node.key}.${part}` : part;
            let next = node.children.find(child => child.key === key);
            if (!next) {
                next = { key, name: part, children: [], value: 0, records: [], depth: node.depth + 1, slot: 0, radius: 0, x: 0, y: 0 };
                node.children.push(next);
            }
            node = next;
        }
        if (node.children.length || node.records.length)
            throw new Error('Hierarchy paths must identify unique leaves.');
        node.records.push(record);
        node.value = value;
    }
    let leaf = 0;
    const calculate = (node) => {
        node.children.forEach(calculate);
        if (node.children.length) {
            node.value = (0, data_common_js_1.sum)(node.children.map(c => c.value));
            node.records = node.children.flatMap(c => c.records);
            node.slot = (node.children[0].slot + node.children.at(-1).slot) / 2;
        }
        else
            node.slot = leaf++;
    };
    calculate(root);
    return root;
}
function drawHierarchy(scene, mark, data) {
    let root;
    try {
        root = hierarchy(data);
    }
    catch (error) {
        scene.issue(String(error));
        return;
    }
    if (!(root.value > 0) || !(0, data_common_js_1.finite)(root.value)) {
        scene.issue('The hierarchy needs a positive total weight.');
        return;
    }
    const displayDepth = scene.settings.iso === true ? 3 : (0, model_js_1.num)(scene.settings.depth, 3);
    if (!Number.isInteger(displayDepth) || displayDepth < 0 || displayDepth > 3) {
        scene.issue('Hierarchy display depth must be an integer in 0..3.');
        return;
    }
    if (displayDepth === 0) {
        scene.add(`Hierarchy summary: ${root.value}`, scene.bounds, [(0, data_common_js_1.box)(scene.bounds, '#eff6ff'), (0, data_common_js_1.label)(`Total ${root.value}`, scene.bounds.x + scene.bounds.width / 2, scene.bounds.y + scene.bounds.height / 2, 18, { 'text-anchor': 'middle' })], root.records[0].source, root.records.flatMap(record => record.contributors), 'Collapsed display at depth zero; all source contributors are retained.');
        return;
    }
    const collapse = (node) => {
        if (node.depth >= displayDepth)
            node.children = [];
        else
            node.children.forEach(collapse);
    };
    collapse(root);
    let nextSlot = 0;
    const slots = (node) => { node.children.forEach(slots); node.slot = node.children.length ? (node.children[0].slot + node.children.at(-1).slot) / 2 : nextSlot++; };
    slots(root);
    const bounds = { ...scene.bounds, x: scene.bounds.x + 24, y: scene.bounds.y + 24, width: Math.max(80, scene.bounds.width - 48), height: Math.max(80, scene.bounds.height - 88) }, all = [];
    const collect = (node) => { all.push(node); node.children.forEach(collect); };
    collect(root);
    const maximumDepth = Math.max(...all.map(n => n.depth));
    const sources = (node) => node.records.flatMap(r => r.contributors);
    const leaves = all.filter(node => !node.children.length), fill = (node) => data_common_js_1.colors[Math.max(0, node.children.length ? root.children.indexOf(node) : leaves.findIndex(leaf => leaf.key === node.key)) % data_common_js_1.colors.length];
    const valueLabel = (node) => `${(0, data_common_js_1.numberLabel)(node.value)}${scene.settings.unit ? ' ' + scene.settings.unit : ''}`;
    if (mark === 'treemap') {
        const draw = (node, b) => {
            if (node !== root) {
                const title = `${node.name}: ${valueLabel(node)}`;
                const lines = b.width >= 18 ? scene.wrap(title, b.width - 10, 11).slice(0, Math.max(0, Math.floor((b.height - 5) / 14))) : [];
                scene.add(`${node.key}: ${node.value}`, b, [(0, data_common_js_1.box)(b, node.children.length ? '#edf2f8' : fill(node), '#fff', { 'fill-opacity': node.children.length ? 1 : .8, 'stroke-width': 2 }), ...lines.map((line, i) => (0, data_common_js_1.label)(line, b.x + 5, b.y + 15 + i * 14, 11, { fill: node.children.length ? '#243449' : '#ffffff' }))], node.records[0].source, sources(node));
            }
            if (node !== root && node.children.length) {
                const header = Math.min(b.height, Math.max(24, scene.wrap(`${node.name}: ${valueLabel(node)}`, Math.max(8, b.width - 10), 11).length * 14 + 10));
                b = { ...b, y: b.y + header, height: Math.max(0, b.height - header) };
            }
            let offset = 0;
            const horizontal = node.depth % 2 === 0;
            for (const child of node.children) {
                const share = node.value ? child.value / node.value : 0, childBounds = horizontal ? { x: b.x + offset, y: b.y, width: b.width * share, height: b.height } : { x: b.x, y: b.y + offset, width: b.width, height: b.height * share };
                offset += horizontal ? childBounds.width : childBounds.height;
                if (share)
                    draw(child, childBounds);
            }
        };
        draw(root, bounds);
        scene.caption('Rectangle area encodes weight; header strips identify parent groups.');
        return;
    }
    if (mark === 'tidytree' || mark === 'radialtree') {
        const leaves = all.filter(n => !n.children.length).length, radius = Math.min(bounds.width, bounds.height) * .42;
        const position = (node) => mark === 'tidytree' ? [bounds.x + (node.slot + .5) * bounds.width / leaves, maximumDepth === 1 ? bounds.y + bounds.height / 2 : bounds.y + 12 + (node.depth - 1) * (bounds.height - 50) / (maximumDepth - 1)] : [bounds.x + bounds.width / 2 + Math.cos((node.slot + .5) / leaves * Math.PI * 2 - Math.PI / 2) * node.depth / maximumDepth * radius, bounds.y + bounds.height / 2 + Math.sin((node.slot + .5) / leaves * Math.PI * 2 - Math.PI / 2) * node.depth / maximumDepth * radius];
        for (const node of all.filter(node => node !== root)) {
            const p = position(node);
            for (const child of node.children) {
                const q = position(child);
                scene.add(`${node.key || 'root'} → ${child.key}`, (0, data_common_js_1.boundsOf)([p, q]), [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)([p, q]), fill(child))], child.records[0].source, sources(child));
            }
            scene.add(node.key || 'root', { x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, [(0, data_common_js_1.ellipse)(p[0], p[1], node.children.length ? 6 : 4, node.children.length ? '#1E2D43' : fill(node)), (0, data_common_js_1.label)(node.name, p[0], p[1] + 20, 11, { 'text-anchor': 'middle' })], node.records[0].source, sources(node));
        }
        scene.caption(`${mark === 'radialtree' ? 'Radial' : 'Tidy'} hierarchy; named roots remain separate; position encodes hierarchy, not weight.`);
        return;
    }
    if (mark === 'sunburst') {
        const cx = bounds.x + bounds.width / 2, cy = bounds.y + bounds.height / 2, ring = Math.min(bounds.width, bounds.height) / (2 * Math.max(1, maximumDepth));
        const draw = (node, start, end) => {
            if (node !== root && end > start)
                scene.add(`${node.key}: ${node.value}`, bounds, [(0, data_common_js_1.path)((0, data_common_js_1.arcPath)(cx, cy, ring * node.depth, start, end, ring * (node.depth - 1)), '#fff', fill(node), { 'fill-opacity': .45 + .5 * node.depth / maximumDepth }), (0, data_common_js_1.label)(node.name, cx + Math.cos((start + end) / 2) * ring * (node.depth - .5), cy + Math.sin((start + end) / 2) * ring * (node.depth - .5) + 4, 11, { 'text-anchor': 'middle' })], node.records[0].source, sources(node));
            let angle = start;
            for (const child of node.children) {
                const next = angle + (end - start) * child.value / node.value;
                if (child.value)
                    draw(child, angle, next);
                angle = next;
            }
        };
        draw(root, -Math.PI / 2, Math.PI * 1.5);
        scene.caption('Sector angle encodes weight; concentric rings encode hierarchy depth.');
        return;
    }
    const pack = (node) => {
        node.children.forEach(pack);
        if (!node.children.length) {
            node.radius = Math.sqrt(node.value / Math.PI);
            return;
        }
        const children = [...node.children].sort((a, b) => b.radius - a.radius || (a.key < b.key ? -1 : 1));
        if (children.length === 1) {
            children[0].x = children[0].y = 0;
            node.radius = children[0].radius * 1.08;
            return;
        }
        const maximum = Math.max(...children.map(c => c.radius)), circumference = (0, data_common_js_1.sum)(children.map(c => 2 * c.radius + maximum * .1)), ring = Math.max(maximum * 1.05 / Math.sin(Math.PI / children.length), circumference / (2 * Math.PI));
        let angle = 0;
        for (const child of children) {
            const halfAngle = Math.asin(Math.min(1, (child.radius + maximum * .05) / ring));
            angle += halfAngle;
            child.x = ring * Math.cos(angle);
            child.y = ring * Math.sin(angle);
            angle += halfAngle;
        }
        node.radius = (ring + maximum) * 1.06;
    };
    if (mark === 'packedbubble' && data.some(datum => (0, model_js_1.str)(datum.values.label).includes('.'))) {
        const grouped = new Map();
        for (const datum of data) {
            const group = (0, model_js_1.str)(datum.values.label).split('.')[0];
            grouped.set(group, [...grouped.get(group) ?? [], datum]);
        }
        root.children = [...grouped].map(([name, rows], i) => ({ key: name, name, value: (0, data_common_js_1.sum)(rows.map(r => (0, model_js_1.num)(r.values.value))), records: rows, depth: 1, slot: i, radius: 0, x: 0, y: 0, children: rows.map((row, index) => ({ key: (0, model_js_1.str)(row.values.label), name: (0, model_js_1.str)(row.values.label).split('.').at(-1), value: (0, model_js_1.num)(row.values.value), records: [row], depth: 2, slot: index, radius: 0, x: 0, y: 0, children: [] })) }));
        collapse(root);
    }
    pack(root);
    const groupWidth = (0, data_common_js_1.sum)(root.children.map(child => 2 * child.radius)), gap = 24;
    const factor = Math.min((bounds.width - gap * Math.max(0, root.children.length - 1)) / Math.max(1, groupWidth), (bounds.height - 40) / Math.max(1, 2 * Math.max(...root.children.map(child => child.radius))));
    const draw = (node, x, y) => {
        if (node !== root && (mark === 'circlepack' || !node.children.length))
            scene.add(`${node.key}: ${node.value}`, { x: x - node.radius * factor, y: y - node.radius * factor, width: node.radius * factor * 2, height: node.radius * factor * 2 }, [(0, data_common_js_1.ellipse)(x, y, node.radius * factor, node.children.length ? '#ffffff' : fill(node), { 'fill-opacity': node.children.length ? 0 : .78, stroke: node.children.length ? '#C6D5E6' : '#ffffff' }), ...(!node.children.length ? [(0, data_common_js_1.label)(node.name, x, y + (mark === 'packedbubble' ? -3 : 4), 10, { 'text-anchor': 'middle' }), ...(mark === 'packedbubble' ? [(0, data_common_js_1.label)(valueLabel(node), x, y + 13, 10, { 'text-anchor': 'middle' })] : [])] : [])], node.records[0].source, sources(node), node.children.length ? 'Padded approximate container; area is not the sum of child areas.' : 'Leaf area encodes weight.');
        for (const child of node.children)
            draw(child, x + child.x * factor, y + child.y * factor);
    };
    let left = bounds.x + (bounds.width - groupWidth * factor - gap * (root.children.length - 1)) / 2;
    for (const child of root.children) {
        const x = left + child.radius * factor, y = bounds.y + bounds.height / 2;
        draw(child, x, y);
        if (child.children.length)
            scene.add(`${child.name} total`, { x: left, y: y - child.radius * factor - 25, width: child.radius * factor * 2, height: 20 }, [(0, data_common_js_1.label)(`${child.name}: ${valueLabel(child)}`, x, y - child.radius * factor - 10, 12, { 'text-anchor': 'middle' })]);
        left += 2 * child.radius * factor + gap;
    }
    scene.caption('Leaf circle area encodes weight; parent outlines group leaves and include packing space.');
}
function forcePositions(names, links, width, height) {
    let seed = 0xB1024;
    const random = () => { seed = (seed + 0x6D2B79F5) | 0; let word = Math.imul(seed ^ seed >>> 15, seed | 1); word ^= word + Math.imul(word ^ word >>> 7, word | 61); return ((word ^ word >>> 14) >>> 0) / 4294967296; };
    const positions = names.map(() => [random() * 2 - 1, random() * 2 - 1]);
    const index = new Map(names.map((name, i) => [name, i])), k = Math.sqrt(4 / Math.max(1, names.length));
    for (let iteration = 0; iteration < 300; iteration++) {
        const displacement = names.map(() => [0, 0]);
        for (let a = 0; a < names.length; a++)
            for (let b = a + 1; b < names.length; b++) {
                const dx = positions[a][0] - positions[b][0], dy = positions[a][1] - positions[b][1], distance = Math.max(1e-6, Math.hypot(dx, dy)), force = k * k / distance;
                displacement[a][0] += dx / distance * force;
                displacement[a][1] += dy / distance * force;
                displacement[b][0] -= dx / distance * force;
                displacement[b][1] -= dy / distance * force;
            }
        for (const link of links) {
            const a = index.get(link.source), b = index.get(link.target), dx = positions[a][0] - positions[b][0], dy = positions[a][1] - positions[b][1], distance = Math.max(1e-6, Math.hypot(dx, dy)), force = distance * distance / k;
            displacement[a][0] -= dx / distance * force;
            displacement[a][1] -= dy / distance * force;
            displacement[b][0] += dx / distance * force;
            displacement[b][1] += dy / distance * force;
        }
        const temperature = .1 * (1 - iteration / 300);
        positions.forEach((point, i) => {
            const d = displacement[i], length = Math.max(1e-6, Math.hypot(d[0], d[1]));
            point[0] += d[0] / length * Math.min(length, temperature);
            point[1] += d[1] / length * Math.min(length, temperature);
        });
    }
    const xs = positions.map(point => point[0]), ys = positions.map(point => point[1]), lowX = Math.min(...xs), lowY = Math.min(...ys), spanX = Math.max(...xs) - lowX || 1, spanY = Math.max(...ys) - lowY || 1, padX = Math.min(70, width * .15), padY = Math.min(35, height * .15);
    return new Map(names.map((name, i) => [name, [padX + (positions[i][0] - lowX) / spanX * (width - 2 * padX), padY + (positions[i][1] - lowY) / spanY * (height - 2 * padY)]]));
}
function drawLinks(scene, mark, data) {
    const links = data.map(datum => ({ datum, source: (0, model_js_1.str)(datum.values.source), target: (0, model_js_1.str)(datum.values.target), value: (0, model_js_1.num)(datum.values.value) }));
    if (links.some(link => !link.source || !link.target || link.source === link.target || !(link.value > 0))) {
        scene.issue('Weighted links require distinct nonempty endpoints and positive finite weights.');
        return;
    }
    const names = (0, data_common_js_1.unique)(links.flatMap(link => [link.source, link.target])), bound = mark === 'edgebundle' ? 500 : 1000;
    if (names.length > 200 || links.length > bound) {
        scene.issue(`Link projection exceeds 200 nodes or ${bound} links.`);
        return;
    }
    const b = { x: scene.bounds.x + 72, y: scene.bounds.y + 32, width: Math.max(80, scene.bounds.width - 144), height: Math.max(80, scene.bounds.height - 100) }, weights = new Map(names.map(name => [name, (0, data_common_js_1.sum)(links.filter(l => l.source === name || l.target === name).map(l => l.value))])), maximumWeight = Math.max(...weights.values(), 1), maximumLink = Math.max(...links.map(l => l.value), 1);
    if (mark === 'sankey') {
        const indegree = new Map(names.map(name => [name, links.filter(l => l.target === name).length])), depth = new Map(names.map(name => [name, 0])), queue = names.filter(name => indegree.get(name) === 0);
        let processed = 0;
        while (queue.length) {
            const name = queue.shift();
            processed++;
            for (const link of links.filter(l => l.source === name)) {
                depth.set(link.target, Math.max(depth.get(link.target), depth.get(name) + 1));
                indegree.set(link.target, indegree.get(link.target) - 1);
                if (indegree.get(link.target) === 0)
                    queue.push(link.target);
            }
        }
        if (processed !== names.length) {
            scene.issue('Sankey flows must form a directed acyclic graph.');
            return;
        }
        const columns = Math.max(...depth.values(), 0), heights = new Map(names.map(name => [name, Math.max((0, data_common_js_1.sum)(links.filter(l => l.source === name).map(l => l.value)), (0, data_common_js_1.sum)(links.filter(l => l.target === name).map(l => l.value)))])), levels = Array.from({ length: columns + 1 }, (_, i) => names.filter(name => depth.get(name) === i)), gap = Math.min(16, b.height / (2 * Math.max(...levels.map(level => level.length), 1))), factor = Math.min(...levels.map(level => (b.height - Math.max(0, level.length - 1) * gap) / (0, data_common_js_1.sum)(level.map(name => heights.get(name))))), positions = new Map();
        for (const [index, level] of levels.entries()) {
            let y = b.y;
            for (const name of level) {
                const bounds = { x: b.x + index * (b.width - 18) / Math.max(1, columns), y, width: 18, height: heights.get(name) * factor };
                positions.set(name, bounds);
                y += bounds.height + gap;
            }
        }
        const out = new Map(names.map(name => [name, 0])), incoming = new Map(out);
        for (const link of links) {
            const a = positions.get(link.source), target = positions.get(link.target), thickness = link.value * factor, y1 = a.y + out.get(link.source) + thickness / 2, y2 = target.y + incoming.get(link.target) + thickness / 2, x1 = a.x + a.width, x2 = target.x;
            out.set(link.source, out.get(link.source) + thickness);
            incoming.set(link.target, incoming.get(link.target) + thickness);
            scene.add(`${link.source} → ${link.target}: ${link.value}`, (0, data_common_js_1.boundsOf)([[x1, y1], [x2, y2]], thickness / 2), [(0, data_common_js_1.path)(`M${x1},${y1}C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`, data_common_js_1.colors[links.indexOf(link) % data_common_js_1.colors.length], 'none', { 'stroke-width': thickness, 'stroke-opacity': .45 })], link.datum.source, link.datum.contributors);
        }
        for (const name of names) {
            const bounds = positions.get(name);
            scene.add(name, bounds, [(0, data_common_js_1.box)(bounds, '#1E2D43', 'none'), (0, data_common_js_1.label)(`${name}: ${(0, data_common_js_1.numberLabel)(heights.get(name))}${scene.settings.unit ? ' ' + scene.settings.unit : ''}`, depth.get(name) === columns ? bounds.x - 8 : bounds.x + 26, bounds.y + bounds.height / 2 + 4, 11, { 'text-anchor': depth.get(name) === columns ? 'end' : 'start' })], links.find(l => l.source === name || l.target === name).datum.source, links.filter(l => l.source === name || l.target === name).flatMap(l => l.datum.contributors));
        }
        scene.caption('Ribbon thickness encodes flow; node totals are the greater of incoming and outgoing flow.');
        return;
    }
    let positions;
    let hierarchyPositions;
    if (mark === 'force')
        positions = new Map([...forcePositions(names, links, b.width, b.height)].map(([name, point]) => [name, [point[0] + b.x, point[1] + b.y]]));
    else if (mark === 'arc') {
        const ordered = [...names].sort((a, c) => weights.get(c) - weights.get(a) || (a < c ? -1 : a > c ? 1 : 0));
        const x = new Map(ordered.map((name, i) => [name, b.x + (i + .5) * b.width / ordered.length]));
        const upper = Math.max(0, ...links.filter(link => x.get(link.target) > x.get(link.source)).map(link => Math.abs(x.get(link.target) - x.get(link.source)) / 2));
        const lower = Math.max(0, ...links.filter(link => x.get(link.target) < x.get(link.source)).map(link => Math.abs(x.get(link.target) - x.get(link.source)) / 2));
        const baseline = b.y + upper + 12;
        b.height = upper + lower + 48;
        positions = new Map(ordered.map(name => [name, [x.get(name), baseline]]));
        scene.add('Arc node axis', b, [(0, data_common_js_1.path)(`M${b.x},${baseline}H${b.x + b.width}`, '#1E2D43', 'none', { 'stroke-width': 1 })]);
    }
    else {
        if (names.some(name => name.split('.').length > 3)) {
            scene.issue('Edge bundles are bounded to three hierarchy levels.');
            return;
        }
        hierarchyPositions = radialHierarchyPositions(names, b);
        positions = new Map(names.map(name => [name, hierarchyPositions.get(name)]));
    }
    for (const link of links) {
        const a = positions.get(link.source), target = positions.get(link.target), width = 1 + (mark === 'edgebundle' ? 2.5 : mark === 'arc' ? 5 : 4) * link.value / maximumLink;
        let d;
        if (mark === 'arc') {
            const radius = Math.abs(target[0] - a[0]) / 2;
            d = `M${a[0]},${a[1]}A${radius},${radius} 0 0 1 ${target[0]},${target[1]}`;
        }
        else if (mark === 'edgebundle') {
            const source = link.source.split('.'), dest = link.target.split('.');
            let common = 0;
            while (common < source.length && source[common] === dest[common])
                common++;
            const route = [];
            for (let depth = source.length; depth >= common; depth--)
                route.push(hierarchyPositions.get(source.slice(0, depth).join('.')));
            for (let depth = common + 1; depth <= dest.length; depth++)
                route.push(hierarchyPositions.get(dest.slice(0, depth).join('.')));
            d = `M${route[0][0]},${route[0][1]}`;
            for (let i = 1; i < route.length - 1; i++) {
                const current = route[i], next = route[i + 1];
                d += `Q${current[0]},${current[1]} ${(current[0] + next[0]) / 2},${(current[1] + next[1]) / 2}`;
            }
            d += `L${route.at(-1)[0]},${route.at(-1)[1]}`;
        }
        else
            d = (0, data_common_js_1.pointsPath)([a, target]);
        scene.add(`${link.source} → ${link.target}: ${link.value}`, b, [(0, data_common_js_1.path)(d, mark === 'force' ? '#CBD7E6' : data_common_js_1.colors[links.indexOf(link) % data_common_js_1.colors.length], 'none', { 'stroke-width': width, 'stroke-opacity': mark === 'force' ? 1 : .6 })], link.datum.source, link.datum.contributors);
    }
    names.forEach((name, i) => {
        const p = positions.get(name), r = mark === 'edgebundle' ? 3.5 : (mark === 'force' ? 5 : 4) + (mark === 'force' ? 12 : 10) * Math.sqrt(weights.get(name) / maximumWeight), rows = links.filter(l => l.source === name || l.target === name);
        const angle = Math.atan2(p[1] - b.y - b.height / 2, p[0] - b.x - b.width / 2), outsideX = p[0] + Math.cos(angle) * 12, outsideY = p[1] + Math.sin(angle) * 12;
        scene.add(name, { x: p[0] - r, y: p[1] - r, width: r * 2, height: r * 2 }, [(0, data_common_js_1.ellipse)(p[0], p[1], r, mark === 'force' ? data_common_js_1.colors[i % data_common_js_1.colors.length] : '#1E2D43'), (0, data_common_js_1.label)(mark === 'edgebundle' ? name.split('.').at(-1) : name, mark === 'edgebundle' ? outsideX : p[0], mark === 'edgebundle' ? outsideY + 4 : p[1] + r + 16, 11, { 'text-anchor': mark === 'edgebundle' ? Math.cos(angle) < 0 ? 'end' : 'start' : 'middle' })], rows[0].datum.source, rows.flatMap(l => l.datum.contributors), 'Position has no quantitative meaning.');
    });
    scene.caption(mark === 'arc' ? `${names.length} nodes · ${links.length} links · nodes ordered by total weight; arc thickness encodes value; arc height encodes distance only.` : mark === 'edgebundle' ? 'Links follow smooth paths through their lowest common ancestor; thickness encodes weight.' : 'Deterministic force layout (seed 0xB1024); node size and link width encode weight; position has no quantitative meaning.');
}
function radialHierarchyPositions(names, bounds) {
    const root = { name: '', children: [], depth: 0, slot: 0 }, byName = new Map([['', root]]);
    for (const name of names) {
        let parent = root;
        for (const segment of name.split('.')) {
            const prefix = parent.name ? parent.name + '.' + segment : segment;
            let node = byName.get(prefix);
            if (!node) {
                node = { name: prefix, children: [], depth: parent.depth + 1, slot: 0 };
                parent.children.push(node);
                byName.set(prefix, node);
            }
            parent = node;
        }
    }
    let leaves = 0;
    const place = (node) => { node.children.forEach(place); node.slot = node.children.length ? (node.children[0].slot + node.children.at(-1).slot) / 2 : leaves++; };
    place(root);
    const maximum = Math.max(...[...byName.values()].map(node => node.depth)), radius = Math.min(bounds.width, bounds.height) * .4;
    return new Map([...byName].map(([name, node]) => { const angle = (node.slot + .5) / Math.max(1, leaves) * Math.PI * 2 - Math.PI / 2, r = node.depth / Math.max(1, maximum) * radius; return [name, [bounds.x + bounds.width / 2 + Math.cos(angle) * r, bounds.y + bounds.height / 2 + Math.sin(angle) * r]]; }));
}

},
"presentation/src/data-isometric.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.extrudeChart = extrudeChart;
const model_js_1 = require("presentation/src/model.js");
function extrudeChart(result, settings, depths = new Map()) {
    if (settings.iso !== true || result.unavailable.length)
        return result;
    const mark = (0, model_js_1.str)(settings.mark, 'bar');
    if (!['bar', 'area', 'pie', 'donut', 'treemap'].includes(mark))
        return result;
    let maximumDepth = 0;
    const sides = [];
    for (const entry of result.entries) {
        if (entry.definition.owner === 'view')
            continue;
        const depth = depths.get(entry.item.occurrence) ?? (typeof settings.depth === 'string' ? (0, model_js_1.num)((0, model_js_1.pathValue)(entry.definition.record, settings.depth), 0) : (0, model_js_1.num)(settings.depth, 18));
        if (depth === 0)
            continue;
        maximumDepth = Math.max(maximumDepth, depth);
        const dx = depth * Math.sqrt(3) / 2, dy = -depth / 2;
        const filled = entry.item.primitives.filter(primitive => primitive.kind !== 'text' && primitive.kind !== 'image' && primitive.paint?.fill && primitive.paint.fill !== 'none' && primitive.paint.fill !== 'transparent');
        const rectangles = filled.filter((primitive) => primitive.kind === 'rect');
        if (rectangles.length) {
            const primitives = rectangles.map(primitive => {
                const b = primitive.bounds, x = b.x, y = b.y, right = x + b.width, bottom = y + b.height;
                return { kind: 'path', d: `M${x},${y}L${x + dx},${y + dy}L${right + dx},${y + dy}L${right + dx},${bottom + dy}L${right},${bottom}L${x},${bottom}Z`, paint: { ...primitive.paint, fill: shade((0, model_js_1.str)(primitive.paint?.fill)), stroke: 'none' } };
            });
            sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth', hitTargets: [], primitives, bounds: { ...entry.item.bounds, y: entry.item.bounds.y + dy, width: entry.item.bounds.width + dx, height: entry.item.bounds.height - dy }, accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
        }
        const curves = filled.filter((primitive) => primitive.kind === 'path' || primitive.kind === 'ellipse');
        if (mark === 'area') {
            for (const primitive of curves) {
                if (primitive.kind !== 'path')
                    continue;
                const numbers = primitive.d.match(/[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/gi)?.map(Number) ?? [];
                const points = Array.from({ length: numbers.length / 4 }, (_, i) => [numbers[i * 2], numbers[i * 2 + 1]]);
                if (!points.length)
                    continue;
                const ribbon = [...points, ...[...points].reverse().map(([x, y]) => [x + dx, y + dy])];
                const side = { kind: 'path', d: 'M' + ribbon.map(point => point.join(',')).join('L') + 'Z', paint: { fill: shade((0, model_js_1.str)(primitive.paint.fill)), stroke: 'none', 'fill-opacity': .65, opacity: primitive.paint.opacity ?? 1 } };
                sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth', hitTargets: [], primitives: [side], bounds: { ...entry.item.bounds, y: entry.item.bounds.y + dy, width: entry.item.bounds.width + dx, height: entry.item.bounds.height - dy }, accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
            }
            continue;
        }
        if (curves.length)
            for (let step = 12; step >= 1; step--) {
                const m = entry.item.transform, amount = step / 12;
                sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth:' + step, hitTargets: [], transform: [m[0], m[1], m[2], m[3], m[4] + dx * amount, m[5] + dy * amount], primitives: curves.map(primitive => ({ ...primitive, paint: { ...primitive.paint, fill: shade((0, model_js_1.str)(primitive.paint?.fill)), stroke: 'none' } })), accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
            }
    }
    const firstMark = Math.max(0, result.entries.findIndex(entry => entry.definition.owner !== 'view'));
    return { ...result, entries: [...result.entries.slice(0, firstMark), ...sides, ...result.entries.slice(firstMark)], bounds: { ...result.bounds, y: result.bounds.y - maximumDepth / 2, width: result.bounds.width + maximumDepth * Math.sqrt(3) / 2, height: result.bounds.height + maximumDepth / 2 } };
}
function shade(color) {
    const match = /^#([0-9a-f]{6})$/i.exec(color);
    if (match)
        return '#' + [0, 2, 4].map(index => Math.round(parseInt(match[1].slice(index, index + 2), 16) * .62).toString(16).padStart(2, '0')).join('');
    const rgb = /^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/.exec(color);
    return rgb ? `rgb(${rgb.slice(1).map(value => Math.round(Number(value) * .62)).join(',')})` : '#475569';
}

},
"presentation/src/data-quality.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.boundaryHistogram = boundaryHistogram;
exports.paretoPlan = paretoPlan;
exports.waterfallPlan = waterfallPlan;
exports.drawQuality = drawQuality;
const model_js_1 = require("presentation/src/model.js");
const data_common_js_1 = require("presentation/src/data-common.js");
function boundaryHistogram(values, boundaries, normalization = 'count', outside = 'error') {
    if (boundaries.length < 2 || boundaries.length > 101 || boundaries.some((value, index) => !(0, data_common_js_1.finite)(value) || index > 0 && value <= boundaries[index - 1]))
        throw new Error('Histogram needs 2..101 finite, strictly increasing bin boundaries.');
    if (!values.length || values.some(value => !(0, data_common_js_1.finite)(value)))
        throw new Error('Histogram needs finite measured values.');
    const bins = boundaries.slice(0, -1).map((low, index) => ({ low, high: boundaries[index + 1], count: 0, indices: [], value: 0 }));
    let selected = 0;
    values.forEach((raw, index) => {
        let value = raw;
        if (value < boundaries[0] || value > boundaries.at(-1)) {
            if (outside === 'error')
                throw new Error('A sample is outside the declared histogram boundaries.');
            if (outside === 'drop')
                return;
            if (outside !== 'clip')
                throw new Error('Unknown histogram outside policy.');
            value = Math.max(boundaries[0], Math.min(boundaries.at(-1), value));
        }
        const position = value === boundaries.at(-1) ? bins.length - 1 : bins.findIndex(bin => value >= bin.low && value < bin.high);
        const bin = bins[position];
        bin.count++;
        bin.indices.push(index);
        selected++;
    });
    if (!selected)
        throw new Error('Histogram boundaries excluded every sample.');
    if (!['count', 'probability', 'density'].includes(normalization))
        throw new Error('Unknown histogram normalization.');
    for (const bin of bins)
        bin.value = normalization === 'count' ? bin.count : normalization === 'probability' ? bin.count / selected : bin.count / selected / (bin.high - bin.low);
    return bins;
}
function paretoPlan(values) {
    if (!values.length || values.some(value => !(0, data_common_js_1.finite)(value.value) || value.value < 0))
        throw new Error('Pareto requires nonnegative finite category measurements.');
    const grouped = new Map();
    values.forEach((value, index) => {
        let item = grouped.get(value.label);
        if (!item) {
            item = { label: value.label, value: 0, indices: [], cumulative: 0, cumulativeIndices: [] };
            grouped.set(value.label, item);
        }
        item.value += value.value;
        item.indices.push(index);
    });
    const result = [...grouped.values()].sort((a, b) => b.value - a.value || a.indices[0] - b.indices[0]);
    const total = (0, data_common_js_1.sum)(result.map(value => value.value));
    if (!(0, data_common_js_1.finite)(total) || !(total > 0))
        throw new Error('Pareto needs a finite positive total.');
    let cumulative = 0;
    const indices = [];
    for (const item of result) {
        cumulative += item.value;
        indices.push(...item.indices);
        item.cumulative = cumulative / total * 100;
        item.cumulativeIndices = [...indices];
    }
    result.at(-1).cumulative = 100;
    return result;
}
function waterfallPlan(values, steps, baseline = 0) {
    if (!(0, data_common_js_1.finite)(baseline) || values.length !== steps.length || !values.length || values.some(value => !(0, data_common_js_1.finite)(value)))
        throw new Error('Waterfall requires finite measurements, matching step values and a finite baseline.');
    let running = baseline;
    const indices = [];
    return values.map((value, index) => {
        const kind = steps[index];
        if (kind !== 'delta' && kind !== 'subtotal' && kind !== 'total')
            throw new Error('Waterfall step values are delta, subtotal or total.');
        const before = running;
        if (kind === 'delta')
            running += value;
        else if (Math.abs(value - running) > 1e-10 * Math.max(1, Math.abs(value), Math.abs(running)))
            throw new Error('Waterfall subtotal/total differs from the running total.');
        if (!(0, data_common_js_1.finite)(running))
            throw new Error('Waterfall running total exceeds the finite numeric range.');
        indices.push(index);
        return { kind, start: kind === 'delta' ? before : 0, end: running, value, index, indices: [...indices] };
    });
}
function drawQuality(scene, mark, transform, data) {
    const options = scene.settings, authored = (0, model_js_1.object)((0, model_js_1.pathValue)(scene.view.record, 'projection.options'));
    for (const key of ['series', 'layers', 'arrangement', 'aggregate'])
        if (Object.hasOwn(authored, key))
            scene.issue(`The ${transform} transform does not admit an authored ${key} option.`);
    if (mark !== 'bar')
        scene.issue(`${transform} requires the bar mark.`);
    const yKey = (0, model_js_1.str)(options.y), xKey = (0, model_js_1.str)(options.x), stepKey = (0, model_js_1.str)(options.step);
    if (!yKey || transform !== 'histogram' && !xKey)
        scene.issue('Choose the required raw measurement and category bindings.');
    if (transform !== 'histogram' && (0, model_js_1.str)(options.x_type, 'category') !== 'category')
        scene.issue('This quality transform requires categorical x.');
    if (Array.isArray(options.bins) && (Object.hasOwn(authored, 'step') || Object.hasOwn(authored, 'bin_count') && authored.bin_count !== 'auto'))
        scene.issue('Explicit boundaries cannot also declare a bin step/count.');
    if (transform === 'waterfall' && !stepKey)
        scene.issue('Waterfall requires a step field binding.');
    const rows = data.filter(datum => !(options.missing === 'skip' && ((0, data_common_js_1.valueAt)(datum.values, yKey) == null || transform !== 'histogram' && (0, data_common_js_1.valueAt)(datum.values, xKey) == null)));
    for (const datum of rows) {
        if (!(0, data_common_js_1.finite)((0, data_common_js_1.valueAt)(datum.values, yKey)))
            scene.issue('Quality measurements must be finite numbers; numeric strings are not coerced.');
        const category = (0, data_common_js_1.valueAt)(datum.values, xKey);
        if (transform !== 'histogram' && typeof category !== 'string' && !(0, data_common_js_1.finite)(category))
            scene.issue('Quality category labels must be present scalar values.');
        if (options.unit && datum.values.unit !== undefined && datum.values.unit !== options.unit)
            scene.issue('Record unit differs from the declared chart unit.');
    }
    if (!rows.length)
        scene.issue('The quality transform needs at least one measured record.');
    if (scene.result.unavailable.length)
        return;
    const plot = { x: scene.bounds.x + 52, y: scene.bounds.y + 50, width: Math.max(80, (0, model_js_1.num)(options.width, scene.bounds.width) - 110), height: Math.max(80, (0, model_js_1.num)(options.height, scene.bounds.height) - 122) };
    const axes = (domain, categories, xDomain) => {
        const primitives = [(0, data_common_js_1.label)((0, model_js_1.str)(options.unit, yKey), plot.x, plot.y - 12, 11), (0, data_common_js_1.path)(`M${plot.x},${plot.y}V${plot.y + plot.height}H${plot.x + plot.width}`)];
        for (let i = 0; i <= 5; i++) {
            const y = plot.y + plot.height * (1 - i / 5);
            primitives.push((0, data_common_js_1.path)(`M${plot.x},${y}H${plot.x + plot.width}`, '#e2e8f0'), (0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(domain[0], domain[1], i / 5)), plot.x - 6, y + 4, 10, { 'text-anchor': 'end' }));
            if (xDomain)
                primitives.push((0, data_common_js_1.label)((0, data_common_js_1.numberLabel)((0, data_common_js_1.interpolate)(xDomain[0], xDomain[1], i / 5)), plot.x + i * plot.width / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
        }
        categories?.forEach((category, i) => primitives.push((0, data_common_js_1.label)(category, plot.x + (i + .5) * plot.width / categories.length, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' })));
        scene.add(`${transform} axes`, plot, primitives);
    };
    const contributing = (indices) => indices.flatMap(index => rows[index].contributors);
    try {
        if (transform === 'histogram') {
            const values = rows.map(datum => (0, data_common_js_1.valueAt)(datum.values, yKey)), descriptor = (0, model_js_1.object)(options.bins), normalization = options.normalize === true ? 'probability' : options.normalize === false ? 'count' : (0, model_js_1.str)(options.normalize, 'count');
            if (!Array.isArray(options.bins))
                throw new Error('Histogram transform requires explicit bin boundaries.');
            const bins = boundaryHistogram(values, options.bins, normalization, (0, model_js_1.str)(options.outside, 'error'));
            const xd = [bins[0].low, bins.at(-1).high], yd = (0, data_common_js_1.extent)(bins.map(bin => bin.value), true), xs = (0, data_common_js_1.scale)(xd, [plot.x, plot.x + plot.width]), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]);
            axes(yd, undefined, xd);
            bins.forEach(bin => { const width = xs(bin.high) - xs(bin.low), bounds = { x: xs(bin.low), y: ys(bin.value), width: width * .96, height: plot.y + plot.height - ys(bin.value) }; scene.add(`${bin.low}–${bin.high}: ${bin.value}`, bounds, [(0, data_common_js_1.box)(bounds, data_common_js_1.colors[0], 'none')], rows[bin.indices[0]]?.source ?? scene.view, contributing(bin.indices), `${bin.count} measurements; ${normalization}; final upper boundary included`); });
        }
        else if (transform === 'pareto') {
            const values = paretoPlan(rows.map(datum => ({ label: String((0, data_common_js_1.valueAt)(datum.values, xKey)), value: (0, data_common_js_1.valueAt)(datum.values, yKey) }))), yd = (0, data_common_js_1.extent)(values.map(value => value.value), true), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]), band = plot.width / values.length, percent = (0, data_common_js_1.scale)([0, 100], [plot.y + plot.height, plot.y]);
            axes(yd, values.map(value => value.label));
            const line = [];
            values.forEach((value, index) => {
                const x = plot.x + (index + .5) * band, bounds = { x: x - band * .4, y: ys(value.value), width: band * .8, height: plot.y + plot.height - ys(value.value) };
                scene.add(`${value.label}: ${value.value}`, bounds, [(0, data_common_js_1.box)(bounds, data_common_js_1.colors[index % data_common_js_1.colors.length], 'none')], rows[value.indices[0]].source, contributing(value.indices));
                const y = percent(value.cumulative);
                line.push([x, y]);
                scene.add(`Cumulative ${value.cumulative}%`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [(0, data_common_js_1.ellipse)(x, y, 4, '#dc2626')], rows[value.indices[0]].source, contributing(value.cumulativeIndices), 'Cumulative percentage of supplied measurements; prefix contributors retained.');
            });
            scene.add('Pareto cumulative percentage', plot, [(0, data_common_js_1.path)((0, data_common_js_1.pointsPath)(line), '#dc2626'), ...[0, 25, 50, 75, 100].map(value => (0, data_common_js_1.label)(`${value}%`, plot.x + plot.width + 6, percent(value) + 4, 10))], rows[0].source, rows.flatMap(row => row.contributors));
        }
        else if (transform === 'waterfall') {
            const categories = rows.map(datum => String((0, data_common_js_1.valueAt)(datum.values, xKey)));
            if ((0, data_common_js_1.unique)(categories).length !== categories.length)
                throw new Error('Waterfall requires distinct ordered stage labels.');
            const values = waterfallPlan(rows.map(datum => (0, data_common_js_1.valueAt)(datum.values, yKey)), rows.map(datum => (0, data_common_js_1.valueAt)(datum.values, stepKey)), (0, model_js_1.num)(options.baseline, 0)), yd = (0, data_common_js_1.extent)(values.flatMap(value => [value.start, value.end]), true), ys = (0, data_common_js_1.scale)(yd, [plot.y + plot.height, plot.y]), band = plot.width / values.length;
            axes(yd, categories);
            values.forEach((value, index) => {
                const x = plot.x + (index + .5) * band, bounds = { x: x - band * .4, y: ys(Math.max(value.start, value.end)), width: band * .8, height: Math.max(1, Math.abs(ys(value.start) - ys(value.end))) }, color = value.kind === 'total' ? data_common_js_1.colors[3] : value.kind === 'subtotal' ? data_common_js_1.colors[0] : value.value >= 0 ? data_common_js_1.colors[1] : data_common_js_1.colors[2];
                const primitives = [(0, data_common_js_1.box)(bounds, color, 'none')];
                if (index < values.length - 1)
                    primitives.push((0, data_common_js_1.path)(`M${x + band * .4},${ys(value.end)}H${x + band * .6}`, '#64748b', 'none', { 'stroke-dasharray': '3 2' }));
                scene.add(`${categories[index]}: ${value.kind} ${value.value}`, bounds, primitives, rows[index].source, contributing(value.indices), `From ${value.start} to ${value.end}; totals are not additional deltas.`);
            });
        }
        scene.caption(transform === 'histogram' ? 'Explicit bins; left inclusive, right exclusive except final upper boundary; ' + (0, model_js_1.str)(options.normalize, 'count') : transform === 'pareto' ? 'Descending measurements; line shows cumulative percentage.' : 'Running totals; deltas change the total, subtotals and totals summarize it.');
    }
    catch (error) {
        scene.issue(String(error));
    }
}

},
"presentation/src/data-statistics.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.quantileContributors = quantileContributors;
exports.histogramBins = histogramBins;
exports.kernelDensity = kernelDensity;
exports.inverseNormal = inverseNormal;
exports.fiveNumber = fiveNumber;
exports.linearTrend = linearTrend;
exports.loessTrend = loessTrend;
exports.histogramPlan = histogramPlan;
const data_common_js_1 = require("presentation/src/data-common.js");
function quantileContributors(values, probability) {
    const ordered = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value || a.index - b.index);
    if (!ordered.length)
        throw new Error('Quantiles require observations.');
    const position = Math.max(0, Math.min(ordered.length - 1, (ordered.length - 1) * probability));
    const lo = Math.floor(position), hi = Math.ceil(position), a = ordered[lo], b = ordered[hi];
    return { value: (0, data_common_js_1.interpolate)(a.value, b.value, position - lo), indices: lo === hi ? [a.index] : [a.index, b.index], weights: lo === hi ? [1] : [1 - (position - lo), position - lo] };
}
function histogramBins(values, count, domain) {
    if (!values.length || !Number.isInteger(count) || count < 2 || count > 100)
        throw new Error('Histogram needs data and 2..100 bins.');
    const minimum = domain?.[0] ?? Math.min(...values), maximum = domain?.[1] ?? Math.max(...values);
    const low = minimum === maximum ? minimum - .5 : minimum, high = minimum === maximum ? maximum + .5 : maximum;
    if (!(high > low))
        throw new Error('Histogram domain must increase.');
    const bins = Array.from({ length: count }, (_, i) => ({ low: (0, data_common_js_1.interpolate)(low, high, i / count), high: (0, data_common_js_1.interpolate)(low, high, (i + 1) / count), count: 0, indices: [] }));
    values.forEach((value, index) => {
        if (value < low || value > high)
            return;
        let first = 0, last = count;
        while (first + 1 < last) {
            const middle = (first + last) >>> 1;
            if (value < bins[middle].low)
                last = middle;
            else
                first = middle;
        }
        const bin = bins[first];
        bin.count++;
        bin.indices.push(index);
    });
    return bins;
}
function kernelDensity(values, points = 81) {
    if (values.length < 2)
        throw new Error('KDE is UNKNOWN with fewer than two observations.');
    const mean = (0, data_common_js_1.sum)(values) / values.length, sd = Math.sqrt((0, data_common_js_1.sum)(values.map(value => (value - mean) ** 2)) / values.length);
    const bandwidth = 1.06 * sd * values.length ** -.2;
    if (!(bandwidth > 0))
        throw new Error('KDE is UNKNOWN for zero-variance samples.');
    const low = Math.min(...values) - 3 * bandwidth, high = Math.max(...values) + 3 * bandwidth;
    return { bandwidth, points: Array.from({ length: points }, (_, i) => { const x = low + (high - low) * i / (points - 1), y = (0, data_common_js_1.sum)(values.map(v => Math.exp(-.5 * ((x - v) / bandwidth) ** 2))) / (values.length * bandwidth * Math.sqrt(2 * Math.PI)); return [x, y]; }) };
}
function inverseNormal(p) {
    if (!(p > 0 && p < 1))
        throw new Error('Normal quantile probability must be in (0,1).');
    const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
    const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
    const c = [-.00778489400243029, -.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
    const d = [.00778469570904146, .32246712907004, 2.445134137143, 3.75440866190742];
    const poly = (coefficients, x) => coefficients.reduce((value, coefficient) => value * x + coefficient, 0);
    if (p < .02425) {
        const q = Math.sqrt(-2 * Math.log(p));
        return poly(c, q) / (poly(d, q) * q + 1);
    }
    if (p > .97575) {
        const q = Math.sqrt(-2 * Math.log(1 - p));
        return -poly(c, q) / (poly(d, q) * q + 1);
    }
    const q = p - .5, r = q * q;
    return poly(a, r) * q / (poly(b, r) * r + 1);
}
function fiveNumber(values, minmax = false) {
    const q1 = (0, data_common_js_1.quantile)(values, .25), median = (0, data_common_js_1.quantile)(values, .5), q3 = (0, data_common_js_1.quantile)(values, .75), iqr = q3 - q1;
    const inside = values.filter(value => minmax || value >= q1 - 1.5 * iqr && value <= q3 + 1.5 * iqr);
    return { q1, median, q3, low: Math.min(...inside), high: Math.max(...inside), outliers: values.map((value, index) => ({ value, index })).filter(item => !minmax && (item.value < q1 - 1.5 * iqr || item.value > q3 + 1.5 * iqr)) };
}
function linearTrend(points) {
    const n = points.length, mx = (0, data_common_js_1.sum)(points.map(p => p[0])) / n, my = (0, data_common_js_1.sum)(points.map(p => p[1])) / n;
    const denominator = (0, data_common_js_1.sum)(points.map(p => (p[0] - mx) ** 2));
    if (n < 2 || denominator === 0)
        throw new Error('Linear trend is UNKNOWN without distinct x coordinates.');
    const slope = (0, data_common_js_1.sum)(points.map(p => (p[0] - mx) * (p[1] - my))) / denominator;
    return { slope, intercept: my - slope * mx };
}
function loessTrend(points) {
    if (points.length < 3 || points.length > 10000 || points.some(point => !point.every(Number.isFinite)))
        throw new Error('LOESS requires 3..10000 finite observations.');
    const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]), coordinates = [...new Set(sorted.map(point => point[0]))];
    if (coordinates.length < 2)
        throw new Error('LOESS is UNKNOWN without distinct x coordinates.');
    const count = Math.max(3, Math.ceil(sorted.length * 2 / 3));
    const evaluation = coordinates.length <= 201 ? coordinates : Array.from({ length: 201 }, (_, index) => coordinates[Math.round(index * (coordinates.length - 1) / 200)]);
    return evaluation.map(x => {
        const distances = sorted.map(point => Math.abs(point[0] - x)).sort((a, b) => a - b), radius = distances[Math.min(count - 1, distances.length - 1)] || distances.find(distance => distance > 0);
        const bandwidth = radius * (1 + 1e-12);
        const weighted = sorted.map(point => ({ dx: point[0] - x, y: point[1], weight: Math.abs(point[0] - x) <= radius ? (1 - (Math.abs(point[0] - x) / bandwidth) ** 3) ** 3 : 0 }));
        const total = (0, data_common_js_1.sum)(weighted.map(point => point.weight)), meanX = (0, data_common_js_1.sum)(weighted.map(point => point.weight * point.dx)) / total, meanY = (0, data_common_js_1.sum)(weighted.map(point => point.weight * point.y)) / total;
        const variance = (0, data_common_js_1.sum)(weighted.map(point => point.weight * (point.dx - meanX) ** 2)), covariance = (0, data_common_js_1.sum)(weighted.map(point => point.weight * (point.dx - meanX) * (point.y - meanY)));
        const y = variance > 0 ? meanY - covariance / variance * meanX : meanY;
        if (!Number.isFinite(y))
            throw new Error('LOESS arithmetic exceeded the finite numeric range.');
        return [x, y];
    });
}
function histogramPlan(values, options = {}) {
    if (values.length < 2)
        throw new Error('Histogram requires at least two samples.');
    let low = options.minimum ?? Math.min(...values), high = options.maximum ?? Math.max(...values);
    if (low === high && options.minimum === undefined && options.maximum === undefined) {
        low -= .5;
        high += .5;
    }
    if (!Number.isFinite(low) || !Number.isFinite(high) || !(high > low))
        throw new Error('Histogram domain must be finite and increasing.');
    let count = options.count ?? Math.min(40, Math.max(5, Math.ceil(Math.sqrt(values.length))));
    if (options.step !== undefined) {
        const exact = high / options.step - low / options.step;
        if (!(options.step > 0) || !Number.isFinite(exact) || Math.abs(exact - Math.round(exact)) > 1e-10)
            throw new Error('Bin step must divide the declared domain into equal-width bins.');
        if (options.count !== undefined && options.count !== Math.round(exact))
            throw new Error('Histogram count and step disagree.');
        count = Math.round(exact);
    }
    const selected = [];
    values.forEach((value, index) => {
        if (value < low || value > high) {
            if ((options.outside ?? 'error') === 'error')
                throw new Error('A sample is outside the declared histogram domain.');
            if (options.outside === 'drop')
                return;
            value = Math.max(low, Math.min(high, value));
        }
        selected.push({ value, index });
    });
    if (!selected.length)
        throw new Error('Histogram range excluded every sample.');
    return histogramBins(selected.map(item => item.value), count, [low, high]).map(bin => ({ ...bin, indices: bin.indices.map(index => selected[index].index), value: options.normalize === true || options.normalize === 'probability' ? bin.count / selected.length : options.normalize === 'density' ? bin.count / selected.length / (bin.high - bin.low) : bin.count }));
}

},
"presentation/src/family-charts.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.chartsPresentation = exports.projectCharts = void 0;
exports.installChartsPresentation = installChartsPresentation;
const adapters_js_1 = require("presentation/src/adapters.js");
const data_catalogue_js_1 = require("presentation/src/data-catalogue.js");
const data_adapter_js_1 = require("presentation/src/data-adapter.js");
const data_charts_js_1 = require("presentation/src/data-charts.js");
const data_isometric_js_1 = require("presentation/src/data-isometric.js");
const model_js_1 = require("presentation/src/model.js");
exports.projectCharts = (0, data_adapter_js_1.createDataProjector)(data_catalogue_js_1.chartProfileIds, data_charts_js_1.drawChart, (result, settings, scene) => { const profile = (0, model_js_1.str)(scene.view.record.profile); return (0, data_isometric_js_1.extrudeChart)(result, { ...settings, mark: settings.mark ?? (['chart.basic@1', 'chart.quality@1'].includes(profile) ? 'bar' : profile.slice(6).split('@')[0]) }, scene.extrusionDepths); });
exports.chartsPresentation = Object.freeze({ id: 'charts', version: '1.0.0', language: 'ddn-next-1', profiles: data_catalogue_js_1.chartProfileIds, kind: 'data', data: exports.projectCharts });
function installChartsPresentation() { (0, adapters_js_1.installPresentationFamily)(exports.chartsPresentation); }

},
"standalone/src/families/charts.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const family_charts_js_1 = require("presentation/src/family-charts.js");
(0, family_charts_js_1.installChartsPresentation)();

}});})();
