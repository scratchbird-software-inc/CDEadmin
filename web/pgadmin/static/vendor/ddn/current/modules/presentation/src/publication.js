import { wrapCell } from './table.js';
import { object, pathValue, num, str } from './model.js';
export function publicationPageSize(page, content) {
    const measure = (value, fallback) => { const q = object(value); return typeof value === 'number' ? value : num(q.value, fallback) * ({ px: 1, pt: 96 / 72, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 }[str(q.unit, 'px')] ?? 1); };
    const paper = { letter: [816, 1056], legal: [816, 1344], a4: [793.7, 1122.52], a3: [1122.52, 1587.4], tabloid: [1056, 1632] };
    let [width, height] = paper[str(page.size)] ?? [measure(page.width, content.width), measure(page.height, content.height)];
    if (page.orientation === 'landscape' && width < height)
        [width, height] = [height, width];
    return [width, height];
}
/** Page composition is independent of DOM, capture format and diagram method. */
export function publicationScene(items, content, publication, title, date) {
    const record = publication.record, page = object(record.page), size = str(page.size, 'content');
    const measure = (value, fallback) => { const q = object(value); return typeof value === 'number' ? value : num(q.value, fallback) * ({ px: 1, pt: 96 / 72, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 }[str(q.unit, 'px')] ?? 1); };
    let [width, height] = publicationPageSize(page, content);
    const margins = object(page.margin), left = num(margins.left, 32), right = num(margins.right, 32), top = num(margins.top, 32), bottom = num(margins.bottom, 32);
    const tokens = { title, date, page: String(num(page.number_start, 1)), pages: '1', figure: '1', view_id: items[0]?.view.id ?? '' };
    const contentScale = num(page.content_scale, 1);
    if (size === 'content')
        width = content.width * contentScale + left + right;
    const band = (input) => {
        const data = object(input);
        if (data.visible === false)
            return [];
        const entries = Object.entries(object(data.runs)), center = entries.some(([position, value]) => str(object(value).align, position) === 'center'), slotWidth = Math.max(1, (width - left - right) / (entries.length <= 1 ? 1 : center ? 3 : 2) - 12);
        return entries.map(([position, value]) => { const run = object(value), fontSize = measure(run.size, 12), label = str(run.text).replace(/\$(title|date|pages|page|figure|view_id)\b/g, (_, key) => tokens[key]); return { run, position, fontSize, lines: wrapCell(label, slotWidth, value => value.length * fontSize * .6, num(run.lines, 1)).lines }; });
    };
    const header = band(record.header), footer = band(record.footer), bandHeight = (items) => items.length ? Math.max(...items.map(item => item.lines.length * item.fontSize * 1.3)) + 12 : 0, headerHeight = bandHeight(header), footerHeight = bandHeight(footer);
    if (size === 'content')
        height = content.height * contentScale + top + bottom + headerHeight + footerHeight;
    const destination = { x: left, y: top + headerHeight, width: Math.max(1, width - left - right), height: Math.max(1, height - top - bottom - headerHeight - footerHeight) };
    const fit = str(page.fit, 'contain'), scale = fit === 'none' ? contentScale : Math.min(destination.width / content.width, destination.height / content.height);
    const tx = destination.x + (destination.width - content.width * scale) / 2 - content.x * scale, ty = destination.y + (destination.height - content.height * scale) / 2 - content.y * scale;
    const move = (b) => ({ x: b.x * scale + tx, y: b.y * scale + ty, width: b.width * scale, height: b.height * scale });
    const intersect = (a, b) => { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y); return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) }; };
    const transformed = items.map(item => { const m = item.transform; return { ...item, bounds: move(item.bounds), clip: item.clip ? intersect(move(item.clip), destination) : destination, hitTargets: item.hitTargets.map(h => ({ ...h, bounds: move(h.bounds) })), transform: [m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4] * scale + tx, m[5] * scale + ty] }; });
    const bounds = { x: 0, y: 0, width, height };
    const primitives = [{ kind: 'rect', bounds, paint: { fill: str(pathValue(record, 'background.color'), '#ffffff'), stroke: 'none', rx: 0 } }];
    const border = num(pathValue(record, 'border.width'));
    if (border > 0)
        primitives.push({ kind: 'rect', bounds: { x: left / 2, y: top / 2, width: width - (left + right) / 2, height: height - (top + bottom) / 2 }, paint: { fill: 'none', stroke: str(pathValue(record, 'border.color'), '#475569'), 'stroke-width': border, rx: 0 } });
    for (const [items, y] of [[header, top], [footer, height - bottom - footerHeight]]) {
        for (const { run, position, fontSize, lines } of items) {
            const align = str(run.align, position);
            primitives.push({ kind: 'text', runs: lines.map((text, index) => ({ text, x: align === 'right' ? width - right : align === 'center' ? width / 2 : left, y: y + 6 + fontSize + index * fontSize * 1.3, fontKey: str(run.font, 'sans'), style: { 'font-size': fontSize, fill: str(run.color, '#334155'), 'text-anchor': align === 'right' ? 'end' : align === 'center' ? 'middle' : 'start', 'font-weight': num(run.weight, 400), ...(run.italic ? { 'font-style': 'italic' } : {}), ...(run.decoration === 'strike' ? { 'text-decoration': 'line-through' } : {}), ...(run.variant === 'small_caps' ? { 'font-variant': 'small-caps' } : {}) } })) });
        }
    }
    const frame = { occurrence: 'publication:' + publication.ref.id, target: publication.ref, view: items[0]?.view ?? publication.ref, layer: 'views', bounds, transform: [1, 0, 0, 1, 0, 0], primitives, hitTargets: [], accessible: { role: 'graphics-object', label: title }, evidence: 'current' };
    const diagnostics = [];
    if (content.width * scale > destination.width + .01 || content.height * scale > destination.height + .01)
        diagnostics.push({ code: 'publication-overflow', severity: page.overflow === 'report' ? 'warning' : 'error', message: page.overflow === 'tile' ? 'This capture requires a tiled publication output adapter.' : 'Content exceeds the page content area at the requested scale.', target: publication.ref });
    const fonts = items.flatMap(i => i.primitives.flatMap(p => p.kind === 'text' ? p.runs.map(r => num(r.style['font-size'], 16) * scale * num(page.embedding_scale, 1)) : []));
    if (fonts.length && Math.min(...fonts) < num(page.minimum_text, 0))
        diagnostics.push({ code: 'publication-minimum-text', severity: 'warning', message: 'Page fitting places some text below the publication minimum text size.', target: publication.ref });
    return { items: [frame, ...transformed], bounds, diagnostics };
}
//# sourceMappingURL=publication.js.map