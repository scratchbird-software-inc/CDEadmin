import { array, object, str, num, pathValue } from './model.js';
import { DataScene, finite, valueAt, colors, label, box, path, ellipse, extent, scale, unique, sum, numberLabel, pointsPath, boundsOf, arcPath, colorScale, numericDate, mergedDatum, interpolate } from './data-common.js';
import { fiveNumber, histogramBins, histogramPlan, inverseNormal, kernelDensity, linearTrend, loessTrend, quantileContributors } from './data-statistics.js';
import { chartOptionErrors } from '../../profiles/src/projection-rules.js';
import { drawQuality } from './data-quality.js';
import { drawHierarchy, drawLinks } from './data-hierarchy.js';
const sampleMarks = new Set(['histogram', 'density', 'qq', 'quantiledot']);
const hierarchyMarks = new Set(['treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble']);
const linkMarks = new Set(['sankey', 'arc', 'force', 'edgebundle']);
export function drawChart(scene) {
    const settings = scene.settings, profile = str(scene.view.record.profile), specialized = profile.slice(6).split('@')[0], mark = str(settings.mark, ['basic', 'quality'].includes(specialized) ? 'bar' : specialized);
    const layers = array(settings.layers).map(object), qualityTransform = str(settings.transform, 'identity'), retainedTransform = ['histogram', 'pareto', 'waterfall', 'boxplot'].includes(qualityTransform);
    const authored = object(object(scene.view.record.projection).options);
    for (const message of chartOptionErrors(profile, { ...authored, mark, ...(settings.transform !== undefined ? { transform: settings.transform } : {}) }))
        scene.issue(message, 'DDN-CHART-OPTION');
    if (settings.aggregate !== undefined && settings.aggregate !== 'none' && !['bar', 'pie', 'donut', 'topk'].includes(mark))
        scene.issue(`Aggregation does not apply to ${mark}.`);
    if (settings.aggregate === 'count' && settings.unit !== undefined)
        scene.issue('Count has no physical unit.');
    if (qualityTransform !== 'waterfall' && settings.baseline !== undefined && settings.baseline !== 0)
        scene.issue('Area-encoded marks require a zero baseline.');
    const data = scene.data(), xKey = str(settings.x, str(layers[0]?.x)), yKey = str(settings.y, str(layers[0]?.y)), seriesKey = str(settings.series), xType = str(settings.x_type, sampleMarks.has(mark) || mark === 'densityheatmap' ? 'number' : mark === 'calendar' ? 'date' : 'category');
    if (settings.iso === true && typeof settings.depth === 'string')
        for (const datum of data) {
            const depth = valueAt(datum.values, settings.depth);
            if (!finite(depth) || depth < 0 || depth > 2000)
                scene.issue('Every extrusion depth must be finite and between 0 and 2000', 'DDN-CHART-DEPTH');
        }
    if (retainedTransform && qualityTransform !== 'boxplot') {
        drawQuality(scene, mark, qualityTransform, data);
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
        const rawX = valueAt(datum.values, xKey), rawY = sampleMarks.has(mark) || mark === 'candlestick' ? 0 : valueAt(datum.values, yKey);
        const x = xType === 'date' ? numericDate(rawX) : rawX;
        const missing = rawX === null || rawX === undefined || rawY === null || rawY === undefined;
        if (missing && settings.missing === 'skip')
            continue;
        const gap = (rawY === null || rawY === undefined) && settings.missing === 'gap' && ['bar', 'line', 'area', 'point'].includes(mark) && !layers.length;
        if (!finite(rawY) && !gap || (xType === 'number' || xType === 'date' ? !finite(x) : typeof x !== 'string' && !finite(x))) {
            scene.issue(`Record ${datum.source.ref.id} has an invalid ${!finite(rawY) ? 'y' : 'x'} value; numeric strings are not coerced.`, 'DDN-CHART-DATA', 'error', datum.source.ref);
            continue;
        }
        const series = seriesKey ? valueAt(datum.values, seriesKey) : '';
        if (seriesKey && typeof series !== 'string' && !finite(series)) {
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
        if (str(settings.transform, 'identity') !== 'identity' || layers.some(layer => !['bar', 'point', 'line', 'area'].includes(str(layer.mark, mark)))) {
            scene.issue('Layers require the identity transform and bar/point/line/area marks.');
            return;
        }
        const names = unique(points.map(point => point.series));
        if (seriesKey && layers.length !== names.length) {
            scene.issue('Declare one layer per series in series order.');
            return;
        }
        const layered = [];
        for (const [index, layer] of layers.entries())
            for (const original of points.filter(point => !seriesKey || point.series === names[index])) {
                const rawX = valueAt(original.datum.values, str(layer.x, xKey)), rawY = valueAt(original.datum.values, str(layer.y, yKey)), x = xType === 'date' ? numericDate(rawX) : rawX;
                if (!finite(rawY) || (xType === 'category' ? typeof x !== 'string' && !finite(x) : !finite(x))) {
                    scene.issue('A layer channel is missing or has the wrong type.');
                    continue;
                }
                layered.push({ ...original, x: x, y: rawY, series: seriesKey ? original.series : `Layer ${index + 1}`, mark: str(layer.mark, mark), color: str(layer.color, colors[index % colors.length]), opacity: num(layer.opacity, 1) });
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
    if (mark === 'funnel' && unique(points.map(p => p.x)).length < 2) {
        scene.issue('Funnel requires at least two distinct stages.');
        return;
    }
    const uniqueCoordinates = ['bar', 'line', 'area', 'pie', 'donut', 'funnel', 'candlestick', 'topk'].includes(mark);
    if (uniqueCoordinates && str(settings.aggregate, 'none') === 'none' && unique(points.map(p => JSON.stringify([p.x, p.series]))).length !== points.length) {
        scene.issue('Duplicate coordinates require an applicable explicit aggregation.');
        return;
    }
    if (!points.length && !['bar', 'line', 'area', 'point'].includes(mark)) {
        scene.issue(`${mark} requires at least one record.`);
        return;
    }
    if (hierarchyMarks.has(mark)) {
        drawHierarchy(scene, mark, points.map(p => ({ ...p.datum, values: { ...p.datum.values, label: String(p.x), value: p.y } })));
        return;
    }
    if (linkMarks.has(mark)) {
        drawLinks(scene, mark, points.map(p => ({ ...p.datum, values: { ...p.datum.values, source: String(p.x), value: p.y, target: valueAt(p.datum.values, str(settings.target, 'target')) } })));
        return;
    }
    const plot = { x: scene.bounds.x + 64, y: scene.bounds.y + 50, width: Math.max(80, num(settings.width, scene.bounds.width) - 96), height: Math.max(80, num(settings.height, scene.bounds.height) - 122) };
    const xLabel = (value) => xType === 'date' && typeof value === 'number' ? new Date(value).toISOString().slice(0, 10) : String(value);
    const addPoint = (p, bounds, primitives, description = '') => {
        scene.add(`${xLabel(p.x)}: ${numberLabel(p.y)}${p.series ? ` (${p.series})` : ''}`, bounds, primitives, p.datum.source, p.datum.contributors, description);
        const entry = scene.result.entries.at(-1), depth = typeof settings.depth === 'string' ? valueAt(p.datum.values, settings.depth) : undefined;
        if (entry && finite(depth))
            scene.extrusionDepths.set(entry.item.occurrence, depth);
    };
    const axes = (xDomain, yDomain, categories) => {
        const primitive = [label(mark === 'histogram' ? str(settings.normalize, 'count') : mark === 'density' ? 'Density' : str(settings.unit, str(settings.y)), plot.x, plot.y - 12, 11), path(`M${plot.x},${plot.y}V${plot.y + plot.height}H${plot.x + plot.width}`)];
        for (let i = 0; i <= 5; i++) {
            const y = plot.y + plot.height * (1 - i / 5);
            primitive.push(path(`M${plot.x},${y}H${plot.x + plot.width}`, '#e2e8f0'), label(numberLabel(interpolate(yDomain[0], yDomain[1], i / 5)), plot.x - 6, y + 4, 10, { 'text-anchor': 'end' }));
        }
        if (categories)
            categories.forEach((name, i) => primitive.push(label(name, plot.x + (i + .5) * plot.width / Math.max(1, categories.length), plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' })));
        else
            for (let i = 0; i <= 5; i++)
                primitive.push(label(xType === 'date' ? xLabel(interpolate(xDomain[0], xDomain[1], i / 5)) : numberLabel(interpolate(xDomain[0], xDomain[1], i / 5)), plot.x + plot.width * i / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
        if (mark === 'histogram' || mark === 'density')
            primitive.push(label(str(settings.unit, xKey), plot.x + plot.width / 2, plot.y + plot.height + 38, 11, { 'text-anchor': 'middle' }));
        scene.add('Chart axes', { ...plot, x: plot.x - 48, width: plot.width + 48, height: plot.height + 28 }, primitive);
    };
    if (mark === 'gauge') {
        if (points.length !== 1 || points[0].y < 0 || points[0].y > 100 || settings.target !== undefined && (!finite(settings.target) || settings.target < 0 || settings.target > 100)) {
            scene.issue('Gauge requires one value and optional target in 0..100.');
            return;
        }
        const p = points[0], radius = Math.min(plot.width / 2 - 35, plot.height - 50), cx = plot.x + plot.width / 2, cy = plot.y + radius + 12, inner = radius * .78;
        const primitives = [];
        for (let i = 0; i < 4; i++)
            primitives.push(path(arcPath(cx, cy, radius, Math.PI + Math.PI * i / 4, Math.PI + Math.PI * (i + 1) / 4, inner), '#fff', colors[i]));
        for (let i = 0; i <= 4; i++) {
            const angle = Math.PI + Math.PI * i / 4;
            primitives.push(label(String(i * 25), cx + (radius + 22) * Math.cos(angle), cy + (radius + 22) * Math.sin(angle) + 4, 11, { 'text-anchor': 'middle' }));
        }
        const angle = Math.PI + Math.PI * p.y / 100;
        primitives.push(path(`M${cx},${cy}L${cx + (inner - 10) * Math.cos(angle)},${cy + (inner - 10) * Math.sin(angle)}`, '#1E2D43', 'none', { 'stroke-width': 3 }), ellipse(cx, cy, 5, '#1E2D43'), label(`${numberLabel(p.y)}%`, cx, cy - radius * .28, 26, { 'text-anchor': 'middle' }), label(String(p.x), cx, cy + 34, 14, { 'text-anchor': 'middle' }));
        if (finite(settings.target)) {
            const a = Math.PI + Math.PI * settings.target / 100;
            primitives.push(path(`M${cx + (radius + 2) * Math.cos(a)},${cy + (radius + 2) * Math.sin(a)}L${cx + (radius + 16) * Math.cos(a)},${cy + (radius + 16) * Math.sin(a)}`, '#1E2D43', 'none', { 'stroke-width': 3 }));
        }
        addPoint(p, plot, primitives);
        scene.caption(`Gauge: 0–100%; needle encodes value${finite(settings.target) ? '; outer tick marks target ' + settings.target + '%' : ''}.`);
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
            addPoint(p, boundsOf(shape), [path(pointsPath(shape, true), '#fff', colors[i % colors.length]), label(text, inside ? center : center + Math.max(top, bottom) / 2 + 12, y + height / 2 + 4, 12, { 'text-anchor': inside ? 'middle' : 'start', fill: inside ? '#ffffff' : '#243449' })]);
        });
        scene.caption(`Stage widths encode values; ${points.length} stages; total ${sum(points.map(p => p.y)).toLocaleString('en-US')}${settings.unit ? ' ' + settings.unit : ''}.`);
        return;
    }
    if (mark === 'pie' || mark === 'donut') {
        const grouped = aggregate(points, str(settings.aggregate, 'none'), scene);
        if (grouped.some(p => p.y < 0) || !(sum(grouped.map(p => p.y)) > 0) || seriesKey) {
            scene.issue('Arc shares require nonnegative values and a positive total without series.');
            return;
        }
        const total = sum(grouped.map(p => p.y)), legendWidth = Math.min(240, plot.width * .35), cx = plot.x + (plot.width - legendWidth) / 2, cy = plot.y + plot.height / 2, radius = Math.min(plot.width - legendWidth - 24, plot.height) / 2;
        let angle = -Math.PI / 2;
        grouped.forEach((p, i) => {
            const end = angle + p.y / total * Math.PI * 2;
            if (end > angle)
                addPoint(p, { x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, [path(arcPath(cx, cy, radius, angle, end, mark === 'donut' ? Math.min(radius * .9, num(settings.inner_radius, radius * .55)) : 0), '#fff', colors[i % colors.length]), ...(p.y / total > .05 ? [label(`${numberLabel(p.y / total * 100)}%`, cx + Math.cos((angle + end) / 2) * radius * .72, cy + Math.sin((angle + end) / 2) * radius * .72, 11, { 'text-anchor': 'middle', fill: '#ffffff' })] : [])]);
            angle = end;
        });
        scene.legend(grouped.map((p, i) => ({ label: `${p.x}: ${numberLabel(p.y)}${settings.unit ? ' ' + settings.unit : ''}`, color: colors[i % colors.length] })), plot.x + plot.width - legendWidth, plot.y + 20, true);
        scene.caption(`Shares of total ${numberLabel(total)}${settings.unit ? ' ' + settings.unit : ''}; angles encode values.`);
        return;
    }
    if (mark === 'radar' || mark === 'parallelcoords') {
        const categories = unique(points.map(p => String(p.x))), series = unique(points.map(p => p.series));
        if (categories.length < (mark === 'radar' ? 3 : 2) || categories.length > (mark === 'radar' ? 40 : 24) || points.length !== new Set(points.map(p => JSON.stringify([p.x, p.series]))).size) {
            scene.issue('Axes and series must have unique samples and stay within the axis bound.');
            return;
        }
        const byCategory = categories.map(c => points.filter(p => String(p.x) === c)), domains = byCategory.map(values => extent(values.map(p => p.y))), max = Math.max(...points.map(p => p.y), 1), center = [plot.x + plot.width / 2, plot.y + plot.height / 2], radius = Math.min(plot.width, plot.height) * .42;
        const point = (index, value) => mark === 'radar' ? [center[0] + Math.cos(index * 2 * Math.PI / categories.length - Math.PI / 2) * radius * (value ?? 0) / max, center[1] + Math.sin(index * 2 * Math.PI / categories.length - Math.PI / 2) * radius * (value ?? 0) / max] : [plot.x + index * plot.width / (categories.length - 1), value === undefined || byCategory[index].every(p => p.y === byCategory[index][0].y) ? plot.y + plot.height / 2 : scale(domains[index], [plot.y + plot.height, plot.y])(value)];
        if (mark === 'radar' && points.some(p => p.y < 0)) {
            scene.issue('Radar values must be nonnegative.');
            return;
        }
        scene.legend(series.map((name, i) => ({ label: name || str(settings.y), color: colors[i % colors.length] })));
        if (mark === 'radar')
            for (let ring = 1; ring <= 4; ring++)
                scene.add('Radar scale', plot, [path(pointsPath(categories.map((_, i) => point(i, max * ring / 4)), true), '#D9E3EF'), label(numberLabel(max * ring / 4), center[0] + 6, center[1] - radius * ring / 4, 10)]);
        categories.forEach((category, i) => {
            const end = mark === 'radar' ? point(i, max) : [plot.x + i * plot.width / (categories.length - 1), plot.y], start = mark === 'radar' ? center : [end[0], plot.y + plot.height];
            scene.add(category, plot, [path(pointsPath([start, end]), '#cbd5e1'), label(category, end[0], end[1] - 6, 11, { 'text-anchor': 'middle' }), ...(mark === 'parallelcoords' ? [label(numberLabel(domains[i][1]), end[0] + 6, end[1] + 14, 10), label(numberLabel(domains[i][0]), end[0] + 6, plot.y + plot.height - 4, 10)] : [])]);
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
            scene.add(name || mark, plot, [path(pointsPath(coordinates, mark === 'radar'), colors[si % colors.length], mark === 'radar' ? colors[si % colors.length] : 'none', { 'fill-opacity': .12 }), ...coordinates.map(([x, y]) => ellipse(x, y, 3, colors[si % colors.length]))], members[0].datum.source, members.flatMap(p => p.datum.contributors));
        });
        scene.caption(mark === 'radar' ? `Shared radial scale: 0–${numberLabel(max)}${settings.unit ? ' ' + settings.unit : ''}.` : 'Each axis is normalized independently; constant or missing values are UNKNOWN at mid-height.');
        return;
    }
    if (mark === 'candlestick') {
        const rows = points.map(p => ({ p, open: valueAt(p.datum.values, str(settings.open, 'open')), high: valueAt(p.datum.values, str(settings.high, 'high')), low: valueAt(p.datum.values, str(settings.low, 'low')), close: valueAt(p.datum.values, str(settings.close, 'close')) }));
        if (rows.some(r => ![r.open, r.high, r.low, r.close].every(finite) || num(r.low) > Math.min(num(r.open), num(r.close)) || num(r.high) < Math.max(num(r.open), num(r.close)))) {
            scene.issue('OHLC values must be finite and enclosed by low/high.');
            return;
        }
        const domain = extent(rows.flatMap(r => [num(r.low), num(r.high)])), ys = scale(domain, [plot.y + plot.height, plot.y]), step = plot.width / Math.max(1, rows.length);
        axes([0, rows.length], domain, rows.map(r => xLabel(r.p.x)));
        rows.forEach((r, i) => { const x = plot.x + (i + .5) * step, top = ys(Math.max(num(r.open), num(r.close))), bottom = ys(Math.min(num(r.open), num(r.close))), fill = num(r.close) >= num(r.open) ? colors[1] : colors[2]; addPoint(r.p, { x: x - step * .22, y: ys(num(r.high)), width: step * .44, height: ys(num(r.low)) - ys(num(r.high)) }, [path(`M${x},${ys(num(r.high))}V${ys(num(r.low))}`, fill), box({ x: x - step * .22, y: top, width: step * .44, height: Math.max(1, bottom - top) }, fill)], `Open ${r.open}; high ${r.high}; low ${r.low}; close ${r.close}`); });
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
    let plotted = aggregate(points, str(settings.aggregate, 'none'), scene);
    if (mark === 'topk') {
        const k = num(settings.k, 10);
        if (!Number.isInteger(k) || k < 1 || k > 100) {
            scene.issue('Top-k requires k in 1..100.');
            return;
        }
        plotted = [...plotted].sort((a, b) => b.y - a.y || (String(a.x) < String(b.x) ? -1 : String(a.x) > String(b.x) ? 1 : a.datum.ordinal - b.datum.ordinal));
        const remainder = plotted.slice(k);
        plotted = plotted.slice(0, k);
        if (remainder.length && settings.others !== false)
            plotted.push({ x: 'Others', y: sum(remainder.map(p => p.y)), series: '', datum: mergedDatum({}, remainder.map(p => p.datum)) });
    }
    const transform = str(settings.transform, 'identity');
    if (transform !== 'identity') {
        const maximum = Math.max(...plotted.map(p => Math.abs(p.y)), 0);
        if (plotted.some(p => !p.gap && (transform === 'log' && p.y <= 0 || transform === 'sqrt' && p.y < 0)) || transform === 'normalize' && maximum === 0) {
            scene.issue('The selected transformation is undefined for supplied values.');
            return;
        }
        plotted = plotted.map(p => ({ ...p, y: p.gap ? 0 : transform === 'log' ? Math.log(p.y) : transform === 'sqrt' ? Math.sqrt(p.y) : transform === 'normalize' ? p.y / maximum : p.y }));
    }
    const categories = unique(plotted.map(p => String(p.x))), series = unique(plotted.map(p => p.series)), arrangement = str(settings.arrangement, 'group');
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
        if (arrangement === 'percent' && (plotted.some(p => p.y < 0) || categories.some(category => sum(plotted.filter(p => String(p.x) === category).map(p => p.y)) <= 0))) {
            scene.issue('Percent stacks require nonnegative values and positive totals.');
            return;
        }
    }
    const percentTotals = new Map(categories.map(category => [category, sum(plotted.filter(p => String(p.x) === category).map(p => p.y))]));
    if (arrangement === 'percent' && [...percentTotals.values()].some(value => !finite(value))) {
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
    const errors = object(settings.error), errorValues = plotted.filter(p => !p.gap).flatMap(p => {
        const amount = valueAt(p.datum.values, str(errors.value)), low = errors.low ? valueAt(p.datum.values, str(errors.low)) : finite(amount) ? p.y - amount : undefined, high = errors.high ? valueAt(p.datum.values, str(errors.high)) : finite(amount) ? p.y + amount : undefined;
        return [low, high].filter(finite);
    });
    const yDomain = extent([...plotted.filter(p => !p.gap).flatMap(p => [offsets.get(p) + p.y]), ...errorValues], true), xDomain = xType === 'category' ? [0, categories.length] : extent(plotted.map(p => Number(p.x))), ys = scale(yDomain, [plot.y + plot.height, plot.y]), xs = (p) => xType === 'category' ? plot.x + (categories.indexOf(String(p.x)) + .5) * plot.width / Math.max(1, categories.length) : scale(xDomain, [plot.x, plot.x + plot.width])(Number(p.x));
    axes(xDomain, yDomain, xType === 'category' ? categories : undefined);
    const markFor = (p) => p.mark ?? mark, colorFor = (p) => p.color ?? (mark === 'topk' && p.x === 'Others' ? '#C6D5E6' : colors[(series.length === 1 && ['bar', 'topk', 'point'].includes(markFor(p)) ? categories.indexOf(String(p.x)) : series.indexOf(p.series)) % colors.length]);
    if (series.some(Boolean))
        scene.legend(series.map(name => ({ label: name, color: colorFor(plotted.find(p => p.series === name)) })));
    if (mark === 'topk')
        scene.caption(`Top ${num(settings.k, 10)} categories by value${settings.others !== false ? '; remaining values grouped as Others' : ''}.`);
    if (plotted.some(p => ['bar', 'topk'].includes(markFor(p)) && xType !== 'category')) {
        scene.issue('Layer marks must match the shared x-axis type.');
        return;
    }
    for (const p of plotted) {
        if (p.gap) {
            scene.add(`${xLabel(p.x)}: missing`, { x: xs(p) - 24, y: plot.y + plot.height + 22, width: 48, height: 18 }, [label('missing', xs(p), plot.y + plot.height + 34, 10, { 'text-anchor': 'middle' })], p.datum.source, p.datum.contributors);
            continue;
        }
        const shape = markFor(p), opacity = p.opacity ?? 1;
        if (shape === 'bar' || shape === 'topk') {
            const i = series.indexOf(p.series), band = plot.width / Math.max(1, categories.length), width = band * .8 / (arrangement === 'group' ? series.length : 1), x = xs(p) - band * .4 + (arrangement === 'group' ? i * width : 0), base = offsets.get(p), y = ys(Math.max(base, base + p.y)), height = Math.max(0, ys(Math.min(base, base + p.y)) - y), bounds = { x, y, width: Math.max(1, width - 1), height };
            addPoint(p, bounds, [box(bounds, colorFor(p), 'none', { opacity })], `Contributors: ${p.datum.contributors.map(r => r.id).join(', ')}`);
        }
        else if (shape === 'point') {
            const rawSize = settings.size ? valueAt(p.datum.values, str(settings.size)) : 25;
            if (!finite(rawSize) || rawSize < 0) {
                scene.issue('Point size requires a finite nonnegative value.');
                continue;
            }
            const radius = Math.sqrt(rawSize);
            addPoint(p, { x: xs(p) - radius, y: ys(p.y) - radius, width: radius * 2, height: radius * 2 }, [ellipse(xs(p), ys(p.y), radius, colorFor(p), { opacity })]);
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
            scene.add(name || shape, plot, [path(pointsPath(shape === 'area' ? [...coordinates, ...bottom] : coordinates, shape === 'area'), colorFor(segment[0]), shape === 'area' ? colorFor(segment[0]) : 'none', { 'fill-opacity': .2, opacity: segment[0].opacity ?? 1, 'stroke-width': 2, ...(series.indexOf(name) % 2 ? { 'stroke-dasharray': '6 3' } : {}) }), ...(shape === 'line' && !layers.some(layer => layer.mark === 'point') ? coordinates.map(([x, y]) => ellipse(x, y, 3, colorFor(segment[0]))) : [])], segment[0].datum.source, segment.flatMap(p => p.datum.contributors));
        }
    }
    if (settings.trend && object(settings.trend).show !== false) {
        try {
            const method = str(object(settings.trend).method, 'linear');
            if (!['linear', 'loess'].includes(method))
                throw new Error('Trend method must be linear or loess.');
            const values = plotted.filter(p => !p.gap).map(p => [Number(p.x), p.y]);
            if (xType !== 'number')
                throw new Error('Trend requires numeric x.');
            const fit = method === 'linear' ? linearTrend(values) : undefined;
            const trend = fit ? [xDomain[0], xDomain[1]].map(x => [x, fit.slope * x + fit.intercept]) : loessTrend(values);
            const ends = trend.map(([x, y]) => [scale(xDomain, [plot.x, plot.x + plot.width])(x), ys(y)]);
            scene.add(method === 'linear' ? 'Linear trend' : 'LOESS trend', plot, [path(pointsPath(ends), '#dc2626', 'none', { 'stroke-dasharray': '6 3' })], scene.view, plotted.flatMap(p => p.datum.contributors), method === 'loess' ? 'Local linear fit; tricube weights; 2/3 span; no robust iterations' : 'Least-squares linear fit');
        }
        catch (error) {
            scene.issue(String(error), 'DDN-PJW04', 'warning');
        }
    }
    const error = object(settings.error);
    if (Object.keys(error).length)
        for (const p of plotted.filter(p => !p.gap)) {
            const amount = valueAt(p.datum.values, str(error.value)), lo = error.low ? valueAt(p.datum.values, str(error.low)) : finite(amount) ? p.y - amount : undefined, hi = error.high ? valueAt(p.datum.values, str(error.high)) : finite(amount) ? p.y + amount : undefined;
            if (!finite(lo) || !finite(hi) || lo > hi) {
                scene.issue('Error bounds must be finite and increasing.');
                continue;
            }
            const x = xs(p);
            scene.add('Error interval', boundsOf([[x, ys(lo)], [x, ys(hi)]], 4), [path(`M${x},${ys(lo)}V${ys(hi)}M${x - 4},${ys(lo)}h8M${x - 4},${ys(hi)}h8`, '#334155')], p.datum.source, p.datum.contributors);
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
    return [...groups.values()].map(group => { const values = group.map(p => p.y), sorted = [...values].sort((a, b) => a - b), first = group[0]; return { ...first, y: operation === 'sum' ? sum(values) : operation === 'count' ? values.length : operation === 'min' ? Math.min(...values) : operation === 'max' ? Math.max(...values) : operation === 'average' ? sum(values) / values.length : sorted.length % 2 ? sorted[Math.floor(sorted.length / 2)] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2, datum: mergedDatum(first.datum.values, group.map(p => p.datum)) }; });
}
function drawSamples(scene, points, mark, plot, axes) {
    const samples = points.map(p => Number(p.x));
    if (points.length < 2) {
        scene.issue(`${mark} requires at least two observations.`);
        return;
    }
    if (mark === 'histogram') {
        const settings = scene.settings, descriptor = object(settings.bins), authored = object(object(scene.view.record.projection).options);
        const count = typeof settings.bins === 'number' ? settings.bins : typeof descriptor.count === 'number' ? descriptor.count : settings.bin_count === 'auto' || settings.bin_count === undefined ? undefined : num(settings.bin_count);
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
            bins = histogramPlan(samples, {
                ...(count !== undefined ? { count } : {}),
                ...(finite(descriptor.min) ? { minimum: descriptor.min } : {}),
                ...(finite(descriptor.max) ? { maximum: descriptor.max } : {}),
                ...(finite(settings.step) ? { step: settings.step } : finite(descriptor.step) ? { step: descriptor.step } : {}),
                outside: str(settings.outside, 'error'),
                normalize: settings.normalize === true ? true : settings.normalize === false ? false : str(settings.normalize, 'count')
            });
        }
        catch (error) {
            scene.issue(String(error));
            return;
        }
        const xd = [bins[0].low, bins.at(-1).high], yd = extent(bins.map(bin => bin.value), true), xs = scale(xd, [plot.x, plot.x + plot.width]), ys = scale(yd, [plot.y + plot.height, plot.y]);
        axes(xd, yd);
        bins.forEach(bin => { const b = { x: xs(bin.low), y: ys(bin.value), width: Math.max(.1, xs(bin.high) - xs(bin.low) - Math.min(1, (xs(bin.high) - xs(bin.low)) * .1)), height: plot.y + plot.height - ys(bin.value) }; const members = bin.indices.map(i => points[i].datum); scene.add(`${numberLabel(bin.low)}–${numberLabel(bin.high)}: ${numberLabel(bin.value)}`, b, [box(b, colors[0], 'none')], members[0]?.source ?? scene.view, members.flatMap(d => d.contributors), `${bin.count} contributing observations; normalization ${String(settings.normalize ?? 'count')}`); });
        scene.caption(`n=${samples.length}; ${bins.length} equal-width bins; left inclusive, right exclusive except final bin; ${String(settings.normalize ?? 'count')}.`);
        return;
    }
    if (mark === 'density') {
        try {
            const kde = kernelDensity(samples), xd = extent(kde.points.map(p => p[0])), yd = extent(kde.points.map(p => p[1]), true), xs = scale(xd, [plot.x, plot.x + plot.width]), ys = scale(yd, [plot.y + plot.height, plot.y]);
            axes(xd, yd);
            const coordinates = kde.points.map(p => [xs(p[0]), ys(p[1])]);
            scene.add('Gaussian density estimate', plot, [path(pointsPath([...coordinates, [plot.x + plot.width, plot.y + plot.height], [plot.x, plot.y + plot.height]], true), colors[0], colors[0], { 'fill-opacity': .18 })], points[0].datum.source, points.flatMap(p => p.datum.contributors), `Bandwidth ${kde.bandwidth}; 81 evaluation points`);
            scene.caption(`Gaussian KDE; n=${samples.length}; bandwidth ${numberLabel(kde.bandwidth)}; area under curve ≈ 1.`);
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
        const ordered = [...points].sort((a, b) => Number(a.x) - Number(b.x) || a.datum.ordinal - b.datum.ordinal), pairs = ordered.map((p, i) => [inverseNormal((i + .5) / ordered.length), Number(p.x)]), xd = extent(pairs.map(p => p[0])), yd = extent(samples), xs = scale(xd, [plot.x, plot.x + plot.width]), ys = scale(yd, [plot.y + plot.height, plot.y]);
        axes(xd, yd);
        scene.add('Theoretical normal quantiles', plot, [label('Theoretical normal quantiles', plot.x + plot.width / 2, plot.y + plot.height + 40, 11, { 'text-anchor': 'middle' })]);
        ordered.forEach((p, i) => { const xy = pairs[i], x = xs(xy[0]), y = ys(xy[1]); scene.add(`Rank ${i + 1}: ${xy[1]}`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [ellipse(x, y, 4)], p.datum.source, p.datum.contributors); });
        const q1 = quantileContributors(samples, .25).value, q3 = quantileContributors(samples, .75).value, slope = (q3 - q1) / (inverseNormal(.75) - inverseNormal(.25)), intercept = q1 - slope * inverseNormal(.25);
        scene.add('Quartile reference', plot, [path(pointsPath(xd.map(x => [xs(x), ys(intercept + slope * x)])), '#64748b', 'none', { 'stroke-dasharray': '5 3' })]);
        scene.caption(`Normal Q–Q: theoretical normal quantiles against sample${scene.settings.unit ? ' (' + scene.settings.unit + ')' : ''}; quartile reference line; n=${samples.length}.`);
        return;
    }
    const xd = extent(samples), xs = scale(xd, [plot.x, plot.x + plot.width]), count = Math.min(20, samples.length), previous = [];
    const axis = [path(`M${plot.x},${plot.y + plot.height}H${plot.x + plot.width}`)];
    for (let i = 0; i <= 4; i++) {
        const x = plot.x + plot.width * i / 4;
        axis.push(path(`M${x},${plot.y}V${plot.y + plot.height}`, '#E2E8F0'), label(numberLabel(interpolate(xd[0], xd[1], i / 4)), x, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
    }
    axis.push(label(`${count} quantiles of ${str(scene.settings.unit, str(scene.settings.x))}`, plot.x, plot.y - 12, 11));
    scene.add('Quantile sample axis', plot, axis);
    scene.caption(`${count} equal-probability quantiles${scene.settings.unit ? '; ' + scene.settings.unit : ''}; vertical displacement avoids overlap and has no quantitative meaning.`);
    for (let i = 0; i < count; i++) {
        const q = quantileContributors(samples, (i + .5) / count), x = xs(q.value);
        let lane = 0;
        while (previous.some(p => Math.abs(p[0] - x) < 16.8 && Math.abs(p[1] - lane) < 1))
            lane++;
        previous.push([x, lane]);
        const y = plot.y + plot.height - lane * 16.8 - 7, contributors = q.indices.flatMap(index => points[index].datum.contributors);
        scene.add(`Quantile ${(i + .5) / count}: ${q.value}`, { x: x - 7, y: y - 7, width: 14, height: 14 }, [ellipse(x, y, 7)], points[q.indices[0]].datum.source, contributors, `R-7 interpolated value; source indices ${q.indices.join(', ')}; weights ${q.weights.join(', ')}`);
    }
}
function drawDistributions(scene, points, mark, plot, axes) {
    const categories = unique(points.map(p => String(p.x)));
    if (categories.length > 40) {
        scene.issue('Distribution charts are bounded to 40 categories.');
        return;
    }
    const groups = categories.map(name => points.filter(p => String(p.x) === name));
    const densities = mark === 'violin' ? groups.map(group => {
        try {
            return kernelDensity(group.map(p => p.y), 61);
        }
        catch (error) {
            scene.issue(String(error), 'DDN-PJ132');
            return undefined;
        }
    }) : [];
    if (scene.result.unavailable.length)
        return;
    const yd = extent(mark === 'violin' ? densities.flatMap(d => d.points.map(p => p[0])) : points.map(p => p.y)), ys = scale(yd, [plot.y + plot.height, plot.y]), band = plot.width / Math.max(1, categories.length);
    axes([0, categories.length], yd, categories);
    scene.caption(mark === 'boxplot' ? 'R-7 quartiles; median; Tukey 1.5-IQR whiskers and outliers.' : mark === 'violin' ? 'Gaussian KDE; common density scale; median and interquartile range.' : 'Each dot is one observation; horizontal displacement has no quantitative meaning.');
    groups.forEach((group, index) => {
        const x = plot.x + (index + .5) * band, color = colors[index % colors.length];
        if (mark === 'boxplot' || mark === 'violin') {
            const f = fiveNumber(group.map(p => p.y)), primitives = [];
            if (mark === 'boxplot' && scene.settings.transform === 'boxplot' && scene.settings.whiskers === 'minmax') {
                f.low = Math.min(...group.map(p => p.y));
                f.high = Math.max(...group.map(p => p.y));
                f.outliers = [];
            }
            if (mark === 'violin') {
                const density = densities[index], maximum = Math.max(...densities.flatMap(d => d.points.map(p => p[1]))), half = band * .42, coordinates = [...density.points.map(p => [x - p[1] / maximum * half, ys(p[0])]), ...[...density.points].reverse().map(p => [x + p[1] / maximum * half, ys(p[0])])];
                primitives.push(path(pointsPath(coordinates, true), color, color, { 'fill-opacity': .2, 'stroke-width': 2 }), path(`M${x},${ys(f.q1)}V${ys(f.q3)}`, '#334155', 'none', { 'stroke-width': 5 }), ellipse(x, ys(f.median), 4, '#fff', { stroke: '#334155' }));
            }
            else {
                const w = Math.min(70, band * .45);
                primitives.push(path(`M${x},${ys(f.low)}V${ys(f.q1)}M${x},${ys(f.q3)}V${ys(f.high)}M${x - w / 3},${ys(f.low)}h${w * 2 / 3}M${x - w / 3},${ys(f.high)}h${w * 2 / 3}`, color), box({ x: x - w / 2, y: ys(f.q3), width: w, height: Math.max(1, ys(f.q1) - ys(f.q3)) }, color, color, { 'fill-opacity': .22, 'stroke-width': 2 }), path(`M${x - w / 2},${ys(f.median)}h${w}`, color, 'none', { 'stroke-width': 3 }));
            }
            primitives.push(label(`n=${group.length}`, x, plot.y + plot.height + 34, 10, { 'text-anchor': 'middle' }));
            scene.add(`${categories[index]}: median ${f.median}`, { x: x - band * .45, y: plot.y, width: band * .9, height: plot.height }, primitives, group[0].datum.source, group.flatMap(p => p.datum.contributors), `R-7 quartiles ${f.q1}, ${f.median}, ${f.q3}; ${scene.settings.whiskers === 'minmax' ? 'Min/max' : 'Tukey'} whiskers ${f.low}, ${f.high}`);
            if (mark === 'boxplot')
                f.outliers.forEach(outlier => { const p = group[outlier.index], y = ys(outlier.value); scene.add(`Outlier ${outlier.value}`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [ellipse(x, y, 4, '#fff', { stroke: color })], p.datum.source, p.datum.contributors); });
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
                scene.add(`${p.x}: ${p.y}`, { x: x + offset - radius, y: y - radius, width: radius * 2, height: radius * 2 }, [ellipse(x + offset, y, radius, color, { 'fill-opacity': .85 })], p.datum.source, p.datum.contributors, 'Horizontal displacement is collision avoidance only.');
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
            const size = 15 + (Math.max(30, Math.min(58, plot.width / 9)) - 15) * Math.sqrt(p.y / maximum), width = scene.measure(String(p.x), size) * 1.08 + 10, height = size * 1.3 * num(pathValue(scene.effective, 'style.font_size'), 16) / 16;
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
            scene.add(`${p.x}: ${p.y}`, found, [label(String(p.x), found.x + width / 2, found.y + height / 2 + size * .35, size, { 'text-anchor': 'middle', fill: colors[index % colors.length], 'font-weight': 700 })], p.datum.source, p.datum.contributors);
        }
        scene.caption('Word size encodes weight; placement is deterministic and has no quantitative meaning.');
        return;
    }
    if (mark === 'densityheatmap' && (points.every(p => p.x === points[0]?.x) || points.every(p => p.y === points[0]?.y))) {
        scene.issue('Density heatmap is UNKNOWN when either coordinate has zero range.', 'DDN-PJ132');
        return;
    }
    if (mark === 'densityheatmap') {
        const count = num(scene.settings.bin_count, 20);
        if (!Number.isInteger(count) || count < 2 || count > 60) {
            scene.issue('Density heatmap requires 2..60 bins per axis.');
            return;
        }
        const xd = extent(points.map(p => Number(p.x))), yd = extent(points.map(p => p.y)), groups = new Map();
        for (const p of points) {
            const ix = Math.min(count - 1, Math.floor((Number(p.x) - xd[0]) / (xd[1] - xd[0]) * count)), iy = Math.min(count - 1, Math.floor((p.y - yd[0]) / (yd[1] - yd[0]) * count)), key = `${ix}:${iy}`;
            groups.set(key, [...groups.get(key) ?? [], p]);
        }
        const maximum = Math.max(...[...groups.values()].map(p => p.length));
        scene.intensity([0, maximum], 'observations / bin');
        const axes = [];
        for (let i = 0; i <= 5; i++)
            axes.push(label(numberLabel(interpolate(xd[0], xd[1], i / 5)), plot.x + plot.width * i / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }), label(numberLabel(interpolate(yd[0], yd[1], i / 5)), plot.x - 7, plot.y + plot.height * (1 - i / 5) + 4, 10, { 'text-anchor': 'end' }));
        scene.add('Density heatmap axes', plot, axes);
        scene.caption(`${count} × ${count} bins; color encodes observation count; empty bins are blank.`);
        for (const [key, values] of groups) {
            const [ix, iy] = key.split(':').map(Number), b = { x: plot.x + ix * plot.width / count, y: plot.y + (count - 1 - iy) * plot.height / count, width: plot.width / count, height: plot.height / count };
            scene.add(`Bin ${key}: ${values.length}`, b, [box(b, colorScale(values.length, [0, maximum]), '#fff')], values[0].datum.source, values.flatMap(p => p.datum.contributors));
        }
        return;
    }
    const domain = extent(points.map(p => p.y));
    scene.intensity(domain, str(scene.settings.unit));
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
        ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].forEach((dayName, i) => scene.add(dayName, { x: plot.x - 32, y: plot.y + i * cell, width: 30, height: cell }, [label(dayName, plot.x - 6, plot.y + (i + .65) * cell, 10, { 'text-anchor': 'end' })]));
        let month = '';
        for (let week = 0; week < weeks; week++) {
            const date = new Date(start + week * 7 * day), name = date.toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
            if (name !== month) {
                scene.add(name, { x: plot.x + week * cell, y: plot.y - 24, width: cell, height: 20 }, [label(name, plot.x + week * cell, plot.y - 10, 10)]);
                month = name;
            }
        }
        scene.caption('Monday-first calendar; UTC days; color encodes value; missing days are blank.');
        if (scene.settings.iso)
            for (let week = 0; week < weeks; week++) {
                const monday = start + week * 7 * day, thursday = new Date(monday + 3 * day), year = thursday.getUTCFullYear(), january4 = Date.UTC(year, 0, 4), weekOne = january4 - ((new Date(january4).getUTCDay() + 6) % 7) * day, number = 1 + Math.round((monday - weekOne) / (7 * day));
                scene.add(`ISO week ${year}-W${String(number).padStart(2, '0')}`, { x: plot.x + week * cell, y: plot.y - 18, width: cell, height: 18 }, [label(`W${number}`, plot.x + (week + .5) * cell, plot.y - 5, 9, { 'text-anchor': 'middle' })]);
            }
        points.forEach(p => { const index = Math.floor((Number(p.x) - start) / day), b = { x: plot.x + Math.floor(index / 7) * cell, y: plot.y + index % 7 * cell, width: cell - 1, height: cell - 1 }; scene.add(`${new Date(Number(p.x)).toISOString().slice(0, 10)}: ${p.y}`, b, [box(b, colorScale(p.y, domain), '#fff')], p.datum.source, p.datum.contributors); });
        return;
    }
    const columns = unique(points.map(p => String(p.x))), rows = unique(points.map(p => p.series));
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
    columns.forEach((c, i) => scene.add(c, plot, [label(c, plot.x + (i + .5) * width, plot.y + plot.height + 16, 11, { 'text-anchor': 'middle' })]));
    rows.forEach((r, i) => scene.add(r, plot, [label(r, plot.x - 6, plot.y + (i + .5) * height, 11, { 'text-anchor': 'end' })]));
    points.forEach(p => { const b = { x: plot.x + columns.indexOf(String(p.x)) * width, y: plot.y + rows.indexOf(p.series) * height, width, height }; scene.add(`${p.x}, ${p.series}: ${p.y}`, b, [box(b, colorScale(p.y, domain), '#fff'), label(numberLabel(p.y), b.x + width / 2, b.y + height / 2 + 4, 11, { 'text-anchor': 'middle' })], p.datum.source, p.datum.contributors); });
}
//# sourceMappingURL=data-charts.js.map