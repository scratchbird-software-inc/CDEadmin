/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-30b5187aadd6","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-6cf9d24a4527"],"modules":[{"id":"presentation/src/stationery.js","bytes":17617,"sha256":"191e81db7a0da7192e959f97cdf747e45f3c086d221b47cdd57f9cfd9c51017a","dependencies":["presentation/src/model.js"]}],"hash":"b0cc2743b6f16df38a75d3ec66411b32930b7fc47cb8a01d89f7310eef40d2bf"},{"presentation/src/stationery.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.decoratePaper = decoratePaper;
const model_js_1 = require("presentation/src/model.js");
const marker = 'ddn-decoration';
const finite = (value, fallback, min, max) => typeof value === 'number' && Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
const color = (value, fallback) => typeof value === 'string' && /^(?:transparent|#[\da-f]{3}|#[\da-f]{6}|#[\da-f]{8})$/i.test(value) ? value : fallback;
const defaults = { 'push-pin': '#df4545', 'round-pin': '#45a3da', 'paper-clip': '#5b83b4', 'binder-clip': '#3b414b', tape: '#e4c788' };
const p = (d, paint, category = 'paper') => ({ kind: 'path', d, paint: { ...paint, [marker]: category } });
const rounded = (n) => Number(n.toFixed(5));
function shade(value, amount) {
    if (value === 'transparent')
        return value;
    let hex = value.slice(1);
    if (hex.length === 3)
        hex = [...hex].map(c => c + c).join('');
    const channels = [0, 2, 4].map(offset => parseInt(hex.slice(offset, offset + 2), 16));
    return '#' + channels.map(channel => Math.round(amount >= 0 ? channel + (255 - channel) * amount : channel * (1 + amount)).toString(16).padStart(2, '0')).join('') + hex.slice(6);
}
function alpha(value) { return value === 'transparent' ? 0 : value.length === 9 ? parseInt(value.slice(7), 16) / 255 : 1; }
function transform(point, matrix) { return [matrix[0] * point[0] + matrix[2] * point[1] + matrix[4], matrix[1] * point[0] + matrix[3] * point[1] + matrix[5]]; }
function transformed(bounds, matrix) {
    const corners = [[bounds.x, bounds.y], [bounds.x + bounds.width, bounds.y], [bounds.x, bounds.y + bounds.height], [bounds.x + bounds.width, bounds.y + bounds.height]];
    return bounding(corners.map(point => transform(point, matrix)));
}
function bounding(points, padding = 0) {
    const x = Math.min(...points.map(point => point[0])) - padding, y = Math.min(...points.map(point => point[1])) - padding;
    return { x, y, width: Math.max(...points.map(point => point[0])) + padding - x, height: Math.max(...points.map(point => point[1])) + padding - y };
}
function union(a, b) {
    const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    return { x, y, width: Math.max(a.x + a.width, b.x + b.width) - x, height: Math.max(a.y + a.height, b.y + b.height) - y };
}
function inverse(matrix) {
    const determinant = matrix[0] * matrix[3] - matrix[1] * matrix[2];
    if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-10)
        return;
    return [matrix[3] / determinant, -matrix[1] / determinant, -matrix[2] / determinant, matrix[0] / determinant, (matrix[2] * matrix[5] - matrix[3] * matrix[4]) / determinant, (matrix[1] * matrix[4] - matrix[0] * matrix[5]) / determinant];
}
function rectangle(b) { return `M${b.x},${b.y}H${b.x + b.width}V${b.y + b.height}H${b.x}Z`; }
class Drawing {
    matrix;
    size;
    opacity;
    primitives = [];
    points = [];
    padding = 0;
    constructor(matrix, size, opacity) {
        this.matrix = matrix;
        this.size = size;
        this.opacity = opacity;
    }
    path(commands, paint) {
        const result = [];
        for (let i = 0; i < commands.length;) {
            const command = commands[i++];
            if (typeof command === 'string') {
                result.push(command);
                continue;
            }
            const coordinate = transform([command, commands[i++]], this.matrix);
            this.points.push(coordinate);
            result.push(rounded(coordinate[0]), rounded(coordinate[1]));
        }
        const width = finite(paint['stroke-width'], 0, 0, 1) * this.size, blur = finite(paint.blur, 0, 0, 1) * this.size;
        this.padding = Math.max(this.padding, width / 2 + blur * 3);
        this.primitives.push(p(result.join(' '), { ...paint, ...(width ? { 'stroke-width': width } : {}), ...(blur ? { blur } : {}), opacity: finite(paint.opacity, 1, 0, 1) * this.opacity }, 'attachment'));
    }
    ellipse(x, y, rx, ry, paint) {
        const k = .5522847498;
        this.path(['M', x + rx, y, 'C', x + rx, y + k * ry, x + k * rx, y + ry, x, y + ry, 'C', x - k * rx, y + ry, x - rx, y + k * ry, x - rx, y, 'C', x - rx, y - k * ry, x - k * rx, y - ry, x, y - ry, 'C', x + k * rx, y - ry, x + rx, y - k * ry, x + rx, y, 'Z'], paint);
    }
    bounds() { return bounding(this.points, this.padding); }
}
function attachment(kind, tint, draw) {
    const dark = shade(tint, -.34), medium = shade(tint, -.12), light = shade(tint, .4), glint = shade(tint, .76);
    const shadow = { fill: '#172230', opacity: .16 * alpha(tint), blur: .035 };
    if (kind === 'push-pin') {
        draw.ellipse(.12, .43, .24, .07, shadow);
        draw.path(['M', -.035, .09, 'L', .065, .09, .012, .56, -.013, .61, 'Z'], { fill: '#7b8590' });
        draw.path(['M', -.012, .12, 'L', .018, .13, .003, .54], { fill: 'none', stroke: '#edf2f4', 'stroke-width': .018, 'stroke-linecap': 'round' });
        draw.ellipse(0, .12, .3, .125, { fill: dark });
        draw.ellipse(0, .073, .3, .125, { fill: tint });
        draw.ellipse(-.025, .043, .255, .098, { fill: light, opacity: .55 });
        draw.path(['M', -.155, -.43, 'L', .16, -.43, .145, .06, 'C', .08, .13, -.08, .13, -.15, .055, 'Z'], { fill: dark });
        draw.path(['M', -.155, -.43, 'L', .035, -.43, .02, .09, 'C', -.07, .1, -.14, .08, -.15, .055, 'Z'], { fill: tint });
        draw.path(['M', -.11, -.39, 'L', -.055, -.39, -.06, .035, -.108, .015, 'Z'], { fill: light, opacity: .65 });
        draw.ellipse(0, -.43, .22, .105, { fill: medium });
        draw.ellipse(-.008, -.458, .215, .104, { fill: tint });
        draw.ellipse(-.065, -.485, .12, .047, { fill: light, opacity: .85 });
        draw.ellipse(-.12, -.492, .036, .017, { fill: glint });
    }
    else if (kind === 'round-pin') {
        draw.ellipse(.12, .46, .18, .065, shadow);
        draw.path(['M', -.027, -.12, 'L', .047, -.12, .013, .55, -.01, .6, 'Z'], { fill: '#7b8590' });
        draw.path(['M', -.007, -.1, 'L', .011, .48], { fill: 'none', stroke: '#f2f5f7', 'stroke-width': .017, 'stroke-linecap': 'round' });
        draw.ellipse(0, -.3, .26, .26, { fill: dark });
        draw.ellipse(-.035, -.335, .225, .225, { fill: tint });
        draw.ellipse(-.075, -.395, .155, .125, { fill: light, opacity: .75 });
        draw.ellipse(-.12, -.445, .055, .035, { fill: glint, opacity: .9 });
        draw.path(['M', .12, -.49, 'C', .245, -.41, .24, -.23, .12, -.13], { fill: 'none', stroke: medium, 'stroke-width': .045, opacity: .75 });
    }
    else if (kind === 'paper-clip') {
        const wire = ['M', .065, .23, 'L', .065, -.31, 'C', .065, -.48, -.2, -.48, -.2, -.31, 'L', -.2, .3, 'C', -.2, .58, .23, .58, .23, .3, 'L', .23, -.25, 'C', .23, -.59, -.31, -.59, -.31, -.25, 'L', -.31, .19];
        draw.path(wire, { fill: 'none', stroke: '#172230', 'stroke-width': .19, opacity: .12 * alpha(tint), blur: .025, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
        draw.path(wire, { fill: 'none', stroke: dark, 'stroke-width': .13, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
        draw.path(wire, { fill: 'none', stroke: tint, 'stroke-width': .09, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
        draw.path(wire, { fill: 'none', stroke: light, 'stroke-width': .028, opacity: .7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
    }
    else if (kind === 'binder-clip') {
        draw.ellipse(.03, .28, .42, .1, shadow);
        draw.path(['M', -.2, -.06, 'L', -.2, -.38, 'C', -.2, -.67, .2, -.67, .2, -.38, 'L', .2, -.06], { fill: 'none', stroke: '#626c77', 'stroke-width': .07, 'stroke-linejoin': 'round' });
        draw.path(['M', -.2, -.06, 'L', -.2, -.38, 'C', -.2, -.67, .2, -.67, .2, -.38, 'L', .2, -.06], { fill: 'none', stroke: '#e6ebee', 'stroke-width': .035, 'stroke-linejoin': 'round' });
        draw.path(['M', -.38, -.13, 'L', .32, -.13, .43, .22, -.43, .22, 'Z'], { fill: dark, stroke: dark, 'stroke-width': .03, 'stroke-linejoin': 'round' });
        draw.path(['M', -.33, -.13, 'L', .27, -.13, .31, .14, -.36, .14, 'Z'], { fill: tint });
        draw.path(['M', -.32, -.1, 'L', -.24, -.1, -.27, .12, -.36, .12, 'Z'], { fill: light, opacity: .45 });
        draw.path(['M', -.21, .22, 'L', -.21, .47, 'C', -.21, .69, .21, .69, .21, .47, 'L', .21, .22], { fill: 'none', stroke: '#626c77', 'stroke-width': .065 });
        draw.path(['M', -.21, .22, 'L', -.21, .47, 'C', -.21, .69, .21, .69, .21, .47, 'L', .21, .22], { fill: 'none', stroke: '#e6ebee', 'stroke-width': .029 });
    }
    else if (kind === 'tape') {
        draw.path(['M', -.64, -.19, 'L', -.57, -.23, -.6, -.29, .6, -.29, .56, -.22, .63, -.16, .57, -.1, .64, -.03, .59, .04, .62, .12, .56, .2, -.61, .2, -.57, .13, -.64, .07, -.59, 0, -.65, -.07, -.59, -.13, 'Z'], { fill: tint, stroke: medium, 'stroke-width': .016, opacity: .78 });
        draw.path(['M', -.55, -.19, 'L', .55, -.19, .55, -.11, -.55, -.11, 'Z'], { fill: light, opacity: .3 });
        draw.path(['M', -.54, .11, 'L', .54, .11], { fill: 'none', stroke: dark, 'stroke-width': .009, opacity: .2 });
    }
}
function shadow(bounds, input) {
    if (!input || typeof input !== 'object' || Array.isArray(input))
        return;
    const settings = (0, model_js_1.object)(input), kind = (0, model_js_1.str)(settings.kind, 'offset');
    if (!['offset', 'centre', 'corners', 'corner'].includes(kind))
        return;
    const blur = finite(settings.blur, 4, 0, 128), spread = finite(settings.spread, 0, 0, 128), lift = finite(settings.lift, 10, 0, 64);
    const dx = finite(settings.x, kind === 'offset' ? 6 : 0, -1e9, 1e9), dy = finite(settings.y, kind === 'offset' ? 8 : 0, -1e9, 1e9);
    const x = bounds.x - spread + dx, y = bounds.y - spread + dy, w = bounds.width + 2 * spread, h = bounds.height + 2 * spread, right = x + w, bottom = y + h;
    const inset = Math.min(2, w * .02, h * .02);
    const d = kind === 'offset' ? rectangle({ x, y, width: w, height: h }) : kind === 'centre' ? `M${x + inset},${bottom - lift * .8}H${right - inset}V${bottom - lift * .08}C${x + w * .78},${bottom + lift * 1.4} ${x + w * .24},${bottom + lift * 1.4} ${x + inset},${bottom - lift * .08}Z` : kind === 'corners' ? `M${x + inset},${bottom - lift}H${right - inset}L${right + lift * .34},${bottom + lift}C${x + w * .85},${bottom + lift} ${x + w * .7},${bottom - lift * .08} ${x + w * .5},${bottom - lift * .08}C${x + w * .3},${bottom - lift * .08} ${x + w * .15},${bottom + lift} ${x - lift * .34},${bottom + lift}Z` : `M${x + inset},${y + inset}H${right - inset}C${right - inset},${y + h * .4} ${right + lift * .375},${y + h * .83} ${right + lift * .75},${bottom + lift * 1.08}C${x + w * .8},${bottom + lift * .58} ${x + w * .4},${bottom - lift * .08} ${x + inset},${bottom - 1}Z`;
    const padding = 3 * blur + (kind !== 'offset' && lift > 0 ? .7 : 0), tint = color(settings.color, '#000000'), opacity = finite(settings.opacity, .24, 0, 1);
    const primitives = [p(d, { fill: tint, opacity, blur }, 'shadow')];
    if (kind !== 'offset' && lift > 0) {
        const contact = kind === 'centre' ? `M${x + inset},${bottom - 1}Q${x + w * .055},${bottom + 2} ${x + w * .11},${bottom - 1}M${x + w * .89},${bottom - 1}Q${x + w * .95},${bottom + 2} ${right - inset},${bottom - 1}` : kind === 'corners' ? `M${x + w * .4},${bottom - 1}Q${x + w * .5},${bottom + 3} ${x + w * .6},${bottom - 1}` : `M${x + inset},${bottom - 1}Q${x + w * .09},${bottom + 2} ${x + w * .18},${bottom - 1}`;
        primitives.push(p(contact, { fill: 'none', stroke: tint, 'stroke-width': 1.4, opacity: opacity * .75, blur: Math.min(.8, blur) }, 'shadow'));
    }
    const left = x - (kind === 'corners' ? lift * .34 : 0), top = kind === 'centre' ? bottom - lift * .8 : kind === 'corners' ? bottom - lift : y;
    const rightExtent = right + (kind === 'corners' ? lift * .34 : kind === 'corner' ? lift * .75 : 0), bottomExtent = bottom + Math.max(kind !== 'offset' && lift > 0 ? 3 : 0, kind === 'centre' ? lift * 1.4 : kind === 'corners' ? lift : kind === 'corner' ? lift * 1.08 : 0);
    return { primitives, bounds: { x: left - padding, y: top - padding, width: rightExtent - left + padding * 2, height: bottomExtent - top + padding * 2 } };
}
function decoratePaper(entry) {
    const item = entry.item;
    if (entry.definition.record.category === 'relation' || item.layer === 'relations' || item.primitives.some(primitive => 'paint' in primitive && (primitive.paint[marker] || primitive.paint['ddn-texture'])) || entry.definition.owner === 'view' && item.layer !== 'views')
        return entry;
    const paper = (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'style.paper'), 'plain'), settings = entry.effective.shadow;
    const textureValue = (0, model_js_1.pathValue)(entry.effective, 'background.texture');
    const texture = textureValue && typeof textureValue === 'object' && !Array.isArray(textureValue) ? textureValue : undefined;
    const decorations = (0, model_js_1.array)(entry.effective.decorations).map(model_js_1.object).filter(value => Object.hasOwn(defaults, (0, model_js_1.str)(value.kind))).slice(0, 32);
    if (paper === 'plain' && (!settings || (0, model_js_1.object)(settings).kind === 'none') && !decorations.length && !texture)
        return entry;
    const inv = inverse(item.transform);
    if (!inv)
        return entry;
    const local = transformed(item.bounds, inv), primitives = [...item.primitives], under = [], over = [];
    let extent = local;
    let outerIndex = primitives.findIndex(primitive => primitive.kind === 'rect' && primitive.bounds.width >= local.width * .75 && primitive.bounds.height >= local.height * .75);
    if (outerIndex < 0 && (0, model_js_1.pathValue)(entry.effective, 'style.look') === 'handdrawn')
        outerIndex = primitives.findIndex(primitive => primitive.kind === 'path' && /z\s*$/i.test(primitive.d) && primitive.paint.fill !== 'none');
    const outer = outerIndex < 0 ? undefined : primitives[outerIndex];
    const surface = outer && 'bounds' in outer ? outer.bounds : local;
    const cast = shadow(surface, settings);
    if (cast) {
        under.push(...cast.primitives);
        extent = union(extent, cast.bounds);
    }
    if (outer && ['note', 'pad'].includes(paper)) {
        const fill = color((0, model_js_1.pathValue)(entry.effective, 'background.color'), '#fff59d');
        const { x, y, width: w, height: h } = surface;
        if (paper === 'pad') {
            for (const offset of [7, 3.5]) {
                const sheet = { x: x + offset, y: y + offset, width: w, height: h };
                under.push(p(rectangle(sheet), { fill: shade(fill, offset === 7 ? -.15 : -.07), stroke: shade(fill, -.35), 'stroke-width': .8 }));
                extent = union(extent, { ...sheet, width: w + 1, height: h + 1 });
            }
        }
        const sheet = [p(outer.kind === 'path' ? outer.d : rectangle(surface), { ...outer.paint, fill, ...(texture ? { 'ddn-texture': texture } : {}) })];
        const band = Math.min(h * .13, 24);
        sheet.push(p(rectangle({ x: x + 1, y: y + 1, width: Math.max(0, w - 2), height: band }), { fill: shade(fill, .28), opacity: .48 }));
        if (paper === 'pad') {
            const curl = Math.min(30, w * .16, h * .2);
            sheet.push(p(`M${x + w - curl},${y + h}Q${x + w - curl * .15},${y + h - curl * .13} ${x + w},${y + h - curl}Q${x + w - curl * .9},${y + h - curl * .85} ${x + w - curl},${y + h}Z`, { fill: shade(fill, .45), stroke: shade(fill, -.2), 'stroke-width': .7 }));
        }
        if (outer.kind === 'path')
            sheet.push(p(outer.d, { ...outer.paint, fill: 'none' }));
        primitives.splice(outerIndex, 1, ...sheet);
    }
    else if (texture) {
        const index = outerIndex >= 0 ? outerIndex : primitives.findIndex(primitive => primitive.kind === 'path' && /z\s*$/i.test(primitive.d) && primitive.paint.fill !== 'none' || primitive.kind === 'ellipse' && primitive.bounds.width >= local.width * .75 && primitive.bounds.height >= local.height * .75);
        const target = primitives[index];
        if (target && 'paint' in target) {
            primitives[index] = { ...target, paint: { ...target.paint, 'ddn-texture': texture } };
            outerIndex = index;
        }
    }
    for (const decoration of decorations) {
        const size = finite(decoration.size, 32, 8, 128), rotation = finite(decoration.rotation, 0, -180, 180) * Math.PI / 180, opacity = finite(decoration.opacity, 1, 0, 1);
        const position = (0, model_js_1.str)(decoration.position, 'ct'), horizontal = { l: 0, c: .5, r: 1 }[position[0]] ?? .5, vertical = { t: 0, m: .5, b: 1 }[position[1]] ?? 0;
        const x = surface.x + surface.width * horizontal + finite((0, model_js_1.pathValue)(decoration, 'offset.x'), 0, -256, 256), y = surface.y + surface.height * vertical + finite((0, model_js_1.pathValue)(decoration, 'offset.y'), 0, -256, 256);
        const draw = new Drawing([size * Math.cos(rotation), size * Math.sin(rotation), -size * Math.sin(rotation), size * Math.cos(rotation), x, y], size, opacity);
        attachment((0, model_js_1.str)(decoration.kind), color(decoration.color, defaults[(0, model_js_1.str)(decoration.kind)]), draw);
        over.push(...draw.primitives);
        extent = union(extent, draw.bounds());
    }
    if (!under.length && !over.length && primitives.length === item.primitives.length && outerIndex < 0)
        return entry;
    return { ...entry, item: { ...item, primitives: [...under, ...primitives, ...over], bounds: union(item.bounds, transformed(extent, item.transform)) } };
}

}});})();
