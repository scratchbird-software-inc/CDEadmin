import { num, object } from './model.js';
const positive = (value) => typeof value === 'number' && Number.isFinite(value) && value > 0;
/** Null dimensions retain the existing content-sized view contract. */
export function fixedViewSurface(effective) {
    const surface = object(effective.surface);
    if (!positive(surface.width) || !positive(surface.height))
        return undefined;
    return { width: surface.width, height: surface.height, scale: positive(surface.scale) ? surface.scale : 1,
        padding: Math.max(0, num(surface.padding, 32)), fit: surface.fit === 'none' ? 'none' : 'contain' };
}
export function surfaceBounds(bounds, matrix) {
    return { x: bounds.x * matrix[0] + matrix[4], y: bounds.y * matrix[3] + matrix[5], width: bounds.width * matrix[0], height: bounds.height * matrix[3] };
}
function intersect(a, b) {
    const left = Math.max(a.x, b.x), top = Math.max(a.y, b.y);
    return { x: Math.max(b.x, Math.min(b.x + b.width, left)), y: Math.max(b.y, Math.min(b.y + b.height, top)), width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - left), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - top) };
}
function annotationsBounds(primitives, measure) {
    return primitives.flatMap(primitive => {
        if (primitive.kind !== 'text')
            return 'bounds' in primitive ? [primitive.bounds] : [];
        return primitive.runs.map(run => {
            const size = num(run.style['font-size'], 12), width = measure(run.text, size, run.fontKey);
            const shift = run.style['text-anchor'] === 'middle' ? width / 2 : run.style['text-anchor'] === 'end' ? width : 0;
            return { x: run.x - shift, y: run.y - size, width, height: size * 1.3 };
        });
    });
}
/** Fit logical diagram geometry, preserving its origin and explicit positions when
 * they already fit. Source positions stay logical; surfaceTransform exposes the
 * inverse mapping to editors without changing semantic coordinates. */
export function fitSurfaceContent(entries, annotations, surface, origin, chrome, measure) {
    const { width, height, scale: preferred, padding } = surface;
    const padX = Math.min(padding * preferred, width / 4), padY = Math.min(padding * preferred, height / 4);
    const header = (chrome.title !== false ? 64 : chrome.banner !== false ? 32 : 0) * preferred;
    const footer = chrome.footer !== false ? 30 * preferred : 0;
    const top = Math.min(height / 2, Math.max(padY, header));
    const bottom = Math.min(height / 4, Math.max(padY, footer));
    const drawable = { x: origin.x + padX, y: origin.y + top, width: Math.max(1, width - padX * 2), height: Math.max(1, height - top - bottom) };
    const logicalLeft = origin.x + padX / preferred, logicalTop = origin.y + top / preferred;
    const extents = [...entries.map(entry => entry.item.bounds), ...annotationsBounds(annotations, measure)];
    const left = Math.min(logicalLeft, ...extents.map(bounds => bounds.x)), upper = Math.min(logicalTop, ...extents.map(bounds => bounds.y));
    const right = Math.max(logicalLeft + 1, ...extents.map(bounds => bounds.x + bounds.width));
    const lower = Math.max(logicalTop + 1, ...extents.map(bounds => bounds.y + bounds.height));
    const factor = surface.fit === 'none' ? preferred : Math.min(preferred, drawable.width / (right - left), drawable.height / (lower - upper));
    const matrix = surface.fit === 'none' ? [factor, 0, 0, factor, origin.x * (1 - factor), origin.y * (1 - factor)]
        : [factor, 0, 0, factor, drawable.x - left * factor, drawable.y - upper * factor];
    const clipped = extents.some(bounds => {
        const b = surfaceBounds(bounds, matrix);
        return b.x < drawable.x - .01 || b.y < drawable.y - .01 || b.x + b.width > drawable.x + drawable.width + .01 || b.y + b.height > drawable.y + drawable.height + .01;
    });
    const transformed = entries.map(entry => {
        const item = entry.item, m = item.transform;
        const clip = intersect(item.clip ? surfaceBounds(item.clip, matrix) : drawable, drawable);
        return { ...entry, surfaceTransform: matrix, item: { ...item, bounds: intersect(surfaceBounds(item.bounds, matrix), drawable), clip,
                transform: [m[0] * factor, m[1] * factor, m[2] * factor, m[3] * factor, m[4] * factor + matrix[4], m[5] * factor + matrix[5]],
                hitTargets: item.hitTargets.map(hit => ({ ...hit, bounds: intersect(surfaceBounds(hit.bounds, matrix), drawable) })).filter(hit => hit.bounds.width > 0 && hit.bounds.height > 0) } };
    });
    // The pre-frame annotations are relationship-key and unsupported-profile text.
    const transformedAnnotations = annotations.map(primitive => primitive.kind === 'text'
        ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, x: run.x * factor + matrix[4], y: run.y * factor + matrix[5], style: { ...run.style, 'font-size': num(run.style['font-size'], 12) * factor } })) }
        : 'bounds' in primitive ? { ...primitive, bounds: surfaceBounds(primitive.bounds, matrix) } : primitive);
    return { entries: transformed, annotations: transformedAnnotations, matrix, drawable, clipped, bounds: { x: origin.x, y: origin.y, width, height } };
}
//# sourceMappingURL=view-surface.js.map