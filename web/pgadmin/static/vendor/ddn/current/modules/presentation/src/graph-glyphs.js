import { cardTextLayout } from './card-text.js';
import { roleDescriptor } from '../../profiles/src/core.js';
import { array, object, str, num, pathValue } from './model.js';
export const line = (a, b, stroke = '#475569', width = 1.5, dash) => ({ kind: 'path', d: `M${a[0]},${a[1]}L${b[0]},${b[1]}`, paint: { fill: 'none', stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
export const label = (value, x, y, size = 14, color = '#1e293b', extra = {}) => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: 'sans', style: { 'font-size': size, fill: color, ...extra } }] });
export const box = (bounds, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
export const oval = (bounds, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'ellipse', bounds, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
export const path = (d, fill = '#fff', stroke = '#475569', width = 1.5, dash) => ({ kind: 'path', d, paint: { fill, stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) } });
export const polygon = (points, fill = '#fff', stroke = '#475569', width = 1.5) => path('M' + points.map(p => `${p[0]},${p[1]}`).join('L') + 'Z', fill, stroke, width);
export function rounded(b, fill, stroke, radius = 12, width = 1.5, dash) {
    const { x, y, width: w, height: h } = b, r = Math.min(radius, w / 2, h / 2);
    return path(`M${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x + r}Q${x},${y + h} ${x},${y + h - r}V${y + r}Q${x},${y} ${x + r},${y}Z`, fill, stroke, width, dash);
}
export const metadata = (record, key) => object(record.metadata)[key];
const centered = (value, b, size = 15, extra = {}) => {
    const limit = Math.max(8, Math.floor((b.width - 24) / (size * .56))), lines = [];
    for (const word of value.split(/\s+/)) {
        const last = lines.at(-1);
        if (last && last.length + word.length + 1 <= limit)
            lines[lines.length - 1] = last + ' ' + word;
        else
            lines.push(word);
    }
    return { kind: 'text', runs: lines.map((text, i) => ({ text, x: b.x + b.width / 2, y: b.y + b.height / 2 + (i - (lines.length - 1) / 2) * size * 1.2 + size / 3, fontKey: 'sans', style: { 'font-size': size, fill: '#1e293b', 'text-anchor': 'middle', 'font-weight': 600, ...extra } })) };
};
export const coreCardCode = (role) => ({ application: 'APP', service: 'SRV', object: 'OBJ', record: 'REC', entity: 'ENT', table: 'TBL', term: 'TERM' }[role] ?? str(roleDescriptor(role)?.render.text_label, role).toUpperCase());
export function coreCardText(role, title, width, scale = 1) {
    const layout = cardTextLayout(coreCardCode(role), title, width, (text, size) => text.length * size * .6, 9 * scale, 15 * scale, 10);
    return { ...layout, height: Math.max(40 + layout.typeLines.length * 11 * scale + 8, layout.titleLines.length * 18 * scale + 20) };
}
/** Small deterministic contour variation preserves the same semantic symbol. */
export function sketchPrimitive(primitive, seed = 42, roughness = 1) {
    let state = seed >>> 0;
    const jitter = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return (state / 4294967296 - .5) * Math.max(0, Math.min(4, roughness)) * 2; };
    let source = primitive;
    if (source.kind === 'rect') {
        const b = source.bounds;
        source = { kind: 'path', d: `M${b.x},${b.y}H${b.x + b.width}V${b.y + b.height}H${b.x}Z`, paint: source.paint };
    }
    if (source.kind === 'ellipse') {
        const b = source.bounds, cx = b.x + b.width / 2, cy = b.y + b.height / 2, rx = b.width / 2, ry = b.height / 2, k = .5522847498;
        source = { kind: 'path', d: `M${cx + rx},${cy}C${cx + rx},${cy + ry * k} ${cx + rx * k},${cy + ry} ${cx},${cy + ry}C${cx - rx * k},${cy + ry} ${cx - rx},${cy + ry * k} ${cx - rx},${cy}C${cx - rx},${cy - ry * k} ${cx - rx * k},${cy - ry} ${cx},${cy - ry}C${cx + rx * k},${cy - ry} ${cx + rx},${cy - ry * k} ${cx + rx},${cy}Z`, paint: source.paint };
    }
    if (source.kind !== 'path')
        return source;
    let command = '', index = 0;
    const d = source.d.replace(/[a-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/gi, token => { if (/^[a-df-z]$/i.test(token)) {
        command = token.toUpperCase();
        index = 0;
        return token;
    } const i = index++, value = Number(token); return String(Number((value + (command === 'A' && i % 7 < 5 ? 0 : jitter())).toFixed(3))); });
    return { ...source, d, paint: { ...source.paint, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' } };
}
export function shadowPrimitive(primitive, dx = 5, dy = 5) {
    if (primitive.kind === 'rect' || primitive.kind === 'ellipse')
        return { ...primitive, bounds: { ...primitive.bounds, x: primitive.bounds.x + dx, y: primitive.bounds.y + dy }, paint: { fill: '#cbd5e1', stroke: 'none' } };
    if (primitive.kind !== 'path' || primitive.paint.fill === 'none')
        return;
    let command = '', index = 0;
    const d = primitive.d.replace(/[a-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:e[-+]?\d+)?/gi, token => { if (/^[a-df-z]$/i.test(token)) {
        command = token.toUpperCase();
        index = 0;
        return token;
    } const i = index++; return String(Number(token) + (command === 'A' ? (i % 7 === 5 ? dx : i % 7 === 6 ? dy : 0) : command === 'H' ? dx : command === 'V' ? dy : i % 2 ? dy : dx)); });
    return { ...primitive, d, paint: { fill: '#cbd5e1', stroke: 'none' } };
}
/** Profile shapes are ordinary retained SVG primitives, never embedded markup. */
export function nodeGlyph(role, record, b, options) {
    const { x, y, width: w, height: h } = b, cx = x + w / 2, cy = y + h / 2;
    const fill = options.fill ?? '#fff', stroke = options.stroke ?? '#475569', width = options.width ?? 1.5;
    const ps = [], m = (key) => object(metadata(record, key)), render = roleDescriptor(role)?.render, silhouette = str(render?.silhouette), coreCard = !role.includes('.') && !role.includes('::') && !(options.profile.startsWith('chen.') || options.profile === 'chebotko.conceptual@1');
    const diamond = () => polygon([[cx, y], [x + w, cy], [cx, y + h], [x, cy]], fill, stroke, width);
    const hexagon = () => polygon([[x + 20, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x + 20, y + h], [x, cy]], fill, stroke, width);
    const document = () => path(`M${x},${y}H${x + w}V${y + h - 10}C${x + w * .66},${y + h - 26} ${x + w * .4},${y + h + 10} ${x},${y + h - 8}Z`, fill, stroke, width);
    const cylinder = () => { ps.push(path(`M${x},${y + 12}C${x},${y - 4} ${x + w},${y - 4} ${x + w},${y + 12}V${y + h - 12}C${x + w},${y + h + 4} ${x},${y + h + 4} ${x},${y + h - 12}Z`, fill, stroke, width), oval({ x, y, width: w, height: 24 }, fill, stroke, width)); };
    let title = true;
    if (role === 'uml.actor' || role === 'vsm.operator' || role === 'c4.person' || silhouette === 'actor') {
        const r = Math.min(16, h / 6), yy = y + r + 5;
        ps.push(oval({ x: cx - r, y: yy - r, width: 2 * r, height: 2 * r }, fill, stroke, width), line([cx, yy + r], [cx, y + h * .65], stroke), line([cx - 24, Math.max(yy + r + 5, y + h * .4)], [cx + 24, Math.max(yy + r + 5, y + h * .4)], stroke), line([cx, y + h * .65], [cx - 24, y + h * .8], stroke), line([cx, y + h * .65], [cx + 24, y + h * .8], stroke), label(options.title, cx, y + h - 3, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if ((role === 'flow.start' || role === 'flow.end') && !options.profile.startsWith('bpmn') && !options.profile.startsWith('uml.activity'))
        ps.push(rounded(b, fill, stroke, h / 2));
    else if (/^(state|flow)\.(initial|junction)$/.test(role) || role === 'state.initial') {
        ps.push(oval(b, stroke, stroke));
        title = false;
    }
    else if (role === 'state.final' || role === 'flow.end' && !options.profile.startsWith('bpmn')) {
        ps.push(oval(b, fill, stroke, 2), oval({ x: x + w * .2, y: y + h * .2, width: w * .6, height: h * .6 }, stroke, stroke));
        title = false;
    }
    else if (role === 'state.terminate' || role === 'flow.flowfinal') {
        if (role === 'flow.flowfinal')
            ps.push(oval(b, fill, stroke));
        ps.push(line([x + 5, y + 5], [x + w - 5, y + h - 5], stroke, 2), line([x + w - 5, y + 5], [x + 5, y + h - 5], stroke, 2));
        title = false;
    }
    else if (role === 'state.history_deep' || role === 'state.history_shallow') {
        ps.push(oval(b, fill, stroke), centered(role === 'state.history_deep' ? 'H*' : 'H', b));
        title = false;
    }
    else if (role === 'state.entrypoint' || role === 'state.exitpoint') {
        ps.push(oval(b, fill, stroke));
        if (role === 'state.exitpoint')
            ps.push(line([x + 4, y + 4], [x + w - 4, y + h - 4], stroke), line([x + w - 4, y + 4], [x + 4, y + h - 4], stroke));
        title = false;
    }
    else if (role === 'state.forkjoin' || role === 'flow.forkjoin' || role === 'petri.transition' || role === 'flow.parallelmode') {
        ps.push(box({ x, y: cy - 5, width: w, height: 10 }, stroke, stroke));
        title = false;
    }
    else if (role === 'petri.place') {
        ps.push(oval(b, fill, stroke));
        const count = num(m('x_petri').tokens);
        if (count <= 6) {
            for (let i = 0; i < count; i++)
                ps.push(oval({ x: cx - 3 + (count === 1 ? 0 : Math.cos(i / count * Math.PI * 2) * 13), y: cy - 3 + (count === 1 ? 0 : Math.sin(i / count * Math.PI * 2) * 13), width: 6, height: 6 }, stroke, stroke));
        }
        else
            ps.push(centered(String(count), b));
        ps.push(label(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'flow.start' || role === 'flow.intermediate' || role === 'flow.end' || role.startsWith('cmmn.') && role.endsWith('event')) {
        const event = m('x_event'), dashed = event.interrupting === false ? '5 3' : undefined;
        ps.push(oval(b, fill, stroke, role === 'flow.end' ? 3 : 1.5, dashed));
        if (role === 'flow.intermediate' || event.position === 'intermediate' || event.position === 'boundary')
            ps.push(oval({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, 1.2, dashed));
        const type = str(event.type, role === 'cmmn.timerevent' ? 'timer' : role === 'cmmn.userevent' ? 'user' : 'none');
        const ib = { x: cx - w * .23, y: cy - h * .23, width: w * .46, height: h * .46 };
        if (type === 'message')
            ps.push(box(ib, 'none', stroke), path(`M${ib.x},${ib.y}L${cx},${cy}L${ib.x + ib.width},${ib.y}`, 'none', stroke));
        else if (type === 'timer') {
            ps.push(oval(ib, 'none', stroke), line([cx, cy], [cx, ib.y + 3], stroke), line([cx, cy], [ib.x + ib.width - 3, cy], stroke));
            for (let i = 0; i < 12; i++) {
                const a = i * Math.PI / 6;
                ps.push(line([cx + Math.sin(a) * w * .19, cy + Math.cos(a) * h * .19], [cx + Math.sin(a) * w * .22, cy + Math.cos(a) * h * .22], stroke, 1));
            }
        }
        else if (type === 'signal')
            ps.push(polygon([[cx, ib.y], [ib.x + ib.width, ib.y + ib.height], [ib.x, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'terminate')
            ps.push(oval(ib, stroke, stroke));
        else if (type === 'error')
            ps.push(polygon([[ib.x + ib.width * .55, ib.y], [ib.x, ib.y + ib.height * .6], [ib.x + ib.width * .45, ib.y + ib.height * .45], [ib.x + ib.width * .2, ib.y + ib.height], [ib.x + ib.width, ib.y + ib.height * .3], [ib.x + ib.width * .6, ib.y + ib.height * .45]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'escalation')
            ps.push(polygon([[cx, ib.y], [ib.x + ib.width, ib.y + ib.height], [cx, ib.y + ib.height * .6], [ib.x, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'compensation') {
            ps.push(polygon([[ib.x, cy], [cx, ib.y], [cx, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke), polygon([[cx, cy], [ib.x + ib.width, ib.y], [ib.x + ib.width, ib.y + ib.height]], role === 'flow.end' ? stroke : fill, stroke));
        }
        else if (type === 'conditional') {
            ps.push(box(ib, 'none', stroke));
            for (let i = 1; i < 4; i++)
                ps.push(line([ib.x + 3, ib.y + i * ib.height / 4], [ib.x + ib.width - 3, ib.y + i * ib.height / 4], stroke));
        }
        else if (type === 'link')
            ps.push(polygon([[ib.x, cy - 3], [cx, cy - 3], [cx, ib.y], [ib.x + ib.width, cy], [cx, ib.y + ib.height], [cx, cy + 3], [ib.x, cy + 3]], role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'cancel')
            ps.push(line([ib.x, ib.y], [ib.x + ib.width, ib.y + ib.height], stroke, 3), line([ib.x + ib.width, ib.y], [ib.x, ib.y + ib.height], stroke, 3));
        else if (type === 'multiple')
            ps.push(polygon(Array.from({ length: 5 }, (_, i) => [cx + Math.sin(i * Math.PI * .4) * ib.width / 2, cy - Math.cos(i * Math.PI * .4) * ib.height / 2]), role === 'flow.end' ? stroke : fill, stroke));
        else if (type === 'parallel_multiple')
            ps.push(line([ib.x, cy], [ib.x + ib.width, cy], stroke, 3), line([cx, ib.y], [cx, ib.y + ib.height], stroke, 3));
        else if (type === 'user')
            ps.push(oval({ x: cx - 5, y: cy - 9, width: 10, height: 10 }, 'none', stroke), path(`M${cx - 9},${cy + 10}Q${cx},${cy - 3} ${cx + 9},${cy + 10}`, 'none', stroke));
        ps.push(label(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (['flow.decision', 'flow.merge', 'flow.gateway', 'state.choice', 'cmmn.sentry', 'chen.association'].includes(role)) {
        ps.push(diamond());
        const gateway = m('x_gateway');
        const mark = { exclusive: '×', parallel: '+', inclusive: '○', complex: '*', event: '◎', event_exclusive: '◎' }[str(gateway.type)];
        if (mark) {
            const radius = Math.min(w, h) * .2, type = str(gateway.type);
            if (type === 'exclusive')
                ps.push(line([cx - radius, cy - radius], [cx + radius, cy + radius], stroke, 3), line([cx + radius, cy - radius], [cx - radius, cy + radius], stroke, 3));
            else if (type === 'parallel')
                ps.push(line([cx - radius, cy], [cx + radius, cy], stroke, 3), line([cx, cy - radius], [cx, cy + radius], stroke, 3));
            else if (type === 'inclusive')
                ps.push(oval({ x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, 'none', stroke, 2.5));
            else if (type === 'complex') {
                for (let i = 0; i < 4; i++)
                    ps.push(line([cx - Math.cos(i * Math.PI / 4) * radius, cy - Math.sin(i * Math.PI / 4) * radius], [cx + Math.cos(i * Math.PI / 4) * radius, cy + Math.sin(i * Math.PI / 4) * radius], stroke, 2));
            }
            else {
                ps.push(oval({ x: cx - radius, y: cy - radius, width: radius * 2, height: radius * 2 }, 'none', stroke), oval({ x: cx - radius + 3, y: cy - radius + 3, width: radius * 2 - 6, height: radius * 2 - 6 }, 'none', stroke), polygon(Array.from({ length: 5 }, (_, i) => [cx + Math.sin(i * Math.PI * .4) * radius * .55, cy - Math.cos(i * Math.PI * .4) * radius * .55]), 'none', stroke));
            }
            title = false;
            ps.push(label(options.title, cx, y + h + 17, 13, stroke, { 'text-anchor': 'middle' }));
        }
    }
    else if (role === 'uml.usecase' || role === 'orm.entitytype' || role === 'orm.valuetype' || role === 'uml.collaboration' || role === 'soaml.servicecontract')
        ps.push(oval(b, fill, stroke, width, ['orm.valuetype', 'uml.collaboration', 'soaml.servicecontract'].includes(role) ? '6 4' : undefined));
    else if (role === 'dfd.process' && options.profile === 'dfd.yourdon@1')
        ps.push(oval(b, fill, stroke, width));
    else if (role === 'dfd.process') {
        ps.push(rounded(b, fill, stroke));
        ps.push(line([x, y + 22], [x + w, y + 22], stroke), line([x, y + h - 22], [x + w, y + h - 22], stroke));
        const diagram = m('x_diagram');
        ps.push(label(String(diagram.number ?? diagram.id ?? diagram.code ?? ''), x + 8, y + 17, 11, stroke));
        if (diagram.responsibility || diagram.owner)
            ps.push(label(str(diagram.responsibility, str(diagram.owner)), x + 8, y + h - 7, 11, stroke));
    }
    else if (role === 'dfd.store') {
        ps.push(line([x, y], [x + w, y], stroke), line([x, y + h], [x + w, y + h], stroke));
        if (options.profile === 'dfd.gane_sarson@1')
            ps.push(line([x, y], [x, y + h], stroke), line([x + 36, y], [x + 36, y + h], stroke));
        const diagram = m('x_diagram');
        if (diagram.code || diagram.id || diagram.number)
            ps.push(label(String(diagram.code ?? diagram.id ?? diagram.number), x + 6, cy + 4, 11, stroke));
    }
    else if (['flow.document', 'epk.infoobject', 'dmn.knowledgesource'].includes(role) || silhouette === 'document')
        ps.push(document());
    else if (['flow.storage', 'flow.datastore', 'c4.store'].includes(role) || silhouette === 'cylinder')
        cylinder();
    else if (['flow.io', 'sdl.input', 'sdl.output', 'flow.sendsignal', 'flow.acceptsignal', 'flow.manualinput', 'sdl.signal'].includes(role)) {
        const input = role === 'sdl.input' || role === 'flow.acceptsignal';
        ps.push(role === 'flow.manualinput' ? polygon([[x, y + 16], [x + w, y], [x + w, y + h], [x, y + h]], fill, stroke) : input ? polygon([[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x + 20, cy]], fill, stroke) : role === 'sdl.output' || role === 'flow.sendsignal' || role === 'sdl.signal' ? polygon([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h]], fill, stroke) : polygon([[x + 20, y], [x + w, y], [x + w - 20, y + h], [x, y + h]], fill, stroke));
    }
    else if (role === 'flow.subprocess' || role === 'sdl.procedure') {
        ps.push(rounded(b, fill, stroke), line([x + 12, y], [x + 12, y + h], stroke), line([x + w - 12, y], [x + w - 12, y + h], stroke));
    }
    else if (role === 'sdl.save')
        ps.push(polygon([[x + 20, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x + 20, y + h], [x, cy]], fill, stroke));
    else if (role === 'sdl.create')
        ps.push(polygon([[x + 15, y], [x + w - 15, y], [x + w, y + 15], [x + w, y + h - 15], [x + w - 15, y + h], [x + 15, y + h], [x, y + h - 15], [x, y + 15]], fill, stroke));
    else if (role === 'sdl.set' || role === 'sdl.reset' || role === 'sdl.timer') {
        ps.push(box(b, fill, stroke));
        ps.push(oval({ x: x + 8, y: y + 8, width: 22, height: 22 }, 'none', stroke), line([x + 19, y + 19], [x + 19, y + 10], stroke), line([x + 19, y + 19], [x + 26, y + 19], stroke));
        if (role === 'sdl.reset')
            ps.push(line([x + 9, y + 9], [x + 29, y + 29], stroke));
    }
    else if (['flow.conversation', 'flow.callconversation', 'flow.subconversation', 'epk.event', 'flow.preparation'].includes(role)) {
        ps.push(hexagon());
        if (role === 'flow.callconversation')
            ps.push(polygon([[x + 24, y + 4], [x + w - 24, y + 4], [x + w - 5, cy], [x + w - 24, y + h - 4], [x + 24, y + h - 4], [x + 5, cy]], 'none', stroke));
    }
    else if (role === 'epk.connector') {
        ps.push(oval(b, fill, stroke), centered(str(m('x_epc').type, str(m('x_epc').operator, 'and')).toUpperCase(), b));
        title = false;
    }
    else if (role === 'flow.connector' || role === 'family.union') {
        ps.push(oval(b, fill, stroke));
    }
    else if (role === 'flow.offpage')
        ps.push(polygon([[x, y], [x + w, y], [x + w, y + h * .65], [cx, y + h], [x, y + h * .65]], fill, stroke));
    else if (role === 'flow.manualop')
        ps.push(polygon([[x, y], [x + w, y], [x + w - 20, y + h], [x + 20, y + h]], fill, stroke));
    else if (role === 'flow.delay')
        ps.push(path(`M${x},${y}H${x + w / 2}C${x + w * 1.16},${y} ${x + w * 1.16},${y + h} ${x + w / 2},${y + h}H${x}Z`, fill, stroke));
    else if (role === 'flow.display')
        ps.push(path(`M${x + 20},${y}H${x + w - 20}Q${x + w + 20},${cy} ${x + w - 20},${y + h}H${x + 20}L${x},${cy}Z`, fill, stroke));
    else if (role === 'flow.card' || role === 'dmn.bkm')
        ps.push(polygon([[x + 18, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y + 18]], fill, stroke));
    else if (role === 'flow.sort') {
        ps.push(diamond(), line([x, cy], [x + w, cy], stroke));
    }
    else if (role === 'flow.collate' || role === 'flow.timeevent') {
        ps.push(polygon([[x, y], [x + w, y], [x, y + h], [x + w, y + h]], fill, stroke));
    }
    else if (role === 'flow.isoextract' || role === 'flow.isomerge')
        ps.push(role === 'flow.isoextract' ? polygon([[cx, y], [x + w, y + h], [x, y + h]], fill, stroke) : polygon([[x, y], [x + w, y], [cx, y + h]], fill, stroke));
    else if (role === 'flow.loopstart' || role === 'flow.loopend')
        ps.push(role === 'flow.loopstart' ? polygon([[x + 16, y], [x + w - 16, y], [x + w, y + 16], [x + w, y + h], [x, y + h], [x, y + 16]], fill, stroke) : polygon([[x, y], [x + w, y], [x + w, y + h - 16], [x + w - 16, y + h], [x + 16, y + h], [x, y + h - 16]], fill, stroke));
    else if (role === 'uml.package') {
        ps.push(box({ x, y: y + 14, width: w, height: h - 14 }, fill, stroke), box({ x, y, width: Math.min(90, w * .4), height: 14 }, fill, stroke));
    }
    else if (['uml.node', 'uml.device', 'uml.executionenv'].includes(role)) {
        ps.push(box({ x, y: y + 12, width: w - 12, height: h - 12 }, fill, stroke), polygon([[x, y + 12], [x + 12, y], [x + w, y], [x + w - 12, y + 12]], fill, stroke), polygon([[x + w - 12, y + 12], [x + w, y], [x + w, y + h - 12], [x + w - 12, y + h]], fill, stroke));
    }
    else if (['uml.artifact', 'flow.dataobject', 'flow.datainput', 'flow.dataoutput', 'cmmn.casefile'].includes(role)) {
        ps.push(polygon([[x, y], [x + w - 16, y], [x + w, y + 16], [x + w, y + h], [x, y + h]], fill, stroke), path(`M${x + w - 16},${y}V${y + 16}H${x + w}`, 'none', stroke));
        if (role === 'flow.datainput' || role === 'flow.dataoutput')
            ps.push(label(role === 'flow.datainput' ? '⇢' : '➜', x + 8, y + 22, 18, stroke));
    }
    else if (role === 'ladder.contact') {
        ps.push(line([x, cy], [cx - 12, cy], stroke), line([cx - 12, y + 5], [cx - 12, y + h - 5], stroke, 2), line([cx + 12, y + 5], [cx + 12, y + h - 5], stroke, 2), line([cx + 12, cy], [x + w, cy], stroke));
        if (m('x_contact').form === 'nc')
            ps.push(line([cx - 18, y + h - 4], [cx + 18, y + 4], stroke));
        ps.push(label(options.title, cx, y - 5, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'ladder.coil') {
        ps.push(line([x, cy], [cx - 15, cy], stroke), path(`M${cx - 6},${y + 5}Q${cx - 28},${cy} ${cx - 6},${y + h - 5}M${cx + 6},${y + 5}Q${cx + 28},${cy} ${cx + 6},${y + h - 5}`, 'none', stroke), line([cx + 15, cy], [x + w, cy], stroke));
        const form = str(m('x_coil').mode);
        if (form === 'set' || form === 'reset')
            ps.push(centered(form === 'set' ? 'S' : 'R', b));
        if (form === 'negated')
            ps.push(line([cx - 18, y + h], [cx + 18, y], stroke));
        ps.push(label(options.title, cx, y - 5, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'network.bus') {
        ps.push(line([x, cy], [x + w, cy], stroke, 6));
        ps.push(label(options.title, cx, cy - 12, 13, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'network.rack' && options.profile === 'network.rack@1') {
        ps.push(box(b, '#f8fafc', stroke, 2));
        const units = Math.min(100, num(m('x_rack').units, 42));
        for (let i = 1; i <= units; i++)
            ps.push(line([x + 25, y + h - i * (h - 30) / units], [x + w - 10, y + h - i * (h - 30) / units], '#cbd5e1', .5), label(String(i), x + 4, y + h - (i - .5) * (h - 30) / units, 9, stroke));
        ps.push(label(options.title, x + 10, y + 20, 14, stroke));
        title = false;
    }
    else if (role === 'tree.event')
        ps.push(oval(b, fill, stroke, width));
    else if (role === 'tree.gate') {
        const type = str(m('x_gate').type, 'and');
        ps.push(type === 'and' ? path(`M${x},${y + h}V${y + h * .45}C${x},${y - h * .15} ${x + w},${y - h * .15} ${x + w},${y + h * .45}V${y + h}Z`, fill, stroke) : path(`M${x},${y + h}Q${cx},${y + h * .65} ${x + w},${y + h}Q${x + w},${y + h * .25} ${cx},${y}Q${x},${y + h * .25} ${x},${y + h}Z`, fill, stroke));
        ps.push(label(type.toUpperCase(), cx, cy + 6, 12, stroke, { 'text-anchor': 'middle' }));
        title = false;
    }
    else if (role === 'vsm.inventory') {
        ps.push(polygon([[cx, y], [x + w, y + h], [x, y + h]], fill, stroke));
    }
    else if (role === 'vsm.kaizen') {
        const points = [];
        for (let i = 0; i < 24; i++) {
            const a = i * Math.PI / 12, r = i % 2 ? .65 : 1;
            points.push([cx + Math.cos(a) * w / 2 * r, cy + Math.sin(a) * h / 2 * r]);
        }
        ps.push(polygon(points, fill, stroke));
    }
    else if (role === 'vsm.supermarket') {
        ps.push(path(`M${x},${y}V${y + h}H${x + w}V${y}M${x},${cy}H${x + w}`, 'none', stroke));
    }
    else if (role === 'orm.facttype') {
        const count = Math.max(2, array(record.members).length || array(m('x_role').roles).length);
        ps.push(box(b, fill, stroke, width));
        const cellWidth = Math.min(80, (w - 24) / count), left = x + 12, top = y + h - 30;
        for (let i = 0; i < count; i++)
            ps.push(box({ x: left + i * cellWidth, y: top, width: cellWidth, height: 24 }, fill, stroke));
        if (m('x_role').unique)
            ps.push(line([left, top - 4], [left + cellWidth * count, top - 4], stroke, 2));
    }
    else if (role === 'ui.checkbox') {
        ps.push(box({ x, y: cy - 10, width: 20, height: 20 }, '#fff', '#64748b'));
        if (m('x_ui').checked)
            ps.push(path(`M${x + 3},${cy}L${x + 8},${cy + 6}L${x + 17},${cy - 6}`, 'none', '#334155', 2));
        ps.push(label(options.title, x + 28, cy + 5));
        title = false;
    }
    else if (role === 'uml.subject') {
        ps.push(box(b, 'none', stroke), label(options.title, x + 8, y + 20, 14, stroke));
        title = false;
    }
    else if (role === 'ui.label') {
        ps.push(label(options.title, x + 4, cy + 5));
        title = false;
    }
    else if (role === 'ui.image') {
        ps.push(box(b, '#f1f5f9', '#64748b'), line([x, y], [x + w, y + h], '#94a3b8'), line([x + w, y], [x, y + h], '#94a3b8'));
    }
    else if (role === 'flow.annotation') {
        ps.push(path(`M${x + 16},${y}H${x}V${y + h}H${x + 16}`, 'none', stroke));
    }
    else if (role === 'flow.group')
        ps.push(rounded(b, 'none', stroke, 8, 1.5, '8 3 2 3'));
    else if (role.startsWith('cmmn.')) {
        const mC = m('x_cmmn');
        ps.push(rounded(b, fill, stroke, role === 'cmmn.milestone' ? h / 2 : 4, width, mC.discretionary ? '6 4' : undefined));
    }
    else if (role === 'dmn.inputdata' || role === 'flow.process' || role === 'state.state' || role === 'epk.function' || role === 'ui.button')
        ps.push(rounded(b, fill, stroke, role === 'dmn.inputdata' ? h / 2 : 10, m('x_activity').call ? 3 : width, m('x_activity').event_subprocess ? '5 3' : undefined));
    else if (silhouette === 'round')
        ps.push(rounded(b, fill, stroke, 12, width));
    else if (silhouette === 'ellipse' || silhouette === 'circle')
        ps.push(oval(b, fill, stroke, width));
    else if (silhouette === 'diamond')
        ps.push(diamond());
    else if (silhouette === 'tag')
        ps.push(polygon([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h]], fill, stroke, width));
    else if (silhouette === 'arrow')
        ps.push(polygon([[x, y], [x + w - 20, y], [x + w, cy], [x + w - 20, y + h], [x, y + h], [x + 20, cy]], fill, stroke, width));
    else if (coreCard && render?.shape === 'card')
        ps.push(rounded(b, fill, stroke, 5, width));
    else
        ps.push(box(b, fill, stroke, width));
    if (role === 'uml.component' || silhouette === 'component')
        ps.push(box({ x: x - 6, y: y + 12, width: 16, height: 12 }, fill, stroke), box({ x: x - 6, y: y + 34, width: 16, height: 12 }, fill, stroke));
    if (role === 'dmn.decisionservice')
        ps.push(line([x, y + 25], [x + w, y + 25], stroke));
    if (m('x_io').set)
        for (let i = -1; i <= 1; i++)
            ps.push(line([cx + i * 5, y + h - 15], [cx + i * 5, y + h - 5], stroke, 2));
    if (role === 'cmmn.humantask' || role === 'cmmn.processtask' || role === 'cmmn.decisiontask')
        ps.push(label(role === 'cmmn.humantask' ? '♙' : role === 'cmmn.processtask' ? '⊞' : '▤', x + 7, y + 20, 15, stroke));
    if (role === 'cmmn.sentry' && m('x_sentry').on === 'exit')
        ps.push(polygon([[cx, y + 6], [x + w - 6, cy], [cx, y + h - 6], [x + 6, cy]], stroke, stroke));
    if (role === 'idef0.activity')
        ps.push(label(str(m('x_idef0').node), x + w - 8, y + h - 7, 11, stroke, { 'text-anchor': 'end' }));
    if (role === 'epk.processlink')
        ps.push(polygon([[x + 4, y + 4], [x + 24, y + 4], [x + 34, y + 14], [x + 24, y + 24], [x + 4, y + 24], [x - 6, y + 14]], fill, stroke));
    if (role === 'ui.list')
        for (let i = 0; i < 3; i++)
            ps.push(line([x + 12, y + 10 + i * 20], [x + w - 12, y + 10 + i * 20], '#cbd5e1', 1));
    if (role === 'network.server' || role === 'network.switch')
        for (let i = 0; i < 3; i++)
            ps.push(line([x + 10, y + h - 12 - i * 8], [x + 44, y + h - 12 - i * 8], stroke), oval({ x: x + w - 16, y: y + h - 16 - i * 8, width: 4, height: 4 }, '#16a34a', '#16a34a'));
    if (!title && /^(state\.|flow\.(forkjoin|parallelmode|flowfinal)|petri\.transition|tree\.gate|epk\.connector)/.test(role) && options.title)
        ps.push(label(options.title, cx, y + h + 18, 13, stroke, { 'text-anchor': 'middle' }));
    if (coreCard) {
        const ib = { x: x + 10, y: y + 10, width: 19, height: 19 }, layout = coreCardText(role, options.title, w, options.textScale);
        const scale = options.textScale ?? 1;
        if (render?.shape === 'frame')
            ps.push(box({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, .7, '3 3'));
        ps.push(box(ib, 'none', stroke, 1.2));
        if (role === 'application')
            ps.push(line([ib.x, ib.y + 5], [ib.x + 19, ib.y + 5], stroke, 1), path(`M${ib.x + 3},${ib.y + 9}L${ib.x + 7},${ib.y + 12}L${ib.x + 3},${ib.y + 15}M${ib.x + 10},${ib.y + 15}H${ib.x + 16}`, 'none', stroke, 1));
        else if (['service', 'server'].includes(role))
            for (let i = 0; i < 3; i++)
                ps.push(line([ib.x, ib.y + 5 + i * 6], [ib.x + 19, ib.y + 5 + i * 6], stroke, .8));
        else if (['table', 'record', 'entity'].includes(role))
            ps.push(line([ib.x, ib.y + 6], [ib.x + 19, ib.y + 6], stroke, 1), line([ib.x + 6, ib.y], [ib.x + 6, ib.y + 19], stroke, 1));
        for (const [i, code] of layout.typeLines.entries())
            ps.push(label(code, x + 10, y + 38 + 9 * scale + i * 11 * scale, 9, stroke, { 'font-weight': 600 }));
    }
    if (title && coreCard) {
        const scale = options.textScale ?? 1, layout = coreCardText(role, options.title, w, scale);
        for (const [i, value] of layout.titleLines.entries())
            ps.push(label(value, x + layout.titleOffset + layout.titleWidth / 2, y + h / 2 + (i - (layout.titleLines.length - 1) / 2) * 18 * scale + 5 * scale, 15, '#1e293b', { 'text-anchor': 'middle', 'font-weight': 600 }));
    }
    else if (title)
        ps.push(centered(options.title, role === 'dfd.store' ? { ...b, x: x + 40, width: w - 44 } : b, 15, options.profile.startsWith('uml.object') ? { 'text-decoration': 'underline' } : {}));
    const activity = m('x_activity');
    if (activity.transaction)
        ps.push(rounded({ x: x + 5, y: y + 5, width: w - 10, height: h - 10 }, 'none', stroke, 8));
    const marks = [...array(activity.markers).map(v => ({ loop: '↻', parallel: '|||', sequential: '≡', compensation: '≪' }[str(v)] ?? str(v))), ...(activity.adhoc ? ['~'] : []), ...(activity.collapsed || role === 'flow.subconversation' ? ['⊞'] : [])];
    const cmmn = m('x_cmmn');
    for (const [key, mark] of Object.entries({ required: '!', repetition: '#', manual_activation: '▷', completion: '■', collapsed: '+' }))
        if (cmmn[key])
            marks.push(mark);
    if (marks.length)
        ps.push(label(marks.join(' '), cx, y + h - 5, 13, stroke, { 'text-anchor': 'middle' }));
    if (role === 'flow.choreotask') {
        const bands = array(metadata(record, 'x_bands')).map(String);
        bands.forEach((band, i) => { const yy = i === 0 ? y : y + h - (bands.length - i) * 18; ps.push(box({ x, y: yy, width: w, height: 18 }, i === 0 ? '#e2e8f0' : '#fff', stroke), label(band, cx, yy + 13, 11, stroke, { 'text-anchor': 'middle' })); });
    }
    if (role === 'fbd.block' || role === 'ladder.timer') {
        const type = str(m('x_fbd').type, str(m('x_timer').type, str(pathValue(record, 'content.type'), str(m('x_record').block_type))));
        if (type)
            ps.push(label(type, x + 8, y + 18, 11, stroke));
    }
    const sdl = m('x_sdl'), sdlMarks = [sdl.priority ? 'priority ' + str(sdl.priority) : '', sdl.spontaneous ? 'spontaneous' : '', sdl.continuous ? 'continuous ' + str(sdl.continuous) : '', sdl.duration ? 'after ' + str(sdl.duration) : ''].filter(Boolean);
    if (sdlMarks.length)
        ps.push(label(sdlMarks.join('; '), cx, y + h + 16, 10, stroke, { 'text-anchor': 'middle' }));
    const planning = array(m('x_planning').items);
    if (planning.length) {
        ps.push(box({ x: cx - 18, y: y - 12, width: 36, height: 20 }, '#fff', stroke), line([cx - 18, y - 2], [cx + 18, y - 2], stroke), line([cx, y - 12], [cx, y + 8], stroke));
        ps.push(label('Planning: ' + planning.map(String).join(', '), x + 8, y + h + 16, 10, stroke));
    }
    if (options.look === 'handdrawn' && ps[0])
        ps[0] = sketchPrimitive(ps[0], options.seed, options.roughness);
    return ps;
}
export function arrowMarker(point, toward, kind = 'open', stroke = '#475569') {
    if (kind === 'none' || !kind)
        return [];
    const [x, y] = point, theta = Math.atan2(y - toward[1], x - toward[0]), ux = Math.cos(theta), uy = Math.sin(theta), px = -uy, py = ux;
    const at = (back, side) => [x - ux * back + px * side, y - uy * back + py * side];
    if (['one', 'zeroone', 'many', 'zeromany'].includes(kind)) {
        const ps = [];
        if (kind.includes('many'))
            ps.push(line(at(15, 0), at(0, 8), stroke), line(at(15, 0), at(0, -8), stroke), line(at(15, 0), point, stroke));
        else
            ps.push(line(at(7, -8), at(7, 8), stroke));
        if (kind === 'one')
            ps.push(line(at(13, -8), at(13, 8), stroke));
        if (kind === 'many')
            ps.push(line(at(24, -8), at(24, 8), stroke));
        if (kind.startsWith('zero')) {
            const p = at(24, 0);
            ps.push(oval({ x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, '#fff', stroke));
        }
        return ps;
    }
    if (kind === 'port')
        return [polygon([at(0, -5), at(0, 5), at(10, 5), at(10, -5)], '#fff', stroke)];
    if (kind === 'junction')
        return [oval({ x: x - 4, y: y - 4, width: 8, height: 8 }, stroke, stroke)];
    if (kind === 'range')
        return [line(at(4, -7), at(4, 7), stroke), line(at(16, -7), at(16, 7), stroke), line(at(4, 0), at(16, 0), stroke)];
    if (kind === 'lollipop')
        return [oval({ x: x - 8, y: y - 8, width: 16, height: 16 }, '#fff', stroke)];
    if (kind === 'socket')
        return [path(`M${at(0, -10).join(',')}Q${at(18, 0).join(',')} ${at(0, 10).join(',')}`, 'none', stroke)];
    if (kind === 'xcircle')
        return [oval({ x: x - 8, y: y - 8, width: 16, height: 16 }, '#fff', stroke), line([x - 5, y - 5], [x + 5, y + 5], stroke), line([x - 5, y + 5], [x + 5, y - 5], stroke)];
    if (kind === 'circle' || kind === 'filled-circle') {
        const p = at(5, 0);
        return [oval({ x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, kind === 'circle' ? '#fff' : stroke, stroke)];
    }
    if (kind === 'diamond' || kind === 'filled-diamond')
        return [polygon([point, at(10, 6), at(20, 0), at(10, -6)], kind === 'diamond' ? '#fff' : stroke, stroke)];
    if (kind === 'triangle' || kind === 'filled' || kind === 'filled-triangle')
        return [polygon([point, at(13, 7), at(13, -7)], kind === 'triangle' ? '#fff' : stroke, stroke)];
    return [line(at(12, 6), point, stroke), line(point, at(12, -6), stroke)];
}
//# sourceMappingURL=graph-glyphs.js.map