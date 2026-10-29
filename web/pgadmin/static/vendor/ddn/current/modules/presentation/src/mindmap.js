import { isMindmapTopic, mindmapKey, mindmapRelationKind } from '../../profiles/src/mindmap.js';
import { roleDescriptor } from '../../profiles/src/core.js';
import { array, object, pathValue, str, num, refKey } from './model.js';
import { endEntry, endpoint, center, changed, finiteBounds, cubicPoints, routeIntersects, decorateEdge, styled } from './graph-common.js';
import { path, sketchPrimitive } from './graph-glyphs.js';
const topicBounds = (entry) => entry.item.hitTargets.find(hit => refKey(hit.target) === refKey(entry.definition.ref))?.bounds ?? entry.item.bounds;
/** Endpoint ordering is a presentation property. It never rewrites the semantic
 * parent direction or adds junctions where several branches leave a topic. */
export function mindmapEdges(edges, nodes, all, frame, viewProperties, diagnostics, unavailable) {
    const topics = new Set(nodes.filter(node => node.mindmapTopic !== false && isMindmapTopic(node.definition.record)).map(node => mindmapKey(node.definition)));
    const connections = edges.map(edge => {
        const from = endEntry(edge, 0, nodes, all), to = endEntry(edge, 1, nodes, all);
        return { edge, from, to, internal: mindmapRelationKind(from?.definition, to?.definition, topics) === 'internal' };
    });
    const outward = new Map(), parents = new Map();
    for (const connection of connections)
        if (connection.internal && connection.to)
            parents.set(connection.to.item.occurrence, connection);
    const branchSide = (connection) => {
        const authored = pathValue(connection.edge.appearance?.record, 'route.source_side');
        if (authored === 'west' || authored === 'east')
            return authored === 'west' ? -1 : 1;
        return center(topicBounds(connection.to))[0] < center(topicBounds(connection.from))[0] ? -1 : 1;
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
    // One visit per topic, even when source declarations run leaf-to-root.
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
            rootKeys.delete(mindmapKey(connection.to.definition));
    const uniqueRoot = rootKeys.size === 1 ? [...rootKeys][0] : undefined;
    const ports = new Map();
    for (const connection of connections) {
        if (!connection.from || !connection.to)
            continue;
        for (const at of [0, 1]) {
            const node = at === 0 ? connection.from : connection.to, other = at === 0 ? connection.to : connection.from;
            if (!topics.has(mindmapKey(node.definition)))
                continue;
            const authored = pathValue(connection.edge.appearance?.record, at === 0 ? 'route.source_side' : 'route.target_side');
            const vertical = at === 1 && !connection.internal && uniqueRoot === mindmapKey(node.definition) && !topics.has(mindmapKey(other.definition)) && (authored === 'north' || authored === 'south');
            const direction = outward.get(node.item.occurrence), side = vertical ? (authored === 'north' ? -1 : 1) : direction === undefined ? (authored === 'west' ? -1 : authored === 'east' ? 1 : center(topicBounds(other))[0] < center(topicBounds(node))[0] ? -1 : 1) : at === 0 ? direction : -direction;
            const key = node.item.occurrence + ':' + (vertical ? 'vertical:' : 'horizontal:') + side, list = ports.get(key) ?? [];
            list.push({ connection, at, node, side, vertical, otherY: center(topicBounds(other))[vertical ? 0 : 1] });
            ports.set(key, list);
            if (!vertical && (authored === 'north' || authored === 'south'))
                diagnostics.push({ code: 'mindmap-horizontal-attachment', severity: 'warning', target: connection.edge.definition.ref, message: 'Mind-map topics attach on the left or right; the authored top/bottom attachment is ignored.' });
            else if (authored === 'west' && side > 0 || authored === 'east' && side < 0) {
                diagnostics.push({ code: 'mindmap-attachment-conflict', severity: 'warning', target: connection.edge.definition.ref, message: 'The authored attachment conflicts with the incoming/outgoing sides of this mind-map topic.' });
                unavailable.push('mindmap-attachment:' + refKey(connection.edge.definition.ref));
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
            const route = { ...object(edge.appearance?.record.route), routing: 'curved' };
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
                const decorated = decorateEdge({ ...edge, appearance: { ...occurrence, record: { ...occurrence.record, route: current } } }, nodes, all, 'mindmap.basic@1', frame, obstacles, labels, tracks, 'none', viewProperties, { ...(connection.a ? { source: connection.a, sourceDirection: normal(connection.a, from) } : {}), ...(connection.b ? { target: connection.b, targetDirection: normal(connection.b, to) } : {}), horizontal: true });
                return { decorated, points: tracks.at(-1), labels };
            };
            const clear = (points) => {
                const interior = [...points];
                if (interior.length > 1)
                    for (const [at, neighbour] of [[0, 1], [interior.length - 1, interior.length - 2]]) {
                        const p = points[at], q = points[neighbour], distance = Math.max(1, Math.hypot(q[0] - p[0], q[1] - p[1]));
                        interior[at] = [p[0] + (q[0] - p[0]) * .01 / distance, p[1] + (q[1] - p[1]) * .01 / distance];
                    }
                return !nodes.some(node => { const b = topicBounds(node); return node === from || node === to ? routeIntersects(interior, { x: b.x + .1, y: b.y + .1, width: b.width - .2, height: b.height - .2 }) : routeIntersects(points, b); }) && !prior.some(track => routesCross(points, track));
            };
            let chosen = render(), clearRoute = clear(chosen.points);
            if (!clearRoute && !array(route.via).length) {
                const a = connection.a ?? endpoint(edge, 0, from, to, all), b = connection.b ?? endpoint(edge, 1, to, from, all);
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
                unavailable.push('mindmap-route:' + refKey(edge.definition.ref));
            }
            prior.push(chosen.points);
            reserved.splice(0, reserved.length, ...chosen.labels);
            const { appearance: _appearance, ...result } = chosen.decorated;
            output.set(edge, { ...result, ...(edge.appearance ? { appearance: edge.appearance } : {}) });
            continue;
        }
        const a = connection.a, b = connection.b, direction = a[0] === topicBounds(from).x ? -1 : 1;
        const reach = Math.max(24, Math.abs(b[0] - a[0]) / 2), c1 = [a[0] + direction * reach, a[1]], c2 = [b[0] - direction * reach, b[1]];
        const points = cubicPoints(a, c1, c2, b);
        const blocked = constrained && nodes.some(node => node !== from && node !== to && routeIntersects(points, topicBounds(node)));
        const crossed = constrained && prior.some(route => routesCross(points, route));
        if (blocked || crossed || direction * (b[0] - a[0]) <= 0) {
            diagnostics.push({ code: 'mindmap-route-conflict', severity: 'warning', target: edge.definition.ref, message: 'Pinned topic positions prevent a clear outward mind-map branch. Move or unpin the affected topics.' });
            unavailable.push('mindmap-route:' + refKey(edge.definition.ref));
        }
        prior.push(points);
        const defaults = roleDescriptor('assoc', 'relation')?.render ?? {}, stroke = str(styled(edge, 'stroke.color', defaults.colour), '#475569'), weight = num(styled(edge, 'stroke.weight', styled(edge, 'stroke.width', defaults.width)), 1.5);
        const dash = styled(edge, 'stroke.dash', defaults.pattern ?? ''), pattern = Array.isArray(dash) ? dash.join(' ') : dash === 'dotted' ? '2 3' : dash === 'dashed' ? '6 4' : typeof dash === 'string' && dash !== 'solid' ? dash : undefined;
        const line = path(`M${a[0]},${a[1]}C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${b[0]},${b[1]}`, 'none', stroke, weight, pattern);
        const primitives = [str(styled(edge, 'style.look', pathValue(viewProperties, 'style.look'))) === 'handdrawn' ? sketchPrimitive(line, num(pathValue(edge.effective, 'style.seed'), 42), num(pathValue(edge.effective, 'style.roughness'), 1)) : line];
        output.set(edge, changed(edge, finiteBounds([Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1]))], [Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))], 8), primitives, 'Mind-map branch'));
    }
    return connections.map(connection => output.get(connection.edge));
}
/** Proper interior intersections; touching endpoints are not crossovers. */
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
//# sourceMappingURL=mindmap.js.map