import { roleDescriptor } from '../../profiles/src/core.js';
import { array, object, pathValue, str, num } from './model.js';
import { box, line, oval, path, rounded, label, nodeGlyph } from './graph-glyphs.js';
const codes = { object: 'OBJ', entity: 'ENT', table: 'TBL', history: 'HIST', term: 'TERM', domain: 'DOM', binding: 'BIND', identity: 'KEY', activity: 'ACT', pipeline: 'PIP', application: 'APP', dataset: 'DST', document: 'DOC', collection: 'COL', array: 'ARR', sample: 'SMP', note: 'NOTE', 'note.sticky': 'NOTE', procedure: 'PRC', function: 'FUN', service: 'SRV', database: 'DB', schema: 'SCM', context: 'CTX', topic: 'TOP', queue: 'QUE', record: 'REC', view: 'VIW', materialized_view: 'MV', rule: 'RULE', test: 'TEST', cloud: 'CLOUD', replica: 'RPL', shard: 'SHD', cache: 'CAC', graph_node: 'NOD', graph_edge: 'EDG', key_value: 'KVS', report: 'RPT', dashboard: 'DSH', data_product: 'DPR', contract: 'CTRT', team: 'TEAM', fact: 'FCT', dimension: 'DIM', vector: 'VEC', backup: 'BAK', recovery: 'RCP', external_actor: 'ACTOR' };
export const nativeCode = (role) => codes[role] ?? role.split('.').at(-1).replaceAll('_', ' ').toUpperCase();
/** Small semantic symbols use retained primitives and stay independent of browser assets. */
export function nativeIcon(glyph, b, color) {
    const { x, y, width: w, height: h } = b, cx = x + w / 2, cy = y + h / 2;
    const p = (d) => path(d, 'none', color, 1.4), l = (a, c, d, e) => line([x + a * w, y + c * h], [x + d * w, y + e * h], color, 1.4);
    if (glyph === 'server')
        return [rounded(b, 'none', color, 2), l(0, .33, 1, .33), l(0, .66, 1, .66), ...[[.18, .18], [.18, .5], [.18, .82]].map(([a, c]) => oval({ x: x + a * w - 1, y: y + c * h - 1, width: 2, height: 2 }, color, color))];
    if (['backup', 'restore', 'cache'].includes(glyph))
        return [oval({ x, y: y + h * .1, width: w * .75, height: h * .28 }, 'none', color), p(`M${x},${y + h * .25}V${y + h * .8}Q${x + w * .35},${y + h} ${x + w * .75},${y + h * .8}V${y + h * .25}`), ...(glyph === 'cache' ? [p(`M${x + w * .7},${y + h * .4}L${x + w * .45},${y + h * .7}H${x + w * .7}L${x + w * .6},${y + h}L${x + w},${y + h * .6}H${x + w * .8}Z`)] : [p(`M${x + w * .55},${y + h * .75}A${w * .25},${h * .25} 0 1 ${glyph === 'restore' ? 0 : 1} ${x + w},${y + h * .75} M${x + w * .75},${y + h * .55}L${x + w},${y + h * .75}L${x + w * .75},${y + h * .85}`)])];
    if (glyph === 'export')
        return [box({ x, y, width: w * .65, height: h }, 'none', color), l(.4, .5, 1, .5), l(.75, .25, 1, .5), l(.75, .75, 1, .5)];
    if (glyph === 'zone')
        return [box(b, 'none', color, 1.4, '3 2'), oval({ x: x + w * .3, y: y + h * .3, width: w * .4, height: h * .4 }, 'none', color)];
    if (glyph === 'copy')
        return [box({ x: x + w * .25, y: y + h * .25, width: w * .75, height: h * .75 }, 'none', color), p(`M${x + w * .15},${y + h * .75}H${x}V${y}H${x + w * .75}V${y + h * .15}`)];
    if (glyph === 'keyvalue')
        return [oval({ x, y, width: w * .35, height: h * .35 }, 'none', color), l(.3, .3, .7, .7), l(.5, .5, .65, .35), l(.65, .8, 1, .8), l(.65, 1, 1, 1)];
    if (glyph === 'people')
        return [[.2, .35], [.8, .35], [.5, .12]].flatMap(([a, c]) => [oval({ x: x + a * w - w * .12, y: y + c * h, width: w * .24, height: h * .24 }, 'none', color), p(`M${x + (a - .2) * w},${y + (c + .6) * h}V${y + (c + .4) * h}Q${x + a * w},${y + (c + .2) * h} ${x + (a + .2) * w},${y + (c + .4) * h}V${y + (c + .6) * h}`)]);
    if (glyph === 'product')
        return [p(`M${cx},${y}L${x + w},${y + h * .25}V${y + h * .75}L${cx},${y + h}L${x},${y + h * .75}V${y + h * .25}Z M${x},${y + h * .25}L${cx},${cy}L${x + w},${y + h * .25} M${cx},${cy}V${y + h}`)];
    if (glyph === 'contract')
        return [box(b, 'none', color), l(.2, .2, .8, .2), l(.2, .4, .8, .4), oval({ x: x + w * .45, y: y + h * .6, width: w * .4, height: h * .3 }, 'none', color), l(.15, .8, .4, .6)];
    if (['table', 'sample', 'dataset', 'record', 'field', 'widecolumn', 'fact', 'dimension', 'bridge'].includes(glyph))
        return [box(b, 'none', color, 1.3), l(0, .3, 1, .3), l(.32, 0, .32, 1), l(0, .65, 1, .65), ...(glyph === 'dimension' ? [l(.65, 0, .65, 1)] : [])];
    if (['database', 'service', 'registry', 'keyspace'].includes(glyph))
        return [p(`M${x},${y + h * .2}V${y + h * .8}C${x},${y + h * 1.06} ${x + w},${y + h * 1.06} ${x + w},${y + h * .8}V${y + h * .2}`), oval({ x, y, width: w, height: h * .4 }, 'none', color, 1.3)];
    if (['book', 'catalog', 'semantic'].includes(glyph))
        return [p(`M${cx},${y + h * .15}Q${x + w * .25},${y - h * .05} ${x},${y + h * .1}V${y + h * .9}Q${x + w * .25},${y + h * .75} ${cx},${y + h}Q${x + w * .75},${y + h * .75} ${x + w},${y + h * .9}V${y + h * .1}Q${x + w * .75},${y - h * .05} ${cx},${y + h * .15}V${y + h}`)];
    if (['gear', 'pipeline', 'job', 'test', 'hand'].includes(glyph)) {
        const points = Array.from({ length: 24 }, (_, i) => { const a = i * Math.PI / 12, r = i % 3 === 0 ? .5 : .38; return `${cx + Math.cos(a) * w * r},${cy + Math.sin(a) * h * r}`; });
        return [p('M' + points.join('L') + 'Z'), oval({ x: x + w * .33, y: y + h * .33, width: w * .34, height: h * .34 }, 'none', color)];
    }
    if (['history', 'clock', 'timeseries', 'schedule', 'calendar', 'recovery'].includes(glyph))
        return [oval(b, 'none', color), l(.5, .18, .5, .5), l(.5, .5, .78, .62)];
    if (['key', 'identity'].includes(glyph))
        return [oval({ x, y, width: w * .45, height: h * .45 }, 'none', color), l(.38, .38, 1, 1), l(.65, .65, .8, .5), l(.8, .8, .95, .65)];
    if (['concept', 'domain', 'type', 'sql_domain', 'variant', 'binding'].includes(glyph))
        return [p(`M${cx},${y}L${x + w},${cy}L${cx},${y + h}L${x},${cy}Z`), ...(glyph === 'binding' ? [l(0, .65, 1, .65)] : [oval({ x: x + w * .34, y: y + h * .34, width: w * .32, height: h * .32 }, 'none', color, 1)])];
    if (['note', 'document', 'file', 'manifest', 'report', 'policy'].includes(glyph))
        return [p(`M${x},${y}H${x + w * .65}L${x + w},${y + h * .32}V${y + h}H${x}Z M${x + w * .65},${y}V${y + h * .32}H${x + w}`), l(.2, .55, .8, .55), l(.2, .75, .7, .75)];
    if (['folder', 'schema', 'package', 'context', 'workspace'].includes(glyph))
        return [p(`M${x},${y + h * .22}V${y}H${cx}L${x + w * .65},${y + h * .22}H${x + w}V${y + h}H${x}Z`)];
    if (['check', 'constraint'].includes(glyph))
        return [l(.05, .5, .35, .85), l(.35, .85, .95, .1)];
    if (['eye', 'materialized', 'search', 'query'].includes(glyph))
        return glyph === 'search' ? [oval({ x, y, width: w * .7, height: h * .7 }, 'none', color), l(.6, .6, 1, 1)] : [p(`M${x},${cy}Q${cx},${y - h * .3} ${x + w},${cy}Q${cx},${y + h * 1.3} ${x},${cy}Z`), oval({ x: x + w * .35, y: y + h * .35, width: w * .3, height: h * .3 }, 'none', color)];
    if (['topic', 'queue', 'publish', 'subscribe', 'consumers'].includes(glyph))
        return [l(.2, 0, .2, 1), l(.4, .25, 1, .25), l(.4, .5, 1, .5), l(.4, .75, 1, .75), oval({ x: x - w * .04, y: y + h * .4, width: w * .2, height: h * .2 }, 'none', color)];
    if (['message', 'command', 'interface', 'endpoint', 'port', 'application'].includes(glyph))
        return [box(b, 'none', color), l(0, .25, 1, .25), ...(glyph === 'message' ? [l(0, .25, .5, .65), l(.5, .65, 1, .25)] : [l(.2, .55, .4, .7), l(.4, .7, .2, .85), l(.55, .8, .85, .8)])];
    if (['node', 'graph', 'edge', 'rdf', 'tensor', 'federation'].includes(glyph))
        return [l(.2, .2, .8, .3), l(.8, .3, .5, .85), l(.5, .85, .2, .2), ...[[.2, .2], [.8, .3], [.5, .85]].map(([a, c]) => oval({ x: x + a * w - 2, y: y + c * h - 2, width: 4, height: 4 }, color, color))];
    if (['chart', 'vector', 'metric', 'model', 'dashboard'].includes(glyph))
        return [l(0, 0, 0, 1), l(0, 1, 1, 1), p(`M${x + w * .15},${y + h * .75}L${x + w * .4},${y + h * .4}L${x + w * .65},${y + h * .6}L${x + w * .95},${y + h * .1}`)];
    if (['cloud', 'bucket'].includes(glyph))
        return [p(`M${x + w * .2},${y + h * .85}C${x - w * .2},${y + h * .8} ${x},${y + h * .3} ${x + w * .25},${y + h * .4}C${x + w * .2},${y - h * .1} ${x + w * .85},${y - h * .1} ${x + w * .8},${y + h * .4}C${x + w * 1.15},${y + h * .25} ${x + w * 1.25},${y + h * .9} ${x + w * .8},${y + h * .85}Z`)];
    if (['bolt', 'trigger'].includes(glyph))
        return [p(`M${x + w * .6},${y}L${x},${y + h * .6}H${x + w * .45}L${x + w * .3},${y + h}L${x + w},${y + h * .4}H${cx}Z`)];
    if (['list', 'array', 'set', 'collection', 'files', 'shard', 'replica'].includes(glyph))
        return [box({ x, y, width: w * .8, height: h * .8 }, 'none', color), p(`M${x + w * .2},${y + h * .85}V${y + h}H${x + w}V${y + h * .2}`), l(.15, .25, .65, .25), l(.15, .5, .65, .5)];
    if (['link', 'alias', 'plug', 'connector'].includes(glyph))
        return [oval({ x, y: y + h * .1, width: w * .65, height: h * .5 }, 'none', color), oval({ x: x + w * .35, y: y + h * .4, width: w * .65, height: h * .5 }, 'none', color)];
    if (['function', 'procedure', 'operator'].includes(glyph))
        return [label(glyph === 'function' ? 'ƒ' : glyph === 'operator' ? '±' : '≡', cx, y + h * .85, h, color, { 'text-anchor': 'middle', 'font-weight': 600 })];
    return [box(b, 'none', color, 1.4)];
}
export function nativeContour(role, record, b, fill, stroke, weight, look, roughness, seed) {
    const descriptor = roleDescriptor(role)?.render, shape = str(descriptor?.shape, 'card'), out = [];
    if (look === 'neo')
        out.push(box({ ...b, x: b.x + 4, y: b.y + 5 }, '#00000020', 'none', 0));
    if (['external_actor', 'uml.actor'].includes(role)) {
        const cx = b.x + b.width / 2, y = b.y + 8, h = Math.max(65, b.height - 44);
        return [oval({ x: cx - 12, y, width: 24, height: 24 }, fill, stroke, weight), line([cx, y + 24], [cx, y + h * .68], stroke, weight), line([cx - 25, y + h * .4], [cx + 25, y + h * .4], stroke, weight), line([cx, y + h * .68], [cx - 25, y + h], stroke, weight), line([cx, y + h * .68], [cx + 25, y + h], stroke, weight)];
    }
    if ((role.startsWith('flow.') || role.startsWith('state.') || role.startsWith('uml.') || role.startsWith('dfd.')) && !(role === 'flow.process' && look === 'handdrawn'))
        return [...out, ...nodeGlyph(role, record, b, { title: '', profile: 'flow.basic@1', fill, stroke, width: weight })];
    if (look === 'handdrawn') {
        let state = seed >>> 0;
        const rnd = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return (state / 4294967296 - .5) * roughness * 3; };
        const points = [[b.x, b.y], [b.x + b.width, b.y], [b.x + b.width, b.y + b.height], [b.x, b.y + b.height], [b.x, b.y]].map(([x, y]) => `${x + rnd()},${y + rnd()}`);
        out.push(path('M' + points.join('L') + 'Z', fill, stroke, weight));
        for (let d = 12; d < b.width + b.height; d += 12) {
            const start = [b.x + Math.max(0, d - b.height), b.y + Math.min(d, b.height)], end = [b.x + Math.min(d, b.width), b.y + Math.max(0, d - b.width)];
            out.push({ kind: 'path', d: `M${start[0]},${start[1]}L${end[0]},${end[1]}`, paint: { fill: 'none', stroke, 'stroke-width': .5, opacity: .1 } });
        }
    }
    else if (shape === 'activity')
        out.push(rounded(b, fill, stroke, 12, weight));
    else if (shape === 'note')
        out.push(path(`M${b.x},${b.y}H${b.x + b.width - 16}L${b.x + b.width},${b.y + 16}V${b.y + b.height}H${b.x}Z M${b.x + b.width - 16},${b.y}V${b.y + 16}H${b.x + b.width}`, fill, stroke, weight));
    else
        out.push(rounded(b, fill, stroke, shape === 'card' ? 5 : 0, weight));
    if (shape === 'frame')
        out.push(box({ x: b.x + 5, y: b.y + 5, width: b.width - 10, height: b.height - 10 }, 'none', stroke, .7, '2 2'));
    return out;
}
const badgeNames = { AUTH: 'AUTHORITATIVE', DER: 'DERIVED', BT: 'BITEMPORAL', EVH: 'EVENT HISTORY', VT: 'VALID TIME', RT: 'RECORDED TIME', CACHE: 'CACHE', PITR: 'PITR' };
export function nativeBadges(record, appearance, view) {
    const facets = object(record.facets), result = [];
    for (const [group, values] of Object.entries(facets))
        if ((group === 'maturity' ? pathValue(view, 'display.maturity') : pathValue(view, 'display.badges')) !== 'none')
            result.push(...array(values).map(v => badgeNames[str(v)] ?? str(v)));
    result.push(...array(appearance?.marks).map(String));
    const distribution = pathValue(record, 'properties.distribution');
    if (distribution && pathValue(view, 'display.badges') !== 'none')
        result.push(String(distribution).toUpperCase());
    return [...new Set(result)];
}
export function badgePrimitives(values, b, size, color, fill) {
    let x = b.x + 12;
    const result = [];
    for (const value of values) {
        const w = value.length * size * .6 + 10;
        result.push(rounded({ x, y: b.y + b.height - 22, width: w, height: 16 }, fill, color, 3, .7), label(value, x + 5, b.y + b.height - 10, size, color, { 'font-weight': 600 }));
        x += w + 6;
    }
    return result;
}
export function inheritedPresentation(values, properties, view) {
    const result = { ...values };
    for (const group of ['style', 'text']) {
        const next = { ...object(values[group]) };
        for (const [key, value] of Object.entries(object(view[group]))) {
            if (group === 'style' && !['look', 'font', 'font_size', 'seed', 'roughness', 'theme'].includes(key))
                continue;
            const origin = properties.find(p => p.path === group + '.' + key)?.origin;
            if (!origin || origin === 'standard:definition' || origin === 'standard:appearance')
                next[key] = value;
        }
        result[group] = next;
    }
    return result;
}
//# sourceMappingURL=native-render.js.map