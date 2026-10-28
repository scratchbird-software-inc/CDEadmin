const ns = 'http://www.w3.org/2000/svg';
const color = (value, fallback) => typeof value === 'string' && /^(?:transparent|#[\da-f]{3}|#[\da-f]{6}|#[\da-f]{8})$/i.test(value) ? value : fallback;
const number = (value, fallback, low, high) => typeof value === 'number' && Number.isFinite(value) ? Math.min(high, Math.max(low, value)) : fallback;
const rounded = (value) => Number(value.toFixed(3));
/** Null/absence is off; an empty record selects the versioned paper defaults. */
export function normalizeTexture(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        return;
    const source = value, kind = source.kind ?? 'paper';
    if (!['paper', 'linen', 'grid', 'dots'].includes(String(kind)))
        return;
    return { kind: kind, color: color(source.color, '#725d43'), opacity: number(source.opacity, .12, 0, 1), scale: number(source.scale, 32, 4, 128), seed: Math.floor(number(source.seed, 1, 0, 2147483647)) };
}
function shapes(settings, baseFill) {
    const result = [{ tag: 'rect', attributes: { width: 64, height: 64, fill: color(baseFill, 'transparent') } }];
    if (!settings.opacity || settings.color === 'transparent')
        return result;
    let state = settings.seed >>> 0;
    const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
    const stroke = (d, width, opacity) => result.push({ tag: 'path', attributes: { d, fill: 'none', stroke: settings.color, 'stroke-width': width, 'stroke-linecap': 'round', opacity: rounded(settings.opacity * opacity) } });
    if (settings.kind === 'grid') {
        // Half-width inset avoids a clipped half-stroke at either tile edge.
        stroke('M.5 64V.5H64', 1, 1);
    }
    else if (settings.kind === 'dots') {
        result.push({ tag: 'circle', attributes: { cx: 32, cy: 32, r: 1.8, fill: settings.color, opacity: settings.opacity } });
    }
    else if (settings.kind === 'linen') {
        for (let direction = 0; direction < 2; direction++) {
            let threads = '', weave = '';
            for (let line = 0; line < 8; line++) {
                const position = rounded(line * 8 + 2 + random());
                threads += direction ? `M0 ${position}H64` : `M${position} 0V64`;
                for (let cross = 0; cross < 8; cross++)
                    if ((line + cross + direction) % 2 === 0) {
                        const start = cross * 8 + 1;
                        weave += direction ? `M${start} ${position}h5` : `M${position} ${start}v5`;
                    }
            }
            stroke(threads, 1.1, .52);
            stroke(weave, 1.9, .48);
        }
    }
    else {
        // Grain and fibres are batched into six paths, independent of surface
        // size. Wrapped copies avoid seams without runtime SVG filters.
        const grain = ['', '', ''], fibres = ['', '', ''];
        for (let index = 0; index < 84; index++) {
            const x = rounded(random() * 64), y = rounded(random() * 64);
            grain[index % 3] += `M${x} ${y}h.12`;
        }
        for (let index = 0; index < 18; index++) {
            const x = random() * 64, y = random() * 64, length = 3 + random() * 8, angle = random() * Math.PI * 2;
            const dx = Math.cos(angle) * length, dy = Math.sin(angle) * length, bend = (random() - .5) * 3;
            for (const ox of [-64, 0, 64])
                for (const oy of [-64, 0, 64]) {
                    const left = Math.min(x, x + dx, x + dx / 2 + bend) + ox, right = Math.max(x, x + dx, x + dx / 2 + bend) + ox;
                    const top = Math.min(y, y + dy, y + dy / 2 - bend) + oy, bottom = Math.max(y, y + dy, y + dy / 2 - bend) + oy;
                    if (right < 0 || left > 64 || bottom < 0 || top > 64)
                        continue;
                    fibres[index % 3] += `M${rounded(x + ox)} ${rounded(y + oy)}q${rounded(dx / 2 + bend)} ${rounded(dy / 2 - bend)} ${rounded(dx)} ${rounded(dy)}`;
                }
        }
        grain.forEach((d, index) => stroke(d, .45 + index * .3, .42 + index * .23));
        fibres.forEach((d, index) => stroke(d, .28 + index * .16, .4 + index * .2));
    }
    return result;
}
/** id is a renderer-owned identifier, never an authored resource reference. */
export function createTexturePattern(document, id, value, baseFill = 'transparent') {
    const settings = normalizeTexture(value);
    if (!settings || !/^[A-Za-z_][\w.-]*$/.test(id))
        return;
    const pattern = document.createElementNS(ns, 'pattern');
    for (const [key, entry] of Object.entries({ id, patternUnits: 'userSpaceOnUse', width: settings.scale, height: settings.scale, viewBox: '0 0 64 64', preserveAspectRatio: 'none' }))
        pattern.setAttribute(key, String(entry));
    for (const shape of shapes(settings, baseFill)) {
        const node = document.createElementNS(ns, shape.tag);
        for (const [key, entry] of Object.entries(shape.attributes))
            node.setAttribute(key, String(entry));
        pattern.appendChild(node);
    }
    return pattern;
}
/** SVG data is assembled solely from the closed, validated geometry above.
 * The returned image is already a CSS url(...) value; size is in logical px. */
export function textureBackground(value, baseFill = 'transparent') {
    const settings = normalizeTexture(value);
    if (!settings)
        return;
    const body = shapes(settings, baseFill).map(shape => `<${shape.tag} ${Object.entries(shape.attributes).map(([key, entry]) => `${key}="${entry}"`).join(' ')}/>`).join('');
    const svg = `<svg xmlns="${ns}" width="${settings.scale}" height="${settings.scale}" viewBox="0 0 64 64">${body}</svg>`;
    return { image: `url("data:image/svg+xml,${encodeURIComponent(svg)}")`, size: `${settings.scale}px ${settings.scale}px` };
}
//# sourceMappingURL=texture.js.map