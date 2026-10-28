import { roleDescriptor } from '../../profiles/src/core.js';
import { isMindmapTopic } from '../../profiles/src/mindmap.js';
import { array, object, str, num, pathValue, records, resolveRecord, refKey, titleOf } from './model.js';
import { graphLayout } from './graph-layouts.js';
import { symbolTerminal, symbolTerminals, electricalWireWithoutLabel } from './symbol-presentation.js';
import { metadata, arrowMarker, sketchPrimitive, line, label, box, oval, path, polygon } from './graph-glyphs.js';
import { relationCaption, relationPresentation } from './relation-presentation.js';
export const center = (b) => [b.x + b.width / 2, b.y + b.height / 2];
export const identity = [1, 0, 0, 1, 0, 0];
/** Unconnected palette drops wait outside the method layout until linked. */
export function provisionalNodes(entries, all) {
    const nodes = entries.filter(entry => entry.definition.record.category !== 'relation');
    const connected = new Set(entries.filter(entry => entry.definition.record.category === 'relation').flatMap(edge => array(edge.definition.record.endpoints).map((_, index) => endEntry(edge, index, nodes, all)?.item.occurrence)));
    return nodes.filter(node => node.appearance?.record.pinned === false && typeof node.appearance.record.position === 'object' && !connected.has(node.item.occurrence));
}
export const finiteBounds = (a, b, padding = 4) => ({ x: Math.min(a[0], b[0]) - padding, y: Math.min(a[1], b[1]) - padding, width: Math.max(1, Math.abs(a[0] - b[0])) + padding * 2, height: Math.max(1, Math.abs(a[1] - b[1])) + padding * 2 });
export const changed = (entry, bounds, primitives, description) => ({ ...entry, item: { ...entry.item, bounds, primitives, transform: identity, hitTargets: [{ id: entry.item.occurrence, target: entry.definition.ref, bounds }], accessible: { ...entry.item.accessible, ...(description ? { description } : {}) } } });
export function mark(owner, target, suffix, bounds, primitives, description) {
    const occurrence = owner.item.occurrence + ':' + suffix;
    return { ...owner, definition: target, item: { ...owner.item, occurrence, target: target.ref, bounds, primitives, transform: identity, hitTargets: [{ id: occurrence, target: target.ref, bounds }], accessible: { role: 'graphics-symbol', label: titleOf(target.record), description } } };
}
export function memberRecords(entry, all) {
    const declared = array(entry.definition.record.members).map(ref => resolveRecord(all, ref, entry.definition.file)).filter((v) => !!v);
    for (const record of all)
        if (record.owner === 'definition' && refKey(resolveRecord(all, record.record.parent ?? pathValue(record.record, 'content.parent') ?? pathValue(record.record, 'content.owner'), record.file)?.ref ?? { file: '', id: '' }) === refKey(entry.definition.ref) && !declared.includes(record))
            declared.push(record);
    return declared;
}
export function endEntry(edge, at, nodes, all) {
    const end = object(array(edge.definition.record.endpoints)[at]);
    const semantic = resolveRecord(all, end.definition ?? end.target ?? end.ref, edge.definition.file);
    if (!semantic)
        return undefined;
    const occurrence = resolveRecord(all, pathValue(edge.appearance?.record, at === 0 ? 'route.from' : 'route.to'), edge.appearance?.file ?? edge.definition.file);
    return nodes.find(n => refKey(n.definition.ref) === refKey(semantic.ref) && (!occurrence || n.appearance && refKey(n.appearance.ref) === refKey(occurrence.ref)));
}
function portBounds(entry) {
    return entry.item.hitTargets.find(hit => refKey(hit.target) === refKey(entry.definition.ref))?.bounds ?? entry.item.bounds;
}
function sidePoint(entry, side, fraction, shaped, automatic = false) {
    const b = shaped || entry.standalone ? portBounds(entry) : entry.item.bounds, horizontal = side === 'west' || side === 'east', sign = side === 'west' || side === 'north' ? -1 : 1;
    const c = center(b);
    // Only the outer body ellipse qualifies, not actor heads, status dots or ports.
    const ellipse = shaped && entry.item.primitives.some(p => p.kind === 'ellipse' && Math.abs(p.bounds.width - b.width) < .01 && Math.abs(p.bounds.height - b.height) < .01 && Math.abs(p.bounds.x + entry.item.transform[4] - b.x) < .01 && Math.abs(p.bounds.y + entry.item.transform[5] - b.y) < .01);
    // Automatic distribution is safe only for a positively identified body
    // ellipse. Keep established central anchors for diamonds, capsules, tags,
    // cylinders and other path contours; an SVG bounding box is not their edge.
    const f = automatic && !ellipse ? .5 : Math.max(0, Math.min(1, fraction)), transverse = (f - .5) * 2;
    const extent = ellipse ? Math.sqrt(Math.max(0, 1 - transverse * transverse)) : 1;
    return horizontal ? [c[0] + sign * b.width / 2 * extent, b.y + b.height * f] : [b.x + b.width * f, c[1] + sign * b.height / 2 * extent];
}
export function endpoint(edge, at, entry, other, all, shaped = false) {
    const end = object(array(edge.definition.record.endpoints)[at]);
    const member = resolveRecord(all, end.member ?? end.port, edge.definition.file), bounds = shaped || entry.standalone ? portBounds(entry) : entry.item.bounds;
    const routeSide = str(pathValue(edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side')), routeFraction = num(pathValue(edge.appearance?.record, at === 0 ? 'route.source_fraction' : 'route.target_fraction'), .5);
    const terminal = symbolTerminal(entry, other, routeSide, routeFraction);
    if (terminal)
        return terminal;
    if (routeSide === 'north' || routeSide === 'south')
        return sidePoint(entry, routeSide, routeFraction, shaped);
    if (routeSide === 'west' || routeSide === 'east')
        return sidePoint(entry, routeSide, routeFraction, shaped);
    if (member) {
        const side = str(object(metadata(member.record, 'x_icom')).type, str(pathValue(member.record, 'content.direction')));
        const ports = memberRecords(entry, all).filter(record => str(record.record.role) === 'core::Port'), portIndex = ports.findIndex(record => refKey(record.ref) === refKey(member.ref)), fraction = portIndex < 0 ? .5 : (portIndex + 1) / (ports.length + 1);
        if (side === 'north' || side === 'top' || side === 'control')
            return [bounds.x + bounds.width * fraction, bounds.y];
        if (side === 'south' || side === 'bottom' || side === 'mechanism')
            return [bounds.x + bounds.width * fraction, bounds.y + bounds.height];
        if (side === 'west' || side === 'left' || side === 'input')
            return [bounds.x, bounds.y + bounds.height * fraction];
        if (side === 'east' || side === 'right' || side === 'output')
            return [bounds.x + bounds.width, bounds.y + bounds.height * fraction];
    }
    const a = center(bounds), b = center(other.standalone ? portBounds(other) : other.item.bounds), dx = b[0] - a[0], dy = b[1] - a[1];
    if (Math.abs(dx) / bounds.width >= Math.abs(dy) / bounds.height)
        return sidePoint(entry, dx >= 0 ? 'east' : 'west', shaped ? Math.max(.25, Math.min(.75, .5 + dy / (bounds.height * 2))) : .5, shaped, true);
    return sidePoint(entry, dy >= 0 ? 'south' : 'north', shaped ? Math.max(.25, Math.min(.75, .5 + dx / (bounds.width * 2))) : .5, shaped, true);
}
/** Styling reaches every generated graph label once, before any inline composition. */
export function resolvedText(entries, profile) {
    return entries.map(entry => {
        if (entry.standalone)
            return entry;
        if (['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile) && entry.definition.record.category !== 'relation')
            return entry;
        if (profile === 'erd.crowfoot@1' && ['columns', 'draft', 'notes'].includes(str(entry.appearance?.record.body, str(entry.effective.body))))
            return entry;
        const font = str(pathValue(entry.effective, 'style.font')), size = num(pathValue(entry.effective, 'style.font_size'), 16), color = str(pathValue(entry.effective, 'text.color'));
        return { ...entry, item: { ...entry.item, primitives: entry.item.primitives.map(primitive => primitive.kind === 'text' ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, fontKey: font || run.fontKey, style: { ...run.style, 'font-size': num(run.style['font-size'], 14) * size / 16, ...(color ? { fill: color } : {}) } })) } : primitive) } };
    });
}
/** Role defaults are subordinate to authored properties, including CSS. */
export function styled(entry, key, fallback) {
    const origin = entry.propertyOrigins?.[key];
    const own = pathValue(entry.appearance?.record, key) ?? pathValue(entry.definition.record, key);
    if (own !== undefined || origin && (!origin.startsWith('standard:') || origin.startsWith('standard:theme')))
        return pathValue(entry.effective, key) ?? own ?? fallback;
    if (origin)
        return fallback;
    const value = pathValue(entry.effective, key);
    return value !== undefined && !['#fff', '#ffffff', 'transparent', '#475569', '#1f2933', 'solid', 'none', 'classic', 1, 1.5, 0].includes(value) ? value : fallback;
}
export function guardText(value) {
    if (typeof value === 'string')
        return value;
    const record = object(value), op = (name) => ({ eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤', in: 'in' }[str(name)] ?? str(name));
    if (record.field)
        return `${str(record.field)} ${op(record.op)} ${String(record.value)}`;
    if (Array.isArray(record.all) || Array.isArray(record.any))
        return array(record.all ?? record.any).map(guardText).join(record.all ? ' and ' : ' or ');
    return Object.entries(record).map(([field, value]) => { const test = object(value); return Object.keys(test).length ? `${field} ${op(test.op)} ${String(test.value ?? '')}` : `${field} = ${String(value)}`; }).join(' and ');
}
export function edgeLabel(entry, all = []) {
    const record = entry.definition.record, role = str(record.role), transition = object(metadata(record, 'x_transition')), message = object(metadata(record, 'x_message'));
    let title = typeof record.title === 'string' ? record.title : str(record.name);
    if (role === 'state.transition')
        title = `${str(transition.event)}${transition.guard ? ' [' + guardText(transition.guard) + ']' : ''}${transition.effect ? ' / ' + str(transition.effect) : ''}` || title;
    if (role === 'uml.message' && ['create', 'delete'].includes(str(message.sort)) && !title.includes('«'))
        title = '«' + str(message.sort) + '» ' + title;
    if (role === 'uml.message')
        title = `${message.seq ? String(message.seq) + ': ' : ''}${title}${message.time ? ' {' + str(message.time) + '}' : ''}${message.duration ? ' {' + str(message.duration) + '}' : ''}`;
    const stereotypes = { 'uml.include': 'include', 'uml.extend': 'extend', 'uml.import': 'import', 'uml.access': 'access', 'uml.merge': 'merge', 'uml.deploy': 'deploy', 'uml.manifest': 'manifest', 'uml.application': 'apply', 'sysml.derive': 'deriveReqt', 'sysml.satisfy': 'satisfy', 'sysml.verify': 'verify', 'sysml.refine': 'refine', 'sysml.trace': 'trace', 'sysml.copy': 'copy', 'sysml.master': 'master', 'sysml.allocate': 'allocate', 'req.satisfies': 'satisfies', 'req.verifies': 'verifies' };
    if (stereotypes[role])
        title = `«${stereotypes[role]}»${title && title.replace(/[«»\s_-]/g, '').toLowerCase() !== stereotypes[role].toLowerCase() ? ' ' + title : ''}`;
    if (role.startsWith('uaf.'))
        title = `«${role.slice(4)}»${title && title.replace(/[«»\s_-]/g, '').toLowerCase() !== role.slice(4).toLowerCase() ? ' ' + title : ''}`;
    const flow = object(metadata(record, 'x_flow'));
    for (const key of ['rate', 'probability', 'continuous'])
        if (flow[key] !== undefined)
            title += ` {${key}=${String(flow[key])}}`;
    const usecase = object(metadata(record, 'x_usecase'));
    if (usecase.condition)
        title += ` [${str(usecase.condition)}]`;
    const sdl = object(metadata(record, 'x_sdl'));
    if (sdl.signals) {
        const signals = '[' + array(sdl.signals).map(value => { const target = resolveRecord(all, value, entry.definition.file); return target ? titleOf(target.record) : typeof value === 'string' ? value.split('::').at(-1).split('.').at(-1) : str(object(value).name, str(object(value).id)); }).join(', ') + ']';
        if (title.replaceAll(' ', '') !== signals.replaceAll(' ', ''))
            title += ' ' + signals;
    }
    if (sdl.nodelay)
        title += ' NODELAY';
    const compatibility = object(metadata(record, 'x_compatibility'));
    if (compatibility.mode)
        title += ' {' + str(compatibility.mode) + '}';
    const continuation = object(metadata(record, 'x_continuation'));
    if (continuation.key)
        title += ' [' + str(continuation.key) + ']';
    const evidence = object(metadata(record, 'x_evidence'));
    if (evidence.result)
        title += ' [' + str(evidence.result) + ']';
    const petri = object(metadata(record, 'x_petri'));
    if (petri.weight !== undefined && petri.weight !== 1)
        title += ` ${String(petri.weight)}`;
    return title;
}
export function orthogonalRoute(a, b, obstacles) {
    const clearance = 18;
    const blocked = (p, q, r) => p[0] === q[0] ? p[0] > r.x - 3 && p[0] < r.x + r.width + 3 && Math.max(p[1], q[1]) > r.y - 3 && Math.min(p[1], q[1]) < r.y + r.height + 3 : p[1] === q[1] && p[1] > r.y - 3 && p[1] < r.y + r.height + 3 && Math.max(p[0], q[0]) > r.x - 3 && Math.min(p[0], q[0]) < r.x + r.width + 3;
    const candidates = [[a, [b[0], a[1]], b], [a, [a[0], b[1]], b], [a, [(a[0] + b[0]) / 2, a[1]], [(a[0] + b[0]) / 2, b[1]], b]];
    const top = Math.min(a[1], b[1], ...obstacles.map(r => r.y)) - clearance, bottom = Math.max(a[1], b[1], ...obstacles.map(r => r.y + r.height)) + clearance, left = Math.min(a[0], b[0], ...obstacles.map(r => r.x)) - clearance, right = Math.max(a[0], b[0], ...obstacles.map(r => r.x + r.width)) + clearance;
    for (const y of [top, bottom])
        candidates.push([a, [a[0], y], [b[0], y], b]);
    for (const x of [left, right])
        candidates.push([a, [x, a[1]], [x, b[1]], b]);
    // Nearby bypass lanes keep edges compact without an unbounded grid search.
    const nearby = obstacles.filter(r => r.x < Math.max(a[0], b[0]) + clearance && r.x + r.width > Math.min(a[0], b[0]) - clearance && r.y < Math.max(a[1], b[1]) + clearance && r.y + r.height > Math.min(a[1], b[1]) - clearance).slice(0, 12);
    for (const obstacle of nearby)
        for (const y of [obstacle.y - clearance, obstacle.y + obstacle.height + clearance])
            candidates.push([a, [a[0], y], [b[0], y], b]);
    const scored = candidates.map(points => ({ points: points.filter((point, i) => !i || point[0] !== points[i - 1][0] || point[1] !== points[i - 1][1]), crossings: points.slice(1).reduce((sum, point, i) => sum + obstacles.filter(r => blocked(points[i], point, r)).length, 0), length: points.slice(1).reduce((sum, point, i) => sum + Math.abs(point[0] - points[i][0]) + Math.abs(point[1] - points[i][1]), 0) }));
    scored.sort((x, y) => x.crossings - y.crossings || x.length - y.length);
    return scored[0].points;
}
// Conservative deterministic text boxes keep labels outside semantic glyphs.
// Candidate count is bounded independently of author route length; the final
// lane below occupied content guarantees a clear placement without rerouting.
export function graphLabelBounds(value, x, y, size, anchor = 'start') {
    const width = [...value].reduce((sum, char) => sum + (/[^\u0000-\u024f]/u.test(char) ? 1 : /[MW@#%]/.test(char) ? .9 : /[il.,' :;]/.test(char) ? .4 : .65) * size, 0) + 8;
    return { x: x - (anchor === 'middle' ? width / 2 : anchor === 'end' ? width : 0) - 4, y: y - size - 3, width, height: size + 8 };
}
export function placeGraphLabel(value, points, obstacles, reserved, size, avoidRoute = false) {
    const lines = value.split('\n'), measurements = lines.map(line => graphLabelBounds(line, 0, 0, size)), width = Math.max(...measurements.map(m => m.width)), height = measurements[0].height + (lines.length - 1) * size * 1.25;
    const intersects = (a, b) => a.x < b.x + b.width + 4 && a.x + a.width + 4 > b.x && a.y < b.y + b.height + 4 && a.y + a.height + 4 > b.y;
    const occupied = [...obstacles, ...reserved], routeSegments = points.slice(1).map((b, i) => ({ a: points[i], b, length: Math.hypot(b[0] - points[i][0], b[1] - points[i][1]) })), segments = [...routeSegments].sort((a, b) => b.length - a.length).slice(0, 16);
    // A sampled cubic can have its longest segments near the endpoints. Always
    // consider the complete route's middle before local segment candidates, so
    // a label can use a narrow inter-card gap without being pushed above a card.
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
        // Prefer the route normal, but also try the other axis: a steep cubic
        // can still have its only free label space directly above its midpoint.
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
    return { bounds, point: [bounds.x + 4, bounds.y + size + 3], ...(Math.hypot(point[0] - closest[0], point[1] - closest[1]) > 18 ? { leader: line(point, closest, '#94a3b8', .7, '2 2') } : {}) };
}
export function roundedRoute(points, radius) {
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
export function cubicPoints(a, c1, c2, b) {
    return Array.from({ length: 33 }, (_, i) => { const t = i / 32, u = 1 - t; return [u * u * u * a[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * b[0], u * u * u * a[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * b[1]]; });
}
export function roundedPoints(points, radius) {
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
export function routeIntersects(points, bounds) {
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
/** Disconnect crossing tracks without changing semantic junctions/endpoints.
 * Arc-length intervals let a gap span sampled curve segments, including a
 * crossing exactly on a sample vertex. The source curve stays smooth elsewhere. */
export function crossingRoute(points, prior, mode) {
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
    const at = (length) => { let i = 1; while (i < distance.length - 1 && distance[i] < length)
        i++; const fraction = (length - distance[i - 1]) / Math.max(.001, distance[i] - distance[i - 1]), a = points[i - 1], b = points[i]; return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction]; };
    let d = `M${points[0][0]},${points[0][1]}`, cursor = 0;
    const append = (end) => { for (let i = 1; i < distance.length; i++)
        if (distance[i] > cursor && distance[i] < end)
            d += `L${points[i][0]},${points[i][1]}`; const p = at(end); d += `L${p[0]},${p[1]}`; cursor = end; };
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
export function cleanRoute(points) { const result = []; for (const p of points) {
    if (result.length && result.at(-1)[0] === p[0] && result.at(-1)[1] === p[1])
        continue;
    while (result.length > 1) {
        const a = result.at(-2), b = result.at(-1);
        if (Math.abs((b[0] - a[0]) * (p[1] - b[1]) - (b[1] - a[1]) * (p[0] - b[0])) > .001 || (b[0] - a[0]) * (p[0] - b[0]) + (b[1] - a[1]) * (p[1] - b[1]) < 0)
            break;
        result.pop();
    }
    result.push(p);
} return result; }
/** Outward cardinal normal, including authored attachment sides. */
function portDirection(edge, at, node, point) {
    const terminal = symbolTerminals(node).find(t => Math.hypot(t.point[0] - point[0], t.point[1] - point[1]) < .01);
    if (terminal)
        return terminal.direction;
    const side = pathValue(edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side');
    if (side === 'north')
        return [0, -1];
    if (side === 'south')
        return [0, 1];
    if (side === 'west')
        return [-1, 0];
    if (side === 'east')
        return [1, 0];
    const b = portBounds(node), c = center(b), dx = (point[0] - c[0]) / Math.max(1, b.width), dy = (point[1] - c[1]) / Math.max(1, b.height);
    return Math.abs(dx) >= Math.abs(dy) ? [dx < 0 ? -1 : 1, 0] : [0, dy < 0 ? -1 : 1];
}
/** Route between escape points; endpoint bodies remain obstacles for the middle
 * section. Rounded corners reserve extra length so their visible straight
 * segment still satisfies layout.port_clearance. Explicit waypoints bypass this. */
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
        // Shared endpoint stems are intentional. Middle tracks must not retrace
        // earlier parallel/reverse relations, including diagonal endpoint pairs.
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
export function decorateEdge(edge, nodes, all, profile, frame, labelObstacles, reservedLabels, priorRoutes, crossings, viewProperties, attachments) {
    const from = endEntry(edge, 0, nodes, all), to = endEntry(edge, 1, nodes, all);
    if (!from || !to)
        return edge;
    const a = [...(attachments?.source ?? endpoint(edge, 0, from, to, all, profile !== 'mindmap.basic@1'))], b = [...(attachments?.target ?? endpoint(edge, 1, to, from, all, profile !== 'mindmap.basic@1'))], role = str(edge.definition.record.role), record = edge.definition.record;
    if (refKey(from.definition.ref) === refKey(to.definition.ref)) {
        if (!pathValue(edge.appearance?.record, 'route.source_side')) {
            const p = sidePoint(from, 'east', .35, profile !== 'mindmap.basic@1');
            a[0] = p[0];
            a[1] = p[1];
        }
        if (!pathValue(edge.appearance?.record, 'route.target_side')) {
            const p = sidePoint(to, 'east', .65, profile !== 'mindmap.basic@1');
            b[0] = p[0];
            b[1] = p[1];
        }
    }
    const marks = array(edge.appearance?.record.marks ?? edge.effective.marks ?? record.marks).map(String), render = roleDescriptor(role, 'relation')?.render ?? {}, stroke = str(styled(edge, 'stroke.color', marks.includes('forbidden') ? '#b91c1c' : marks.includes('tentative') ? '#64748b' : render.colour), '#475569'), qualifiers = object(record.qualifiers);
    const dashed = /dependency|realization|include|extend|import|access|merge|manifest|deploy|application|sysml\.(allocate|derive|satisfy|verify|refine|trace|copy|master)|req\.|messageflow|petri\.testarc|bpmn\.association/.test(role) || object(metadata(record, 'x_message')).sort === 'reply' || metadata(record, 'x_return') === true;
    const route = array(pathValue(edge.appearance?.record, 'route.via')).map(object).map(p => [frame.x + num(p.x), frame.y + num(p.y)]);
    const same = refKey(from.definition.ref) === refKey(to.definition.ref) || a[0] === b[0] && a[1] === b[1], routing = str(pathValue(edge.appearance?.record, 'route.routing'), str(pathValue(viewProperties ?? edge.view.record, 'layout.routing'), 'orthogonal')), points = same ? [a, [a[0] + 50, a[1]], [b[0] + 50, b[1]], b] : route.length ? [a, ...route, b] : routing === 'straight' || routing === 'string' || routing === 'curved' && str(pathValue(edge.appearance?.record, 'route.curve'), str(pathValue(viewProperties ?? edge.view.record, 'layout.curve'), 'bezier')) !== 'rounded' ? [a, b] : orthogonalRoute(a, b, nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes(str(node.definition.record.role))).map(node => node.item.bounds));
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
    const curve = str(pathValue(edge.appearance?.record, 'route.curve'), str(pathValue(viewProperties ?? edge.view.record, 'layout.curve'), 'bezier')), tension = num(pathValue(edge.appearance?.record, 'route.curve_tension'), num(pathValue(viewProperties ?? edge.view.record, 'layout.curve_tension'), .5)), radius = num(pathValue(edge.appearance?.record, 'route.curve_radius'), num(pathValue(viewProperties ?? edge.view.record, 'layout.curve_radius'), 32));
    let cornerRadius = radius;
    const endpointRouting = profile !== 'mindmap.basic@1' && !route.length && (same || routing === 'orthogonal' || routing === 'curved' && curve === 'rounded');
    if (endpointRouting) {
        const clearance = Math.max(0, num(pathValue(viewProperties ?? edge.view.record, 'layout.port_clearance'), 28)), objectClearance = Math.max(0, num(pathValue(viewProperties ?? edge.view.record, 'layout.object_clearance'), 16));
        const source = attachments?.sourceDirection ?? portDirection(edge, 0, from, a), target = attachments?.targetDirection ?? portDirection(edge, 1, to, b);
        // A full corner radius must not push the escape into a neighbouring
        // body. Reduce the corner locally; retain the requested visible stem.
        if (routing === 'curved')
            for (const [point, normal, owner] of [[a, source, from], [b, target, to]])
                for (const node of nodes) {
                    if (node === owner || ['uml.subject', 'network.rack'].includes(str(node.definition.record.role)))
                        continue;
                    const box = portBounds(node), transverse = normal[0] ? point[1] >= box.y && point[1] <= box.y + box.height : point[0] >= box.x && point[0] <= box.x + box.width;
                    const distance = normal[0] ? normal[0] > 0 ? box.x - point[0] : point[0] - box.x - box.width : normal[1] > 0 ? box.y - point[1] : point[1] - box.y - box.height;
                    if (transverse && distance >= 0)
                        cornerRadius = Math.min(cornerRadius, Math.max(0, (distance - clearance) / 2));
                }
        const routed = portRoute(a, b, from, to, source, target, nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes(str(node.definition.record.role))).map(portBounds), clearance, objectClearance, routing === 'curved' ? cornerRadius : 0, parallel, priorRoutes);
        points.splice(0, points.length, ...routed);
    }
    const cleaned = cleanRoute(points), obstacles = nodes.filter(node => node !== from && node !== to && !['uml.subject', 'network.rack'].includes(str(node.definition.record.role))).map(node => ({ ...node.item.bounds, x: node.item.bounds.x - 8, y: node.item.bounds.y - 8, width: node.item.bounds.width + 16, height: node.item.bounds.height + 16 }));
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
    const routePrimitive = path(d, 'none', stroke, num(styled(edge, 'stroke.weight', styled(edge, 'stroke.width', render.width)), 1.5), dashPattern), handdrawn = str(styled(edge, 'style.look', pathValue(viewProperties ?? edge.view.record, 'style.look'))) === 'handdrawn';
    const ps = [handdrawn ? sketchPrimitive(routePrimitive, num(pathValue(edge.effective, 'style.seed'), 42), num(pathValue(edge.effective, 'style.roughness'), 1)) : routePrimitive];
    if (marks.includes('forbidden')) {
        const middle = Math.floor((labelPoints.length - 1) / 2), start = labelPoints[middle], finish = labelPoints[middle + 1] ?? start, mx = (start[0] + finish[0]) / 2, my = (start[1] + finish[1]) / 2, angle = Math.atan2(finish[1] - start[1], finish[0] - start[0]), nx = -Math.sin(angle), ny = Math.cos(angle), tx = Math.cos(angle), ty = Math.sin(angle);
        for (const offset of [-5, 0, 5])
            ps.push(line([mx + tx * offset - nx * 9, my + ty * offset - ny * 9], [mx + tx * offset + nx * 9, my + ty * offset + ny * 9], stroke, 2));
    }
    const end = points.at(-1), prev = tangentEnd;
    const sourceEndpoint = object(qualifiers.source), targetEndpoint = object(qualifiers.target);
    let sourceMark = str(sourceEndpoint.mark, str(pathValue(record, 'properties.source_mark'))), targetMark = str(targetEndpoint.mark, str(pathValue(record, 'properties.target_mark')));
    if (!sourceMark && typeof sourceEndpoint.navigable === 'boolean')
        sourceMark = sourceEndpoint.navigable ? 'open' : 'none';
    if (!targetMark && typeof targetEndpoint.navigable === 'boolean')
        targetMark = targetEndpoint.navigable ? 'open' : 'none';
    if (!sourceMark)
        sourceMark = str(styled(edge, 'stroke.source_mark', render.start === 'diamond' ? 'filled-diamond' : render.start === 'hollow_diamond' ? 'diamond' : render.start === 'filled_triangle' ? 'filled-triangle' : render.start));
    if (!targetMark)
        targetMark = str(styled(edge, 'stroke.target_mark', render.end === 'diamond' ? 'filled-diamond' : render.end === 'hollow_diamond' ? 'diamond' : render.end === 'filled_triangle' ? 'filled-triangle' : render.end));
    if (!targetMark)
        targetMark = role === 'uml.generalization' || role === 'uml.realization' ? 'triangle' : role === 'uml.extension' ? 'filled' : role === 'petri.inhibitor' ? 'circle' : /assoc|uml\.link|commpath|family\.partner|network\.attaches|fbd\.wire|ladder\.series|bpmn\.conversationlink/.test(role) ? 'none' : 'open';
    if (role === 'sysml.composition' && !sourceMark)
        sourceMark = 'filled-diamond';
    if (profile === 'erd.crowfoot@1') {
        const chen = object(metadata(record, 'x_chen'));
        const cardinal = (value) => { const c = object(value); return c.max === 'many' ? c.min === 0 ? 'zeromany' : 'many' : c.min === 0 ? 'zeroone' : 'one'; };
        sourceMark = str(pathValue(record, 'properties.source_mark'), cardinal(chen.from));
        targetMark = str(pathValue(record, 'properties.target_mark'), cardinal(chen.to));
    }
    ps.push(...arrowMarker(a, tangentStart, sourceMark, stroke), ...arrowMarker(end, prev, targetMark, stroke));
    if (role === 'bpmn.messageflow')
        ps.push(...arrowMarker(a, b, 'circle', stroke));
    if (role === 'vsm.einfo')
        ps.push(path(`M${a[0]},${a[1]}L${(a[0] + b[0]) / 2 - 12},${(a[1] + b[1]) / 2 + 10}L${(a[0] + b[0]) / 2 + 12},${(a[1] + b[1]) / 2 - 10}L${b[0]},${b[1]}`, 'none', stroke));
    const labelBounds = [], textScale = num(pathValue(edge.effective, 'style.font_size'), 16) / 16;
    const addLabel = (value, at, font = 12, numeric = false) => {
        if (!value)
            return;
        // Narrow connector gaps need wrapped labels, not a distant single-line
        // caption below the whole diagram. End labels remain a compact block.
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
        const fill = str(pathValue(viewProperties ?? edge.view.record, 'background.color'), '#fff');
        if (numeric) {
            const cx = placement.bounds.x + placement.bounds.width / 2, cy = placement.bounds.y + placement.bounds.height / 2;
            ps.push(oval({ x: cx - 11, y: cy - 11, width: 22, height: 22 }, fill, '#64748b', .8), label(value, cx, cy + 4, 11, '#334155', { 'text-anchor': 'middle' }));
        }
        else
            ps.push(box(placement.bounds, fill, 'none', 0), ...lines.map((text, i) => label(text, placement.point[0], placement.point[1] + i * font * textScale * 1.25, font, '#334155')));
    };
    const wireWithoutLabel = electricalWireWithoutLabel(edge, from, to);
    edge = { ...edge, wireWithoutLabel };
    const presentation = relationPresentation(edge, viewProperties);
    addLabel(relationCaption(edge, edgeLabel(edge, all), viewProperties), labelPoints, 12, presentation.mode === 'numbers');
    const endlabels = object(metadata(record, 'x_endlabels'));
    for (const [key, p] of [['source', a], ['target', b]]) {
        const endLabel = object(endlabels[key]);
        const value = [endLabel.role, endLabel.multiplicity, endLabel.qualifier ? '[' + str(endLabel.qualifier) + ']' : ''].filter(Boolean).join(' ');
        if (value)
            addLabel(value, [p, p], 11);
    }
    if (metadata(record, 'x_interrupt') || metadata(record, 'x_exception'))
        ps.push(label('ϟ', (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 10, 24, stroke));
    if (metadata(record, 'x_tunnel'))
        ps.push(label('( )', a[0] - 10, a[1] + 5, 13, stroke));
    return changed({ ...edge, ...(wireWithoutLabel ? { wireWithoutLabel } : {}) }, finiteBounds([Math.min(...labelPoints.map(p => p[0]), ...labelBounds.map(b => b.x)), Math.min(...labelPoints.map(p => p[1]), ...labelBounds.map(b => b.y))], [Math.max(...labelPoints.map(p => p[0]), ...labelBounds.map(b => b.x + b.width)), Math.max(...labelPoints.map(p => p[1]), ...labelBounds.map(b => b.y + b.height))], 18), ps, `${profile}; ${role}; ${edgeLabel(edge)}${marks.length ? '; ' + marks.join(', ') : ''}`);
}
export function boundaryPoint(bounds, toward) { const c = center(bounds), dx = toward[0] - c[0], dy = toward[1] - c[1], ratio = 1 / Math.max(Math.abs(dx) / (bounds.width / 2), Math.abs(dy) / (bounds.height / 2), 1); return [c[0] + dx * ratio, c[1] + dy * ratio]; }
export function layoutNative(nodes, edges, all, view, frame, effective) {
    nodes = nodes.map(node => {
        const reference = object(metadata(node.definition.record, 'x_subdiagram'));
        if (!reference.view || !['link', 'badge', 'collapsed'].includes(str(reference.display, 'collapsed')))
            return node;
        const target = resolveRecord(all, reference.view, node.definition.file) ?? all.find(r => r.owner === 'view' && r.file === node.definition.file && (r.ref.id === reference.view || r.record.name === reference.view));
        const title = target ? titleOf(target.record) : str(reference.view), b = node.item.bounds, footer = { x: b.x, y: b.y + b.height, width: b.width, height: 28 };
        const limit = Math.max(10, Math.floor((b.width - 24) / 6.6)), caption = '↗ ' + (title.length > limit ? title.slice(0, limit - 1) + '…' : title), stroke = str(styled(node, 'symbol.color', '#42689f'));
        const primitives = [...node.item.primitives, box(footer, str(styled(node, 'symbol.fill', '#edf3fb')), stroke, 1), label(caption, footer.x + 10, footer.y + 19, 12, stroke)];
        return { ...node, item: { ...node.item, bounds: { ...b, height: b.height + 28 }, primitives, hitTargets: node.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, height: hit.bounds.height + 28 } })), accessible: { ...node.item.accessible, description: 'Reference to ' + title } } };
    });
    const mindmapProfile = str(view.record.profile) === 'mindmap.basic@1';
    const layout = object(effective?.layout ?? view.record.layout), root = resolveRecord(all, layout.root, view.file), regions = array(view.record.regions).map(object);
    const settings = { algorithm: str(layout.algorithm, str(view.record.profile) === 'mindmap.basic@1' ? 'mindmap' : 'grid'), gap: num(layout.gap, 64), row_gap: num(layout.row_gap, 64), columns: num(layout.columns, 3), direction: str(layout.direction, 'right'), width: frame.width, height: frame.height, mindmapProfile, ...(root ? { root: refKey(root.ref) } : {}) };
    if (settings.algorithm === 'auto')
        settings.algorithm = str(view.record.profile) === 'mindmap.basic@1' ? 'mindmap' : edges.length ? 'layered' : 'grid';
    const layoutNodes = mindmapProfile ? [...nodes.filter(node => node.mindmapTopic !== false && isMindmapTopic(node.definition.record)), ...nodes.filter(node => node.mindmapTopic === false || !isMindmapTopic(node.definition.record))] : nodes;
    const positions = graphLayout(layoutNodes.map(node => ({ id: node.item.occurrence, bounds: { ...node.item.bounds, x: node.item.bounds.x - frame.x, y: node.item.bounds.y - frame.y }, pinned: typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false, group: str(regions.find(region => array(region.members).some(ref => refKey(resolveRecord(all, ref, view.file)?.ref ?? { file: '', id: '' }) === refKey(node.definition.ref)))?.id, str(layout.group_by === 'role' ? pathValue(node.definition.record, 'metadata.x_record.layout_group') : undefined, str(pathValue(node.definition.record, str(layout.group_by, 'role')), str(node.definition.record.role)))) })), edges.flatMap(edge => { const a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all), side = pathValue(edge.appearance?.record, 'route.source_side'); return a && b && (!mindmapProfile || a.mindmapTopic !== false && b.mindmapTopic !== false && isMindmapTopic(a.definition.record) && isMindmapTopic(b.definition.record)) ? [{ from: a.item.occurrence, to: b.item.occurrence, ...(mindmapProfile && (side === 'west' || side === 'east') ? { side: side === 'west' ? 'left' : 'right' } : {}) }] : []; }), { ...settings, ...(root ? { root: nodes.find(node => refKey(node.definition.ref) === refKey(root.ref))?.item.occurrence ?? '' } : {}) });
    return nodes.map(node => {
        const local = positions.get(node.item.occurrence), bounds = { ...local, x: local.x + frame.x, y: local.y + frame.y }, dx = bounds.x - node.item.bounds.x, dy = bounds.y - node.item.bounds.y, m = node.item.transform;
        const primitives = [...node.item.primitives];
        return { ...node, item: { ...node.item, bounds, ...(node.item.clip ? { clip: { ...node.item.clip, x: node.item.clip.x + dx, y: node.item.clip.y + dy } } : {}), transform: [m[0], m[1], m[2], m[3], m[4] + dx, m[5] + dy], primitives, hitTargets: node.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, x: hit.bounds.x + dx, y: hit.bounds.y + dy } })) } };
    });
}
export function graphAdornments(entries, view, all, profile) {
    const nodes = entries.filter(e => e.definition.record.category !== 'relation'), output = [...entries];
    for (const owner of nodes.filter(node => node.definition.record.role === 'uml.package')) {
        const members = nodes.filter(node => { const target = resolveRecord(all, object(metadata(node.definition.record, 'x_pack')).package, node.definition.file); return target && refKey(target.ref) === refKey(owner.definition.ref); });
        if (!members.length)
            continue;
        const content = [owner, ...members].map(node => node.item.bounds), x = Math.min(...content.map(b => b.x)) - 22, y = Math.min(...content.map(b => b.y)) - 35, bounds = { x, y, width: Math.max(...content.map(b => b.x + b.width)) - x + 22, height: Math.max(...content.map(b => b.y + b.height)) - y + 22 };
        output.unshift(mark(owner, owner.definition, 'package-members', bounds, [box(bounds, 'none', '#94a3b8'), label('package ' + titleOf(owner.definition.record), x + 8, y + 19, 12)], 'Package frame for explicit x_pack.package ownership'));
    }
    const regionBounds = new Map(), regions = array(view.record.regions).map(object);
    const selection = (region) => {
        const members = array(region.members).map(ref => resolveRecord(all, ref, view.file)).filter((r) => !!r), scope = resolveRecord(all, region.scope, view.file);
        return nodes.filter(n => members.some(m => refKey(m.ref) === refKey(n.definition.ref)) || object(metadata(n.definition.record, 'x_partition')).lane === region.id || scope && refKey(scope.ref) === refKey(n.definition.ref));
    };
    const regionBox = (region, trail = new Set()) => {
        const id = str(region.id), cached = regionBounds.get(id);
        if (cached)
            return cached;
        const next = new Set(trail);
        next.add(id);
        const selected = selection(region).map(n => n.item.bounds), childBoxes = trail.size < 32 ? regions.filter(child => child.parent === id && !next.has(str(child.id))).map(child => regionBox(child, next)) : [];
        const content = [...selected, ...childBoxes], explicit = object(region.bounds), minX = content.length ? Math.min(...content.map(b => b.x)) : 50, minY = content.length ? Math.min(...content.map(b => b.y)) : 90;
        const fallback = content.length ? { x: minX - 30, y: minY - 40, width: Math.max(...content.map(b => b.x + b.width)) - minX + 60, height: Math.max(...content.map(b => b.y + b.height)) - minY + 70 } : { x: 20, y: 50, width: 350, height: 220 };
        const b = { x: num(explicit.x, fallback.x), y: num(explicit.y, fallback.y), width: num(explicit.width, fallback.width), height: num(explicit.height, fallback.height) };
        regionBounds.set(id, b);
        return b;
    };
    for (const region of regions) {
        const role = str(region.role), id = str(region.id), selected = selection(region), b = regionBox(region), scope = resolveRecord(all, region.scope, view.file);
        // The subject itself already owns its boundary and title.
        if (scope?.record.role === 'uml.subject' && selected.some(n => refKey(n.definition.ref) === refKey(scope.ref)))
            continue;
        const anchor = nodes.find(n => scope && refKey(n.definition.ref) === refKey(scope.ref)) ?? nodes[0];
        if (!anchor)
            continue;
        const dashed = /region|interruptible|parallel/.test(role), ps = [box(b, 'none', '#64748b', 1.2, dashed ? '7 5' : undefined), label(str(region.name, id), b.x + 9, b.y + 20, 13, '#334155', { 'font-weight': 600 })];
        if (/pool|lane|partition/.test(role))
            ps.push(line([b.x + 25, b.y + 28], [b.x + b.width, b.y + 28], '#94a3b8', 1));
        if (/expansion/.test(role))
            for (let i = 0; i < 3; i++)
                ps.push(box({ x: b.x + 24 + i * 14, y: b.y - 6, width: 12, height: 12 }, '#fff', '#475569'));
        const marked = mark(anchor, scope ?? view, 'region:' + id, b, ps, `Scoped ${role || 'frame'}; ${selected.length} selected members`);
        output.unshift({ ...marked, item: { ...marked.item, layer: 'frames' } });
    }
    for (const edge of entries.filter(e => e.definition.record.category === 'relation')) {
        const m = object(edge.definition.record.metadata), a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all);
        if (!a || !b)
            continue;
        const mid = [(center(a.item.bounds)[0] + center(b.item.bounds)[0]) / 2, (center(a.item.bounds)[1] + center(b.item.bounds)[1]) / 2];
        const associationClass = resolveRecord(all, object(m.x_association_class).class, edge.definition.file), classNode = associationClass && nodes.find(n => refKey(n.definition.ref) === refKey(associationClass.ref));
        if (classNode)
            output.push(mark(edge, edge.definition, 'association-class', finiteBounds(mid, center(classNode.item.bounds)), [line(mid, center(classNode.item.bounds), '#64748b', 1, '5 4')], 'Association-class connector'));
        const genset = object(m.x_genset);
        if (genset.name)
            output.push(mark(edge, edge.definition, 'generalization-set', { x: mid[0], y: mid[1] + 12, width: 210, height: 22 }, [label(`${str(genset.name)} {${genset.disjoint ? 'disjoint' : 'overlapping'}, ${genset.complete ? 'complete' : 'incomplete'}}`, mid[0], mid[1] + 27, 10)], 'Generalization-set annotation'));
        const extras = array(object(m.x_nary).ends), participants = [a, b, ...extras.map(end => { const ref = resolveRecord(all, object(end).element, edge.definition.file); return ref && nodes.find(node => refKey(node.definition.ref) === refKey(ref.ref)); }).filter((e) => !!e)];
        if (extras.length && participants.length > 2) {
            const x = participants.reduce((sum, node) => sum + center(node.item.bounds)[0], 0) / participants.length, y = participants.reduce((sum, node) => sum + center(node.item.bounds)[1], 0) / participants.length, ps = participants.map(node => line([x, y], center(node.item.bounds)));
            ps.push(polygon([[x, y - 14], [x + 14, y], [x, y + 14], [x - 14, y]], '#fff'));
            extras.forEach((end, i) => {
                const p = participants[i + 2];
                if (p)
                    ps.push(label([object(end).role, object(end).multiplicity].filter(Boolean).join(' '), (x + center(p.item.bounds)[0]) / 2, (y + center(p.item.bounds)[1]) / 2 - 4, 11));
            });
            const idx = output.indexOf(edge);
            if (idx >= 0)
                output[idx] = changed(edge, { x: x - 20, y: y - 20, width: 40, height: 40 }, ps, `N-ary association, ${participants.length} participant ends`);
        }
        if (m.x_fragment && /communication|c4.dynamic/.test(profile)) {
            const f = object(m.x_fragment), selected = array(f.operands).flatMap(v => array(object(v).messages)).map(ref => resolveRecord(all, ref, edge.definition.file)).filter((r) => !!r);
            const ys = entries.filter(e => selected.some(r => refKey(r.ref) === refKey(e.definition.ref))).map(e => e.item.bounds);
            if (ys.length) {
                const x = Math.min(...ys.map(b => b.x)) - 20, y = Math.min(...ys.map(b => b.y)) - 30, bounds = { x, y, width: Math.max(...ys.map(b => b.x + b.width)) - x + 20, height: Math.max(...ys.map(b => b.y + b.height)) - y + 20 };
                const ps = [box(bounds, 'none', '#64748b'), label(str(f.operator), x + 5, y + 18, 12)];
                array(f.operands).forEach((value, i) => { const operand = object(value), yy = y + 36 + i * 22; if (operand.guard)
                    ps.push(label('[' + str(operand.guard) + ']', x + 10, yy, 11)); });
                output.unshift(mark(edge, edge.definition, 'communication-fragment', bounds, ps, 'Combined fragment around declared communication messages'));
            }
        }
    }
    return output;
}
export function inlineInteractions(snapshot, view, input, all, options, diagnostics, unavailable, fallback, supportsFallback) {
    const output = [...input], chain = [...options.ancestors ?? [], refKey(view.ref)];
    for (const node of input.filter(entry => entry.definition.record.category !== 'relation')) {
        const metadataValue = object(metadata(node.definition.record, 'x_subdiagram'));
        if (!metadataValue.view || !['inline', 'thumbnail'].includes(str(metadataValue.display, str(view.record.profile) === 'uml.interaction_overview@2' ? 'inline' : 'collapsed')))
            continue;
        const name = str(metadataValue.view), split = name.lastIndexOf('::'), file = split < 0 ? node.definition.file : name.slice(0, split), id = split < 0 ? name : name.slice(split + 2);
        const target = resolveRecord(all, metadataValue.view, node.definition.file) ?? all.find(record => record.owner === 'view' && (record.file === file && (record.ref.id === id || record.record.name === id) || record.file === node.definition.file && (record.ref.id === name || record.record.name === name)));
        if (metadataValue.frozen) {
            const snapshotName = str(metadataValue.snapshot), separator = snapshotName.lastIndexOf('::'), snapshotFile = separator < 0 ? node.definition.file : snapshotName.slice(0, separator), snapshotKey = separator < 0 ? snapshotName : snapshotName.slice(separator + 2);
            const asset = all.find(record => record.owner === 'asset' && record.file === snapshotFile && (record.ref.id === snapshotKey || record.record.name === snapshotKey || record.record.path === snapshotKey));
            if (asset && str(asset.record.media_type).startsWith('image/')) {
                const b = node.item.bounds, width = Math.max(b.width, metadataValue.display === 'thumbnail' ? 260 : 600), height = Math.max(b.height, metadataValue.display === 'thumbnail' ? 180 : 400);
                output[output.indexOf(node)] = changed(node, { ...b, width, height }, [box({ ...b, width, height }, '#fff', '#64748b'), label('Frozen ' + (str(metadataValue.snapshot_at) || name), b.x + 10, b.y + 23, 12), { kind: 'image', assetId: refKey(asset.ref), bounds: { x: b.x + 10, y: b.y + 35, width: width - 20, height: height - 45 } }], 'Declared frozen image artifact; loaded through the host asset pipeline');
                continue;
            }
            diagnostics.push({ code: 'inline-snapshot-unavailable', severity: 'warning', message: 'Frozen inline display requires a supplied, declared image snapshot asset.', target: node.definition.ref });
            unavailable.push('inline-snapshot:' + refKey(node.definition.ref));
            continue;
        }
        const problem = !target ? 'Referenced view is unavailable.' : chain.includes(refKey(target.ref)) || chain.length > 8 ? 'Recursive inline view expansion exceeds its bounded scope.' : !supportsFallback?.(str(target.record.profile)) && !options.projectInline ? 'Referenced view needs an installed inline projection adapter.' : undefined;
        if (problem) {
            diagnostics.push({ code: 'inline-view-unavailable', severity: 'warning', message: problem, target: node.definition.ref });
            unavailable.push('inline:' + refKey(node.definition.ref));
            continue;
        }
        const selected = array(pathValue(target.record, 'selection.include')).map(ref => resolveRecord(all, ref, target.file)).filter((record) => !!record);
        const appearances = all.filter(record => record.owner === 'appearance' && refKey(resolveRecord(all, record.record.parent, record.file)?.ref ?? { file: '', id: '' }) === refKey(target.ref));
        const candidates = appearances.length ? appearances.map(appearance => ({ definition: resolveRecord(all, appearance.record.target, appearance.file), appearance })) : selected.map(definition => ({ definition, appearance: undefined }));
        const childEntries = [];
        for (const [index, candidate] of candidates.entries()) {
            if (!candidate.definition)
                continue;
            const position = object(candidate.appearance?.record.position), size = object(candidate.appearance?.record.size), bounds = { x: num(position.x, 30 + index % 3 * 260), y: num(position.y, 60 + Math.floor(index / 3) * 160), width: num(size.width, 220), height: num(size.height, 72) }, occurrence = node.item.occurrence + ':inline-source:' + (candidate.appearance?.ref.id ?? candidate.definition.ref.id);
            childEntries.push({ ...node, definition: candidate.definition, view: target, ...(candidate.appearance ? { appearance: candidate.appearance } : {}), effective: candidate.definition.record, item: { ...node.item, occurrence, target: candidate.definition.ref, view: target.ref, bounds, primitives: [], hitTargets: [{ id: occurrence, target: candidate.definition.ref, bounds }], transform: identity } });
        }
        const nodes = childEntries.filter(entry => entry.definition.record.category !== 'relation');
        for (const relation of all.filter(record => record.owner === 'definition' && record.record.category === 'relation')) {
            if (childEntries.some(entry => refKey(entry.definition.ref) === refKey(relation.ref)))
                continue;
            const ends = array(relation.record.endpoints).map(end => resolveRecord(all, object(end).definition, relation.file));
            if (ends.length < 2 || ends.some(end => !end || !nodes.some(node => refKey(node.definition.ref) === refKey(end.ref))))
                continue;
            childEntries.push({ ...node, definition: relation, view: target, effective: relation.record, item: { ...node.item, occurrence: node.item.occurrence + ':inline-source:' + relation.ref.id, target: relation.ref, view: target.ref, primitives: [], transform: identity } });
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
        output[idx] = changed(node, { ...b, width, height }, [box({ ...b, width, height }, '#fff', '#64748b'), label('ref ' + titleOf(target.record), b.x + 10, b.y + 23, 13), label('↗ inline', b.x + width - 76, b.y + 23, 11), label(array(object(metadata(node.definition.record, 'x_use')).arguments).length ? '(' + array(object(metadata(node.definition.record, 'x_use')).arguments).map(String).join(', ') + ')' : '', b.x + 10, b.y + 36, 11)], 'Inline referenced interaction; original source identities retained');
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
//# sourceMappingURL=graph-common.js.map