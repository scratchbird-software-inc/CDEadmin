import { graphNodeDimensions } from './node-dimensions.js';
import { prepareRelationPresentation, relationCaption } from './relation-presentation.js';
import { center, identity, finiteBounds, changed, mark, memberRecords, endEntry, resolvedText, provisionalNodes, styled, edgeLabel, graphLabelBounds, decorateEdge, boundaryPoint, layoutNative, graphAdornments, inlineInteractions } from './graph-common.js';
import { projectNativeGraph } from './graph-native.js';
import { roleDescriptor } from '../../profiles/src/core.js';
import { array, object, str, num, pathValue, records, resolveRecord, refKey, titleOf } from './model.js';
import { graphLayout } from './graph-layouts.js';
import { wrapCell } from './table.js';
import { graphCatalogue } from './graph-catalogue.js';
import { nodeGlyph, coreCardText, metadata, arrowMarker, sketchPrimitive, shadowPrimitive, line, label, box, oval, path, polygon } from './graph-glyphs.js';
export const graphProfileIds = Object.freeze(Object.keys(graphCatalogue));
function dimensions(entry, profile) {
    return graphNodeDimensions(str(entry.definition.record.role), profile, entry.item.bounds, entry.definition.record, typeof entry.appearance?.record.size === 'object');
}
function compartmentRows(entry, all, profile) {
    const result = [];
    const record = entry.definition.record, requirement = object(metadata(record, 'x_requirement')), diagram = object(metadata(record, 'x_diagram'));
    if (profile.startsWith('chen.'))
        return [];
    if (['req.requirement', 'sysml.requirement'].includes(str(record.role))) {
        for (const key of ['code', 'text'])
            if (diagram[key])
                result.push({ group: 'requirement', label: String(diagram[key]), style: {} });
    }
    for (const key of ['id', 'owner', 'acceptance', 'state'])
        if (requirement[key])
            result.push({ group: 'requirement', label: `${key} = ${typeof requirement[key] === 'string' ? requirement[key] : JSON.stringify(requirement[key])}`, style: {} });
    const recordMeta = object(metadata(record, 'x_record'));
    if (recordMeta.reference)
        result.push({ group: 'reference', label: str(recordMeta.reference), style: {} });
    const state = object(metadata(record, 'x_state'));
    for (const key of ['entry', 'do', 'exit'])
        if (state[key])
            result.push({ group: 'behavior', label: `${key} / ${str(state[key])}`, style: {} });
    for (const item of array(state.internal))
        result.push({ group: 'internal', label: str(item), style: {} });
    const members = memberRecords(entry, all);
    for (const member of members) {
        const meta = object(metadata(member.record, 'x_member')), content = object(member.record.content), block = object(metadata(member.record, 'x_block'));
        if (str(member.record.role).toLowerCase().includes('port') || metadata(member.record, 'x_pin') || profile === 'orm.basic@1' && record.role === 'orm.facttype')
            continue;
        const kind = str(meta.kind, 'attribute');
        const visibility = { public: '+', private: '-', protected: '#', package: '~' }[str(meta.visibility)] ?? '';
        const part = object(metadata(member.record, 'x_part')), flow = object(metadata(member.record, 'x_flow'));
        const classifier = resolveRecord(all, part.classifier, member.file) ?? (part.classifier ? all.find(candidate => candidate.file === member.file && (candidate.ref.id === part.classifier || candidate.record.name === part.classifier)) : undefined);
        const suffix = str(content.type) || str(content.datatype) || (classifier ? titleOf(classifier.record) : str(part.classifier).replace(/^declared-classifier:/, '')), multiplicity = str(meta.multiplicity, str(part.multiplicity)), modifiers = array(meta.modifiers).map(String);
        const value = content.value, unit = object(metadata(member.record, 'x_unit'));
        const text = `${flow.direction ? str(flow.direction) + ' ' : ''}${visibility}${meta.derived ? '/' : ''}${titleOf(member.record)}${kind === 'operation' && !titleOf(member.record).includes('(') ? '()' : ''}${suffix ? ': ' + suffix : ''}${multiplicity ? ' [' + multiplicity + ']' : ''}${value !== undefined ? ' = ' + String(value) : ''}${modifiers.length ? ' {' + modifiers.join(', ') + '}' : ''}${unit.unit ? ' [' + str(unit.unit) + (unit.quantity ? '; ' + str(unit.quantity) : '') + ']' : ''}`;
        result.push({ group: str(block.compartment, kind === 'operation' ? 'operations' : kind === 'literal' ? 'literals' : 'attributes'), label: text, style: { ...(meta.static ? { 'text-decoration': 'underline' } : {}), ...(meta.abstract ? { 'font-style': 'italic' } : {}) }, source: member });
    }
    const vsm = object(metadata(record, 'x_vsm'));
    for (const key of ['va', 'nva'])
        if (vsm[key] !== undefined)
            result.push({ group: 'process data', label: `${key.toUpperCase()}: ${String(vsm[key])} ${str(vsm.unit)}`, style: {} });
    const rawValues = metadata(record, 'x_values'), values = array(Array.isArray(rawValues) ? rawValues : object(rawValues).values);
    if (values.length)
        result.push({ group: 'value constraints', label: '{' + values.map(String).join(', ') + '}', style: {} });
    const derive = metadata(record, 'x_derive');
    if (derive)
        result.push({ group: 'derivation', label: typeof derive === 'string' ? derive : str(object(derive).text), style: {} });
    if (profile === 'family.tree@1') {
        const birth = metadata(record, 'x_birth'), death = metadata(record, 'x_death');
        if (birth !== undefined || death !== undefined)
            result.push({ group: 'dates', label: `${birth ?? '?'} – ${death ?? ''}`, style: {} });
    }
    const instance = object(metadata(record, 'x_instance')), classifier = resolveRecord(all, instance.classifier, entry.definition.file);
    if (classifier)
        result.push({ group: 'instance', label: ': ' + titleOf(classifier.record), style: {} });
    for (const [name, value] of Object.entries(object(instance.slots)))
        result.push({ group: 'slots', label: `${name} = ${typeof value === 'string' ? value : JSON.stringify(value)}`, style: {} });
    for (const extension of array(object(metadata(record, 'x_usecase')).extension_points))
        result.push({ group: 'extension points', label: str(extension), style: {} });
    if (profile === 'erd.crowfoot@1' && !members.length && entry.appearance?.record.body !== 'title') {
        let data = object(record.data);
        const source = resolveRecord(all, data.source, entry.definition.file);
        if (source?.owner === 'data')
            data = source.record;
        if (!Array.isArray(data.rows))
            data = object(data.snapshot);
        const columns = array(data.columns).map(object), visibility = { ...object(record.column_visibility), ...object(entry.appearance?.record.column_visibility) };
        for (const row of array(data.rows))
            result.push({ group: 'fields', label: array(row).filter((_, index) => visibility[str(columns[index]?.id)] !== 'hidden').map(value => value === null ? '' : String(value)).join('  '), style: {} });
    }
    const boxed = object(metadata(record, 'x_boxed'));
    if (boxed.form === 'literal' || boxed.form === 'invocation')
        result.push({ group: 'boxed ' + str(boxed.form), label: str(boxed.text), style: {} });
    if (boxed.form === 'context' || boxed.form === 'relation')
        for (const entry of array(boxed.entries).map(object))
            result.push({ group: 'boxed ' + str(boxed.form), label: `${str(entry.name)}: ${str(entry.text)}`, style: {}, cells: [str(entry.name), str(entry.text)] });
    const pack = object(metadata(record, 'x_pack')), ownerPackage = resolveRecord(all, pack.package, entry.definition.file);
    if (pack.visibility || ownerPackage)
        result.push({ group: 'package', label: [pack.visibility, ownerPackage ? 'package ' + titleOf(ownerPackage.record) : ''].filter(Boolean).join(' · '), style: {} });
    const evidence = object(metadata(record, 'x_evidence'));
    if (evidence.result)
        result.push({ group: 'evidence', label: `${str(evidence.result)} · ${str(evidence.observed_at)}`, style: {} });
    const choreography = resolveRecord(all, object(metadata(record, 'x_contract')).choreography, entry.definition.file);
    if (choreography)
        result.push({ group: 'service contract', label: 'choreography: ' + titleOf(choreography.record), style: {} });
    const continuation = object(metadata(record, 'x_continuation'));
    if (continuation.key)
        result.push({ group: 'continuation', label: `${str(continuation.side)} ${str(continuation.key)}${recordMeta.continuation_page ? ' · page ' + String(recordMeta.continuation_page) : ''}`.trim(), style: {} });
    const jump = resolveRecord(all, object(metadata(record, 'x_jump')).target, entry.definition.file);
    if (jump)
        result.push({ group: 'control', label: 'jump ' + titleOf(jump.record), style: {} });
    const c4 = array(object(metadata(record, 'x_c4tag')).tags);
    if (c4.length)
        result.push({ group: 'tags', label: c4.map(String).join(', '), style: {} });
    const interfaces = object(metadata(record, 'x_interfaces'));
    for (const key of ['provides', 'requires']) {
        const names = array(interfaces[key]).map(ref => resolveRecord(all, ref, entry.definition.file)).filter((record) => !!record).map(record => titleOf(record.record));
        if (names.length)
            result.push({ group: 'interfaces', label: key + ': ' + names.join(', '), style: {} });
    }
    const sentry = object(metadata(record, 'x_sentry'));
    if (sentry.if_part)
        result.push({ group: 'criterion', label: '[' + str(sentry.if_part) + ']', style: {} });
    if (state.submachine) {
        const view = resolveRecord(all, state.submachine, entry.definition.file);
        if (view)
            result.push({ group: 'behavior', label: 'ref ' + titleOf(view.record), style: {} });
    }
    for (const constraint of array(metadata(record, 'x_timeconstraint')))
        result.push({ group: 'time constraints', label: str(constraint), style: {} });
    return result.flatMap(row => { if (row.cells)
        return [row]; const words = row.label.split(/\s+/), lines = []; for (const word of words) {
        const last = lines.at(-1);
        if (last && last.length + word.length < 65)
            lines[lines.length - 1] = last + ' ' + word;
        else
            lines.push(word);
    } return lines.map(label => ({ ...row, label })); });
}
function glyphStyle(entry, profile) {
    const render = roleDescriptor(str(entry.definition.record.role))?.render ?? {}, borderWidth = num(styled(entry, 'border.width', 0));
    return { fill: str(styled(entry, 'background.color', styled(entry, 'symbol.fill', render.fill)), profile === 'wireframe.ui@1' ? '#f8fafc' : '#fff'), stroke: str(styled(entry, borderWidth > 0 ? 'border.color' : 'symbol.color', render.colour), '#475569'), width: borderWidth > 0 ? borderWidth : num(styled(entry, 'symbol.width', 1.5), 1.5), look: str(pathValue(entry.effective, 'style.look')), seed: num(pathValue(entry.effective, 'style.seed'), 42), roughness: num(pathValue(entry.effective, 'style.roughness'), 1) };
}
function decorateNode(entry, all, profile, preserveBounds = false) {
    if (entry.standalone)
        return entry;
    const record = entry.definition.record, role = str(record.role), effective = entry.effective;
    // Crow's-foot changes relation notation; its progressive entity body keeps
    // the same measured columns/draft editor presentation as native DDN.
    if (profile === 'erd.crowfoot@1' && entry.item.primitives.length && ['columns', 'draft', 'notes'].includes(str(entry.appearance?.record.body, str(effective.body))))
        return entry;
    let bounds = preserveBounds ? entry.item.bounds : dimensions(entry, profile);
    const rows = compartmentRows(entry, all, profile), { fill, stroke, width } = glyphStyle(entry, profile), textScale = num(pathValue(effective, 'style.font_size'), 16) / 16;
    const nativeCard = !role.includes('.') && !!roleDescriptor(role), title = str(entry.appearance?.record.title) || titleOf(record), decorated = rows.length > 0 && !role.startsWith('ladder.');
    if (nativeCard && !profile.startsWith('chen.')) {
        const header = coreCardText(role, title, bounds.width, textScale);
        if (!preserveBounds && pathValue(effective, 'size.height') === undefined)
            bounds = { ...bounds, height: Math.max(bounds.height, header.height) };
    }
    if (role === 'orm.facttype')
        bounds = { ...bounds, height: Math.max(bounds.height, 112 + rows.length * 24) };
    if (decorated)
        bounds = { ...bounds, height: Math.max(bounds.height, (58 + rows.length * 23 + new Set(rows.map(r => r.group)).size * 18) * Math.max(1, textScale) + (nativeCard ? coreCardText(role, title, bounds.width, textScale).height : 0)), width: Math.max(bounds.width, ...rows.map(r => Math.min(520, r.label.length * 7 * textScale + 24))) };
    const typed = role.startsWith('uaf.') || role.startsWith('req.') || role.startsWith('sysml.') || role.startsWith('soaml.') || ['uml.class', 'uml.device', 'uml.executionenv', 'uml.artifact', 'uml.interface', 'uml.enumeration', 'uml.stereotype', 'uml.metaclass', 'c4.component', 'c4.deploymentnode', 'sdl.signalset', 'sdl.procedure', 'flow.offpage', 'idef0.activity'].includes(role);
    const actorType = roleDescriptor(role)?.render.silhouette === 'actor';
    const typeName = str(roleDescriptor(role)?.render.text_label, role.slice(role.indexOf('.') + 1));
    const typeLines = typed ? wrapCell(`«${typeName}»`, Math.max(8, bounds.width - 24), value => value.length * 11 * textScale * .6, 64).lines : [];
    const titleLines = wrapCell(title, Math.max(8, bounds.width - 24), value => value.length * 15 * textScale * .6, 64).lines;
    const typeHeight = typeLines.length * 13 * textScale;
    const header = nativeCard ? coreCardText(role, title, bounds.width, textScale) : undefined;
    const headingHeight = header?.height ?? (12 + typeHeight + titleLines.length * 18 * textScale + 10);
    if (!preserveBounds && pathValue(effective, 'size.height') === undefined && (decorated || typed && !actorType))
        bounds = { ...bounds, height: Math.max(bounds.height, headingHeight + (decorated ? (rows.length * 23 + new Set(rows.map(row => row.group)).size * 18 + 8) * Math.max(1, textScale) : 0)) };
    let primitives = nodeGlyph(role, record, bounds, { profile, title: decorated || typed && !actorType ? '' : title, textScale, ...glyphStyle(entry, profile) });
    if (typed)
        for (const [i, value] of typeLines.entries())
            primitives.push(label(value, bounds.x + bounds.width / 2, actorType ? bounds.y - 8 - (typeLines.length - 1 - i) * 13 * textScale : bounds.y + 16 * textScale + i * 13 * textScale, 11, stroke, { 'text-anchor': 'middle' }));
    if (decorated || typed && !actorType) {
        const lines = header?.titleLines ?? titleLines, titleX = header ? bounds.x + header.titleOffset + header.titleWidth / 2 : bounds.x + bounds.width / 2;
        const firstY = decorated ? bounds.y + (header ? 20 * textScale : 12 + typeHeight + 15 * textScale) : bounds.y + Math.max(12 + typeHeight + 15 * textScale, typeHeight + (bounds.height - typeHeight) / 2 - (lines.length - 1) * 9 * textScale + 5 * textScale);
        for (const [i, value] of lines.entries())
            primitives.push(label(value, titleX, firstY + i * 18 * textScale, 15, '#1e293b', { 'text-anchor': 'middle', 'font-weight': 600, ...(profile.startsWith('uml.object') ? { 'text-decoration': 'underline' } : {}) }));
    }
    if (decorated) {
        let y = bounds.y + headingHeight, group = '';
        for (const row of rows) {
            if (group !== row.group) {
                primitives.push(line([bounds.x, y], [bounds.x + bounds.width, y], stroke, .8));
                if (profile.startsWith('sysml.') || profile.startsWith('soaml.') || profile.startsWith('uml.') || profile === 'orm.basic@1') {
                    y += 14 * Math.max(1, textScale);
                    primitives.push(label(row.group.toUpperCase(), bounds.x + 8, y, 10, '#64748b'));
                }
                group = row.group;
            }
            y += 22 * Math.max(1, textScale);
            if (row.cells) {
                const split = bounds.x + bounds.width * .35;
                primitives.push(box({ x: bounds.x, y: y - 17, width: bounds.width, height: 22 }, 'none', stroke, .7), line([split, y - 17], [split, y + 5], stroke, .7), label(row.cells[0] ?? '', bounds.x + 8, y, 12), label(row.cells[1] ?? '', split + 8, y, 12));
            }
            else
                primitives.push(label(row.label, bounds.x + 10, y, 13, '#1e293b', row.style));
        }
    }
    const template = metadata(record, 'x_template');
    if (template) {
        const parameters = typeof template === 'string' ? [template] : array(object(template).parameters).map(value => typeof value === 'string' ? value : [object(value).name, object(value).type ? ': ' + str(object(value).type) : '', object(value).default ? ' = ' + String(object(value).default) : ''].join(''));
        const values = parameters.length ? parameters : ['template'], height = values.length * 14 + 10, top = bounds.y - height + 8, width = Math.max(80, Math.min(bounds.width, Math.max(...values.map(value => value.length)) * 6 + 12)), left = bounds.x + bounds.width - width + 10;
        primitives.push(box({ x: left, y: top, width, height }, '#fff', stroke, 1, '4 3'), ...values.map((value, i) => label(value, left + 6, top + 14 + i * 14, 10)));
    }
    if (role === 'orm.facttype') {
        const roles = memberRecords(entry, all), cellWidth = Math.min(80, (bounds.width - 24) / Math.max(2, roles.length));
        roles.forEach((member, i) => {
            const flags = object(metadata(member.record, 'x_role'));
            primitives.push(label(titleOf(member.record), bounds.x + 12 + (i + .5) * cellWidth, bounds.y + bounds.height - 14, 12, stroke, { 'text-anchor': 'middle' }));
            if (flags.uniqueness)
                primitives.push(line([bounds.x + 12 + i * cellWidth + 3, bounds.y + bounds.height - 34], [bounds.x + 12 + (i + 1) * cellWidth - 3, bounds.y + bounds.height - 34], '#475569', 2));
            if (flags.mandatory)
                primitives.push(oval({ x: bounds.x + 12 + (i + .5) * cellWidth - 3, y: bounds.y + bounds.height - 4, width: 6, height: 6 }, '#334155', '#334155'));
        });
        const objectified = object(metadata(record, 'x_objectified'));
        if (objectified.name)
            primitives.push(box({ x: bounds.x - 12, y: bounds.y - 20, width: bounds.width + 24, height: bounds.height + 32 }, 'none', '#475569', 1, '5 3'), label(str(objectified.name), bounds.x + 3, bounds.y - 6, 12));
    }
    const subdiagram = metadata(record, 'x_subdiagram');
    if (subdiagram) {
        const raw = object(subdiagram).view, target = resolveRecord(all, raw, entry.definition.file) ?? all.find(item => item.file === entry.definition.file && (item.ref.id === raw || item.record.name === raw));
        primitives.push(label('ref ' + (target ? titleOf(target.record) : str(raw)), bounds.x + 7, bounds.y + bounds.height - 6, 11, stroke));
    }
    const use = object(metadata(record, 'x_use'));
    if (use.arguments)
        primitives.push(label('(' + array(use.arguments).map(String).join(', ') + ')', bounds.x + 8, bounds.y + bounds.height + 16, 11, stroke));
    if (use.gates)
        array(use.gates).forEach((gate, i) => primitives.push(box({ x: bounds.x - 4, y: bounds.y + 18 + i * 18, width: 8, height: 8 }, '#fff', stroke), label(str(gate), bounds.x + 9, bounds.y + 25 + i * 18, 10)));
    const ports = memberRecords(entry, all).filter(member => /port/i.test(str(member.record.role)) || metadata(member.record, 'x_port') || metadata(member.record, 'x_fbd') || metadata(member.record, 'x_icom') || metadata(member.record, 'x_pin'));
    ports.forEach((port, i) => {
        const content = object(port.record.content), p = object(metadata(port.record, 'x_port')), fbd = object(metadata(port.record, 'x_fbd')), icom = object(metadata(port.record, 'x_icom'));
        const side = str(content.side, str(pathValue(port.record, 'properties.side'), str(icom.type, str(content.direction) === 'output' ? 'east' : 'west')));
        const fraction = num(content.fraction, num(pathValue(port.record, 'properties.fraction'), (i + 1) / (ports.length + 1)));
        const x = side === 'north' || side === 'control' || side === 'south' || side === 'mechanism' ? bounds.x + bounds.width * fraction : side === 'east' || side === 'output' ? bounds.x + bounds.width : bounds.x;
        const y = side === 'north' || side === 'control' ? bounds.y : side === 'south' || side === 'mechanism' ? bounds.y + bounds.height : bounds.y + bounds.height * fraction;
        const pb = { x: x - 6, y: y - 6, width: 12, height: 12 };
        primitives.push(box(pb, p.type === 'full' ? '#cbd5e1' : '#fff', stroke), label(`${p.type ? '«' + str(p.type) + '» ' : ''}${p.conjugated ? '~' : ''}${titleOf(port.record)}${p.multiplicity ? ' [' + str(p.multiplicity) + ']' : ''}${fbd.type ? ': ' + str(fbd.type) : ''}`, x + 10, y - 6, 10, stroke));
        if (fbd.negated)
            primitives.push(oval({ x: x - 4, y: y - 4, width: 8, height: 8 }, '#fff', stroke));
        const service = object(metadata(port.record, 'x_service'));
        if (service.kind)
            primitives.push(label(service.kind === 'request' ? '«Request»' : '«Service»', x + 8, y + 16, 9, stroke));
        if (object(metadata(port.record, 'x_pin')).streaming)
            primitives.push(label('≫', x - 5, y + 4, 10, stroke));
        array(p.nested).forEach((nested, index) => { primitives.push(box({ x: x + index * 11 - 4, y: y + 12, width: 9, height: 9 }, '#fff', stroke), label(str(object(nested).name), x + index * 11, y + 31, 8)); });
    });
    if (role === 'ladder.jump') {
        const target = resolveRecord(all, object(metadata(record, 'x_jump')).target, entry.definition.file);
        if (target)
            primitives.push(label('→ ' + titleOf(target.record), bounds.x + 4, bounds.y + bounds.height + 16, 11, stroke));
    }
    const status = str(pathValue(record, 'design.state'), 'draft');
    primitives.push({ kind: 'ellipse', bounds: { x: bounds.x + bounds.width - 10, y: bounds.y - 4, width: 8, height: 8 }, paint: { fill: status === 'accepted' ? '#15803d' : status === 'in-review' ? '#7c3aed' : status === 'in-progress' ? '#2563eb' : '#d97706', stroke: '#fff', 'stroke-width': 1, 'ddn-design-status': status } });
    const imageRef = pathValue(effective, 'background.image'), asset = imageRef ? resolveRecord(all, imageRef, entry.definition.file) : undefined;
    if (asset)
        primitives.push({ kind: 'image', assetId: refKey(asset.ref), bounds: { x: bounds.x + 8, y: bounds.y + 8, width: 24, height: 24 } });
    const look = str(pathValue(effective, 'style.look'));
    if (look === 'neo' && primitives[0]) {
        const shadow = shadowPrimitive(primitives[0]);
        if (shadow)
            primitives.unshift(shadow);
    }
    return changed(entry, bounds, primitives, `${profile}; ${role}; ${status}`);
}
function chen(entries, all, profile, diagnostics, unavailable, view, frame, effective) {
    const direct = (owner) => memberRecords(owner, all).filter(member => { const parent = resolveRecord(all, member.record.parent ?? pathValue(member.record, 'content.parent'), member.file); return !parent || refKey(parent.ref) === refKey(owner.definition.ref); });
    const span = (owner, level = 0, trail = new Set()) => { const key = refKey(owner.definition.ref); if (level > 8 || trail.has(key))
        return 155; const next = new Set(trail); next.add(key); const children = direct(owner); return Math.max(155, children.reduce((sum, member) => sum + span({ ...owner, definition: member }, level + 1, next), 0)); };
    const originals = entries.filter(e => e.definition.record.category !== 'relation'), attributeWidth = Math.max(240, ...originals.map(node => span(node))), edges = entries.filter(e => e.definition.record.category === 'relation'), nodes = layoutGraph(originals, edges, all, profile, frame, view, { ...effective, layout: { ...object(effective?.layout ?? view.record.layout), gap: attributeWidth + 80, row_gap: 360 } });
    const result = nodes.map(node => decorateNode(node, all, profile, true));
    for (const node of [...result]) {
        const b = node.item.bounds, weak = object(metadata(node.definition.record, 'x_chen')).weak;
        if (weak && !node.standalone)
            result[result.indexOf(node)] = changed(node, b, [...node.item.primitives, box({ x: b.x + 5, y: b.y + 5, width: b.width - 10, height: b.height - 10 }, 'none')]);
        const visit = (parent, parentBounds, members, level, trail) => {
            const spans = members.map(member => span({ ...node, definition: member }, level, trail)), total = spans.reduce((sum, value) => sum + value, 0);
            let cursor = parentBounds.x + parentBounds.width / 2 - total / 2;
            members.forEach((member, i) => {
                const key = refKey(member.ref);
                if (trail.has(key) || level > 8) {
                    diagnostics.push({ code: 'chen-attribute-depth', severity: 'warning', message: 'Attribute expansion is cyclic or exceeds eight nested levels.', target: member.ref });
                    unavailable.push('chen-attributes:' + key);
                    return;
                }
                const next = new Set(trail);
                next.add(key);
                const meta = object(metadata(member.record, 'x_chen')), bounds = { x: cursor + (spans[i] - 135) / 2, y: parentBounds.y + parentBounds.height + 70, width: 135, height: 48 };
                cursor += spans[i];
                const ps = [line(boundaryPoint(parentBounds, center(bounds)), boundaryPoint(bounds, center(parentBounds))), oval(bounds, '#fff', '#64748b', 1.3, meta.derived ? '5 3' : undefined)];
                if (meta.multivalued)
                    ps.push(oval({ x: bounds.x + 4, y: bounds.y + 4, width: bounds.width - 8, height: bounds.height - 8 }, 'none', '#64748b'));
                ps.push(label(titleOf(member.record), bounds.x + bounds.width / 2, bounds.y + 29, 13, '#1e293b', { 'text-anchor': 'middle', ...(meta.key || pathValue(member.record, 'content.key') === 'primary' ? { 'text-decoration': 'underline' } : {}) }));
                if (meta.partial_key)
                    ps.push(line([bounds.x + 18, bounds.y + 34], [bounds.x + bounds.width - 18, bounds.y + 34], '#475569', 1, '4 3'));
                result.push(mark(node, member, 'attribute:' + key, bounds, ps, `Generated Chen attribute of ${titleOf(parent.record)}; source field identity`));
                const childEntry = { ...node, definition: member };
                visit(member, bounds, direct(childEntry), level + 1, next);
            });
        };
        visit(node.definition, b, direct(node), 0, new Set([refKey(node.definition.ref)]));
    }
    for (const edge of edges) {
        const participants = [endEntry(edge, 0, nodes, all), endEntry(edge, 1, nodes, all)].filter((v) => !!v);
        for (const end of array(object(metadata(edge.definition.record, 'x_nary')).ends)) {
            const target = resolveRecord(all, object(end).element, edge.definition.file);
            const node = target && nodes.find(n => refKey(n.definition.ref) === refKey(target.ref));
            if (node && !participants.includes(node))
                participants.push(node);
        }
        if (participants.length < 2)
            continue;
        const centers = participants.map(n => center(n.item.bounds)), x = centers.reduce((sum, p) => sum + p[0], 0) / centers.length, y = centers.reduce((sum, p) => sum + p[1], 0) / centers.length;
        const b = { x: x - 58, y: y - 32, width: 116, height: 64 }, ps = [];
        const meta = object(metadata(edge.definition.record, 'x_chen'));
        participants.forEach((node, i) => {
            const p = center(node.item.bounds);
            ps.push(line(boundaryPoint(b, p), boundaryPoint(node.item.bounds, [x, y])));
            const cardinality = object(meta[i === 0 ? 'from' : 'to']);
            const extra = object(array(object(metadata(edge.definition.record, 'x_nary')).ends)[i - 2]);
            const annotation = i > 1 ? [extra.role, extra.multiplicity].filter(Boolean).join(' ') : cardinality.min !== undefined || cardinality.max !== undefined ? `(${cardinality.min ?? '?'},${cardinality.max ?? '?'})` : '';
            if (annotation)
                ps.push(label(annotation, (x + p[0]) / 2, (y + p[1]) / 2 - 5, 11));
        });
        ps.push(polygon([[x, b.y], [b.x + b.width, y], [x, b.y + b.height], [b.x, y]]));
        if (meta.identifying)
            ps.push(polygon([[x, b.y + 5], [b.x + b.width - 8, y], [x, b.y + b.height - 5], [b.x + 8, y]], 'none'));
        const caption = relationCaption(edge, edgeLabel(edge, all), effective);
        if (caption)
            ps.push(label(caption, x, y + 4, 11, '#1e293b', { 'text-anchor': 'middle' }));
        const edgeBounds = finiteBounds([Math.min(b.x, ...centers.map(p => p[0])), Math.min(b.y, ...centers.map(p => p[1]))], [Math.max(b.x + b.width, ...centers.map(p => p[0])), Math.max(b.y + b.height, ...centers.map(p => p[1]))], 12);
        result.push(changed(edge, edgeBounds, ps, `Chen relationship; ${participants.length} participants`));
    }
    const shift = Math.max(0, frame.x + 32 - Math.min(...result.map(entry => entry.item.bounds.x)));
    return result.map(entry => ({ ...entry, item: { ...entry.item, bounds: { ...entry.item.bounds, x: entry.item.bounds.x + shift }, transform: [entry.item.transform[0], entry.item.transform[1], entry.item.transform[2], entry.item.transform[3], entry.item.transform[4] + shift, entry.item.transform[5]], hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, x: hit.bounds.x + shift } })) } }));
}
function sequence(entries, all, profile, frame, diagnostics, unavailable, viewProperties) {
    const participants = entries.filter(e => e.definition.record.category !== 'relation'), edges = entries.filter(e => e.definition.record.category === 'relation'), result = [];
    const messageY = new Map();
    edges.forEach((edge, i) => messageY.set(refKey(edge.definition.ref), frame.y + 170 + i * 65));
    const positions = new Map();
    const yEnd = frame.y + 210 + Math.max(1, edges.length) * 65;
    participants.forEach((entry, i) => {
        if (entry.definition.record.role === 'msc.hmscref') {
            const b = { x: frame.x + 45 + participants.filter(p => p.definition.record.role === 'msc.hmscref').indexOf(entry) * 380, y: yEnd + 30, width: 350, height: 95 }, sub = object(metadata(entry.definition.record, 'x_subdiagram')), params = array(object(metadata(entry.definition.record, 'x_hmscref')).params);
            result.push(changed(entry, b, [box(b, '#fff', '#475569'), path(`M${b.x},${b.y + 25}H${b.x + 40}L${b.x + 50},${b.y + 15}V${b.y}`, 'none'), label('ref', b.x + 8, b.y + 17, 11), label(titleOf(entry.definition.record), b.x + 15, b.y + 48, 14), label(params.length ? '(' + params.map(String).join(', ') + ')' : '', b.x + 15, b.y + 73, 12)], 'HMSC reference with declared actual parameters'));
            return;
        }
        const b = { x: frame.x + 45 + participants.filter(p => p.definition.record.role !== 'msc.hmscref').indexOf(entry) * 245, y: frame.y + 60, width: 180, height: 60 }, x = b.x + b.width / 2;
        positions.set(refKey(entry.definition.ref), b);
        const creation = edges.find(edge => object(metadata(edge.definition.record, 'x_message')).sort === 'create' && endEntry(edge, 1, participants, all) === entry);
        if (creation)
            b.y = (messageY.get(refKey(creation.definition.ref)) ?? b.y) - b.height / 2;
        const deletion = edges.find(edge => object(metadata(edge.definition.record, 'x_message')).sort === 'delete' && endEntry(edge, 1, participants, all) === entry), end = deletion ? messageY.get(refKey(deletion.definition.ref)) ?? yEnd : yEnd;
        const ps = nodeGlyph(str(entry.definition.record.role), entry.definition.record, b, { title: titleOf(entry.definition.record), profile, ...glyphStyle(entry, profile) });
        for (const [index, constraint] of array(metadata(entry.definition.record, 'x_timeconstraint')).entries())
            ps.push(label(str(constraint), b.x + 4, b.y + b.height + 15 + index * 14, 10, '#475569'));
        ps.push(line([x, b.y + b.height], [x, end], '#64748b', 1, '6 5'));
        if (deletion)
            ps.push(line([x - 9, end - 9], [x + 9, end + 9], '#334155', 2), line([x + 9, end - 9], [x - 9, end + 9], '#334155', 2));
        const activations = array(metadata(entry.definition.record, 'x_activation'));
        if (activations.length)
            activations.forEach((value, index) => {
                const activation = object(value), from = resolveRecord(all, activation.from, entry.definition.file), to = resolveRecord(all, activation.to, entry.definition.file);
                const start = from && messageY.get(refKey(from.ref)), stop = to && messageY.get(refKey(to.ref));
                if (start !== undefined && stop !== undefined)
                    ps.push(box({ x: x - 6 + index * 3, y: Math.min(start, stop), width: 12, height: Math.max(15, Math.abs(stop - start)) }, '#e2e8f0', '#475569'));
            });
        else {
            const calls = edges.filter(edge => endEntry(edge, 1, participants, all) === entry && !['reply', 'delete', 'create', 'lost'].includes(str(object(metadata(edge.definition.record, 'x_message')).sort)));
            for (const edge of calls) {
                const start = messageY.get(refKey(edge.definition.ref)), caller = endEntry(edge, 0, participants, all);
                const reply = edges.find(candidate => messageY.get(refKey(candidate.definition.ref)) > start && endEntry(candidate, 0, participants, all) === entry && endEntry(candidate, 1, participants, all) === caller && (object(metadata(candidate.definition.record, 'x_message')).sort === 'reply' || metadata(candidate.definition.record, 'x_return') === true));
                const stop = reply ? messageY.get(refKey(reply.definition.ref)) : Math.max(start + 32, ...edges.filter(candidate => endEntry(candidate, 0, participants, all) === entry).map(candidate => messageY.get(refKey(candidate.definition.ref))));
                ps.push(box({ x: x - 6, y: start, width: 12, height: Math.max(24, stop - start) }, '#e2e8f0', '#475569'));
            }
        }
        for (const value of array(metadata(entry.definition.record, 'x_invariant'))) {
            const invariant = object(value), after = resolveRecord(all, invariant.after, entry.definition.file), yy = (after && messageY.get(refKey(after.ref)) || b.y + b.height) + 20;
            if (invariant.role)
                ps.push(label(str(invariant.role), x - 70, yy - 3, 9, '#64748b'));
            ps.push(polygon([[x - 70, yy], [x + 70, yy], [x + 80, yy + 12], [x + 70, yy + 24], [x - 70, yy + 24], [x - 80, yy + 12]], '#fff'), label(str(invariant.label), x, yy + 16, 11, '#334155', { 'text-anchor': 'middle' }));
        }
        result.push(changed(entry, { ...b, height: end - b.y + 10 }, ps, `Participant lifeline; ${profile}`));
    });
    for (const edge of edges) {
        const a = endEntry(edge, 0, participants, all), b = endEntry(edge, 1, participants, all);
        if (!a || !b)
            continue;
        const ab = positions.get(refKey(a.definition.ref)), bb = positions.get(refKey(b.definition.ref)), y = messageY.get(refKey(edge.definition.ref));
        if (!ab || !bb) {
            diagnostics.push({ code: 'sequence-participant-required', severity: 'error', message: 'Messages require participant lifelines, not reference boxes.', target: edge.definition.ref });
            unavailable.push('sequence-message:' + refKey(edge.definition.ref));
            continue;
        }
        const message = object(metadata(edge.definition.record, 'x_message')), sort = str(message.sort, metadata(edge.definition.record, 'x_return') ? 'reply' : 'synch');
        let x1 = ab.x + ab.width / 2, x2 = bb.x + bb.width / 2;
        if (sort === 'create')
            x2 = bb.x;
        if (sort === 'lost')
            x2 = x1 + (x2 >= x1 ? 110 : -110);
        if (sort === 'found')
            x1 = x2 + (x1 > x2 ? 110 : -110);
        const ps = [], self = a === b && !['lost', 'found'].includes(sort);
        if (self)
            ps.push(path(`M${x1},${y}H${x1 + 70}V${y + 25}H${x1}`, 'none', '#475569', 1.5, sort === 'reply' ? '6 4' : undefined), ...arrowMarker([x1, y + 25], [x1 + 70, y + 25], sort === 'synch' ? 'filled' : 'open'));
        else
            ps.push(line([x1, y], [x2, y], '#475569', 1.5, sort === 'reply' ? '6 4' : undefined), ...arrowMarker([x2, y], [x1, y], sort === 'synch' ? 'filled' : 'open'));
        if (sort === 'lost' || sort === 'found') {
            const x = sort === 'lost' ? x2 : x1;
            ps.push(oval({ x: x - 5, y: y - 5, width: 10, height: 10 }, '#334155', '#334155'));
        }
        const caption = relationCaption(edge, (message.seq ? '' : String(edges.indexOf(edge) + 1) + ': ') + edgeLabel(edge, all), viewProperties);
        if (caption)
            ps.push(label(caption, (x1 + x2) / 2 + (self ? 35 : 0), y - 8, 12, '#334155', { 'text-anchor': 'middle' }));
        const bounds = finiteBounds([x1, y], [x2 + (self ? 70 : 0), y + 25], 12);
        result.push(changed(edge, bounds, ps, `Message ${sort}; declaration order ${edges.indexOf(edge) + 1}`));
        const fragment = object(metadata(edge.definition.record, 'x_fragment'));
        const drawFragment = (data, level) => {
            if (level > 12) {
                diagnostics.push({ code: 'sequence-fragment-depth', severity: 'warning', message: 'Fragment projection exceeds twelve nested levels.', target: edge.definition.ref });
                unavailable.push('sequence-fragment:' + refKey(edge.definition.ref));
                return;
            }
            const ys = array(data.operands).flatMap(value => array(object(value).messages).map(reference => resolveRecord(all, reference, edge.definition.file)).filter((r) => !!r).map(r => messageY.get(refKey(r.ref))).filter((v) => v !== undefined));
            if (!ys.length)
                return;
            const fb = { x: frame.x + 18 + level * 8, y: Math.min(...ys) - 27, width: Math.max(260, participants.length * 245 - 8 - level * 16), height: Math.max(...ys) - Math.min(...ys) + 65 }, fps = [box(fb, 'none', '#64748b'), polygon([[fb.x, fb.y], [fb.x + 70, fb.y], [fb.x + 70, fb.y + 14], [fb.x + 60, fb.y + 24], [fb.x, fb.y + 24]], '#f8fafc', '#64748b'), label(str(data.operator), fb.x + 6, fb.y + 16, 11)];
            array(data.operands).forEach((value, index) => {
                const operand = object(value), referenced = array(operand.messages).map(ref => resolveRecord(all, ref, edge.definition.file)).filter((r) => !!r), points = referenced.map(r => messageY.get(refKey(r.ref))).filter((v) => v !== undefined), yy = points.length ? Math.min(...points) - 24 : fb.y;
                if (index)
                    fps.push(line([fb.x, yy], [fb.x + fb.width, yy], '#64748b', 1, '5 4'));
                if (operand.guard)
                    fps.push(label('[' + str(operand.guard) + ']', fb.x + 80, yy + 16, 11));
                for (const nested of array(operand.fragments))
                    drawFragment(object(nested), level + 1);
            });
            result.push(mark(edge, edge.definition, `fragment:${level}:${result.length}`, fb, fps, `Combined fragment ${str(data.operator)}`));
        };
        if (fragment.operator)
            drawFragment(fragment, 0);
    }
    return result;
}
function timing(entries, all, profile, frame, diagnostics, unavailable, viewProperties) {
    const nodes = entries.filter(e => e.definition.record.category !== 'relation'), edges = entries.filter(e => e.definition.record.category === 'relation');
    const parsed = nodes.map(node => ({ node, states: array(metadata(node.definition.record, 'x_states')).map((value) => Array.isArray(value) ? { at: value[0], state: value[1] } : object(value)).map(value => ({ at: num(value.at, num(value.time, NaN)), state: str(value.state, str(value.value)), duration: str(value.duration), slew: str(value.slew) })) }));
    const times = parsed.flatMap(row => [...row.states.map(state => state.at), ...row.states.flatMap(state => (state.duration.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number)), ...array(metadata(row.node.definition.record, 'x_timeconstraint')).flatMap(value => (String(value).match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number))]).filter(Number.isFinite), min = Math.min(0, ...times), max = Math.max(1, ...times), plotX = frame.x + 170, plotW = Math.max(600, frame.width - 210), result = [];
    const sx = (time) => plotX + (time - min) / (max - min) * plotW;
    parsed.forEach(({ node, states }, row) => {
        const b = { x: frame.x + 25, y: frame.y + 65 + row * 165, width: plotW + 150, height: 145 }, labels = [...new Set(states.map(v => v.state))];
        if (!states.length || states.some((state, i) => !Number.isFinite(state.at) || !state.state || i > 0 && state.at <= states[i - 1].at)) {
            diagnostics.push({ code: 'timing-states-invalid', severity: 'error', target: node.definition.ref, message: 'Timing states require named values at finite, strictly increasing declared times.' });
            unavailable.push('timing:' + refKey(node.definition.ref));
            result.push(changed(node, b, [label(titleOf(node.definition.record), b.x, b.y + 20), label('Incomplete timing states', plotX, b.y + 60, 13, '#9f1239')]));
            return;
        }
        const sy = (state) => b.y + 32 + labels.indexOf(state) * 70 / Math.max(1, labels.length - 1), ps = [label(titleOf(node.definition.record), b.x, b.y + 16, 14), line([plotX, b.y + 118], [plotX + plotW, b.y + 118], '#94a3b8')];
        labels.forEach(state => ps.push(label(state, plotX - 10, sy(state) + 4, 11, '#64748b', { 'text-anchor': 'end' })));
        let d = `M${sx(states[0].at)},${sy(states[0].state)}`;
        states.forEach((state, i) => {
            if (i)
                d += `H${sx(state.at)}V${sy(state.state)}`;
            if (state.duration)
                ps.push(label(state.duration, sx(state.at) + 10, sy(state.state) - 23, 11, '#475569'));
            if (state.slew)
                ps.push(label(state.slew, sx(state.at) + 10, sy(state.state) + 20, 10, '#475569'));
            const until = states[i + 1]?.at ?? max;
            if (until > state.at)
                ps.push(label(state.state, (sx(state.at) + sx(until)) / 2, sy(state.state) - 8, 11, '#334155', { 'text-anchor': 'middle' }));
            ps.push(line([sx(state.at), b.y + 115], [sx(state.at), b.y + 122], '#64748b'), label(String(state.at), sx(state.at), b.y + 138, 10, '#475569', { 'text-anchor': 'middle' }));
        });
        d += `H${plotX + plotW}`;
        ps.push(path(d, 'none', glyphStyle(node, profile).stroke, 2));
        const constraint = metadata(node.definition.record, 'x_timeconstraint');
        if (constraint)
            ps.push(label(typeof constraint === 'string' ? constraint : Array.isArray(constraint) ? constraint.map(String).join('; ') : str(object(constraint).text, str(object(constraint).label)), plotX, b.y + 155, 10, '#475569'));
        for (const value of array(metadata(node.definition.record, 'x_duration'))) {
            const span = object(value), from = num(span.from), to = num(span.to);
            const yy = b.y + 12;
            ps.push(line([sx(from), yy], [sx(to), yy]), line([sx(from), yy - 4], [sx(from), yy + 4]), line([sx(to), yy - 4], [sx(to), yy + 4]), label(str(span.label, `{${from}..${to}}`), (sx(from) + sx(to)) / 2, yy - 7, 11, '#475569', { 'text-anchor': 'middle' }));
        }
        result.push(changed(node, b, ps, `Timing band; ${states.length} state changes; ${profile}`));
    });
    for (const edge of edges) {
        const a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all), at = num(object(metadata(edge.definition.record, 'x_message')).at, NaN);
        if (!a || !b || !Number.isFinite(at))
            continue;
        const y1 = frame.y + 115 + nodes.indexOf(a) * 165, y2 = frame.y + 115 + nodes.indexOf(b) * 165, x = sx(at);
        result.push(changed(edge, finiteBounds([x, y1], [x, y2], 15), [line([x, y1], [x, y2]), ...arrowMarker([x, y2], [x, y1]), ...(relationCaption(edge, edgeLabel(edge, all), viewProperties) ? [label(relationCaption(edge, edgeLabel(edge, all), viewProperties), x + 8, (y1 + y2) / 2, 11)] : [])], 'Timestamp-anchored lifeline message'));
    }
    return result;
}
function fishbone(entries, all, frame, diagnostics, unavailable, viewProperties) {
    const profile = 'fishbone.basic@1', nodes = entries.filter(e => e.definition.record.category !== 'relation'), edges = entries.filter(e => e.definition.record.category === 'relation'), effect = nodes.find(n => n.definition.record.role === 'quality.effect');
    if (!effect) {
        diagnostics.push({ code: 'fishbone-effect-missing', severity: 'error', message: 'Fishbone needs a selected effect.' });
        unavailable.push('fishbone:effect');
        return [...entries];
    }
    const incoming = new Map();
    for (const edge of edges) {
        const node = endEntry(edge, 0, nodes, all), parent = endEntry(edge, 1, nodes, all);
        if (!node || !parent)
            continue;
        const key = refKey(parent.definition.ref), list = incoming.get(key) ?? [];
        list.push({ node, edge });
        incoming.set(key, list);
    }
    let occurrence = 0, limited = false;
    const expand = (node, edge, level, ancestors) => {
        const key = refKey(node.definition.ref);
        if (ancestors.has(key) || level > 4 || occurrence >= 250) {
            limited = true;
            return;
        }
        const id = occurrence++, next = new Set([...ancestors, key]);
        const children = (incoming.get(key) ?? []).flatMap(pair => { const branch = expand(pair.node, pair.edge, level + 1, next); return branch ? [branch] : []; });
        return { node, edge, children, level, rows: 1 + children.reduce((sum, child) => sum + child.rows, 0), row: 0, y: 0, width: 0, occurrence: id };
    };
    const categories = (incoming.get(refKey(effect.definition.ref)) ?? []).flatMap(pair => { const branch = expand(pair.node, pair.edge, 0, new Set([refKey(effect.definition.ref)])); return branch ? [branch] : []; });
    if (limited) {
        unavailable.push('fishbone:bounded-traversal');
        diagnostics.push({ code: 'fishbone-bounded-traversal', severity: 'error', message: 'Fishbone requires acyclic cause branches within four cause levels and 250 occurrences.' });
    }
    const fontScale = (entry) => Math.max(.25, num(pathValue(entry.effective, 'style.font_size'), 16) / 16);
    const textWidth = (branch) => graphLabelBounds(titleOf(branch.node.definition.record), 0, 0, (branch.level ? 14 : 17) * fontScale(branch.node)).width;
    const maxRows = Math.max(1, ...categories.map(category => category.rows - 1)), rowHeight = Math.max(44, ...nodes.map(node => 30 * fontScale(node))), halfHeight = Math.max(260, (maxRows + 1) * rowHeight);
    const top = frame.y + Math.max(100, ...categories.map(category => 17 * fontScale(category.node) + 76)), spineY = top + halfHeight, slope = .5, indent = 28;
    // Each subtree owns consecutive rows. Above the spine the parent precedes
    // its children; below it the children precede the parent. Nested branches
    // therefore grow towards the spine without crossing a sibling's row band.
    categories.forEach((category, index) => {
        const above = index % 2 === 0, step = halfHeight / Math.max(2, category.rows), first = above ? top : spineY;
        let row = 1;
        const assign = (branch) => {
            if (above)
                branch.row = row++;
            (above ? branch.children : [...branch.children].reverse()).forEach(assign);
            if (!above)
                branch.row = row++;
            branch.y = first + branch.row * step;
        };
        (above ? category.children : [...category.children].reverse()).forEach(assign);
        const measure = (branch) => {
            const childWidth = Math.max(0, ...branch.children.map(measure)), distance = Math.max(0, ...branch.children.map(child => Math.abs(child.y - branch.y)));
            return branch.width = Math.max(textWidth(branch) + 12, branch.children.length ? indent + childWidth + distance * slope + 16 : 0);
        };
        category.children.forEach(measure);
        category.width = Math.max(220, textWidth(category) / 2 + 24, ...category.children.map(child => child.width + 32));
    });
    const columnMargins = Array.from({ length: Math.ceil(categories.length / 2) }, (_, i) => Math.max(44, ...categories.slice(i * 2, i * 2 + 2).map(category => textWidth(category) / 2 + 24 - halfHeight * slope)));
    const columnWidths = columnMargins.map((margin, i) => Math.max(categories[i * 2].width, categories[i * 2 + 1]?.width ?? 0) + halfHeight * slope + margin);
    const effectBounds = { x: frame.x + 40 + columnWidths.reduce((sum, width) => sum + width, 0) + 48, y: spineY - 50, width: 240, height: 100 };
    const effectStyle = glyphStyle(effect, profile), result = [changed(effect, effectBounds, nodeGlyph('quality.effect', effect.definition.record, effectBounds, { title: titleOf(effect.definition.record), profile, ...effectStyle }))];
    const spineStart = [frame.x + 40, spineY], spineEnd = [effectBounds.x, spineY];
    const spineStyle = categories[0]?.edge ?? effect, relationColour = (entry) => str(styled(entry, 'stroke.color', roleDescriptor('quality.cause', 'relation')?.render.colour), '#2563eb');
    const weight = (entry, fallback) => num(styled(entry, 'stroke.weight', styled(entry, 'stroke.width', fallback)), fallback);
    const spinePaint = relationColour(spineStyle);
    const spine = mark(effect, effect.definition, 'spine', finiteBounds(spineStart, spineEnd, 8), [line(spineStart, spineEnd, spinePaint, weight(spineStyle, 2.4)), ...arrowMarker(spineEnd, spineStart, 'filled', spinePaint)], 'Fishbone main spine to the selected effect');
    result.push({ ...spine, item: { ...spine.item, layer: 'relations' } });
    const addLabel = (branch, x, y, category = false) => {
        const size = category ? 17 : 14, align = category ? 'middle' : 'start', bounds = graphLabelBounds(titleOf(branch.node.definition.record), x, y, size * fontScale(branch.node), align);
        result.push(mark(branch.node, branch.node.definition, `cause:${branch.occurrence}`, bounds, [label(titleOf(branch.node.definition.record), x, y, size, '#1e293b', { 'text-anchor': align, ...(category ? { 'font-weight': 700 } : {}) })], `Fishbone level ${branch.level}; source identity retained`));
    };
    const addBone = (branch, points) => {
        const xs = points.map(point => point[0]), ys = points.map(point => point[1]), bounds = { x: Math.min(...xs) - 4, y: Math.min(...ys) - 4, width: Math.max(...xs) - Math.min(...xs) + 8, height: Math.max(...ys) - Math.min(...ys) + 8 };
        const dash = styled(branch.edge, 'stroke.dash', 'solid'), dashPattern = Array.isArray(dash) ? dash.join(' ') : dash === 'dashed' ? '6 4' : dash === 'dotted' ? '2 3' : typeof dash === 'string' && dash !== 'solid' ? dash : undefined;
        const primitives = [path('M' + points.map(point => point.join(',')).join('L'), 'none', relationColour(branch.edge), weight(branch.edge, branch.level === 0 ? 1.8 : 1.2), dashPattern)];
        const caption = relationCaption(branch.edge, edgeLabel(branch.edge, all), viewProperties);
        if (caption) {
            const first = points[0], last = points.at(-1), x = (first[0] + last[0]) / 2, y = (first[1] + last[1]) / 2 + 17;
            const textBounds = graphLabelBounds(caption, x, y, 11, 'middle');
            primitives.push(box(textBounds, str(pathValue(viewProperties, 'background.color'), '#fff'), 'none', 0), label(caption, x, y, 11, '#334155', { 'text-anchor': 'middle' }));
            const right = Math.max(bounds.x + bounds.width, textBounds.x + textBounds.width), bottom = Math.max(bounds.y + bounds.height, textBounds.y + textBounds.height);
            bounds.x = Math.min(bounds.x, textBounds.x);
            bounds.y = Math.min(bounds.y, textBounds.y);
            bounds.width = right - bounds.x;
            bounds.height = bottom - bounds.y;
        }
        result.push(mark(branch.edge, branch.edge.definition, `cause-edge:${branch.occurrence}`, bounds, primitives, 'Fishbone cause relationship; original relation identity'));
    };
    let columnLeft = frame.x + 40;
    categories.forEach((category, index) => {
        if (index && index % 2 === 0)
            columnLeft += columnWidths[index / 2 - 1];
        const above = index % 2 === 0, width = columnWidths[Math.floor(index / 2)], joint = [columnLeft + width - columnMargins[Math.floor(index / 2)], spineY], tip = [joint[0] - halfHeight * slope, above ? top : spineY + halfHeight];
        addLabel(category, tip[0], tip[1] + (above ? -28 : 34), true);
        addBone(category, [tip, joint]);
        const draw = (branch, left, end, span = branch.width) => {
            const start = [left, branch.y], elbow = [left + span, branch.y];
            addLabel(branch, left, branch.y - 8);
            addBone(branch, branch.level === 1 ? [start, end] : [start, elbow, end]);
            const childSpan = Math.max(0, ...branch.children.map(child => child.width));
            for (const child of branch.children) {
                const childLeft = left + indent, attach = [childLeft + childSpan + Math.abs(child.y - branch.y) * slope, branch.y];
                draw(child, childLeft, attach, childSpan);
            }
        };
        for (const branch of category.children) {
            const fraction = (branch.y - tip[1]) / (joint[1] - tip[1]);
            draw(branch, columnLeft, [tip[0] + (joint[0] - tip[0]) * fraction, branch.y]);
        }
    });
    return result.map(entry => ({ ...entry, item: { ...entry.item, primitives: entry.item.primitives.map((primitive, i) => primitive.kind === 'path' && str(pathValue(entry.effective, 'style.look')) === 'handdrawn' ? sketchPrimitive(primitive, num(pathValue(entry.effective, 'style.seed'), 42) + i, num(pathValue(entry.effective, 'style.roughness'), 1)) : primitive) } }));
}
/** Method layouts may place an item in a smaller slot after the common graph
 * pass. Built-in glyphs are redrawn there; standalone artwork already exists,
 * so its paint and routing body must move/scale together without distortion. */
function specializedBounds(entry, slot) {
    if (!entry.standalone)
        return { ...entry, item: { ...entry.item, bounds: slot } };
    const original = entry.item.bounds, matrix = entry.item.transform;
    const scale = Math.min(slot.width / Math.max(1, original.width), slot.height / Math.max(1, original.height));
    const x = slot.x + (slot.width - original.width * scale) / 2, y = slot.y + (slot.height - original.height * scale) / 2;
    const bounds = (b) => ({ x: x + (b.x - original.x) * scale, y: y + (b.y - original.y) * scale, width: b.width * scale, height: b.height * scale });
    return { ...entry, item: { ...entry.item, bounds: bounds(original),
            transform: [matrix[0] * scale, matrix[1] * scale, matrix[2] * scale, matrix[3] * scale, x + (matrix[4] - original.x) * scale, y + (matrix[5] - original.y) * scale],
            ...(entry.item.clip ? { clip: bounds(entry.item.clip) } : {}),
            hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: bounds(hit.bounds) })),
        } };
}
function layoutGraph(nodes, edges, all, profile, frame, view, effective) {
    // Measure compartments before placement: a large class cannot grow through
    // the next rank after the layout has reserved only its title rectangle.
    let positioned = nodes.map(node => decorateNode(node, all, profile));
    const declared = object(effective?.layout ?? view.record.layout), hierarchical = /^(org|wbs|family|fault|event)\./.test(profile);
    let algorithm = str(declared.algorithm, hierarchical ? 'tree' : 'layered');
    if (algorithm === 'auto')
        algorithm = hierarchical ? 'tree' : 'layered';
    const direction = str(declared.direction, hierarchical ? 'down' : 'right');
    const regions = array(view.record.regions).map(object), key = (entry) => refKey(entry.definition.ref);
    const regionMembers = (region) => new Set(array(region.members).map(ref => resolveRecord(all, ref, view.file)).filter((r) => !!r).map(r => refKey(r.ref)));
    const groups = new Map();
    for (const node of positioned) {
        if (node.definition.record.role === 'uml.subject' && positioned.some(child => array(object(metadata(child.definition.record, 'x_usecase')).subjects).some(ref => refKey(resolveRecord(all, ref, child.definition.file)?.ref ?? { file: '', id: '' }) === key(node))))
            continue;
        const subject = array(object(metadata(node.definition.record, 'x_usecase')).subjects)[0], owner = resolveRecord(all, subject, node.definition.file);
        const matching = regions.filter(region => regionMembers(region).has(key(node)) || refKey(resolveRecord(all, region.scope, view.file)?.ref ?? { file: '', id: '' }) === key(node)).sort((a, b) => array(a.members).length - array(b.members).length);
        const group = owner ? 'subject:' + refKey(owner.ref) : str(matching[0]?.id, str(object(metadata(node.definition.record, 'x_partition')).lane, 'outside'));
        const bucket = groups.get(group) ?? [];
        bucket.push(node);
        groups.set(group, bucket);
    }
    const links = edges.flatMap(edge => { const a = endEntry(edge, 0, positioned, all), b = endEntry(edge, 1, positioned, all); return a && b ? [{ from: a.item.occurrence, to: b.item.occurrence }] : []; });
    const root = resolveRecord(all, declared.root, view.file), settings = { algorithm, direction, gap: num(declared.gap, 88), row_gap: num(declared.row_gap, 76), columns: num(declared.columns, 3), width: frame.width, height: frame.height, ...(root ? { root: positioned.find(n => key(n) === refKey(root.ref))?.item.occurrence ?? '' } : {}) };
    let offset = 0;
    const locations = new Map();
    const ancestry = (id, trail = new Set()) => { const region = regions.find(r => r.id === id); if (!region || trail.has(id))
        return '0000/' + id; const next = new Set(trail); next.add(id); const rank = String(regions.indexOf(region) + 1).padStart(4, '0'); return region.parent ? ancestry(str(region.parent), next) + '/' + rank : rank; };
    for (const [, group] of [...groups].sort(([a], [b]) => ancestry(a).localeCompare(ancestry(b)))) {
        const positions = graphLayout(group.map(node => ({ id: node.item.occurrence, bounds: { ...node.item.bounds, x: node.item.bounds.x - frame.x, y: node.item.bounds.y - frame.y }, pinned: typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false })), links, settings);
        let extent = 0;
        for (const node of group) {
            const pos = positions.get(node.item.occurrence);
            const vertical = ['down', 'up'].includes(direction);
            const pin = typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false;
            locations.set(node.item.occurrence, { ...pos, x: frame.x + pos.x + (!pin && vertical ? offset : 0), y: frame.y + pos.y + (!pin && !vertical ? offset : 0) });
            extent = Math.max(extent, vertical ? pos.x + pos.width : pos.y + pos.height);
        }
        offset += extent + 100;
    }
    positioned = positioned.map(node => { const bounds = locations.get(node.item.occurrence) ?? node.item.bounds, m = node.item.transform, dx = bounds.x - node.item.bounds.x, dy = bounds.y - node.item.bounds.y; return { ...node, item: { ...node.item, bounds, transform: [m[0], m[1], m[2], m[3], m[4] + dx, m[5] + dy], hitTargets: node.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, x: hit.bounds.x + dx, y: hit.bounds.y + dy } })) } }; });
    if (profile === 'ladder.basic@1') {
        const incoming = new Set(edges.map(edge => endEntry(edge, 1, positioned, all)).filter(Boolean).map(node => refKey(node.definition.ref))), roots = positioned.filter(node => !incoming.has(refKey(node.definition.ref)));
        const rung = new Map(), level = new Map();
        roots.forEach((root, ri) => {
            const visit = (node, depth, trail) => {
                const key = refKey(node.definition.ref);
                if (trail.has(key) || depth > 64)
                    return;
                const next = new Set(trail);
                next.add(key);
                rung.set(key, ri);
                level.set(key, Math.max(depth, level.get(key) ?? 0));
                for (const edge of edges)
                    if (endEntry(edge, 0, positioned, all) === node) {
                        const to = endEntry(edge, 1, positioned, all);
                        if (to)
                            visit(to, depth + 1, next);
                    }
            };
            visit(root, 0, new Set());
        });
        const counts = new Map();
        positioned = positioned.map(node => { const key = refKey(node.definition.ref), ri = rung.get(key) ?? 0, depth = level.get(key) ?? 0, bucket = ri + ':' + depth, branch = counts.get(bucket) ?? 0; counts.set(bucket, branch + 1); return specializedBounds(node, { ...node.item.bounds, x: frame.x + (node.definition.record.role === 'ladder.coil' ? Math.max(760, frame.width - 150) : 70 + depth * 175), y: frame.y + 100 + ri * 210 + branch * 75 }); });
    }
    if (profile === 'network.rack@1') {
        const racks = positioned.filter(n => n.definition.record.role === 'network.rack');
        positioned = positioned.map(node => {
            if (node.definition.record.role === 'network.rack')
                return node;
            const region = array(node.view.record.regions).map(object).find(region => array(region.members).some(member => refKey(resolveRecord(all, member, node.view.file)?.ref ?? { file: '', id: '' }) === refKey(node.definition.ref))), scope = region && resolveRecord(all, region.scope, node.view.file);
            const rack = racks.find(r => scope && refKey(r.definition.ref) === refKey(scope.ref)) ?? racks.find(r => memberRecords(r, all).some(member => refKey(member.ref) === refKey(node.definition.ref)));
            const unit = num(object(metadata(node.definition.record, 'x_rack')).unit);
            if (!rack || !unit)
                return node;
            const units = num(object(metadata(rack.definition.record, 'x_rack')).units, 42), rb = rack.item.bounds, h = (rb.height - 30) / units;
            return specializedBounds(node, { x: rb.x + 32, y: rb.y + rb.height - h * unit, width: rb.width - 45, height: Math.max(8, h) });
        });
    }
    positioned = positioned.map(node => {
        const event = object(metadata(node.definition.record, 'x_event')), sentry = object(metadata(node.definition.record, 'x_sentry')), attached = resolveRecord(all, event.position === 'boundary' ? event.on : sentry.attach, node.definition.file), owner = attached && positioned.find(entry => refKey(entry.definition.ref) === refKey(attached.ref));
        if (owner) {
            const size = sentry.attach ? 22 : 40, b = owner.item.bounds;
            return specializedBounds(node, { x: b.x + b.width - size * 1.5, y: b.y + b.height - size / 2, width: size, height: size });
        }
        if (node.definition.record.role === 'uml.subject') {
            const contained = positioned.filter(entry => array(object(metadata(entry.definition.record, 'x_usecase')).subjects).some(ref => refKey(resolveRecord(all, ref, entry.definition.file)?.ref ?? { file: '', id: '' }) === refKey(node.definition.ref)));
            if (contained.length) {
                const minX = Math.min(...contained.map(e => e.item.bounds.x)), minY = Math.min(...contained.map(e => e.item.bounds.y)), maxX = Math.max(...contained.map(e => e.item.bounds.x + e.item.bounds.width)), maxY = Math.max(...contained.map(e => e.item.bounds.y + e.item.bounds.height));
                return specializedBounds(node, { x: minX - 25, y: minY - 40, width: maxX - minX + 50, height: maxY - minY + 65 });
            }
        }
        return node;
    });
    return positioned;
}
function cpm(entries, nodes, edges, all, diagnostics, unavailable) {
    const invalid = nodes.filter(node => { const duration = metadata(node.definition.record, 'x_estimate'); return typeof duration !== 'number' || !Number.isFinite(duration) || duration < 0; });
    if (invalid.length) {
        for (const node of invalid)
            diagnostics.push({ code: 'cpm-duration-incomplete', severity: 'warning', target: node.definition.ref, message: 'Critical-path analysis requires a supplied finite, nonnegative day estimate.' });
        unavailable.push('analysis:cpm:durations');
        return [...entries];
    }
    const keys = nodes.map(n => refKey(n.definition.ref)), duration = new Map(nodes.map(n => [refKey(n.definition.ref), num(metadata(n.definition.record, 'x_estimate'))])), parents = new Map(keys.map(k => [k, []])), children = new Map(keys.map(k => [k, []]));
    for (const edge of edges) {
        const a = endEntry(edge, 0, nodes, all), b = endEntry(edge, 1, nodes, all);
        if (a && b) {
            parents.get(refKey(b.definition.ref)).push(refKey(a.definition.ref));
            children.get(refKey(a.definition.ref)).push(refKey(b.definition.ref));
        }
    }
    const order = [], remaining = new Set(keys);
    while (remaining.size) {
        const ready = [...remaining].filter(k => parents.get(k).every(p => !remaining.has(p)));
        if (!ready.length) {
            diagnostics.push({ code: 'cpm-cycle', severity: 'error', message: 'Critical-path analysis is unavailable for cyclic precedence.' });
            unavailable.push('analysis:cpm:cycle');
            return [...entries];
        }
        for (const k of ready) {
            order.push(k);
            remaining.delete(k);
        }
    }
    const es = new Map(), ef = new Map(), ls = new Map(), lf = new Map();
    for (const k of order) {
        es.set(k, Math.max(0, ...parents.get(k).map(p => ef.get(p))));
        ef.set(k, es.get(k) + duration.get(k));
    }
    const finish = Math.max(0, ...ef.values());
    for (const k of [...order].reverse()) {
        lf.set(k, children.get(k).length ? Math.min(...children.get(k).map(p => ls.get(p))) : finish);
        ls.set(k, lf.get(k) - duration.get(k));
    }
    return entries.map(entry => {
        const k = refKey(entry.definition.ref);
        if (!es.has(k)) {
            const a = endEntry(entry, 0, nodes, all), b = endEntry(entry, 1, nodes, all), ak = a && refKey(a.definition.ref), bk = b && refKey(b.definition.ref);
            if (ak && bk && ls.get(ak) === es.get(ak) && ls.get(bk) === es.get(bk) && ef.get(ak) === es.get(bk))
                return changed(entry, entry.item.bounds, entry.item.primitives.map(p => 'paint' in p ? { ...p, paint: { ...p.paint, stroke: '#2563eb', 'stroke-width': 2.5 } } : p), 'Critical precedence edge');
            return entry;
        }
        const b = entry.item.bounds, slack = ls.get(k) - es.get(k);
        return changed(entry, { ...b, height: b.height + 62 }, [...entry.item.primitives, box({ x: b.x, y: b.y + b.height, width: b.width, height: 62 }, '#fff', slack === 0 ? '#2563eb' : '#94a3b8'), label(`Duration ${duration.get(k)} d`, b.x + 6, b.y + b.height + 17, 11), label(`ES ${es.get(k)}  EF ${ef.get(k)}  LS ${ls.get(k)}  LF ${lf.get(k)}`, b.x + 6, b.y + b.height + 36, 11), label(`Slack ${slack} d${slack === 0 ? ' · critical' : ''}`, b.x + 6, b.y + b.height + 53, 11, slack === 0 ? '#2563eb' : '#475569')], 'Deterministic CPM over declared day estimates');
    });
}
function methodCaption(entries, view, text) {
    if (!entries.length)
        return [...entries];
    const left = Math.min(...entries.map(e => e.item.bounds.x)), right = Math.max(...entries.map(e => e.item.bounds.x + e.item.bounds.width)), top = Math.max(...entries.map(e => e.item.bounds.y + e.item.bounds.height)) + 28, width = Math.max(480, right - left), limit = Math.max(35, Math.floor(width / 6.4)), lines = [];
    for (const word of text.split(/\s+/)) {
        const previous = lines.at(-1);
        if (previous && previous.length + word.length + 1 <= limit)
            lines[lines.length - 1] = previous + ' ' + word;
        else
            lines.push(word);
    }
    const bounds = { x: left, y: top, width, height: lines.length * 17 + 8 };
    const caption = mark(entries[0], view, 'method-caption', bounds, lines.map((lineText, i) => label(lineText, left, top + 13 + i * 17, 12, str(pathValue(entries[0].effective, 'text.color'), '#64748b'))), 'Interpretation of the supplied method data');
    return [...entries, { ...caption, item: { ...caption.item, layer: 'annotations' } }];
}
export function projectGraphProfile(snapshot, view, entries, options = {}) {
    const profile = str(view.record.profile), native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
    if (native)
        return projectNativeGraph(snapshot, view, entries, options, projectGraphProfile, id => !!graphCatalogue[id]);
    const contract = graphCatalogue[profile], diagnostics = [], unavailable = [];
    if (!contract)
        return { entries, diagnostics, unavailable };
    const frame = options.bounds ?? { x: 0, y: 0, width: 960, height: 680 }, all = records(snapshot);
    entries = prepareRelationPresentation(entries, all, options.viewProperties ?? view.record);
    const pending = provisionalNodes(entries, all);
    if (pending.length) {
        // Sequence, fishbone, rack and other specialized layouts also wait
        // until a dropped element joins the diagram through a relationship.
        const waiting = new Set(pending);
        const connected = entries.filter(entry => !waiting.has(entry));
        const result = connected.length ? projectGraphProfile(snapshot, view, connected, options) : { entries: [], diagnostics: [], unavailable: [] };
        return { ...result, entries: [...result.entries, ...resolvedText(pending.map(node => decorateNode(node, all, profile)), profile)] };
    }
    if (contract.projection === 'chen')
        return { entries: resolvedText(chen(entries, all, profile, diagnostics, unavailable, view, frame, options.viewProperties), profile), diagnostics, unavailable };
    if (contract.projection === 'sequence')
        return { entries: methodCaption(inlineInteractions(snapshot, view, resolvedText(sequence(entries, all, profile, frame, diagnostics, unavailable, options.viewProperties), profile), all, options, diagnostics, unavailable, projectGraphProfile, id => !!graphCatalogue[id]), view, `Declaration order, not a verified protocol · ${entries.filter(e => e.definition.record.category !== 'relation' && e.definition.record.role !== 'msc.hmscref').length} participants · ${entries.filter(e => e.definition.record.category === 'relation').length} messages · dashed arrows are returns · bars are receiver activations.`), diagnostics, unavailable };
    if (contract.projection === 'timing')
        return { entries: methodCaption(resolvedText(timing(entries, all, profile, frame, diagnostics, unavailable, options.viewProperties), profile), view, `Supplied time points, not a simulation · ${entries.filter(e => e.definition.record.category !== 'relation').length} participants · abstract numeric time axis in the author's unit.`), diagnostics, unavailable };
    if (contract.projection === 'fishbone')
        return { entries: methodCaption(resolvedText(fishbone(entries, all, frame, diagnostics, unavailable, options.viewProperties), profile), view, 'Possible causes, not proven causality · branches are source relationships · repeated appearances retain one identity.'), diagnostics, unavailable };
    const originalNodes = entries.filter(e => e.definition.record.category !== 'relation'), originalEdges = entries.filter(e => e.definition.record.category === 'relation');
    const nodes = layoutGraph(originalNodes, originalEdges, all, profile, frame, view, options.viewProperties).map(node => decorateNode(node, all, profile, true));
    const reservedLabels = [], labelObstacles = [{ x: frame.x, y: frame.y, width: frame.width, height: 45 }, ...nodes.flatMap(node => [...(node.definition.record.role === 'uml.subject' ? [] : [node.item.bounds]), ...node.item.primitives.flatMap(primitive => primitive.kind === 'text' ? primitive.runs.map(run => graphLabelBounds(run.text, run.x, run.y, num(run.style['font-size'], 14) * num(pathValue(node.effective, 'style.font_size'), 16) / 16, str(run.style['text-anchor'], 'start'))) : [])])];
    const priorRoutes = [];
    let output = [...originalEdges.map(edge => decorateEdge(edge, nodes, all, profile, frame, labelObstacles, reservedLabels, priorRoutes, str(pathValue(options.viewProperties ?? view.record, 'layout.crossings'), 'gap'), options.viewProperties)), ...nodes];
    if (profile === 'pert.cpm@1')
        output = cpm(output, nodes, originalEdges, all, diagnostics, unavailable);
    if (profile === 'ladder.basic@1' && nodes.length) {
        const y1 = frame.y + 70, y2 = Math.max(...nodes.map(n => n.item.bounds.y + n.item.bounds.height)) + 40, left = frame.x + 35, right = frame.x + Math.max(900, frame.width - 20);
        const rail = nodes[0];
        output.unshift(mark(rail, view, 'power-rails', { x: left, y: y1, width: right - left, height: y2 - y1 }, [line([left, y1], [left, y2], '#334155', 3), line([right, y1], [right, y2], '#334155', 3)], 'Ladder power rails'));
        for (const node of nodes) {
            const hasParent = originalEdges.some(edge => endEntry(edge, 1, nodes, all) === node);
            if (!hasParent)
                output.push(mark(node, node.definition, 'rail-feed', finiteBounds([left, center(node.item.bounds)[1]], [node.item.bounds.x, center(node.item.bounds)[1]]), [line([left, center(node.item.bounds)[1]], [node.item.bounds.x, center(node.item.bounds)[1]])], 'Ladder rung feed'));
            if (node.definition.record.role === 'ladder.coil')
                output.push(mark(node, node.definition, 'rail-return', finiteBounds([node.item.bounds.x + node.item.bounds.width, center(node.item.bounds)[1]], [right, center(node.item.bounds)[1]]), [line([node.item.bounds.x + node.item.bounds.width, center(node.item.bounds)[1]], [right, center(node.item.bounds)[1]])], 'Ladder rung return'));
        }
    }
    if (profile === 'vsm.basic@1') {
        const processes = nodes.filter(node => node.definition.record.role === 'vsm.process');
        if (processes.length) {
            const y = Math.max(...nodes.map(n => n.item.bounds.y + n.item.bounds.height)) + 50, ps = [];
            let x = frame.x + 30;
            for (const node of processes) {
                const values = object(metadata(node.definition.record, 'x_vsm'));
                ps.push(path(`M${x},${y}H${x + 70}V${y + 25}H${x + 140}V${y}`, 'none'), label(`${num(values.nva)} ${str(values.unit)}`, x + 3, y - 8, 11), label(`${num(values.va)} ${str(values.unit)}`, x + 75, y + 43, 11));
                x += 140;
            }
            ps.push(label('VA / NVA timeline · Σ ' + processes.reduce((sum, node) => { const values = object(metadata(node.definition.record, 'x_vsm')); return sum + num(values.va) + num(values.nva); }, 0), frame.x + 30, y + 70, 12));
            output.push(mark(processes[0], view, 'vsm-timeline', { x: frame.x + 30, y: y - 15, width: x - frame.x, height: 90 }, ps, 'Declared non-value-added and value-added timeline ladder'));
        }
    }
    return { entries: inlineInteractions(snapshot, view, resolvedText(graphAdornments(output, view, all, profile), profile), all, options, diagnostics, unavailable, projectGraphProfile, id => !!graphCatalogue[id]), diagnostics, unavailable };
}
//# sourceMappingURL=graph-profiles.js.map