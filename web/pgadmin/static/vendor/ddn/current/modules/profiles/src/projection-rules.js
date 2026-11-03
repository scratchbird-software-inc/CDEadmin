import { getProfile } from './core.js';
import { getPath, isRecord, stableStringify } from './schema-core.js';
import { profileSelection } from './semantic.js';
const obj = (v) => isRecord(v) ? v : {};
const arr = (v) => Array.isArray(v) ? v : [];
const str = (v) => typeof v === 'string' ? v : '';
const num = (v) => typeof v === 'number' && Number.isFinite(v);
const key = (r) => r.file + '\0' + r.ref.id;
const same = (a, b) => a === undefined || b === undefined ? a === b : stableStringify(a) === stableStringify(b);
/** Options admitted by the retained mark operations, before defaults are added. */
export function chartOptionErrors(profileId, authored) {
    const specialized = profileId.slice(6).split('@')[0], transform = str(authored.transform), operation = ['histogram', 'pareto', 'waterfall', 'boxplot'].includes(transform), mark = str(authored.mark) || (operation ? transform === 'boxplot' ? 'boxplot' : 'bar' : ['basic', 'quality'].includes(specialized) ? 'bar' : specialized), layers = arr(authored.layers).map(obj);
    const errors = [];
    const common = ['width', 'height', 'records', 'mark', 'x', 'y', 'x_type', 'unit', 'aggregate', 'filter', 'order', 'missing'];
    const specific = { bar: ['series', 'series_missing', 'arrangement', 'baseline', 'transform', 'layers', 'error'], line: ['series', 'series_missing', 'arrangement', 'transform', 'layers', 'error', 'trend'], area: ['series', 'series_missing', 'arrangement', 'baseline', 'transform', 'layers', 'error'], point: ['series', 'series_missing', 'transform', 'layers', 'size', 'error', 'trend'], pie: [], donut: ['inner_radius'], radar: ['series'], funnel: [], gauge: ['target'], candlestick: ['open', 'high', 'low', 'close'], histogram: ['bin_count', 'bins', 'normalize', 'outside', 'step'], density: [], qq: [], quantiledot: [], dotplot: [], beeswarm: [], boxplot: ['quartiles', 'whiskers'], violin: [], topk: ['k', 'others'], treemap: ['depth'], tidytree: ['depth'], radialtree: ['depth'], circlepack: ['depth'], sunburst: ['depth'], packedbubble: ['depth'], heatmap: ['series'], densityheatmap: ['bin_count'], calendar: ['iso'], parallelcoords: ['series'], wordcloud: [], sankey: ['target'], arc: ['target'], force: ['target'], edgebundle: ['target'] };
    const operationFields = { histogram: ['bins', 'normalize', 'outside'], pareto: [], waterfall: ['step', 'baseline'], boxplot: ['quartiles', 'whiskers'] };
    if (!Object.hasOwn(specific, mark))
        errors.push('No chart operation is registered for ' + mark);
    const extrudable = ['bar', 'area', 'pie', 'donut', 'treemap'].includes(mark);
    const allowed = new Set(operation ? [...common.filter(name => name !== 'aggregate'), 'transform', ...operationFields[transform]] : [...common, ...specific[mark] ?? [], ...(extrudable ? ['iso', 'depth'] : []), ...(layers.some(layer => layer.mark === 'point') ? ['size'] : []), ...(layers.some(layer => ['line', 'point'].includes(str(layer.mark))) ? ['trend'] : [])]);
    if (authored.iso === true && extrudable && authored.depth !== undefined && (typeof authored.depth === 'string' ? !authored.depth.trim() : !num(authored.depth) || authored.depth < 0 || authored.depth > 2000))
        errors.push('Chart extrusion depth must be a channel name or a finite number between 0 and 2000');
    for (const name of Object.keys(authored))
        if (!allowed.has(name))
            errors.push('Option ' + name + ' does not apply to ' + mark);
    if (!operation && mark === 'boxplot' && (authored.quartiles !== undefined && authored.quartiles !== 'linear' || authored.whiskers !== undefined && authored.whiskers !== 'iqr' && authored.whiskers !== 1.5))
        errors.push('Direct boxplots use linear R7 quartiles and Tukey 1.5-IQR whiskers');
    return errors;
}
export function projectionRows(view, records) {
    const { resolve } = profileSelection(view, records), options = obj(getPath(view.record, 'projection.options'));
    const refs = options.records === undefined ? [] : Array.isArray(options.records) ? options.records : [options.records];
    const rows = [];
    for (const ref of refs) {
        const source = resolve(ref);
        if (!source)
            continue;
        const data = source.owner === 'data' ? source.record : source.record.data === undefined ? undefined : obj(source.record.data);
        if (data) {
            const columns = arr(data.columns).map(v => str(obj(v).id));
            for (const row of arr(data.rows))
                rows.push({ source: source.ref, values: Array.isArray(row) ? Object.fromEntries(columns.map((name, i) => [name, row[i] ?? null])) : obj(row) });
        }
        else
            rows.push({ source: source.ref, values: { ...source.record, ...obj(getPath(source.record, 'metadata.x_record')) } });
    }
    return rows.filter(row => arr(options.filter).every(filter => { const f = obj(filter), value = getPath(row.values, str(f.key)); return f.op === 'in' ? arr(f.value).some(v => same(value, v)) : same(value, f.value); }));
}
export function projectionDiagnostics(view, records, review) {
    const profile = getProfile(str(view.record.profile));
    if (!profile)
        return [];
    const result = [], options = {};
    for (const [path, value] of Object.entries(profile.defaults))
        if (path.startsWith('projection.options.') && value.kind === 'literal' && value.value !== undefined)
            options[path.slice(19)] = value.value;
    Object.assign(options, obj(getPath(view.record, 'projection.options')));
    const { resolve, nodes, edges, links, selected } = profileSelection(view, records);
    const issue = (code, message, target = view.ref, severity = 'error') => result.push({ code, severity, message, target, rule: 'ddn.profile.' + profile.id });
    const incomplete = (message) => { if (review)
        issue('DDN-PROJECTION-INCOMPLETE', message, view.ref, 'warning'); };
    const binding = (row, name, fallback) => getPath(row.values, str(options[name]) || fallback || name);
    const rows = projectionRows(view, records);
    const geoMark = str(options.mark) || (profile.id === 'geo.outline@1' ? 'outline' : profile.id === 'geo.symbols@1' ? 'symbol' : 'choropleth');
    if (['chart', 'timeline', 'geo'].includes(profile.projection)) {
        if (options.records === undefined && !(profile.projection === 'geo' && geoMark === 'outline'))
            incomplete('Projection needs an explicit records binding');
        const refs = options.records === undefined ? [] : Array.isArray(options.records) ? options.records : [options.records];
        for (const ref of refs)
            if (!resolve(ref))
                issue('DDN-PROJECTION-REFERENCE', 'Projection input does not resolve');
        if (refs.length && !rows.length && arr(options.filter).length && projectionRows({ ...view, record: { ...view.record, projection: { options: { ...options, filter: [] } } } }, records).length)
            issue('DDN-PROJECTION-FILTER', 'Filtering nonempty input to no records is not a completed projection');
    }
    if (profile.projection === 'chart') {
        if (options.iso === true && typeof options.depth === 'string')
            for (const row of rows) {
                const depth = getPath(row.values, options.depth);
                if (!num(depth) || depth < 0 || depth > 2000)
                    issue('DDN-CHART-DEPTH', 'Every extrusion depth must be finite and between 0 and 2000', row.source);
            }
        for (const message of chartOptionErrors(profile.id, obj(getPath(view.record, 'projection.options'))))
            issue('DDN-CHART-OPTION', message);
        const operation = str(options.transform);
        if (['histogram', 'pareto', 'waterfall', 'boxplot'].includes(operation)) {
            const authored = obj(getPath(view.record, 'projection.options')), mark = str(authored.mark) || (operation === 'boxplot' ? 'boxplot' : 'bar');
            if (mark !== (operation === 'boxplot' ? 'boxplot' : 'bar'))
                issue('DDN-TRANSFORM-MARK', 'Transform ' + operation + ' requires ' + (operation === 'boxplot' ? 'boxplot' : 'bar') + ' marks');
            if (!str(options.y) || operation !== 'histogram' && !str(options.x)) {
                incomplete('Transform requires explicit measured y and applicable x channel bindings');
                return result;
            }
            const values = [];
            for (const row of rows) {
                const x = binding(row, 'x'), y = binding(row, 'y');
                if ((y === null || y === undefined || operation !== 'histogram' && (x === null || x === undefined)) && options.missing === 'skip')
                    continue;
                if (!num(y) || operation !== 'histogram' && typeof x !== 'string' && !num(x)) {
                    issue('DDN-TRANSFORM-DATA', 'Transform channels require finite measurements and scalar categories', row.source);
                    continue;
                }
                values.push({ x, y, row });
            }
            if (!values.length)
                incomplete('Transform requires nonempty measurements');
            if (operation === 'histogram') {
                const bounds = arr(options.bins);
                if (!bounds.length)
                    incomplete('Histogram transform requires explicit bin boundaries');
                else if (bounds.length < 2 || bounds.length > 101 || bounds.some((bound, index) => { const previous = bounds[index - 1]; return !num(bound) || index > 0 && num(previous) && bound <= previous; }))
                    issue('DDN-TRANSFORM-BINS', 'Histogram transform requires 2..101 strictly increasing finite boundaries');
                else {
                    const low = bounds[0], high = bounds.at(-1), outside = values.filter(value => value.y < low || value.y > high);
                    if ((options.outside ?? 'error') === 'error' && outside.length)
                        issue('DDN-HISTOGRAM-OUTSIDE', 'Samples lie outside the declared transform bins');
                    if (options.outside === 'drop' && outside.length === values.length && values.length)
                        issue('DDN-HISTOGRAM-EMPTY', 'Histogram bounds exclude every sample');
                }
            }
            if (operation === 'pareto' && values.length && (values.some(value => value.y < 0) || !num(values.reduce((sum, value) => sum + value.y, 0)) || values.reduce((sum, value) => sum + value.y, 0) <= 0))
                issue('DDN-PARETO-TOTAL', 'Pareto requires nonnegative measurements with a positive finite total');
            if (operation === 'waterfall') {
                if (!str(options.step))
                    incomplete('Waterfall requires a step field binding');
                let total = num(options.baseline) ? options.baseline : 0;
                for (const value of values) {
                    const step = getPath(value.row.values, str(options.step));
                    if (step === 'delta')
                        total += value.y;
                    else if (step === 'subtotal' || step === 'total') {
                        if (Math.abs(value.y - total) > 1e-10 * Math.max(1, Math.abs(total), Math.abs(value.y)))
                            issue('DDN-WATERFALL-TOTAL', 'Declared subtotal/total does not match the running total', value.row.source);
                    }
                    else if (options.step !== undefined)
                        issue('DDN-WATERFALL-STEP', 'Step must be delta, subtotal or total', value.row.source);
                    if (!num(total))
                        issue('DDN-WATERFALL-RANGE', 'Running total exceeds the finite numeric range', value.row.source);
                }
            }
            if (operation === 'boxplot') {
                if (options.quartiles !== undefined && options.quartiles !== 'linear' || options.whiskers !== undefined && !['iqr', 'minmax'].includes(str(options.whiskers)) && options.whiskers !== 1.5)
                    issue('DDN-BOXPLOT-METHOD', 'Boxplot transform uses linear R7 quartiles and IQR or minmax whiskers');
                if (new Set(values.map(value => stableStringify(value.x ?? null))).size > 40)
                    issue('DDN-CHART-CATEGORY-LIMIT', 'Boxplot transform permits at most 40 categories');
            }
            return result;
        }
        const mark = str(options.mark) || (profile.id === 'chart.basic@1' || profile.id === 'chart.quality@1' ? 'bar' : profile.id.slice(6).split('@')[0]);
        const samples = ['histogram', 'density', 'qq', 'quantiledot'].includes(mark), linksMark = ['sankey', 'arc', 'force', 'edgebundle'].includes(mark), hierarchy = ['treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble'].includes(mark);
        if (!rows.length && !['bar', 'line', 'area', 'point'].includes(mark) && options.records !== undefined)
            incomplete(mark + ' requires records');
        if (str(options.aggregate) && options.aggregate !== 'none' && !['bar', 'pie', 'donut', 'topk'].includes(mark))
            issue('DDN-CHART-AGGREGATE', 'Aggregation is not available for ' + mark);
        if (options.aggregate === 'count' && options.unit !== undefined)
            issue('DDN-CHART-COUNT-UNIT', 'Count has no physical unit');
        if (samples && (options.y !== undefined || options.series !== undefined))
            issue('DDN-CHART-SAMPLE-CHANNEL', 'Raw-sample marks do not accept y or series');
        if (mark === 'densityheatmap' && options.x_type !== 'number')
            issue('DDN-CHART-XTYPE', mark + ' requires numeric x');
        if (['bar', 'pie', 'donut', 'radar', 'funnel'].includes(mark) && options.x_type !== undefined && options.x_type !== 'category')
            issue('DDN-CHART-XTYPE', mark + ' requires categorical x');
        if (['bar', 'area'].includes(mark) && options.baseline !== undefined && options.baseline !== 0)
            issue('DDN-CHART-BASELINE', 'Area-encoded marks require a zero baseline');
        if (samples && rows.length < 2)
            incomplete(mark + ' requires at least two samples');
        if (mark === 'boxplot' && (options.quartiles !== undefined && options.quartiles !== 'linear' || options.whiskers !== undefined && options.whiskers !== 'iqr' && options.whiskers !== 1.5))
            issue('DDN-BOXPLOT-METHOD', 'Direct boxplots use linear R7 quartiles and Tukey 1.5-IQR whiskers');
        const nonnegative = ['pie', 'donut', 'radar', 'funnel', 'treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble'].includes(mark);
        const values = [], categories = new Set(), series = new Set(), pairs = new Set(), dates = new Set(), nodeNames = new Set();
        const groups = new Map(), graph = new Map();
        for (const row of rows) {
            const x = binding(row, 'x'), y = binding(row, samples ? 'x' : 'y'), s = binding(row, 'series');
            const missing = x === undefined || x === null || mark !== 'candlestick' && (y === undefined || y === null);
            if (missing) {
                if ((options.missing ?? 'error') === 'error')
                    issue('DDN-CHART-MISSING', 'Chart input has a missing channel value', row.source);
                else
                    continue;
            }
            if (mark !== 'candlestick' && !num(y))
                issue('DDN-CHART-NUMBER', 'Chart measurements must be finite numbers; strings are not coerced', row.source);
            if (num(y)) {
                values.push(y);
                if (nonnegative && y < 0 || (linksMark || mark === 'wordcloud') && y <= 0)
                    issue('DDN-CHART-RANGE', mark + ' has an out-of-range value', row.source);
            }
            if ((samples || options.x_type === 'number') && !num(x))
                issue('DDN-CHART-NUMBER', 'Numeric x must be finite', row.source);
            if (options.x_type === 'date' && (typeof x !== 'string' || !validDate(x)))
                issue('DDN-CHART-DATE', 'Date axes require ISO dates or zoned instants', row.source);
            if (options.unit !== undefined && row.values.unit !== undefined && options.unit !== row.values.unit)
                issue('DDN-CHART-UNIT', 'Record and projection units disagree', row.source);
            const category = stableStringify(x ?? null), seriesName = stableStringify(s ?? null), pair = category + '\0' + seriesName;
            categories.add(category);
            series.add(seriesName);
            if (['heatmap', 'parallelcoords'].includes(mark) && pairs.has(pair))
                issue('DDN-CHART-DUPLICATE', 'Each category/series pair requires one measurement', row.source);
            pairs.add(pair);
            const group = groups.get(category) ?? [];
            if (num(y))
                group.push(y);
            groups.set(category, group);
            if (mark === 'calendar') {
                const date = typeof x === 'string' && validDate(x) ? new Date(x).toISOString().slice(0, 10) : '';
                if (!date || dates.has(date))
                    issue('DDN-CALENDAR-DAY', 'Calendar requires one value per valid UTC day', row.source);
                dates.add(date);
            }
            if (mark === 'candlestick') {
                const [o, h, l, c] = ['open', 'high', 'low', 'close'].map(name => binding(row, name));
                if (![o, h, l, c].every(num) || o > h || o < l || c > h || c < l || h < l)
                    issue('DDN-CANDLESTICK-OHLC', 'OHLC must be finite with open/close inside low..high', row.source);
            }
            if (hierarchy && (typeof x !== 'string' || !x || x.split('.').some(part => !part)))
                issue('DDN-HIERARCHY-PATH', 'Hierarchy paths need nonempty dotted segments', row.source);
            if (linksMark) {
                const target = getPath(row.values, str(options.target) || 'target');
                if (options.target !== undefined && typeof options.target !== 'string' || typeof x !== 'string' || !x || typeof target !== 'string' || !target || x === target)
                    issue('DDN-CHART-LINK', 'Links require distinct named endpoints and a text target field binding', row.source);
                else {
                    nodeNames.add(x);
                    nodeNames.add(target);
                    graph.set(x, [...graph.get(x) ?? [], target]);
                    if (mark === 'edgebundle' && Math.max(x.split('.').length, target.split('.').length) > 3)
                        issue('DDN-EDGEBUNDLE-DEPTH', 'Edge bundle paths permit at most three levels', row.source);
                }
            }
            if (options.transform === 'log' && num(y) && y <= 0 || options.transform === 'sqrt' && num(y) && y < 0)
                issue('DDN-CHART-TRANSFORM', 'Transform input is outside its numeric domain', row.source);
            if (options.error !== undefined) {
                const error = obj(options.error), low = getPath(row.values, str(error.low)), high = getPath(row.values, str(error.high));
                if (error.low !== undefined && (!num(low) || num(y) && low > y) || error.high !== undefined && (!num(high) || num(y) && high < y))
                    issue('DDN-CHART-ERROR-BOUNDS', 'Error interval must bracket its measured value', row.source);
            }
        }
        if (rows.length && ['pie', 'donut'].includes(mark) && values.reduce((a, b) => a + b, 0) <= 0)
            issue('DDN-CHART-TOTAL', 'Arc shares need a positive total');
        if (mark === 'gauge') {
            if (!rows.length)
                incomplete('Gauge requires one value');
            if (rows.length > 1 || values.some(v => v < 0 || v > 100) || options.target !== undefined && (!num(options.target) || options.target < 0 || options.target > 100))
                issue('DDN-GAUGE-RANGE', 'Gauge requires one value and optional target in 0..100');
        }
        if (mark === 'density' && values.length > 1 && new Set(values).size < 2)
            issue('DDN-DENSITY-UNKNOWN', 'Zero-variance data has no defined density estimate', view.ref, 'warning');
        if (['boxplot', 'violin'].includes(mark) && categories.size > 40)
            issue('DDN-CHART-CATEGORY-LIMIT', 'Distribution plots allow at most 40 categories');
        if (mark === 'violin' && [...groups.values()].some(v => v.length < 2 || new Set(v).size < 2))
            issue('DDN-VIOLIN-UNKNOWN', 'Each violin needs at least two nonidentical observations', view.ref, 'warning');
        if (mark === 'radar' && categories.size < 3)
            incomplete('Radar needs at least three categories');
        if (mark === 'funnel' && categories.size < 2)
            incomplete('Funnel requires at least two stages');
        if (mark === 'qq' && values.length > 1 && new Set(values).size < 2)
            issue('DDN-QQ-UNKNOWN', 'Zero-variance samples have no defined normal reference comparison', view.ref, 'warning');
        if (mark === 'densityheatmap' && rows.length && (categories.size < 2 || new Set(values).size < 2))
            issue('DDN-DENSITYHEATMAP-UNKNOWN', 'Density heatmap requires nonzero range on both axes', view.ref, 'warning');
        if (hierarchy) {
            const paths = rows.map(row => str(binding(row, 'x')));
            if (paths.some(path => path.split('.').length > 3))
                issue('DDN-HIERARCHY-DEPTH', 'Hierarchy paths permit at most three levels');
            if (new Set(paths).size !== paths.length || paths.some(path => paths.some(other => other.startsWith(path + '.'))))
                issue('DDN-HIERARCHY-LEAF', 'Hierarchy input requires unique leaf paths; an input leaf cannot also be a parent');
        }
        if (mark === 'parallelcoords' && ([...groups.values()].some(values => new Set(values).size < 2) || pairs.size < categories.size * series.size))
            issue('DDN-PARALLEL-UNKNOWN', 'Constant or missing axes are unknown and display at mid-height', view.ref, 'warning');
        if (options.series !== undefined && (mark === 'radar' || options.series_missing === 'error' || ['stack', 'percent'].includes(str(options.arrangement)) && options.series_missing !== 'zero') && pairs.size < categories.size * series.size)
            issue('DDN-CHART-SERIES-INCOMPLETE', 'Each series requires a measurement at every category or an explicitly supported zero fill');
        if (mark === 'heatmap' && (categories.size > 60 || series.size > 60))
            issue('DDN-HEATMAP-LIMIT', 'Heatmap is bounded to 60 by 60');
        if (mark === 'parallelcoords') {
            if (categories.size < 2)
                incomplete('Parallel coordinates require at least two axes');
            if (categories.size > 24)
                issue('DDN-PARALLEL-AXES', 'Parallel coordinates permit at most 24 axes');
        }
        if (mark === 'wordcloud' && (rows.length > 120 || categories.size !== rows.length))
            issue('DDN-WORDCLOUD-LIMIT', 'Word cloud permits at most 120 unique words');
        if (linksMark && (nodeNames.size > 200 || rows.length > (mark === 'edgebundle' ? 500 : 1000)))
            issue('DDN-LINK-CHART-LIMIT', 'Link chart exceeds its bounded nodes/links');
        if (mark === 'sankey') {
            const visited = new Set(), active = new Set();
            const visit = (n) => { if (active.has(n))
                return false; if (visited.has(n))
                return true; active.add(n); for (const child of graph.get(n) ?? [])
                if (!visit(child))
                    return false; active.delete(n); visited.add(n); return true; };
            if ([...nodeNames].some(n => !visit(n)))
                issue('DDN-SANKEY-CYCLE', 'Sankey flows must form a DAG');
        }
        if (['histogram', 'densityheatmap'].includes(mark) && options.bin_count !== undefined && options.bin_count !== 'auto' && (!Number.isInteger(options.bin_count) || options.bin_count < 2 || options.bin_count > (mark === 'histogram' ? 100 : 60)))
            issue('DDN-CHART-BINS', 'Bin count is outside the mark-specific bound');
        if (mark === 'topk' && options.k !== undefined && (!Number.isInteger(options.k) || options.k < 1 || options.k > 100))
            issue('DDN-TOPK-BOUND', 'Top-k requires k in 1..100');
        if (profile.id === 'chart.quality@1' && (series.size > 20 || pairs.size > 200))
            issue('DDN-QUALITY-LIMIT', 'Quality chart is bounded to 20 series and 200 coordinates');
        if (options.arrangement === 'percent' && (values.some(v => v < 0) || [...groups.values()].some(v => v.reduce((a, b) => a + b, 0) <= 0)))
            issue('DDN-PERCENT-TOTAL', 'Percent arrangement requires nonnegative values and positive category totals');
        const layers = arr(options.layers).map(obj);
        if (layers.length && (options.transform !== undefined && options.transform !== 'identity' || layers.some(layer => !['bar', 'line', 'area', 'point'].includes(str(layer.mark) || mark))))
            issue('DDN-CHART-LAYERS', 'Layers require identity operation and ordinary cartesian marks');
        if (layers.length && options.series !== undefined && series.size && layers.length !== series.size)
            issue('DDN-CHART-LAYERS', 'Declare one layer per series in series order');
        for (const layer of layers)
            for (const row of rows) {
                const value = getPath(row.values, str(layer.y) || str(options.y));
                if (!num(value))
                    issue('DDN-CHART-LAYER-DATA', 'Each layer measurement must be finite', row.source);
            }
        if (mark === 'histogram' && options.bins !== undefined) {
            const bins = obj(options.bins), count = bins.count ?? options.bin_count, min = bins.min, max = bins.max, step = bins.step;
            if (count !== undefined && count !== 'auto' && (!Number.isInteger(count) || count < 2 || count > 100) || min !== undefined && !num(min) || max !== undefined && !num(max) || num(min) && num(max) && min >= max || step !== undefined && (!num(step) || step <= 0))
                issue('DDN-HISTOGRAM-BINS', 'Histogram bins require increasing finite bounds, positive step, and 2..100 bins');
            if ((options.outside ?? 'error') === 'error' && values.some(value => num(min) && value < min || num(max) && value > max))
                issue('DDN-HISTOGRAM-OUTSIDE', 'Sample lies outside the explicitly declared histogram bounds');
        }
        if (mark === 'histogram') {
            if (Array.isArray(options.bins))
                issue('DDN-HISTOGRAM-BINS', 'Explicit boundary arrays require the histogram transform');
            const bins = obj(options.bins), step = options.step ?? bins.step, count = typeof options.bins === 'number' ? options.bins : bins.count ?? options.bin_count;
            if (typeof options.bins === 'number' && (!Number.isInteger(options.bins) || options.bins < 2 || options.bins > 100))
                issue('DDN-HISTOGRAM-BINS', 'Histogram bin count is bounded to 2..100');
            if (step !== undefined) {
                if (!num(step) || step <= 0)
                    issue('DDN-HISTOGRAM-BINS', 'Direct histogram step must be a positive number');
                else if (values.length) {
                    let low = num(bins.min) ? bins.min : Math.min(...values), high = num(bins.max) ? bins.max : Math.max(...values);
                    if (low === high && bins.min === undefined && bins.max === undefined) {
                        low -= .5;
                        high += .5;
                    }
                    const exact = high / step - low / step;
                    if (!num(exact) || Math.abs(exact - Math.round(exact)) > 1e-10 || exact < 2 || exact > 100 || num(count) && count !== Math.round(exact))
                        issue('DDN-HISTOGRAM-BINS', 'Step must divide the domain into 2..100 bins and agree with explicit count');
                }
            }
        }
    }
    if (profile.projection === 'matrix') {
        const rowRefs = arr(options.rows), columnRefs = arr(options.columns), rowItems = rowRefs.map(r => resolve(r)), columnItems = columnRefs.map(r => resolve(r));
        if (review && (!rowRefs.length || !columnRefs.length || !str(options.relation)))
            incomplete('Matrix needs explicit rows, columns and relation role');
        if (rowRefs.length * columnRefs.length > 5000 || columnRefs.length > 40)
            issue('DDN-MATRIX-SIZE', 'Matrix is bounded to 5000 cells and 40 columns');
        if (rowItems.some(r => !r) || columnItems.some(r => !r))
            issue('DDN-MATRIX-REFERENCE', 'Matrix axes must resolve');
        if (new Set(rowItems.filter((r) => !!r).map(key)).size !== rowRefs.length || new Set(columnItems.filter((r) => !!r).map(key)).size !== columnRefs.length)
            issue('DDN-MATRIX-AXIS', 'Matrix axes must be unique');
        const cells = new Map(), rowCodes = new Map(), stories = new Set();
        for (const link of links.filter(l => l.item.record.role === options.relation)) {
            if (!rowItems.includes(link.from) || !columnItems.includes(link.to))
                continue;
            const id = key(link.from) + '\0' + key(link.to), existing = cells.get(id) ?? [];
            cells.set(id, [...existing, link]);
            const value = options.value ? getPath(link.item.record, str(options.value)) : getPath(link.item.record, 'metadata.x_assignment.code');
            if (profile.id === 'matrix.raci@1' && !['R', 'A', 'C', 'I'].includes(str(value)))
                issue('DDN-RACI-CODE', 'RACI codes must be R, A, C or I', link.item.ref);
            if (profile.id === 'matrix.crud@1' && (!/^[CRUD]+$/.test(str(value)) || new Set(str(value)).size !== str(value).length))
                issue('DDN-CRUD-CODE', 'CRUD codes require unique C/R/U/D letters', link.item.ref);
            rowCodes.set(key(link.from), [...rowCodes.get(key(link.from)) ?? [], str(value)]);
            if (profile.id === 'matrix.storymap@1') {
                const task = resolve(getPath(link.item.record, 'metadata.x_story.task'), link.item);
                if (!task || task.record.role !== 'analysis.task' || !selected.has(key(task)))
                    issue('DDN-STORYMAP-TASK', 'Story cell must reference a selected task', link.item.ref);
                else if (stories.has(key(task)))
                    issue('DDN-STORYMAP-DUPLICATE', 'A story can appear in only one cell', link.item.ref);
                else
                    stories.add(key(task));
            }
        }
        for (const cell of cells.values())
            if (cell.length > 1 && (options.duplicates !== 'join' || ['matrix.raci@1', 'matrix.crud@1', 'matrix.heatmap@1'].includes(profile.id)))
                issue('DDN-MATRIX-DUPLICATE', 'Duplicate cell assignment is not allowed', cell[0].item.ref);
        if (profile.id === 'matrix.raci@1' && review)
            for (const row of rowItems)
                if (row) {
                    const codes = rowCodes.get(key(row)) ?? [];
                    if (codes.filter(c => c === 'A').length !== 1 || !codes.includes('R'))
                        issue('DDN-RACI-ACCOUNTABILITY', 'Every completed row requires exactly one A and at least one R', row.ref);
                }
        const axes = { 'matrix.bcg@1': ['growth', ['high', 'low'], 'share', ['high', 'low']], 'matrix.ansoff@1': ['market', ['existing', 'new'], 'product', ['existing', 'new']], 'matrix.tows@1': ['internal', ['strength', 'weakness'], 'external', ['opportunity', 'threat']] };
        if (axes[profile.id]) {
            const [ra, rv, ca, cv] = axes[profile.id];
            if (rowItems.length < 2 || columnItems.length < 2)
                incomplete('Strategy matrix requires two rows and two columns');
            if (rowItems.length > 2 || columnItems.length > 2)
                issue('DDN-STRATEGY-AXES', 'Strategy matrix permits only two rows and two columns');
            for (const [items, axis, values] of [[rowItems, ra, rv], [columnItems, ca, cv]]) {
                const levels = items.map(n => n && obj(getPath(n.record, 'metadata.x_category')));
                if (levels.some(v => !v || v.axis === undefined || v.level === undefined))
                    incomplete('Strategy matrix categories need axis and level');
                if (levels.some(v => v && (v.axis !== undefined && v.axis !== axis || v.level !== undefined && !values.includes(str(v.level)))) || levels.length === 2 && levels.every(v => v && v.level !== undefined) && new Set(levels.map(v => v && v.level)).size !== 2)
                    issue('DDN-STRATEGY-CATEGORY', 'Strategy matrix categories do not match its declared axes');
            }
        }
        if (profile.id === 'matrix.heatmap@1') {
            const encoding = obj(options.encoding), domain = obj(encoding.domain), range = obj(encoding.range), mode = str(encoding.mode) || 'numeric';
            const values = [...cells.values()].flatMap(cell => cell.map(link => options.value ? getPath(link.item.record, str(options.value)) : getPath(link.item.record, 'metadata.x_assignment.code'))).filter(value => value !== undefined && value !== null);
            if (!['numeric', 'categorical', 'threshold'].includes(mode))
                issue('DDN-MATRIX-ENCODING', 'Heatmap mode must be numeric, categorical or threshold');
            if (mode === 'numeric' || mode === 'threshold') {
                if (values.some(value => !num(value)))
                    issue('DDN-MATRIX-VALUE', 'Numeric heatmap values must be finite numbers');
                if (encoding.domain !== undefined && (!num(domain.min) || !num(domain.max) || domain.min >= domain.max))
                    issue('DDN-MATRIX-DOMAIN', 'Explicit numeric domains require finite increasing bounds');
                const minimum = domain.min, maximum = domain.max;
                if (num(minimum) && num(maximum) && values.some(value => num(value) && (value < minimum || value > maximum)))
                    issue('DDN-MATRIX-VALUE', 'Encoded values must fit the explicit numeric domain');
            }
            const labels = arr(encoding.labels), boundaries = arr(encoding.boundaries);
            if (encoding.scale !== undefined && !['blue', 'diverging', 'linear'].includes(str(encoding.scale)))
                issue('DDN-MATRIX-SCALE', 'Heatmap scale must be blue, diverging or linear');
            if (mode === 'categorical' && (values.some(value => typeof value === 'object') || new Set(values.map(value => stableStringify(value))).size > 12 || labels.length && values.some(value => !labels.some(label => same(value, label)))))
                issue('DDN-MATRIX-CATEGORIES', 'Categorical heatmaps require 1..12 scalar labels and values within their declared domain');
            if (mode === 'threshold') {
                if (encoding.boundaries !== undefined) {
                    if (boundaries.length < 2 || boundaries.length > 13 || boundaries.some((value, index) => { const previous = boundaries[index - 1]; return !num(value) || index > 0 && num(previous) && value <= previous; }))
                        issue('DDN-MATRIX-THRESHOLD', 'Band boundaries must contain 2..13 strictly increasing finite values');
                    else {
                        const first = boundaries[0], last = boundaries.at(-1);
                        if (values.some(value => num(value) && (value < first || value > last)))
                            issue('DDN-MATRIX-VALUE', 'Band values must fit the explicit boundary domain');
                    }
                }
                else if (!num(range.min) || !num(range.max) || range.min >= range.max)
                    issue('DDN-MATRIX-THRESHOLD', 'Threshold heatmaps require increasing range bounds or explicit boundaries');
            }
        }
    }
    if (profile.projection === 'panels') {
        const columns = typeof options.columns === 'number' ? options.columns : 1, panels = arr(options.panels), occupied = new Set(), ids = new Set();
        if (!Number.isInteger(columns) || columns < 1 || columns > 12 || panels.length > 80)
            issue('DDN-PANELS-LIMIT', 'Panel grid permits 1..12 columns and at most 80 panels');
        if (!panels.length)
            incomplete('Panel view needs at least one panel');
        const layouts = [];
        for (const [index, raw] of panels.entries()) {
            const inclusion = obj(raw), target = resolve(inclusion.target);
            if (!target) {
                issue('DDN-PANEL-TARGET', 'Panel target must resolve');
                continue;
            }
            const data = obj(getPath(target.record, 'metadata.x_record')), placement = { ...data, ...obj(inclusion.layout) }, id = inclusion.kind === 'view' ? key(view) + ':panel:' + index : str(data.id) || str(target.record.name) || target.ref.id;
            const row = typeof placement.row === 'number' ? placement.row : Math.floor(index / columns), column = typeof placement.column === 'number' ? placement.column : index % columns, rowspan = typeof placement.rowspan === 'number' ? placement.rowspan : 1, colspan = typeof placement.colspan === 'number' ? placement.colspan : 1;
            layouts.push({ id, row, column, rowspan, colspan, data, inclusion });
            if (ids.has(id))
                issue('DDN-PANEL-ID', 'Panel IDs must be unique', target.ref);
            ids.add(id);
            if (![row, column, rowspan, colspan].every(Number.isInteger) || row < 0 || row > 100 || column < 0 || rowspan < 1 || colspan < 1 || column + colspan > columns || row + rowspan > 101) {
                issue('DDN-PANEL-BOUNDS', 'Panel spans must stay inside the grid', target.ref);
                continue;
            }
            for (let r = row; r < row + rowspan; r++)
                for (let c = column; c < column + colspan; c++) {
                    const cell = r + ':' + c;
                    if (occupied.has(cell))
                        issue('DDN-PANEL-OVERLAP', 'Panel cells cannot overlap', target.ref);
                    occupied.add(cell);
                }
            if (inclusion.kind === 'view' && arr(data.items).length)
                issue('DDN-PANEL-CONTENT', 'A panel holds either a view or item references', target.ref);
            if (inclusion.kind === 'view') {
                if (target === view)
                    issue('DDN-PANEL-RECURSION', 'Panel cannot embed its containing view', target.ref);
                if (arr(getPath(target.record, 'projection.options.panels')).some(v => obj(v).kind === 'view'))
                    issue('DDN-PANEL-DEPTH', 'Embedded panels support one child-view level', target.ref);
            }
        }
        const required = profile.standard_overrides['template.required_panel_ids'];
        if (Array.isArray(required) && review && required.some(id => !ids.has(str(id))))
            issue('DDN-CANVAS-PANELS', 'Canvas is missing required named blocks');
        if (profile.id === 'panels.pyramid@1') {
            if (panels.length < 3)
                incomplete('Pyramid requires at least three bands');
            if (columns !== 1 || panels.length > 5 || layouts.some((p, i) => p.row !== i || p.rowspan !== 1 || p.colspan !== 1))
                issue('DDN-PYRAMID-BANDS', 'Pyramid requires one column and at most five contiguous single-row bands');
        }
        if (profile.id === 'panels.venn@1') {
            if (panels.length < 2)
                incomplete('Venn requires at least two sets');
            if (panels.length > 3)
                issue('DDN-VENN-SETS', 'Venn supports at most three sets');
            const memberships = new Map();
            for (const panel of layouts)
                for (const reference of arr(panel.data.items)) {
                    const target = resolve(reference);
                    if (!target) {
                        issue('DDN-PANEL-ITEM', 'Panel member must resolve');
                        continue;
                    }
                    const membership = memberships.get(key(target)) ?? { target, sets: new Set() };
                    membership.sets.add(panel.id);
                    memberships.set(key(target), membership);
                }
            for (const { target, sets } of memberships.values()) {
                const declared = arr(getPath(target.record, 'metadata.x_sets'));
                if (!declared.length)
                    incomplete('Venn members require their exact declared set IDs');
                else if (declared.length !== sets.size || declared.some(id => !sets.has(str(id))))
                    issue('DDN-VENN-MEMBERSHIP', 'Venn member set IDs must exactly match panel membership', target.ref);
            }
        }
        if (profile.id === 'panels.journey@1' && layouts.length) {
            const phases = layouts.filter(panel => panel.id.startsWith('phase-')).sort((a, b) => a.column - b.column), slugs = phases.map(panel => panel.id.slice(6));
            if (phases.length < 2)
                incomplete('Journey requires at least two phases');
            if (phases.length > 8 || columns > 8)
                issue('DDN-JOURNEY-PHASES', 'Journey permits at most eight phase columns');
            if (phases.length !== columns)
                incomplete('Journey needs one phase for each declared column');
            const expected = new Map();
            slugs.forEach((slug, column) => ['phase', 'actions', 'touchpoints', 'opportunities'].forEach((prefix, row) => expected.set(prefix + '-' + slug, { row, column, colspan: 1 })));
            expected.set('emotions', { row: 4, column: 0, colspan: columns });
            if ([...expected.keys()].some(id => !ids.has(id)))
                incomplete('Journey requires phase, actions, touchpoints, opportunities and emotions panels');
            for (const panel of layouts) {
                const position = expected.get(panel.id);
                if (!position || panel.row !== position.row || panel.column !== position.column || panel.colspan !== position.colspan || panel.rowspan !== 1)
                    issue('DDN-JOURNEY-LAYOUT', 'Journey panel IDs and positions must match the declared phase grid');
            }
            const emotion = layouts.find(panel => panel.id === 'emotions'), seen = new Set();
            for (const reference of arr(emotion?.data.items)) {
                const target = resolve(reference), value = obj(getPath(target?.record, 'metadata.x_record')), phase = str(value.phase);
                if (!target || !slugs.includes(phase) || seen.has(phase) || !num(value.value) || value.value < 1 || value.value > 5)
                    issue('DDN-JOURNEY-EMOTION', 'Emotion records require a unique declared phase and a value from 1 through 5');
                seen.add(phase);
            }
        }
    }
    if (profile.projection === 'timeline') {
        const calendar = obj(view.record.calendar), holidays = arr(calendar.holidays);
        if (holidays.some(value => typeof value !== 'string' || value.length !== 10 || !validDate(value)) || new Set(holidays).size !== holidays.length)
            issue('DDN-TIMELINE-HOLIDAYS', 'Business holidays must be unique valid date-only values');
        for (const row of rows) {
            const start = binding(row, 'start'), end = binding(row, 'end');
            if (typeof start !== 'string' || !validDate(start) || end !== undefined && end !== null && (typeof end !== 'string' || !validDate(end)))
                issue('DDN-TIMELINE-DATE', 'Timeline requires ISO dates or explicitly zoned timestamps', row.source);
            else if (typeof end === 'string' && Date.parse(end) < Date.parse(start))
                issue('DDN-TIMELINE-ORDER', 'End cannot precede start', row.source);
        }
        const instants = rows.flatMap(row => [binding(row, 'start'), binding(row, 'end')]).filter((value) => typeof value === 'string' && validDate(value)).map(Date.parse);
        if (options.calendar === 'business' && instants.length && (Math.max(...instants) - Math.min(...instants)) / 86400000 > 366000)
            issue('DDN-TIMELINE-RANGE', 'Business counting is bounded to 366000 days');
        for (const reference of arr(options.dependencies)) {
            const dependency = resolve(reference);
            if (!dependency || dependency.record.category !== 'relation')
                issue('DDN-TIMELINE-DEPENDENCY', 'Timeline dependencies must resolve to relations');
            else
                for (const endpoint of arr(dependency.record.endpoints)) {
                    const target = resolve(obj(endpoint).definition, dependency);
                    if (!target || !rows.some(row => key(target) === row.source.file + '\0' + row.source.id))
                        issue('DDN-TIMELINE-DEPENDENCY', 'Dependency endpoints must be included timeline records', dependency.ref);
                }
        }
        if (options.timezone !== undefined)
            try {
                new Intl.DateTimeFormat('en', { timeZone: str(options.timezone) }).format(0);
            }
            catch {
                issue('DDN-TIMEZONE-UNKNOWN', 'Named timezone is unavailable in this host', view.ref, 'warning');
            }
        if (options.calendar !== undefined && !['gregorian', 'fiscal', 'business'].includes(str(options.calendar)))
            issue('DDN-TIMELINE-CALENDAR', 'Calendar must be gregorian, fiscal or business');
    }
    if (profile.projection === 'fishbone') {
        const effects = nodes.filter(n => n.record.role === 'quality.effect'), effect = options.effect ? resolve(options.effect) : effects[0];
        if (review && (effects.length !== 1 || !effect))
            issue('DDN-FISHBONE-EFFECT', 'Fishbone requires exactly one selected effect');
        if (effect) {
            const used = new Set(), active = new Set();
            let occurrences = 0;
            const visit = (n, depth) => { if (++occurrences > 250 || depth > 4) {
                issue('DDN-FISHBONE-LIMIT', 'Fishbone exceeds four cause levels or 250 occurrences');
                return;
            } if (active.has(key(n))) {
                issue('DDN-FISHBONE-CYCLE', 'Fishbone cannot cycle');
                return;
            } active.add(key(n)); used.add(key(n)); for (const l of links.filter(l => l.to === n && (!options.relation || l.item.record.role === options.relation)))
                visit(l.from, depth + 1); active.delete(key(n)); };
            visit(effect, 0);
            const categories = links.filter(l => l.to === effect);
            if (review && (categories.length < 1 || categories.length > 12 || categories.some(l => l.from.record.role !== 'quality.category')))
                issue('DDN-FISHBONE-CATEGORIES', 'Effect requires 1..12 first-level category ribs');
            if (links.some(l => !used.has(key(l.from)) || !used.has(key(l.to))))
                issue('DDN-FISHBONE-DISCONNECTED', 'Selected cause graph contains disconnected branches');
        }
    }
    if (profile.projection === 'geo') {
        if (!str(options.geography))
            incomplete('Geographic projection requires host-supplied geography');
        if (!['outline', 'symbol', 'choropleth'].includes(geoMark))
            issue('DDN-GEO-MARK', 'Geographic projections admit outline, symbol or choropleth marks');
        if (geoMark === 'symbol')
            for (const row of rows) {
                const longitude = binding(row, 'x'), latitude = binding(row, 'y');
                if (!num(longitude) || longitude < -180 || longitude > 180 || !num(latitude) || latitude < -90 || latitude > 90)
                    issue('DDN-GEO-COORDINATE', 'Geographic coordinates must be finite longitude/latitude in range', row.source);
                if (options.size !== undefined && (!num(binding(row, 'size')) || binding(row, 'size') < 0))
                    issue('DDN-GEO-SIZE', 'Symbol size must be finite and nonnegative', row.source);
            }
        if (geoMark === 'choropleth') {
            const seen = new Set();
            for (const row of rows) {
                const region = binding(row, 'x'), value = binding(row, 'value');
                const id = stableStringify(region ?? null);
                if (region === undefined || seen.has(id))
                    issue('DDN-GEO-REGION', 'Choropleth region keys must be present and unique', row.source);
                seen.add(id);
                if (!num(value))
                    issue('DDN-GEO-VALUE', 'Choropleth measures must be finite numbers', row.source);
            }
        }
    }
    return result;
}
function validDate(value) { if (!/^\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d))?$/.test(value) || !Number.isFinite(Date.parse(value)))
    return false; const date = value.slice(0, 10); return new Date(date).toISOString().slice(0, 10) === date; }
//# sourceMappingURL=projection-rules.js.map