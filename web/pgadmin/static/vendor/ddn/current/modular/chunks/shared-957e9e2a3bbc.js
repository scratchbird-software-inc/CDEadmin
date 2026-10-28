/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-957e9e2a3bbc","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-2f1e15abcacd","shared-4d0c8910f2dc","shared-da593b1d80b5"],"modules":[{"id":"presentation/src/card-text.js","bytes":882,"sha256":"1037e1238d236c485d38e88a485db55c796b0f212105421188a942e33417185f","dependencies":["presentation/src/table.js"]},{"id":"presentation/src/graph-common.js","bytes":73356,"sha256":"1e62ac560804d05f4c4df2b9d57f4f2c6b9abd083e654ad1967089886bf88bd8","dependencies":["profiles/src/core.js","profiles/src/mindmap.js","presentation/src/model.js","presentation/src/graph-layouts.js","presentation/src/symbol-presentation.js","presentation/src/graph-glyphs.js","presentation/src/relation-presentation.js"]},{"id":"presentation/src/graph-glyphs.js","bytes":40661,"sha256":"5c859ad1c537113ff42815f456b70917de413f46f0d1520a2619ba06080f4abb","dependencies":["presentation/src/card-text.js","profiles/src/core.js","presentation/src/model.js"]},{"id":"presentation/src/graph-layouts.js","bytes":18547,"sha256":"b5b8d5af3a08530c976413a12d669eb79202aa488f615a7e43512d73b6257808","dependencies":[]},{"id":"presentation/src/graph-native.js","bytes":2597,"sha256":"0c66e8ffea24994a828040329b0c61b9074e8fbdae9e10096004ac01fe2f2e8e","dependencies":["presentation/src/model.js","presentation/src/graph-common.js","presentation/src/mindmap.js","presentation/src/relation-presentation.js"]},{"id":"presentation/src/markdown.js","bytes":3043,"sha256":"504d2c1ae4851ac74e8acc37bb036c0810d0b5a0362b5141d71fea13710d8941","dependencies":[]},{"id":"presentation/src/mindmap.js","bytes":15575,"sha256":"245f311851ce1c77564e8c5dd2f7cd64096ba5859db58e1e076cb5fa9c2d82ac","dependencies":["profiles/src/mindmap.js","profiles/src/core.js","presentation/src/model.js","presentation/src/graph-common.js","presentation/src/graph-glyphs.js"]},{"id":"presentation/src/relation-presentation.js","bytes":4402,"sha256":"72691c559ba54894daf1ba2dfe8ba96d3bf4015c66064bd8ec8b4cbd6134deb9","dependencies":["presentation/src/model.js","profiles/src/mindmap.js"]},{"id":"presentation/src/symbol-presentation.js","bytes":15153,"sha256":"2b6669b66c12c0a55c80a04ccf40258043fbc627d3d1c9a3fbffe98a247ad072","dependencies":["presentation/src/model.js","presentation/src/table.js","presentation/src/markdown.js"]}],"hash":"6bcf2602a406401199f8e1d9256acd64c37cda82efc3bca2b838da9765384762"},{"presentation/src/card-text.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.cardTextLayout = cardTextLayout;
const table_js_1 = require("presentation/src/table.js");
function cardTextLayout(type, title, width, measure, typeSize, titleSize, padding = 12) {
    const available = Math.max(8, width - padding * 2);
    const typeWidth = type ? Math.min(Math.max(20, measure(type, typeSize)), Math.max(20, Math.min(96, available * .32))) : 0;
    const gap = type ? 12 : 0;
    const titleOffset = padding + typeWidth + gap;
    const titleWidth = Math.max(8, width - padding - titleOffset);
    const typeLines = type ? (0, table_js_1.wrapCell)(type, typeWidth, text => measure(text, typeSize), 64).lines : [];
    return { typeWidth, typeLines, titleOffset, titleWidth, titleLines: (0, table_js_1.wrapCell)(title, titleWidth, text => measure(text, titleSize), 64).lines };
}

},
"presentation/src/graph-common.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.changed = exports.finiteBounds = exports.identity = exports.center = void 0;
exports.provisionalNodes = provisionalNodes;
exports.mark = mark;
exports.memberRecords = memberRecords;
exports.endEntry = endEntry;
exports.endpoint = endpoint;
exports.resolvedText = resolvedText;
exports.styled = styled;
exports.guardText = guardText;
exports.edgeLabel = edgeLabel;
exports.orthogonalRoute = orthogonalRoute;
exports.graphLabelBounds = graphLabelBounds;
exports.placeGraphLabel = placeGraphLabel;
exports.roundedRoute = roundedRoute;
exports.cubicPoints = cubicPoints;
exports.roundedPoints = roundedPoints;
exports.routeIntersects = routeIntersects;
exports.crossingRoute = crossingRoute;
exports.cleanRoute = cleanRoute;
exports.decorateEdge = decorateEdge;
exports.boundaryPoint = boundaryPoint;
exports.layoutNative = layoutNative;
exports.graphAdornments = graphAdornments;
exports.inlineInteractions = inlineInteractions;
const core_js_1 = require("profiles/src/core.js");
const mindmap_js_1 = require("profiles/src/mindmap.js");
const model_js_1 = require("presentation/src/model.js");
const graph_layouts_js_1 = require("presentation/src/graph-layouts.js");
const symbol_presentation_js_1 = require("presentation/src/symbol-presentation.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
const relation_presentation_js_1 = require("presentation/src/relation-presentation.js");
const center = (b) => [b.x + b.width / 2, b.y + b.height / 2];
exports.center = center;
exports.identity = [1, 0, 0, 1, 0, 0];
function provisionalNodes(entries, all) {
    const nodes = entries.filter(entry => entry.definition.record.category !== 'relation');
    const connected = new Set(entries.filter(entry => entry.definition.record.category === 'relation').flatMap(edge => (0, model_js_1.array)(edge.definition.record.endpoints).map((_, index) => endEntry(edge, index, nodes, all)?.item.occurrence)));
    return nodes.filter(node => node.appearance?.record.pinned === false && typeof node.appearance.record.position === 'object' && !connected.has(node.item.occurrence));
}
const finiteBounds = (a, b, padding = 4) => ({ x: Math.min(a[0], b[0]) - padding, y: Math.min(a[1], b[1]) - padding, width: Math.max(1, Math.abs(a[0] - b[0])) + padding * 2, height: Math.max(1, Math.abs(a[1] - b[1])) + padding * 2 });
exports.finiteBounds = finiteBounds;
const changed = (entry, bounds, primitives, description) => ({ ...entry, item: { ...entry.item, bounds, primitives, transform: exports.identity, hitTargets: [{ id: entry.item.occurrence, target: entry.definition.ref, bounds }], accessible: { ...entry.item.accessible, ...(description ? { description } : {}) } } });
exports.changed = changed;
function mark(owner, target, suffix, bounds, primitives, description) {
    const occurrence = owner.item.occurrence + ':' + suffix;
    return { ...owner, definition: target, item: { ...owner.item, occurrence, target: target.ref, bounds, primitives, transform: exports.identity, hitTargets: [{ id: occurrence, target: target.ref, bounds }], accessible: { role: 'graphics-symbol', label: (0, model_js_1.titleOf)(target.record), description } } };
}
function memberRecords(entry, all) {
    const declared = (0, model_js_1.array)(entry.definition.record.members).map(ref => (0, model_js_1.resolveRecord)(all, ref, entry.definition.file)).filter((v) => !!v);
    for (const record of all)
        if (record.owner === 'definition' && (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, record.record.parent ?? (0, model_js_1.pathValue)(record.record, 'content.parent') ?? (0, model_js_1.pathValue)(record.record, 'content.owner'), record.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(entry.definition.ref) && !declared.includes(record))
            declared.push(record);
    return declared;
}
function endEntry(edge, at, nodes, all) {
    const end = (0, model_js_1.object)((0, model_js_1.array)(edge.definition.record.endpoints)[at]);
    const semantic = (0, model_js_1.resolveRecord)(all, end.definition ?? end.target ?? end.ref, edge.definition.file);
    if (!semantic)
        return undefined;
    const occurrence = (0, model_js_1.resolveRecord)(all, (0, model_js_1.pathValue)(edge.appearance?.record, at === 0 ? 'route.from' : 'route.to'), edge.appearance?.file ?? edge.definition.file);
    return nodes.find(n => (0, model_js_1.refKey)(n.definition.ref) === (0, model_js_1.refKey)(semantic.ref) && (!occurrence || n.appearance && (0, model_js_1.refKey)(n.appearance.ref) === (0, model_js_1.refKey)(occurrence.ref)));
}
function portBounds(entry) {
    return entry.item.hitTargets.find(hit => (0, model_js_1.refKey)(hit.target) === (0, model_js_1.refKey)(entry.definition.ref))?.bounds ?? entry.item.bounds;
}
function sidePoint(entry, side, fraction, shaped, automatic = false) {
    const b = shaped || entry.standalone ? portBounds(entry) : entry.item.bounds, horizontal = side === 'west' || side === 'east', sign = side === 'west' || side === 'north' ? -1 : 1;
    const c = (0, exports.center)(b);
    const ellipse = shaped && entry.item.primitives.some(p => p.kind === 'ellipse' && Math.abs(p.bounds.width - b.width) < .01 && Math.abs(p.bounds.height - b.height) < .01 && Math.abs(p.bounds.x + entry.item.transform[4] - b.x) < .01 && Math.abs(p.bounds.y + entry.item.transform[5] - b.y) < .01);
    const f = automatic && !ellipse ? .5 : Math.max(0, Math.min(1, fraction)), transverse = (f - .5) * 2;
    const extent = ellipse ? Math.sqrt(Math.max(0, 1 - transverse * transverse)) : 1;
    return horizontal ? [c[0] + sign * b.width / 2 * extent, b.y + b.height * f] : [b.x + b.width * f, c[1] + sign * b.height / 2 * extent];
}
function endpoint(edge, at, entry, other, all, shaped = false) {
    const end = (0, model_js_1.object)((0, model_js_1.array)(edge.definition.record.endpoints)[at]);
    const member = (0, model_js_1.resolveRecord)(all, end.member ?? end.port, edge.definition.file), bounds = shaped || entry.standalone ? portBounds(entry) : entry.item.bounds;
    const routeSide = (0, model_js_1.str)((0, model_js_1.pathValue)(edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side')), routeFraction = (0, model_js_1.num)((0, model_js_1.pathValue)(edge.appearance?.record, at === 0 ? 'route.source_fraction' : 'route.target_fraction'), .5);
    const terminal = (0, symbol_presentation_js_1.symbolTerminal)(entry, other, routeSide, routeFraction);
    if (terminal)
        return terminal;
    if (routeSide === 'north' || routeSide === 'south')
        return sidePoint(entry, routeSide, routeFraction, shaped);
    if (routeSide === 'west' || routeSide === 'east')
        return sidePoint(entry, routeSide, routeFraction, shaped);
    if (member) {
        const side = (0, model_js_1.str)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_icom')).type, (0, model_js_1.str)((0, model_js_1.pathValue)(member.record, 'content.direction')));
        const ports = memberRecords(entry, all).filter(record => (0, model_js_1.str)(record.record.role) === 'core::Port'), portIndex = ports.findIndex(record => (0, model_js_1.refKey)(record.ref) === (0, model_js_1.refKey)(member.ref)), fraction = portIndex < 0 ? .5 : (portIndex + 1) / (ports.length + 1);
        if (side === 'north' || side === 'top' || side === 'control')
            return [bounds.x + bounds.width * fraction, bounds.y];
        if (side === 'south' || side === 'bottom' || side === 'mechanism')
            return [bounds.x + bounds.width * fraction, bounds.y + bounds.height];
        if (side === 'west' || side === 'left' || side === 'input')
            return [bounds.x, bounds.y + bounds.height * fraction];
        if (side === 'east' || side === 'right' || side === 'output')
            return [bounds.x + bounds.width, bounds.y + bounds.height * fraction];
    }
    const a = (0, exports.center)(bounds), b = (0, exports.center)(other.standalone ? portBounds(other) : other.item.bounds), dx = b[0] - a[0], dy = b[1] - a[1];
    if (Math.abs(dx) / bounds.width >= Math.abs(dy) / bounds.height)
        return sidePoint(entry, dx >= 0 ? 'east' : 'west', shaped ? Math.max(.25, Math.min(.75, .5 + dy / (bounds.height * 2))) : .5, shaped, true);
    return sidePoint(entry, dy >= 0 ? 'south' : 'north', shaped ? Math.max(.25, Math.min(.75, .5 + dx / (bounds.width * 2))) : .5, shaped, true);
}
function resolvedText(entries, profile) {
    return entries.map(entry => {
        if (entry.standalone)
            return entry;
        if (['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile) && entry.definition.record.category !== 'relation')
            return entry;
        if (profile === 'erd.crowfoot@1' && ['columns', 'draft', 'notes'].includes((0, model_js_1.str)(entry.appearance?.record.body, (0, model_js_1.str)(entry.effective.body))))
            return entry;
        const font = (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'style.font')), size = (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.font_size'), 16), color = (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'text.color'));
        return { ...entry, item: { ...entry.item, primitives: entry.item.primitives.map(primitive => primitive.kind === 'text' ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, fontKey: font || run.fontKey, style: { ...run.style, 'font-size': (0, model_js_1.num)(run.style['font-size'], 14) * size / 16, ...(color ? { fill: color } : {}) } })) } : primitive) } };
    });
}
function styled(entry, key, fallback) {
    const origin = entry.propertyOrigins?.[key];
    const own = (0, model_js_1.pathValue)(entry.appearance?.record, key) ?? (0, model_js_1.pathValue)(entry.definition.record, key);
    if (own !== undefined || origin && (!origin.startsWith('standard:') || origin.startsWith('standard:theme')))
        return (0, model_js_1.pathValue)(entry.effective, key) ?? own ?? fallback;
    if (origin)
        return fallback;
    const value = (0, model_js_1.pathValue)(entry.effective, key);
    return value !== undefined && !['#fff', '#ffffff', 'transparent', '#475569', '#1f2933', 'solid', 'none', 'classic', 1, 1.5, 0].includes(value) ? value : fallback;
}
function guardText(value) {
    if (typeof value === 'string')
        return value;
    const record = (0, model_js_1.object)(value), op = (name) => ({ eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤', in: 'in' }[(0, model_js_1.str)(name)] ?? (0, model_js_1.str)(name));
    if (record.field)
        return `${(0, model_js_1.str)(record.field)} ${op(record.op)} ${String(record.value)}`;
    if (Array.isArray(record.all) || Array.isArray(record.any))
        return (0, model_js_1.array)(record.all ?? record.any).map(guardText).join(record.all ? ' and ' : ' or ');
    return Object.entries(record).map(([field, value]) => { const test = (0, model_js_1.object)(value); return Object.keys(test).length ? `${field} ${op(test.op)} ${String(test.value ?? '')}` : `${field} = ${String(value)}`; }).join(' and ');
}
function edgeLabel(entry, all = []) {
    const record = entry.definition.record, role = (0, model_js_1.str)(record.role), transition = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_transition')), message = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_message'));
    let title = typeof record.title === 'string' ? record.title : (0, model_js_1.str)(record.name);
    if (role === 'state.transition')
        title = `${(0, model_js_1.str)(transition.event)}${transition.guard ? ' [' + guardText(transition.guard) + ']' : ''}${transition.effect ? ' / ' + (0, model_js_1.str)(transition.effect) : ''}` || title;
    if (role === 'uml.message' && ['create', 'delete'].includes((0, model_js_1.str)(message.sort)) && !title.includes('«'))
        title = '«' + (0, model_js_1.str)(message.sort) + '» ' + title;
    if (role === 'uml.message')
        title = `${message.seq ? String(message.seq) + ': ' : ''}${title}${message.time ? ' {' + (0, model_js_1.str)(message.time) + '}' : ''}${message.duration ? ' {' + (0, model_js_1.str)(message.duration) + '}' : ''}`;
    const stereotypes = { 'uml.include': 'include', 'uml.extend': 'extend', 'uml.import': 'import', 'uml.access': 'access', 'uml.merge': 'merge', 'uml.deploy': 'deploy', 'uml.manifest': 'manifest', 'uml.application': 'apply', 'sysml.derive': 'deriveReqt', 'sysml.satisfy': 'satisfy', 'sysml.verify': 'verify', 'sysml.refine': 'refine', 'sysml.trace': 'trace', 'sysml.copy': 'copy', 'sysml.master': 'master', 'sysml.allocate': 'allocate', 'req.satisfies': 'satisfies', 'req.verifies': 'verifies' };
    if (stereotypes[role])
        title = `«${stereotypes[role]}»${title && title.replace(/[«»\s_-]/g, '').toLowerCase() !== stereotypes[role].toLowerCase() ? ' ' + title : ''}`;
    if (role.startsWith('uaf.'))
        title = `«${role.slice(4)}»${title && title.replace(/[«»\s_-]/g, '').toLowerCase() !== role.slice(4).toLowerCase() ? ' ' + title : ''}`;
    const flow = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_flow'));
    for (const key of ['rate', 'probability', 'continuous'])
        if (flow[key] !== undefined)
            title += ` {${key}=${String(flow[key])}}`;
    const usecase = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_usecase'));
    if (usecase.condition)
        title += ` [${(0, model_js_1.str)(usecase.condition)}]`;
    const sdl = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_sdl'));
    if (sdl.signals) {
        const signals = '[' + (0, model_js_1.array)(sdl.signals).map(value => { const target = (0, model_js_1.resolveRecord)(all, value, entry.definition.file); return target ? (0, model_js_1.titleOf)(target.record) : typeof value === 'string' ? value.split('::').at(-1).split('.').at(-1) : (0, model_js_1.str)((0, model_js_1.object)(value).name, (0, model_js_1.str)((0, model_js_1.object)(value).id)); }).join(', ') + ']';
        if (title.replaceAll(' ', '') !== signals.replaceAll(' ', ''))
            title += ' ' + signals;
    }
    if (sdl.nodelay)
        title += ' NODELAY';
    const compatibility = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_compatibility'));
    if (compatibility.mode)
        title += ' {' + (0, model_js_1.str)(compatibility.mode) + '}';
    const continuation = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_continuation'));
    if (continuation.key)
        title += ' [' + (0, model_js_1.str)(continuation.key) + ']';
    const evidence = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_evidence'));
    if (evidence.result)
        title += ' [' + (0, model_js_1.str)(evidence.result) + ']';
    const petri = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_petri'));
    if (petri.weight !== undefined && petri.weight !== 1)
        title += ` ${String(petri.weight)}`;
    return title;
}
function orthogonalRoute(a, b, obstacles) {
    const clearance = 18;
    const blocked = (p, q, r) => p[0] === q[0] ? p[0] > r.x - 3 && p[0] < r.x + r.width + 3 && Math.max(p[1], q[1]) > r.y - 3 && Math.min(p[1], q[1]) < r.y + r.height + 3 : p[1] === q[1] && p[1] > r.y - 3 && p[1] < r.y + r.height + 3 && Math.max(p[0], q[0]) > r.x - 3 && Math.min(p[0], q[0]) < r.x + r.width + 3;
    const candidates = [[a, [b[0], a[1]], b], [a, [a[0], b[1]], b], [a, [(a[0] + b[0]) / 2, a[1]], [(a[0] + b[0]) / 2, b[1]], b]];
    const top = Math.min(a[1], b[1], ...obstacles.map(r => r.y)) - clearance, bottom = Math.max(a[1], b[1], ...obstacles.map(r => r.y + r.height)) + clearance, left = Math.min(a[0], b[0], ...obstacles.map(r => r.x)) - clearance, right = Math.max(a[0], b[0], ...obstacles.map(r => r.x + r.width)) + clearance;
    for (const y of [top, bottom])
        candidates.push([a, [a[0], y], [b[0], y], b]);
    for (const x of [left, right])
        candidates.push([a, [x, a[1]], [x, b[1]], b]);
    const nearby = obstacles.filter(r => r.x < Math.max(a[0], b[0]) + clearance && r.x + r.width > Math.min(a[0], b[0]) - clearance && r.y < Math.max(a[1], b[1]) + clearance && r.y + r.height > Math.min(a[1], b[1]) - clearance).slice(0, 12);
    for (const obstacle of nearby)
        for (const y of [obstacle.y - clearance, obstacle.y + obstacle.height + clearance])
            candidates.push([a, [a[0], y], [b[0], y], b]);
    const scored = candidates.map(points => ({ points: points.filter((point, i) => !i || point[0] !== points[i - 1][0] || point[1] !== points[i - 1][1]), crossings: points.slice(1).reduce((sum, point, i) => sum + obstacles.filter(r => blocked(points[i], point, r)).length, 0), length: points.slice(1).reduce((sum, point, i) => sum + Math.abs(point[0] - points[i][0]) + Math.abs(point[1] - points[i][1]), 0) }));
    scored.sort((x, y) => x.crossings - y.crossings || x.length - y.length);
    return scored[0].points;
}
function graphLabelBounds(value, x, y, size, anchor = 'start') {
    const width = [...value].reduce((sum, char) => sum + (/[^\u0000-\u024f]/u.test(char) ? 1 : /[MW@#%]/.test(char) ? .9 : /[il.,' :;]/.test(char) ? .4 : .65) * size, 0) + 8;
    return { x: x - (anchor === 'middle' ? width / 2 : anchor === 'end' ? width : 0) - 4, y: y - size - 3, width, height: size + 8 };
}
function placeGraphLabel(value, points, obstacles, reserved, size, avoidRoute = false) {
    const lines = value.split('\n'), measurements = lines.map(line => graphLabelBounds(line, 0, 0, size)), width = Math.max(...measurements.map(m => m.width)), height = measurements[0].height + (lines.length - 1) * size * 1.25;
    const intersects = (a, b) => a.x < b.x + b.width + 4 && a.x + a.width + 4 > b.x && a.y < b.y + b.height + 4 && a.y + a.height + 4 > b.y;
    const occupied = [...obstacles, ...reserved], routeSegments = points.slice(1).map((b, i) => ({ a: points[i], b, length: Math.hypot(b[0] - points[i][0], b[1] - points[i][1]) })), segments = [...routeSegments].sort((a, b) => b.length - a.length).slice(0, 16);
    const anchors = [], total = routeSegments.reduce((sum, segment) => sum + segment.length, 0);
    for (const fraction of [.5, .4, .6, .25, .75]) {
        let remaining = total * fraction;
        for (const segment of routeSegments) {
            if (remaining > segment.length) {
                remaining -= segment.length;
                continue;
            }
            const t = segment.length ? remaining / segment.length : 0;
            anchors.push({ point: [segment.a[0] + (segment.b[0] - segment.a[0]) * t, segment.a[1] + (segment.b[1] - segment.a[1]) * t], horizontal: Math.abs(segment.b[0] - segment.a[0]) >= Math.abs(segment.b[1] - segment.a[1]), cost: Math.abs(fraction - .5) * 20 });
            break;
        }
    }
    for (const [rank, segment] of segments.entries())
        for (const fraction of [.5, .25, .75])
            anchors.push({ point: [segment.a[0] + (segment.b[0] - segment.a[0]) * fraction, segment.a[1] + (segment.b[1] - segment.a[1]) * fraction], horizontal: Math.abs(segment.b[0] - segment.a[0]) >= Math.abs(segment.b[1] - segment.a[1]), cost: 3 + rank * 3 + Math.abs(fraction - .5) * segment.length * .1 });
    const candidates = [];
    for (const { point, horizontal, cost } of anchors)
        for (const verticalOffset of [horizontal, !horizontal])
            for (const gap of [8, 24, 40, 64, 88, 120, 160])
                for (const side of [-1, 1]) {
                    const bounds = verticalOffset ? { x: point[0] - width / 2, y: side < 0 ? point[1] - gap - height : point[1] + gap, width, height } : { x: side < 0 ? point[0] - gap - width : point[0] + gap, y: point[1] - height / 2, width, height };
                    candidates.push({ bounds, point, cost: gap + cost + (verticalOffset === horizontal ? 0 : 4) });
                }
    const chosen = candidates.sort((a, b) => a.cost - b.cost).find(candidate => candidate.bounds.y >= (obstacles[0]?.y ?? 0) + (obstacles[0]?.height ?? 0) && occupied.every(bound => !intersects(candidate.bounds, bound)) && (!avoidRoute || !routeIntersects(points, { x: candidate.bounds.x - 5, y: candidate.bounds.y - 5, width: candidate.bounds.width + 10, height: candidate.bounds.height + 10 })));
    const point = chosen?.point ?? points[0] ?? [0, 0], bounds = chosen?.bounds ?? { x: point[0] - width / 2, y: Math.max(point[1], ...occupied.map(bound => bound.y + bound.height), ...(avoidRoute ? points.map(p => p[1]) : [])) + 16, width, height };
    reserved.push(bounds);
    const closest = [Math.max(bounds.x, Math.min(bounds.x + bounds.width, point[0])), Math.max(bounds.y, Math.min(bounds.y + bounds.height, point[1]))];
    return { bounds, point: [bounds.x + 4, bounds.y + size + 3], ...(Math.hypot(point[0] - closest[0], point[1] - closest[1]) > 18 ? { leader: (0, graph_glyphs_js_1.line)(point, closest, '#94a3b8', .7, '2 2') } : {}) };
}
function roundedRoute(points, radius) {
    if (points.length < 2)
        return '';
    let result = `M${points[0][0]},${points[0][1]}`;
    for (let i = 1; i < points.length - 1; i++) {
        const a = points[i - 1], b = points[i], c = points[i + 1], before = Math.hypot(b[0] - a[0], b[1] - a[1]), after = Math.hypot(c[0] - b[0], c[1] - b[1]), r = Math.min(radius, before / 2, after / 2);
        if (!before || !after) {
            result += `L${b[0]},${b[1]}`;
            continue;
        }
        const x = b[0] - (b[0] - a[0]) / before * r, y = b[1] - (b[1] - a[1]) / before * r, nextX = b[0] + (c[0] - b[0]) / after * r, nextY = b[1] + (c[1] - b[1]) / after * r;
        result += `L${x},${y}Q${b[0]},${b[1]} ${nextX},${nextY}`;
    }
    return result + `L${points.at(-1)[0]},${points.at(-1)[1]}`;
}
function cubicPoints(a, c1, c2, b) {
    return Array.from({ length: 33 }, (_, i) => { const t = i / 32, u = 1 - t; return [u * u * u * a[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * b[0], u * u * u * a[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * b[1]]; });
}
function roundedPoints(points, radius) {
    const samples = [points[0]];
    for (let i = 1; i < points.length - 1; i++) {
        const a = points[i - 1], b = points[i], c = points[i + 1], before = Math.hypot(b[0] - a[0], b[1] - a[1]), after = Math.hypot(c[0] - b[0], c[1] - b[1]), r = Math.min(radius, before / 2, after / 2);
        if (!before || !after)
            continue;
        const start = [b[0] - (b[0] - a[0]) / before * r, b[1] - (b[1] - a[1]) / before * r], end = [b[0] + (c[0] - b[0]) / after * r, b[1] + (c[1] - b[1]) / after * r];
        samples.push(start);
        for (let j = 1; j <= 8; j++) {
            const t = j / 8, u = 1 - t;
            samples.push([u * u * start[0] + 2 * u * t * b[0] + t * t * end[0], u * u * start[1] + 2 * u * t * b[1] + t * t * end[1]]);
        }
    }
    samples.push(points.at(-1));
    return samples;
}
function routeIntersects(points, bounds) {
    return points.slice(1).some((b, i) => {
        const a = points[i], dx = b[0] - a[0], dy = b[1] - a[1];
        let lo = 0, hi = 1;
        for (const [p, q] of [[-dx, a[0] - bounds.x], [dx, bounds.x + bounds.width - a[0]], [-dy, a[1] - bounds.y], [dy, bounds.y + bounds.height - a[1]]]) {
            if (!p) {
                if (q < 0)
                    return false;
            }
            else if (p < 0)
                lo = Math.max(lo, q / p);
            else
                hi = Math.min(hi, q / p);
        }
        return lo <= hi;
    });
}
function crossingRoute(points, prior, mode) {
    const distance = [0];
    for (let i = 1; i < points.length; i++)
        distance.push(distance[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
    const total = distance.at(-1), hits = [];
    for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], b = points[i], dx = b[0] - a[0], dy = b[1] - a[1], length = distance[i] - distance[i - 1];
        if (!length)
            continue;
        for (const route of prior)
            for (let j = 1; j < route.length; j++) {
                const c = route[j - 1], z = route[j], ux = z[0] - c[0], uy = z[1] - c[1], den = dx * uy - dy * ux;
                if (Math.abs(den) < .001)
                    continue;
                const t = ((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) / den, u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den, at = distance[i - 1] + t * length;
                if (t >= 0 && t <= 1 && u >= 0 && u <= 1 && at > 7 && at < total - 7 && !hits.some(v => Math.abs(v - at) < 14)) {
                    const x = a[0] + dx * t, y = a[1] + dy * t, shared = route.slice(1).some((end, k) => { const start = route[k], vx = end[0] - start[0], vy = end[1] - start[1]; return Math.abs(dx * vy - dy * vx) < .001 && Math.abs((x - start[0]) * dy - (y - start[1]) * dx) < .001 && x >= Math.min(start[0], end[0]) - .01 && x <= Math.max(start[0], end[0]) + .01 && y >= Math.min(start[1], end[1]) - .01 && y <= Math.max(start[1], end[1]) + .01; });
                    if (!shared)
                        hits.push(at);
                }
            }
    }
    const at = (length) => {
        let i = 1;
        while (i < distance.length - 1 && distance[i] < length)
            i++;
        const fraction = (length - distance[i - 1]) / Math.max(.001, distance[i] - distance[i - 1]), a = points[i - 1], b = points[i];
        return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction];
    };
    let d = `M${points[0][0]},${points[0][1]}`, cursor = 0;
    const append = (end) => {
        for (let i = 1; i < distance.length; i++)
            if (distance[i] > cursor && distance[i] < end)
                d += `L${points[i][0]},${points[i][1]}`;
        const p = at(end);
        d += `L${p[0]},${p[1]}`;
        cursor = end;
    };
    for (const hit of hits.sort((a, b) => a - b)) {
        const start = at(hit - 6), end = at(hit + 6), mid = at(hit), length = Math.hypot(end[0] - start[0], end[1] - start[1]), px = -(end[1] - start[1]) / length * 9, py = (end[0] - start[0]) / length * 9;
        append(hit - 6);
        if (mode === 'bridge')
            d += `Q${mid[0] + px},${mid[1] + py} ${end[0]},${end[1]}`;
        else if (mode === 'square_bridge')
            d += `L${start[0] + px},${start[1] + py}L${end[0] + px},${end[1] + py}L${end[0]},${end[1]}`;
        else
            d += `M${end[0]},${end[1]}`;
        cursor = hit + 6;
    }
    append(total);
    return d;
}
function cleanRoute(points) {
    const result = [];
    for (const p of points) {
        if (result.length && result.at(-1)[0] === p[0] && result.at(-1)[1] === p[1])
            continue;
        while (result.length > 1) {
            const a = result.at(-2), b = result.at(-1);
            if (Math.abs((b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])) > .001 || (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1]) < 0)
                break;
            result.pop();
        }
        result.push(p);
    }
    return result;
}
function portDirection(edge, at, node, point) {
    const terminal = (0, symbol_presentation_js_1.symbolTerminals)(node).find(t => Math.hypot(t.point[0] - point[0], t.point[1] - point[1]) < .01);
    if (terminal)
        return terminal.direction;
    const side = (0, model_js_1.pathValue)(edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side');
    if (side === 'north')
        return [0, -1];
    if (side === 'south')
        return [0, 1];
    if (side === 'west')
        return [-1, 0];
    if (side === 'east')
        return [1, 0];
    const b = portBounds(node), c = (0, exports.center)(b), dx = (point[0] - c[0]) / Math.max(1, b.width), dy = (point[1] - c[1]) / Math.max(1, b.height);
    return Math.abs(dx) >= Math.abs(dy) ? [dx < 0 ? -1 : 1, 0] : [0, dy < 0 ? -1 : 1];
}
function portRoute(a, b, from, to, source, target, obstacles, clearance, objectClearance, radius, parallel, prior) {
    const escape = (p, n, body) => {
        const face = n[0] ? n[0] > 0 ? body.x + body.width - p[0] : p[0] - body.x : n[1] > 0 ? body.y + body.height - p[1] : p[1] - body.y;
        const reach = Math.max(clearance + radius, face + objectClearance + radius + .01);
        return [p[0] + n[0] * reach, p[1] + n[1] * reach];
    };
    const s = escape(a, source, portBounds(from)), t = escape(b, target, portBounds(to));
    const bodies = [...obstacles, portBounds(from), ...(from === to ? [] : [portBounds(to)])], expanded = bodies.map(r => ({ x: r.x - objectClearance, y: r.y - objectClearance, width: r.width + objectClearance * 2, height: r.height + objectClearance * 2 }));
    const middle = [orthogonalRoute(s, t, expanded)];
    const lane = Math.max(clearance, objectClearance, 12) + radius;
    const xs = [(s[0] + t[0]) / 2, Math.min(s[0], t[0], ...expanded.map(r => r.x)) - lane, Math.max(s[0], t[0], ...expanded.map(r => r.x + r.width)) + lane];
    const ys = [(s[1] + t[1]) / 2, Math.min(s[1], t[1], ...expanded.map(r => r.y)) - lane, Math.max(s[1], t[1], ...expanded.map(r => r.y + r.height)) + lane];
    if (parallel) {
        xs.unshift((s[0] + t[0]) / 2 + 48 * parallel, (s[0] + t[0]) / 2 - 48 * parallel);
        ys.unshift((s[1] + t[1]) / 2 + 48 * parallel, (s[1] + t[1]) / 2 - 48 * parallel);
    }
    for (const x of xs)
        middle.push([s, [x, s[1]], [x, t[1]], t]);
    for (const y of ys)
        middle.push([s, [s[0], y], [t[0], y], t]);
    const scored = middle.map(points => {
        const hits = (bounds) => bounds.reduce((sum, r) => sum + (routeIntersects(points, { x: r.x + .001, y: r.y + .001, width: Math.max(0, r.width - .002), height: Math.max(0, r.height - .002) }) ? 1 : 0), 0);
        const collisions = hits(bodies), marginHits = hits(expanded);
        const path = cleanRoute([a, ...points, b]);
        const length = path.slice(1).reduce((sum, p, i) => sum + Math.hypot(p[0] - path[i][0], p[1] - path[i][1]), 0);
        const mid = cleanRoute(points), first = mid[1] ?? t, last = mid.at(-2) ?? s;
        const backwards = Number((first[0] - s[0]) * source[0] + (first[1] - s[1]) * source[1] < -.001) + Number((last[0] - t[0]) * target[0] + (last[1] - t[1]) * target[1] < -.001);
        let shared = 0;
        if (parallel)
            for (let i = 1; i < mid.length; i++)
                for (const old of prior)
                    for (let j = 1; j < old.length; j++) {
                        const p = mid[i - 1], q = mid[i], u = old[j - 1], v = old[j];
                        if (Math.abs(p[1] - q[1]) < .001 && Math.abs(u[1] - v[1]) < .001 && Math.abs(p[1] - u[1]) < .001)
                            shared += Math.max(0, Math.min(Math.max(p[0], q[0]), Math.max(u[0], v[0])) - Math.max(Math.min(p[0], q[0]), Math.min(u[0], v[0])));
                        if (Math.abs(p[0] - q[0]) < .001 && Math.abs(u[0] - v[0]) < .001 && Math.abs(p[0] - u[0]) < .001)
                            shared += Math.max(0, Math.min(Math.max(p[1], q[1]), Math.max(u[1], v[1])) - Math.max(Math.min(p[1], q[1]), Math.min(u[1], v[1])));
                    }
        return { path, collisions, backwards, marginHits, shared, length };
    });
    scored.sort((x, y) => x.collisions - y.collisions || x.backwards - y.backwards || x.marginHits - y.marginHits || x.shared - y.shared || x.length - y.length);
    return scored[0].path;
}
function decorateEdge(edge, nodes, all, profile, frame, labelObstacles, reservedLabels, priorRoutes, crossings, viewProperties, attachments) {
    const from = endEntry(edge, 0, nodes, all), to = endEntry(edge, 1, nodes, all);
    if (!from || !to)
        return edge;
    const a = [...(attachments?.source ?? endpoint(edge, 0, from, to, all, profile !== 'mindmap.basic@1'))], b = [...(attachments?.target ?? endpoint(edge, 1, to, from, all, profile !== 'mindmap.basic@1'))], role = (0, model_js_1.str)(edge.definition.record.role), record = edge.definition.record;
    if ((0, model_js_1.refKey)(from.definition.ref) === (0, model_js_1.refKey)(to.definition.ref)) {
        if (!(0, model_js_1.pathValue)(edge.appearance?.record, 'route.source_side')) {
            const p = sidePoint(from, 'east', .35, profile !== 'mindmap.basic@1');
            a[0] = p[0];
            a[1] = p[1];
        }
        if (!(0, model_js_1.pathValue)(edge.appearance?.record, 'route.target_side')) {
            const p = sidePoint(to, 'east', .65, profile !== 'mindmap.basic@1');
            b[0] = p[0];
            b[1] = p[1];
        }
    }
    const marks = (0, model_js_1.array)(edge.appearance?.record.marks ?? edge.effective.marks ?? record.marks).map(String), render = (0, core_js_1.roleDescriptor)(role, 'relation')?.render ?? {}, stroke = (0, model_js_1.str)(styled(edge, 'stroke.color', marks.includes('forbidden') ? '#b91c1c' : marks.includes('tentative') ? '#64748b' : render.colour), '#475569'), qualifiers = (0, model_js_1.object)(record.qualifiers);
    const dashed = /dependency|realization|include|extend|import|access|merge|manifest|deploy|application|sysml\.(allocate|derive|satisfy|verify|refine|trace|copy|master)|req\.|messageflow|petri\.testarc|bpmn\.association/.test(role) || (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_message')).sort === 'reply' || (0, graph_glyphs_js_1.metadata)(record, 'x_return') === true;
    const route = (0, model_js_1.array)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.via')).map(model_js_1.object).map(p => [frame.x + (0, model_js_1.num)(p.x), frame.y + (0, model_js_1.num)(p.y)]);
    const same = (0, model_js_1.refKey)(from.definition.ref) === (0, model_js_1.refKey)(to.definition.ref) || a[0] === b[0] && a[1] === b[1], routing = (0, model_js_1.str)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.routing'), (0, model_js_1.str)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.routing'), 'orthogonal')), points = same ? [a, [a[0] + 50, a[1]], [b[0] + 50, b[1]], b] : route.length ? [a, ...route, b] : routing === 'straight' || routing === 'string' || routing === 'curved' && (0, model_js_1.str)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.curve'), (0, model_js_1.str)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.curve'), 'bezier')) !== 'rounded' ? [a, b] : orthogonalRoute(a, b, nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes((0, model_js_1.str)(node.definition.record.role))).map(node => node.item.bounds));
    const equal = (x, y) => Math.hypot(x[0] - y[0], x[1] - y[1]) < .01, parallel = priorRoutes.filter(r => equal(r[0], a) && equal(r.at(-1), b) || equal(r[0], b) && equal(r.at(-1), a)).length;
    if (profile === 'mindmap.basic@1' && parallel && !route.length && !same && (routing === 'orthogonal' || routing === 'curved' && points.length > 2)) {
        const offset = Math.ceil(parallel / 2) * (parallel % 2 ? 1 : -1) * 48;
        if (Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1])) {
            const dx = Math.sign(b[0] - a[0]) * Math.min(24, Math.abs(b[0] - a[0]) / 3);
            points.splice(0, points.length, a, [a[0] + dx, a[1]], [a[0] + dx, a[1] + offset], [b[0] - dx, b[1] + offset], [b[0] - dx, b[1]], b);
        }
        else {
            const dy = Math.sign(b[1] - a[1]) * Math.min(24, Math.abs(b[1] - a[1]) / 3);
            points.splice(0, points.length, a, [a[0], a[1] + dy], [a[0] + offset, a[1] + dy], [b[0] + offset, b[1] - dy], [b[0], b[1] - dy], b);
        }
    }
    const curve = (0, model_js_1.str)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.curve'), (0, model_js_1.str)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.curve'), 'bezier')), tension = (0, model_js_1.num)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.curve_tension'), (0, model_js_1.num)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.curve_tension'), .5)), radius = (0, model_js_1.num)((0, model_js_1.pathValue)(edge.appearance?.record, 'route.curve_radius'), (0, model_js_1.num)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.curve_radius'), 32));
    let cornerRadius = radius;
    const endpointRouting = profile !== 'mindmap.basic@1' && !route.length && (same || routing === 'orthogonal' || routing === 'curved' && curve === 'rounded');
    if (endpointRouting) {
        const clearance = Math.max(0, (0, model_js_1.num)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.port_clearance'), 28)), objectClearance = Math.max(0, (0, model_js_1.num)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'layout.object_clearance'), 16));
        const source = attachments?.sourceDirection ?? portDirection(edge, 0, from, a), target = attachments?.targetDirection ?? portDirection(edge, 1, to, b);
        if (routing === 'curved')
            for (const [point, normal, owner] of [[a, source, from], [b, target, to]])
                for (const node of nodes) {
                    if (node === owner || ['uml.subject', 'network.rack'].includes((0, model_js_1.str)(node.definition.record.role)))
                        continue;
                    const box = portBounds(node), transverse = normal[0] ? point[1] >= box.y && point[1] <= box.y + box.height : point[0] >= box.x && point[0] <= box.x + box.width;
                    const distance = normal[0] ? normal[0] > 0 ? box.x - point[0] : point[0] - box.x - box.width : normal[1] > 0 ? box.y - point[1] : point[1] - box.y - box.height;
                    if (transverse && distance >= 0)
                        cornerRadius = Math.min(cornerRadius, Math.max(0, (distance - clearance) / 2));
                }
        const routed = portRoute(a, b, from, to, source, target, nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes((0, model_js_1.str)(node.definition.record.role))).map(portBounds), clearance, objectClearance, routing === 'curved' ? cornerRadius : 0, parallel, priorRoutes);
        points.splice(0, points.length, ...routed);
    }
    const cleaned = cleanRoute(points), obstacles = nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes((0, model_js_1.str)(node.definition.record.role))).map(node => ({ ...node.item.bounds, x: node.item.bounds.x - 8, y: node.item.bounds.y - 8, width: node.item.bounds.width + 16, height: node.item.bounds.height + 16 }));
    const curved = routing === 'curved' || routing === 'string', direct = curved && !same && !route.length && points.length === 2, horizontal = attachments?.horizontal ?? Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
    const length = Math.max(1, Math.hypot(b[0] - a[0], b[1] - a[1])), normal = [-(b[1] - a[1]) / length, (b[0] - a[0]) / length], bow = routing === 'string' ? Math.min(80, length * .16) * (normal[1] < 0 ? -1 : 1) : 0, offset = bow + (parallel ? Math.ceil(parallel / 2) * (parallel % 2 ? 1 : -1) * 64 : 0);
    const c1 = routing === 'string' ? [a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3] : horizontal ? [a[0] + (b[0] - a[0]) * tension, a[1]] : [a[0], a[1] + (b[1] - a[1]) * tension];
    const c2 = routing === 'string' ? [a[0] + (b[0] - a[0]) * 2 / 3, a[1] + (b[1] - a[1]) * 2 / 3] : horizontal ? [b[0] - (b[0] - a[0]) * tension, b[1]] : [b[0], b[1] - (b[1] - a[1]) * tension];
    c1[0] += normal[0] * offset;
    c1[1] += normal[1] * offset;
    c2[0] += normal[0] * offset;
    c2[1] += normal[1] * offset;
    const sourceDirection = attachments?.sourceDirection, targetDirection = attachments?.targetDirection, reach = Math.max(24, Math.hypot(b[0] - a[0], b[1] - a[1]) * tension);
    if (sourceDirection) {
        c1[0] = a[0] + sourceDirection[0] * reach;
        c1[1] = a[1] + sourceDirection[1] * reach;
    }
    if (targetDirection) {
        c2[0] = b[0] + targetDirection[0] * reach;
        c2[1] = b[1] + targetDirection[1] * reach;
    }
    let labelPoints = direct ? cubicPoints(a, c1, c2, b) : curved ? roundedPoints(cleaned, cornerRadius) : cleaned;
    let d = direct ? `M${a[0]},${a[1]}C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${b[0]},${b[1]}` : curved ? roundedRoute(cleaned, cornerRadius) : crossingRoute(cleaned, priorRoutes, crossings);
    let tangentStart = direct ? c1 : points[1], tangentEnd = direct ? c2 : points.at(-2);
    if (direct && obstacles.some(bounds => routeIntersects(labelPoints, bounds))) {
        const bypass = orthogonalRoute(a, b, obstacles);
        labelPoints = roundedPoints(bypass, Math.min(radius, 18));
        d = roundedRoute(bypass, Math.min(radius, 18));
        tangentStart = bypass[1];
        tangentEnd = bypass.at(-2);
    }
    if (curved && crossings !== 'none') {
        const crossing = crossingRoute(labelPoints, priorRoutes, crossings), continuous = crossingRoute(labelPoints, [], crossings);
        if (crossing !== continuous)
            d = crossing;
    }
    priorRoutes.push(labelPoints);
    const dash = styled(edge, 'stroke.dash', marks.includes('forbidden') || marks.includes('tentative') ? '6 4' : render.pattern ?? (dashed ? '6 4' : '')), dashPattern = Array.isArray(dash) ? dash.join(' ') : dash === 'dotted' ? '2 3' : dash === 'dashed' ? '6 4' : typeof dash === 'string' && dash !== 'solid' ? dash : undefined;
    const routePrimitive = (0, graph_glyphs_js_1.path)(d, 'none', stroke, (0, model_js_1.num)(styled(edge, 'stroke.weight', styled(edge, 'stroke.width', render.width)), 1.5), dashPattern), handdrawn = (0, model_js_1.str)(styled(edge, 'style.look', (0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'style.look'))) === 'handdrawn';
    const ps = [handdrawn ? (0, graph_glyphs_js_1.sketchPrimitive)(routePrimitive, (0, model_js_1.num)((0, model_js_1.pathValue)(edge.effective, 'style.seed'), 42), (0, model_js_1.num)((0, model_js_1.pathValue)(edge.effective, 'style.roughness'), 1)) : routePrimitive];
    if (marks.includes('forbidden')) {
        const middle = Math.floor((labelPoints.length - 1) / 2), start = labelPoints[middle], finish = labelPoints[middle + 1] ?? start, mx = (start[0] + finish[0]) / 2, my = (start[1] + finish[1]) / 2, angle = Math.atan2(finish[1] - start[1], finish[0] - start[0]), nx = -Math.sin(angle), ny = Math.cos(angle), tx = Math.cos(angle), ty = Math.sin(angle);
        for (const offset of [-5, 0, 5])
            ps.push((0, graph_glyphs_js_1.line)([mx + tx * offset - nx * 9, my + ty * offset - ny * 9], [mx + tx * offset + nx * 9, my + ty * offset + ny * 9], stroke, 2));
    }
    const end = points.at(-1), prev = tangentEnd;
    const sourceEndpoint = (0, model_js_1.object)(qualifiers.source), targetEndpoint = (0, model_js_1.object)(qualifiers.target);
    let sourceMark = (0, model_js_1.str)(sourceEndpoint.mark, (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'properties.source_mark'))), targetMark = (0, model_js_1.str)(targetEndpoint.mark, (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'properties.target_mark')));
    if (!sourceMark && typeof sourceEndpoint.navigable === 'boolean')
        sourceMark = sourceEndpoint.navigable ? 'open' : 'none';
    if (!targetMark && typeof targetEndpoint.navigable === 'boolean')
        targetMark = targetEndpoint.navigable ? 'open' : 'none';
    if (!sourceMark)
        sourceMark = (0, model_js_1.str)(styled(edge, 'stroke.source_mark', render.start === 'diamond' ? 'filled-diamond' : render.start === 'hollow_diamond' ? 'diamond' : render.start === 'filled_triangle' ? 'filled-triangle' : render.start));
    if (!targetMark)
        targetMark = (0, model_js_1.str)(styled(edge, 'stroke.target_mark', render.end === 'diamond' ? 'filled-diamond' : render.end === 'hollow_diamond' ? 'diamond' : render.end === 'filled_triangle' ? 'filled-triangle' : render.end));
    if (!targetMark)
        targetMark = role === 'uml.generalization' || role === 'uml.realization' ? 'triangle' : role === 'uml.extension' ? 'filled' : role === 'petri.inhibitor' ? 'circle' : /assoc|uml\.link|commpath|family\.partner|network\.attaches|fbd\.wire|ladder\.series|bpmn\.conversationlink/.test(role) ? 'none' : 'open';
    if (role === 'sysml.composition' && !sourceMark)
        sourceMark = 'filled-diamond';
    if (profile === 'erd.crowfoot@1') {
        const chen = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_chen'));
        const cardinal = (value) => { const c = (0, model_js_1.object)(value); return c.max === 'many' ? c.min === 0 ? 'zeromany' : 'many' : c.min === 0 ? 'zeroone' : 'one'; };
        sourceMark = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'properties.source_mark'), cardinal(chen.from));
        targetMark = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'properties.target_mark'), cardinal(chen.to));
    }
    ps.push(...(0, graph_glyphs_js_1.arrowMarker)(a, tangentStart, sourceMark, stroke), ...(0, graph_glyphs_js_1.arrowMarker)(end, prev, targetMark, stroke));
    if (role === 'bpmn.messageflow')
        ps.push(...(0, graph_glyphs_js_1.arrowMarker)(a, b, 'circle', stroke));
    if (role === 'vsm.einfo')
        ps.push((0, graph_glyphs_js_1.path)(`M${a[0]},${a[1]}L${(a[0] + b[0]) / 2 - 12},${(a[1] + b[1]) / 2 + 10}L${(a[0] + b[0]) / 2 + 12},${(a[1] + b[1]) / 2 - 10}L${b[0]},${b[1]}`, 'none', stroke));
    const labelBounds = [], textScale = (0, model_js_1.num)((0, model_js_1.pathValue)(edge.effective, 'style.font_size'), 16) / 16;
    const addLabel = (value, at, font = 12, numeric = false) => {
        if (!value)
            return;
        const horizontalGap = Math.abs((at.at(-1)?.[0] ?? 0) - (at[0]?.[0] ?? 0)), available = horizontalGap < 48 ? 180 : Math.max(48, Math.min(180, horizontalGap - 16)), lines = [];
        for (const word of value.split(/\s+/)) {
            const previous = lines.at(-1), candidate = previous ? previous + ' ' + word : word;
            if (previous && graphLabelBounds(candidate, 0, 0, font * textScale).width > available)
                lines.push(word);
            else if (previous)
                lines[lines.length - 1] = candidate;
            else
                lines.push(word);
        }
        const placement = placeGraphLabel(lines.join('\n'), at, labelObstacles, reservedLabels, font * textScale, endpointRouting);
        labelBounds.push(placement.bounds);
        if (placement.leader)
            ps.push(placement.leader);
        const fill = (0, model_js_1.str)((0, model_js_1.pathValue)(viewProperties ?? edge.view.record, 'background.color'), '#fff');
        if (numeric) {
            const cx = placement.bounds.x + placement.bounds.width / 2, cy = placement.bounds.y + placement.bounds.height / 2;
            ps.push((0, graph_glyphs_js_1.oval)({ x: cx - 11, y: cy - 11, width: 22, height: 22 }, fill, '#64748b', .8), (0, graph_glyphs_js_1.label)(value, cx, cy + 4, 11, '#334155', { 'text-anchor': 'middle' }));
        }
        else
            ps.push((0, graph_glyphs_js_1.box)(placement.bounds, fill, 'none', 0), ...lines.map((text, i) => (0, graph_glyphs_js_1.label)(text, placement.point[0], placement.point[1] + i * font * textScale * 1.25, font, '#334155')));
    };
    const wireWithoutLabel = (0, symbol_presentation_js_1.electricalWireWithoutLabel)(edge, from, to);
    edge = { ...edge, wireWithoutLabel };
    const presentation = (0, relation_presentation_js_1.relationPresentation)(edge, viewProperties);
    addLabel((0, relation_presentation_js_1.relationCaption)(edge, edgeLabel(edge, all), viewProperties), labelPoints, 12, presentation.mode === 'numbers');
    const endlabels = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_endlabels'));
    for (const [key, p] of [['source', a], ['target', b]]) {
        const endLabel = (0, model_js_1.object)(endlabels[key]);
        const value = [endLabel.role, endLabel.multiplicity, endLabel.qualifier ? '[' + (0, model_js_1.str)(endLabel.qualifier) + ']' : ''].filter(Boolean).join(' ');
        if (value)
            addLabel(value, [p, p], 11);
    }
    if ((0, graph_glyphs_js_1.metadata)(record, 'x_interrupt') || (0, graph_glyphs_js_1.metadata)(record, 'x_exception'))
        ps.push((0, graph_glyphs_js_1.label)('ϟ', (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 10, 24, stroke));
    if ((0, graph_glyphs_js_1.metadata)(record, 'x_tunnel'))
        ps.push((0, graph_glyphs_js_1.label)('( )', a[0] - 10, a[1] + 5, 13, stroke));
    return (0, exports.changed)({ ...edge, ...(wireWithoutLabel ? { wireWithoutLabel } : {}) }, (0, exports.finiteBounds)([Math.min(...labelPoints.map(p => p[0]), ...labelBounds.map(b => b.x)), Math.min(...labelPoints.map(p => p[1]), ...labelBounds.map(b => b.y))], [Math.max(...labelPoints.map(p => p[0]), ...labelBounds.map(b => b.x + b.width)), Math.max(...labelPoints.map(p => p[1]), ...labelBounds.map(b => b.y + b.height))], 18), ps, `${profile}; ${role}; ${edgeLabel(edge)}${marks.length ? '; ' + marks.join(', ') : ''}`);
}
function boundaryPoint(bounds, toward) { const c = (0, exports.center)(bounds), dx = toward[0] - c[0], dy = toward[1] - c[1], ratio = 1 / Math.max(Math.abs(dx) / (bounds.width / 2), Math.abs(dy) / (bounds.height / 2), 1); return [c[0] + dx * ratio, c[1] + dy * ratio]; }
function layoutNative(nodes, edges, all, view, frame, effective) {
    nodes = nodes.map(node => {
        const reference = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_subdiagram'));
        if (!reference.view || !['link', 'badge', 'collapsed'].includes((0, model_js_1.str)(reference.display, 'collapsed')))
            return node;
        const target = (0, model_js_1.resolveRecord)(all, reference.view, node.definition.file) ?? all.find(r => r.owner === 'view' && r.file === node.definition.file && (r.ref.id === reference.view || r.record.name === reference.view));
        const title = target ? (0, model_js_1.titleOf)(target.record) : (0, model_js_1.str)(reference.view), b = node.item.bounds, footer = { x: b.x, y: b.y + b.height, width: b.width, height: 28 };
        const limit = Math.max(10, Math.floor((b.width - 24) / 6.6)), caption = '↗ ' + (title.length > limit ? title.slice(0, limit - 1) + '…' : title), stroke = (0, model_js_1.str)(styled(node, 'symbol.color', '#42689f'));
        const primitives = [...node.item.primitives, (0, graph_glyphs_js_1.box)(footer, (0, model_js_1.str)(styled(node, 'symbol.fill', '#edf3fb')), stroke, 1), (0, graph_glyphs_js_1.label)(caption, footer.x + 10, footer.y + 19, 12, stroke)];
        return { ...node, item: { ...node.item, bounds: { ...b, height: b.height + 28 }, primitives, hitTargets: node.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, height: hit.bounds.height + 28 } })), accessible: { ...node.item.accessible, description: 'Reference to ' + title } } };
    });
    const mindmapProfile = (0, model_js_1.str)(view.record.profile) === 'mindmap.basic@1';
    const layout = (0, model_js_1.object)(effective?.layout ?? view.record.layout), root = (0, model_js_1.resolveRecord)(all, layout.root, view.file), regions = (0, model_js_1.array)(view.record.regions).map(model_js_1.object);
    const settings = { algorithm: (0, model_js_1.str)(layout.algorithm, (0, model_js_1.str)(view.record.profile) === 'mindmap.basic@1' ? 'mindmap' : 'grid'), gap: (0, model_js_1.num)(layout.gap, 64), row_gap: (0, model_js_1.num)(layout.row_gap, 64), columns: (0, model_js_1.num)(layout.columns, 3), direction: (0, model_js_1.str)(layout.direction, 'right'), width: frame.width, height: frame.height, mindmapProfile, ...(root ? { root: (0, model_js_1.refKey)(root.ref) } : {}) };
    if (settings.algorithm === 'auto')
        settings.algorithm = (0, model_js_1.str)(view.record.profile) === 'mindmap.basic@1' ? 'mindmap' : edges.length ? 'layered' : 'grid';
    const layoutNodes = mindmapProfile ? [...nodes.filter(node => node.mindmapTopic !== false && (0, mindmap_js_1.isMindmapTopic)(node.definition.record)), ...nodes.filter(node => node.mindmapTopic === false || !(0, mindmap_js_1.isMindmapTopic)(node.definition.record))] : nodes;
    const positions = (0, graph_layouts_js_1.graphLayout)(layoutNodes.map(node => ({ id: node.item.occurrence, bounds: { ...node.item.bounds, x: node.item.bounds.x - frame.x, y: node.item.bounds.y - frame.y }, pinned: typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false, group: (0, model_js_1.str)(regions.find(region => (0, model_js_1.array)(region.members).some(ref => (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, ref, view.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(node.definition.ref)))?.id, (0, model_js_1.str)(layout.group_by === 'role' ? (0, model_js_1.pathValue)(node.definition.record, 'metadata.x_record.layout_group') : undefined, (0, model_js_1.str)((0, model_js_1.pathValue)(node.definition.record, (0, model_js_1.str)(layout.group_by, 'role')), (0, model_js_1.str)(node.definition.record.role)))) })), edges.flatMap(edge => { const a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all), side = (0, model_js_1.pathValue)(edge.appearance?.record, 'route.source_side'); return a && b && (!mindmapProfile || a.mindmapTopic !== false && b.mindmapTopic !== false && (0, mindmap_js_1.isMindmapTopic)(a.definition.record) && (0, mindmap_js_1.isMindmapTopic)(b.definition.record)) ? [{ from: a.item.occurrence, to: b.item.occurrence, ...(mindmapProfile && (side === 'west' || side === 'east') ? { side: side === 'west' ? 'left' : 'right' } : {}) }] : []; }), { ...settings, ...(root ? { root: nodes.find(node => (0, model_js_1.refKey)(node.definition.ref) === (0, model_js_1.refKey)(root.ref))?.item.occurrence ?? '' } : {}) });
    return nodes.map(node => {
        const local = positions.get(node.item.occurrence), bounds = { ...local, x: local.x + frame.x, y: local.y + frame.y }, dx = bounds.x - node.item.bounds.x, dy = bounds.y - node.item.bounds.y, m = node.item.transform;
        const primitives = [...node.item.primitives];
        return { ...node, item: { ...node.item, bounds, ...(node.item.clip ? { clip: { ...node.item.clip, x: node.item.clip.x + dx, y: node.item.clip.y + dy } } : {}), transform: [m[0], m[1], m[2], m[3], m[4] + dx, m[5] + dy], primitives, hitTargets: node.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, x: hit.bounds.x + dx, y: hit.bounds.y + dy } })) } };
    });
}
function graphAdornments(entries, view, all, profile) {
    const nodes = entries.filter(e => e.definition.record.category !== 'relation'), output = [...entries];
    for (const owner of nodes.filter(node => node.definition.record.role === 'uml.package')) {
        const members = nodes.filter(node => { const target = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_pack')).package, node.definition.file); return target && (0, model_js_1.refKey)(target.ref) === (0, model_js_1.refKey)(owner.definition.ref); });
        if (!members.length)
            continue;
        const content = [owner, ...members].map(node => node.item.bounds), x = Math.min(...content.map(b => b.x)) - 22, y = Math.min(...content.map(b => b.y)) - 35, bounds = { x, y, width: Math.max(...content.map(b => b.x + b.width)) - x + 22, height: Math.max(...content.map(b => b.y + b.height)) - y + 22 };
        output.unshift(mark(owner, owner.definition, 'package-members', bounds, [(0, graph_glyphs_js_1.box)(bounds, 'none', '#94a3b8'), (0, graph_glyphs_js_1.label)('package ' + (0, model_js_1.titleOf)(owner.definition.record), x + 8, y + 19, 12)], 'Package frame for explicit x_pack.package ownership'));
    }
    const regionBounds = new Map(), regions = (0, model_js_1.array)(view.record.regions).map(model_js_1.object);
    const selection = (region) => {
        const members = (0, model_js_1.array)(region.members).map(ref => (0, model_js_1.resolveRecord)(all, ref, view.file)).filter((r) => !!r), scope = (0, model_js_1.resolveRecord)(all, region.scope, view.file);
        return nodes.filter(n => members.some(m => (0, model_js_1.refKey)(m.ref) === (0, model_js_1.refKey)(n.definition.ref)) || (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(n.definition.record, 'x_partition')).lane === region.id || scope && (0, model_js_1.refKey)(scope.ref) === (0, model_js_1.refKey)(n.definition.ref));
    };
    const regionBox = (region, trail = new Set()) => {
        const id = (0, model_js_1.str)(region.id), cached = regionBounds.get(id);
        if (cached)
            return cached;
        const next = new Set(trail);
        next.add(id);
        const selected = selection(region).map(n => n.item.bounds), childBoxes = trail.size < 32 ? regions.filter(child => child.parent === id && !next.has((0, model_js_1.str)(child.id))).map(child => regionBox(child, next)) : [];
        const content = [...selected, ...childBoxes], explicit = (0, model_js_1.object)(region.bounds), minX = content.length ? Math.min(...content.map(b => b.x)) : 50, minY = content.length ? Math.min(...content.map(b => b.y)) : 90;
        const fallback = content.length ? { x: minX - 30, y: minY - 40, width: Math.max(...content.map(b => b.x + b.width)) - minX + 60, height: Math.max(...content.map(b => b.y + b.height)) - minY + 70 } : { x: 20, y: 50, width: 350, height: 220 };
        const b = { x: (0, model_js_1.num)(explicit.x, fallback.x), y: (0, model_js_1.num)(explicit.y, fallback.y), width: (0, model_js_1.num)(explicit.width, fallback.width), height: (0, model_js_1.num)(explicit.height, fallback.height) };
        regionBounds.set(id, b);
        return b;
    };
    for (const region of regions) {
        const role = (0, model_js_1.str)(region.role), id = (0, model_js_1.str)(region.id), selected = selection(region), b = regionBox(region), scope = (0, model_js_1.resolveRecord)(all, region.scope, view.file);
        if (scope?.record.role === 'uml.subject' && selected.some(n => (0, model_js_1.refKey)(n.definition.ref) === (0, model_js_1.refKey)(scope.ref)))
            continue;
        const anchor = nodes.find(n => scope && (0, model_js_1.refKey)(n.definition.ref) === (0, model_js_1.refKey)(scope.ref)) ?? nodes[0];
        if (!anchor)
            continue;
        const dashed = /region|interruptible|parallel/.test(role), ps = [(0, graph_glyphs_js_1.box)(b, 'none', '#64748b', 1.2, dashed ? '7 5' : undefined), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(region.name, id), b.x + 9, b.y + 20, 13, '#334155', { 'font-weight': 600 })];
        if (/pool|lane|partition/.test(role))
            ps.push((0, graph_glyphs_js_1.line)([b.x + 25, b.y + 28], [b.x + b.width, b.y + 28], '#94a3b8', 1));
        if (/expansion/.test(role))
            for (let i = 0; i < 3; i++)
                ps.push((0, graph_glyphs_js_1.box)({ x: b.x + 24 + i * 14, y: b.y - 6, width: 12, height: 12 }, '#fff', '#475569'));
        const marked = mark(anchor, scope ?? view, 'region:' + id, b, ps, `Scoped ${role || 'frame'}; ${selected.length} selected members`);
        output.unshift({ ...marked, item: { ...marked.item, layer: 'frames' } });
    }
    for (const edge of entries.filter(e => e.definition.record.category === 'relation')) {
        const m = (0, model_js_1.object)(edge.definition.record.metadata), a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all);
        if (!a || !b)
            continue;
        const mid = [((0, exports.center)(a.item.bounds)[0] + (0, exports.center)(b.item.bounds)[0]) / 2, ((0, exports.center)(a.item.bounds)[1] + (0, exports.center)(b.item.bounds)[1]) / 2];
        const associationClass = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(m.x_association_class).class, edge.definition.file), classNode = associationClass && nodes.find(n => (0, model_js_1.refKey)(n.definition.ref) === (0, model_js_1.refKey)(associationClass.ref));
        if (classNode)
            output.push(mark(edge, edge.definition, 'association-class', (0, exports.finiteBounds)(mid, (0, exports.center)(classNode.item.bounds)), [(0, graph_glyphs_js_1.line)(mid, (0, exports.center)(classNode.item.bounds), '#64748b', 1, '5 4')], 'Association-class connector'));
        const genset = (0, model_js_1.object)(m.x_genset);
        if (genset.name)
            output.push(mark(edge, edge.definition, 'generalization-set', { x: mid[0], y: mid[1] + 12, width: 210, height: 22 }, [(0, graph_glyphs_js_1.label)(`${(0, model_js_1.str)(genset.name)} {${genset.disjoint ? 'disjoint' : 'overlapping'}, ${genset.complete ? 'complete' : 'incomplete'}}`, mid[0], mid[1] + 27, 10)], 'Generalization-set annotation'));
        const extras = (0, model_js_1.array)((0, model_js_1.object)(m.x_nary).ends), participants = [a, b, ...extras.map(end => { const ref = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).element, edge.definition.file); return ref && nodes.find(node => (0, model_js_1.refKey)(node.definition.ref) === (0, model_js_1.refKey)(ref.ref)); }).filter((e) => !!e)];
        if (extras.length && participants.length > 2) {
            const x = participants.reduce((sum, node) => sum + (0, exports.center)(node.item.bounds)[0], 0) / participants.length, y = participants.reduce((sum, node) => sum + (0, exports.center)(node.item.bounds)[1], 0) / participants.length, ps = participants.map(node => (0, graph_glyphs_js_1.line)([x, y], (0, exports.center)(node.item.bounds)));
            ps.push((0, graph_glyphs_js_1.polygon)([[x, y - 14], [x + 14, y], [x, y + 14], [x - 14, y]], '#fff'));
            extras.forEach((end, i) => {
                const p = participants[i + 2];
                if (p)
                    ps.push((0, graph_glyphs_js_1.label)([(0, model_js_1.object)(end).role, (0, model_js_1.object)(end).multiplicity].filter(Boolean).join(' '), (x + (0, exports.center)(p.item.bounds)[0]) / 2, (y + (0, exports.center)(p.item.bounds)[1]) / 2 - 4, 11));
            });
            const idx = output.indexOf(edge);
            if (idx >= 0)
                output[idx] = (0, exports.changed)(edge, { x: x - 20, y: y - 20, width: 40, height: 40 }, ps, `N-ary association, ${participants.length} participant ends`);
        }
        if (m.x_fragment && /communication|c4.dynamic/.test(profile)) {
            const f = (0, model_js_1.object)(m.x_fragment), selected = (0, model_js_1.array)(f.operands).flatMap(v => (0, model_js_1.array)((0, model_js_1.object)(v).messages)).map(ref => (0, model_js_1.resolveRecord)(all, ref, edge.definition.file)).filter((r) => !!r);
            const ys = entries.filter(e => selected.some(r => (0, model_js_1.refKey)(r.ref) === (0, model_js_1.refKey)(e.definition.ref))).map(e => e.item.bounds);
            if (ys.length) {
                const x = Math.min(...ys.map(b => b.x)) - 20, y = Math.min(...ys.map(b => b.y)) - 30, bounds = { x, y, width: Math.max(...ys.map(b => b.x + b.width)) - x + 20, height: Math.max(...ys.map(b => b.y + b.height)) - y + 20 };
                const ps = [(0, graph_glyphs_js_1.box)(bounds, 'none', '#64748b'), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(f.operator), x + 5, y + 18, 12)];
                (0, model_js_1.array)(f.operands).forEach((value, i) => {
                    const operand = (0, model_js_1.object)(value), yy = y + 36 + i * 22;
                    if (operand.guard)
                        ps.push((0, graph_glyphs_js_1.label)('[' + (0, model_js_1.str)(operand.guard) + ']', x + 10, yy, 11));
                });
                output.unshift(mark(edge, edge.definition, 'communication-fragment', bounds, ps, 'Combined fragment around declared communication messages'));
            }
        }
    }
    return output;
}
function inlineInteractions(snapshot, view, input, all, options, diagnostics, unavailable, fallback, supportsFallback) {
    const output = [...input], chain = [...options.ancestors ?? [], (0, model_js_1.refKey)(view.ref)];
    for (const node of input.filter(entry => entry.definition.record.category !== 'relation')) {
        const metadataValue = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_subdiagram'));
        if (!metadataValue.view || !['inline', 'thumbnail'].includes((0, model_js_1.str)(metadataValue.display, (0, model_js_1.str)(view.record.profile) === 'uml.interaction_overview@2' ? 'inline' : 'collapsed')))
            continue;
        const name = (0, model_js_1.str)(metadataValue.view), split = name.lastIndexOf('::'), file = split < 0 ? node.definition.file : name.slice(0, split), id = split < 0 ? name : name.slice(split + 2);
        const target = (0, model_js_1.resolveRecord)(all, metadataValue.view, node.definition.file) ?? all.find(record => record.owner === 'view' && (record.file === file && (record.ref.id === id || record.record.name === id) || record.file === node.definition.file && (record.ref.id === name || record.record.name === name)));
        if (metadataValue.frozen) {
            const snapshotName = (0, model_js_1.str)(metadataValue.snapshot), separator = snapshotName.lastIndexOf('::'), snapshotFile = separator < 0 ? node.definition.file : snapshotName.slice(0, separator), snapshotKey = separator < 0 ? snapshotName : snapshotName.slice(separator + 2);
            const asset = all.find(record => record.owner === 'asset' && record.file === snapshotFile && (record.ref.id === snapshotKey || record.record.name === snapshotKey || record.record.path === snapshotKey));
            if (asset && (0, model_js_1.str)(asset.record.media_type).startsWith('image/')) {
                const b = node.item.bounds, width = Math.max(b.width, metadataValue.display === 'thumbnail' ? 260 : 600), height = Math.max(b.height, metadataValue.display === 'thumbnail' ? 180 : 400);
                output[output.indexOf(node)] = (0, exports.changed)(node, { ...b, width, height }, [(0, graph_glyphs_js_1.box)({ ...b, width, height }, '#fff', '#64748b'), (0, graph_glyphs_js_1.label)('Frozen ' + ((0, model_js_1.str)(metadataValue.snapshot_at) || name), b.x + 10, b.y + 23, 12), { kind: 'image', assetId: (0, model_js_1.refKey)(asset.ref), bounds: { x: b.x + 10, y: b.y + 35, width: width - 20, height: height - 45 } }], 'Declared frozen image artifact; loaded through the host asset pipeline');
                continue;
            }
            diagnostics.push({ code: 'inline-snapshot-unavailable', severity: 'warning', message: 'Frozen inline display requires a supplied, declared image snapshot asset.', target: node.definition.ref });
            unavailable.push('inline-snapshot:' + (0, model_js_1.refKey)(node.definition.ref));
            continue;
        }
        const problem = !target ? 'Referenced view is unavailable.' : chain.includes((0, model_js_1.refKey)(target.ref)) || chain.length > 8 ? 'Recursive inline view expansion exceeds its bounded scope.' : !supportsFallback?.((0, model_js_1.str)(target.record.profile)) && !options.projectInline ? 'Referenced view needs an installed inline projection adapter.' : undefined;
        if (problem) {
            diagnostics.push({ code: 'inline-view-unavailable', severity: 'warning', message: problem, target: node.definition.ref });
            unavailable.push('inline:' + (0, model_js_1.refKey)(node.definition.ref));
            continue;
        }
        const selected = (0, model_js_1.array)((0, model_js_1.pathValue)(target.record, 'selection.include')).map(ref => (0, model_js_1.resolveRecord)(all, ref, target.file)).filter((record) => !!record);
        const appearances = all.filter(record => record.owner === 'appearance' && (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, record.record.parent, record.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(target.ref));
        const candidates = appearances.length ? appearances.map(appearance => ({ definition: (0, model_js_1.resolveRecord)(all, appearance.record.target, appearance.file), appearance })) : selected.map(definition => ({ definition, appearance: undefined }));
        const childEntries = [];
        for (const [index, candidate] of candidates.entries()) {
            if (!candidate.definition)
                continue;
            const position = (0, model_js_1.object)(candidate.appearance?.record.position), size = (0, model_js_1.object)(candidate.appearance?.record.size), bounds = { x: (0, model_js_1.num)(position.x, 30 + index % 3 * 260), y: (0, model_js_1.num)(position.y, 60 + Math.floor(index / 3) * 160), width: (0, model_js_1.num)(size.width, 220), height: (0, model_js_1.num)(size.height, 72) }, occurrence = node.item.occurrence + ':inline-source:' + (candidate.appearance?.ref.id ?? candidate.definition.ref.id);
            childEntries.push({ ...node, definition: candidate.definition, view: target, ...(candidate.appearance ? { appearance: candidate.appearance } : {}), effective: candidate.definition.record, item: { ...node.item, occurrence, target: candidate.definition.ref, view: target.ref, bounds, primitives: [], hitTargets: [{ id: occurrence, target: candidate.definition.ref, bounds }], transform: exports.identity } });
        }
        const nodes = childEntries.filter(entry => entry.definition.record.category !== 'relation');
        for (const relation of all.filter(record => record.owner === 'definition' && record.record.category === 'relation')) {
            if (childEntries.some(entry => (0, model_js_1.refKey)(entry.definition.ref) === (0, model_js_1.refKey)(relation.ref)))
                continue;
            const ends = (0, model_js_1.array)(relation.record.endpoints).map(end => (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).definition, relation.file));
            if (ends.length < 2 || ends.some(end => !end || !nodes.some(node => (0, model_js_1.refKey)(node.definition.ref) === (0, model_js_1.refKey)(end.ref))))
                continue;
            childEntries.push({ ...node, definition: relation, view: target, effective: relation.record, item: { ...node.item, occurrence: node.item.occurrence + ':inline-source:' + relation.ref.id, target: relation.ref, view: target.ref, primitives: [], transform: exports.identity } });
        }
        const nestedBounds = { x: 0, y: 0, width: 900, height: 600 };
        const projected = options.projectInline ? options.projectInline(snapshot, target, nestedBounds, chain) : fallback(snapshot, target, childEntries, { bounds: nestedBounds, ancestors: chain });
        diagnostics.push(...projected.diagnostics);
        unavailable.push(...projected.unavailable);
        const content = projected.entries;
        if (!content.length)
            continue;
        const minX = Math.min(...content.map(e => e.item.bounds.x)), minY = Math.min(...content.map(e => e.item.bounds.y)), maxX = Math.max(...content.map(e => e.item.bounds.x + e.item.bounds.width)), maxY = Math.max(...content.map(e => e.item.bounds.y + e.item.bounds.height));
        const b = node.item.bounds, width = Math.max(b.width, metadataValue.display === 'thumbnail' ? 260 : 600), height = Math.max(b.height, metadataValue.display === 'thumbnail' ? 180 : 400), scale = Math.min((width - 24) / Math.max(1, maxX - minX), (height - 55) / Math.max(1, maxY - minY)), tx = b.x + 12 - minX * scale, ty = b.y + 40 - minY * scale;
        const idx = output.indexOf(node);
        output[idx] = (0, exports.changed)(node, { ...b, width, height }, [(0, graph_glyphs_js_1.box)({ ...b, width, height }, '#fff', '#64748b'), (0, graph_glyphs_js_1.label)('ref ' + (0, model_js_1.titleOf)(target.record), b.x + 10, b.y + 23, 13), (0, graph_glyphs_js_1.label)('↗ inline', b.x + width - 76, b.y + 23, 11), (0, graph_glyphs_js_1.label)((0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_use')).arguments).length ? '(' + (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_use')).arguments).map(String).join(', ') + ')' : '', b.x + 10, b.y + 36, 11)], 'Inline referenced interaction; original source identities retained');
        for (const entry of content) {
            const cb = entry.item.bounds, m = entry.item.transform, bounds = { x: cb.x * scale + tx, y: cb.y * scale + ty, width: cb.width * scale, height: cb.height * scale }, occurrence = node.item.occurrence + ':inline:' + entry.item.occurrence;
            const childClip = entry.item.clip, outerClip = { x: b.x + 12, y: b.y + 40, width: width - 24, height: height - 55 };
            const mappedClip = childClip ? { x: childClip.x * scale + tx, y: childClip.y * scale + ty, width: childClip.width * scale, height: childClip.height * scale } : outerClip;
            const clipX = Math.max(outerClip.x, mappedClip.x), clipY = Math.max(outerClip.y, mappedClip.y), clip = { x: clipX, y: clipY, width: Math.max(0, Math.min(outerClip.x + outerClip.width, mappedClip.x + mappedClip.width) - clipX), height: Math.max(0, Math.min(outerClip.y + outerClip.height, mappedClip.y + mappedClip.height) - clipY) };
            output.push({ ...entry, item: { ...entry.item, occurrence, view: view.ref, bounds, clip, transform: [m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4] * scale + tx, m[5] * scale + ty], hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, id: occurrence + ':' + hit.id, bounds: { x: hit.bounds.x * scale + tx, y: hit.bounds.y * scale + ty, width: hit.bounds.width * scale, height: hit.bounds.height * scale } })) } });
        }
    }
    return output;
}

},
"presentation/src/graph-glyphs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.coreCardCode = exports.metadata = exports.polygon = exports.path = exports.oval = exports.box = exports.label = exports.line = void 0;
exports.rounded = rounded;
exports.coreCardText = coreCardText;
exports.sketchPrimitive = sketchPrimitive;
exports.shadowPrimitive = shadowPrimitive;
exports.nodeGlyph = nodeGlyph;
exports.arrowMarker = arrowMarker;
const card_text_js_1 = require("presentation/src/card-text.js");
const core_js_1 = require("profiles/src/core.js");
const model_js_1 = require("presentation/src/model.js");
const line = (a, b, stroke = '#475569', width = 1.5, dash) => ({ kind: 'path', d: `M${a[0]},${a[1]}L${b[0]},${b[1]}`, paint: { fill: 'none', stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
exports.line = line;
const label = (value, x, y, size = 14, color = '#1e293b', extra = {}) => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: 'sans', style: { 'font-size': size, fill: color, ...extra } }] });
exports.label = label;
const box = (bounds, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
exports.box = box;
const oval = (bounds, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'ellipse', bounds, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
exports.oval = oval;
const path = (d, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'path', d, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
exports.path = path;
const polygon = (points, fill = '#fff', stroke = '#475569', width = 1.5) => (0, exports.path)('M' + points.map(p => `${p[0]},${p[1]}`).join('L') + 'Z', fill, stroke, width);
exports.polygon = polygon;
function rounded(b, fill, stroke, radius = 12, width = 1.5, dash) {
    const { x, y, width: w, height: h } = b, r = Math.min(radius, w / 2, h / 2);
    return (0, exports.path)(`M${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x + r}Q${x},${y + h} ${x},${y + h - r}V${y + r}Q${x},${y} ${x + r},${y}Z`, fill, stroke, width, dash);
}
const metadata = (record, key) => (0, model_js_1.object)(record.metadata)[key];
exports.metadata = metadata;
const centered = (value, b, size = 15, extra = {}) => {
    const limit = Math.max(8, Math.floor((b.width - 24) / (size * .56))), lines = [];
    for (const word of value.split(/\s+/)) {
        const last = lines.at(-1);
        if (last && last.length + word.length + 1 <= limit)
            lines[lines.length - 1] = last + ' ' + word;
        else
            lines.push(word);
    }
    return { kind: 'text', runs: lines.map((text, i) => ({ text, x: b.x + b.width / 2, y: b.y + b.height / 2 + (i - (lines.length - 1) / 2) * size * 1.2 + size / 3, fontKey: 'sans', style: { 'font-size': size, fill: '#1e293b', 'text-anchor': 'middle', 'font-weight': 600, ...extra } })) };
};
const coreCardCode = (role) => ({ application: 'APP', service: 'SRV', object: 'OBJ', record: 'REC', entity: 'ENT', table: 'TBL', term: 'TERM' }[role] ?? (0, model_js_1.str)((0, core_js_1.roleDescriptor)(role)?.render.text_label, role).toUpperCase());
exports.coreCardCode = coreCardCode;
function coreCardText(role, title, width, scale = 1) {
    const layout = (0, card_text_js_1.cardTextLayout)((0, exports.coreCardCode)(role), title, width, (text, size) => text.length * size * .6, 9 * scale, 15 * scale, 10);
    return { ...layout, height: Math.max(40 + layout.typeLines.length * 11 * scale + 8, layout.titleLines.length * 18 * scale + 20) };
}
function sketchPrimitive(primitive, seed = 42, roughness = 1) {
    let state = seed >>> 0;
    const jitter = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return (state / 4294967296 - .5) * Math.max(0, Math.min(4, roughness)) * 2; };
    let source = primitive;
    if (source.kind === 'rect') {
        const b = source.bounds;
        source = { kind: 'path', d: `M${b.x},${b.y}H${b.x + b.width}V${b.y + b.height}H${b.x}Z`, paint: source.paint };
    }
    if (source.kind === 'ellipse') {
        const b = source.bounds, cx = b.x + b.width / 2, cy = b.y + b.height / 2, rx = b.width / 2, ry = b.height / 2, k = .5522847498;
        source = { kind: 'path', d: `M${cx + rx},${cy}C${cx + rx},${cy + ry * k} ${cx + rx * k},${cy + ry} ${cx},${cy + ry}C${cx - rx * k},${cy + ry} ${cx - rx},${cy + ry * k} ${cx - rx},${cy}C${cx - rx},${cy - ry * k} ${cx - rx * k},${cy - ry} ${cx},${cy - ry}C${cx + rx * k},${cy - ry} ${cx + rx},${cy - ry * k} ${cx + rx},${cy}Z`, paint: source.paint };
    }
    if (source.kind !== 'path')
        return source;
    let command = '', index = 0;
    const d = source.d.replace(/[a-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/gi, token => {
        if (/^[a-df-z]$/i.test(token)) {
            command = token.toUpperCase();
            index = 0;
            return token;
        }
        const i = index++, value = Number(token);
        return String(Number((value + (command === 'A' && i % 7 < 5 ? 0 : jitter())).toFixed(3)));
    });
    return { ...source, d, paint: { ...source.paint, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' } };
}
function shadowPrimitive(primitive, dx = 5, dy = 5) {
    if (primitive.kind === 'rect' || primitive.kind === 'ellipse')
        return { ...primitive, bounds: { ...primitive.bounds, x: primitive.bounds.x + dx, y: primitive.bounds.y + dy }, paint: { fill: '#cbd5e1', stroke: 'none' } };
    if (primitive.kind !== 'path' || primitive.paint.fill === 'none')
        return;
    let command = '', index = 0;
    const d = primitive.d.replace(/[a-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/gi, token => {
        if (/^[a-df-z]$/i.test(token)) {
            command = token.toUpperCase();
            index = 0;
            return token;
        }
        const i = index++;
        return String(Number(token) + (command === 'A' ? (i % 7 === 5 ? dx : i % 7 === 6 ? dy : 0) : command === 'H' ? dx : command === 'V' ? dy : i % 2 ? dy : dx));
    });
    return { ...primitive, d, paint: { fill: '#cbd5e1', stroke: 'none' } };
}
function nodeGlyph(role, record, b, options) {
    const { x, y, width: w, height: h } = b, cx = x + w / 2, cy = y + h / 2;
    const fill = options.fill ?? '#fff', stroke = options.stroke ?? '#475569', width = options.width ?? 1.5;
    const ps = [], m = (key) => (0, model_js_1.object)((0, exports.metadata)(record, key)), render = (0, core_js_1.roleDescriptor)(role)?.render, silhouette = (0, model_js_1.str)(render?.silhouette), coreCard = !role.includes('.') && !role.includes('::') && !options.profile.startsWith('chen.');
    const diamond = () => (0, exports.polygon)([[cx, y], [x + w, cy], [cx, y + h], [x, cy]], fill, stroke, width);
    const hexagon = () => (0, exports.polygon)([[x + 20, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x + 20, y + h], [x, cy]], fill, stroke, width);
    const document = () => (0, exports.path)(`M${x},${y}H${x + w}V${y + h - 10}C${x + w * .66},${y + h - 26} ${x + w * .4},${y + h + 10} ${x},${y + h - 8}Z`, fill, stroke, width);
    const cylinder = () => { ps.push((0, exports.path)(`M${x},${y + 12}C${x},${y - 4} ${x + w},${y - 4} ${x + w},${y + 12}V${y + h - 12}C${x + w},${y + h + 4} ${x},${y + h + 4} ${x},${y + h - 12}Z`, fill, stroke, width), (0, exports.oval)({ x, y, width: w, height: 24 }, fill, stroke, width)); };
    let title = true;
    if (role === 'uml.actor' || role === 'vsm.operator' || role === 'c4.person' || silhouette === 'actor') {
        const r = Math.min(16, h / 6), yy = y + r + 5;
        ps.push((0, exports.oval)({ x: cx - r, y: yy - r, width: 2 * r, height: 2 * r }, fill, stroke, width), (0, exports.line)([cx, yy + r], [cx, y + h * .65], stroke), (0, exports.line)([cx - 24, Math.max(yy + r + 5, y + h * .4)], [cx + 24, Math.max(yy + r + 5, y + h * .4)], stroke), (0, exports.line)([cx, y + h * .65], [cx - 24, y + h * .8], stroke), (0, exports.line)([cx, y + h * .65], [cx + 24, y + h * .8], stroke), (0, exports.label)(options.title, cx, y + h - 3, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if ((role === 'flow.start' || role === 'flow.end') && !options.profile.startsWith('bpmn') && !options.profile.startsWith('uml.activity'))
        ps.push(rounded(b, fill, stroke, h / 2));
    else if (/^(state|flow)\.(initial|junction)$/.test(role) || role === 'state.initial') {
        ps.push((0, exports.oval)(b, stroke, stroke));
        title = false;
    }
    else if (role === 'state.final' || role === 'flow.end' && !options.profile.startsWith('bpmn')) {
        ps.push((0, exports.oval)(b, fill, stroke, 2), (0, exports.oval)({ x: x + w * .2, y: y + h * .2, width: w * .6, height: h * .6 }, stroke, stroke));
        title = false;
    }
    else if (role === 'state.terminate' || role === 'flow.flowfinal') {
        if (role === 'flow.flowfinal')
            ps.push((0, exports.oval)(b, fill, stroke));
        ps.push((0, exports.line)([x + 5, y + 5], [x + w - 5, y + h - 5], stroke, 2), (0, exports.line)([x + w - 5, y + 5], [x + 5, y + h - 5], stroke, 2));
        title = false;
    }
    else if (role === 'state.history_deep' || role === 'state.history_shallow') {
        ps.push((0, exports.oval)(b, fill, stroke), centered(role === 'state.history_deep' ? 'H*' : 'H', b));
        title = false;
    }
    else if (role === 'state.entrypoint' || role === 'state.exitpoint') {
        ps.push((0, exports.oval)(b, fill, stroke));
        if (role === 'state.exitpoint')
            ps.push((0, exports.line)([x + 4, y + 4], [x + w - 4, y + h - 4], stroke), (0, exports.line)([x + w - 4, y + 4], [x + 4, y + h - 4], stroke));
        title = false;
    }
    else if (role === 'state.forkjoin' || role === 'flow.forkjoin' || role === 'petri.transition' || role === 'flow.parallelmode') {
        ps.push((0, exports.box)({ x, y: cy - 5, width: w, height: 10 }, stroke, stroke));
        title = false;
    }
    else if (role === 'petri.place') {
        ps.push((0, exports.oval)(b, fill, stroke));
        const count = (0, model_js_1.num)(m('x_petri').tokens);
        if (count <= 6) {
            for (let i = 0; i < count; i++)
                ps.push((0, exports.oval)({ x: cx - 3 + (count === 1 ? 0 : Math.cos(i / count * Math.PI * 2) * 13), y: cy - 3 + (count === 1 ? 0 : Math.sin(i / count * Math.PI * 2) * 13), width: 6, height: 6 }, stroke, stroke));
        }
        else
            ps.push(centered(String(count), b));
        ps.push((0, exports.label)(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'flow.start' || role === 'flow.intermediate' || role === 'flow.end' || role.startsWith('cmmn.') && role.endsWith('event')) {
        const event = m('x_event'), dashed = event.interrupting === false ? '5 3' : undefined;
        ps.push((0, exports.oval)(b, fill, stroke, role === 'flow.end' ? 3 : 1.5, dashed));
        if (role === 'flow.intermediate' || event.position === 'intermediate' || event.position === 'boundary')
            ps.push((0, exports.oval)({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, 1.2, dashed));
        const type = (0, model_js_1.str)(event.type, role === 'cmmn.timerevent' ? 'timer' : role === 'cmmn.userevent' ? 'user' : 'none');
        const ib = { x: cx - w * .23, y: cy - h * .23, width: w * .46, height: h * .46 };
        if (type === 'message')
            ps.push((0, exports.box)(ib, 'none', stroke), (0, exports.path)(`M${ib.x},${ib.y}L${cx},${cy}L${ib.x + ib.width},${ib.y}`, 'none', stroke));
        else if (type === 'timer') {
            ps.push((0, exports.oval)(ib, 'none', stroke), (0, exports.line)([cx, cy], [cx, ib.y + 3], stroke), (0, exports.line)([cx, cy], [ib.x + ib.width - 3, cy], stroke));
            for (let i = 0; i < 12; i++) {
                const a = i * Math.PI / 6;
                ps.push((0, exports.line)([cx + Math.sin(a) * w * .19, cy + Math.cos(a) * h * .19], [cx + Math.sin(a) * w * .22, cy + Math.cos(a) * h * .22], stroke, 1));
            }
        }
        else if (type === 'signal')
            ps.push((0, exports.polygon)([[cx, ib.y], [ib.x + ib.width, ib.y + ib.height], [ib.x, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'terminate')
            ps.push((0, exports.oval)(ib, stroke, stroke));
        else if (type === 'error')
            ps.push((0, exports.polygon)([[ib.x + ib.width * .55, ib.y], [ib.x, ib.y + ib.height * .6], [ib.x + ib.width * .45, ib.y + ib.height * .45], [ib.x + ib.width * .2, ib.y + ib.height], [ib.x + ib.width, ib.y + ib.height * .3], [ib.x + ib.width * .6, ib.y + ib.height * .45]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'escalation')
            ps.push((0, exports.polygon)([[cx, ib.y], [ib.x + ib.width, ib.y + ib.height], [cx, ib.y + ib.height * .6], [ib.x, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'compensation') {
            ps.push((0, exports.polygon)([[ib.x, cy], [cx, ib.y], [cx, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke), (0, exports.polygon)([[cx, cy], [ib.x + ib.width, ib.y], [ib.x + ib.width, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        }
        else if (type === 'conditional') {
            ps.push((0, exports.box)(ib, 'none', stroke));
            for (let i = 1; i < 4; i++)
                ps.push((0, exports.line)([ib.x + 3, ib.y + i * ib.height / 4], [ib.x + ib.width - 3, ib.y + i * ib.height / 4], stroke));
        }
        else if (type === 'link')
            ps.push((0, exports.polygon)([[ib.x, cy - 3], [cx, cy - 3], [cx, ib.y], [ib.x + ib.width, cy], [cx, ib.y + ib.height], [cx, cy + 3], [ib.x, cy + 3]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'cancel')
            ps.push((0, exports.line)([ib.x, ib.y], [ib.x + ib.width, ib.y + ib.height], stroke, 3), (0, exports.line)([ib.x + ib.width, ib.y], [ib.x, ib.y + ib.height], stroke, 3));
        else if (type === 'multiple')
            ps.push((0, exports.polygon)(Array.from({ length: 5 }, (_, i) => [cx + Math.sin(i * Math.PI * .4) * ib.width / 2, cy - Math.cos(i * Math.PI * .4) * ib.height / 2]), role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'parallel_multiple')
            ps.push((0, exports.line)([ib.x, cy], [ib.x + ib.width, cy], stroke, 3), (0, exports.line)([cx, ib.y], [cx, ib.y + ib.height], stroke, 3));
        else if (type === 'user')
            ps.push((0, exports.oval)({ x: cx - 5, y: cy - 9, width: 10, height: 10 }, 'none', stroke), (0, exports.path)(`M${cx - 9},${cy + 10}Q${cx},${cy - 3} ${cx + 9},${cy + 10}`, 'none', stroke));
        ps.push((0, exports.label)(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (['flow.decision', 'flow.merge', 'flow.gateway', 'state.choice', 'cmmn.sentry', 'chen.association'].includes(role)) {
        ps.push(diamond());
        const gateway = m('x_gateway');
        const mark = { exclusive: '×', parallel: '+', inclusive: '○', complex: '*', event: '◎', event_exclusive: '◎' }[(0, model_js_1.str)(gateway.type)];
        if (mark) {
            const radius = Math.min(w, h) * .2, type = (0, model_js_1.str)(gateway.type);
            if (type === 'exclusive')
                ps.push((0, exports.line)([cx - radius, cy - radius], [cx + radius, cy + radius], stroke, 3), (0, exports.line)([cx + radius, cy - radius], [cx - radius, cy + radius], stroke, 3));
            else if (type === 'parallel')
                ps.push((0, exports.line)([cx - radius, cy], [cx + radius, cy], stroke, 3), (0, exports.line)([cx, cy - radius], [cx, cy + radius], stroke, 3));
            else if (type === 'inclusive')
                ps.push((0, exports.oval)({ x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, 'none', stroke, 2.5));
            else if (type === 'complex') {
                for (let i = 0; i < 4; i++)
                    ps.push((0, exports.line)([cx - Math.cos(i * Math.PI / 4) * radius, cy - Math.sin(i * Math.PI / 4) * radius], [cx + Math.cos(i * Math.PI / 4) * radius, cy + Math.sin(i * Math.PI / 4) * radius], stroke, 2));
            }
            else {
                ps.push((0, exports.oval)({ x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, 'none', stroke), (0, exports.oval)({ x: cx - radius + 3, y: cy - radius + 3, width: radius * 2 - 6, height: radius * 2 - 6 }, 'none', stroke), (0, exports.polygon)(Array.from({ length: 5 }, (_, i) => [cx + Math.sin(i * Math.PI * .4) * radius * .55, cy - Math.cos(i * Math.PI * .4) * radius * .55]), 'none', stroke));
            }
            title = false;
            ps.push((0, exports.label)(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        }
    }
    else if (role === 'uml.usecase' || role === 'orm.entitytype' || role === 'orm.valuetype' || role === 'uml.collaboration' || role === 'soaml.servicecontract')
        ps.push((0, exports.oval)(b, fill, stroke, width, ['orm.valuetype', 'uml.collaboration', 'soaml.servicecontract'].includes(role) ? '6 4' : undefined));
    else if (role === 'dfd.process' && options.profile === 'dfd.yourdon@1')
        ps.push((0, exports.oval)(b, fill, stroke, width));
    else if (role === 'dfd.process') {
        ps.push(rounded(b, fill, stroke));
        ps.push((0, exports.line)([x, y + 22], [x + w, y + 22], stroke), (0, exports.line)([x, y + h - 22], [x + w, y + h - 22], stroke));
        const diagram = m('x_diagram');
        ps.push((0, exports.label)(String(diagram.number ?? diagram.id ?? diagram.code ?? ''), x + 8, y + 17, 11, stroke));
        if (diagram.responsibility || diagram.owner)
            ps.push((0, exports.label)((0, model_js_1.str)(diagram.responsibility, (0, model_js_1.str)(diagram.owner)), x + 8, y + h - 7, 11, stroke));
    }
    else if (role === 'dfd.store') {
        ps.push((0, exports.line)([x, y], [x + w, y], stroke), (0, exports.line)([x, y + h], [x + w, y + h], stroke));
        if (options.profile === 'dfd.gane_sarson@1')
            ps.push((0, exports.line)([x, y], [x, y + h], stroke), (0, exports.line)([x + 36, y], [x + 36, y + h], stroke));
        const diagram = m('x_diagram');
        if (diagram.code || diagram.id || diagram.number)
            ps.push((0, exports.label)(String(diagram.code ?? diagram.id ?? diagram.number), x + 6, cy + 4, 11, stroke));
    }
    else if (['flow.document', 'epk.infoobject', 'dmn.knowledgesource'].includes(role) || silhouette === 'document')
        ps.push(document());
    else if (['flow.storage', 'flow.datastore', 'c4.store'].includes(role) || silhouette === 'cylinder')
        cylinder();
    else if (['flow.io', 'sdl.input', 'sdl.output', 'flow.sendsignal', 'flow.acceptsignal', 'flow.manualinput', 'sdl.signal'].includes(role)) {
        const input = role === 'sdl.input' || role === 'flow.acceptsignal';
        ps.push(role === 'flow.manualinput' ? (0, exports.polygon)([[x, y + 16], [x + w, y], [x + w, y + h], [x, y + h]], fill, stroke) : input ? (0, exports.polygon)([[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x + 20, cy]], fill, stroke) : role === 'sdl.output' || role === 'flow.sendsignal' || role === 'sdl.signal' ? (0, exports.polygon)([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h]], fill, stroke) : (0, exports.polygon)([[x + 20, y], [x + w, y], [x + w - 20, y + h], [x, y + h]], fill, stroke));
    }
    else if (role === 'flow.subprocess' || role === 'sdl.procedure') {
        ps.push(rounded(b, fill, stroke), (0, exports.line)([x + 12, y], [x + 12, y + h], stroke), (0, exports.line)([x + w - 12, y], [x + w - 12, y + h], stroke));
    }
    else if (role === 'sdl.save')
        ps.push((0, exports.polygon)([[x + 20, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x + 20, y + h], [x, cy]], fill, stroke));
    else if (role === 'sdl.create')
        ps.push((0, exports.polygon)([[x + 15, y], [x + w - 15, y], [x + w, y + 15], [x + w, y + h - 15], [x + w - 15, y + h], [x + 15, y + h], [x, y + h - 15], [x, y + 15]], fill, stroke));
    else if (role === 'sdl.set' || role === 'sdl.reset' || role === 'sdl.timer') {
        ps.push((0, exports.box)(b, fill, stroke));
        ps.push((0, exports.oval)({ x: x + 8, y: y + 8, width: 22, height: 22 }, 'none', stroke), (0, exports.line)([x + 19, y + 19], [x + 19, y + 10], stroke), (0, exports.line)([x + 19, y + 19], [x + 26, y + 19], stroke));
        if (role === 'sdl.reset')
            ps.push((0, exports.line)([x + 9, y + 9], [x + 29, y + 29], stroke));
    }
    else if (['flow.conversation', 'flow.callconversation', 'flow.subconversation', 'epk.event', 'flow.preparation'].includes(role)) {
        ps.push(hexagon());
        if (role === 'flow.callconversation')
            ps.push((0, exports.polygon)([[x + 24, y + 4], [x + w - 24, y + 4], [x + w - 5, cy], [x + w - 24, y + h - 4], [x + 24, y + h - 4], [x + 5, cy]], 'none', stroke));
    }
    else if (role === 'epk.connector') {
        ps.push((0, exports.oval)(b, fill, stroke), centered((0, model_js_1.str)(m('x_epc').type, (0, model_js_1.str)(m('x_epc').operator, 'and')).toUpperCase(), b));
        title = false;
    }
    else if (role === 'flow.connector' || role === 'family.union') {
        ps.push((0, exports.oval)(b, fill, stroke));
    }
    else if (role === 'flow.offpage')
        ps.push((0, exports.polygon)([[x, y], [x + w, y], [x + w, y + h * .65], [cx, y + h], [x, y + h * .65]], fill, stroke));
    else if (role === 'flow.manualop')
        ps.push((0, exports.polygon)([[x, y], [x + w, y], [x + w - 20, y + h], [x + 20, y + h]], fill, stroke));
    else if (role === 'flow.delay')
        ps.push((0, exports.path)(`M${x},${y}H${x + w / 2}C${x + w * 1.16},${y} ${x + w * 1.16},${y + h} ${x + w / 2},${y + h}H${x}Z`, fill, stroke));
    else if (role === 'flow.display')
        ps.push((0, exports.path)(`M${x + 20},${y}H${x + w - 20}Q${x + w + 20},${cy} ${x + w - 20},${y + h}H${x + 20}L${x},${cy}Z`, fill, stroke));
    else if (role === 'flow.card' || role === 'dmn.bkm')
        ps.push((0, exports.polygon)([[x + 18, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y + 18]], fill, stroke));
    else if (role === 'flow.sort') {
        ps.push(diamond(), (0, exports.line)([x, cy], [x + w, cy], stroke));
    }
    else if (role === 'flow.collate' || role === 'flow.timeevent') {
        ps.push((0, exports.polygon)([[x, y], [x + w, y], [x, y + h], [x + w, y + h]], fill, stroke));
    }
    else if (role === 'flow.isoextract' || role === 'flow.isomerge')
        ps.push(role === 'flow.isoextract' ? (0, exports.polygon)([[cx, y], [x + w, y + h], [x, y + h]], fill, stroke) : (0, exports.polygon)([[x, y], [x + w, y], [cx, y + h]], fill, stroke));
    else if (role === 'flow.loopstart' || role === 'flow.loopend')
        ps.push(role === 'flow.loopstart' ? (0, exports.polygon)([[x + 16, y], [x + w - 16, y], [x + w, y + 16], [x + w, y + h], [x, y + h], [x, y + 16]], fill, stroke) : (0, exports.polygon)([[x, y], [x + w, y], [x + w, y + h - 16], [x + w - 16, y + h], [x + 16, y + h], [x, y + h - 16]], fill, stroke));
    else if (role === 'uml.package') {
        ps.push((0, exports.box)({ x, y: y + 14, width: w, height: h - 14 }, fill, stroke), (0, exports.box)({ x, y, width: Math.min(90, w * .4), height: 14 }, fill, stroke));
    }
    else if (['uml.node', 'uml.device', 'uml.executionenv'].includes(role)) {
        ps.push((0, exports.box)({ x, y: y + 12, width: w - 12, height: h - 12 }, fill, stroke), (0, exports.polygon)([[x, y + 12], [x + 12, y], [x + w, y], [x + w - 12, y + 12]], fill, stroke), (0, exports.polygon)([[x + w - 12, y + 12], [x + w, y], [x + w, y + h - 12], [x + w - 12, y + h]], fill, stroke));
    }
    else if (['uml.artifact', 'flow.dataobject', 'flow.datainput', 'flow.dataoutput', 'cmmn.casefile'].includes(role)) {
        ps.push((0, exports.polygon)([[x, y], [x + w - 16, y], [x + w, y + 16], [x + w, y + h], [x, y + h]], fill, stroke), (0, exports.path)(`M${x + w - 16},${y}V${y + 16}H${x + w}`, 'none', stroke));
        if (role === 'flow.datainput' || role === 'flow.dataoutput')
            ps.push((0, exports.label)(role === 'flow.datainput' ? '⇢' : '➜', x + 8, y + 22, 18, stroke));
    }
    else if (role === 'ladder.contact') {
        ps.push((0, exports.line)([x, cy], [cx - 12, cy], stroke), (0, exports.line)([cx - 12, y + 5], [cx - 12, y + h - 5], stroke, 2), (0, exports.line)([cx + 12, y + 5], [cx + 12, y + h - 5], stroke, 2), (0, exports.line)([cx + 12, cy], [x + w, cy], stroke));
        if (m('x_contact').form === 'nc')
            ps.push((0, exports.line)([cx - 18, y + h - 4], [cx + 18, y + 4], stroke));
        ps.push((0, exports.label)(options.title, cx, y - 5, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'ladder.coil') {
        ps.push((0, exports.line)([x, cy], [cx - 15, cy], stroke), (0, exports.path)(`M${cx - 6},${y + 5}Q${cx - 28},${cy} ${cx - 6},${y + h - 5}M${cx + 6},${y + 5}Q${cx + 28},${cy} ${cx + 6},${y + h - 5}`, 'none', stroke), (0, exports.line)([cx + 15, cy], [x + w, cy], stroke));
        const form = (0, model_js_1.str)(m('x_coil').mode);
        if (form === 'set' || form === 'reset')
            ps.push(centered(form === 'set' ? 'S' : 'R', b));
        if (form === 'negated')
            ps.push((0, exports.line)([cx - 18, y + h], [cx + 18, y], stroke));
        ps.push((0, exports.label)(options.title, cx, y - 5, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'network.bus') {
        ps.push((0, exports.line)([x, cy], [x + w, cy], stroke, 6));
        ps.push((0, exports.label)(options.title, cx, cy - 12, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'network.rack' && options.profile === 'network.rack@1') {
        ps.push((0, exports.box)(b, '#f8fafc', stroke, 2));
        const units = Math.min(100, (0, model_js_1.num)(m('x_rack').units, 42));
        for (let i = 1; i <= units; i++)
            ps.push((0, exports.line)([x + 25, y + h - i * (h - 30) / units], [x + w - 10, y + h - i * (h - 30) / units], '#cbd5e1', .5), (0, exports.label)(String(i), x + 4, y + h - (i - .5) * (h - 30) / units, 9, stroke));
        ps.push((0, exports.label)(options.title, x + 10, y + 20, 14, stroke));
        title = false;
    }
    else if (role === 'tree.event')
        ps.push((0, exports.oval)(b, fill, stroke, width));
    else if (role === 'tree.gate') {
        const type = (0, model_js_1.str)(m('x_gate').type, 'and');
        ps.push(type === 'and' ? (0, exports.path)(`M${x},${y + h}V${y + h * .45}C${x},${y - h * .15} ${x + w},${y - h * .15} ${x + w},${y + h * .45}V${y + h}Z`, fill, stroke) : (0, exports.path)(`M${x},${y + h}Q${cx},${y + h * .65} ${x + w},${y + h}Q${x + w},${y + h * .25} ${cx},${y}Q${x},${y + h * .25} ${x},${y + h}Z`, fill, stroke));
        ps.push((0, exports.label)(type.toUpperCase(), cx, cy + 6, 12, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'vsm.inventory') {
        ps.push((0, exports.polygon)([[cx, y], [x + w, y + h], [x, y + h]], fill, stroke));
    }
    else if (role === 'vsm.kaizen') {
        const points = [];
        for (let i = 0; i < 24; i++) {
            const a = i * Math.PI / 12, r = i % 2 ? .65 : 1;
            points.push([cx + Math.cos(a) * w / 2 * r, cy + Math.sin(a) * h / 2 * r]);
        }
        ps.push((0, exports.polygon)(points, fill, stroke));
    }
    else if (role === 'vsm.supermarket') {
        ps.push((0, exports.path)(`M${x},${y}V${y + h}H${x + w}V${y}M${x},${cy}H${x + w}`, 'none', stroke));
    }
    else if (role === 'orm.facttype') {
        const count = Math.max(2, (0, model_js_1.array)(record.members).length || (0, model_js_1.array)(m('x_role').roles).length);
        ps.push((0, exports.box)(b, fill, stroke, width));
        const cellWidth = Math.min(80, (w - 24) / count), left = x + 12, top = y + h - 30;
        for (let i = 0; i < count; i++)
            ps.push((0, exports.box)({ x: left + i * cellWidth, y: top, width: cellWidth, height: 24 }, fill, stroke));
        if (m('x_role').unique)
            ps.push((0, exports.line)([left, top - 4], [left + cellWidth * count, top - 4], stroke, 2));
    }
    else if (role === 'ui.checkbox') {
        ps.push((0, exports.box)({ x, y: cy - 10, width: 20, height: 20 }, '#fff', '#64748b'));
        if (m('x_ui').checked)
            ps.push((0, exports.path)(`M${x + 3},${cy}L${x + 8},${cy + 6}L${x + 17},${cy - 6}`, 'none', '#334155', 2));
        ps.push((0, exports.label)(options.title, x + 28, cy + 5));
        title = false;
    }
    else if (role === 'uml.subject') {
        ps.push((0, exports.box)(b, 'none', stroke), (0, exports.label)(options.title, x + 8, y + 20, 14, stroke));
        title = false;
    }
    else if (role === 'ui.label') {
        ps.push((0, exports.label)(options.title, x + 4, cy + 5));
        title = false;
    }
    else if (role === 'ui.image') {
        ps.push((0, exports.box)(b, '#f1f5f9', '#64748b'), (0, exports.line)([x, y], [x + w, y + h], '#94a3b8'), (0, exports.line)([x + w, y], [x, y + h], '#94a3b8'));
    }
    else if (role === 'flow.annotation') {
        ps.push((0, exports.path)(`M${x + 16},${y}H${x}V${y + h}H${x + 16}`, 'none', stroke));
    }
    else if (role === 'flow.group')
        ps.push(rounded(b, 'none', stroke, 8, 1.5, '8 3 2 3'));
    else if (role.startsWith('cmmn.')) {
        const mC = m('x_cmmn');
        ps.push(rounded(b, fill, stroke, role === 'cmmn.milestone' ? h / 2 : 4, width, mC.discretionary ? '6 4' : undefined));
    }
    else if (role === 'dmn.inputdata' || role === 'flow.process' || role === 'state.state' || role === 'epk.function' || role === 'ui.button')
        ps.push(rounded(b, fill, stroke, role === 'dmn.inputdata' ? h / 2 : 10, m('x_activity').call ? 3 : width, m('x_activity').event_subprocess ? '5 3' : undefined));
    else if (silhouette === 'round')
        ps.push(rounded(b, fill, stroke, 12, width));
    else if (silhouette === 'ellipse' || silhouette === 'circle')
        ps.push((0, exports.oval)(b, fill, stroke, width));
    else if (silhouette === 'diamond')
        ps.push(diamond());
    else if (silhouette === 'tag')
        ps.push((0, exports.polygon)([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h]], fill, stroke, width));
    else if (silhouette === 'arrow')
        ps.push((0, exports.polygon)([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h], [x + 20, cy]], fill, stroke, width));
    else if (coreCard && render?.shape === 'card')
        ps.push(rounded(b, fill, stroke, 5, width));
    else
        ps.push((0, exports.box)(b, fill, stroke, width));
    if (role === 'uml.component' || silhouette === 'component')
        ps.push((0, exports.box)({ x: x - 6, y: y + 12, width: 16, height: 12 }, fill, stroke), (0, exports.box)({ x: x - 6, y: y + 34, width: 16, height: 12 }, fill, stroke));
    if (role === 'dmn.decisionservice')
        ps.push((0, exports.line)([x, y + 25], [x + w, y + 25], stroke));
    if (m('x_io').set)
        for (let i = -1; i <= 1; i++)
            ps.push((0, exports.line)([cx + i * 5, y + h - 15], [cx + i * 5, y + h - 5], stroke, 2));
    if (role === 'cmmn.humantask' || role === 'cmmn.processtask' || role === 'cmmn.decisiontask')
        ps.push((0, exports.label)(role === 'cmmn.humantask' ? '♙' : role === 'cmmn.processtask' ? '⊞' : '▤', x + 7, y + 20, 15, stroke));
    if (role === 'cmmn.sentry' && m('x_sentry').on === 'exit')
        ps.push((0, exports.polygon)([[cx, y + 6], [x + w - 6, cy], [cx, y + h - 6], [x + 6, cy]], stroke, stroke));
    if (role === 'idef0.activity')
        ps.push((0, exports.label)((0, model_js_1.str)(m('x_idef0').node), x + w - 8, y + h - 7, 11, stroke, { 'text-anchor': 'end' }));
    if (role === 'epk.processlink')
        ps.push((0, exports.polygon)([[x + 4, y + 4], [x + 24, y + 4], [x + 34, y + 14], [x + 24, y + 24], [x + 4, y + 24], [x - 6, y + 14]], fill, stroke));
    if (role === 'ui.list')
        for (let i = 0; i < 3; i++)
            ps.push((0, exports.line)([x + 12, y + 10 + i * 20], [x + w - 12, y + 10 + i * 20], '#cbd5e1', 1));
    if (role === 'network.server' || role === 'network.switch')
        for (let i = 0; i < 3; i++)
            ps.push((0, exports.line)([x + 10, y + h - 12 - i * 8], [x + 44, y + h - 12 - i * 8], stroke), (0, exports.oval)({ x: x + w - 16, y: y + h - 16 - i * 8, width: 4, height: 4 }, '#16a34a', '#16a34a'));
    if (!title && /^(state\.|flow\.(forkjoin|parallelmode|flowfinal)|petri\.transition|tree\.gate|epk\.connector)/.test(role) && options.title)
        ps.push((0, exports.label)(options.title, cx, y + h + 18, 13, stroke, { 'text-anchor': 'middle' }));
    if (coreCard) {
        const ib = { x: x + 10, y: y + 10, width: 19, height: 19 }, layout = coreCardText(role, options.title, w, options.textScale);
        const scale = options.textScale ?? 1;
        if (render?.shape === 'frame')
            ps.push((0, exports.box)({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, .7, '3 3'));
        ps.push((0, exports.box)(ib, 'none', stroke, 1.2));
        if (role === 'application')
            ps.push((0, exports.line)([ib.x, ib.y + 5], [ib.x + 19, ib.y + 5], stroke, 1), (0, exports.path)(`M${ib.x + 3},${ib.y + 9}L${ib.x + 7},${ib.y + 12}L${ib.x + 3},${ib.y + 15}M${ib.x + 10},${ib.y + 15}H${ib.x + 16}`, 'none', stroke, 1));
        else if (['service', 'server'].includes(role))
            for (let i = 0; i < 3; i++)
                ps.push((0, exports.line)([ib.x, ib.y + 5 + i * 6], [ib.x + 19, ib.y + 5 + i * 6], stroke, .8));
        else if (['table', 'record', 'entity'].includes(role))
            ps.push((0, exports.line)([ib.x, ib.y + 6], [ib.x + 19, ib.y + 6], stroke, 1), (0, exports.line)([ib.x + 6, ib.y], [ib.x + 6, ib.y + 19], stroke, 1));
        for (const [i, code] of layout.typeLines.entries())
            ps.push((0, exports.label)(code, x + 10, y + 38 + 9 * scale + i * 11 * scale, 9, stroke, { 'font-weight': 600 }));
    }
    if (title && coreCard) {
        const scale = options.textScale ?? 1, layout = coreCardText(role, options.title, w, scale);
        for (const [i, value] of layout.titleLines.entries())
            ps.push((0, exports.label)(value, x + layout.titleOffset + layout.titleWidth / 2, y + h / 2 + (i - (layout.titleLines.length - 1) / 2) * 18 * scale + 5 * scale, 15, '#1e293b', { 'text-anchor': 'middle', 'font-weight': 600 }));
    }
    else if (title)
        ps.push(centered(options.title, role === 'dfd.store' ? { ...b, x: x + 40, width: w - 44 } : b, 15, options.profile.startsWith('uml.object') ? { 'text-decoration': 'underline' } : {}));
    const activity = m('x_activity');
    if (activity.transaction)
        ps.push(rounded({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, 8));
    const marks = [...(0, model_js_1.array)(activity.markers).map(v => ({ loop: '↻', parallel: '|||', sequential: '≡', compensation: '≪' }[(0, model_js_1.str)(v)] ?? (0, model_js_1.str)(v))), ...(activity.adhoc ? ['~'] : []), ...(activity.collapsed || role === 'flow.subconversation' ? ['⊞'] : [])];
    const cmmn = m('x_cmmn');
    for (const [key, mark] of Object.entries({ required: '!', repetition: '#', manual_activation: '▷', completion: '■', collapsed: '+' }))
        if (cmmn[key])
            marks.push(mark);
    if (marks.length)
        ps.push((0, exports.label)(marks.join(' '), cx, y + h - 5, 13, stroke, { 'text-anchor': 'middle' }));
    if (role === 'flow.choreotask') {
        const bands = (0, model_js_1.array)((0, exports.metadata)(record, 'x_bands')).map(String);
        bands.forEach((band, i) => { const yy = i === 0 ? y : y + h - (bands.length - i) * 18; ps.push((0, exports.box)({ x, y: yy, width: w, height: 18 }, i === 0 ? '#e2e8f0' : '#fff', stroke), (0, exports.label)(band, cx, yy + 13, 11, stroke, { 'text-anchor': 'middle' })); });
    }
    if (role === 'fbd.block' || role === 'ladder.timer') {
        const type = (0, model_js_1.str)(m('x_fbd').type, (0, model_js_1.str)(m('x_timer').type, (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'content.type'), (0, model_js_1.str)(m('x_record').block_type))));
        if (type)
            ps.push((0, exports.label)(type, x + 8, y + 18, 11, stroke));
    }
    const sdl = m('x_sdl'), sdlMarks = [sdl.priority ? 'priority ' + (0, model_js_1.str)(sdl.priority) : '', sdl.spontaneous ? 'spontaneous' : '', sdl.continuous ? 'continuous ' + (0, model_js_1.str)(sdl.continuous) : '', sdl.duration ? 'after ' + (0, model_js_1.str)(sdl.duration) : ''].filter(Boolean);
    if (sdlMarks.length)
        ps.push((0, exports.label)(sdlMarks.join('; '), cx, y + h + 16, 10, stroke, { 'text-anchor': 'middle' }));
    const planning = (0, model_js_1.array)(m('x_planning').items);
    if (planning.length) {
        ps.push((0, exports.box)({ x: cx - 18, y: y - 12, width: 36, height: 20 }, '#fff', stroke), (0, exports.line)([cx - 18, y - 2], [cx + 18, y - 2], stroke), (0, exports.line)([cx, y - 12], [cx, y + 8], stroke));
        ps.push((0, exports.label)('Planning: ' + planning.map(String).join(', '), x + 8, y + h + 16, 10, stroke));
    }
    if (options.look === 'handdrawn' && ps[0])
        ps[0] = sketchPrimitive(ps[0], options.seed, options.roughness);
    return ps;
}
function arrowMarker(point, toward, kind = 'open', stroke = '#475569') {
    if (kind === 'none' || !kind)
        return [];
    const [x, y] = point, theta = Math.atan2(y - toward[1], x - toward[0]), ux = Math.cos(theta), uy = Math.sin(theta), px = -uy, py = ux;
    const at = (back, side) => [x - ux * back + px * side, y - uy * back + py * side];
    if (['one', 'zeroone', 'many', 'zeromany'].includes(kind)) {
        const ps = [];
        if (kind.includes('many'))
            ps.push((0, exports.line)(at(15, 0), at(0, 8), stroke), (0, exports.line)(at(15, 0), at(0, -8), stroke), (0, exports.line)(at(15, 0), point, stroke));
        else
            ps.push((0, exports.line)(at(7, -8), at(7, 8), stroke));
        if (kind === 'one')
            ps.push((0, exports.line)(at(13, -8), at(13, 8), stroke));
        if (kind === 'many')
            ps.push((0, exports.line)(at(24, -8), at(24, 8), stroke));
        if (kind.startsWith('zero')) {
            const p = at(24, 0);
            ps.push((0, exports.oval)({ x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, '#fff', stroke));
        }
        return ps;
    }
    if (kind === 'port')
        return [(0, exports.polygon)([at(0, -5), at(0, 5), at(10, 5), at(10, -5)], '#fff', stroke)];
    if (kind === 'junction')
        return [(0, exports.oval)({ x: x - 4, y: y - 4, width: 8, height: 8 }, stroke, stroke)];
    if (kind === 'range')
        return [(0, exports.line)(at(4, -7), at(4, 7), stroke), (0, exports.line)(at(16, -7), at(16, 7), stroke), (0, exports.line)(at(4, 0), at(16, 0), stroke)];
    if (kind === 'lollipop')
        return [(0, exports.oval)({ x: x - 8, y: y - 8, width: 16, height: 16 }, '#fff', stroke)];
    if (kind === 'socket')
        return [(0, exports.path)(`M${at(0, -10).join(',')}Q${at(18, 0).join(',')} ${at(0, 10).join(',')}`, 'none', stroke)];
    if (kind === 'xcircle')
        return [(0, exports.oval)({ x: x - 8, y: y - 8, width: 16, height: 16 }, '#fff', stroke), (0, exports.line)([x - 5, y - 5], [x + 5, y + 5], stroke), (0, exports.line)([x - 5, y + 5], [x + 5, y - 5], stroke)];
    if (kind === 'circle' || kind === 'filled-circle') {
        const p = at(5, 0);
        return [(0, exports.oval)({ x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, kind === 'circle' ? '#fff' : stroke, stroke)];
    }
    if (kind === 'diamond' || kind === 'filled-diamond')
        return [(0, exports.polygon)([point, at(10, 6), at(20, 0), at(10, -6)], kind === 'diamond' ? '#fff' : stroke, stroke)];
    if (kind === 'triangle' || kind === 'filled' || kind === 'filled-triangle')
        return [(0, exports.polygon)([point, at(13, 7), at(13, -7)], kind === 'triangle' ? '#fff' : stroke, stroke)];
    return [(0, exports.line)(at(12, 6), point, stroke), (0, exports.line)(point, at(12, -6), stroke)];
}

},
"presentation/src/graph-layouts.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.graphLayout = graphLayout;
function graphLayout(nodes, links, settings = {}) {
    const positions = new Map();
    if (!nodes.length)
        return positions;
    const n = nodes.length, index = new Map(nodes.map((node, i) => [node.id, i]));
    const outgoing = nodes.map(() => []), incoming = nodes.map(() => []);
    for (const link of links) {
        const a = index.get(link.from), b = index.get(link.to);
        if (a !== undefined && b !== undefined && a !== b && !outgoing[a].includes(b)) {
            outgoing[a].push(b);
            incoming[b].push(a);
        }
    }
    const gap = Math.max(8, settings.gap ?? 64), rowGap = Math.max(8, settings.row_gap ?? 64), width = Math.max(...nodes.map(node => node.bounds.width)), height = Math.max(...nodes.map(node => node.bounds.height));
    const stepX = width + gap, stepY = height + rowGap, algorithm = settings.algorithm ?? 'grid', columns = Math.max(1, Math.floor(settings.columns ?? 3));
    const direction = settings.direction ?? (algorithm === 'tree' ? 'down' : 'right');
    let intrinsic = false, preserveWorld = false;
    const xy = nodes.map((_, i) => ({ x: (i % columns) * stepX, y: Math.floor(i / columns) * stepY }));
    const roots = nodes.map((_, i) => i).filter(i => !incoming[i].length), declared = settings.root === undefined ? undefined : index.get(settings.root);
    if (declared !== undefined) {
        const at = roots.indexOf(declared);
        if (at >= 0)
            roots.splice(at, 1);
        roots.unshift(declared);
    }
    if (!roots.length)
        roots.push(0);
    const parents = new Map(), depths = new Map(), components = new Map();
    let component = 0;
    for (const root of [...roots, ...nodes.map((_, i) => i)]) {
        if (depths.has(root))
            continue;
        depths.set(root, 0);
        components.set(root, component++);
        const queue = [root];
        for (let i = 0; i < queue.length; i++)
            for (const child of outgoing[queue[i]])
                if (!depths.has(child)) {
                    parents.set(child, queue[i]);
                    depths.set(child, depths.get(queue[i]) + 1);
                    components.set(child, components.get(root));
                    queue.push(child);
                }
    }
    if (algorithm === 'fit_grid') {
        intrinsic = true;
        const adjacent = nodes.map((_, i) => [...new Set([...outgoing[i], ...incoming[i]])]), pins = nodes.map((_, i) => i).filter(i => nodes[i].pinned), degree = (i) => adjacent[i].length;
        const seed = pins.length ? pins : [declared ?? nodes.map((_, i) => i).sort((a, b) => degree(b) - degree(a) || nodes[a].id.localeCompare(nodes[b].id))[0]], distance = new Map(), queue = [...seed];
        seed.forEach(i => distance.set(i, 0));
        for (let at = 0; at < queue.length; at++)
            for (const i of adjacent[queue[at]])
                if (!distance.has(i)) {
                    distance.set(i, distance.get(queue[at]) + 1);
                    queue.push(i);
                }
        const order = nodes.map((_, i) => i).filter(i => !nodes[i].pinned).sort((a, b) => (distance.get(a) ?? n) - (distance.get(b) ?? n) || degree(b) - degree(a) || nodes[a].id.localeCompare(nodes[b].id));
        const anchor = pins.length ? { x: (Math.min(...pins.map(i => nodes[i].bounds.x)) + Math.max(...pins.map(i => nodes[i].bounds.x + nodes[i].bounds.width))) / 2, y: (Math.min(...pins.map(i => nodes[i].bounds.y)) + Math.max(...pins.map(i => nodes[i].bounds.y + nodes[i].bounds.height))) / 2 } : { x: 0, y: 0 }, placed = new Set(pins);
        pins.forEach(i => xy[i] = { x: nodes[i].bounds.x, y: nodes[i].bounds.y });
        preserveWorld = !!pins.length;
        let sumX = 0, sumY = 0, count = 0;
        for (const i of order) {
            let best;
            const bounds = nodes[i].bounds;
            for (let ring = 0; ring <= n && !best; ring++)
                for (let col = -ring; col <= ring; col++)
                    for (let row = -ring; row <= ring; row++)
                        if (Math.max(Math.abs(col), Math.abs(row)) === ring) {
                            const cx = anchor.x + col * stepX, cy = anchor.y + row * stepY, x = cx - bounds.width / 2, y = cy - bounds.height / 2;
                            if ([...placed].some(j => x < nodes[j].bounds.width + xy[j].x + gap / 2 && x + bounds.width > xy[j].x - gap / 2 && y < nodes[j].bounds.height + xy[j].y + rowGap / 2 && y + bounds.height > xy[j].y - rowGap / 2))
                                continue;
                            const peers = adjacent[i].filter(j => placed.has(j)), links = peers.reduce((v, j) => v + Math.hypot(cx - xy[j].x - nodes[j].bounds.width / 2, cy - xy[j].y - nodes[j].bounds.height / 2), 0) / Math.max(1, peers.length), cost = Math.hypot(cx - anchor.x, cy - anchor.y) + .7 * Math.hypot(sumX + cx - anchor.x, sumY + cy - anchor.y) / (count + 1) + .12 * links;
                            if (!best || cost < best.cost - .001)
                                best = { x, y, cost };
                        }
            xy[i] = { x: best?.x ?? anchor.x + (n + 1) * stepX, y: best?.y ?? anchor.y + count * stepY };
            placed.add(i);
            sumX += xy[i].x + bounds.width / 2 - anchor.x;
            sumY += xy[i].y + bounds.height / 2 - anchor.y;
            count++;
        }
    }
    else if (algorithm === 'ladder') {
        xy.forEach((p, i) => { p.x = 0; p.y = i * stepY; });
    }
    else if (algorithm === 'layered') {
        intrinsic = true;
        const seen = new Set(), finished = [];
        for (let root = 0; root < n; root++)
            if (!seen.has(root)) {
                seen.add(root);
                const stack = [[root, 0]];
                while (stack.length) {
                    const top = stack.at(-1), i = top[0], next = top[1];
                    if (next >= outgoing[i].length) {
                        stack.pop();
                        finished.push(i);
                        continue;
                    }
                    top[1]++;
                    const child = outgoing[i][next];
                    if (!seen.has(child)) {
                        seen.add(child);
                        stack.push([child, 0]);
                    }
                }
            }
        const componentOf = new Map(), groups = [];
        for (const root of finished.reverse())
            if (!componentOf.has(root)) {
                const id = groups.length, members = [], stack = [root];
                componentOf.set(root, id);
                while (stack.length) {
                    const i = stack.pop();
                    members.push(i);
                    for (const parent of incoming[i])
                        if (!componentOf.has(parent)) {
                            componentOf.set(parent, id);
                            stack.push(parent);
                        }
                }
                groups.push(members.sort((a, b) => a - b));
            }
        const forward = groups.map(() => new Set()), backward = groups.map(() => new Set());
        for (let i = 0; i < n; i++)
            for (const child of outgoing[i]) {
                const a = componentOf.get(i), b = componentOf.get(child);
                if (a !== b) {
                    forward[a].add(b);
                    backward[b].add(a);
                }
            }
        const pending = backward.map(peers => peers.size), levels = groups.map(() => 0), queue = groups.map((_, i) => i).filter(i => !pending[i]).sort((a, b) => groups[a][0] - groups[b][0]);
        for (let at = 0; at < queue.length; at++) {
            const i = queue[at];
            for (const child of forward[i]) {
                levels[child] = Math.max(levels[child], levels[i] + 1);
                pending[child]--;
                if (!pending[child])
                    queue.push(child);
            }
        }
        const ranks = Array.from({ length: Math.max(...levels) + 1 }, () => []);
        groups.forEach((_, i) => ranks[levels[i]].push(i));
        ranks.forEach((rank, level) => rank.sort((a, b) => (level === 0 ? forward[a].size - forward[b].size : 0) || groups[a][0] - groups[b][0]));
        const order = new Map();
        const refresh = () => ranks.forEach(rank => rank.forEach((id, i) => order.set(id, i)));
        refresh();
        for (let sweep = 0; sweep < 4; sweep++)
            for (const descending of [false, true]) {
                const visit = descending ? [...ranks].reverse() : ranks;
                for (const rank of visit) {
                    const neighbours = descending ? forward : backward, score = (id) => { const peers = [...neighbours[id]]; return peers.length ? peers.reduce((sum, k) => sum + (order.get(k) ?? 0), 0) / peers.length : order.get(id) ?? 0; };
                    rank.sort((a, b) => score(a) - score(b) || (order.get(a) ?? 0) - (order.get(b) ?? 0));
                    refresh();
                }
            }
        const vertical = ['down', 'up'].includes(direction), spacing = vertical ? gap : rowGap, dimension = (i) => vertical ? nodes[i].bounds.width : nodes[i].bounds.height;
        const members = ranks.map(rank => rank.flatMap(id => groups[id])), spans = members.map(rank => rank.reduce((sum, i) => sum + dimension(i), 0) + Math.max(0, rank.length - 1) * spacing), maxSpan = Math.max(...spans);
        members.forEach((rank, level) => {
            let cursor = (maxSpan - spans[level]) / 2;
            for (const i of rank) {
                xy[i] = vertical ? { x: cursor, y: level * stepY + (height - nodes[i].bounds.height) / 2 } : { x: level * stepX + (width - nodes[i].bounds.width) / 2, y: cursor };
                cursor += dimension(i) + spacing;
            }
        });
    }
    else if (['tree', 'spanning_tree', 'mindmap', 'radial'].includes(algorithm)) {
        const children = nodes.map(() => []);
        for (const [child, parent] of parents)
            children[parent].push(child);
        const breadth = new Map();
        let leaf = 0;
        for (const root of nodes.map((_, i) => i).filter(i => !parents.has(i))) {
            const stack = [[root, false]];
            while (stack.length) {
                const [i, done] = stack.pop();
                const kids = children[i];
                if (!done && kids.length) {
                    stack.push([i, true]);
                    for (const child of [...kids].reverse())
                        stack.push([child, false]);
                }
                else
                    breadth.set(i, kids.length ? (breadth.get(kids[0]) + breadth.get(kids.at(-1))) / 2 : leaf++);
            }
        }
        xy.forEach((p, i) => { p.x = (depths.get(i) ?? 0) * stepX; p.y = (breadth.get(i) ?? 0) * stepY; });
        if (algorithm === 'mindmap') {
            intrinsic = true;
            const root = roots[0], branches = children[root], spans = new Map();
            for (const i of nodes.map((_, i) => i).sort((a, b) => (depths.get(b) ?? 0) - (depths.get(a) ?? 0))) {
                const kids = children[i], childrenHeight = kids.reduce((sum, k) => sum + spans.get(k), 0) + Math.max(0, kids.length - 1) * rowGap;
                spans.set(i, Math.max(nodes[i].bounds.height, childrenHeight));
            }
            xy[root] = { x: (width - nodes[root].bounds.width) / 2, y: -nodes[root].bounds.height / 2 };
            const place = (branch, top, side) => {
                const stack = [[branch, top]];
                while (stack.length) {
                    const [i, start] = stack.pop(), span = spans.get(i), kids = children[i];
                    xy[i] = { x: (depths.get(i) ?? 0) * stepX * side + (width - nodes[i].bounds.width) / 2, y: start + (span - nodes[i].bounds.height) / 2 };
                    const childrenHeight = kids.reduce((sum, k) => sum + spans.get(k), 0) + Math.max(0, kids.length - 1) * rowGap;
                    let cursor = start + (span - childrenHeight) / 2;
                    for (const child of kids) {
                        stack.push([child, cursor]);
                        cursor += spans.get(child) + rowGap;
                    }
                }
            };
            const branchSides = new Map(branches.map((branch, i) => { const explicit = settings.mindmapProfile ? links.find(link => link.from === nodes[root].id && link.to === nodes[branch].id)?.side : undefined; return [branch, explicit === 'left' ? -1 : explicit === 'right' ? 1 : (i % 2 ? -1 : 1) * (settings.mindmapProfile && direction === 'left' ? -1 : 1)]; }));
            for (const side of [1, -1]) {
                const peers = branches.filter(branch => branchSides.get(branch) === side), total = peers.reduce((sum, i) => sum + spans.get(i), 0) + Math.max(0, peers.length - 1) * rowGap;
                let top = -total / 2;
                for (const branch of peers) {
                    place(branch, top, side);
                    top += spans.get(branch) + rowGap;
                }
            }
            let bottom = Math.max(...xy.map((p, i) => p.y + nodes[i].bounds.height)) + rowGap;
            for (const other of nodes.map((_, i) => i).filter(i => !parents.has(i) && i !== root)) {
                place(other, bottom, 1);
                bottom += spans.get(other) + rowGap;
            }
        }
        if (algorithm === 'radial') {
            const perDepth = new Map();
            nodes.forEach((_, i) => { const d = depths.get(i) ?? 0; const peers = perDepth.get(d) ?? []; peers.push(i); perDepth.set(d, peers); });
            for (const [depth, peers] of perDepth)
                peers.forEach((i, j) => { const radius = depth === 0 ? 0 : Math.max(depth * stepX, peers.length * stepX / (2 * Math.PI)), angle = j / peers.length * 2 * Math.PI - Math.PI / 2; xy[i] = { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }; });
        }
    }
    else if (algorithm === 'circular') {
        const radius = Math.max(stepX, n * stepX / (2 * Math.PI));
        xy.forEach((p, i) => { const angle = i / n * 2 * Math.PI - Math.PI / 2; p.x = radius * Math.cos(angle); p.y = radius * Math.sin(angle); });
    }
    else if (algorithm === 'grouped') {
        const groups = new Map();
        nodes.forEach((node, i) => { const key = node.group ?? 'ungrouped', peers = groups.get(key) ?? []; peers.push(i); groups.set(key, peers); });
        let offset = 0;
        for (const peers of groups.values()) {
            const count = Math.min(columns, peers.length);
            peers.forEach((i, j) => { xy[i] = { x: offset + j % count * stepX, y: Math.floor(j / count) * stepY }; });
            offset += count * stepX + gap;
        }
    }
    else if (algorithm === 'organic') {
        const radius = Math.max(stepX, n * stepX / (2 * Math.PI));
        xy.forEach((p, i) => { const angle = i / n * 2 * Math.PI; p.x = radius * Math.cos(angle); p.y = radius * Math.sin(angle); });
        const span = Math.min(128, n - 1);
        for (let iteration = 0; iteration < 48; iteration++) {
            const force = nodes.map(() => ({ x: 0, y: 0 }));
            for (let i = 0; i < n; i++)
                for (let offset = 1; offset <= span; offset++) {
                    const j = (i + offset) % n, dx = xy[i].x - xy[j].x, dy = xy[i].y - xy[j].y, length = Math.max(1, Math.hypot(dx, dy)), repel = stepX * stepY / (length * length);
                    force[i].x += dx / length * repel;
                    force[i].y += dy / length * repel;
                }
            for (const link of links) {
                const a = index.get(link.from), b = index.get(link.to);
                if (a === undefined || b === undefined)
                    continue;
                const dx = xy[b].x - xy[a].x, dy = xy[b].y - xy[a].y, length = Math.max(1, Math.hypot(dx, dy)), pull = (length - stepX) * .018;
                force[a].x += dx / length * pull;
                force[a].y += dy / length * pull;
                force[b].x -= dx / length * pull;
                force[b].y -= dy / length * pull;
            }
            xy.forEach((p, i) => {
                if (!nodes[i].pinned) {
                    p.x += Math.max(-stepX / 10, Math.min(stepX / 10, force[i].x));
                    p.y += Math.max(-stepY / 10, Math.min(stepY / 10, force[i].y));
                }
            });
        }
    }
    if (['tree', 'spanning_tree'].includes(algorithm) && ['down', 'up'].includes(direction))
        xy.forEach(p => { const x = p.x; p.x = p.y / stepY * stepX; p.y = x / stepX * stepY; });
    if (!intrinsic && ['layered', 'tree', 'spanning_tree', 'mindmap', 'radial', 'circular'].includes(algorithm))
        xy.forEach((p, i) => { p.x += (width - nodes[i].bounds.width) / 2; p.y += (height - nodes[i].bounds.height) / 2; });
    if (direction === 'left' && algorithm !== 'fit_grid' && !(algorithm === 'mindmap' && settings.mindmapProfile))
        xy.forEach((p, i) => p.x = -p.x - nodes[i].bounds.width);
    if (direction === 'up' && algorithm !== 'fit_grid' && !(algorithm === 'mindmap' && settings.mindmapProfile))
        xy.forEach((p, i) => p.y = -p.y - nodes[i].bounds.height);
    const minX = Math.min(...xy.map(p => p.x)), minY = Math.min(...xy.map(p => p.y));
    nodes.forEach((node, i) => positions.set(node.id, node.pinned ? node.bounds : { ...node.bounds, x: xy[i].x - (preserveWorld ? 0 : minX - 32), y: xy[i].y - (preserveWorld ? 0 : minY - 64) }));
    if (nodes.some(node => node.pinned) && algorithm !== 'fit_grid') {
        const occupied = nodes.filter(node => node.pinned).map(node => node.bounds), padding = Math.min(gap, rowGap) / 2, vertical = ['down', 'up'].includes(direction);
        const overlaps = (a, b) => a.x < b.x + b.width + padding && a.x + a.width > b.x - padding && a.y < b.y + b.height + padding && a.y + a.height > b.y - padding;
        for (const node of nodes.filter(node => !node.pinned)) {
            const initial = positions.get(node.id);
            let chosen = initial;
            for (let attempt = 0; attempt <= n * 2 && occupied.some(bounds => overlaps(chosen, bounds)); attempt++) {
                const offset = (Math.floor(attempt / 2) + 1) * (attempt % 2 ? -1 : 1);
                chosen = { ...initial, x: initial.x + (vertical ? offset * stepX : 0), y: initial.y + (vertical ? 0 : offset * stepY) };
            }
            positions.set(node.id, chosen);
            occupied.push(chosen);
        }
    }
    return positions;
}

},
"presentation/src/graph-native.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.projectNativeGraph = projectNativeGraph;
const model_js_1 = require("presentation/src/model.js");
const graph_common_js_1 = require("presentation/src/graph-common.js");
const mindmap_js_1 = require("presentation/src/mindmap.js");
const relation_presentation_js_1 = require("presentation/src/relation-presentation.js");
function projectNativeGraph(snapshot, view, entries, options = {}, fallback, supportsFallback) {
    const profile = (0, model_js_1.str)(view.record.profile), diagnostics = [], unavailable = [], frame = options.bounds ?? { x: 0, y: 0, width: 960, height: 680 }, all = (0, model_js_1.records)(snapshot);
    entries = (0, relation_presentation_js_1.prepareRelationPresentation)(entries, all, options.viewProperties ?? view.record);
    const pending = (0, graph_common_js_1.provisionalNodes)(entries, all);
    if (pending.length) {
        const waiting = new Set(pending);
        const result = projectNativeGraph(snapshot, view, entries.filter(entry => !waiting.has(entry)), options, fallback, supportsFallback);
        return { ...result, entries: [...result.entries, ...(0, graph_common_js_1.resolvedText)(pending, profile)] };
    }
    const originalNodes = entries.filter(e => e.definition.record.category !== 'relation'), originalEdges = entries.filter(e => e.definition.record.category === 'relation');
    const nodes = (0, graph_common_js_1.layoutNative)(originalNodes, originalEdges, all, view, frame, options.viewProperties);
    const reservedLabels = [], labelObstacles = [{ x: frame.x, y: frame.y, width: frame.width, height: 45 }, ...nodes.flatMap(node => node.definition.record.role === 'uml.subject' ? [] : [node.item.bounds])];
    const priorRoutes = [];
    const projectedEdges = profile === 'mindmap.basic@1' ? (0, mindmap_js_1.mindmapEdges)(originalEdges, nodes, all, frame, options.viewProperties ?? view.record, diagnostics, unavailable) : originalEdges.map(edge => (0, graph_common_js_1.decorateEdge)(edge, nodes, all, profile, frame, labelObstacles, reservedLabels, priorRoutes, (0, model_js_1.str)((0, model_js_1.pathValue)(options.viewProperties ?? view.record, 'layout.crossings'), 'gap'), options.viewProperties));
    const output = [...projectedEdges, ...nodes];
    return { entries: (0, graph_common_js_1.inlineInteractions)(snapshot, view, (0, graph_common_js_1.resolvedText)((0, graph_common_js_1.graphAdornments)(output, view, all, profile), profile), all, options, diagnostics, unavailable, fallback, supportsFallback), diagnostics, unavailable };
}

},
"presentation/src/markdown.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.safeURL = safeURL;
exports.inlineMarkdown = inlineMarkdown;
exports.markdownBlocks = markdownBlocks;
function safeURL(value) {
    try {
        const url = new URL(value);
        return ['https:', 'http:', 'mailto:'].includes(url.protocol) ? url.href : undefined;
    }
    catch {
        return undefined;
    }
}
function inlineMarkdown(text, depth = 0) {
    if (depth > 8)
        return [{ text }];
    const runs = [];
    let start = 0;
    const matcher = /(\*\*|__|\+\+|\*|_|`)(.+?)\1|\[([^\]]+)\]\(([^)]+)\)/g;
    let match;
    while ((match = matcher.exec(text))) {
        if (match.index > start)
            runs.push({ text: text.slice(start, match.index) });
        if (match[3] !== undefined) {
            const href = safeURL(match[4] ?? '');
            runs.push(href ? { text: match[3], href } : { text: match[3] });
        }
        else {
            const marker = match[1];
            const children = marker === '`' ? [{ text: match[2] ?? '' }] : inlineMarkdown(match[2] ?? '', depth + 1);
            for (const run of children)
                runs.push({ ...run, ...(marker === '**' || marker === '__' ? { bold: true } : marker === '++' ? { underline: true } : marker === '`' ? { code: true } : { italic: true }) });
        }
        start = matcher.lastIndex;
    }
    if (start < text.length || !runs.length)
        runs.push({ text: text.slice(start) });
    return runs;
}
function markdownBlocks(text, formatted = true) {
    if (!formatted)
        return text.split(/\r?\n/).map(line => ({ runs: [{ text: line }], heading: 0, list: false, quote: false, code: false }));
    const blocks = [];
    let paragraph = [];
    let code = false;
    const flush = () => {
        if (paragraph.length) {
            blocks.push({ runs: inlineMarkdown(paragraph.join(' ')), heading: 0, list: false, quote: false, code: false });
            paragraph = [];
        }
    };
    for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
        if (/^\s*```/.test(line)) {
            flush();
            code = !code;
            continue;
        }
        if (code) {
            blocks.push({ runs: [{ text: line, code: true }], heading: 0, list: false, quote: false, code: true });
            continue;
        }
        if (!line.trim()) {
            flush();
            blocks.push({ runs: [{ text: '' }], heading: 0, list: false, quote: false, code: false });
            continue;
        }
        const heading = /^(#{1,6})\s*(.*)$/.exec(line);
        const list = /^\s*(?:[-*+] |\d+\. )(.*)$/.exec(line);
        const quote = /^\s*>\s?(.*)$/.exec(line);
        if (heading || list || quote) {
            flush();
            blocks.push({ runs: inlineMarkdown(heading?.[2] ?? list?.[1] ?? quote?.[1] ?? ''), heading: heading?.[1]?.length ?? 0, list: !!list, quote: !!quote, code: false });
        }
        else
            paragraph.push(line.trim());
    }
    flush();
    return blocks;
}

},
"presentation/src/mindmap.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mindmapEdges = mindmapEdges;
const mindmap_js_1 = require("profiles/src/mindmap.js");
const core_js_1 = require("profiles/src/core.js");
const model_js_1 = require("presentation/src/model.js");
const graph_common_js_1 = require("presentation/src/graph-common.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
const topicBounds = (entry) => entry.item.hitTargets.find(hit => (0, model_js_1.refKey)(hit.target) === (0, model_js_1.refKey)(entry.definition.ref))?.bounds ?? entry.item.bounds;
function mindmapEdges(edges, nodes, all, frame, viewProperties, diagnostics, unavailable) {
    const topics = new Set(nodes.filter(node => node.mindmapTopic !== false && (0, mindmap_js_1.isMindmapTopic)(node.definition.record)).map(node => (0, mindmap_js_1.mindmapKey)(node.definition)));
    const connections = edges.map(edge => {
        const from = (0, graph_common_js_1.endEntry)(edge, 0, nodes, all), to = (0, graph_common_js_1.endEntry)(edge, 1, nodes, all);
        return { edge, from, to, internal: (0, mindmap_js_1.mindmapRelationKind)(from?.definition, to?.definition, topics) === 'internal' };
    });
    const outward = new Map(), parents = new Map();
    for (const connection of connections)
        if (connection.internal && connection.to)
            parents.set(connection.to.item.occurrence, connection);
    const branchSide = (connection) => {
        const authored = (0, model_js_1.pathValue)(connection.edge.appearance?.record, 'route.source_side');
        if (authored === 'west' || authored === 'east')
            return authored === 'west' ? -1 : 1;
        return (0, graph_common_js_1.center)(topicBounds(connection.to))[0] < (0, graph_common_js_1.center)(topicBounds(connection.from))[0] ? -1 : 1;
    };
    const children = new Map(), queue = [];
    for (const connection of connections)
        if (connection.internal && connection.from && connection.to) {
            const key = connection.from.item.occurrence, list = children.get(key) ?? [];
            list.push(connection);
            children.set(key, list);
            if (!parents.has(key)) {
                outward.set(connection.to.item.occurrence, branchSide(connection));
                queue.push(connection.to.item.occurrence);
            }
        }
    for (let at = 0; at < queue.length; at++)
        for (const connection of children.get(queue[at]) ?? [])
            if (!outward.has(connection.to.item.occurrence)) {
                const key = connection.to.item.occurrence;
                outward.set(key, outward.get(queue[at]));
                queue.push(key);
            }
    const rootKeys = new Set(topics);
    for (const connection of connections)
        if (connection.internal && connection.to)
            rootKeys.delete((0, mindmap_js_1.mindmapKey)(connection.to.definition));
    const uniqueRoot = rootKeys.size === 1 ? [...rootKeys][0] : undefined;
    const ports = new Map();
    for (const connection of connections) {
        if (!connection.from || !connection.to)
            continue;
        for (const at of [0, 1]) {
            const node = at === 0 ? connection.from : connection.to, other = at === 0 ? connection.to : connection.from;
            if (!topics.has((0, mindmap_js_1.mindmapKey)(node.definition)))
                continue;
            const authored = (0, model_js_1.pathValue)(connection.edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side');
            const vertical = at === 1 && !connection.internal && uniqueRoot === (0, mindmap_js_1.mindmapKey)(node.definition) && !topics.has((0, mindmap_js_1.mindmapKey)(other.definition)) && (authored === 'north' || authored === 'south');
            const direction = outward.get(node.item.occurrence), side = vertical ? (authored === 'north' ? -1 : 1) : direction === undefined ? (authored === 'west' ? -1 : authored === 'east' ? 1 : (0, graph_common_js_1.center)(topicBounds(other))[0] < (0, graph_common_js_1.center)(topicBounds(node))[0] ? -1 : 1) : at === 0 ? direction : -direction;
            const key = node.item.occurrence + ':' + (vertical ? 'vertical:' : 'horizontal:') + side, list = ports.get(key) ?? [];
            list.push({ connection, at, node, side, vertical, otherY: (0, graph_common_js_1.center)(topicBounds(other))[vertical ? 0 : 1] });
            ports.set(key, list);
            if (!vertical && (authored === 'north' || authored === 'south'))
                diagnostics.push({ code: 'mindmap-horizontal-attachment', severity: 'warning', target: connection.edge.definition.ref, message: 'Mind-map topics attach on the left or right; the authored top/bottom attachment is ignored.' });
            else if (authored === 'west' && side > 0 || authored === 'east' && side < 0) {
                diagnostics.push({ code: 'mindmap-attachment-conflict', severity: 'warning', target: connection.edge.definition.ref, message: 'The authored attachment conflicts with the incoming/outgoing sides of this mind-map topic.' });
                unavailable.push('mindmap-attachment:' + (0, model_js_1.refKey)(connection.edge.definition.ref));
            }
        }
    }
    for (const list of ports.values()) {
        list.sort((a, b) => a.otherY - b.otherY || a.connection.edge.item.occurrence.localeCompare(b.connection.edge.item.occurrence));
        list.forEach((port, index) => {
            const b = topicBounds(port.node), fraction = (index + 1) / (list.length + 1), point = port.vertical ? [b.x + b.width * fraction, b.y + (port.side > 0 ? b.height : 0)] : [b.x + (port.side > 0 ? b.width : 0), b.y + b.height * fraction];
            if (port.at === 0)
                port.connection.a = point;
            else
                port.connection.b = point;
        });
    }
    const prior = [], reserved = [], obstacles = [{ x: frame.x, y: frame.y, width: frame.width, height: 45 }, ...nodes.map(topicBounds)];
    const constrained = nodes.some(node => typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false);
    let externalIndex = 0;
    const output = new Map();
    const ordered = [...connections.filter(connection => connection.internal), ...connections.filter(connection => !connection.internal)];
    for (const connection of ordered) {
        const { edge, from, to } = connection;
        if (!from || !to) {
            output.set(edge, edge);
            continue;
        }
        if (!connection.internal) {
            const route = { ...(0, model_js_1.object)(edge.appearance?.record.route), routing: 'curved' };
            for (const at of [0, 1]) {
                const point = at === 0 ? connection.a : connection.b, node = at === 0 ? from : to;
                if (!point)
                    continue;
                const b = topicBounds(node), prefix = at === 0 ? 'source' : 'target';
                const vertical = point[1] === b.y || point[1] === b.y + b.height;
                route[prefix + '_side'] = vertical ? point[1] === b.y ? 'north' : 'south' : point[0] === b.x ? 'west' : 'east';
                route[prefix + '_fraction'] = vertical ? (point[0] - b.x) / b.width : (point[1] - b.y) / b.height;
            }
            const occurrence = edge.appearance ?? { ...edge.definition, owner: 'appearance' };
            const normal = (point, node) => { const b = topicBounds(node); return point[0] === b.x ? [-1, 0] : point[0] === b.x + b.width ? [1, 0] : point[1] === b.y ? [0, -1] : [0, 1]; };
            externalIndex++;
            const render = (via) => {
                const tracks = [...prior], labels = [...reserved], current = { ...route, ...(via ? { via: via.map(([x, y]) => ({ x: x - frame.x, y: y - frame.y })) } : {}) };
                const decorated = (0, graph_common_js_1.decorateEdge)({ ...edge, appearance: { ...occurrence, record: { ...occurrence.record, route: current } } }, nodes, all, 'mindmap.basic@1', frame, obstacles, labels, tracks, 'none', viewProperties, { ...(connection.a ? { source: connection.a, sourceDirection: normal(connection.a, from) } : {}), ...(connection.b ? { target: connection.b, targetDirection: normal(connection.b, to) } : {}), horizontal: true });
                return { decorated, points: tracks.at(-1), labels };
            };
            const clear = (points) => {
                const interior = [...points];
                if (interior.length > 1)
                    for (const [at, neighbour] of [[0, 1], [interior.length - 1, interior.length - 2]]) {
                        const p = points[at], q = points[neighbour], distance = Math.max(1, Math.hypot(q[0] - p[0], q[1] - p[1]));
                        interior[at] = [p[0] + (q[0] - p[0]) * .01 / distance, p[1] + (q[1] - p[1]) * .01 / distance];
                    }
                return !nodes.some(node => { const b = topicBounds(node); return node === from || node === to ? (0, graph_common_js_1.routeIntersects)(interior, { x: b.x + .1, y: b.y + .1, width: b.width - .2, height: b.height - .2 }) : (0, graph_common_js_1.routeIntersects)(points, b); }) && !prior.some(track => routesCross(points, track));
            };
            let chosen = render(), clearRoute = clear(chosen.points);
            if (!clearRoute && !(0, model_js_1.array)(route.via).length) {
                const a = connection.a ?? (0, graph_common_js_1.endpoint)(edge, 0, from, to, all), b = connection.b ?? (0, graph_common_js_1.endpoint)(edge, 1, to, from, all);
                const stub = (point, node) => { const bounds = topicBounds(node); return point[0] <= bounds.x + .01 ? [point[0] - 20, point[1]] : point[0] >= bounds.x + bounds.width - .01 ? [point[0] + 20, point[1]] : [point[0], point[1] + (point[1] <= bounds.y + .01 ? -20 : 20)]; };
                const start = stub(a, from), end = stub(b, to), boxes = nodes.map(topicBounds), margin = 36 + externalIndex * 14;
                const top = Math.min(...boxes.map(b => b.y)) - margin, bottom = Math.max(...boxes.map(b => b.y + b.height)) + margin, left = Math.min(...boxes.map(b => b.x)) - margin, right = Math.max(...boxes.map(b => b.x + b.width)) + margin;
                const candidates = [
                    [start, [start[0], end[1]], end], [start, [end[0], start[1]], end],
                    [start, [start[0], top], [end[0], top], end], [start, [start[0], bottom], [end[0], bottom], end],
                    [start, [left, start[1]], [left, end[1]], end], [start, [right, start[1]], [right, end[1]], end],
                ];
                for (const via of candidates) {
                    const candidate = render(via);
                    if (clear(candidate.points)) {
                        chosen = candidate;
                        clearRoute = true;
                        break;
                    }
                }
            }
            if (!clearRoute) {
                diagnostics.push({ code: 'mindmap-route-conflict', severity: 'warning', target: edge.definition.ref, message: 'This context relationship cannot avoid the current mind-map branches. Move its context endpoint or adjust the authored route.' });
                unavailable.push('mindmap-route:' + (0, model_js_1.refKey)(edge.definition.ref));
            }
            prior.push(chosen.points);
            reserved.splice(0, reserved.length, ...chosen.labels);
            const { appearance: _appearance, ...result } = chosen.decorated;
            output.set(edge, { ...result, ...(edge.appearance ? { appearance: edge.appearance } : {}) });
            continue;
        }
        const a = connection.a, b = connection.b, direction = a[0] === topicBounds(from).x ? -1 : 1;
        const reach = Math.max(24, Math.abs(b[0] - a[0]) / 2), c1 = [a[0] + direction * reach, a[1]], c2 = [b[0] - direction * reach, b[1]];
        const points = (0, graph_common_js_1.cubicPoints)(a, c1, c2, b);
        const blocked = constrained && nodes.some(node => node !== from && node !== to && (0, graph_common_js_1.routeIntersects)(points, topicBounds(node)));
        const crossed = constrained && prior.some(route => routesCross(points, route));
        if (blocked || crossed || direction * (b[0] - a[0]) <= 0) {
            diagnostics.push({ code: 'mindmap-route-conflict', severity: 'warning', target: edge.definition.ref, message: 'Pinned topic positions prevent a clear outward mind-map branch. Move or unpin the affected topics.' });
            unavailable.push('mindmap-route:' + (0, model_js_1.refKey)(edge.definition.ref));
        }
        prior.push(points);
        const defaults = (0, core_js_1.roleDescriptor)('assoc', 'relation')?.render ?? {}, stroke = (0, model_js_1.str)((0, graph_common_js_1.styled)(edge, 'stroke.color', defaults.colour), '#475569'), weight = (0, model_js_1.num)((0, graph_common_js_1.styled)(edge, 'stroke.weight', (0, graph_common_js_1.styled)(edge, 'stroke.width', defaults.width)), 1.5);
        const dash = (0, graph_common_js_1.styled)(edge, 'stroke.dash', defaults.pattern ?? ''), pattern = Array.isArray(dash) ? dash.join(' ') : dash === 'dotted' ? '2 3' : dash === 'dashed' ? '6 4' : typeof dash === 'string' && dash !== 'solid' ? dash : undefined;
        const line = (0, graph_glyphs_js_1.path)(`M${a[0]},${a[1]}C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${b[0]},${b[1]}`, 'none', stroke, weight, pattern);
        const primitives = [(0, model_js_1.str)((0, graph_common_js_1.styled)(edge, 'style.look', (0, model_js_1.pathValue)(viewProperties, 'style.look'))) === 'handdrawn' ? (0, graph_glyphs_js_1.sketchPrimitive)(line, (0, model_js_1.num)((0, model_js_1.pathValue)(edge.effective, 'style.seed'), 42), (0, model_js_1.num)((0, model_js_1.pathValue)(edge.effective, 'style.roughness'), 1)) : line];
        output.set(edge, (0, graph_common_js_1.changed)(edge, (0, graph_common_js_1.finiteBounds)([Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1]))], [Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))], 8), primitives, 'Mind-map branch'));
    }
    return connections.map(connection => output.get(connection.edge));
}
function routesCross(a, b) {
    const bounds = (points) => ({ left: Math.min(...points.map(p => p[0])), right: Math.max(...points.map(p => p[0])), top: Math.min(...points.map(p => p[1])), bottom: Math.max(...points.map(p => p[1])) });
    const x = bounds(a), y = bounds(b);
    if (x.right < y.left || y.right < x.left || x.bottom < y.top || y.bottom < x.top)
        return false;
    for (let i = 1; i < a.length; i++)
        for (let j = 1; j < b.length; j++) {
            const p = a[i - 1], q = a[i], r = b[j - 1], s = b[j], dx = q[0] - p[0], dy = q[1] - p[1], ux = s[0] - r[0], uy = s[1] - r[1], den = dx * uy - dy * ux;
            if (Math.abs(den) < 1e-8) {
                if (Math.abs((r[0] - p[0]) * dy - (r[1] - p[1]) * dx) < 1e-8) {
                    const axis = Math.abs(dx) >= Math.abs(dy) ? 0 : 1;
                    if (Math.min(Math.max(p[axis], q[axis]), Math.max(r[axis], s[axis])) - Math.max(Math.min(p[axis], q[axis]), Math.min(r[axis], s[axis])) > 1e-6)
                        return true;
                }
                continue;
            }
            const t = ((r[0] - p[0]) * uy - (r[1] - p[1]) * ux) / den, u = ((r[0] - p[0]) * dy - (r[1] - p[1]) * dx) / den;
            if (t >= 0 && t <= 1 && u >= 0 && u <= 1 && !(i === 1 && t === 0 || i === a.length - 1 && t === 1) && !(j === 1 && u === 0 || j === b.length - 1 && u === 1))
                return true;
        }
    return false;
}

},
"presentation/src/relation-presentation.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.relationLegendVisible = relationLegendVisible;
exports.relationPresentation = relationPresentation;
exports.relationCaption = relationCaption;
exports.prepareRelationPresentation = prepareRelationPresentation;
const model_js_1 = require("presentation/src/model.js");
const mindmap_js_1 = require("profiles/src/mindmap.js");
function relationLegendVisible(view) {
    return (0, model_js_1.pathValue)(view, 'legend.placement') !== 'none' && (0, model_js_1.pathValue)(view, 'chrome.legend') !== 'off';
}
function relationPresentation(entry, view = entry.view.record) {
    const allowed = entry.definition.record.category === 'relation' && entry.relationLabelAllowed !== false;
    const setting = (path) => (0, model_js_1.pathValue)(entry.effective, path) ?? (0, model_js_1.pathValue)(entry.appearance?.record, path);
    const profile = (0, model_js_1.str)(entry.view.record.profile), viewMode = (0, model_js_1.str)((0, model_js_1.pathValue)(view, 'legend.mode'), 'text');
    const native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
    const inherited = relationLegendVisible(view) && (viewMode === 'numbers' || native && viewMode === 'tokens') ? viewMode : 'text';
    const requested = setting('label.mode'), mode = requested === 'numbers' || requested === 'text' ? requested : inherited;
    const visibility = setting('label.visible'), included = setting('legend.include');
    return {
        allowed,
        visible: allowed && (typeof visibility === 'boolean' ? visibility : !entry.wireWithoutLabel && profile !== 'fishbone.basic@1'),
        mode: allowed ? mode : 'text',
        inLegend: allowed && (typeof included === 'boolean' ? included : native && !entry.wireWithoutLabel && ['numbers', 'tokens'].includes(viewMode)),
        number: entry.relationNumber ?? '1',
    };
}
function relationCaption(entry, semantic, view) {
    const state = relationPresentation(entry, view);
    if (!state.visible)
        return '';
    if (state.mode === 'numbers')
        return state.number;
    if (state.mode === 'tokens')
        return (0, model_js_1.str)(entry.definition.record.role);
    return (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'route.callout'), (0, model_js_1.str)((0, model_js_1.pathValue)(entry.appearance?.record, 'route.callout'))) || semantic;
}
function prepareRelationPresentation(entries, all, view) {
    const topics = new Set(entries.filter(entry => entry.mindmapTopic !== false && (0, mindmap_js_1.isMindmapTopic)(entry.definition.record)).map(entry => (0, mindmap_js_1.mindmapKey)(entry.definition)));
    const candidates = entries.filter(entry => entry.definition.record.category === 'relation');
    const allowed = (entry) => {
        if ((0, model_js_1.str)(entry.view.record.profile) !== 'mindmap.basic@1')
            return true;
        const ends = (0, model_js_1.array)(entry.definition.record.endpoints);
        return (0, mindmap_js_1.mindmapRelationKind)((0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(ends[0]).definition, entry.definition.file), (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(ends[1]).definition, entry.definition.file), topics) === 'external';
    };
    const identities = new Map();
    for (const entry of candidates)
        if (allowed(entry))
            identities.set((0, model_js_1.refKey)(entry.definition.ref), entry);
    const counts = new Map();
    for (const entry of identities.values()) {
        const id = entry.definition.ref.id;
        counts.set(id, (counts.get(id) ?? 0) + 1);
    }
    const keys = (0, model_js_1.object)((0, model_js_1.pathValue)(view, 'legend.keys')), numbers = new Map();
    let index = 0;
    for (const [identity, entry] of identities) {
        const { file, id } = entry.definition.ref;
        const key = keys[identity] ?? keys[file + '::' + id] ?? (counts.get(id) === 1 ? keys[id] ?? keys[id.split('::').at(-1)] : undefined);
        index++;
        numbers.set(identity, key === undefined ? String(index) : String(key));
    }
    return entries.map(entry => entry.definition.record.category !== 'relation' ? entry : { ...entry, relationLabelAllowed: allowed(entry), ...(numbers.has((0, model_js_1.refKey)(entry.definition.ref)) ? { relationNumber: numbers.get((0, model_js_1.refKey)(entry.definition.ref)) } : {}) });
}

},
"presentation/src/symbol-presentation.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.notePrimitives = notePrimitives;
exports.standaloneChoice = standaloneChoice;
exports.standaloneNode = standaloneNode;
exports.symbolTerminals = symbolTerminals;
exports.symbolTerminal = symbolTerminal;
exports.electricalWireWithoutLabel = electricalWireWithoutLabel;
const model_js_1 = require("presentation/src/model.js");
const table_js_1 = require("presentation/src/table.js");
const markdown_js_1 = require("presentation/src/markdown.js");
const text = (value, x, y, size, color, extra = {}, font = 'sans') => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: font, style: { 'font-size': size, fill: color, ...extra } }] });
function notePrimitives(value, x, y, width, size, color, measure, formatted, maxLines = 30, bodyFont = 'sans') {
    const primitives = [];
    let offset = 0;
    let count = 0;
    for (const block of (0, markdown_js_1.markdownBlocks)(value, formatted)) {
        const font = block.heading ? size * (1.55 - block.heading * .08) : size;
        const sourceRuns = [...(block.list ? [{ text: '• ' }] : block.quote ? [{ text: '› ' }] : []), ...block.runs];
        const label = sourceRuns.map(r => r.text).join('');
        let cursor = 0;
        const lines = (0, table_js_1.layoutTable)([{ id: 'text', max_lines: maxLines }], [[label]], width, value => measure(value) * font / size, { header: false, lineHeight: font * 1.3 }).rows[0]?.cells[0]?.lines ?? [label];
        for (const line of lines) {
            if (count++ >= maxLines) {
                primitives.push(text('…', x, y + offset, font, color));
                return { primitives, height: offset + font * 1.4 };
            }
            const visible = line.endsWith('…') ? line.slice(0, -1) : line;
            const start = Math.max(cursor, label.indexOf(visible, cursor)), end = start + visible.length;
            let sourceOffset = 0;
            const runs = sourceRuns.flatMap(run => {
                const runStart = sourceOffset, runEnd = runStart + run.text.length;
                sourceOffset = runEnd;
                const from = Math.max(start, runStart), to = Math.min(end, runEnd);
                return to > from ? [{ ...run, text: run.text.slice(from - runStart, to - runStart) }] : [];
            });
            if (line.endsWith('…'))
                runs.push({ text: '…' });
            cursor = end;
            let dx = x;
            const textRuns = runs.map(run => { const result = { text: run.text, x: dx, y: y + offset + font - size, fontKey: run.code || block.code ? 'monospace' : bodyFont, style: { 'font-size': font, fill: color, ...(run.bold || block.heading ? { 'font-weight': 700 } : {}), ...(run.italic ? { 'font-style': 'italic' } : {}), ...(run.underline ? { 'text-decoration': 'underline' } : {}) } }; dx += measure(run.text) * font / size; return result; });
            primitives.push({ kind: 'text', runs: textRuns });
            offset += font * 1.4;
        }
    }
    return { primitives, height: offset };
}
function standaloneChoice(effective, definition, origins = {}) {
    const mode = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'symbol.mode'), 'auto');
    if (mode === 'card')
        return undefined;
    if (mode === 'text')
        return { mode };
    const icon = (0, model_js_1.object)((0, model_js_1.pathValue)(definition.record, 'metadata.x_icon'));
    const image = (0, model_js_1.pathValue)(effective, 'symbol.image');
    const authoredNull = image === null && !!origins['symbol.image'] && !origins['symbol.image'].startsWith('standard:');
    const selected = image ?? (!authoredNull && Object.keys(icon).length ? (0, model_js_1.pathValue)(effective, 'background.image') : undefined);
    if (mode !== 'image' && !selected)
        return undefined;
    return { mode: 'image', image: selected, ...(icon.library === 'electrical-common@1' ? { electricalIcon: (0, model_js_1.str)(icon.icon, (0, model_js_1.str)(icon.name)) } : {}) };
}
function union(boxes) {
    const x = Math.min(...boxes.map(b => b.x)), y = Math.min(...boxes.map(b => b.y));
    return { x, y, width: Math.max(...boxes.map(b => b.x + b.width)) - x, height: Math.max(...boxes.map(b => b.y + b.height)) - y };
}
function dimension(value) { return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined; }
function rawNotes(definition) {
    return (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'content.text')) || (0, model_js_1.str)(definition.record.description) || (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'draft.text')) || (0, model_js_1.array)(definition.record.notes).filter(n => !(0, model_js_1.str)((0, model_js_1.object)(n).title).startsWith('Additional source')).map(n => (0, model_js_1.str)((0, model_js_1.object)(n).text)).join('\n\n');
}
function standaloneNode(input) {
    const { definition, appearance, effective, origins, all, x, y, measure } = input;
    const choice = standaloneChoice(effective, definition, origins);
    if (!choice)
        return undefined;
    const size = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.font_size'), 16), font = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'style.font'), 'sans'), color = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'text.color'), '#1f2933');
    const title = (0, model_js_1.str)(appearance?.record.title) || (0, model_js_1.titleOf)(definition.record), primitives = [], diagnostics = [], unavailable = [];
    const presentation = { mode: choice.mode, ...(choice.electricalIcon !== undefined ? { electricalIcon: choice.electricalIcon } : {}) };
    const requestedWidth = dimension((0, model_js_1.pathValue)(effective, 'size.width')), requestedHeight = dimension((0, model_js_1.pathValue)(effective, 'size.height'));
    const maxWidth = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'max_size.width'), 4000), maxHeight = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'max_size.height'), 4000);
    const clampWidth = (v) => Math.max(1, Math.min(maxWidth, Math.max(v, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'min_size.width'), 0))));
    const clampHeight = (v) => Math.max(1, Math.min(maxHeight, Math.max(v, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'min_size.height'), 0))));
    const caption = (label, placement, body) => {
        if (placement === 'none' || !label)
            return body;
        const gap = Math.max(0, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'symbol.label_gap'), 6));
        const lines = label.split('\n'), width = Math.max(1, ...lines.map(line => measure(line, size, font))), height = lines.length * size * 1.4;
        const left = placement.includes('left'), right = placement.includes('right'), top = placement.includes('top'), bottom = placement.includes('bottom');
        const x = left ? body.x - gap - width : right ? body.x + body.width + gap : body.x + (body.width - width) / 2;
        const y = top ? body.y - gap - height : bottom ? body.y + body.height + gap : body.y + (body.height - height) / 2;
        lines.forEach((line, index) => primitives.push(text(line, x, y + size + index * size * 1.4, size, color, {}, font)));
        return union([body, { x, y, width, height }]);
    };
    let body, bounds;
    if (choice.mode === 'text') {
        const content = rawNotes(definition), placement = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'symbol.label'), 'auto'), showTitle = placement !== 'none';
        const inlineTitle = placement === 'auto' || placement === 'inside';
        const value = content ? (showTitle && inlineTitle && title ? title + '\n\n' : '') + content : showTitle ? title : '';
        const width = clampWidth(requestedWidth ?? Math.max(64, Math.min(320, ...value.split('\n').map(line => measure(line, size, font)))));
        const maxLines = Math.max(1, Math.floor((requestedHeight ?? maxHeight) / (size * 1.4)));
        const result = notePrimitives(value, x, y + size, width, size, color, line => measure(line, size, font), (0, model_js_1.pathValue)(effective, 'text.format') !== 'plain' && (0, model_js_1.pathValue)(definition.record, 'content.format') !== 'plain', maxLines, font);
        primitives.push(...result.primitives);
        body = { x, y, width, height: clampHeight(requestedHeight ?? Math.max(size * 1.4, result.height)) };
        bounds = content && showTitle && !inlineTitle ? caption(title, placement, body) : body;
    }
    else {
        const sourcePath = (0, model_js_1.pathValue)(effective, 'symbol.image') != null ? 'symbol.image' : 'background.image';
        const declaringFile = appearance && (0, model_js_1.pathValue)(appearance.record, sourcePath) !== undefined ? appearance.file : definition.file;
        const asset = choice.image ? (0, model_js_1.resolveRecord)(all, choice.image, declaringFile) : undefined;
        const intrinsic = (0, model_js_1.object)(asset?.record.intrinsic_size), natural = asset ? input.assetSizes?.get((0, model_js_1.refKey)(asset.ref)) : undefined;
        const naturalWidth = dimension(intrinsic.width) ?? dimension(natural?.width), naturalHeight = dimension(intrinsic.height) ?? dimension(natural?.height);
        const aspect = naturalWidth && naturalHeight ? naturalWidth / naturalHeight : 1;
        const envelopeWidth = clampWidth(requestedWidth ?? (requestedHeight ? requestedHeight * aspect : 96));
        const envelopeHeight = clampHeight(requestedHeight ?? envelopeWidth / aspect);
        const width = Math.min(envelopeWidth, envelopeHeight * aspect), height = width / aspect;
        body = { x: x + (envelopeWidth - width) / 2, y: y + (envelopeHeight - height) / 2, width, height };
        bounds = body;
        if (asset?.owner === 'asset')
            primitives.push({ kind: 'image', assetId: (0, model_js_1.refKey)(asset.ref), bounds: body });
        else {
            diagnostics.push({ code: 'symbol-image-unavailable', severity: 'warning', message: 'The standalone image has no resolvable asset; its image cannot be displayed.', target: appearance?.ref ?? definition.ref });
            unavailable.push('symbol-image:' + (0, model_js_1.refKey)(appearance?.ref ?? definition.ref));
            primitives.push(text('Image unavailable', body.x + body.width / 2, body.y + body.height / 2, Math.min(size, 12), color, { 'text-anchor': 'middle' }, font));
        }
        const suppliedLabel = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'symbol.label'), 'auto');
        const placement = suppliedLabel === 'auto' ? choice.electricalIcon !== undefined ? 'none' : 'bottom' : suppliedLabel;
        bounds = caption(title, placement, body);
        if (effective.body === 'notes' || effective.body === 'draft') {
            const value = rawNotes(definition);
            if (value) {
                const top = bounds.y + bounds.height + 6, noteWidth = Math.max(body.width, Math.min(280, ...value.split('\n').map(line => measure(line, size, font))));
                const result = notePrimitives(value, body.x, top + size, noteWidth, size, color, line => measure(line, size, font), effective.body !== 'draft' && (0, model_js_1.pathValue)(effective, 'text.format') !== 'plain', 30, font);
                primitives.push(...result.primitives);
                bounds = union([bounds, { x: body.x, y: top, width: noteWidth, height: result.height }]);
            }
        }
    }
    const styles = {};
    for (const [key, attr] of [['weight', 'font-weight'], ['italic', 'font-style'], ['decoration', 'text-decoration'], ['variant', 'font-variant']]) {
        const value = (0, model_js_1.pathValue)(effective, 'text.' + key), origin = origins['text.' + key];
        if (value !== undefined && origin && !origin.startsWith('standard:'))
            styles[attr] = key === 'italic' ? value ? 'italic' : 'normal' : key === 'decoration' && value === 'strike' ? 'line-through' : key === 'variant' && value === 'small_caps' ? 'small-caps' : value;
    }
    for (let index = 0; index < primitives.length; index++) {
        const p = primitives[index];
        if (p.kind === 'text')
            primitives[index] = { ...p, runs: p.runs.map(run => ({ ...run, style: { ...run.style, ...styles } })) };
    }
    return { presentation, bounds, body, primitives, diagnostics, unavailable };
}
function symbolTerminals(entry) {
    const icon = entry.standalone?.electricalIcon;
    if (icon === undefined)
        return [];
    const body = entry.item.hitTargets.find(hit => (0, model_js_1.refKey)(hit.target) === (0, model_js_1.refKey)(entry.definition.ref))?.bounds ?? entry.item.bounds;
    let terminals;
    if (icon === 'ground')
        terminals = [{ x: 12, y: 4, side: 'north' }];
    else if (['gate-and', 'gate-xor', 'op-amp'].includes(icon))
        terminals = [{ x: 1, y: 9, side: 'west' }, { x: 1, y: 15, side: 'west' }, { x: 23, y: 12, side: 'east' }];
    else if (icon === 'switch-no')
        terminals = [{ x: 1, y: 18, side: 'west' }, { x: 23, y: 18, side: 'east' }];
    else if (icon === 'transistor-npn')
        terminals = [{ x: 1, y: 12, side: 'west' }, { x: 18, y: 1, side: 'north' }, { x: 18, y: 23, side: 'south' }];
    else if (['battery', 'fuse', 'resistor', 'capacitor', 'inductor', 'diode', 'led'].includes(icon))
        terminals = [{ x: 1, y: 12, side: 'west' }, { x: 23, y: 12, side: 'east' }];
    else
        return [];
    return terminals.map(t => ({ point: [body.x + body.width * t.x / 24, body.y + body.height * t.y / 24], direction: t.side === 'north' ? [0, -1] : t.side === 'south' ? [0, 1] : t.side === 'west' ? [-1, 0] : [1, 0], side: t.side }));
}
function symbolTerminal(entry, other, side = '', fraction = .5) {
    const terminals = symbolTerminals(entry);
    if (!terminals.length)
        return undefined;
    const body = entry.item.hitTargets.find(hit => (0, model_js_1.refKey)(hit.target) === (0, model_js_1.refKey)(entry.definition.ref))?.bounds ?? entry.item.bounds;
    const target = other.item.hitTargets.find(hit => (0, model_js_1.refKey)(hit.target) === (0, model_js_1.refKey)(other.definition.ref))?.bounds ?? other.item.bounds;
    const sameSide = terminals.filter(t => t.side === side);
    const targetPoint = sameSide.length ? [body.x + body.width * fraction, body.y + body.height * fraction] : [target.x + target.width / 2, target.y + target.height / 2];
    return [...(sameSide.length ? sameSide : terminals)].sort((a, b) => Math.hypot(a.point[0] - targetPoint[0], a.point[1] - targetPoint[1]) - Math.hypot(b.point[0] - targetPoint[0], b.point[1] - targetPoint[1]))[0]?.point;
}
function electricalWireWithoutLabel(edge, from, to) {
    const title = (0, model_js_1.str)(edge.definition.record.title, (0, model_js_1.str)(edge.definition.record.name)).trim().toLowerCase();
    return edge.definition.record.role === 'assoc' && from.standalone?.electricalIcon !== undefined && to.standalone?.electricalIcon !== undefined && ['', 'associated with', 'assoc', 'association'].includes(title) && !(0, model_js_1.pathValue)(edge.appearance?.record, 'route.callout');
}

}});})();
