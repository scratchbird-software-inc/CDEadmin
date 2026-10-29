import { array, object, num, str, pathValue, resolveRecord, refKey, titleOf } from './model.js';
import { DataScene, box, label, path, ellipse, pointsPath, finite, valueAt, sum, unique, numericDate, colors } from './data-common.js';
import { matrixEncoding } from './data-encoding.js';
import { wrapCell } from './table.js';
import { analyzeProfile } from '../../profiles/src/analysis-profile.js';
function lookup(scene, reference) { return typeof reference === 'string' ? scene.all.find(r => r.file === scene.view.file && (r.record.name === reference || r.ref.id === reference)) : resolveRecord(scene.all, reference, scene.view.file); }
/** Layout dimensions are measured from content; explicitly supplied projection sizes remain minima. */
function fontScale(scene) { return num(pathValue(scene.effective, 'style.font_size'), 16) / 16; }
function lines(scene, text, width, size) {
    return text.split(/\r?\n/).flatMap(paragraph => paragraph ? wrapCell(paragraph, Math.max(1, width), value => scene.measure(value, size), 500).lines : ['']);
}
function block(text, x, baseline, size, lineHeight, paint = {}) {
    return text.map((value, index) => label(value, x, baseline + index * lineHeight, size, paint));
}
function surfaceBounds(scene, width, height) {
    const bounds = { x: scene.bounds.x, y: scene.bounds.y, width: Math.max(width, num(scene.settings.width)), height: Math.max(height, num(scene.settings.height)) };
    scene.result.bounds = bounds;
    return bounds;
}
function contrast(fill) {
    const normalized = /^#[0-9a-f]{3}$/i.test(fill) ? '#' + [...fill.slice(1)].map(value => value + value).join('') : fill;
    const hex = /^#([0-9a-f]{6})$/i.exec(normalized), rgb = /^rgb\((\d+),\s*(\d+),\s*(\d+)\)$/.exec(fill);
    const channels = hex ? [0, 2, 4].map(i => parseInt(hex[1].slice(i, i + 2), 16)) : rgb ? rgb.slice(1).map(Number) : [];
    return channels.length && channels[0] * .299 + channels[1] * .587 + channels[2] * .114 < 145 ? '#ffffff' : '#243449';
}
function thresholdIndex(encoding, value, values) {
    const boundaries = array(encoding.boundaries).filter(finite), range = object(encoding.range), numeric = values.filter(finite);
    if (boundaries.length)
        return value === boundaries.at(-1) ? boundaries.length - 2 : boundaries.findIndex((boundary, i) => i < boundaries.length - 1 && value >= boundary && value < boundaries[i + 1]);
    return value < num(range.min, num(object(encoding.domain).min, Math.min(...numeric, 0))) ? 0 : value < num(range.max, num(object(encoding.domain).max, Math.max(...numeric, 1))) ? 1 : 2;
}
const matrixHeadings = { 'matrix.raci@1': 'ACTIVITY / RESPONSIBILITY', 'matrix.crud@1': 'PROCESS / DATA ACCESS', 'matrix.relations@1': 'RELATIONSHIP MATRIX', 'matrix.heatmap@1': 'DECLARED CELL ENCODING', 'matrix.bcg@1': 'GROWTH / SHARE MATRIX', 'matrix.ansoff@1': 'PRODUCT / MARKET MATRIX', 'matrix.tows@1': 'TOWS STRATEGY MATRIX', 'matrix.storymap@1': 'RELEASE / BACKBONE STORY MAP' };
const matrixCaptions = {
    'matrix.raci@1': 'R responsible · A accountable · C consulted · I informed. One A and at least one R per row.',
    'matrix.crud@1': 'C create · R read · U update · D delete. Cells are shared relationship records.',
    'matrix.bcg@1': 'Rows: market growth (high/low) · Columns: relative share (high/low) · Cells are declared items, not computed positions.',
    'matrix.ansoff@1': 'Rows: markets · Columns: products (existing/new) · Cells are declared strategy items.',
    'matrix.tows@1': 'Rows: internal strengths/weaknesses · Columns: external opportunities/threats · Cells are declared strategy notes.',
    'matrix.storymap@1': 'Rows are releases (top ships first) · columns are backbone activities · cells are declared analysis.task stories.',
    'matrix.relations@1': 'Cells derive from declared relationships; an empty cell is not an invented relation.',
    'matrix.heatmap@1': 'Colours encode declared values; a missing cell is no record, not zero.'
};
export function drawMatrix(scene) {
    const settings = scene.settings, profile = str(scene.view.record.profile), rowRefs = array(settings.rows), colRefs = array(settings.columns), rows = rowRefs.map(ref => lookup(scene, ref)), columns = colRefs.map(ref => lookup(scene, ref));
    if (rows.some(r => !r) || columns.some(c => !c) || !rows.length || !columns.length) {
        scene.issue('Matrix requires ordered, resolved row and column references.');
        return;
    }
    if (columns.length > 40 || rows.length * columns.length > 5000) {
        scene.issue('Matrix exceeds 40 columns or 5,000 cells.');
        return;
    }
    if (unique(rows.map(r => refKey(r.ref))).length !== rows.length || unique(columns.map(r => refKey(r.ref))).length !== columns.length) {
        scene.issue('Matrix axes cannot repeat references.');
        return;
    }
    const relationRole = str(settings.relation);
    if (!relationRole) {
        scene.issue('Choose the matrix relation role.');
        return;
    }
    const relations = scene.all.filter(r => r.owner === 'definition' && r.record.category === 'relation' && r.record.role === relationRole), map = new Map();
    for (const relation of relations) {
        const ends = array(relation.record.endpoints).map(e => resolveRecord(scene.all, object(e).definition, relation.file));
        if (ends.length < 2 || !ends[0] || !ends[1])
            continue;
        const row = rows.findIndex(r => refKey(r.ref) === refKey(ends[0].ref)), column = columns.findIndex(r => refKey(r.ref) === refKey(ends[1].ref));
        if (row < 0 || column < 0)
            continue;
        const key = `${row}:${column}`;
        map.set(key, [...map.get(key) ?? [], relation]);
    }
    const strategy = ['matrix.bcg@1', 'matrix.ansoff@1', 'matrix.tows@1'].includes(profile), duplicateMode = str(settings.duplicates, strategy || profile === 'matrix.storymap@1' ? 'join' : 'error');
    if (['matrix.raci@1', 'matrix.crud@1'].includes(profile) && duplicateMode !== 'error') {
        scene.issue('Responsibility and CRUD cells cannot merge duplicate assignments.');
        return;
    }
    if (strategy && (rows.length !== 2 || columns.length !== 2)) {
        scene.issue('Strategy matrices require exactly two rows and two columns.');
        return;
    }
    const rawValue = (relation) => valueAt({ ...relation.record, ...object(pathValue(relation.record, 'metadata.x_record')) }, str(settings.value, 'value'));
    const values = [...map.values()].flatMap(rs => rs.map(rawValue)), encoding = object(settings.encoding), usedStories = new Set(), heatmap = profile === 'matrix.heatmap@1';
    let heatColor = () => '#f1f5f9';
    if (heatmap) {
        try {
            if ([...map.values()].some(contributions => contributions.length > 1))
                throw new Error('Encoded heatmap cells require exactly one contribution.');
            heatColor = matrixEncoding(encoding, values);
        }
        catch (error) {
            scene.issue(String(error));
            return;
        }
    }
    const texts = rows.map((row, ri) => {
        let accountable = 0, responsible = 0;
        const cells = columns.map((_column, ci) => {
            const contributors = map.get(`${ri}:${ci}`) ?? [];
            if (contributors.length > 1 && duplicateMode === 'error')
                scene.issue('Duplicate matrix assignments are not permitted.', 'DDN-MATRIX-DUPLICATE', 'error', contributors[1].ref);
            let result = contributors.map(relation => {
                const metadata = object(relation.record.metadata), raw = ['matrix.raci@1', 'matrix.crud@1'].includes(profile) ? pathValue(metadata, 'x_assignment.code') : rawValue(relation);
                if (profile === 'matrix.raci@1') {
                    if (!['R', 'A', 'C', 'I'].includes(str(raw)))
                        scene.issue('RACI assignment must be R, A, C or I.');
                    if (raw === 'A')
                        accountable++;
                    if (raw === 'R')
                        responsible++;
                }
                if (profile === 'matrix.crud@1' && (typeof raw !== 'string' || !/^[CRUD]+$/.test(raw) || new Set(raw).size !== raw.length))
                    scene.issue('CRUD assignment contains invalid or repeated letters.');
                if (profile === 'matrix.storymap@1') {
                    const story = resolveRecord(scene.all, pathValue(metadata, 'x_story.task'), relation.file);
                    if (!story || story.record.role !== 'analysis.task') {
                        scene.issue('Story cells must reference an analysis.task.');
                        return '';
                    }
                    const id = refKey(story.ref);
                    if (usedStories.has(id))
                        scene.issue('A story appears in more than one cell or release.');
                    usedStories.add(id);
                    return titleOf(story.record);
                }
                if (heatmap && encoding.mode === 'threshold' && finite(raw)) {
                    const band = array(encoding.labels)[thresholdIndex(encoding, raw, values)];
                    if (typeof band === 'string')
                        return `${band} · ${raw}`;
                }
                return raw == null ? titleOf(relation.record) : typeof raw === 'object' ? JSON.stringify(raw) : String(raw);
            });
            if (duplicateMode === 'first')
                result = result.slice(0, 1);
            else if (duplicateMode === 'last')
                result = result.slice(-1);
            else if (duplicateMode === 'sum' && contributors.length) {
                const raw = contributors.map(rawValue);
                if (raw.some(value => !finite(value)))
                    scene.issue('Summed matrix cells require finite numbers without string coercion.');
                result = [String(sum(raw.filter(finite)))];
            }
            return result.join(' / ') || (heatmap ? '— no record' : '—');
        });
        if (profile === 'matrix.raci@1' && (accountable !== 1 || responsible < 1))
            scene.issue(`RACI row ${titleOf(row.record)} needs exactly one A and at least one R.`, 'DDN-RACI-COMPLETE', 'warning', row.ref);
        return cells;
    });
    const s = fontScale(scene), rowWidth = Math.max(230 * s, Math.min(390 * s, Math.max(...rows.map(row => scene.measure(titleOf(row.record), 13))) + 32 * s));
    const cellWidth = Math.max(130 * s, (num(settings.width, scene.bounds.width) - rowWidth) / columns.length), width = rowWidth + cellWidth * columns.length;
    const headingLines = columns.map(column => lines(scene, titleOf(column.record), cellWidth - 24 * s, 13)), headHeight = Math.max(75 * s, ...headingLines.map(text => (text.length * 19 + 30) * s));
    const size = profile === 'matrix.relations@1' || heatmap ? 13 : 17, rowLines = rows.map(row => lines(scene, titleOf(row.record), rowWidth - 28 * s, 13));
    const cellLines = texts.map(row => row.map(text => lines(scene, text, cellWidth - 24 * s, size)));
    const rowHeights = rows.map((_row, ri) => Math.max(62 * s, (Math.max(rowLines[ri].length, ...cellLines[ri].map(text => text.length)) * 23 + 25) * s));
    const caption = lines(scene, matrixCaptions[profile] ?? '', width - 24 * s, 11);
    surfaceBounds(scene, width, headHeight + sum(rowHeights) + (caption.length * 16 + 24) * s);
    const x = scene.bounds.x, y = scene.bounds.y;
    scene.add('Matrix heading', { x, y, width: rowWidth, height: headHeight }, [box({ x, y, width: rowWidth, height: headHeight }, '#f5f7fb'), ...block(lines(scene, matrixHeadings[profile] ?? 'MATRIX', rowWidth - 32 * s, 11), x + 16 * s, y + 28 * s, 11, 16 * s, { 'font-weight': 600 })]);
    columns.forEach((column, ci) => { const b = { x: x + rowWidth + ci * cellWidth, y, width: cellWidth, height: headHeight }; scene.add(titleOf(column.record), b, [box(b, '#f5f7fb'), ...block(headingLines[ci], b.x + 12 * s, y + 28 * s, 13, 19 * s, { 'font-weight': 600 })], column); });
    let top = y + headHeight;
    rows.forEach((row, ri) => {
        const height = rowHeights[ri], fill = ri % 2 ? '#f5f7fb' : '#ffffff', head = { x, y: top, width: rowWidth, height };
        scene.add(titleOf(row.record), head, [box(head, fill), ...block(rowLines[ri], x + 14 * s, top + height / 2 - (rowLines[ri].length - 1) * 19 * s / 2 + 5 * s, 13, 19 * s, { 'font-weight': 600 })], row);
        columns.forEach((column, ci) => {
            const contributors = map.get(`${ri}:${ci}`) ?? [], b = { x: x + rowWidth + ci * cellWidth, y: top, width: cellWidth, height };
            let background = fill;
            if (heatmap && contributors.length) {
                try {
                    background = heatColor(rawValue(contributors[0]));
                }
                catch (error) {
                    scene.issue(String(error));
                }
            }
            const content = cellLines[ri][ci];
            scene.add(`${titleOf(row.record)} / ${titleOf(column.record)}: ${texts[ri][ci]}`, b, [box(b, background), ...block(content, b.x + b.width / 2, b.y + b.height / 2 - (content.length - 1) * 23 * s / 2 + size * s * .35, size, 23 * s, { 'text-anchor': 'middle', 'font-weight': 600, fill: heatmap && contributors.length ? contrast(background) : '#243449' })], contributors[0] ?? row, [row.ref, column.ref, ...contributors.map(r => r.ref)], 'Row-to-column assignment; a missing cell is not zero or an implied relation.');
        });
        top += height;
    });
    const legendHeight = heatmap ? drawMatrixLegend(scene, encoding, values, heatColor, x + rowWidth, top + 18 * s, width - rowWidth) + 30 * s : 0;
    const footer = { x, y: top + legendHeight, width, height: (caption.length * 16 + 24) * s };
    scene.add('Matrix interpretation', footer, block(caption, x + 12 * s, footer.y + 20 * s, 11, 16 * s));
}
function drawMatrixLegend(scene, encoding, values, color, x, y, width) {
    const s = fontScale(scene), mode = str(encoding.mode, 'numeric'), numeric = values.filter(finite), domain = object(encoding.domain), min = num(domain.min, Math.min(...numeric, 0)), max = num(domain.max, Math.max(...numeric, 1));
    const primitives = [];
    let height = 44 * s;
    if (mode === 'numeric') {
        const w = Math.min(width - 12 * s, 360 * s);
        for (let i = 0; i < 64; i++)
            primitives.push(box({ x: x + i * w / 64, y, width: w / 64 + .1, height: 12 * s }, color(min + (max - min) * i / 63), 'none'));
        for (let i = 0; i <= 4; i++) {
            const value = min + (max - min) * i / 4, tx = x + w * i / 4;
            primitives.push(path(`M${tx},${y + 12 * s}v${5 * s}`), label(String(Number(value.toPrecision(5))), tx, y + 31 * s, 11, { 'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle' }));
        }
    }
    else {
        const boundaries = array(encoding.boundaries).filter(finite), range = object(encoding.range), numeric = values.filter(finite);
        const entries = mode === 'categorical' ? (Array.isArray(encoding.labels) ? array(encoding.labels) : unique(values)).map(value => ({ value, text: String(value) })) : boundaries.length ? boundaries.slice(0, -1).map((value, i) => ({ value: (value + boundaries[i + 1]) / 2, text: typeof array(encoding.labels)[i] === 'string' ? `${array(encoding.labels)[i]} [${value}, ${boundaries[i + 1]}${i === boundaries.length - 2 ? ']' : ')'}` : `${value}–${boundaries[i + 1]}${i === boundaries.length - 2 ? ' inclusive' : ''}` })) : [{ value: num(range.min, min) - 1, text: `Below ${num(range.min, min)}` }, { value: (num(range.min, min) + num(range.max, max)) / 2, text: `${num(range.min, min)}–${num(range.max, max)}` }, { value: num(range.max, max), text: `${num(range.max, max)} and above` }];
        let tx = x, ty = y, rowHeight = 22 * s;
        for (const entry of entries) {
            const wrapped = lines(scene, entry.text, width - 30 * s, 11), itemWidth = Math.min(width, scene.measure(entry.text, 11) + 30 * s);
            if (tx > x && tx + itemWidth > x + width) {
                tx = x;
                ty += rowHeight;
                rowHeight = 22 * s;
            }
            rowHeight = Math.max(rowHeight, wrapped.length * 16 * s + 6 * s);
            height = Math.max(height, ty - y + rowHeight);
            let fill = '#f1f5f9';
            try {
                fill = color(entry.value);
            }
            catch { /* Invalid samples are already reported by the cell renderer. */ }
            primitives.push(box({ x: tx, y: ty, width: 12 * s, height: 12 * s }, fill, 'none'), ...block(wrapped, tx + 18 * s, ty + 11 * s, 11, 16 * s));
            tx += itemWidth;
        }
    }
    scene.add('Heatmap scale', { x, y, width, height }, primitives);
    return height;
}
const templates = {
    'canvas.bmc@1': [10, [['kp', 'Key partners', 0, 0, 2, 2], ['ka', 'Key activities', 0, 2, 2, 1], ['kr', 'Key resources', 1, 2, 2, 1], ['vp', 'Value proposition', 0, 4, 2, 2], ['cr', 'Customer relationships', 0, 6, 2, 1], ['ch', 'Channels', 1, 6, 2, 1], ['cs', 'Customer segments', 0, 8, 2, 2], ['cost', 'Cost structure', 2, 0, 5, 1], ['rev', 'Revenue streams', 2, 5, 5, 1]]],
    'canvas.lean@1': [10, [['problem', 'Problem', 0, 0, 2, 2], ['solution', 'Solution', 0, 2, 2, 1], ['keymetrics', 'Key metrics', 1, 2, 2, 1], ['uvp', 'Unique value proposition', 0, 4, 2, 2], ['unfair', 'Unfair advantage', 0, 6, 2, 1], ['channels', 'Channels', 1, 6, 2, 1], ['segments', 'Customer segments', 0, 8, 2, 2], ['cost', 'Cost structure', 2, 0, 5, 1], ['revenue', 'Revenue streams', 2, 5, 5, 1]]],
    'canvas.pest@1': [4, ['political', 'economic', 'social', 'technological'].map((id, i) => [id, id, 0, i, 1, 1])],
    'canvas.pestle@1': [3, ['political', 'economic', 'social', 'technological', 'legal', 'environmental'].map((id, i) => [id, id, Math.floor(i / 3), i % 3, 1, 1])],
    'canvas.porter5@1': [3, [['entrants', 'New entrants', 0, 1, 1, 1], ['supplier', 'Supplier power', 1, 0, 1, 1], ['rivalry', 'Competitive rivalry', 1, 1, 1, 1], ['buyer', 'Buyer power', 1, 2, 1, 1], ['substitutes', 'Substitutes', 2, 1, 1, 1]]],
    'canvas.empathy@1': [3, [['says', 'Says', 0, 0, 1, 1], ['thinks', 'Thinks', 0, 2, 1, 1], ['persona', 'Persona', 0, 1, 1, 2], ['does', 'Does', 1, 0, 1, 1], ['feels', 'Feels', 1, 2, 1, 1]]],
    'canvas.scorecard@1': [1, ['financial', 'customer', 'internal', 'learning'].map((id, i) => [id, id, i, 0, 1, 1])]
};
export function drawPanels(scene) {
    const profile = str(scene.view.record.profile), template = templates[profile], settings = scene.settings, columns = num(settings.columns, template?.[0] ?? 1), panels = [];
    if (!Number.isInteger(columns) || columns < 1 || columns > 12) {
        scene.issue('Panels require 1..12 grid columns.');
        return;
    }
    for (const [index, raw] of array(settings.panels).entries()) {
        const inclusion = object(raw);
        if (inclusion.condition === false)
            continue;
        if (inclusion.condition !== undefined && inclusion.condition !== true) {
            scene.issue('Conditional panel inclusion needs supplied evaluation evidence.');
            continue;
        }
        const source = resolveRecord(scene.all, inclusion.target, scene.view.file);
        if (!source) {
            scene.issue('Panel target does not resolve.');
            continue;
        }
        const metadata = object(pathValue(source.record, 'metadata.x_record')), defaults = template?.[1].find(p => p[0] === metadata.id || p[0] === source.record.name || p[0] === source.ref.id), id = inclusion.kind === 'view' ? refKey(scene.view.ref) + ':panel:' + index : str(metadata.id, str(source.record.name, source.ref.id)), itemRefs = array(metadata.items), items = itemRefs.map(ref => resolveRecord(scene.all, ref, source.file)).filter((r) => !!r);
        if (items.length !== itemRefs.length)
            scene.issue('Panel content reference does not resolve.');
        const placement = { ...metadata, ...object(inclusion.layout) };
        const panel = { id, title: str(inclusion.title, titleOf(source.record)), source, row: num(placement.row, defaults?.[2] ?? Math.floor(index / columns)), column: num(placement.column, defaults?.[3] ?? index % columns), colspan: num(placement.colspan, defaults?.[4] ?? 1), rowspan: num(placement.rowspan, defaults?.[5] ?? 1), items };
        if (source.owner === 'view' && inclusion.kind === 'view')
            panel.child = source;
        if (panel.child && items.length)
            scene.issue('A composed panel contains item references or a child view, never both.');
        panels.push(panel);
    }
    if (!panels.length && template)
        for (const [id, title, row, column, colspan, rowspan] of template[1])
            panels.push({ id, title, row, column, colspan, rowspan, source: scene.view, items: [] });
    if (panels.length > 80 || panels.some(p => ![p.row, p.column, p.colspan, p.rowspan].every(Number.isInteger) || p.row < 0 || p.row > 100 || p.column < 0 || p.colspan < 1 || p.rowspan < 1 || p.row + p.rowspan > 101 || p.column + p.colspan > columns)) {
        scene.issue('Panel bounds or spans are outside the declared grid.');
        return;
    }
    const occupied = new Set();
    for (const panel of panels)
        for (let y = panel.row; y < panel.row + panel.rowspan; y++)
            for (let x = panel.column; x < panel.column + panel.colspan; x++) {
                const key = `${x}:${y}`;
                if (occupied.has(key))
                    scene.issue('Panel grid cells overlap.');
                occupied.add(key);
            }
    if (template && template[1].some(p => !panels.some(panel => panel.id === p[0])))
        scene.issue('Required canvas panels are missing.');
    if (scene.result.unavailable.length)
        return;
    if (profile === 'panels.venn@1') {
        drawVenn(scene, panels);
        return;
    }
    if (profile === 'panels.pyramid@1') {
        panels.sort((a, b) => a.row - b.row);
        if (panels.length < 3 || panels.length > 5 || columns !== 1 || panels.some((panel, index) => panel.row !== index || panel.column !== 0 || panel.colspan !== 1 || panel.rowspan !== 1)) {
            scene.issue('Pyramid requires three to five contiguous one-column bands.');
            return;
        }
        drawPyramid(scene, panels);
        return;
    }
    const s = fontScale(scene), gap = 22 * s, padding = 18 * s, rowCount = Math.max(1, ...panels.map(p => p.row + p.rowspan));
    let unitWidth = Math.max(230 * s, (num(settings.width, scene.bounds.width) - gap * (columns - 1)) / columns);
    const childSizes = new Map();
    for (const panel of panels.filter(p => p.child)) {
        if (profile !== 'panels.composed@1' || panel.child.record.profile === 'panels.composed@1' || refKey(panel.child.ref) === refKey(scene.view.ref)) {
            scene.issue('Only one child-view level is permitted in composed panels.');
            continue;
        }
        if (!scene.options.projectChild) {
            scene.issue('Child-view projection adapter is unavailable.');
            continue;
        }
        // Ask the same new-IR adapter for natural child geometry before allocating its panel.
        const child = scene.options.projectChild(panel.child, { x: scene.bounds.x, y: scene.bounds.y, width: 1050 * s, height: 650 * s });
        childSizes.set(panel, child.bounds);
        unitWidth = Math.max(unitWidth, (child.bounds.width + padding * 2 - gap * (panel.colspan - 1)) / panel.colspan);
    }
    const width = unitWidth * columns + gap * (columns - 1), rowHeights = Array.from({ length: rowCount }, () => 160 * s);
    const panelWidth = (panel) => unitWidth * panel.colspan + gap * (panel.colspan - 1);
    const headings = new Map(panels.map(panel => [panel, lines(scene, panel.title, panelWidth(panel) - padding * 2, 14)]));
    const headerHeight = (panel) => (headings.get(panel).length * 20 + 24) * s;
    const content = new Map(panels.map(panel => [panel, panel.items.map(item => ({ item, title: lines(scene, titleOf(item.record), panelWidth(panel) - padding * 2, 14), body: lines(scene, str(pathValue(item.record, 'content.text')), panelWidth(panel) - padding * 2, 12) }))]));
    for (const panel of [...panels].sort((a, b) => a.rowspan - b.rowspan)) {
        const emotion = profile === 'panels.journey@1' && panel.id === 'emotions';
        const childHeight = childSizes.get(panel)?.height;
        const needed = headerHeight(panel) + (emotion ? 220 * s : childHeight !== undefined ? childHeight + padding * 2 : 20 * s + sum(content.get(panel).map(item => (item.title.length * 20 + (item.body.some(Boolean) ? item.body.length * 18 : 0) + 25) * s)));
        const existing = sum(rowHeights.slice(panel.row, panel.row + panel.rowspan)) + gap * (panel.rowspan - 1), extra = Math.max(0, needed - existing) / panel.rowspan;
        for (let row = panel.row; row < panel.row + panel.rowspan; row++)
            rowHeights[row] += extra;
    }
    const minimum = num(settings.height), current = sum(rowHeights) + gap * (rowCount - 1);
    if (minimum > current)
        for (let row = 0; row < rowCount; row++)
            rowHeights[row] += (minimum - current) / rowCount;
    const rowTop = (row) => scene.bounds.y + sum(rowHeights.slice(0, row)) + row * gap;
    surfaceBounds(scene, width, sum(rowHeights) + gap * (rowCount - 1) + 24 * s);
    const frames = new Map();
    for (const panel of panels) {
        const b = { x: scene.bounds.x + panel.column * (unitWidth + gap), y: rowTop(panel.row), width: panelWidth(panel), height: sum(rowHeights.slice(panel.row, panel.row + panel.rowspan)) + gap * (panel.rowspan - 1) }, header = headerHeight(panel);
        frames.set(panel, b);
        scene.add(panel.title, b, [box(b, '#ffffff', '#94a3b8'), ...block(headings.get(panel), b.x + padding, b.y + 28 * s, 14, 20 * s, { 'font-weight': 700 }), path(`M${b.x},${b.y + header}h${b.width}`, '#cbd5e1')], panel.source, [panel.source.ref], '', true);
        const headingEntry = scene.result.entries.at(-1);
        scene.result.entries[scene.result.entries.length - 1] = { ...headingEntry, item: { ...headingEntry.item, clip: { x: b.x - 1, y: b.y - 1, width: b.width + 2, height: b.height + 2 } } };
        if (panel.child && childSizes.has(panel) && scene.options.projectChild) {
            const natural = childSizes.get(panel);
            const childBounds = { x: b.x + padding + Math.max(0, b.width - padding * 2 - natural.width) / 2, y: b.y + header + padding, width: natural.width, height: natural.height };
            const child = scene.options.projectChild(panel.child, childBounds);
            scene.result.entries.push(...child.entries.map(entry => ({ ...entry, item: { ...entry.item, occurrence: `panel:${panel.id}:${entry.item.occurrence}`, view: scene.view.ref, clip: entry.item.clip ? intersectClip(entry.item.clip, b) : b } })));
            scene.result.diagnostics.push(...child.diagnostics);
            scene.result.unavailable.push(...child.unavailable);
        }
        // Emotion records are measurements on the curve, not duplicate note cards.
        if (profile === 'panels.journey@1' && panel.id === 'emotions')
            continue;
        let y = b.y + header + 26 * s;
        for (const item of content.get(panel)) {
            const body = item.body.some(Boolean) ? item.body : [], h = (item.title.length * 20 + body.length * 18 + 25) * s;
            const contentBounds = { x: b.x + padding, y: y - 16 * s, width: b.width - padding * 2, height: h - 12 * s };
            scene.add([titleOf(item.item.record), str(pathValue(item.item.record, 'content.text'))].filter(Boolean).join(': '), contentBounds, [box(contentBounds, 'none', 'none'), ...block(item.title, contentBounds.x, y, 14, 20 * s, { 'font-weight': 600 }), ...block(body, contentBounds.x, y + item.title.length * 20 * s, 12, 18 * s)], item.item, [item.item.ref], '', true);
            y += h;
        }
    }
    if (profile === 'panels.journey@1') {
        const phases = panels.filter(p => p.id.startsWith('phase-')).sort((a, b) => a.column - b.column), emotions = panels.find(p => p.id === 'emotions');
        if (phases.length < 2 || phases.length > 8 || !emotions) {
            scene.issue('Journey requires 2..8 phases and an emotions panel.');
            return;
        }
        const b = frames.get(emotions), top = b.y + headerHeight(emotions) + 34 * s, bottom = b.y + b.height - 30 * s, points = [], contributors = [], primitives = [];
        for (let value = 1; value <= 5; value++) {
            const y = bottom - (value - 1) / 4 * (bottom - top);
            primitives.push(path(`M${b.x + 34 * s},${y}H${b.x + b.width - 18 * s}`, '#dbe3ed'), label(String(value), b.x + 20 * s, y + 4 * s, 11, { 'text-anchor': 'middle' }));
        }
        for (const phase of phases) {
            const slug = phase.id.slice(6), matches = emotions.items.filter(item => pathValue(item.record, 'metadata.x_record.phase') === slug), item = matches[0], value = pathValue(item?.record, 'metadata.x_record.value');
            if (matches.length !== 1 || !item || !finite(value) || value < 1 || value > 5) {
                scene.issue('Journey emotions require one supplied 1..5 value for each phase.');
                continue;
            }
            const frame = frames.get(phase), point = [frame.x + frame.width / 2, bottom - (value - 1) / 4 * (bottom - top)];
            points.push(point);
            contributors.push(item.ref);
            primitives.push(ellipse(point[0], point[1], 5 * s, colors[0]), label(String(value), point[0], point[1] - 12 * s, 12, { 'font-weight': 700, 'text-anchor': 'middle' }));
        }
        if (points.length === phases.length) {
            primitives.unshift(path(pointsPath(points), colors[0], 'none', { 'stroke-width': 2.5 }));
            scene.add('Declared journey emotions', b, primitives, emotions.source, contributors, 'Scale 1–5. Straight segments connect supplied phase-ordered values.');
        }
    }
}
function drawPyramid(scene, panels) {
    const s = fontScale(scene), width = Math.max(num(scene.settings.width, scene.bounds.width), 560 * s), cx = scene.bounds.x + width / 2, noteWidth = 240 * s, gap = 10 * s;
    const content = panels.map(panel => panel.items.flatMap(item => lines(scene, titleOf(item.record) + (pathValue(item.record, 'content.text') ? ': ' + str(pathValue(item.record, 'content.text')) : ''), noteWidth, 11)));
    const bandHeight = Math.max(150 * s, ...content.map(text => (text.length * 17 + 48) * s)), height = panels.length * (bandHeight + gap) + 24 * s;
    surfaceBounds(scene, width + noteWidth + 36 * s, height);
    panels.forEach((panel, index) => {
        const topWidth = width * (index + 1) / (panels.length + 1), bottomWidth = width * (index + 2) / (panels.length + 1), y = scene.bounds.y + index * (bandHeight + gap), color = colors[index % colors.length], b = { x: cx - bottomWidth / 2, y, width: bottomWidth, height: bandHeight };
        const heading = lines(scene, panel.title, (topWidth + bottomWidth) / 2 - 32 * s, 14);
        scene.add(panel.title, b, [path(pointsPath([[cx - topWidth / 2, y], [cx + topWidth / 2, y], [cx + bottomWidth / 2, y + bandHeight], [cx - bottomWidth / 2, y + bandHeight]], true), color, color, { 'fill-opacity': .18, 'stroke-width': 1.6 }), ...block(heading, cx, y + bandHeight / 2 - (heading.length - 1) * 20 * s / 2 + 5 * s, 14, 20 * s, { 'text-anchor': 'middle', 'font-weight': 700 })], panel.source);
        let noteY = y + 26 * s;
        for (const item of panel.items) {
            const text = titleOf(item.record) + (pathValue(item.record, 'content.text') ? ': ' + str(pathValue(item.record, 'content.text')) : ''), wrapped = lines(scene, text, noteWidth, 11), x = cx + bottomWidth / 2 + 18 * s;
            scene.add(text, { x, y: noteY - 12 * s, width: noteWidth, height: wrapped.length * 17 * s }, block(wrapped, x, noteY, 11, 17 * s), item);
            noteY += wrapped.length * 17 * s + 8 * s;
        }
    });
}
function drawVenn(scene, panels) {
    if (panels.length < 2 || panels.length > 3) {
        scene.issue('Venn requires two or three set panels.');
        return;
    }
    const s = fontScale(scene), width = Math.max(640 * s, num(scene.settings.width, scene.bounds.width)), height = Math.max(440 * s, num(scene.settings.height, 600 * s));
    surfaceBounds(scene, width, height);
    const radius = Math.min(width, height) * .3, cx = scene.bounds.x + width / 2, cy = scene.bounds.y + height / 2 + 10 * s, distance = radius * .6;
    const centers = panels.length === 2 ? [[cx - radius * .5, cy], [cx + radius * .5, cy]] : [[cx - .866 * distance, cy - distance * .5], [cx + .866 * distance, cy - distance * .5], [cx, cy + distance]];
    panels.forEach((panel, i) => {
        const p = centers[i], dx = p[0] - cx, dy = p[1] - cy, d = Math.hypot(dx, dy), x = p[0] + dx / d * (radius + 18 * s), y = p[1] + dy / d * (radius + 18 * s), anchor = Math.abs(dx) < .1 ? 'middle' : dx < 0 ? 'end' : 'start';
        scene.add(panel.title, { x: p[0] - radius, y: p[1] - radius, width: radius * 2, height: radius * 2 }, [ellipse(p[0], p[1], radius, colors[i], { 'fill-opacity': .16, stroke: colors[i], 'stroke-width': 1.8 }), label(panel.title, x, y + 4 * s, 14, { 'text-anchor': anchor, 'font-weight': 600 })], panel.source);
    });
    const members = new Map();
    panels.forEach(panel => panel.items.forEach(item => members.set(refKey(item.ref), item)));
    const groups = new Map();
    for (const item of members.values()) {
        const ids = array(pathValue(item.record, 'metadata.x_sets')).map(String), mask = panels.reduce((mask, p, i) => ids.includes(p.id) ? mask | (1 << i) : mask, 0);
        if (!mask || ids.some(id => !panels.some(p => p.id === id))) {
            scene.issue('Venn member declares an unknown set.');
            continue;
        }
        const appearances = panels.filter(p => p.items.some(i => refKey(i.ref) === refKey(item.ref))).map(p => p.id);
        if (ids.length !== appearances.length || ids.some(id => !appearances.includes(id)))
            scene.issue('Venn membership does not match declared panel appearances.');
        groups.set(mask, [...groups.get(mask) ?? [], item]);
    }
    const locations = panels.length === 2 ? { 1: [cx - radius * .9, cy], 2: [cx + radius * .9, cy], 3: [cx, cy] } : { 1: [cx - radius * .9, cy - radius * .45], 2: [cx + radius * .9, cy - radius * .45], 3: [cx, cy - radius * .65], 4: [cx, cy + radius * 1.1], 5: [cx - radius * .5, cy + radius * .45], 6: [cx + radius * .5, cy + radius * .45], 7: [cx, cy + radius * .05] };
    for (let mask = 1; mask < (1 << panels.length); mask++) {
        const p = locations[mask], items = groups.get(mask) ?? [];
        scene.add(`Declared membership ${mask}: ${items.length}`, { x: p[0] - 10, y: p[1] - 10, width: 20, height: 20 }, [label(String(items.length), p[0], p[1] + 4, 14, { 'text-anchor': 'middle', 'font-weight': 700 })], items[0] ?? scene.view, items.map(i => i.ref), 'Schematic areas do not encode cardinality.');
    }
}
export function intersectClip(a, b) {
    const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) };
}
/** Civil milliseconds encode selected-zone calendar fields on a UTC-shaped axis. */
const civilFormatters = new Map();
export function civilTime(instant, zone) {
    let formatter = civilFormatters.get(zone);
    if (!formatter) {
        if (civilFormatters.size >= 64)
            civilFormatters.clear();
        formatter = new Intl.DateTimeFormat('en-CA', { timeZone: zone, calendar: 'iso8601', numberingSystem: 'latn', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
        civilFormatters.set(zone, formatter);
    }
    const parts = formatter.formatToParts(instant);
    const get = (type) => Number(parts.find(part => part.type === type)?.value);
    const result = new Date(0);
    result.setUTCFullYear(get('year'), get('month') - 1, get('day'));
    result.setUTCHours(get('hour'), get('minute'), get('second'), ((instant % 1000) + 1000) % 1000);
    return result.getTime();
}
export function timelineMoment(value, zone) {
    const parsed = numericDate(value);
    if (parsed === undefined)
        throw new Error('Timeline dates must be ISO dates or zoned timestamps.');
    const dateOnly = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
    if (!dateOnly)
        return { instant: parsed, civil: civilTime(parsed, zone), dateOnly };
    let instant = parsed;
    for (let i = 0; i < 6; i++) {
        const delta = parsed - civilTime(instant, zone);
        if (delta === 0)
            return { instant, civil: parsed, dateOnly };
        instant += delta;
    }
    throw new Error('The date has no unambiguous midnight in the selected timezone.');
}
export function businessDays(start, end, weekdays, holidays = []) {
    const day = 86400000;
    if (!finite(start) || !finite(end) || end < start)
        throw new Error('End precedes start or the calendar boundary is not finite.');
    if (Math.ceil(end / day) - Math.floor(start / day) > 366000)
        throw new Error('Calendar span exceeds 366000 days.');
    if (weekdays.some(value => !Number.isInteger(value) || value < 1 || value > 7) || new Set(weekdays).size !== weekdays.length)
        throw new Error('Weekdays must be distinct ISO weekday numbers 1..7.');
    if (new Set(holidays).size !== holidays.length || holidays.some(value => !/^\d{4}-\d{2}-\d{2}$/.test(value) || numericDate(value) === undefined))
        throw new Error('Holidays must be distinct valid date-only values.');
    const excluded = new Set(holidays);
    let result = 0;
    for (let cursor = start; cursor < end;) {
        const next = Math.min(end, (Math.floor(cursor / day) + 1) * day), date = new Date(cursor);
        if (weekdays.includes((date.getUTCDay() + 6) % 7 + 1) && !excluded.has(date.toISOString().slice(0, 10)))
            result += (next - cursor) / day;
        cursor = next;
    }
    return result;
}
export function businessCalendarPosition(start, end, weekdays, holidays = []) {
    businessDays(start, start, weekdays, holidays);
    const day = 86400000, first = Math.floor(start / day), last = Math.ceil(end / day), length = last - first;
    if (length < 0 || length > 366000)
        throw new Error('Calendar span exceeds 366000 days or end precedes start.');
    const prefix = new Float64Array(length + 1), active = new Uint8Array(length), excluded = new Set(holidays);
    for (let i = 0; i < length; i++) {
        const date = new Date((first + i) * day);
        active[i] = weekdays.includes((date.getUTCDay() + 6) % 7 + 1) && !excluded.has(date.toISOString().slice(0, 10)) ? 1 : 0;
        prefix[i + 1] = prefix[i] + active[i];
    }
    const coordinate = (time) => {
        const relative = time - first * day, index = Math.floor(relative / day);
        if (index === length && relative === length * day)
            return prefix[length];
        if (index < 0 || index >= length)
            throw new Error('Calendar position lies outside its planned interval.');
        return prefix[index] + (relative - index * day) / day * active[index];
    };
    const base = coordinate(start);
    return time => coordinate(time) - base;
}
export function drawTimeline(scene) {
    const settings = scene.settings, data = scene.data(), startKey = str(settings.start, 'start'), endKey = str(settings.end, 'end'), labelKey = str(settings.label, 'label'), zone = str(settings.timezone, 'UTC'), calendar = str(settings.calendar, 'gregorian');
    if (!['gregorian', 'fiscal', 'business'].includes(calendar)) {
        scene.issue('Timeline calendar must be gregorian, fiscal or business.');
        return;
    }
    let formatter, items;
    try {
        formatter = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' });
        items = data.map(datum => { const rawStart = valueAt(datum.values, startKey), rawEnd = valueAt(datum.values, endKey); return { datum, start: timelineMoment(rawStart, zone), end: timelineMoment(rawEnd == null ? rawStart : rawEnd, zone) }; });
    }
    catch (error) {
        scene.issue(`Timezone/date ${zone}: ${String(error)}`);
        return;
    }
    if (items.some(item => item.end.instant < item.start.instant)) {
        scene.issue('Timeline end cannot precede start.');
        return;
    }
    if (!items.length)
        return;
    const calendarSettings = { ...object(scene.effective.calendar), ...object(scene.view.record.calendar) }, weekdays = Array.isArray(calendarSettings.weekdays) ? array(calendarSettings.weekdays).filter(finite) : [1, 2, 3, 4, 5], holidays = array(calendarSettings.holidays).map(String), fiscal = num(settings.fiscal_year_start, num(calendarSettings.fiscal_start_month, 1));
    if (!Number.isInteger(fiscal) || fiscal < 1 || fiscal > 12) {
        scene.issue('Fiscal year start must be in 1..12.');
        return;
    }
    const coordinate = (moment) => calendar === 'business' ? moment.civil : moment.instant;
    const minimum = Math.min(...items.map(item => coordinate(item.start))), maximum = Math.max(...items.map(item => coordinate(item.end))), position = (moment) => calendar === 'business' ? businessPosition(moment.civil) : moment.instant - minimum;
    let businessPosition = time => time - minimum;
    let span;
    try {
        businessDays(minimum, minimum, weekdays, holidays);
        if (calendar === 'business')
            businessPosition = businessCalendarPosition(minimum, maximum, weekdays, holidays);
        span = (calendar === 'business' ? businessPosition(maximum) : maximum - minimum) || 1;
    }
    catch (error) {
        scene.issue(String(error));
        return;
    }
    const s = fontScale(scene), names = items.map(item => String(valueAt(item.datum.values, labelKey) ?? titleOf(item.datum.source.record)));
    const labelWidth = Math.max(180 * s, Math.min(300 * s, Math.max(...names.map(name => scene.measure(name, 12))) + 24 * s)), width = Math.max(360 * s, num(settings.width, scene.bounds.width) - labelWidth - 16 * s), left = scene.bounds.x + labelWidth, axis = scene.bounds.y + (calendar === 'fiscal' ? 52 : 36) * s;
    const nameLines = names.map(name => lines(scene, name, labelWidth - 24 * s, 12)), rowHeights = nameLines.map(text => Math.max(42 * s, (text.length * 18 + 18) * s)), bodyHeight = sum(rowHeights);
    const caption = lines(scene, `${calendar[0].toUpperCase() + calendar.slice(1)} calendar · ${zone} · Intervals are end-exclusive; diamonds are milestones.` + (calendar === 'business' ? ' Non-working weekdays and holidays are excluded.' : ''), labelWidth + width, 11);
    surfaceBounds(scene, labelWidth + width + 16 * s, axis - scene.bounds.y + bodyHeight + (caption.length * 16 + 30) * s);
    const format = (moment) => {
        const date = new Date(moment.civil), base = moment.dateOnly ? date.toISOString().slice(0, 10) : formatter.format(moment.instant);
        const month = date.getUTCMonth() + 1, fiscalYear = date.getUTCFullYear() + (fiscal > 1 && month >= fiscal ? 1 : 0), quarter = Math.floor((month - fiscal + 12) % 12 / 3) + 1;
        return base + (calendar === 'fiscal' ? ` · FY${fiscalYear} Q${quarter}` : '');
    };
    const first = items.reduce((a, b) => coordinate(a.start) < coordinate(b.start) ? a : b).start, last = items.reduce((a, b) => coordinate(a.end) > coordinate(b.end) ? a : b).end;
    const ticks = [first], tickCount = Math.max(2, Math.min(7, Math.floor(width / ((calendar === 'fiscal' ? 200 : 110) * s)))), days = (last.civil - first.civil) / 86400000;
    if (days >= 1) {
        const step = Math.max(1, Math.ceil(days / tickCount));
        for (let civil = (Math.floor(first.civil / 86400000) + step) * 86400000; civil < last.civil; civil += step * 86400000) {
            const tick = timelineMoment(new Date(civil).toISOString().slice(0, 10), zone);
            if (coordinate(tick) > minimum && coordinate(tick) < maximum)
                ticks.push(tick);
        }
    }
    else if (maximum > minimum) {
        for (let i = 1; i < tickCount; i++) {
            const instant = first.instant + (last.instant - first.instant) * i / tickCount;
            ticks.push({ instant, civil: civilTime(instant, zone), dateOnly: false });
        }
    }
    if (last.instant !== first.instant)
        ticks.push(last);
    const tickText = (moment) => days < 1 && !moment.dateOnly ? new Intl.DateTimeFormat('en-GB', { timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(moment.instant) : format(moment);
    const axisPrimitives = [path(`M${left},${axis}h${width}`)];
    let previous = -Infinity;
    ticks.forEach((tick, i) => {
        const x = left + position(tick) / span * width, text = tickText(tick), anchor = i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle', textWidth = scene.measure(text, 10), textLeft = x - (anchor === 'middle' ? textWidth / 2 : anchor === 'end' ? textWidth : 0);
        axisPrimitives.push(path(`M${x},${axis}v${bodyHeight}`, '#dbe3ed'));
        // Always retain both endpoints; omit an intermediate label when it would collide.
        if (i !== 0 && i !== ticks.length - 1 && (textLeft < previous + 10 * s || x + textWidth / 2 > left + width - scene.measure(tickText(last), 10) - 12 * s))
            return;
        axisPrimitives.push(label(text, x, axis - 10 * s, 10, { 'text-anchor': anchor }));
        previous = textLeft + textWidth;
    });
    scene.add('Timeline axis', { x: left, y: scene.bounds.y, width, height: axis - scene.bounds.y + bodyHeight }, axisPrimitives);
    const byRef = new Map();
    let rowTop = axis;
    items.forEach((item, index) => {
        const x = left + position(item.start) / span * width, end = left + position(item.end) / span * width, height = rowHeights[index], y = rowTop + (height - 22 * s) / 2, b = { x, y, width: Math.max(4 * s, end - x), height: 22 * s }, title = names[index], color = colors[index % colors.length];
        const primitives = [path(`M${scene.bounds.x},${rowTop + height}H${left + width}`, '#e2e8f0'), ...block(nameLines[index], scene.bounds.x + 3 * s, rowTop + height / 2 - (nameLines[index].length - 1) * 18 * s / 2 + 4 * s, 12, 18 * s), item.start.instant === item.end.instant ? path(pointsPath([[x, y], [x + 7 * s, y + 11 * s], [x, y + 22 * s], [x - 7 * s, y + 11 * s]], true), color, color) : box(b, color, 'none')];
        const elapsed = (item.end.instant - item.start.instant) / 3600000, wall = (item.end.civil - item.start.civil) / 3600000;
        scene.add(`${title}: ${format(item.start)}–${format(item.end)}`, b, primitives, item.datum.source, item.datum.contributors, `${elapsed} elapsed hours; ${wall} wall hours in ${zone}.` + (calendar === 'business' ? ' Business days are end-exclusive; local weekdays and holidays are excluded.' : ''));
        byRef.set(refKey(item.datum.source.ref), [...byRef.get(refKey(item.datum.source.ref)) ?? [], b]);
        rowTop += height;
    });
    scene.add('Timeline calendar', { x: scene.bounds.x, y: rowTop + 10 * s, width: labelWidth + width, height: (caption.length * 16 + 20) * s }, block(caption, scene.bounds.x, rowTop + 28 * s, 11, 16 * s));
    for (const ref of array(settings.dependencies)) {
        const relation = resolveRecord(scene.all, ref, scene.view.file);
        if (!relation) {
            scene.issue('Timeline dependency does not resolve.');
            continue;
        }
        const ends = array(relation.record.endpoints).map(end => resolveRecord(scene.all, object(end).definition, relation.file)), aa = ends[0] ? byRef.get(refKey(ends[0].ref)) : undefined, bb = ends[1] ? byRef.get(refKey(ends[1].ref)) : undefined, a = aa?.length === 1 ? aa[0] : undefined, b = bb?.length === 1 ? bb[0] : undefined;
        if (!a || !b) {
            scene.issue('Timeline dependency endpoints must identify one unambiguous displayed record each.');
            continue;
        }
        const x = a.x + a.width, y = a.y + a.height / 2, x2 = b.x, y2 = b.y + b.height / 2;
        scene.add(titleOf(relation.record), { x: Math.min(x, x2), y: Math.min(y, y2), width: Math.max(1, Math.abs(x - x2)), height: Math.max(1, Math.abs(y - y2)) }, [path(`M${x},${y}h8V${y2}H${x2}`), path(`M${x2 - 6 * s},${y2 - 4 * s}L${x2},${y2}L${x2 - 6 * s},${y2 + 4 * s}Z`, '#64748b', '#64748b')], relation);
    }
}
function scalar(value) { return typeof value === 'string' ? JSON.stringify(value) : value === undefined ? 'missing' : JSON.stringify(value); }
function predicateText(value) {
    if (value === undefined)
        return 'any';
    if (value === null || typeof value !== 'object')
        return '= ' + scalar(value);
    const predicate = object(value), op = str(predicate.op), signs = { eq: '=', ne: '≠', lt: '<', lte: '≤', gt: '>', gte: '≥' };
    if (signs[op])
        return signs[op] + ' ' + scalar(predicate.value);
    if (op === 'interval')
        return `${predicate.include_min === false ? '(' : '['}${predicate.min === undefined ? '−∞' : scalar(predicate.min)}, ${predicate.max === undefined ? '∞' : scalar(predicate.max)}${predicate.include_max === false ? ')' : ']'}`;
    if (op === 'in')
        return 'in ' + array(predicate.values ?? predicate.value).map(scalar).join(', ');
    if (op === 'null' || op === 'missing')
        return op;
    if (op === 'exists')
        return predicate.value === false ? 'missing' : 'present';
    return scalar(value);
}
export function drawDecision(scene) {
    const settings = scene.settings, data = scene.data(), key = (ref) => typeof ref === 'string' ? ref : (() => { const record = lookup(scene, ref); return record ? str(record.record.name, record.ref.id) : ''; })(), inputRefs = array(settings.inputs), outputRefs = array(settings.outputs), inputs = inputRefs.map(key), outputs = outputRefs.map(key);
    if (!inputs.length || inputs.length > 8 || !outputs.length || outputs.length > 20 || inputs.some(k => !k) || outputs.some(k => !k)) {
        scene.issue('Decision table needs 1..8 resolved inputs and 1..20 outputs.');
        return;
    }
    const human = (ref) => { const record = lookup(scene, ref); return record ? titleOf(record.record) : key(ref); };
    const columns = ['Rule', ...inputRefs.map(ref => `If ${human(ref)}`), ...outputRefs.map(ref => `Then ${human(ref)}`)], policy = str(settings.hit_policy, 'unique'), s = fontScale(scene);
    const rules = data.map((datum, index) => {
        const rule = datum.source.owner === 'data' || datum.row !== undefined ? datum.values : object(pathValue(datum.source.record, 'metadata.x_rule')), conditions = object(rule.inputs), conclusions = object(rule.outputs);
        if (outputs.some(k => !Object.hasOwn(conclusions, k)))
            scene.issue('Each decision rule must supply every output.', 'DDN-DECISION-OUTPUT', 'error', datum.source.ref);
        const title = datum.source.owner === 'data' || datum.row !== undefined ? str(rule.title, str(rule.label, str(rule.name, `Rule ${index + 1}`))) : titleOf(datum.source.record);
        return { datum, cells: [title, ...inputs.map(k => predicateText(conditions[k])), ...outputs.map(k => Object.hasOwn(conclusions, k) ? scalar(conclusions[k]) : 'missing')], evidence: ['', ...inputs.map(k => JSON.stringify(conditions[k]) ?? 'any'), ...outputs.map(k => JSON.stringify(conclusions[k]) ?? 'missing')] };
    });
    const widths = columns.map((title, ci) => Math.max(130 * s, Math.min(330 * s, Math.max(scene.measure(title, 13), ...rules.map(row => scene.measure(row.cells[ci], 13))) + 28 * s)));
    const remaining = Math.max(0, num(settings.width, scene.bounds.width) - sum(widths));
    widths.forEach((_value, i) => widths[i] += remaining / widths.length);
    const width = sum(widths), heads = columns.map((title, i) => lines(scene, title, widths[i] - 24 * s, 13)), headHeight = Math.max(44 * s, ...heads.map(text => (text.length * 19 + 24) * s)), rows = rules.map(row => row.cells.map((value, i) => lines(scene, value, widths[i] - 24 * s, 13))), rowHeights = rows.map(row => Math.max(42 * s, (Math.max(...row.map(text => text.length)) * 19 + 24) * s));
    const analysis = object(analyzeProfile(scene.snapshot.normalized, scene.view.ref)), tested = num(analysis.tested), uncovered = array(analysis.uncovered), overlaps = array(analysis.overlaps), errors = array(analysis.errors), complete = tested > 0 && !uncovered.length && !errors.length && analysis.outcome !== 'budget_exceeded';
    const coverage = complete ? 'Coverage complete' : analysis.outcome === 'budget_exceeded' ? 'Coverage not proven: analysis budget exceeded' : errors.length ? 'Coverage unavailable: invalid contract' : tested ? `Coverage incomplete: ${uncovered.length} uncovered partition${uncovered.length === 1 ? '' : 's'}` : 'Coverage not checked';
    const firstHit = object(analysis.firstHit), shadowed = policy === 'first' ? firstHit.outcome === 'complete' && Array.isArray(firstHit.shadowed) ? `Shadowed first-hit rules: ${firstHit.shadowed.length}.` : 'Shadowed first-hit rules: unknown (analysis incomplete).' : '';
    const explanation = [shadowed, tested ? `Partition analysis tested ${tested} boundary/interior combinations.` : '', complete ? 'No uncovered atom in the declared input domains.' : '', overlaps.length ? `${overlaps.length} overlapping rule combination${overlaps.length === 1 ? '' : 's'}.` : tested ? analysis.outcome === 'budget_exceeded' ? 'No overlaps found among tested partitions.' : 'No overlapping rules.' : '', policy === 'first' ? 'First-match precedence follows the displayed rule order.' : policy === 'unique' ? 'Unique policy permits at most one matching rule.' : `Hit policy: ${policy}; rules retain their declared order.`].filter(Boolean).join(' ');
    const footerLines = lines(scene, explanation, width - 24 * s, 11), topLines = lines(scene, `Hit policy: ${policy} · ${coverage}`, width - 80 * s, 13), topHeight = (topLines.length * 20 + 16) * s;
    surfaceBounds(scene, width, topHeight + headHeight + sum(rowHeights) + (footerLines.length * 17 + 30) * s);
    scene.add(`Decision hit policy: ${policy}. ${coverage}`, { x: scene.bounds.x, y: scene.bounds.y, width, height: topHeight }, block(topLines, scene.bounds.x + 12 * s, scene.bounds.y + 22 * s, 13, 20 * s, { 'font-weight': 600 }));
    const badge = { x: scene.bounds.x + width - 44 * s, y: scene.bounds.y + 5 * s, width: 36 * s, height: 26 * s };
    scene.add(coverage, badge, [box(badge, complete ? '#e5f2ec' : '#fff4df', 'none'), label(complete ? 'C+' : tested && analysis.outcome !== 'budget_exceeded' ? 'C−' : '?', badge.x + badge.width / 2, badge.y + 18 * s, 12, { 'text-anchor': 'middle', 'font-weight': 700 })], scene.view, [scene.view.ref], 'Coverage badge reports the bounded partition analysis, independently of the hit policy.');
    let x = scene.bounds.x, y = scene.bounds.y + topHeight;
    columns.forEach((name, ci) => { const b = { x, y, width: widths[ci], height: headHeight }; scene.add(name, b, [box(b, '#eef2f6'), ...block(heads[ci], x + 12 * s, y + 26 * s, 13, 19 * s, { 'font-weight': 700 })]); x += widths[ci]; });
    y += headHeight;
    rules.forEach((rule, ri) => {
        x = scene.bounds.x;
        rule.cells.forEach((text, ci) => { const b = { x, y, width: widths[ci], height: rowHeights[ri] }; scene.add(`${columns[ci]}: ${text}${rule.evidence[ci] ? ` (${rule.evidence[ci]})` : ''}`, b, [box(b, ri % 2 ? '#f5f7fb' : '#ffffff'), ...block(rows[ri][ci], x + 12 * s, y + 26 * s, 13, 19 * s, ci === 0 ? { 'font-weight': 600 } : {})], rule.datum.source, rule.datum.contributors); x += widths[ci]; });
        y += rowHeights[ri];
    });
    scene.add('Decision coverage evidence', { x: scene.bounds.x, y, width, height: (footerLines.length * 17 + 30) * s }, block(footerLines, scene.bounds.x + 12 * s, y + 24 * s, 11, 17 * s), scene.view, [scene.view.ref, ...data.flatMap(datum => datum.contributors)], 'Read-only bounded analysis of the declared input domains and typed predicates.');
}
//# sourceMappingURL=data-surfaces.js.map