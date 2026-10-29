import { cardTextLayout } from './card-text.js';
import { fixedViewSurface, fitSurfaceContent } from './view-surface.js';
import { array, object, pathValue, num, str, records, resolveRecord, refKey, titleOf, tableData } from './model.js';
import { layoutTable, wrapCell } from './table.js';
import { standaloneNode, notePrimitives } from './symbol-presentation.js';
import { recordTableData } from './records.js';
import { projectNativeGraph } from './graph-native.js';
import { availableProjectionProfiles, graphProjector, dataProjector, isGraphProfile, isDataProfile } from './adapters.js';
export { availableProjectionProfiles } from './adapters.js';
import { roleDescriptor } from '../../profiles/src/core.js';
import { isMindmapTopic, mindmapKey, mindmapRelationKind } from '../../profiles/src/mindmap.js';
import { isometricGraph } from './graph-isometric.js';
import { decoratePaper } from './stationery.js';
import { nativeCode, nativeIcon, nativeContour, nativeBadges, badgePrimitives, inheritedPresentation } from './native-render.js';
import { publicationPageSize } from './publication.js';
import { prepareRelationPresentation, relationPresentation, relationLegendVisible } from './relation-presentation.js';
import { edgeLabel } from './graph-common.js';
const identity = [1, 0, 0, 1, 0, 0];
export function unionBounds(items) {
    if (!items.length)
        return { x: 0, y: 0, width: 640, height: 480 };
    const x = Math.min(...items.map(i => i.x)), y = Math.min(...items.map(i => i.y));
    return { x, y, width: Math.max(1, Math.max(...items.map(i => i.x + i.width)) - x), height: Math.max(1, Math.max(...items.map(i => i.y + i.height)) - y) };
}
function intersectBounds(a, b) {
    const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) };
}
const rect = (bounds, fill, stroke, width = 1) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': width } });
const text = (value, x, y, size, color, extra = {}, font = 'sans') => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: font, style: { 'font-size': size, fill: color, ...extra } }] });
function sketch(bounds, fill, stroke, seed, roughness) { let state = seed >>> 0; const random = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return (state / 4294967296 - .5) * Math.max(0, roughness) * 2; }; const { x, y, width: w, height: h } = bounds; const points = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]].map(([px, py]) => `${px + random()},${py + random()}`); return { kind: 'path', d: 'M' + points.join('L') + 'Z', paint: { fill, stroke, 'stroke-width': 1.2, 'stroke-linejoin': 'round' } }; }
function merge(a, b) {
    const result = { ...a };
    for (const [key, value] of Object.entries(b))
        result[key] = value && typeof value === 'object' && !Array.isArray(value) ? merge(object(a[key]), object(value)) : value;
    return result;
}
function withPreview(values, preview) {
    const copy = merge({}, values);
    for (const [path, value] of Object.entries(preview ?? {})) {
        const parts = path.split('.');
        let current = copy;
        for (const part of parts.slice(0, -1)) {
            current[part] = { ...object(current[part]) };
            current = object(current[part]);
        }
        current[parts.at(-1) ?? path] = value;
    }
    return copy;
}
function mindmapLocations(nodes, all) {
    const ids = new Set(nodes.map(node => refKey(node.ref))), children = new Map(), parents = new Set();
    for (const relation of all.filter(record => record.record.category === 'relation')) {
        const endpoints = array(relation.record.endpoints).map(endpoint => resolveRecord(all, object(endpoint).definition, relation.file));
        if (endpoints.length !== 2 || !endpoints[0] || !endpoints[1])
            continue;
        const from = refKey(endpoints[0].ref), to = refKey(endpoints[1].ref);
        if (!ids.has(from) || !ids.has(to) || from === to)
            continue;
        const next = children.get(from) ?? [];
        if (!next.includes(to))
            next.push(to);
        children.set(from, next);
        parents.add(to);
    }
    const root = nodes.find(node => !parents.has(refKey(node.ref))) ?? nodes[0];
    if (!root)
        return new Map();
    const rootId = refKey(root.ref), positions = new Map(), seen = new Set([rootId]);
    const branches = children.get(rootId) ?? [];
    let maxLeftDepth = 0;
    const counts = [0, 0];
    const visit = (id, depth, side) => {
        if (seen.has(id))
            return Math.max(0, counts[side] - 1) * 170;
        seen.add(id);
        if (side === 0)
            maxLeftDepth = Math.max(maxLeftDepth, depth);
        const nested = (children.get(id) ?? []).filter(child => !seen.has(child));
        const ys = nested.map(child => visit(child, depth + 1, side));
        const y = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : counts[side]++ * 170;
        positions.set(id, { x: (side === 0 ? -1 : 1) * depth * 310, y });
        return y;
    };
    for (const [index, branch] of branches.entries())
        visit(branch, 1, index % 2);
    const rootY = Math.max(0, Math.max(...counts) - 1) * 85;
    const rootX = 32 + maxLeftDepth * 310;
    positions.set(rootId, { x: rootX, y: 64 + rootY });
    for (const [id, position] of positions)
        if (id !== rootId) {
            const side = position.x < 0 ? 0 : 1;
            positions.set(id, { x: rootX + position.x, y: 64 + position.y + rootY - Math.max(0, counts[side] - 1) * 85 });
        }
    return positions;
}
function recordTablePrimitives(columns, rows, x, y, width, effective, measure) {
    const size = num(pathValue(effective, 'style.font_size'), 16), font = str(pathValue(effective, 'style.font'), 'sans'), color = str(pathValue(effective, 'text.color'), '#1f2933');
    const header = pathValue(effective, 'table.header') !== false;
    const table = layoutTable(columns, rows, width, value => measure(value, size, font), { header, minChars: num(pathValue(effective, 'table.min_chars'), 1), maxLines: num(pathValue(effective, 'table.max_lines'), 6), lineHeight: size * 1.3 });
    const primitives = [];
    if (!table.fits)
        return { primitives: [rect({ x, y, width: 24, height: 24 }, '#9ca3af', '#4b5563'), text('Table cannot fit', x + 32, y + 18, size, color)], height: 32 };
    let top = y;
    for (const [rowIndex, row] of table.rows.entries()) {
        let left = x;
        for (const [index, cell] of row.cells.entries()) {
            const width = table.widths[index] ?? 0, alignment = columns[index]?.alignment ?? 'lt';
            primitives.push(rect({ x: left, y: top, width, height: row.height }, header && rowIndex === 0 ? '#eef2f6' : rowIndex % 2 ? '#ffffff' : '#f5f7fb', '#cbd5e1', .6));
            const tx = alignment[0] === 'r' ? left + width - 8 : alignment[0] === 'c' ? left + width / 2 : left + 8;
            const anchor = alignment[0] === 'r' ? 'end' : alignment[0] === 'c' ? 'middle' : 'start';
            const offset = alignment[1] === 'b' ? row.height - cell.lines.length * size * 1.3 - 4 : alignment[1] === 'm' ? (row.height - cell.lines.length * size * 1.3) / 2 : 4;
            for (const [lineIndex, line] of cell.lines.entries())
                primitives.push(text(line, tx, top + offset + size + lineIndex * size * 1.3, size, color, { 'text-anchor': anchor, ...(header && rowIndex === 0 ? { 'font-weight': 600 } : {}) }, font));
            left += width;
        }
        top += row.height;
    }
    const caption = notePrimitives('Source-bound table · no expression or decision-rule execution is implied.', x + 8, y + table.height + 22, width - 16, 11, color, value => measure(value, 11, font), false, 4, font);
    primitives.push(...caption.primitives);
    return { primitives, height: table.height + caption.height + 26 };
}
export function projectSnapshot(snapshot, options) {
    const all = records(snapshot), views = all.filter(r => r.owner === 'view' && (!options.onlyView || refKey(r.ref) === refKey(options.onlyView)) && (!options.profiles || options.profiles.includes(str(r.record.profile))));
    const entries = [];
    const diagnostics = [];
    const unavailable = [];
    const measure = options.measure ?? ((s, size) => s.length * size * .58);
    let nextViewX = 0, nextViewY = 0, rowBottom = 0;
    for (const [viewIndex, view] of views.entries()) {
        const vr = options.resolve(view.ref);
        diagnostics.push(...vr.diagnostics);
        const profile = str(view.record.profile);
        const placement = all.find(r => r.owner === 'placement' && resolveRecord(all, r.record.target, r.file)?.ref.id === view.ref.id && resolveRecord(all, r.record.target, r.file)?.file === view.file);
        const pr = placement ? options.resolve(placement.ref) : undefined;
        const pv = pr?.values ?? {};
        // An ordinary placement's own standards must not erase its view's
        // presentation. Authored/scoped placed-paper settings override it.
        const placedPaper = Object.fromEntries((pr?.properties ?? []).filter(p => (p.path === 'style.paper' || p.path === 'background.color' || p.path === 'background.texture' || p.path.startsWith('background.texture.') || p.path === 'decorations' || p.path === 'shadow' || p.path.startsWith('shadow.')) &&
            (p.origin.startsWith('file:') || p.origin === 'css' || p.origin === 'standard:paper' && !vr.properties.some(v => v.path === 'background.color' && !v.origin.startsWith('standard:')))).map(p => [p.path, p.value]));
        const effectiveView = withPreview(withPreview(vr.values, placedPaper), options.preview);
        const surface = fixedViewSurface(effectiveView);
        const vp = object(pv.position);
        const vs = object(pv.size);
        const fixedWidth = typeof pathValue(placement?.record, 'size.width') === 'number' || pr?.properties.some(p => p.path === 'size.width' && !p.origin.startsWith('standard:'));
        const fixedHeight = typeof pathValue(placement?.record, 'size.height') === 'number' || pr?.properties.some(p => p.path === 'size.height' && !p.origin.startsWith('standard:'));
        const viewX = num(vp.x, nextViewX), viewY = num(vp.y, nextViewY);
        let viewWidth = surface ? surface.width / surface.scale : num(vs.width, 960), viewHeight = surface ? surface.height / surface.scale : num(vs.height, 680);
        const title = titleOf(view.record);
        const viewPrimitives = [];
        const firstEntry = entries.length;
        const supported = availableProjectionProfiles.has(profile) && (options.supports?.(profile) ?? true);
        const isDocument = view.record.kind === 'document' || !!view.record.publication && profile === '';
        const appearances = all.filter(r => r.owner === 'appearance' && resolveRecord(all, r.record.parent, r.file)?.ref.id === view.ref.id && resolveRecord(all, r.record.parent, r.file)?.file === view.file);
        const excluded = new Set(array(pathValue(view.record, 'selection.exclude')).map(ref => resolveRecord(all, ref, view.file)).filter((record) => !!record).map(record => refKey(record.ref)));
        const selected = array(pathValue(view.record, 'selection.include')).map(r => resolveRecord(all, r, view.file)).filter((v) => !!v && !excluded.has(refKey(v.ref)));
        const candidates = [];
        // Selection order determines automatic branch and sibling order. Explicit
        // occurrences may add targets, while exclusions always remain authoritative.
        for (const definition of selected) {
            const occurrences = appearances.filter(a => refKey(resolveRecord(all, a.record.target, a.file)?.ref ?? { file: '', id: '' }) === refKey(definition.ref));
            if (occurrences.length)
                candidates.push(...occurrences.map(appearance => ({ definition, appearance })));
            else
                candidates.push({ definition, appearance: undefined });
        }
        for (const appearance of appearances) {
            const definition = resolveRecord(all, appearance.record.target, appearance.file);
            if (definition && !excluded.has(refKey(definition.ref)) && !candidates.some(c => c.appearance === appearance))
                candidates.push({ definition, appearance });
        }
        const selectedDefinitionKeys = new Set(candidates.filter(candidate => candidate.definition).map(candidate => refKey(candidate.definition.ref)));
        const mindmapTopicKeys = new Set(candidates.filter(candidate => candidate.definition && isMindmapTopic(candidate.definition.record)).map(candidate => mindmapKey(candidate.definition)));
        if (profile === 'mindmap.basic@1')
            for (const candidate of [...candidates]) {
                const relation = candidate.definition;
                if (relation?.record.category !== 'relation')
                    continue;
                const ends = array(relation.record.endpoints).map(end => resolveRecord(all, object(end).definition, relation.file));
                if (mindmapRelationKind(ends[0], ends[1], mindmapTopicKeys) !== 'external')
                    continue;
                for (const definition of ends)
                    if (definition && !excluded.has(refKey(definition.ref)) && !candidates.some(item => item.definition && refKey(item.definition.ref) === refKey(definition.ref)))
                        candidates.push({ definition, appearance: undefined });
            }
        const positioned = [];
        const relations = [];
        if (!supported && !isDocument) {
            unavailable.push(`profile:${profile}`);
            diagnostics.push({ code: 'profile-unavailable', severity: 'warning', message: `No installed projection for ${profile}.`, target: view.ref });
            viewPrimitives.push(text(`Unsupported profile: ${profile}`, viewX + 20, viewY + 70, 16, '#8a4b08'));
        }
        else if (profile === 'table.records@1') {
            const data = recordTableData(snapshot, view);
            diagnostics.push(...data.diagnostics);
            if (data.diagnostics.length)
                unavailable.push('table:' + refKey(view.ref));
            const settings = object(pathValue(view.record, 'projection.options'));
            const width = num(settings.width, Math.max(32, viewWidth - 64));
            const effective = withPreview(effectiveView, options.preview);
            const table = recordTablePrimitives(data.columns, data.rows, viewX + 32, viewY + 58, width, effective, measure);
            const bounds = { x: viewX + 32, y: viewY + 58, width, height: table.height };
            const occurrence = 'records:' + refKey(view.ref);
            const item = { occurrence, target: view.ref, view: view.ref, layer: 'content', bounds, transform: identity, primitives: table.primitives, hitTargets: [{ id: occurrence, target: view.ref, bounds }], accessible: { role: 'graphics-object', label: title + ' table', description: `${data.rows.length} records, ${data.columns.length} columns` }, evidence: data.diagnostics.length ? 'partial' : 'current' };
            entries.push({ item, definition: view, view, ...(placement ? { placement } : {}), effective });
            viewWidth = Math.max(viewWidth, width + 64);
            viewHeight = Math.max(fixedHeight ? viewHeight : 0, table.height + 90);
        }
        else if (isDataProfile(profile)) {
            const projected = dataProjector(profile)(snapshot, view, { x: viewX + 32, y: viewY + 58, width: viewWidth - 64, height: viewHeight - 90 }, effectiveView, {
                resolve: options.resolve, measure, ...(options.geography ? { geography: options.geography } : {}),
                projectChild(child, destination) {
                    const path = [...(options.inclusionPath ?? []), refKey(view.ref)];
                    if (path.includes(refKey(child.ref)) || (options.panelDepth ?? 0) >= 1)
                        return {
                            entries: [], bounds: destination, unavailable: ['panel-inclusion:' + refKey(child.ref)],
                            diagnostics: [{ code: 'panel-inclusion-depth', severity: 'error', message: 'Composed panels permit one child-view level without cycles.', target: child.ref }],
                        };
                    const { profiles: _profiles, ...childOptions } = options;
                    const projected = projectSnapshot(snapshot, { ...childOptions, onlyView: child.ref, inclusionPath: path, panelDepth: (options.panelDepth ?? 0) + 1, deferOpacity: true });
                    const scale = 1;
                    const tx = destination.x - projected.bounds.x;
                    const ty = destination.y - projected.bounds.y;
                    const childBounds = { ...projected.bounds, x: destination.x, y: destination.y };
                    const bounds = (b) => ({ x: b.x * scale + tx, y: b.y * scale + ty, width: b.width * scale, height: b.height * scale });
                    const entries = projected.entries.map(entry => {
                        const m = entry.item.transform;
                        return { ...entry, item: { ...entry.item, view: view.ref, occurrence: 'panel:' + refKey(view.ref) + ':' + entry.item.occurrence,
                                bounds: bounds(entry.item.bounds), clip: entry.item.clip ? intersectBounds(childBounds, bounds(entry.item.clip)) : childBounds,
                                hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: bounds(hit.bounds) })),
                                transform: [m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4] * scale + tx, m[5] * scale + ty],
                            } };
                    });
                    return { entries, bounds: childBounds, diagnostics: [...projected.diagnostics], unavailable: [...projected.coverage.unavailable] };
                },
            });
            if (projected) {
                entries.push(...projected.entries);
                diagnostics.push(...projected.diagnostics);
                unavailable.push(...projected.unavailable);
                viewWidth = Math.max(fixedWidth ? viewWidth : 0, projected.bounds.x + projected.bounds.width - viewX + 32);
                viewHeight = Math.max(fixedHeight ? viewHeight : 0, projected.bounds.y + projected.bounds.height - viewY + 32);
            }
        }
        else {
            let nodeIndex = 0;
            const mindmap = profile === 'mindmap.basic@1' ? mindmapLocations(candidates.map(candidate => candidate.definition).filter((record) => !!record && record.record.category !== 'relation'), all) : new Map();
            for (const candidate of candidates) {
                const definition = candidate.definition;
                if (!definition)
                    continue;
                if (definition.record.category === 'relation') {
                    relations.push(candidate);
                    continue;
                }
                const appearance = candidate.appearance;
                const resolved = options.resolve(definition.ref, { view: view.ref, ...(appearance ? { appearance: appearance.ref } : {}) });
                diagnostics.push(...resolved.diagnostics);
                const propertyOrigins = Object.fromEntries(resolved.properties.map(p => [p.path, p.origin]));
                let effective = withPreview(inheritedPresentation(resolved.values, resolved.properties, effectiveView), options.preview);
                let fontSize = num(pathValue(effective, 'style.font_size'), 16);
                const font = str(pathValue(effective, 'style.font'), 'sans');
                const color = str(pathValue(effective, 'text.color'), '#1f2933');
                const p = object(effective.position);
                const sz = object(effective.size);
                const layout = str(pathValue(effectiveView, 'layout.algorithm'));
                const col = nodeIndex % 3, row = Math.floor(nodeIndex / 3);
                const automatic = mindmap.get(refKey(definition.ref));
                const x = viewX + num(p.x, automatic?.x ?? (layout === 'mindmap' ? (nodeIndex === 0 ? viewWidth / 2 - 140 : nodeIndex % 2 ? 40 : viewWidth - 320) : 32 + col * 300));
                const y = viewY + num(p.y, automatic?.y ?? (layout === 'mindmap' ? (nodeIndex === 0 ? viewHeight / 2 - 50 : 65 + Math.floor((nodeIndex - 1) / 2) * 170) : 64 + row * 220));
                const standalone = standaloneNode({ definition, ...(appearance ? { appearance } : {}), effective, origins: propertyOrigins, all, x, y, measure, ...(options.assetSizes ? { assetSizes: options.assetSizes } : {}) });
                if (standalone) {
                    diagnostics.push(...standalone.diagnostics);
                    unavailable.push(...standalone.unavailable);
                    const occurrence = appearance?.ref.id ?? `${refKey(view.ref)}:${refKey(definition.ref)}`, status = str(pathValue(definition.record, 'design.state'), 'draft');
                    const item = { occurrence, target: definition.ref, view: view.ref, layer: str(effective.layer, 'content'), bounds: standalone.bounds, transform: identity, primitives: standalone.primitives, hitTargets: [{ id: occurrence, target: definition.ref, bounds: standalone.body }], accessible: { role: 'graphics-symbol', label: str(appearance?.record.title) || titleOf(definition.record), description: `${str(definition.record.role)}; ${status}; standalone ${standalone.presentation.mode}` }, status, evidence: snapshot.coverage.complete && !standalone.unavailable.length ? 'current' : 'partial' };
                    positioned.push({ item, definition, view, ...(appearance ? { appearance } : {}), ...(placement ? { placement } : {}), effective, propertyOrigins, standalone: standalone.presentation, ...(profile === 'mindmap.basic@1' ? { mindmapTopic: mindmapTopicKeys.has(mindmapKey(definition)) } : {}) });
                    nodeIndex++;
                    continue;
                }
                const role = str(definition.record.role), native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
                const showKind = pathValue(effectiveView, 'display.kind') !== 'none', roleWidth = native ? (showKind ? Math.min(96, Math.max(30, measure(nativeCode(role), 10.5, font))) + 12 : 0) : Math.min(130, Math.max(38, measure(role, 9, 'monospace') + 12));
                let width = num(sz.width, Math.max(248, Math.min(360, measure(titleOf(definition.record), fontSize, font) + roleWidth + 48)));
                const titleText = str(appearance?.record.title) || titleOf(definition.record);
                const primitives = [];
                const explicitBody = propertyOrigins.body ? !propertyOrigins.body.startsWith('standard:') : appearance?.record.body !== undefined || definition.record.body !== undefined;
                const contentText = str(pathValue(definition.record, 'content.text')) || str(definition.record.description) || str(pathValue(definition.record, 'content.meaning'));
                const defaultBody = definition.record.data || array(definition.record.members).length ? 'columns' : pathValue(definition.record, 'draft.text') ? 'draft' : contentText ? 'notes' : 'title';
                const body = explicitBody ? str(effective.body, defaultBody) : defaultBody;
                const fit = str(pathValue(effective, 'text.fit'), 'auto'), maxWidth = Math.min(num(pathValue(effective, 'text.max_width'), 4000), num(pathValue(effective, 'max_size.width'), 4000)), maxHeight = Math.min(num(pathValue(effective, 'text.max_height'), 4000), num(pathValue(effective, 'max_size.height'), 4000));
                width = Math.min(maxWidth, Math.max(width, num(pathValue(effective, 'min_size.width'), 0)));
                if (fit === 'grow' && sz.width === undefined)
                    width = Math.min(maxWidth, Math.max(width, measure(titleText, fontSize, font) + roleWidth + 48));
                const actor = ['external_actor', 'uml.actor'].includes(role), centred = actor || role.startsWith('flow.') || role.startsWith('state.') || ['uml.usecase', 'dfd.process', 'dfd.store'].includes(role);
                const kindLayout = native && showKind && !centred ? cardTextLayout(nativeCode(role), titleText, width, (value, size) => measure(value, size, font), 10.5, fontSize, 14) : undefined;
                const titleWidth = () => kindLayout?.titleWidth ?? Math.max(20, width - roleWidth - 44);
                const titleLimit = () => {
                    const available = Math.min(maxHeight, num(sz.height, maxHeight)) - (native && showKind ? 38 : 22);
                    return Math.max(1, Math.min(64, Math.floor(available / (fontSize * 1.25))));
                };
                let titleLayout = wrapCell(titleText, titleWidth(), txt => measure(txt, fontSize, font), titleLimit());
                if (fit === 'shrink')
                    while (titleLayout.truncated && fontSize > num(pathValue(effective, 'text.min_font'), 8)) {
                        fontSize = Math.max(num(pathValue(effective, 'text.min_font'), 8), fontSize - 1);
                        titleLayout = wrapCell(titleText, titleWidth(), txt => measure(txt, fontSize, font), titleLimit());
                    }
                const titleLines = titleLayout.lines;
                const headerHeight = Math.max(kindLayout ? 48 + kindLayout.typeLines.length * 13 : native && showKind ? 60 : 40, 18 + titleLines.length * fontSize * 1.25);
                let bodyHeight = 0;
                const members = array(definition.record.members).map(r => resolveRecord(all, r, definition.file)).filter((r) => !!r);
                if (body === 'columns') {
                    const data = tableData(snapshot, definition);
                    const visibility = { ...object(effective.column_visibility), ...object(definition.record.column_visibility), ...object(appearance?.record.column_visibility) };
                    const order = array(effective.columns);
                    const nativeFields = data.columns.some(c => c.id === 'field') && native;
                    const shown = data.columns.map((c, i) => ({ c, i })).filter(({ c }) => visibility[str(c.id)] === 'shown' || visibility[str(c.id)] !== 'hidden' && (!nativeFields || str(c.id) === 'field' || Object.keys(visibility).length > 0 && visibility[str(c.id)] !== 'on_demand'));
                    const ordered = order.map(c => shown.find(x => x.c.id === (typeof c === 'string' ? c : str(object(c).id)))).filter((v) => !!v);
                    const picked = [...ordered, ...shown.filter(item => !ordered.includes(item))];
                    const columns = picked.map(({ c }) => c);
                    const rows = data.rows.map((row, ri) => picked.map(({ i, c }) => {
                        const member = members[ri];
                        let value = row[i];
                        if (nativeFields && c.id === 'field' && member) {
                            let depth = 0, parent = resolveRecord(all, pathValue(member.record, 'content.parent'), member.file);
                            const seen = new Set();
                            while (parent && parent.record.role === 'field' && !seen.has(refKey(parent.ref))) {
                                seen.add(refKey(parent.ref));
                                depth++;
                                parent = resolveRecord(all, pathValue(parent.record, 'content.parent'), parent.file);
                            }
                            const key = pathValue(member.record, 'content.key') ?? pathValue(member.record, 'properties.key');
                            const nullable = pathValue(member.record, 'content.nullable') ?? pathValue(member.record, 'properties.nullable');
                            const presence = pathValue(member.record, 'properties.presence');
                            const shape = str(pathValue(member.record, 'properties.shape')), shapeMark = shape === 'array' ? ' []' : shape === 'object' ? ' {}' : shape === 'variant' ? ' <variant>' : '';
                            value = '  '.repeat(depth) + (depth ? '↳ ' : '') + (key && key !== 'none' ? '⚿ ' : '') + str(value) + shapeMark + (nullable === true || presence === 'optional' ? ' ?' : nullable === false ? ' !' : '');
                        }
                        if (role === 'sample')
                            value = value === null ? 'null' : object(value).$missing === true || object(value).$state === 'missing' ? 'missing' : value;
                        return value;
                    }));
                    width = num(sz.width, Math.max(width, columns.length * 95, role === 'sample' ? Math.min(1000, columns.length * Math.max(80, ...rows.flatMap(row => row.map(v => measure(String(v ?? ''), fontSize, font) + 18)))) : 0));
                    const header = pathValue(effective, 'table.header') !== false;
                    const table = layoutTable(columns, rows, width, txt => measure(txt, fontSize, font), { minChars: num(pathValue(effective, 'table.min_chars'), 1), maxLines: num(pathValue(effective, 'table.max_lines'), 6), header, lineHeight: fontSize * 1.3 });
                    if (!table.fits) {
                        primitives.push(rect({ x: x + 12, y: y + headerHeight + 8, width: 24, height: 24 }, '#9ca3af', '#4b5563'));
                        bodyHeight = 40;
                    }
                    else {
                        let ty = y + headerHeight;
                        for (const [ri, tableRow] of table.rows.entries()) {
                            let tx = x;
                            for (const [ci, cell] of tableRow.cells.entries()) {
                                const cw = table.widths[ci] ?? 0, align = columns[ci]?.alignment ?? 'lt';
                                primitives.push(rect({ x: tx, y: ty, width: cw, height: tableRow.height }, header && ri === 0 ? ['dark', 'night', 'blueprint'].includes(str(pathValue(effectiveView, 'style.theme'))) ? '#334155' : '#eef2f6' : 'transparent', '#d4dbe3', .6));
                                const txText = align[0] === 'r' ? tx + cw - 8 : align[0] === 'c' ? tx + cw / 2 : tx + 8, anchor = align[0] === 'r' ? 'end' : align[0] === 'c' ? 'middle' : 'start';
                                const vertical = align[1] === 'b' ? tableRow.height - cell.lines.length * fontSize * 1.3 : align[1] === 'm' ? (tableRow.height - cell.lines.length * fontSize * 1.3) / 2 : 4;
                                for (const [li, value] of cell.lines.entries())
                                    primitives.push(text(value, txText, ty + vertical + fontSize + li * fontSize * 1.3, fontSize, color, { 'text-anchor': anchor, ...(header && ri === 0 ? { 'font-weight': 600 } : {}) }, font));
                                tx += cw;
                            }
                            ty += tableRow.height;
                        }
                        bodyHeight = table.height;
                    }
                }
                if (body === 'draft' || body === 'notes' || body === 'columns' && contentText) {
                    const raw = body === 'draft' ? str(pathValue(definition.record, 'draft.text')) || contentText : contentText || array(definition.record.notes).filter(n => !str(object(n).title).startsWith('Additional source')).map(n => str(object(n).text)).join('\n\n');
                    const bodySize = body === 'draft' ? 13.333 : Math.max(12, fontSize * .82), bodyFont = body === 'draft' ? 'monospace' : font;
                    const maxHeight = num(pathValue(effective, 'note.height'), 180), maxLines = Math.max(1, Math.floor(maxHeight / (bodySize * 1.4)));
                    const blocks = notePrimitives(raw, x + 14, y + headerHeight + bodyHeight + bodySize + 10, width - 28, bodySize, color, txt => measure(txt, bodySize, bodyFont), body !== 'draft' && pathValue(definition.record, 'content.format') !== 'plain', maxLines, bodyFont);
                    primitives.push(...blocks.primitives);
                    bodyHeight += blocks.height + (raw ? 20 : 0);
                }
                if (role === 'sample' && body === 'columns') {
                    const caption = pathValue(definition.record, 'properties.mode') === 'synthetic' ? 'Synthetic · illustrative · not a constraint' : 'Sample data';
                    primitives.push(text(caption, x + 12, y + headerHeight + bodyHeight + 16, 10, color));
                    bodyHeight += 24;
                }
                const badges = native ? nativeBadges(definition.record, appearance?.record, effectiveView) : [];
                const naturalHeight = Math.max(actor ? 145 : pathValue(effective, 'background.image') ? 220 : native ? 100 : 60, headerHeight + bodyHeight + (badges.length ? 28 : 8));
                const height = Math.min(maxHeight, num(sz.height, Math.max(naturalHeight, num(pathValue(effective, 'min_size.height'), 0))));
                const overflow = titleLayout.truncated || headerHeight + bodyHeight + (badges.length ? 28 : 8) > height + 1;
                const bounds = { x, y, width, height }, status = str(pathValue(definition.record, 'design.state'), 'draft');
                const rendering = roleDescriptor(role)?.render ?? {};
                const authored = (path) => propertyOrigins[path] && !propertyOrigins[path].startsWith('standard:');
                const background = str(pathValue(effective, 'background.color'));
                const themed = ['neutral', 'dark', 'night', 'blueprint'].includes(str(pathValue(effectiveView, 'style.theme')));
                const fill = authored('background.color') || themed ? background : str(rendering.fill, background || '#ffffff');
                const symbolColor = authored('symbol.color') || themed ? str(pathValue(effective, 'symbol.color'), '#64748b') : str(rendering.colour, str(pathValue(effective, 'symbol.color'), '#64748b'));
                const borderWidth = num(pathValue(effective, 'border.width')), outlineWidth = borderWidth > 0 ? borderWidth : num(pathValue(effective, 'symbol.width'), num(rendering.width, 1.2));
                const border = borderWidth > 0 ? str(pathValue(effective, 'border.color'), symbolColor) : symbolColor;
                const look = str(pathValue(effective, 'style.look'), str(pathValue(effectiveView, 'style.look')));
                const outline = native ? nativeContour(role, definition.record, bounds, fill, border, outlineWidth, look, num(pathValue(effective, 'style.roughness'), 1), num(pathValue(effective, 'style.seed'), 42) + nodeIndex) : [rect(bounds, fill, border, outlineWidth)];
                const borderStyle = pathValue(effective, 'border.style');
                if (borderStyle === 'dashed' || borderStyle === 'dotted')
                    for (let i = 0; i < outline.length; i++) {
                        const p = outline[i];
                        if ('paint' in p)
                            outline[i] = { ...p, paint: { ...p.paint, 'stroke-dasharray': borderStyle === 'dashed' ? '6 4' : '2 3' } };
                    }
                primitives.unshift(...outline);
                const imageRef = pathValue(effective, 'background.image');
                if (imageRef) {
                    const asset = resolveRecord(all, imageRef, definition.file);
                    if (asset)
                        primitives.splice(outline.length, 0, { kind: 'image', assetId: refKey(asset.ref), bounds: { x: x + 12, y: y + headerHeight + 6, width: width - 24, height: Math.max(24, height - headerHeight - 16) } });
                }
                if (native && showKind && !centred) {
                    primitives.push(...nativeIcon(str(rendering.glyph, role), { x: x + 14, y: y + 16, width: 20, height: 20 }, symbolColor));
                    for (const [i, code] of (kindLayout?.typeLines ?? [nativeCode(role)]).entries())
                        primitives.push(text(code, x + 14, y + 48 + i * 13, 10.5, symbolColor, { 'font-weight': 700 }, font));
                }
                for (const [i, line] of titleLines.entries())
                    primitives.push(text(line, centred ? x + width / 2 : x + (kindLayout?.titleOffset ?? 14 + roleWidth), centred ? (actor ? y + height - 12 : y + height / 2) + (i - (titleLines.length - 1) / 2) * fontSize * 1.25 : y + 18 + fontSize * .8 + i * fontSize * 1.25, fontSize, color, { 'font-weight': 600, ...(centred ? { 'text-anchor': 'middle' } : {}) }, font));
                primitives.push({ kind: 'ellipse', bounds: { x: x + width - 17, y: y + 9, width: 7, height: 7 }, paint: { fill: status === 'accepted' ? '#15803d' : status === 'in-review' ? '#7c3aed' : status === 'in-progress' ? '#2563eb' : '#d97706', stroke: '#ffffff', 'stroke-width': 1, 'ddn-design-status': status } });
                if (bodyHeight > 0)
                    primitives.push({ kind: 'path', d: `M${x},${y + headerHeight}H${x + width}`, paint: { stroke: border, 'stroke-width': .8, fill: 'none' } });
                primitives.push(...badgePrimitives(badges, bounds, 9, symbolColor, fill));
                const textStyle = {};
                for (const [key, attr] of [['weight', 'font-weight'], ['italic', 'font-style'], ['variant', 'font-variant'], ['decoration', 'text-decoration']]) {
                    const value = pathValue(effective, 'text.' + key);
                    if (value !== undefined && (authored('text.' + key) || vr.properties.some(p => p.path === 'text.' + key && !p.origin.startsWith('standard:'))))
                        textStyle[attr] = key === 'italic' ? (value ? 'italic' : 'normal') : key === 'variant' && value === 'small_caps' ? 'small-caps' : key === 'decoration' && value === 'strike' ? 'line-through' : value;
                }
                for (let i = 0; i < primitives.length; i++) {
                    const p = primitives[i];
                    if (p.kind === 'text')
                        primitives[i] = { ...p, runs: p.runs.map(run => ({ ...run, style: { ...run.style, ...textStyle } })) };
                }
                if (overflow) {
                    diagnostics.push({ code: 'text-overflow', severity: 'warning', message: 'Text exceeds its declared bounds; the visible text is clipped and marked with an ellipsis.', target: definition.ref });
                    primitives.push(rect({ x: x + width - 26, y: y + height - 20, width: 24, height: 18 }, fill, 'none', 0), text('…', x + width - 23, y + height - 7, 14, color));
                }
                const occurrence = appearance?.ref.id ?? `${refKey(view.ref)}:${refKey(definition.ref)}`;
                const item = { occurrence, target: definition.ref, view: view.ref, layer: str(effective.layer, 'content'), bounds, ...(overflow ? { clip: bounds } : {}), transform: identity, primitives, hitTargets: [{ id: occurrence, target: definition.ref, bounds }], accessible: { role: 'graphics-symbol', label: titleText, description: `${str(definition.record.role)}; ${status}` }, status, evidence: snapshot.coverage.complete ? 'current' : 'partial' };
                const entry = { item, definition, view, ...(appearance ? { appearance } : {}), ...(placement ? { placement } : {}), effective, propertyOrigins };
                positioned.push({ ...entry, ...(profile === 'mindmap.basic@1' ? { mindmapTopic: mindmapTopicKeys.has(mindmapKey(definition)) } : {}) });
                nodeIndex++;
            }
            const byTarget = new Map(positioned.map(e => [refKey(e.definition.ref), e]));
            const byAppearance = new Map(positioned.filter(entry => entry.appearance).map(entry => [refKey(entry.appearance.ref), entry]));
            const selectedRelationRecords = all.filter(r => r.owner === 'definition' && r.record.category === 'relation' && !excluded.has(refKey(r.ref)) && pathValue(view.record, 'selection.relations') !== 'none' && array(r.record.endpoints).every(end => { const target = resolveRecord(all, object(end).definition ?? object(end).target ?? object(end).ref ?? end, r.file); return target && byTarget.has(refKey(target.ref)) && (profile !== 'mindmap.basic@1' || selectedDefinitionKeys.has(refKey(target.ref))); }));
            for (const relation of selectedRelationRecords)
                if (!relations.some(c => c.definition === relation))
                    relations.push({ definition: relation, appearance: undefined });
            for (const { definition, appearance } of relations) {
                if (!definition)
                    continue;
                const ends = array(definition.record.endpoints).map((end, index) => {
                    const semantic = resolveRecord(all, object(end).definition ?? object(end).target ?? object(end).ref ?? end, definition.file);
                    const explicit = index < 2 ? pathValue(appearance?.record, index === 0 ? 'route.from' : 'route.to') : undefined;
                    if (explicit !== undefined) {
                        const occurrence = resolveRecord(all, explicit, appearance?.file ?? definition.file);
                        const selected = occurrence ? byAppearance.get(refKey(occurrence.ref)) : undefined;
                        if (selected && semantic && refKey(selected.definition.ref) === refKey(semantic.ref))
                            return selected;
                        diagnostics.push({ code: 'relation-occurrence-unavailable', severity: 'warning', message: 'The selected connection occurrence is unavailable in this view or does not represent its semantic endpoint.', target: appearance?.ref ?? definition.ref });
                        unavailable.push('relation-occurrence:' + refKey(appearance?.ref ?? definition.ref));
                        return undefined;
                    }
                    return semantic ? byTarget.get(refKey(semantic.ref)) : undefined;
                });
                if (ends.length < 2 || !ends[0] || !ends[1])
                    continue;
                const from = ends[0], to = ends[1];
                const a = from.item.bounds, b = to.item.bounds;
                const horizontal = Math.abs(b.x + b.width / 2 - a.x - a.width / 2) >= Math.abs(b.y + b.height / 2 - a.y - a.height / 2);
                const right = b.x + b.width / 2 >= a.x + a.width / 2, down = b.y + b.height / 2 >= a.y + a.height / 2;
                const x1 = horizontal ? a.x + (right ? a.width : 0) : a.x + a.width / 2, y1 = horizontal ? a.y + a.height / 2 : a.y + (down ? a.height : 0), x2 = horizontal ? b.x + (right ? 0 : b.width) : b.x + b.width / 2, y2 = horizontal ? b.y + b.height / 2 : b.y + (down ? 0 : b.height);
                const route = str(pathValue(effectiveView, 'layout.routing'), 'orthogonal');
                const d = route === 'straight' ? `M${x1},${y1}L${x2},${y2}` : route === 'curved' ? `M${x1},${y1}C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}` : `M${x1},${y1}H${(x1 + x2) / 2}V${y2}H${x2}`;
                const bounds = { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.max(1, Math.abs(x2 - x1)), height: Math.max(1, Math.abs(y2 - y1)) };
                const resolved = options.resolve(definition.ref, { view: view.ref, ...(appearance ? { appearance: appearance.ref } : {}) });
                const item = { occurrence: appearance?.ref.id ?? `${refKey(view.ref)}:${refKey(definition.ref)}`, target: definition.ref, view: view.ref, layer: 'relations', bounds, transform: identity, primitives: [{ kind: 'path', d, paint: { fill: 'none', stroke: str(pathValue(resolved.values, 'stroke.color'), '#64748b'), 'stroke-width': 1.5 } }, text(str(definition.record.title) || str(definition.record.name), bounds.x + bounds.width / 2, bounds.y - 5, 12, '#334155', { 'text-anchor': 'middle' })], hitTargets: [{ id: definition.ref.id, target: definition.ref, bounds }], accessible: { role: 'graphics-symbol', label: titleOf(definition.record) }, evidence: snapshot.coverage.complete ? 'current' : 'partial' };
                entries.push({ item, definition, view, ...(appearance ? { appearance } : {}), effective: resolved.values, propertyOrigins: Object.fromEntries(resolved.properties.map(p => [p.path, p.origin])) });
            }
            const contentBounds = unionBounds(positioned.map(e => e.item.bounds));
            if (positioned.length && pathValue(effectiveView, 'layout.frame_overflow') !== 'confine') {
                viewWidth = Math.max(viewWidth, contentBounds.x + contentBounds.width - viewX + 32);
                viewHeight = Math.max(viewHeight, contentBounds.y + contentBounds.height - viewY + 32);
            }
            entries.push(...positioned);
            entries.splice(firstEntry, entries.length - firstEntry, ...prepareRelationPresentation(entries.slice(firstEntry), all, effectiveView));
            if (isGraphProfile(profile) || ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile)) {
                const publication = resolveRecord(all, view.record.publication, view.file), page = object(publication ? options.resolve(publication.ref).values.page : undefined);
                if (page.fit === 'reflow' && ['grid', 'fit_grid'].includes(str(pathValue(effectiveView, 'layout.algorithm'))) && !positioned.some(entry => entry.appearance?.record.position && entry.appearance.record.position !== 'auto')) {
                    const [pageWidth] = publicationPageSize(page, { width: 1280, height: 800 }), margins = object(page.margin), gap = num(pathValue(effectiveView, 'layout.gap'), 64), legend = relationLegendVisible(effectiveView) && pathValue(effectiveView, 'legend.placement') === 'right' && entries.slice(firstEntry).some(e => relationPresentation(e, effectiveView).inLegend) ? num(pathValue(effectiveView, 'legend.width'), 310) + 32 : 0;
                    const width = Math.max(1, pageWidth - num(margins.left, 32) - num(margins.right, 32) - legend - 64), nodeWidth = Math.max(248, ...positioned.map(entry => entry.item.bounds.width));
                    effectiveView.layout = { ...object(effectiveView.layout), algorithm: 'grid', columns: Math.max(1, Math.floor((width + gap) / (nodeWidth + gap))) };
                }
                const projected = (graphProjector(profile) ?? projectNativeGraph)(snapshot, view, entries.slice(firstEntry), {
                    bounds: { x: viewX, y: viewY, width: viewWidth, height: viewHeight },
                    viewProperties: effectiveView,
                    ...(options.inclusionPath ? { ancestors: options.inclusionPath } : {}),
                    projectInline(childSnapshot, targetView, _bounds, ancestors) {
                        const { profiles: _profiles, ...childOptions } = options;
                        const result = projectSnapshot(childSnapshot, { ...childOptions, onlyView: targetView.ref, inclusionPath: ancestors, deferOpacity: true });
                        return { entries: result.entries, diagnostics: result.diagnostics, unavailable: result.coverage.unavailable };
                    },
                });
                entries.splice(firstEntry, entries.length - firstEntry, ...projected.entries);
                diagnostics.push(...projected.diagnostics);
                unavailable.push(...(projected.unavailable ?? []));
                if (projected.entries.length) {
                    const extent = unionBounds(projected.entries.map(entry => entry.item.bounds));
                    viewWidth = Math.max(fixedWidth ? viewWidth : 0, extent.x + extent.width - viewX + 32);
                    viewHeight = Math.max(fixedHeight ? viewHeight : 0, extent.y + extent.height - viewY + 32);
                }
            }
        }
        if (!isDataProfile(profile) && profile !== 'table.records@1') {
            const decorated = entries.slice(firstEntry).map(entry => entry.standalone ? entry : decoratePaper(entry));
            entries.splice(firstEntry, entries.length - firstEntry, ...decorated);
            if (decorated.length && pathValue(effectiveView, 'layout.frame_overflow') !== 'confine') {
                const extent = unionBounds(decorated.map(entry => entry.item.bounds));
                viewWidth = Math.max(fixedWidth ? viewWidth : 0, extent.x + extent.width - viewX + 32);
                viewHeight = Math.max(fixedHeight ? viewHeight : 0, extent.y + extent.height - viewY + 32);
            }
        }
        if (pathValue(effectiveView, 'projection.options.iso') === true && (profile === 'ddn@1' || isGraphProfile(profile))) {
            const projected = isometricGraph(entries.slice(firstEntry), { x: viewX, y: viewY, width: viewWidth, height: viewHeight }, num(pathValue(effectiveView, 'projection.options.depth'), 18));
            entries.splice(firstEntry, entries.length - firstEntry, ...projected);
            if (projected.length) {
                const extent = unionBounds(projected.map(entry => entry.item.bounds));
                viewWidth = Math.max(viewWidth, extent.x + extent.width - viewX + 24);
                viewHeight = Math.max(viewHeight, extent.y + extent.height - viewY + 24);
            }
        }
        // Chrome is part of the view, with room reserved above and below its
        // content. Its visibility is independent from the surrounding website.
        const chrome = object(effectiveView.chrome), chromeColor = str(pathValue(effectiveView, 'text.color'), '#243449');
        const banner = chrome.banner !== false, showTitle = chrome.title !== false, footer = chrome.footer !== false;
        // Authored positions are relative to diagram content. Keep their relative
        // geometry while reserving the visible title band above the whole graph.
        if (!isDataProfile(profile) && profile !== 'table.records@1' && entries.length > firstEntry) {
            const content = entries.slice(firstEntry), extent = unionBounds(content.map(e => e.item.bounds));
            const dx = Math.max(0, viewX + 20 - extent.x), dy = Math.max(0, viewY + (showTitle ? 64 : banner ? 32 : 16) - extent.y);
            if (dx || dy) {
                const shift = (b) => ({ ...b, x: b.x + dx, y: b.y + dy });
                entries.splice(firstEntry, content.length, ...content.map(entry => ({ ...entry, item: { ...entry.item, bounds: shift(entry.item.bounds), transform: [entry.item.transform[0], entry.item.transform[1], entry.item.transform[2], entry.item.transform[3], entry.item.transform[4] + dx, entry.item.transform[5] + dy], ...(entry.item.clip ? { clip: shift(entry.item.clip) } : {}), hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: shift(hit.bounds) })) } })));
                viewWidth += dx;
                viewHeight += dy;
            }
        }
        const legendPlacement = str(pathValue(effectiveView, 'legend.placement'), 'right');
        if (relationLegendVisible(effectiveView)) {
            // A relation can have several appearances. One included occurrence
            // creates one semantic legend row; filtering never changes its key.
            const members = new Map();
            for (const entry of entries.slice(firstEntry)) {
                if (!relationPresentation(entry, effectiveView).inLegend)
                    continue;
                const key = refKey(entry.definition.ref), previous = members.get(key);
                if (!previous || relationPresentation(entry, effectiveView).mode === 'numbers')
                    members.set(key, entry);
            }
            if (members.size) {
                const lw = num(pathValue(effectiveView, 'legend.width'), 310), lx = legendPlacement === 'right' ? viewX + viewWidth + 16 : viewX + 24, ly = legendPlacement === 'right' ? viewY + 80 : viewY + viewHeight + 16;
                viewPrimitives.push(text('RELATIONSHIP KEY', lx, ly, 11, chromeColor, { 'font-weight': 600 }));
                let cursor = ly + 26;
                for (const edge of members.values()) {
                    const kind = str(edge.definition.record.role), descriptor = roleDescriptor(kind, 'relation')?.render ?? {}, state = relationPresentation(edge, effectiveView);
                    const token = state.mode === 'numbers' ? state.number : state.mode === 'tokens' ? kind : '';
                    const ends = array(edge.definition.record.endpoints).map(e => resolveRecord(all, object(e).definition, edge.definition.file)).filter((r) => !!r);
                    const semantic = edgeLabel(edge, all) || str(edge.definition.record.description) || str(descriptor.text_label, kind);
                    const label = `${token ? token + '  ' : ''}${ends[0] ? titleOf(ends[0].record) : ''} → ${ends[1] ? titleOf(ends[1].record) : ''}: ${semantic}`;
                    const legendColor = ['dark', 'night', 'blueprint', 'neutral'].includes(str(pathValue(effectiveView, 'style.theme'))) ? chromeColor : str(descriptor.colour, chromeColor);
                    const body = notePrimitives(label, lx, cursor, lw - 20, 11, legendColor, t => measure(t, 11, 'sans'), false, 5);
                    viewPrimitives.push(...body.primitives);
                    cursor += body.height + 10;
                }
                if (legendPlacement === 'right') {
                    viewWidth += lw + 32;
                    viewHeight = Math.max(viewHeight, cursor - viewY + 20);
                }
                else
                    viewHeight = cursor - viewY + 20;
            }
        }
        if (footer)
            viewHeight += 30;
        if (showTitle && !fixedWidth)
            viewWidth = Math.max(viewWidth, measure(str(chrome.title_text) || title, Math.min(24, num(pathValue(effectiveView, 'style.font_size'), 16) + 8), str(pathValue(effectiveView, 'style.font'), 'sans')) + 40);
        let surfaceTransform;
        if (surface) {
            const fitted = fitSurfaceContent(entries.slice(firstEntry), viewPrimitives, surface, { x: viewX, y: viewY }, chrome, measure);
            entries.splice(firstEntry, entries.length - firstEntry, ...fitted.entries);
            viewPrimitives.splice(0, viewPrimitives.length, ...fitted.annotations);
            surfaceTransform = fitted.matrix;
            viewWidth = surface.width;
            viewHeight = surface.height;
            if (fitted.clipped)
                diagnostics.push({ code: 'surface-overflow', severity: 'warning', message: 'Content outside the fixed view surface is clipped; use surface.fit contain to fit the complete diagram.', target: view.ref });
        }
        const bounds = { x: viewX, y: viewY, width: viewWidth, height: viewHeight };
        // Preserve the two-column workarea arrangement, but reserve each view's
        // measured extent after graph/table/chart expansion before placing peers.
        const imageRef = pathValue(effectiveView, 'background.image');
        if (imageRef) {
            const asset = resolveRecord(all, imageRef, view.file);
            if (asset)
                viewPrimitives.push({ kind: 'image', assetId: refKey(asset.ref), bounds });
            else
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: 'View background image does not resolve.', target: view.ref });
        }
        viewPrimitives.unshift(rect(bounds, str(pathValue(effectiveView, 'background.color'), '#f8fafc'), str(pathValue(effectiveView, 'border.color'), '#cbd5e1')));
        const chromeScale = surface?.scale ?? 1;
        if (banner)
            viewPrimitives.push(text(str(chrome.banner_text) || 'DDN / ' + profile + ' / ddn-next-1', viewX + 20 * chromeScale, viewY + 16 * chromeScale, 10 * chromeScale, chromeColor, { 'font-weight': 600 }));
        if (showTitle)
            viewPrimitives.push(text(str(chrome.title_text) || title, viewX + 20 * chromeScale, viewY + (banner ? 40 : 31) * chromeScale, Math.min(24, num(pathValue(effectiveView, 'style.font_size'), 16) + 8) * chromeScale, chromeColor, { 'font-weight': 700 }, str(pathValue(effectiveView, 'style.font'), 'sans')));
        if (footer) {
            viewPrimitives.push({ kind: 'path', d: `M${viewX + 20 * chromeScale},${viewY + viewHeight - 30 * chromeScale}H${viewX + viewWidth - 20 * chromeScale}`, paint: { fill: 'none', stroke: chromeColor, 'stroke-width': .5 * chromeScale, opacity: .3 } }, text(str(chrome.footer_text) || profile, viewX + 20 * chromeScale, viewY + viewHeight - 12 * chromeScale, 10 * chromeScale, chromeColor));
        }
        const frame = { occurrence: `view:${refKey(view.ref)}`, target: view.ref, view: view.ref, layer: 'views', bounds, transform: identity, primitives: viewPrimitives, hitTargets: [{ id: view.ref.id, target: view.ref, bounds }], accessible: { role: 'graphics-object', label: `${title}, ${profile || 'document'}` }, evidence: supported || isDocument ? snapshot.coverage.complete ? 'current' : 'partial' : 'invalid' };
        let decoratedFrame = decoratePaper({ item: frame, definition: view, view, ...(placement ? { placement } : {}), effective: effectiveView });
        if (surface)
            decoratedFrame = { ...decoratedFrame, surfaceTransform: surfaceTransform, item: { ...decoratedFrame.item, bounds, clip: bounds, hitTargets: frame.hitTargets } };
        const viewEntries = entries.slice(firstEntry);
        const hasPaper = [decoratedFrame, ...viewEntries].some(entry => entry.item.primitives.some(p => 'paint' in p && p.paint['ddn-decoration']));
        let paintedFrame = decoratedFrame.item.bounds;
        if (hasPaper && !surface) {
            // Reserve incoming left/top overhang as well as outgoing right/bottom
            // paint. Explicit workarea coordinates remain authoritative.
            const extent = unionBounds([paintedFrame, ...viewEntries.map(entry => entry.item.bounds)]);
            const dx = typeof vp.x === 'number' ? 0 : Math.max(0, viewX - extent.x);
            const dy = typeof vp.y === 'number' ? 0 : Math.max(0, viewY - extent.y);
            const moveBounds = (b) => ({ ...b, x: b.x + dx, y: b.y + dy });
            const move = (entry) => {
                const item = entry.item, m = item.transform;
                return { ...entry, item: { ...item, bounds: moveBounds(item.bounds), ...(item.clip ? { clip: moveBounds(item.clip) } : {}),
                        hitTargets: item.hitTargets.map(hit => ({ ...hit, bounds: moveBounds(hit.bounds) })),
                        transform: [m[0], m[1], m[2], m[3], m[4] + dx, m[5] + dy],
                    } };
            };
            if (dx || dy) {
                decoratedFrame = move(decoratedFrame);
                entries.splice(firstEntry, viewEntries.length, ...viewEntries.map(move));
            }
            paintedFrame = moveBounds(extent);
        }
        entries.unshift(decoratedFrame);
        rowBottom = Math.max(rowBottom, paintedFrame.y + paintedFrame.height);
        if (viewIndex % 2 === 0)
            nextViewX = paintedFrame.x + paintedFrame.width + 80;
        else {
            nextViewX = 0;
            nextViewY = rowBottom + 80;
        }
    }
    const painted = options.deferOpacity ? entries : entries.map(entry => {
        const opacity = num(options.preview?.opacity, num(entry.effective.opacity, 1));
        if (opacity === 1)
            return entry;
        if (entry.item.primitives.some(primitive => primitive.kind === 'image')) {
            diagnostics.push({ code: 'image-opacity-unavailable', severity: 'warning', message: 'Opacity on image primitives is not supported by this scene contract; image opacity is unchanged.', target: entry.definition.ref });
            unavailable.push('image-opacity:' + entry.item.occurrence);
        }
        const primitives = entry.item.primitives.map((primitive) => {
            if (primitive.kind === 'text')
                return { ...primitive, runs: primitive.runs.map(run => ({ ...run, style: { ...run.style, opacity: num(run.style.opacity, 1) * opacity } })) };
            if ('paint' in primitive)
                return { ...primitive, paint: { ...primitive.paint, opacity: num(primitive.paint.opacity, 1) * opacity } };
            return primitive;
        });
        return { ...entry, item: { ...entry.item, primitives } };
    });
    return { items: painted.map(e => e.item), entries: painted, views, bounds: unionBounds(painted.map(e => e.item.bounds)), coverage: { ...snapshot.coverage, complete: snapshot.coverage.complete && !unavailable.length, unavailable: [...snapshot.coverage.unavailable, ...unavailable] }, diagnostics };
}
//# sourceMappingURL=project-core.js.map