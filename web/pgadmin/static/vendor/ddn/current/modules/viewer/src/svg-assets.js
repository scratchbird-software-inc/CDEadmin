// SVG artwork remains an inert, self-contained image. Only presentation styles
// are copied into attributes; stylesheet rules and executable content are not.
const elements = new Set(['svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'defs', 'linearGradient', 'radialGradient', 'stop', 'clipPath', 'mask', 'pattern', 'title', 'desc', 'use']);
const presentation = new Set([
    'color', 'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-opacity', 'stroke-width',
    'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset',
    'opacity', 'stop-color', 'stop-opacity', 'flood-color', 'flood-opacity', 'display', 'visibility', 'overflow',
    'clip-path', 'clip-rule', 'mask', 'filter', 'marker', 'marker-start', 'marker-mid', 'marker-end',
    'font-family', 'font-size', 'font-style', 'font-weight', 'font-variant', 'letter-spacing', 'word-spacing',
    'text-anchor', 'text-decoration', 'dominant-baseline', 'alignment-baseline', 'paint-order', 'vector-effect',
    'shape-rendering', 'text-rendering', 'color-interpolation', 'color-interpolation-filters',
]);
function safePaint(value) {
    // Reject escape/variable indirection and all non-local resource references.
    if (/[\\{}<>@\u0000-\u001f]/.test(value) || /\/\*|\*\//.test(value))
        return undefined;
    if (/url\s*\(/i.test(value)) {
        const match = /^url\(\s*(?:"(#[a-zA-Z0-9_.:-]+)"|'(#[a-zA-Z0-9_.:-]+)'|(#[a-zA-Z0-9_.:-]+))\s*\)$/i.exec(value);
        return match ? 'url(' + (match[1] ?? match[2] ?? match[3]) + ')' : undefined;
    }
    for (const call of value.matchAll(/([a-zA-Z_-][a-zA-Z0-9_-]*)\s*\(/g))
        if (!['rgb', 'rgba', 'hsl', 'hsla'].includes(call[1].toLowerCase()))
            return undefined;
    return value;
}
/** Preserve a bounded SVG paint vocabulary without retaining arbitrary CSS. */
export function sanitizeSvgAsset(svgDocument, hostDocument) {
    // The detached declaration block supplies CSS quoting, duplicate and
    // !important precedence. It never creates a rendered resource request.
    const parsed = hostDocument.createElement('span').style;
    for (const node of [svgDocument.documentElement, ...Array.from(svgDocument.querySelectorAll('*'))]) {
        if (!elements.has(node.localName)) {
            node.remove();
            continue;
        }
        parsed.cssText = node.getAttribute('style') ?? '';
        for (let index = 0; index < parsed.length; index++) {
            const name = parsed.item(index);
            if (!presentation.has(name))
                continue;
            const value = safePaint(parsed.getPropertyValue(name).trim());
            if (value !== undefined)
                node.setAttribute(name, value);
        }
        for (const attribute of Array.from(node.attributes)) {
            const name = attribute.localName, value = attribute.value;
            if (/^on/i.test(name) || name === 'style' || name === 'src' || name === 'base' ||
                (name === 'href' && !/^#[a-zA-Z0-9_.:-]+$/.test(value)) ||
                (presentation.has(name) && safePaint(value) === undefined) ||
                (/url\s*\(/i.test(value) && safePaint(value) === undefined))
                node.removeAttributeNode(attribute);
        }
    }
}
//# sourceMappingURL=svg-assets.js.map