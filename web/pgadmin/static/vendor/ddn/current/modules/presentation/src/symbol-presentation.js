import { array, object, pathValue, num, str, resolveRecord, refKey, titleOf } from './model.js';
import { layoutTable } from './table.js';
import { markdownBlocks } from './markdown.js';
const text = (value, x, y, size, color, extra = {}, font = 'sans') => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: font, style: { 'font-size': size, fill: color, ...extra } }] });
export function notePrimitives(value, x, y, width, size, color, measure, formatted, maxLines = 30, bodyFont = 'sans') {
    const primitives = [];
    let offset = 0;
    let count = 0;
    for (const block of markdownBlocks(value, formatted)) {
        const font = block.heading ? size * (1.55 - block.heading * .08) : size;
        const sourceRuns = [...(block.list ? [{ text: '• ' }] : block.quote ? [{ text: '› ' }] : []), ...block.runs];
        const label = sourceRuns.map(r => r.text).join('');
        let cursor = 0;
        const lines = layoutTable([{ id: 'text', max_lines: maxLines }], [[label]], width, value => measure(value) * font / size, { header: false, lineHeight: font * 1.3 }).rows[0]?.cells[0]?.lines ?? [label];
        for (const line of lines) {
            if (count++ >= maxLines) {
                primitives.push(text('…', x, y + offset, font, color));
                return { primitives, height: offset + font * 1.4 };
            }
            // Wrapped lines retain the overlapping Markdown runs. Trimming a
            // wrap separator must not turn bold/code/underline into plain text.
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
/** Auto recognition is limited to declared artwork, never a decorative background alone. */
export function standaloneChoice(effective, definition, origins = {}) {
    const mode = str(pathValue(effective, 'symbol.mode'), 'auto');
    if (mode === 'card')
        return undefined;
    if (mode === 'text')
        return { mode };
    const icon = object(pathValue(definition.record, 'metadata.x_icon'));
    const image = pathValue(effective, 'symbol.image');
    const authoredNull = image === null && !!origins['symbol.image'] && !origins['symbol.image'].startsWith('standard:');
    const selected = image ?? (!authoredNull && Object.keys(icon).length ? pathValue(effective, 'background.image') : undefined);
    if (mode !== 'image' && !selected)
        return undefined;
    return { mode: 'image', image: selected, ...(icon.library === 'electrical-common@1' ? { electricalIcon: str(icon.icon, str(icon.name)) } : {}) };
}
function union(boxes) {
    const x = Math.min(...boxes.map(b => b.x)), y = Math.min(...boxes.map(b => b.y));
    return { x, y, width: Math.max(...boxes.map(b => b.x + b.width)) - x, height: Math.max(...boxes.map(b => b.y + b.height)) - y };
}
function dimension(value) { return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined; }
function rawNotes(definition) {
    return str(pathValue(definition.record, 'content.text')) || str(definition.record.description) || str(pathValue(definition.record, 'draft.text')) || array(definition.record.notes).filter(n => !str(object(n).title).startsWith('Additional source')).map(n => str(object(n).text)).join('\n\n');
}
/** Produce paint bounds and routing/hit bounds independently. The latter must
 * never acquire caption margins when a graph lays out or routes this item. */
export function standaloneNode(input) {
    const { definition, appearance, effective, origins, all, x, y, measure } = input;
    const choice = standaloneChoice(effective, definition, origins);
    if (!choice)
        return undefined;
    const size = num(pathValue(effective, 'style.font_size'), 16), font = str(pathValue(effective, 'style.font'), 'sans'), color = str(pathValue(effective, 'text.color'), '#1f2933');
    const title = str(appearance?.record.title) || titleOf(definition.record), primitives = [], diagnostics = [], unavailable = [];
    const presentation = { mode: choice.mode, ...(choice.electricalIcon !== undefined ? { electricalIcon: choice.electricalIcon } : {}) };
    const requestedWidth = dimension(pathValue(effective, 'size.width')), requestedHeight = dimension(pathValue(effective, 'size.height'));
    const maxWidth = num(pathValue(effective, 'max_size.width'), 4000), maxHeight = num(pathValue(effective, 'max_size.height'), 4000);
    const clampWidth = (v) => Math.max(1, Math.min(maxWidth, Math.max(v, num(pathValue(effective, 'min_size.width'), 0))));
    const clampHeight = (v) => Math.max(1, Math.min(maxHeight, Math.max(v, num(pathValue(effective, 'min_size.height'), 0))));
    const caption = (label, placement, body) => {
        if (placement === 'none' || !label)
            return body;
        const gap = Math.max(0, num(pathValue(effective, 'symbol.label_gap'), 6));
        const lines = label.split('\n'), width = Math.max(1, ...lines.map(line => measure(line, size, font))), height = lines.length * size * 1.4;
        const left = placement.includes('left'), right = placement.includes('right'), top = placement.includes('top'), bottom = placement.includes('bottom');
        const x = left ? body.x - gap - width : right ? body.x + body.width + gap : body.x + (body.width - width) / 2;
        const y = top ? body.y - gap - height : bottom ? body.y + body.height + gap : body.y + (body.height - height) / 2;
        lines.forEach((line, index) => primitives.push(text(line, x, y + size + index * size * 1.4, size, color, {}, font)));
        return union([body, { x, y, width, height }]);
    };
    let body, bounds;
    if (choice.mode === 'text') {
        const content = rawNotes(definition), placement = str(pathValue(effective, 'symbol.label'), 'auto'), showTitle = placement !== 'none';
        const inlineTitle = placement === 'auto' || placement === 'inside';
        const value = content ? (showTitle && inlineTitle && title ? title + '\n\n' : '') + content : showTitle ? title : '';
        const width = clampWidth(requestedWidth ?? Math.max(64, Math.min(320, ...value.split('\n').map(line => measure(line, size, font)))));
        const maxLines = Math.max(1, Math.floor((requestedHeight ?? maxHeight) / (size * 1.4)));
        const result = notePrimitives(value, x, y + size, width, size, color, line => measure(line, size, font), pathValue(effective, 'text.format') !== 'plain' && pathValue(definition.record, 'content.format') !== 'plain', maxLines, font);
        primitives.push(...result.primitives);
        body = { x, y, width, height: clampHeight(requestedHeight ?? Math.max(size * 1.4, result.height)) };
        bounds = content && showTitle && !inlineTitle ? caption(title, placement, body) : body;
    }
    else {
        const sourcePath = pathValue(effective, 'symbol.image') != null ? 'symbol.image' : 'background.image';
        const declaringFile = appearance && pathValue(appearance.record, sourcePath) !== undefined ? appearance.file : definition.file;
        const asset = choice.image ? resolveRecord(all, choice.image, declaringFile) : undefined;
        const intrinsic = object(asset?.record.intrinsic_size), natural = asset ? input.assetSizes?.get(refKey(asset.ref)) : undefined;
        const naturalWidth = dimension(intrinsic.width) ?? dimension(natural?.width), naturalHeight = dimension(intrinsic.height) ?? dimension(natural?.height);
        const aspect = naturalWidth && naturalHeight ? naturalWidth / naturalHeight : 1;
        const envelopeWidth = clampWidth(requestedWidth ?? (requestedHeight ? requestedHeight * aspect : 96));
        const envelopeHeight = clampHeight(requestedHeight ?? envelopeWidth / aspect);
        const width = Math.min(envelopeWidth, envelopeHeight * aspect), height = width / aspect;
        body = { x: x + (envelopeWidth - width) / 2, y: y + (envelopeHeight - height) / 2, width, height };
        bounds = body;
        if (asset?.owner === 'asset')
            primitives.push({ kind: 'image', assetId: refKey(asset.ref), bounds: body });
        else {
            diagnostics.push({ code: 'symbol-image-unavailable', severity: 'warning', message: 'The standalone image has no resolvable asset; its image cannot be displayed.', target: appearance?.ref ?? definition.ref });
            unavailable.push('symbol-image:' + refKey(appearance?.ref ?? definition.ref));
            primitives.push(text('Image unavailable', body.x + body.width / 2, body.y + body.height / 2, Math.min(size, 12), color, { 'text-anchor': 'middle' }, font));
        }
        const suppliedLabel = str(pathValue(effective, 'symbol.label'), 'auto');
        const placement = suppliedLabel === 'auto' ? choice.electricalIcon !== undefined ? 'none' : 'bottom' : suppliedLabel;
        bounds = caption(title, placement, body);
        if (effective.body === 'notes' || effective.body === 'draft') {
            const value = rawNotes(definition);
            if (value) {
                const top = bounds.y + bounds.height + 6, noteWidth = Math.max(body.width, Math.min(280, ...value.split('\n').map(line => measure(line, size, font))));
                const result = notePrimitives(value, body.x, top + size, noteWidth, size, color, line => measure(line, size, font), effective.body !== 'draft' && pathValue(effective, 'text.format') !== 'plain', 30, font);
                primitives.push(...result.primitives);
                bounds = union([bounds, { x: body.x, y: top, width: noteWidth, height: result.height }]);
            }
        }
    }
    // These are already resolved values; CSS and file origin priority is owned
    // by the resolver. Preserve inline Markdown when no explicit global style is set.
    const styles = {};
    for (const [key, attr] of [['weight', 'font-weight'], ['italic', 'font-style'], ['decoration', 'text-decoration'], ['variant', 'font-variant']]) {
        const value = pathValue(effective, 'text.' + key), origin = origins['text.' + key];
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
/** Terminals are the visible lead endpoints of the bundled 24-unit SVGs.
 * This is attachment geometry, not an electrical/circuit verification model. */
export function symbolTerminals(entry) {
    const icon = entry.standalone?.electricalIcon;
    if (icon === undefined)
        return [];
    const body = entry.item.hitTargets.find(hit => refKey(hit.target) === refKey(entry.definition.ref))?.bounds ?? entry.item.bounds;
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
export function symbolTerminal(entry, other, side = '', fraction = .5) {
    const terminals = symbolTerminals(entry);
    if (!terminals.length)
        return undefined;
    const body = entry.item.hitTargets.find(hit => refKey(hit.target) === refKey(entry.definition.ref))?.bounds ?? entry.item.bounds;
    const target = other.item.hitTargets.find(hit => refKey(hit.target) === refKey(other.definition.ref))?.bounds ?? other.item.bounds;
    const sameSide = terminals.filter(t => t.side === side);
    const targetPoint = sameSide.length ? [body.x + body.width * fraction, body.y + body.height * fraction] : [target.x + target.width / 2, target.y + target.height / 2];
    return [...(sameSide.length ? sameSide : terminals)].sort((a, b) => Math.hypot(a.point[0] - targetPoint[0], a.point[1] - targetPoint[1]) - Math.hypot(b.point[0] - targetPoint[0], b.point[1] - targetPoint[1]))[0]?.point;
}
export function electricalWireWithoutLabel(edge, from, to) {
    const title = str(edge.definition.record.title, str(edge.definition.record.name)).trim().toLowerCase();
    return edge.definition.record.role === 'assoc' && from.standalone?.electricalIcon !== undefined && to.standalone?.electricalIcon !== undefined && ['', 'associated with', 'assoc', 'association'].includes(title) && !pathValue(edge.appearance?.record, 'route.callout');
}
//# sourceMappingURL=symbol-presentation.js.map