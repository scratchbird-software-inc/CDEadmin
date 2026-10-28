import { num, pathValue } from './model.js';
const ground = [Math.sqrt(3) / 2, .5, -Math.sqrt(3) / 2, .5, 0, 0];
const inverse = (m) => { const d = m[0] * m[3] - m[1] * m[2]; return [m[3] / d, -m[1] / d, -m[2] / d, m[0] / d, (m[2] * m[5] - m[3] * m[4]) / d, (m[1] * m[4] - m[0] * m[5]) / d]; };
const compose = (a, b) => [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]];
function transformed(b, m) {
    const points = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].map(([x, y]) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]);
    const x = Math.min(...points.map(p => p[0])), y = Math.min(...points.map(p => p[1]));
    return { x, y, width: Math.max(...points.map(p => p[0])) - x, height: Math.max(...points.map(p => p[1])) - y };
}
/** Isometric graph is a presentation of the existing flat layout. Identities,
 * routes and authored coordinates stay unchanged; depth is purely visual. */
export function isometricGraph(entries, frame, defaultDepth) {
    if (!entries.length)
        return [];
    const projected = entries.map(entry => {
        const relation = entry.definition.record.category === 'relation' || entry.definition.owner === 'view' || entry.item.layer === 'views' || /:(region|package|subject|fragment):/.test(entry.item.occurrence);
        const depth = relation ? 0 : Math.max(0, Math.min(2000, num(pathValue(entry.effective, 'properties.depth'), num(pathValue(entry.definition.record, 'properties.depth'), defaultDepth))));
        const matrix = [ground[0], ground[1], ground[2], ground[3], 0, -depth];
        const top = transformed(entry.item.bounds, matrix);
        return { entry, depth, matrix, bounds: { ...top, height: top.height + depth } };
    });
    const dx = frame.x + 24 - Math.min(...projected.map(p => p.bounds.x)), dy = frame.y + 60 - Math.min(...projected.map(p => p.bounds.y));
    return projected.sort((a, b) => Number(b.entry.definition.record.category === 'relation') - Number(a.entry.definition.record.category === 'relation') || a.bounds.y - b.bounds.y).map(({ entry, depth, matrix, bounds }) => {
        const local = inverse(entry.item.transform);
        const semantic = entry.item.hitTargets.find(hit => hit.target.file === entry.item.target.file && hit.target.id === entry.item.target.id)?.bounds ?? entry.item.bounds;
        const { x, y, width: w, height: h } = transformed(semantic, local);
        const ex = (local[0] + local[2]) * depth, ey = (local[1] + local[3]) * depth;
        const faces = depth ? [
            { kind: 'path', d: `M${x + w},${y}L${x + w + ex},${y + ey}L${x + w + ex},${y + h + ey}L${x + w},${y + h}Z`, paint: { fill: '#aac2d0', stroke: '#64748b', 'stroke-width': 1 } },
            { kind: 'path', d: `M${x},${y + h}L${x + ex},${y + h + ey}L${x + w + ex},${y + h + ey}L${x + w},${y + h}Z`, paint: { fill: '#c9dae3', stroke: '#64748b', 'stroke-width': 1 } },
        ] : [];
        const placed = [matrix[0], matrix[1], matrix[2], matrix[3], dx, dy - depth];
        const itemBounds = { ...bounds, x: bounds.x + dx, y: bounds.y + dy };
        return { ...entry, item: { ...entry.item, bounds: itemBounds, ...(entry.item.clip ? { clip: transformed(entry.item.clip, placed) } : {}), transform: compose(placed, entry.item.transform), primitives: [...faces, ...entry.item.primitives], hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: transformed(hit.bounds, placed) })), accessible: { ...entry.item.accessible, description: [entry.item.accessible.description, depth ? `isometric depth ${depth}` : 'isometric ground route'].filter(Boolean).join('; ') } } };
    });
}
//# sourceMappingURL=graph-isometric.js.map