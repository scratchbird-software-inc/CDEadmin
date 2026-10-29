import { num, str, pathValue } from './model.js';
/** Retained chart depth treatment. Top faces keep their quantitative geometry;
 * oblique side faces carry no additional data values or selectable identities. */
export function extrudeChart(result, settings, depths = new Map()) {
    if (settings.iso !== true || result.unavailable.length)
        return result;
    const mark = str(settings.mark, 'bar');
    if (!['bar', 'area', 'pie', 'donut', 'treemap'].includes(mark))
        return result;
    let maximumDepth = 0;
    const sides = [];
    for (const entry of result.entries) {
        if (entry.definition.owner === 'view')
            continue;
        const depth = depths.get(entry.item.occurrence) ?? (typeof settings.depth === 'string' ? num(pathValue(entry.definition.record, settings.depth), 0) : num(settings.depth, 18));
        if (depth === 0)
            continue;
        maximumDepth = Math.max(maximumDepth, depth);
        const dx = depth * Math.sqrt(3) / 2, dy = -depth / 2;
        const filled = entry.item.primitives.filter(primitive => primitive.kind !== 'text' && primitive.kind !== 'image' && primitive.paint?.fill && primitive.paint.fill !== 'none' && primitive.paint.fill !== 'transparent');
        const rectangles = filled.filter((primitive) => primitive.kind === 'rect');
        if (rectangles.length) {
            const primitives = rectangles.map(primitive => {
                const b = primitive.bounds, x = b.x, y = b.y, right = x + b.width, bottom = y + b.height;
                return { kind: 'path', d: `M${x},${y}L${x + dx},${y + dy}L${right + dx},${y + dy}L${right + dx},${bottom + dy}L${right},${bottom}L${x},${bottom}Z`, paint: { ...primitive.paint, fill: shade(str(primitive.paint?.fill)), stroke: 'none' } };
            });
            sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth', hitTargets: [], primitives, bounds: { ...entry.item.bounds, y: entry.item.bounds.y + dy, width: entry.item.bounds.width + dx, height: entry.item.bounds.height - dy }, accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
        }
        const curves = filled.filter((primitive) => primitive.kind === 'path' || primitive.kind === 'ellipse');
        if (mark === 'area') {
            // An area chart gets a narrow ribbon along its measured upper edge.
            // Extruding whole translucent areas repeatedly would darken the fill.
            for (const primitive of curves) {
                if (primitive.kind !== 'path')
                    continue;
                const numbers = primitive.d.match(/[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/gi)?.map(Number) ?? [];
                const points = Array.from({ length: numbers.length / 4 }, (_, i) => [numbers[i * 2], numbers[i * 2 + 1]]);
                if (!points.length)
                    continue;
                const ribbon = [...points, ...[...points].reverse().map(([x, y]) => [x + dx, y + dy])];
                const side = { kind: 'path', d: 'M' + ribbon.map(point => point.join(',')).join('L') + 'Z', paint: { fill: shade(str(primitive.paint.fill)), stroke: 'none', 'fill-opacity': .65, opacity: primitive.paint.opacity ?? 1 } };
                sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth', hitTargets: [], primitives: [side], bounds: { ...entry.item.bounds, y: entry.item.bounds.y + dy, width: entry.item.bounds.width + dx, height: entry.item.bounds.height - dy }, accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
            }
            continue;
        }
        // A bounded stack fills curved walls without approximating or changing
        // the authored top-face arc, area shape or donut hole.
        if (curves.length)
            for (let step = 12; step >= 1; step--) {
                const m = entry.item.transform, amount = step / 12;
                sides.push({ ...entry, item: { ...entry.item, occurrence: entry.item.occurrence + ':depth:' + step, hitTargets: [], transform: [m[0], m[1], m[2], m[3], m[4] + dx * amount, m[5] + dy * amount], primitives: curves.map(primitive => ({ ...primitive, paint: { ...primitive.paint, fill: shade(str(primitive.paint?.fill)), stroke: 'none' } })), accessible: { ...entry.item.accessible, label: entry.item.accessible.label + ' depth face' } } });
            }
    }
    // Axes stay behind walls, and all top faces stay above every wall.
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
//# sourceMappingURL=data-isometric.js.map