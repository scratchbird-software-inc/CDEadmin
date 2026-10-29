import { object, str, num, pathValue } from './model.js';
import { DataScene, finite, valueAt, colors, unique, sum, label, box, path, ellipse, extent, scale, interpolate, numberLabel, pointsPath } from './data-common.js';
import {} from './data-statistics.js';
export function boundaryHistogram(values, boundaries, normalization = 'count', outside = 'error') {
    if (boundaries.length < 2 || boundaries.length > 101 || boundaries.some((value, index) => !finite(value) || index > 0 && value <= boundaries[index - 1]))
        throw new Error('Histogram needs 2..101 finite, strictly increasing bin boundaries.');
    if (!values.length || values.some(value => !finite(value)))
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
export function paretoPlan(values) {
    if (!values.length || values.some(value => !finite(value.value) || value.value < 0))
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
    const total = sum(result.map(value => value.value));
    if (!finite(total) || !(total > 0))
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
export function waterfallPlan(values, steps, baseline = 0) {
    if (!finite(baseline) || values.length !== steps.length || !values.length || values.some(value => !finite(value)))
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
        if (!finite(running))
            throw new Error('Waterfall running total exceeds the finite numeric range.');
        indices.push(index);
        return { kind, start: kind === 'delta' ? before : 0, end: running, value, index, indices: [...indices] };
    });
}
/** The retained quality operations use raw measurements and an explicit bounded transform. */
export function drawQuality(scene, mark, transform, data) {
    const options = scene.settings, authored = object(pathValue(scene.view.record, 'projection.options'));
    for (const key of ['series', 'layers', 'arrangement', 'aggregate'])
        if (Object.hasOwn(authored, key))
            scene.issue(`The ${transform} transform does not admit an authored ${key} option.`);
    if (mark !== 'bar')
        scene.issue(`${transform} requires the bar mark.`);
    const yKey = str(options.y), xKey = str(options.x), stepKey = str(options.step);
    if (!yKey || transform !== 'histogram' && !xKey)
        scene.issue('Choose the required raw measurement and category bindings.');
    if (transform !== 'histogram' && str(options.x_type, 'category') !== 'category')
        scene.issue('This quality transform requires categorical x.');
    if (Array.isArray(options.bins) && (Object.hasOwn(authored, 'step') || Object.hasOwn(authored, 'bin_count') && authored.bin_count !== 'auto'))
        scene.issue('Explicit boundaries cannot also declare a bin step/count.');
    if (transform === 'waterfall' && !stepKey)
        scene.issue('Waterfall requires a step field binding.');
    const rows = data.filter(datum => !(options.missing === 'skip' && (valueAt(datum.values, yKey) == null || transform !== 'histogram' && valueAt(datum.values, xKey) == null)));
    for (const datum of rows) {
        if (!finite(valueAt(datum.values, yKey)))
            scene.issue('Quality measurements must be finite numbers; numeric strings are not coerced.');
        const category = valueAt(datum.values, xKey);
        if (transform !== 'histogram' && typeof category !== 'string' && !finite(category))
            scene.issue('Quality category labels must be present scalar values.');
        if (options.unit && datum.values.unit !== undefined && datum.values.unit !== options.unit)
            scene.issue('Record unit differs from the declared chart unit.');
    }
    if (!rows.length)
        scene.issue('The quality transform needs at least one measured record.');
    if (scene.result.unavailable.length)
        return;
    const plot = { x: scene.bounds.x + 52, y: scene.bounds.y + 50, width: Math.max(80, num(options.width, scene.bounds.width) - 110), height: Math.max(80, num(options.height, scene.bounds.height) - 122) };
    const axes = (domain, categories, xDomain) => {
        const primitives = [label(str(options.unit, yKey), plot.x, plot.y - 12, 11), path(`M${plot.x},${plot.y}V${plot.y + plot.height}H${plot.x + plot.width}`)];
        for (let i = 0; i <= 5; i++) {
            const y = plot.y + plot.height * (1 - i / 5);
            primitives.push(path(`M${plot.x},${y}H${plot.x + plot.width}`, '#e2e8f0'), label(numberLabel(interpolate(domain[0], domain[1], i / 5)), plot.x - 6, y + 4, 10, { 'text-anchor': 'end' }));
            if (xDomain)
                primitives.push(label(numberLabel(interpolate(xDomain[0], xDomain[1], i / 5)), plot.x + i * plot.width / 5, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' }));
        }
        categories?.forEach((category, i) => primitives.push(label(category, plot.x + (i + .5) * plot.width / categories.length, plot.y + plot.height + 18, 10, { 'text-anchor': 'middle' })));
        scene.add(`${transform} axes`, plot, primitives);
    };
    const contributing = (indices) => indices.flatMap(index => rows[index].contributors);
    try {
        if (transform === 'histogram') {
            const values = rows.map(datum => valueAt(datum.values, yKey)), descriptor = object(options.bins), normalization = options.normalize === true ? 'probability' : options.normalize === false ? 'count' : str(options.normalize, 'count');
            if (!Array.isArray(options.bins))
                throw new Error('Histogram transform requires explicit bin boundaries.');
            const bins = boundaryHistogram(values, options.bins, normalization, str(options.outside, 'error'));
            const xd = [bins[0].low, bins.at(-1).high], yd = extent(bins.map(bin => bin.value), true), xs = scale(xd, [plot.x, plot.x + plot.width]), ys = scale(yd, [plot.y + plot.height, plot.y]);
            axes(yd, undefined, xd);
            bins.forEach(bin => { const width = xs(bin.high) - xs(bin.low), bounds = { x: xs(bin.low), y: ys(bin.value), width: width * .96, height: plot.y + plot.height - ys(bin.value) }; scene.add(`${bin.low}–${bin.high}: ${bin.value}`, bounds, [box(bounds, colors[0], 'none')], rows[bin.indices[0]]?.source ?? scene.view, contributing(bin.indices), `${bin.count} measurements; ${normalization}; final upper boundary included`); });
        }
        else if (transform === 'pareto') {
            const values = paretoPlan(rows.map(datum => ({ label: String(valueAt(datum.values, xKey)), value: valueAt(datum.values, yKey) }))), yd = extent(values.map(value => value.value), true), ys = scale(yd, [plot.y + plot.height, plot.y]), band = plot.width / values.length, percent = scale([0, 100], [plot.y + plot.height, plot.y]);
            axes(yd, values.map(value => value.label));
            const line = [];
            values.forEach((value, index) => {
                const x = plot.x + (index + .5) * band, bounds = { x: x - band * .4, y: ys(value.value), width: band * .8, height: plot.y + plot.height - ys(value.value) };
                scene.add(`${value.label}: ${value.value}`, bounds, [box(bounds, colors[index % colors.length], 'none')], rows[value.indices[0]].source, contributing(value.indices));
                const y = percent(value.cumulative);
                line.push([x, y]);
                scene.add(`Cumulative ${value.cumulative}%`, { x: x - 4, y: y - 4, width: 8, height: 8 }, [ellipse(x, y, 4, '#dc2626')], rows[value.indices[0]].source, contributing(value.cumulativeIndices), 'Cumulative percentage of supplied measurements; prefix contributors retained.');
            });
            scene.add('Pareto cumulative percentage', plot, [path(pointsPath(line), '#dc2626'), ...[0, 25, 50, 75, 100].map(value => label(`${value}%`, plot.x + plot.width + 6, percent(value) + 4, 10))], rows[0].source, rows.flatMap(row => row.contributors));
        }
        else if (transform === 'waterfall') {
            const categories = rows.map(datum => String(valueAt(datum.values, xKey)));
            if (unique(categories).length !== categories.length)
                throw new Error('Waterfall requires distinct ordered stage labels.');
            const values = waterfallPlan(rows.map(datum => valueAt(datum.values, yKey)), rows.map(datum => valueAt(datum.values, stepKey)), num(options.baseline, 0)), yd = extent(values.flatMap(value => [value.start, value.end]), true), ys = scale(yd, [plot.y + plot.height, plot.y]), band = plot.width / values.length;
            axes(yd, categories);
            values.forEach((value, index) => {
                const x = plot.x + (index + .5) * band, bounds = { x: x - band * .4, y: ys(Math.max(value.start, value.end)), width: band * .8, height: Math.max(1, Math.abs(ys(value.start) - ys(value.end))) }, color = value.kind === 'total' ? colors[3] : value.kind === 'subtotal' ? colors[0] : value.value >= 0 ? colors[1] : colors[2];
                const primitives = [box(bounds, color, 'none')];
                if (index < values.length - 1)
                    primitives.push(path(`M${x + band * .4},${ys(value.end)}H${x + band * .6}`, '#64748b', 'none', { 'stroke-dasharray': '3 2' }));
                scene.add(`${categories[index]}: ${value.kind} ${value.value}`, bounds, primitives, rows[index].source, contributing(value.indices), `From ${value.start} to ${value.end}; totals are not additional deltas.`);
            });
        }
        scene.caption(transform === 'histogram' ? 'Explicit bins; left inclusive, right exclusive except final upper boundary; ' + str(options.normalize, 'count') : transform === 'pareto' ? 'Descending measurements; line shows cumulative percentage.' : 'Running totals; deltas change the total, subtotals and totals summarize it.');
    }
    catch (error) {
        scene.issue(String(error));
    }
}
//# sourceMappingURL=data-quality.js.map