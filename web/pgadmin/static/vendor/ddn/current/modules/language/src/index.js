import { asArray, asRecord, asString, findRecord, getPath, isRecord, listRecords, normalizeLocation, recordRef, resolveReference, safePath, setPath } from '../../model/src/index.js';
import { coreTypes, profiles, roleTypes, shapes } from './schema.js';
const aliases = { look: 'style.look', font: 'style.font', 'font-size': 'style.font_size', status: 'design.state', paper: 'style.paper' };
const recipeProfiles = { erd: 'ddn@1', mindmap: 'mindmap.basic@1', bar: 'chart.basic@1' };
const rootKeys = { definition: 'definitions', view: 'views', placement: 'placements', appearance: 'appearances', data: 'data', source: 'sources', asset: 'assets', template: 'templates', publication: 'publications' };
const prohibited = new Set(['__proto__', 'constructor', 'prototype']);
function array(record, key) {
    if (!Array.isArray(record[key]))
        record[key] = [];
    return record[key];
}
function words(text) {
    const out = [];
    let start = -1;
    let quote = '';
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (start < 0) {
            if (/\s/.test(c))
                continue;
            start = i;
        }
        if (quote) {
            if (c === quote) {
                if (text[i + 1] === quote)
                    i++;
                else
                    quote = '';
            }
            continue;
        }
        if ((c === '"' || c === "'") && (i === start || /[\s.:]/.test(text[i - 1]))) {
            quote = c;
            continue;
        }
        if (/\s/.test(c)) {
            out.push({ raw: text.slice(start, i), start, end: i });
            start = -1;
        }
    }
    if (quote)
        throw Error('Unterminated quoted value');
    if (start >= 0)
        out.push({ raw: text.slice(start), start, end: text.length });
    return out;
}
export function splitDelimited(text, delimiter) {
    if (!delimiter)
        throw Error('A delimiter must not be empty');
    const result = [];
    let quote = '';
    let start = 0;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quote) {
            if (c === quote) {
                if (text[i + 1] === quote)
                    i++;
                else
                    quote = '';
            }
            continue;
        }
        if ((c === '"' || c === "'") && (i === 0 || /[\s.:]/.test(text[i - 1]))) {
            quote = c;
            continue;
        }
        if (text.startsWith(delimiter, i)) {
            result.push(text.slice(start, i));
            i += delimiter.length - 1;
            start = i + 1;
        }
    }
    if (quote)
        throw Error('Unterminated quoted value');
    result.push(text.slice(start));
    return result;
}
export function decodeText(raw) {
    if (raw.includes('\n'))
        throw Error('A quoted or scalar value cannot cross a physical line');
    const text = raw.trim();
    const q = text[0];
    if (q !== '"' && q !== "'")
        return text;
    let result = '';
    for (let i = 1; i < text.length; i++) {
        if (text[i] === q) {
            if (text[i + 1] === q) {
                result += q;
                i++;
            }
            else {
                if (text.slice(i + 1).trim())
                    throw Error('Unexpected text after quoted value');
                return result;
            }
        }
        else
            result += text[i];
    }
    throw Error('Unterminated quoted value');
}
export function quoteText(text) {
    if (/[\r\n]/.test(text))
        throw Error('A quoted value cannot contain a line break; use an admitted literal text body');
    return '"' + text.replaceAll('"', '""') + '"';
}
function titleParts(text, columnHeader = false) {
    let quote = '';
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quote) {
            if (c === quote) {
                if (text[i + 1] === quote)
                    i++;
                else
                    quote = '';
            }
            continue;
        }
        if ((c === '"' || c === "'") && (i === 0 || /[\s.:]/.test(text[i - 1]))) {
            quote = c;
            continue;
        }
        if (c === ':' && text[i - 1] !== ':' && text[i + 1] !== ':' && (!columnHeader || /\s/.test(text[i - 1] || '')))
            return { head: text.slice(0, i).trimEnd(), title: decodeText(text.slice(i + 1)), at: i };
    }
    if (quote)
        throw Error('Unterminated quoted value');
    return { head: text.trimEnd() };
}
function lines(text) {
    const result = [];
    let pos = 0;
    while (pos < text.length) {
        const nl = text.indexOf('\n', pos), end = nl < 0 ? text.length : nl + 1;
        let raw = text.slice(pos, nl < 0 ? end : nl);
        let eol = nl < 0 ? '' : '\n';
        if (raw.endsWith('\r') && nl >= 0) {
            raw = raw.slice(0, -1);
            eol = '\r\n';
        }
        const bom = pos === 0 && raw.startsWith('\ufeff') ? 1 : 0;
        const prefix = /^[ \t]*/.exec(raw.slice(bom))[0];
        result.push({ start: pos, end, contentStart: pos + prefix.length + bom, indent: prefix.length, text: raw.slice(prefix.length + bom), eol });
        pos = end;
    }
    return result;
}
function unfold(shape, seen = new Set()) {
    if (!shape?.$ref)
        return shape;
    const name = shape.$ref.split('/').at(-1);
    if (seen.has(name))
        return shape;
    seen.add(name);
    return unfold(shapes[name], seen);
}
function variants(shape) { const s = unfold(shape); return s ? (s.type || s.properties) ? [s] : s.anyOf || s.oneOf ? (s.anyOf || s.oneOf).flatMap(x => variants(x)) : [s] : []; }
function childShape(shape, key) {
    for (const s of variants(shape)) {
        if (s.properties?.[key])
            return s.properties[key];
        if (typeof s.additionalProperties === 'object')
            return s.additionalProperties;
        if (s.additionalProperties === true)
            return shapes.json_value;
    }
    return undefined;
}
function ownerShape(owner, record, path) {
    let shape = shapes[owner];
    if (owner === 'view_definition' && path === 'projection') {
        const projection = childShape(shape, 'projection');
        return { ...unfold(projection), properties: { ...unfold(projection)?.properties, options: shapes['profile_' + asString(record.profile)] ?? {} } };
    }
    if (owner === 'view_definition' && (path === 'projection.options' || path.startsWith('projection.options.'))) {
        let value = shapes['profile_' + asString(record.profile)];
        for (const key of safePath(path).slice(2))
            value = childShape(value, key);
        return value;
    }
    if (owner === 'declaration_map')
        return shapes.declaration_map?.properties?.[path];
    if (owner === 'definition') {
        const role = asString(record.role);
        const info = coreTypes[role] || roleTypes[(record.category === 'relation' ? 'relation::' : '') + role];
        if (info && ['content', 'metadata', 'properties', 'qualifiers'].includes(path.split('.')[0])) {
            if (role.startsWith('core::'))
                shape = { properties: { [record.category === 'relation' ? 'qualifiers' : 'content']: shapes[info.schema], ...(role === 'core::Port' ? { metadata: shapes.port_metadata, properties: shapes.port_properties } : {}) } };
            else
                shape = shapes[info.schema];
        }
    }
    for (const segment of safePath(path))
        shape = childShape(shape, segment);
    return shape;
}
function isReferenceShape(shape) { return variants(shape).some(v => v.properties?.name && v.properties?.file && v.properties?.id); }
function typedValue(raw, shape, file) {
    const text = decodeText(raw), quoted = /^["']/.test(raw.trim());
    const vs = variants(shape);
    const types = vs.flatMap(v => typeof v.type === 'string' ? [v.type] : v.type || []);
    // Nullable reference settings use bare null as the reset value. A quoted
    // "null" remains an ordinary name and can reference an asset named null.
    if (!quoted && text === 'null' && types.includes('null'))
        return null;
    const reference = isReferenceShape(shape) && !(quoted && types.includes('string'));
    if (reference) {
        const bits = splitDelimited(raw, '::');
        return bits.length > 1 ? { file: normalizeLocation(decodeText(bits.slice(0, -1).join('::')), file), name: decodeText(bits.at(-1)) } : { file, name: text };
    }
    if (!quoted && text === 'null')
        return null;
    if (!quoted && text === 'empty list' && types.includes('array'))
        return [];
    if (!quoted && text === 'empty record' && types.includes('object'))
        return {};
    // Quoting is an explicit type discriminator when the declared value admits
    // text alongside numeric/boolean values (including open JSON metadata).
    // Numeric-only properties still accept quoted numeric input.
    if (quoted && types.includes('string'))
        return text;
    if (types.includes('number') || types.includes('integer')) {
        const n = /^[+-]?(?:\d+(?:\.\d+)?)(?:e[+-]?\d+)?$/i.test(text) ? Number(text) : NaN;
        if (Number.isFinite(n) && (!types.includes('integer') || Number.isInteger(n)))
            return n;
        if (shape?.$ref?.endsWith('/base_font_size') || shape?.$ref?.endsWith('/font_size')) {
            const m = /^([\d.]+)(px|pt)$/.exec(text);
            if (m)
                return Number(m[1]) * (m[2] === 'pt' ? 4 / 3 : 1);
        }
        if (!types.includes('string'))
            throw Error('Expected a finite ' + (types.includes('integer') ? 'integer' : 'number'));
    }
    if (types.includes('boolean')) {
        if (text === 'true')
            return true;
        if (text === 'false')
            return false;
        if (!types.includes('string'))
            throw Error('Expected true or false');
    }
    if (vs.some(v => v.properties?.value && v.properties?.unit)) {
        const m = /^([+-]?[\d.]+)(px|pt|mm|cm|in)$/.exec(text);
        if (m && Number.isFinite(Number(m[1])))
            return { value: Number(m[1]), unit: m[2] };
    }
    if (types.length && !types.includes('string') && !types.includes('number') && !types.includes('integer') && !types.includes('boolean'))
        throw Error('Expected an indented record or collection');
    return text;
}
export function parseTableHeader(text) {
    const used = new Set();
    return splitDelimited(text, '.').map(raw => {
        const bits = splitDelimited(raw, ':');
        if (bits.length > 5)
            throw Error('A column has at most alignment, percentage, minimum characters and maximum lines');
        const id = decodeText(bits[0]).normalize('NFC');
        if (!id || used.has(id) || prohibited.has(id))
            throw Error('Column names must be nonempty and unique');
        used.add(id);
        const c = { id };
        if (bits[1]?.trim()) {
            const alignment = decodeText(bits[1]);
            if (!/^[rlcf][tmb]$/.test(alignment))
                throw Error('Invalid column alignment');
            c.alignment = alignment;
        }
        for (const [i, key] of [[2, 'percentage'], [3, 'min_chars'], [4, 'max_lines']])
            if (bits[i]?.trim()) {
                const value = Number(decodeText(bits[i]));
                if (!Number.isFinite(value) || (i !== 2 && (!Number.isInteger(value) || value < 1)) || (i === 2 && (value < 0 || value > 100)))
                    throw Error('Invalid column ' + key);
                c[key] = value;
            }
        return c;
    });
}
export function parseTableRow(text, columns) {
    const cells = splitDelimited(text, '.');
    if (cells.length > columns.length)
        throw Error('More cells than declared columns');
    return columns.map((column, i) => {
        const cell = cells[i];
        if (cell === undefined || !cell.trim())
            return null;
        return typedValue(cell, shapes[asString(column.type, 'text')], '');
    });
}
function resolveSourceReference(bundle, site, scoped = []) {
    const file = asString(site.reference.file, site.file), name = asString(site.reference.name), id = asString(site.reference.id);
    const local = scoped.filter(r => r.file === file && (id ? r.ref.id === id && (!name || r.record.name === name) : r.record.name === name));
    if (local.length)
        return local.length === 1 ? local[0] : undefined;
    const declared = resolveReference(bundle, site.file, site.reference);
    if (declared || id || !name)
        return declared;
    const globals = listRecords(bundle).filter(r => r.file === file);
    // A name always wins, even when duplicate declarations make that name invalid.
    if ([...scoped, ...globals].some(r => r.file === file && r.record.name === name))
        return undefined;
    const localId = scoped.filter(r => r.file === file && r.ref.id === name), candidates = localId.length ? localId : globals.filter(r => r.ref.id === name);
    if (candidates.length !== 1)
        return undefined;
    site.reference.id = candidates[0].ref.id;
    delete site.reference.name;
    site.spelling = 'id';
    return candidates[0];
}
class Decoder {
    diagnostics = [];
    documents = [];
    references = [];
    allocations = [];
    fieldBindings = [];
    cellSources = new WeakMap();
    bundle;
    sourceMap = new Map();
    parsed = new Set();
    current;
    ls = [];
    doc;
    syntax;
    serial = 0;
    usedIds = new Set();
    reservedIds = new Set();
    names = new Map();
    options;
    templateScope;
    constructor(input, options) {
        this.options = options;
        let entry = input.entry;
        try {
            entry = normalizeLocation(entry);
        }
        catch { }
        this.bundle = { version: 'ddn-next-1', entry, files: [] };
        for (const f of input.files) {
            let id = f.id;
            try {
                id = normalizeLocation(id);
            }
            catch {
                this.diagnostics.push({ code: 'source.location', severity: 'error', message: 'Invalid source file location: ' + f.id });
            }
            if (this.sourceMap.has(id))
                this.diagnostics.push({ code: 'source.duplicate', severity: 'error', message: 'Duplicate selected source: ' + id });
            else
                this.sourceMap.set(id, { ...f, id });
        }
    }
    diagnostic(code, message, line, target, severity = 'error') { this.diagnostics.push({ code, message, severity, ...(this.current && line ? { source: { file: this.current.id, revision: this.current.revision, start: line.contentStart, end: line.end } } : {}), ...(target ? { target } : {}) }); }
    structuralLine(line, literal = false) {
        if (this.current.text.slice(line.start, line.contentStart).includes('\t'))
            this.diagnostic('syntax.tab', 'Tabs are not allowed in structural indentation', line);
        if (!literal && line.text.includes('\r'))
            this.diagnostic('syntax.cr', 'A lone carriage return is invalid outside literal content', line);
    }
    scalarChildren(index, end) {
        const child = this.ls.slice(index + 1, end).find(line => line.text.trim() && !line.text.trimStart().startsWith('//'));
        if (child)
            this.diagnostic('syntax.child', 'A supplied scalar value cannot own an indented block', child);
    }
    blockEnd(index, end = this.ls.length) {
        const indent = this.ls[index].indent;
        let i = index + 1;
        for (; i < end; i++) {
            const l = this.ls[i];
            if (l.text.trim() && l.indent <= indent)
                break;
        }
        return i;
    }
    node(line, end, kind) { return { file: this.current.id, kind, start: line.start, end: end < this.ls.length ? this.ls[end].start : this.current.text.length, headerEnd: line.end, bodyStart: line.end, indent: line.indent, raw: this.current.text.slice(line.start, end < this.ls.length ? this.ls[end].start : undefined), children: [] }; }
    reserveAuthoredIds(start, end) {
        for (let i = start; i < end;) {
            const line = this.ls[i];
            if (!line.text.trim() || line.text.trimStart().startsWith('//')) {
                i++;
                continue;
            }
            const stop = this.blockEnd(i, end);
            // This scan reserves spellings only. The ordinary parser owns all
            // syntax/type diagnostics and declaration facts.
            try {
                const keyword = words(line.text)[0]?.raw;
                if (keyword === 'with') {
                    for (let child = i + 1; child < stop;) {
                        const property = this.ls[child];
                        if (!property.text.trim() || property.text.trimStart().startsWith('//')) {
                            child++;
                            continue;
                        }
                        const tokens = words(property.text);
                        if (tokens[0]?.raw === 'id' && tokens[1])
                            this.reservedIds.add(decodeText(property.text.slice(tokens[1].start)));
                        child = this.blockEnd(child, stop);
                    }
                }
                else if (!['notes', 'draft', 'fields', 'defaults', 'version', 'include', 'style'].includes(keyword ?? '')) {
                    // Compact data rows are literals; named typed datasets own
                    // an ordinary with block instead.
                    const first = this.ls.slice(i + 1, stop).find(child => child.text.trim() && !child.text.trimStart().startsWith('//'));
                    if (keyword !== 'data' || first?.text.trim() === 'with')
                        this.reserveAuthoredIds(i + 1, stop);
                }
            }
            catch { /* Malformed source is diagnosed by the ordinary parser. */ }
            i = stop;
        }
    }
    id(node, name) {
        const previous = this.options.previous?.documents.find(d => d.file.id === this.current.id);
        const flatten = (nodes) => nodes.flatMap(n => [n, ...flatten(n.children)]);
        const previousNodes = previous ? flatten(previous.nodes) : [];
        const previousIds = new Set(previousNodes.map(x => x.ref?.id));
        const candidates = previousNodes.filter(x => x.kind === node.kind && x.ref && !this.usedIds.has(x.ref.id));
        const exact = (node.identityKey ? candidates.find(x => x.identityKey === node.identityKey) : undefined) || candidates.find(x => x.raw === node.raw) || (name ? candidates.find(x => findRecord(this.options.previous?.normalized, x.ref)?.name === name) : undefined) || candidates.find(x => x.start === node.start && !this.current.text.includes(x.raw));
        let value = exact?.ref?.id || 'ddn-' + node.kind.replace(/[^a-z0-9]/g, '') + '-' + (++this.serial);
        while (this.usedIds.has(value) || (!exact && (previousIds.has(value) || this.reservedIds.has(value))))
            value = 'ddn-' + node.kind + '-' + (++this.serial);
        this.usedIds.add(value);
        return value;
    }
    add(kind, record, node, name) {
        name = name?.normalize('NFC');
        record.id = this.id(node, name);
        if (name) {
            record.name = name.normalize('NFC');
            if (this.names.has(record.name))
                this.diagnostic('name.duplicate', 'Duplicate declared name: ' + record.name, this.ls.find(l => l.start === node.start));
            else
                this.names.set(record.name, recordRef(this.current.id, record));
        }
        node.ref = recordRef(this.current.id, record);
        this.allocations.push({ record, node, file: this.current.id, initial: node.ref.id });
        array(this.doc, rootKeys[kind]).push(record);
        return record;
    }
    reference(raw, start, kind = 'reference') {
        const parts = splitDelimited(raw, '::');
        if (parts.length > 2)
            throw Error('A file reference has one :: separator');
        const name = decodeText(parts.at(-1)).normalize('NFC');
        if (!name)
            throw Error('Reference name must not be empty');
        const ref = { file: parts.length === 2 ? normalizeLocation(decodeText(parts[0]), this.current.id) : this.current.id, name };
        this.references.push({ file: this.current.id, start, end: start + raw.length, reference: ref, kind, ...(this.templateScope ? { scope: this.templateScope } : {}) });
        return ref;
    }
    value(raw, shape, start) {
        const alternatives = variants(shape);
        const nullableNull = raw.trim() === 'null' && alternatives.some(s => s.type === 'null' || Array.isArray(s.type) && s.type.includes('null'));
        const literal = /^["']/.test(raw.trim()) && splitDelimited(raw, '::').length === 1 && alternatives.some(s => s.type === 'string' || Array.isArray(s.type) && s.type.includes('string'));
        return isReferenceShape(shape) && !literal && !nullableNull ? this.reference(raw, start) : typedValue(raw, shape, this.current.id);
    }
    selection(view, target) {
        if (!isRecord(view.selection))
            view.selection = {};
        array(view.selection, 'include').push(target);
    }
    appearance(target, view, node, name, title) {
        const a = { target, parent: { file: this.current.id, id: asString(view.id) } };
        const own = { ...node, kind: node.kind === 'use' ? 'use' : 'appearance', children: [], implicit: true, identityKey: 'appearance:' + asString(view.id) + ':' + asString(target.file, this.current.id) + ':' + asString(target.id, asString(target.name)) };
        this.add('appearance', a, own, name);
        node.children.push(own);
        if (title !== undefined)
            a.title = title;
        return a;
    }
    rawBody(start, end) {
        const body = this.ls.slice(start, end);
        if (!body.length)
            return '';
        const raw = body.map(line => this.current.text.slice(line.start, line.end - line.eol.length));
        const first = raw.find(line => line.trim());
        // Only spaces establish the literal container's indentation. A following
        // tab is authored content, including on the first literal line.
        const indent = first === undefined ? Math.min(...raw.map(line => /^ */.exec(line)[0].length)) : /^ */.exec(first)[0].length;
        return raw.map(line => line.slice(Math.min(indent, /^ */.exec(line)[0].length))).join('\n');
    }
    sequence(start, end, parent, ctx, nodes) {
        let indent;
        for (let i = start; i < end;) {
            const line = this.ls[i];
            if (!line.text.trim() || line.text.trimStart().startsWith('//')) {
                i++;
                continue;
            }
            if (line.indent <= parent) {
                this.diagnostic('syntax.indent', 'Unexpected dedent', line);
                i++;
                continue;
            }
            if (indent === undefined)
                indent = line.indent;
            if (line.indent !== indent) {
                this.diagnostic('syntax.indent', 'Sibling declarations must use the same indentation', line);
                i++;
                continue;
            }
            this.structuralLine(line);
            if (ctx.kind === 'file' && line.indent !== 0)
                this.diagnostic('syntax.indent', 'File-level declarations must begin without indentation', line);
            const stop = this.blockEnd(i, end), node = this.node(line, stop, 'unknown');
            nodes.push(node);
            try {
                this.statement(i, stop, ctx, node);
            }
            catch (error) {
                this.diagnostic('syntax.statement', error instanceof Error ? error.message : String(error), line, node.ref);
            }
            i = stop;
        }
    }
    readProperties(start, end, parent, record, owner, node, prefix = '', flatten = false, appearance) {
        const supplied = new Set();
        let indent;
        for (let i = start; i < end;) {
            const line = this.ls[i];
            if (!line.text.trim() || line.text.trimStart().startsWith('//')) {
                i++;
                continue;
            }
            this.structuralLine(line);
            if (indent === undefined)
                indent = line.indent;
            if (line.indent <= parent || line.indent !== indent) {
                this.diagnostic('syntax.indent', 'Invalid property indentation', line);
                i++;
                continue;
            }
            const stop = this.blockEnd(i, end);
            const w = words(line.text);
            const key = w[0].raw;
            if (prohibited.has(key))
                throw Error('Unsafe property name');
            let path = prefix + (aliases[key] || key);
            // A silhouette word is the short spelling of shadow.kind. Keep
            // structured shadow blocks and shadow null as the same canonical
            // shadow property, so CSS and file declarations merge normally.
            if (!prefix && key === 'shadow' && w.length === 2 && ['none', 'offset', 'centre', 'corners', 'corner'].includes(decodeText(w[1].raw)))
                path = 'shadow.kind';
            if (owner === 'definition' && record.category === 'relation' && /^(source|target)\./.test(path))
                path = 'qualifiers.' + path;
            safePath(path);
            const appearancePath = appearance && (['position', 'size', 'body', 'columns', 'pinned'].includes(path.split('.')[0]) || record.category === 'relation' && ['label', 'legend'].includes(path.split('.')[0]));
            const propertyRecord = appearancePath ? appearance : record, propertyOwner = appearancePath ? 'appearance' : owner;
            const n = this.node(line, stop, 'property');
            if (appearancePath)
                n.owner = recordRef(this.current.id, appearance);
            else if (node.ref || node.owner)
                n.owner = (node.ref || node.owner);
            n.path = path;
            n.valueStart = line.contentStart + (w[1]?.start ?? line.text.length);
            n.valueEnd = line.end - line.eol.length;
            node.children.push(n);
            const raw = line.text.slice(w[1]?.start ?? line.text.length);
            let shape = ownerShape(propertyOwner, propertyRecord, path);
            if (owner === 'template_record' && !['id', 'name', 'role', 'settings', 'parameters', 'defaults', 'fragment', 'version', 'method', 'profile', 'view'].includes(path.split('.')[0]))
                shape = ownerShape('definition', { role: record.role }, path);
            if (!shape) {
                this.diagnostic('property.unknown', 'Unknown or inapplicable property: ' + path, line, node.ref);
                i = stop;
                continue;
            }
            try {
                const destination = owner === 'template_record' && !['id', 'name', 'role', 'settings', 'parameters', 'defaults', 'fragment', 'version', 'method', 'profile', 'view'].includes(path.split('.')[0]) ? (record.settings ??= {}) : propertyRecord;
                const exists = supplied.has(path);
                supplied.add(path);
                if (exists)
                    this.diagnostic('property.duplicate', 'Repeated supplied property: ' + path, line, node.ref);
                let value;
                if (raw) {
                    this.scalarChildren(i, stop);
                    const valueWords = words(raw);
                    if (valueWords[0]?.raw === 'parameter' && owner === 'template_record')
                        value = { parameter: decodeText(raw.slice(valueWords[1]?.start ?? raw.length)) };
                    else
                        value = owner === 'data_record' && path === 'key' ? [decodeText(raw)] : this.value(raw, shape, n.valueStart);
                }
                else {
                    const variants_ = variants(shape);
                    const arrayShape = this.chooseArray(variants_, i + 1, stop);
                    const objectShape = variants_.find(s => s.type === 'object' || s.properties);
                    const contentLines = this.ls.slice(i + 1, stop).filter(x => x.text.trim() && !x.text.trimStart().startsWith('//'));
                    if (arrayShape && (!objectShape || !contentLines.length || /^item(?:\s|$)/.test(contentLines[0].text))) {
                        value = this.readList(i + 1, stop, line.indent, arrayShape.items, n);
                    }
                    else if (objectShape) {
                        value = {};
                        this.readStructured(i + 1, stop, line.indent, value, shape, n);
                    }
                    else if (this.ls.slice(i + 1, stop).some(line => line.text.trim()) && variants_.some(s => s.type === 'string' || Array.isArray(s.type) && s.type.includes('string'))) {
                        value = this.rawBody(i + 1, stop);
                    }
                    else {
                        array(record, 'incomplete').push({ path, raw: '', reason: 'A supplied scalar has no value' });
                        this.diagnostic('property.incomplete', 'Property needs a value: ' + path, line, node.ref, 'warning');
                        i = stop;
                        continue;
                    }
                }
                if (flatten || destination === record.settings)
                    destination[path] = value;
                else
                    setPath(destination, path, value);
            }
            catch (error) {
                this.diagnostic('property.value', error instanceof Error ? error.message : String(error), line, node.ref);
            }
            i = stop;
        }
    }
    readStructured(start, end, parent, record, shape, node) {
        let indent;
        for (let i = start; i < end;) {
            const l = this.ls[i];
            if (!l.text.trim() || l.text.trimStart().startsWith('//')) {
                i++;
                continue;
            }
            this.structuralLine(l);
            if (indent === undefined)
                indent = l.indent;
            if (l.indent !== indent || l.indent <= parent) {
                this.diagnostic('syntax.indent', 'Invalid record indentation', l);
                i++;
                continue;
            }
            const stop = this.blockEnd(i, end), w = words(l.text), key = decodeText(w[0].raw);
            if (prohibited.has(key))
                throw Error('Unsafe property name');
            const child = childShape(shape, key);
            if (!child) {
                this.diagnostic('property.unknown', 'Unknown record property: ' + key, l);
                i = stop;
                continue;
            }
            const n = this.node(l, stop, 'property');
            if (node.owner)
                n.owner = node.owner;
            if (node.path)
                n.path = node.path + '.' + key;
            n.valueStart = l.contentStart + (w[1]?.start ?? l.text.length);
            n.valueEnd = l.end - l.eol.length;
            node.children.push(n);
            const raw = l.text.slice(w[1]?.start ?? l.text.length);
            let value;
            if (raw) {
                this.scalarChildren(i, stop);
                value = this.value(raw, child, n.valueStart);
            }
            else {
                const vs = variants(child), a = this.chooseArray(vs, i + 1, stop), o = vs.find(v => v.type === 'object' || v.properties);
                if (a && (!o || this.ls.slice(i + 1, stop).find(l => l.text.trim())?.text.match(/^item(?:\s|$)/)))
                    value = this.readList(i + 1, stop, l.indent, a.items, n);
                else if (o) {
                    value = {};
                    this.readStructured(i + 1, stop, l.indent, value, child, n);
                }
                else
                    value = this.rawBody(i + 1, stop);
            }
            if (Object.hasOwn(record, key))
                this.diagnostic('property.duplicate', 'Repeated record property: ' + key, l);
            record[key] = value;
            i = stop;
        }
        if (isReferenceShape(shape) && (typeof record.name === 'string' || typeof record.id === 'string')) {
            if (typeof record.file === 'string')
                record.file = normalizeLocation(record.file, this.current.id);
            else
                record.file = this.current.id;
            const key = typeof record.name === 'string' ? 'name' : 'id';
            const property = node.children.find(n => n.path?.split('.').at(-1) === key);
            if (property?.valueStart !== undefined && property.valueEnd !== undefined)
                this.references.push({ file: this.current.id, start: property.valueStart, end: property.valueEnd, reference: record, kind: 'reference', spelling: key, ...(this.templateScope ? { scope: this.templateScope } : {}) });
        }
    }
    /** Distinguish record lists such as matrix references from table columns. */
    chooseArray(choices, start, end) {
        const arrays = choices.filter(shape => shape.type === 'array');
        if (arrays.length < 2)
            return arrays[0];
        const first = this.ls.slice(start, end).find(line => line.text.trim() && !line.text.trimStart().startsWith('//'));
        if (!first)
            return arrays[0];
        const index = this.ls.indexOf(first), stop = this.blockEnd(index, end);
        const body = this.ls.slice(index + 1, stop).filter(line => line.text.trim() && !line.text.trimStart().startsWith('//'));
        const indent = body[0]?.indent;
        const keys = body.filter(line => line.indent === indent).map(line => decodeText(words(line.text)[0].raw));
        if (!keys.length) {
            const raw = words(first.text).slice(1).map(word => word.raw).join(' ');
            if (raw) {
                // A quoted scalar chooses the literal-list branch when a contract
                // admits both names and references (for example decision outputs).
                if (/^["']/.test(raw) && splitDelimited(raw, '::').length === 1) {
                    const literal = arrays.find(shape => variants(shape.items).some(item => item.type === 'string' || Array.isArray(item.type) && item.type.includes('string')));
                    if (literal)
                        return literal;
                }
                return arrays.find(shape => isReferenceShape(shape.items)) ?? arrays[0];
            }
            return arrays[0];
        }
        const score = (shape) => keys.reduce((total, key) => total + (childShape(shape.items, key) ? 1 : -100), 0);
        return arrays.reduce((best, shape) => score(shape) > score(best) ? shape : best);
    }
    readList(start, end, parent, shape, node) {
        const result = [], sites = [];
        let indent;
        for (let i = start; i < end;) {
            const l = this.ls[i];
            if (!l.text.trim() || l.text.trimStart().startsWith('//')) {
                i++;
                continue;
            }
            this.structuralLine(l);
            if (indent === undefined)
                indent = l.indent;
            const stop = this.blockEnd(i, end), w = words(l.text);
            if (l.indent !== indent || l.indent <= parent || w[0]?.raw !== 'item') {
                this.diagnostic('property.list', 'A collection entry must begin with item at a consistent indentation', l);
                i = stop;
                continue;
            }
            const n = this.node(l, stop, 'item');
            if (node.owner)
                n.owner = node.owner;
            if (node.path)
                n.path = node.path + '.' + result.length;
            n.valueStart = l.contentStart + (w[1]?.start ?? l.text.length);
            n.valueEnd = l.end - l.eol.length;
            node.children.push(n);
            sites.push({ start: n.valueStart, end: n.valueEnd, node: n });
            const raw = l.text.slice(w[1]?.start ?? l.text.length);
            if (raw) {
                this.scalarChildren(i, stop);
                result.push(this.value(raw, shape, n.valueStart));
            }
            else {
                const choices = variants(shape), nested = this.chooseArray(choices, i + 1, stop), object = choices.find(v => v.type === 'object' || v.properties);
                if (nested && (!object || this.ls.slice(i + 1, stop).find(l => l.text.trim())?.text.match(/^item(?:\s|$)/)))
                    result.push(this.readList(i + 1, stop, l.indent, nested.items, n));
                else {
                    const value = {};
                    this.readStructured(i + 1, stop, l.indent, value, shape || {}, n);
                    result.push(value);
                }
            }
            i = stop;
        }
        this.cellSources.set(result, sites);
        return result;
    }
    parseData(start, end, node, columns, fields = false) {
        const body = this.ls.slice(start, end).filter(l => l.text.trim());
        const indent = body[0]?.indent;
        for (const line of body) {
            this.structuralLine(line, true);
            if (line.indent !== indent || line.start !== node.start && line.indent <= node.indent)
                this.diagnostic('syntax.indent', 'Table headers and rows require consistent indentation', line);
        }
        let selected = columns;
        if (!selected) {
            if (fields)
                selected = [{ id: 'field' }];
            else {
                const header = body.shift();
                if (!header)
                    throw Error('A data body requires a column header');
                selected = parseTableHeader(header.text);
            }
        }
        const rows = [];
        for (const line of body) {
            try {
                const row = fields ? [decodeText(line.text)] : parseTableRow(line.text, selected);
                rows.push(row);
                let offset = line.contentStart;
                const sites = (fields ? [line.text] : splitDelimited(line.text, '.')).map(raw => { const site = { start: offset, end: offset + raw.length }; offset += raw.length + 1; return site; });
                this.cellSources.set(row, sites);
            }
            catch (error) {
                this.diagnostic('table.row', String(error.message), line, node.ref);
            }
        }
        return { columns: selected, rows };
    }
    fields(record, node) {
        const data = asRecord(record.data), columns = asArray(data.columns), at = columns.findIndex(c => asRecord(c).id === 'field');
        if (at < 0)
            return;
        const members = [];
        const authoredMembers = asArray(record.members).map(ref => findRecord(this.bundle, asRecord(ref))).filter((field) => !!field && field.role === 'field');
        for (const [ordinal, row] of asArray(data.rows).entries()) {
            const label = asArray(row)[at];
            if (typeof label !== 'string' || !label)
                continue;
            const fieldNode = { ...node, kind: 'field', raw: label, children: [], generated: true, identityKey: 'field:' + asString(record.id) + ':' + label + ':' + asArray(data.rows).slice(0, ordinal).filter(r => asArray(r)[at] === label).length };
            node.children.push(fieldNode);
            const content = { parent: { file: this.current.id, id: asString(record.id) }, ordinal };
            const cell = (id) => { const index = columns.findIndex(c => asRecord(c).id === id); return index < 0 ? undefined : asArray(row)[index]; };
            const datatype = cell('type'), comment = cell('comment');
            if (typeof datatype === 'string')
                content.datatype = datatype;
            if (typeof comment === 'string')
                content.comment = comment;
            const existing = authoredMembers.find(field => asRecord(field.content).ordinal === ordinal) ?? authoredMembers.find(field => field.title === label);
            const field = existing ?? this.add('definition', { role: 'field', title: label, content }, fieldNode);
            if (existing) {
                const authored = asRecord(field.content);
                field.title = label;
                field.content = { ...authored, ...content, parent: authored.parent ?? content.parent };
            }
            const sites = Array.isArray(row) ? this.cellSources.get(row) : undefined;
            const site = (id) => sites?.[columns.findIndex(c => asRecord(c).id === id)];
            const domain = cell('domain'), key = cell('key'), constraints = cell('constraints') ?? cell('constraint'), domainSite = site('domain'), constraintsSite = site('constraints') ?? site('constraint');
            this.fieldBindings.push({ file: this.current.id, field, ...(this.templateScope ? { scope: this.templateScope } : {}), ...(domainSite ? { domainSite } : {}), ...(constraintsSite ? { constraintsSite } : {}), ...(domain !== undefined && domain !== null && domain !== '' ? { domain } : {}), ...(key !== undefined && key !== null && key !== '' ? { key } : {}), ...(constraints !== undefined && constraints !== null && constraints !== '' ? { constraints } : {}) });
            members.push({ file: this.current.id, id: asString(field.id) });
        }
        if (members.length)
            record.members = [...members, ...asArray(record.members).filter(ref => { const member = findRecord(this.bundle, asRecord(ref)); return member?.role !== 'field'; })];
    }
    statement(index, end, ctx, node) {
        const line = this.ls[index], w = words(line.text), keyword = w[0].raw;
        node.kind = keyword;
        const columnHeader = keyword === 'erd' && w.some(x => x.raw === 'as');
        const parts = titleParts(line.text, columnHeader), head = parts.head, ws = words(head);
        if (parts.at !== undefined) {
            node.titleStart = line.contentStart + parts.at;
            node.titleEnd = line.end - line.eol.length;
        }
        const tail = (at, until = ws.length) => head.slice(ws[at]?.start ?? head.length, until < ws.length ? ws[until].start : head.length).trim();
        const clause = (word, from = 1) => ws.findIndex((x, i) => i >= from && x.raw === word);
        const nameSpan = (at, until = ws.length) => {
            node.nameStart = line.contentStart + (ws[at]?.start ?? head.length);
            node.nameEnd = line.contentStart + (until < ws.length ? ws[until].start : head.length);
            while (node.nameEnd > node.nameStart && /\s/.test(this.current.text[node.nameEnd - 1]))
                node.nameEnd--;
        };
        if (['version', 'include', 'style'].includes(keyword))
            this.scalarChildren(index, end);
        if (keyword === 'version') {
            if (ctx.kind !== 'file')
                throw Error('version is a file declaration');
            if (this.doc.version)
                this.diagnostic('version.duplicate', 'Only one version declaration is permitted', line);
            this.doc.version = decodeText(tail(1));
            if (this.doc.version !== 'ddn-next-1')
                this.diagnostic('version.unsupported', 'Unsupported language/default contract: ' + this.doc.version, line);
            return;
        }
        if (keyword === 'include') {
            if (ctx.kind !== 'file')
                throw Error('include is a file declaration');
            array(this.doc, 'includes').push(normalizeLocation(decodeText(tail(1)), this.current.id));
            return;
        }
        if (keyword === 'style') {
            if (!['file', 'view', 'document'].includes(ctx.kind))
                throw Error('style is allowed at file or view scope');
            if (!isRecord(ctx.record.style))
                ctx.record.style = {};
            const location = normalizeLocation(decodeText(tail(1)), this.current.id);
            if (ctx.kind === 'file')
                array(ctx.record.style, 'sheets').push(location);
            else {
                const asset = this.add('asset', { media_type: 'text/css', path: location }, node);
                asset.name = '_stylesheet_' + asString(asset.id);
                array(ctx.record.style, 'sheets').push({ file: this.current.id, id: asString(asset.id) });
            }
            return;
        }
        if (keyword === 'with') {
            if (ctx.kind === 'file')
                throw Error('with needs an owning declaration');
            if (ctx.record.id)
                node.owner = recordRef(this.current.id, ctx.record);
            this.readProperties(index + 1, end, line.indent, ctx.record, ctx.owner, node, '', false, ctx.appearance);
            return;
        }
        if (keyword === 'defaults') {
            const as = clause('as'), owner = decodeText(tail(1, as < 0 ? ws.length : as));
            if (!['element', 'relation', 'view', 'document', 'workarea'].includes(owner))
                throw Error('Unknown defaults owner');
            const selector = { owner: owner === 'element' || owner === 'relation' ? 'definition' : owner === 'view' ? 'view_definition' : owner };
            if (owner === 'element' || owner === 'relation')
                selector.category = owner;
            if (as >= 0)
                selector[owner === 'view' ? 'profile' : 'role'] = decodeText(tail(as + 1));
            const declarations = {};
            const rule = { selector, declarations };
            array(ctx.record, ctx.kind === 'view' || ctx.kind === 'document' ? 'role_defaults' : 'defaults').push(rule);
            this.readProperties(index + 1, end, line.indent, declarations, 'declaration_map', node, '', true);
            return;
        }
        if (keyword === 'workarea') {
            if (ctx.kind !== 'file')
                throw Error('A workarea must be declared at file level');
            if (this.doc.workarea)
                throw Error('Only one workarea per file');
            const as = clause('as'), name = decodeText(tail(1, as < 0 ? ws.length : as)).normalize('NFC');
            if (!name)
                throw Error('Workarea name must not be empty');
            node.kind = 'workarea';
            nameSpan(1, as < 0 ? ws.length : as);
            const record = { id: this.id(node, name), name, method: as < 0 ? 'ddn' : decodeText(tail(as + 1)) };
            if (parts.title !== undefined)
                record.title = parts.title;
            this.doc.workarea = record;
            node.ref = recordRef(this.current.id, record);
            this.allocations.push({ record, node, file: this.current.id, initial: node.ref.id });
            if (this.names.has(name))
                this.diagnostic('name.duplicate', 'Duplicate declared name: ' + name, line);
            this.names.set(name, node.ref);
            this.sequence(index + 1, end, line.indent, { kind: 'workarea', record, owner: 'workarea' }, node.children);
            return;
        }
        if (keyword === 'view' || keyword in recipeProfiles || keyword === 'document') {
            if (ctx.kind !== 'file')
                throw Error('Views and documents are file-level declarations');
            const as = clause('as');
            if (keyword === 'view' && as < 0 || keyword === 'document' && as < 0)
                throw Error('An explicit view/document requires as');
            const recipe = keyword in recipeProfiles ? keyword : { 'ddn::erd': 'erd', 'ddn::mindmap': 'mindmap', 'ddn::bar': 'bar' }[decodeText(tail(as + 1))];
            const profile = recipe ? recipeProfiles[recipe] : decodeText(tail(as + 1));
            const name = decodeText(tail(1, as < 0 ? ws.length : as));
            if (!name)
                throw Error('View name must not be empty');
            node.kind = keyword === 'document' ? 'document' : 'view';
            nameSpan(1, as < 0 ? ws.length : as);
            const record = this.add('view', keyword === 'document' ? { kind: 'document', format: profile } : { profile: profile, ...(recipe ? { subtype: [recipe] } : {}) }, node, name);
            if (parts.title !== undefined)
                record.title = parts.title;
            const placement = this.node(line, end, 'placement');
            placement.implicit = true;
            placement.identityKey = 'placement:' + asString(record.id);
            this.add('placement', { target: { file: this.current.id, id: asString(record.id) } }, placement);
            node.children.push(placement);
            let inputColumns;
            if (keyword === 'erd' && as >= 0) {
                inputColumns = parseTableHeader(tail(as + 1));
                record.table_schema = inputColumns;
            }
            if (keyword !== 'document' && !profiles.includes(profile))
                this.diagnostic('profile.unknown', 'Unknown profile: ' + profile, line, node.ref);
            const next = { kind: keyword === 'document' ? 'document' : 'view', record, owner: keyword === 'document' ? 'document' : 'view_definition' };
            if (recipe)
                next.recipe = recipe;
            if (inputColumns)
                next.inputColumns = inputColumns;
            next.view = record;
            if (recipe === 'mindmap') {
                const generated = this.node(line, end, 'mindmaproot');
                generated.generated = true;
                generated.identityKey = 'mindmap-root:' + asString(record.id);
                node.children.push(generated);
                const root = this.add('definition', { role: 'object', title: parts.title ?? name }, generated);
                this.selection(record, { file: this.current.id, id: asString(root.id) });
                this.appearance({ file: this.current.id, id: asString(root.id) }, record, generated);
                next.root = root;
            }
            if (recipe === 'bar') {
                const dataNode = this.node(line, end, 'chartdata');
                dataNode.generated = true;
                node.children.push(dataNode);
                const data = this.add('data', { columns: [{ id: 'label', type: 'text' }, { id: 'value', type: 'number' }], rows: [] }, dataNode);
                data.name = '_bar_' + asString(data.id);
                record.projection = { options: { records: { file: this.current.id, id: asString(data.id) }, x: 'label', y: 'value', x_type: 'category', mark: 'bar' } };
            }
            this.sequence(index + 1, end, line.indent, next, node.children);
            return;
        }
        if (keyword === 'publication') {
            if (ctx.kind !== 'file')
                throw Error('publication must be declared at file scope');
            const name = decodeText(tail(1));
            if (!name)
                throw Error('publication requires a name');
            node.kind = 'publication';
            nameSpan(1);
            const record = this.add('publication', {}, node, name);
            this.sequence(index + 1, end, line.indent, { kind: 'element', record, owner: 'publication' }, node.children);
            return;
        }
        if (keyword === 'element' || (!['connect', 'relation', 'use', 'notes', 'data', 'source', 'asset', 'template', 'draft', 'fields', 'endpoint'].includes(keyword) && ['view', 'element'].includes(ctx.kind))) {
            if (ctx.recipe === 'bar' && keyword !== 'element') {
                const value = ws.at(-1);
                if (ws.length < 2)
                    throw Error('A chart row needs a label and numeric value');
                const number = typedValue(value.raw, shapes.number, this.current.id);
                const label = decodeText(head.slice(0, value.start));
                const reference = asRecord(asRecord(ctx.record.projection).options).records;
                const data = asArray(this.doc.data).find(d => asRecord(d).id === asRecord(reference).id);
                if (!isRecord(data))
                    throw Error('Chart recipe data is unavailable');
                array(data, 'rows').push([label, number]);
                return;
            }
            if (ctx.kind === 'element' && ctx.recipe === 'erd' && keyword !== 'element') {
                node.kind = 'field-row';
                node.owner = recordRef(this.current.id, ctx.record);
                const rows = this.parseData(index, end, node, ctx.inputColumns || ['field', 'type', 'domain', 'key', 'comment'].map(id => ({ id })));
                const existing = asRecord(ctx.record.data);
                ctx.record.data = Object.keys(existing).length ? { columns: existing.columns, rows: [...asArray(existing.rows), ...asArray(rows.rows)] } : rows;
                return;
            }
            if (!['file', 'view', 'element', 'template'].includes(ctx.kind))
                throw Error('Element is not permitted here');
            if (ctx.kind === 'element' && ctx.recipe !== 'mindmap')
                throw Error('This recipe does not define nested elements');
            const as = clause('as'), from = clause('from'), using = clause('using');
            let role, name;
            let nameEnd;
            if (keyword === 'element') {
                if (as < 0)
                    throw Error('Element requires as Role');
                name = decodeText(tail(1, as));
                const roleEnd = Math.min(...[from, using, ws.length].filter(x => x > as));
                role = decodeText(tail(as + 1, roleEnd));
                nameSpan(1, as);
            }
            else {
                role = ctx.recipe === 'erd' ? 'entity' : ctx.recipe === 'mindmap' ? 'object' : '';
                if (!role)
                    throw Error('This profile requires an explicit element role');
                nameEnd = from >= 0 ? from : ws.length;
                name = decodeText(tail(0, nameEnd));
                nameSpan(0, nameEnd);
            }
            if (['core::Workarea', 'core::View', 'core::Appearance', 'core::Document'].includes(role))
                throw Error('Structural core types require dedicated declarations');
            const info = coreTypes[role] || roleTypes[role];
            if (!info || info.category !== 'element')
                this.diagnostic('role.unknown', 'Unknown element role: ' + role, line);
            node.kind = 'element';
            const record = this.add('definition', { role }, node, name || undefined);
            if (parts.title !== undefined)
                record.title = parts.title;
            if (from >= 0) {
                const limit = using > from ? using : ws.length;
                record.data = { source: this.reference(tail(from + 1, limit), line.contentStart + ws[from + 1].start) };
            }
            if (using >= 0) {
                const limit = from > using ? from : ws.length;
                record.template = this.reference(tail(using + 1, limit), line.contentStart + ws[using + 1].start);
            }
            let occurrence;
            if (ctx.view) {
                this.selection(ctx.view, { file: this.current.id, id: asString(record.id) });
                occurrence = this.appearance({ file: this.current.id, id: asString(record.id) }, ctx.view, node);
            }
            if (ctx.recipe === 'mindmap' && (ctx.parent || ctx.root)) {
                const parent = ctx.parent || ctx.root;
                const edgeNode = this.node(line, end, 'branch');
                edgeNode.generated = true;
                edgeNode.identityKey = 'branch:' + asString(parent.id) + ':' + asString(record.id);
                node.children.push(edgeNode);
                const edge = this.add('definition', { category: 'relation', role: 'assoc', endpoints: [{ definition: { file: this.current.id, id: asString(parent.id) } }, { definition: { file: this.current.id, id: asString(record.id) } }] }, edgeNode);
                if (ctx.view) {
                    this.selection(ctx.view, { file: this.current.id, id: asString(edge.id) });
                    this.appearance({ file: this.current.id, id: asString(edge.id) }, ctx.view, edgeNode);
                }
            }
            const child = { kind: 'element', record, owner: 'definition' };
            if (occurrence)
                child.appearance = occurrence;
            if (ctx.view)
                child.view = ctx.view;
            if (ctx.recipe)
                child.recipe = ctx.recipe;
            if (ctx.inputColumns)
                child.inputColumns = ctx.inputColumns;
            if (ctx.root)
                child.root = ctx.root;
            child.parent = record;
            this.sequence(index + 1, end, line.indent, child, node.children);
            this.fields(record, node);
            return;
        }
        if (keyword === 'draft' || keyword === 'fields') {
            if (ctx.kind !== 'element')
                throw Error('Draft/fields requires an element');
            node.owner = recordRef(this.current.id, ctx.record);
            if (keyword === 'draft') {
                const format = decodeText(tail(1)) || 'text';
                if (!['text', 'fields', 'table'].includes(format))
                    throw Error('Unknown draft interpretation');
                ctx.record.draft = { format, text: this.rawBody(index + 1, end) };
            }
            else
                ctx.record.data = this.parseData(index + 1, end, node, undefined, true);
            return;
        }
        if (keyword === 'data') {
            if (ctx.kind === 'template') {
                if (tail(1))
                    throw Error('The template fragment schema has no named data collection; use an element data body');
                const settings = (ctx.record.settings ??= {});
                settings.data = this.parseData(index + 1, end, node);
                return;
            }
            const from = clause('from'), name = decodeText(tail(1, from < 0 ? ws.length : from));
            if (ctx.kind === 'file' && !name)
                throw Error('File-level data requires a name');
            let record;
            if (name) {
                node.kind = 'data';
                nameSpan(1, from < 0 ? ws.length : from);
                record = this.add('data', {}, node, name);
            }
            else {
                if (ctx.kind !== 'element')
                    throw Error('Anonymous data belongs to an element');
                record = {};
                ctx.record.data = record;
                node.owner = recordRef(this.current.id, ctx.record);
            }
            const firstBody = this.ls.slice(index + 1, end).find(l => l.text.trim() && !l.text.trimStart().startsWith('//'));
            if (from >= 0 || firstBody?.text.trim() === 'with') {
                if (from >= 0)
                    record.source = this.reference(tail(from + 1), line.contentStart + ws[from + 1].start);
                this.sequence(index + 1, end, line.indent, { kind: 'element', record, owner: 'data_record' }, node.children);
            }
            else
                Object.assign(record, this.parseData(index + 1, end, node));
            return;
        }
        if (keyword === 'use') {
            if (ctx.kind !== 'view' && ctx.kind !== 'document')
                throw Error('use belongs to a view/document');
            const named = clause('named'), raw = tail(1, named < 0 ? ws.length : named), reference = this.reference(raw, line.contentStart + ws[1].start);
            const name = named >= 0 ? decodeText(tail(named + 1)) : undefined;
            if (ctx.kind === 'document') {
                const section = { kind: 'view', target: reference };
                if (parts.title !== undefined)
                    section.title = parts.title;
                array(ctx.record, 'sections').push(section);
                node.owner = recordRef(this.current.id, ctx.record);
                this.sequence(index + 1, end, line.indent, { kind: 'element', record: section, owner: 'inclusion' }, node.children);
            }
            else {
                this.selection(ctx.record, reference);
                node.kind = 'use';
                const occurrence = this.appearance(reference, ctx.record, node, name, parts.title);
                node.ref = recordRef(this.current.id, occurrence);
                node.children = node.children.filter(n => n.ref?.id !== node.ref.id);
                if (named >= 0)
                    nameSpan(named + 1);
                this.sequence(index + 1, end, line.indent, { kind: 'element', record: occurrence, owner: 'appearance' }, node.children);
            }
            return;
        }
        if (keyword === 'connect' || keyword === 'relation') {
            if (!['file', 'view'].includes(ctx.kind))
                throw Error('Relations belong at file or view scope');
            const as = clause('as'), named = clause('named');
            let role = as >= 0 ? decodeText(tail(as + 1, named > as ? named : ws.length)) : ctx.recipe === 'erd' || ctx.recipe === 'mindmap' ? 'assoc' : '';
            if (!role)
                throw Error('Choose a relationship role with as');
            const name = keyword === 'relation' ? decodeText(tail(1, as)) : named >= 0 ? decodeText(tail(named + 1)) : undefined;
            node.kind = 'relation';
            if (keyword === 'relation')
                nameSpan(1, as);
            else if (named >= 0)
                nameSpan(named + 1);
            const record = this.add('definition', { category: 'relation', role, endpoints: [] }, node, name);
            if (parts.title !== undefined)
                record.title = parts.title;
            // Relation display settings belong to this view occurrence. Create
            // it before reading `with` so compact connect declarations can carry
            // label/legend settings without changing the shared relationship.
            const appearance = ctx.view ? this.appearance({ file: this.current.id, id: asString(record.id) }, ctx.view, node) : undefined;
            const endpoint = (raw, start) => {
                const ww = words(raw), at = ww.findIndex(x => x.raw === 'at');
                const refraw = raw.slice(0, at < 0 ? raw.length : ww[at].start).trim();
                const result = { definition: this.reference(refraw, start) };
                if (at >= 0) {
                    const memberRaw = raw.slice(ww[at + 1]?.start ?? raw.length);
                    result.member = this.reference(memberRaw, start + (ww[at + 1]?.start ?? raw.length), 'member');
                }
                return result;
            };
            if (keyword === 'connect') {
                const to = clause('to');
                if (to < 0)
                    throw Error('connect requires to');
                const limit = Math.min(...[as, named, ws.length].filter(x => x > to));
                record.endpoints = [endpoint(tail(1, to), line.contentStart + ws[1].start), endpoint(tail(to + 1, limit), line.contentStart + ws[to + 1].start)];
                this.sequence(index + 1, end, line.indent, { kind: 'element', record, owner: 'definition', ...(appearance ? { appearance } : {}) }, node.children);
            }
            else {
                let indent;
                for (let i = index + 1; i < end;) {
                    const l = this.ls[i];
                    if (!l.text.trim() || l.text.startsWith('//')) {
                        i++;
                        continue;
                    }
                    this.structuralLine(l);
                    indent ??= l.indent;
                    if (l.indent <= line.indent || l.indent !== indent)
                        this.diagnostic('syntax.indent', 'Relation children require consistent indentation', l);
                    const stop = this.blockEnd(i, end);
                    if (l.text.startsWith('endpoint ')) {
                        const ep = endpoint(l.text.slice(9), l.contentStart + 9);
                        array(record, 'endpoints').push(ep);
                        this.sequence(i + 1, stop, l.indent, { kind: 'element', record: ep, owner: 'endpoint' }, node.children);
                    }
                    else if (l.text === 'with')
                        this.readProperties(i + 1, stop, l.indent, record, 'definition', node, '', false, appearance);
                    else
                        this.diagnostic('relation.child', 'Expected endpoint or with', l, node.ref);
                    i = stop;
                }
            }
            if (ctx.view) {
                this.selection(ctx.view, { file: this.current.id, id: asString(record.id) });
            }
            return;
        }
        if (keyword === 'notes') {
            if (parts.at === undefined)
                throw Error('notes requires a title colon');
            const name = decodeText(tail(1)).normalize('NFC');
            node.kind = 'notes';
            const note = { text: this.rawBody(index + 1, end), format: 'markdown' };
            if (parts.title !== undefined)
                note.title = parts.title;
            if (ctx.kind === 'element') {
                note.id = this.id(node, name || undefined);
                if (name) {
                    note.name = name;
                    if (this.names.has(name))
                        this.diagnostic('name.duplicate', 'Duplicate declared name: ' + name, line);
                    this.names.set(name, recordRef(this.current.id, note));
                }
                node.ref = recordRef(this.current.id, note);
                array(ctx.record, 'notes').push(note);
            }
            else if (ctx.kind === 'file') {
                const view = this.add('view', { profile: 'ddn@1', subtype: ['notes'], notes: [note], ...(parts.title !== undefined ? { title: parts.title } : {}) }, node, name || undefined);
                const placement = this.node(line, end, 'placement');
                this.add('placement', { target: { file: this.current.id, id: asString(view.id) } }, placement);
            }
            else {
                const text = this.add('definition', { role: 'core::Text', content: { text: note.text, format: 'markdown' }, ...(parts.title !== undefined ? { title: parts.title } : {}) }, node, name || undefined);
                if (ctx.kind === 'document')
                    array(ctx.record, 'sections').push({ kind: 'text', target: { file: this.current.id, id: asString(text.id) } });
                else if (ctx.view) {
                    this.selection(ctx.view, { file: this.current.id, id: asString(text.id) });
                    this.appearance({ file: this.current.id, id: asString(text.id) }, ctx.view, node);
                }
            }
            if (name)
                nameSpan(1);
            return;
        }
        if (keyword === 'source' || keyword === 'asset' || keyword === 'template') {
            if (ctx.kind !== 'file')
                throw Error(keyword + ' must be declared at file scope');
            const as = clause('as'), from = clause('from');
            if (as < 0)
                throw Error(keyword + ' requires as');
            const name = decodeText(tail(1, as)), type = decodeText(tail(as + 1, from > as ? from : ws.length));
            node.kind = keyword;
            nameSpan(1, as);
            const record = this.add(keyword, keyword === 'source' ? { mode: type } : keyword === 'template' ? { role: type } : {}, node, name);
            if (keyword === 'asset') {
                if (from < 0)
                    throw Error('asset requires from');
                record.path = normalizeLocation(decodeText(tail(from + 1)), this.current.id);
            }
            if (keyword === 'template') {
                const outerDocument = this.doc, outerNames = this.names, outerScope = this.templateScope;
                this.doc = {};
                this.names = new Map();
                this.templateScope = node.ref;
                try {
                    this.sequence(index + 1, end, line.indent, { kind: 'template', record, owner: 'template_record' }, node.children);
                    if (Object.keys(this.doc).length) {
                        const fragment = asRecord(record.fragment);
                        for (const [key, values] of Object.entries(this.doc))
                            fragment[key] = [...asArray(fragment[key]), ...asArray(values)];
                        record.fragment = fragment;
                    }
                    const fragment = asRecord(record.fragment);
                    for (const collection of ['definitions', 'views', 'appearances'])
                        for (const [ordinal, item] of asArray(fragment[collection]).entries())
                            if (isRecord(item)) {
                                if (!item.id)
                                    item.id = 'fragment-' + collection + '-' + ordinal;
                                for (const [noteIndex, note] of asArray(item.notes).entries())
                                    if (isRecord(note) && !note.id)
                                        note.id = asString(item.id) + '-note-' + noteIndex;
                            }
                }
                finally {
                    this.doc = outerDocument;
                    this.names = outerNames;
                    this.templateScope = outerScope;
                }
            }
            else
                this.sequence(index + 1, end, line.indent, { kind: 'element', record, owner: keyword + '_record' }, node.children);
            return;
        }
        throw Error('Unexpected declaration: ' + keyword);
    }
    parseFile(file) {
        if (this.parsed.has(file))
            return;
        this.parsed.add(file);
        const source = this.sourceMap.get(file);
        if (!source) {
            this.diagnostic('include.missing', 'Selected source is unavailable: ' + file);
            return;
        }
        this.current = source;
        this.ls = lines(source.text);
        this.doc = {};
        this.serial = 0;
        this.usedIds = new Set();
        this.reservedIds = new Set();
        this.reserveAuthoredIds(0, this.ls.length);
        this.names = new Map();
        this.syntax = { file: source, nodes: [], newline: source.text.includes('\r\n') ? '\r\n' : '\n', bom: source.text.startsWith('\ufeff') };
        this.documents.push(this.syntax);
        this.bundle.files.push({ location: file, document: this.doc });
        this.sequence(0, this.ls.length, -1, { kind: 'file', record: this.doc, owner: 'file' }, this.syntax.nodes);
        const includes = asArray(this.doc.includes).filter((x) => typeof x === 'string');
        for (const include of includes)
            this.parseFile(include);
    }
    resolve() {
        const remap = new Map();
        for (const item of this.allocations) {
            const current = asString(item.record.id);
            if (current !== item.initial)
                remap.set(item.file + '\0' + item.initial, current);
            item.node.ref = { file: item.file, id: current };
        }
        const rewrite = (value) => {
            if (Array.isArray(value)) {
                for (const item of value)
                    rewrite(item);
            }
            else if (isRecord(value)) {
                if (typeof value.file === 'string' && typeof value.id === 'string') {
                    const id = remap.get(value.file + '\0' + value.id);
                    if (id)
                        value.id = id;
                }
                for (const v of Object.values(value))
                    rewrite(v);
            }
        };
        rewrite(this.bundle);
        for (const doc of this.documents) {
            const visit = (nodes) => {
                for (const n of nodes) {
                    if (n.ref) {
                        const id = remap.get(n.ref.file + '\0' + n.ref.id);
                        if (id)
                            n.ref = { file: n.ref.file, id };
                    }
                    if (n.owner) {
                        const id = remap.get(n.owner.file + '\0' + n.owner.id);
                        if (id)
                            n.owner = { file: n.owner.file, id };
                    }
                    visit(n.children);
                }
            };
            visit(doc.nodes);
        }
        const identities = new Set();
        for (const r of listRecords(this.bundle)) {
            if (!r.ref.id)
                continue;
            const key = r.file + '\0' + r.ref.id;
            if (identities.has(key))
                this.diagnostics.push({ code: 'identity.duplicate', severity: 'error', message: 'Duplicate identity: ' + r.ref.id, target: r.ref });
            identities.add(key);
        }
        for (const binding of this.fieldBindings)
            if (binding.scope) {
                const id = remap.get(binding.scope.file + '\0' + binding.scope.id);
                if (id)
                    binding.scope = { file: binding.scope.file, id };
            }
        for (const site of this.references) {
            if (site.scope) {
                const id = remap.get(site.scope.file + '\0' + site.scope.id);
                if (id)
                    site.scope = { file: site.scope.file, id };
            }
            if (site.kind === 'member')
                continue;
            const template = site.scope ? findRecord(this.bundle, site.scope) : undefined;
            const fragment = asRecord(template?.fragment);
            const scoped = template ? listRecords({ version: 'ddn-next-1', entry: site.file, files: [{ location: site.file, document: fragment }] }) : [];
            const match = resolveSourceReference(this.bundle, site, scoped);
            if (match) {
                site.reference.id = match.ref.id;
                site.target = match.ref;
            }
            else
                this.diagnostics.push({ code: 'reference.unresolved', severity: 'error', message: 'Unresolved or ambiguous reference: ' + asString(site.reference.name), source: { file: site.file, revision: this.sourceMap.get(site.file)?.revision || '', start: site.start, end: site.end } });
        }
    }
    resolveFieldBindings() {
        this.references = this.references.filter(site => !site.boundCell);
        const allowedKeys = new Set(['primary', 'candidate', 'business', 'partition', 'clustering', 'foreign']);
        for (const binding of this.fieldBindings) {
            const content = asRecord(binding.field.content), target = recordRef(binding.file, binding.field);
            const derived = ['content.domain', 'content.key', 'content.constraints'];
            const retained = asArray(binding.field.incomplete).filter(item => !derived.includes(asString(asRecord(item).path)));
            if (retained.length)
                binding.field.incomplete = retained;
            else
                delete binding.field.incomplete;
            this.diagnostics = this.diagnostics.filter(d => !(d.target?.file === target.file && d.target.id === target.id && ['field.domain', 'field.key', 'field.constraints'].includes(d.code)));
            const template = binding.scope ? findRecord(this.bundle, binding.scope) : undefined;
            const scoped = template ? listRecords({ version: 'ddn-next-1', entry: binding.file, files: [{ location: binding.file, document: asRecord(template.fragment) }] }) : [];
            const incomplete = (path, value, reason) => { const raw = typeof value === 'string' ? value : JSON.stringify(value); array(binding.field, 'incomplete').push({ path, raw, reason }); this.diagnostics.push({ code: 'field.' + path.split('.').at(-1), severity: 'warning', message: reason, target }); };
            const resolve = (value) => {
                if (isRecord(value))
                    return resolveSourceReference(this.bundle, { file: binding.file, start: 0, end: 0, kind: 'reference', reference: { ...value } }, scoped);
                if (typeof value !== 'string')
                    return undefined;
                const exact = resolveSourceReference(this.bundle, { file: binding.file, start: 0, end: 0, kind: 'reference', reference: { file: binding.file, name: value } }, scoped);
                if (exact)
                    return exact;
                const parts = splitDelimited(value, '::');
                if (parts.length > 2)
                    return undefined;
                let file = binding.file, name = value;
                if (parts.length === 2) {
                    try {
                        file = normalizeLocation(decodeText(parts[0]), binding.file);
                        name = decodeText(parts[1]);
                    }
                    catch {
                        return undefined;
                    }
                }
                const site = { file: binding.file, start: 0, end: 0, kind: 'reference', reference: { file, name } };
                return resolveSourceReference(this.bundle, site, scoped);
            };
            const referenceSite = (value, entry, site) => {
                if (!site)
                    return;
                let start = site.start, end = site.end;
                let spelling = 'cell';
                if (isRecord(value)) {
                    if (typeof value.name !== 'string')
                        return;
                    const property = site.node?.children.find(n => n.path?.split('.').at(-1) === 'name');
                    if (property?.valueStart === undefined || property.valueEnd === undefined)
                        return;
                    start = property.valueStart;
                    end = property.valueEnd;
                    spelling = 'name';
                }
                else if (typeof value === 'string' && value === entry.ref.id && value !== entry.record.name)
                    spelling = 'id';
                this.references.push({ file: binding.file, start, end, reference: { file: entry.file, id: entry.ref.id, ...(typeof entry.record.name === 'string' ? { name: entry.record.name } : {}) }, target: entry.ref, kind: 'reference', spelling, boundCell: true, ...(binding.scope ? { scope: binding.scope } : {}) });
            };
            if (binding.domain !== undefined) {
                const domain = resolve(binding.domain);
                const descriptor = domain && (roleTypes[asString(domain.record.role)] || coreTypes[asString(domain.record.role)]);
                if (domain && domain.kind === 'definition' && descriptor?.core === 'EL08') {
                    content.domain = { file: domain.file, id: domain.ref.id };
                    referenceSite(binding.domain, domain, binding.domainSite);
                }
                else
                    incomplete('content.domain', binding.domain, 'The domain cell must identify an existing named domain; no domain fact was inferred');
            }
            if (binding.key !== undefined) {
                if (typeof binding.key === 'string' && allowedKeys.has(binding.key))
                    content.key = binding.key;
                else
                    incomplete('content.key', binding.key, 'The key cell is retained as draft text; use a registered key value to assert its meaning');
            }
            if (binding.constraints !== undefined) {
                const values = Array.isArray(binding.constraints) ? binding.constraints : [binding.constraints], resolved = [];
                let valid = true;
                for (const [index, value] of values.entries()) {
                    const constraint = resolve(value);
                    const descriptor = constraint && (roleTypes[asString(constraint.record.role)] || coreTypes[asString(constraint.record.role)]);
                    if (!constraint || constraint.kind !== 'definition' || descriptor?.core !== 'EL21') {
                        valid = false;
                        break;
                    }
                    resolved.push({ file: constraint.file, id: constraint.ref.id });
                    referenceSite(value, constraint, Array.isArray(binding.constraints) ? this.cellSources.get(binding.constraints)?.[index] : binding.constraintsSite);
                }
                if (valid)
                    content.constraints = resolved;
                else
                    incomplete('content.constraints', binding.constraints, 'Constraint cells must identify existing constraints; arbitrary text was not converted into a constraint');
            }
        }
    }
    resolveChildren() {
        for (const site of this.references) {
            if (site.target || site.kind !== 'reference')
                continue;
            const match = resolveSourceReference(this.bundle, site);
            if (!match)
                continue;
            site.reference.id = match.ref.id;
            site.target = match.ref;
            this.diagnostics = this.diagnostics.filter(d => !(d.code === 'reference.unresolved' && d.source?.file === site.file && d.source.start === site.start));
        }
        for (const entry of listRecords(this.bundle)) {
            if (entry.kind === 'view' && isRecord(entry.record.selection) && Array.isArray(entry.record.selection.include)) {
                const seen = new Set();
                const selection = entry.record.selection;
                selection.include = selection.include.filter(reference => {
                    const target = resolveReference(this.bundle, entry.file, reference);
                    if (!target)
                        return true;
                    const key = target.file + '\0' + target.ref.id;
                    if (seen.has(key))
                        return false;
                    seen.add(key);
                    return true;
                });
            }
            if (entry.kind === 'definition')
                for (const [endpointIndex, endpoint] of asArray(entry.record.endpoints).entries()) {
                    const ep = asRecord(endpoint);
                    let definition = resolveReference(this.bundle, entry.file, ep.definition);
                    if (definition?.kind === 'appearance') {
                        if (definition.file !== entry.file) {
                            this.diagnostics.push({ code: 'reference.appearance-scope', severity: 'error', message: 'An endpoint occurrence must be local to the relationship file', target: entry.ref });
                        }
                        else {
                            const selected = resolveReference(this.bundle, definition.file, definition.record.target);
                            if (selected?.kind === 'definition') {
                                const occurrence = definition;
                                ep.definition = { file: selected.file, id: selected.ref.id };
                                definition = selected;
                                const parent = resolveReference(this.bundle, occurrence.file, occurrence.record.parent);
                                const appearances = listRecords(this.bundle).filter(item => item.kind === 'appearance' && resolveReference(this.bundle, item.file, item.record.target)?.ref.id === entry.ref.id && resolveReference(this.bundle, item.file, item.record.target)?.file === entry.file && resolveReference(this.bundle, item.file, item.record.parent)?.ref.id === parent?.ref.id && resolveReference(this.bundle, item.file, item.record.parent)?.file === parent?.file);
                                if (endpointIndex > 1 || !appearances.length)
                                    this.diagnostics.push({ code: 'reference.appearance-route', severity: 'error', message: 'An explicit endpoint occurrence requires a local binary relation appearance', target: entry.ref });
                                else
                                    for (const appearance of appearances) {
                                        const route = (appearance.record.route ??= {});
                                        const side = endpointIndex === 0 ? 'from' : 'to';
                                        if (route[side] === undefined)
                                            route[side] = { file: occurrence.file, id: occurrence.ref.id };
                                    }
                            }
                            else
                                this.diagnostics.push({ code: 'reference.appearance-target', severity: 'error', message: 'Endpoint occurrence must target an existing definition', target: entry.ref });
                        }
                    }
                    if (isRecord(ep.member) && definition) {
                        const id = asString(ep.member.id), name = asString(ep.member.name, id), file = asString(ep.member.file, definition.file);
                        const candidates = asArray(definition.record.members).map(ref => resolveReference(this.bundle, definition.file, ref)).filter(x => x && x.file === file && (id ? x.record.id === id : x.record.id === name || x.record.title === name || x.record.name === name));
                        const site = this.references.find(s => s.reference === ep.member);
                        if (candidates.length === 1) {
                            ep.member = { file: candidates[0].file, id: candidates[0].ref.id };
                            if (site)
                                site.target = candidates[0].ref;
                        }
                        else
                            this.diagnostics.push({ code: 'reference.member', severity: 'error', message: 'Missing or ambiguous endpoint member: ' + name, target: entry.ref });
                    }
                }
            if (entry.kind === 'view' && entry.record.kind === 'document')
                for (const section of asArray(entry.record.sections)) {
                    const s = asRecord(section), target = resolveReference(this.bundle, entry.file, s.target);
                    if (target)
                        s.kind = target.kind === 'data' ? 'data' : target.kind === 'asset' ? 'asset' : target.kind === 'definition' ? 'text' : 'view';
                }
        }
    }
    expandTemplates() {
        const expanded = new Set(), stack = new Set();
        const copy = (value) => Array.isArray(value) ? value.map(copy) : isRecord(value) ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, copy(v)])) : value;
        const error = (code, message, target) => { this.diagnostics.push({ code: 'template.' + code, severity: 'error', message, target }); };
        const compatible = (value, shape) => variants(shape).some(s => {
            const types = typeof s.type === 'string' ? [s.type] : s.type || [];
            if (value === null)
                return types.includes('null');
            if (Array.isArray(value))
                return types.includes('array') && value.every(v => compatible(v, s.items));
            if (isRecord(value))
                return (types.includes('object') || !!s.properties) && Object.entries(value).every(([k, v]) => { const child = childShape(s, k); return !!child && compatible(v, child); });
            return types.includes(typeof value) || (typeof value === 'number' && Number.isInteger(value) && types.includes('integer'));
        });
        const expand = (file, record, ancestry = []) => {
            const key = file + '\0' + asString(record.id), target = recordRef(file, record);
            if (expanded.has(key) || !record.template)
                return;
            const template = resolveReference(this.bundle, file, record.template);
            if (!template || template.kind !== 'template') {
                error('reference', 'Template reference must resolve to a template', target);
                return;
            }
            const templateKey = template.file + '\0' + template.ref.id;
            if (stack.has(key) || ancestry.includes(templateKey)) {
                error('cycle', 'Recursive template expansion is invalid', target);
                return;
            }
            stack.add(key);
            if (template.record.role !== record.role) {
                error('role', 'Template role differs from the instance role', target);
                stack.delete(key);
                return;
            }
            const parameters = asRecord(template.record.parameters), arguments_ = asRecord(record.arguments), bindings = {};
            for (const name of Object.keys(arguments_))
                if (!Object.hasOwn(parameters, name))
                    error('argument', 'Unknown template argument: ' + name, target);
            for (const [name, raw] of Object.entries(parameters)) {
                const parameter = asRecord(raw), value = Object.hasOwn(arguments_, name) ? arguments_[name] : parameter.default;
                if (value === undefined) {
                    if (parameter.required === true)
                        error('required', 'Missing required template argument: ' + name, target);
                    continue;
                }
                const type = asString(parameter.type, 'text'), shape = type === 'json' ? shapes.json_value : shapes[type];
                if (!shape || !compatible(value, shape)) {
                    error('argument-type', 'Invalid template argument type for ' + name, target);
                    continue;
                }
                bindings[name] = copy(value);
            }
            const bind = (value) => {
                if (isRecord(value) && typeof value.parameter === 'string' && Object.keys(value).length === 1) {
                    if (!Object.hasOwn(parameters, value.parameter)) {
                        error('parameter', 'Unknown parameter: ' + value.parameter, target);
                        return undefined;
                    }
                    if (!Object.hasOwn(bindings, value.parameter)) {
                        error('required', 'Missing template value: ' + value.parameter, target);
                        return undefined;
                    }
                    return copy(bindings[value.parameter]);
                }
                if (Array.isArray(value)) {
                    const out = [];
                    for (const item of value) {
                        const next = bind(item);
                        if (next === undefined)
                            return undefined;
                        out.push(next);
                    }
                    return out;
                }
                if (isRecord(value)) {
                    const out = {};
                    for (const [k, v] of Object.entries(value)) {
                        const next = bind(v);
                        if (next === undefined)
                            return undefined;
                        out[k] = next;
                    }
                    return out;
                }
                return value;
            };
            for (const [path, raw] of Object.entries(asRecord(template.record.settings))) {
                if (['id', 'name', 'acceptance', 'acceptance_history', 'access'].includes(path.split('.')[0]) || path === 'design.state' && raw === 'accepted') {
                    error('authority', 'Template setting cannot supply identity or acceptance authority: ' + path, target);
                    continue;
                }
                if (getPath(record, path) !== undefined)
                    continue;
                const value = bind(raw);
                if (value === undefined)
                    continue;
                const shape = ownerShape('definition', record, path);
                if (!shape || !compatible(value, shape)) {
                    error('property-type', 'Template setting has the wrong registered type: ' + path, target);
                    continue;
                }
                setPath(record, path, value);
            }
            const fragment = asRecord(template.record.fragment), local = new Map();
            const generated = { definitions: [], views: [], appearances: [] };
            const bindingCopies = new Map();
            for (const collection of ['definitions', 'views', 'appearances'])
                for (const [ordinal, raw] of asArray(fragment[collection]).entries()) {
                    if (!isRecord(raw))
                        continue;
                    const child = copy(raw), old = asString(raw.id, 'fragment-' + collection + '-' + ordinal);
                    if (local.has(old)) {
                        error('identity', 'Duplicate identity inside template fragment: ' + old, target);
                        continue;
                    }
                    child.id = asString(record.id) + '--' + old;
                    local.set(old, asString(child.id));
                    if (typeof raw.name === 'string')
                        child.name = asString(record.name, asString(record.id)) + '::' + raw.name;
                    for (const [noteIndex, note] of asArray(child.notes).entries())
                        if (isRecord(note)) {
                            const original = asString(note.id, old + '-note-' + noteIndex);
                            const mutable = note;
                            mutable.id = asString(record.id) + '--' + original;
                            local.set(original, asString(mutable.id));
                            if (typeof mutable.name === 'string')
                                mutable.name = asString(record.name, asString(record.id)) + '::' + mutable.name;
                        }
                    const binding = this.fieldBindings.find(b => b.file === template.file && b.scope?.id === template.ref.id && b.field.id === raw.id);
                    if (binding)
                        bindingCopies.set(child, binding);
                    generated[collection].push(child);
                }
            const remap = (value) => {
                if (Array.isArray(value)) {
                    for (const v of value)
                        remap(v);
                }
                else if (isRecord(value)) {
                    const mutable = value;
                    if ((value.file === template.file || value.file === undefined) && typeof value.id === 'string' && local.has(value.id)) {
                        mutable.file = file;
                        mutable.id = local.get(value.id);
                        delete mutable.name;
                    }
                    for (const v of Object.values(value))
                        remap(v);
                }
            };
            const document = this.bundle.files.find(f => f.location === file).document;
            const instanceAppearances = listRecords(this.bundle).filter(entry => entry.kind === 'appearance' && asRecord(entry.record.target).id === record.id && asString(asRecord(entry.record.target).file, entry.file) === file);
            const children = [];
            for (const collection of ['definitions', 'views', 'appearances'])
                for (const child of generated[collection]) {
                    // Remap nested references, never the generated record's own identity.
                    for (const value of Object.values(child))
                        remap(value);
                    if (listRecords(this.bundle).some(existing => existing.file === file && (existing.record.id === child.id || child.name && existing.record.name === child.name))) {
                        error('collision', 'Generated template child identity or name collision', target);
                        continue;
                    }
                    array(document, collection).push(child);
                    if (collection === 'definitions')
                        children.push(child);
                    const binding = bindingCopies.get(child), content = asRecord(child.content);
                    if (binding)
                        this.fieldBindings.push({ file, field: child, ...(binding.domain !== undefined ? { domain: content.domain ?? binding.domain } : {}), ...(binding.key !== undefined ? { key: binding.key } : {}), ...(binding.constraints !== undefined ? { constraints: content.constraints ?? binding.constraints } : {}) });
                    if (collection === 'views')
                        array(document, 'placements').push({ id: asString(child.id) + '--placement', target: { file, id: asString(child.id) } });
                }
            const explicitlyPlaced = new Set(generated.appearances.map(a => asString(asRecord(a.target).id)));
            for (const child of children) {
                if (!explicitlyPlaced.has(asString(child.id)))
                    for (const occurrence of instanceAppearances) {
                        const parent = asRecord(occurrence.record.parent), owner = this.bundle.files.find(f => f.location === occurrence.file).document;
                        array(owner, 'appearances').push({ id: occurrence.ref.id + '--' + asString(child.id), target: { file, id: asString(child.id) }, parent });
                        const viewFile = asString(parent.file, occurrence.file), viewDocument = this.bundle.files.find(f => f.location === viewFile)?.document;
                        const view = asArray(viewDocument?.views).find(v => asRecord(v).id === parent.id);
                        if (isRecord(view))
                            this.selection(view, { file, id: asString(child.id) });
                    }
                expand(file, child, [...ancestry, templateKey]);
            }
            if (children.length) {
                const members = array(record, 'members');
                for (const child of children)
                    if (child.category !== 'relation' && !members.some(m => asRecord(m).file === file && asRecord(m).id === child.id))
                        members.push({ file, id: asString(child.id) });
            }
            stack.delete(key);
            expanded.add(key);
        };
        for (const item of listRecords(this.bundle))
            if (item.kind === 'definition')
                expand(item.file, item.record);
    }
    run() { this.parseFile(this.bundle.entry); this.resolve(); this.resolveFieldBindings(); this.expandTemplates(); this.resolveFieldBindings(); this.resolveChildren(); const checked = listRecords(this.bundle).filter(r => typeof r.record.id === 'string' && r.record.id.length > 0).map(r => r.ref); const unavailable = this.diagnostics.filter(d => ['include.missing', 'reference.unresolved', 'version.unsupported'].includes(d.code)).map(d => d.message); return { syntaxValid: !this.diagnostics.some(d => d.severity === 'error' && /^(syntax|property|table)\./.test(d.code)), normalized: this.bundle, documents: this.documents, diagnostics: this.diagnostics, coverage: { scope: { kind: 'workarea' }, complete: !this.diagnostics.some(d => d.severity === 'error'), checked, unavailable }, references: this.references }; }
}
export function decodeSources(input, options = {}) {
    if (options.cancel?.aborted)
        return { syntaxValid: false, normalized: { version: 'ddn-next-1', entry: input.entry, files: [] }, documents: [], diagnostics: [{ code: 'decode.cancelled', severity: 'info', message: 'Decoding was cancelled' }], coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: ['cancelled'] }, references: [] };
    return new Decoder(input, options).run();
}
export function allNodes(result) { const flatten = (nodes) => nodes.flatMap(n => [n, ...flatten(n.children)]); return result.documents.flatMap(d => flatten(d.nodes)); }
export function findNode(result, target) { return allNodes(result).find(n => n.ref?.file === target.file && n.ref.id === target.id); }
export function applySourcePatches(input, patches) {
    const selected = new Map();
    for (const file of input.files) {
        const location = normalizeLocation(file.id);
        if (selected.has(location))
            throw Error('Duplicate selected source location: ' + location);
        selected.set(location, file);
    }
    const planned = new Map();
    for (const patch of patches) {
        const location = normalizeLocation(patch.file), file = selected.get(location);
        if (!file)
            throw Error('Patch targets an unavailable source: ' + patch.file);
        if (!file.writable)
            throw Error('Source is read-only: ' + file.id);
        if (patch.base !== file.revision)
            throw Error('Source revision conflict');
        if (!Number.isSafeInteger(patch.start) || !Number.isSafeInteger(patch.end) || patch.start < 0 || patch.end < patch.start || patch.end > file.text.length || typeof patch.text !== 'string')
            throw Error('Overlapping or invalid source patches');
        const edits = planned.get(location) ?? [];
        edits.push(patch);
        planned.set(location, edits);
    }
    // Validate the entire multi-file transaction before producing changed files.
    for (const [location, edits] of planned) {
        edits.sort((a, b) => b.start - a.start);
        let before = selected.get(location).text.length;
        for (const patch of edits) {
            if (patch.end > before)
                throw Error('Overlapping or invalid source patches');
            before = patch.start;
        }
    }
    return { entry: input.entry, files: input.files.map(file => {
            const edits = planned.get(normalizeLocation(file.id));
            if (!edits?.length)
                return file;
            let text = file.text;
            for (const patch of edits)
                text = text.slice(0, patch.start) + patch.text + text.slice(patch.end);
            if (text === file.text)
                return file;
            if (!file.originalBytes)
                return { ...file, text };
            const encoded = new TextEncoder().encode(text);
            const bytes = file.originalBytes;
            // Some hosts retain the BOM only in originalBytes. It then has no text
            // offset and must remain separate; a BOM present in text follows edits.
            const externalBom = !file.text.startsWith('\ufeff') && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf;
            const originalBytes = externalBom ? new Uint8Array(encoded.length + 3) : encoded;
            if (externalBom) {
                originalBytes.set([0xef, 0xbb, 0xbf]);
                originalBytes.set(encoded, 3);
            }
            return { ...file, text, originalBytes };
        }) };
}
function patch(result, file, start, end, text) {
    const source = result.documents.find(d => d.file.id === file)?.file;
    if (!source)
        throw Error('Source not loaded');
    if (start < end && end === source.text.length && !source.text.endsWith('\n'))
        text = text.replace(/\r?\n$/, '');
    return { file, base: source.revision, start, end, text };
}
function childIndent(result, node) {
    const child = node.children.find(child => !child.implicit && !child.generated && child.indent > node.indent);
    if (child)
        return child.indent;
    const parent = allNodes(result).find(parent => parent.children.includes(node) && parent.indent < node.indent);
    return node.indent + (parent ? node.indent - parent.indent : 4);
}
function literalIndent(result, node) {
    const source = result.documents.find(document => document.file.id === node.file).file.text;
    const first = source.slice(node.bodyStart, node.end).split(/\r?\n/).find(line => line.trim());
    const indent = first === undefined ? 0 : /^ */.exec(first)[0].length;
    return indent > node.indent ? indent : childIndent(result, node);
}
function scalar(value) {
    if (value === null)
        return 'null';
    if (typeof value === 'string')
        return quoteText(value);
    if (typeof value === 'number' || typeof value === 'boolean')
        return String(value);
    if (isRecord(value) && (typeof value.id === 'string' || typeof value.name === 'string'))
        return (value.file ? quoteText(asString(value.file)) + '::' : '') + quoteText(asString(value.name, asString(value.id)));
    throw Error('Expected scalar value');
}
function quoteCell(text) {
    if (text.includes('\n'))
        throw Error('A quoted table cell cannot contain a line break');
    // A lone CR belongs to literal data, unlike structural names/properties.
    return '"' + text.replaceAll('"', '""') + '"';
}
function textBodyShape(shape) {
    const choices = variants(shape), types = choices.flatMap(choice => typeof choice.type === 'string' ? [choice.type] : choice.type ?? []);
    return types.includes('string') && !types.includes('object') && !types.includes('array') && !choices.some(choice => choice.properties);
}
function serializeList(values, indent, newline, shape) {
    return values.map(value => Array.isArray(value)
        ? value.length ? indent + 'item' + newline + serializeList(value, indent + '    ', newline, variants(shape).find(choice => choice.type === 'array')?.items) : indent + 'item empty list' + newline
        : isRecord(value)
            ? Object.keys(value).length ? indent + 'item' + newline + serializePropertyRecord(value, indent + '    ', newline, key => childShape(shape, key)) : indent + 'item empty record' + newline
            : indent + 'item ' + scalar(value) + newline).join('');
}
function serializePropertyRecord(properties, indent, newline, resolve) {
    return Object.entries(properties).map(([key, value]) => {
        safePath(key);
        const label = key === 'item' || /[\s"']/.test(key) ? quoteText(key) : key;
        const shape = resolve(key);
        if (Array.isArray(value))
            return value.length ? indent + label + newline + serializeList(value, indent + '    ', newline, variants(shape).find(choice => choice.type === 'array')?.items) : indent + label + ' empty list' + newline;
        if (isRecord(value))
            return Object.keys(value).length ? indent + label + newline + serializePropertyRecord(value, indent + '    ', newline, child => childShape(shape, child)) : indent + label + ' empty record' + newline;
        if (typeof value === 'string' && /[\r\n]/.test(value)) {
            if (!textBodyShape(shape))
                throw Error('Multiline text requires an unambiguous registered text-body property');
            return indent + label + newline + value.replace(/\r\n/g, '\n').split('\n').map(line => indent + '    ' + line).join(newline) + newline;
        }
        return indent + label + ' ' + scalar(value) + newline;
    }).join('');
}
export function serializeProperties(properties, indent = '    ', newline = '\n') {
    return serializePropertyRecord(properties, indent, newline, key => ownerShape('definition', properties, key));
}
export function patchProperty(result, target, path, value) {
    safePath(path);
    let node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    if (node.generated)
        throw Error('Generated content must be edited through its owning recipe, table or template');
    if (node.kind === 'notes' && (path === 'text' || path === 'content.text') && typeof value === 'string')
        return replaceNoteBody(result, target, value);
    if (path === 'notes' && node.children.some(child => child.kind === 'notes'))
        throw Error('Edit raw notes through their individual note identities');
    if (path === 'name' && typeof value === 'string')
        return renameDeclaration(result, target, value);
    if (path === 'draft.text' && typeof value === 'string')
        return replaceDraftBody(result, target, value, asString(asRecord(findRecord(result.normalized, target)?.draft).format, 'text'));
    if (node.implicit) {
        const occurrence = findRecord(result.normalized, target);
        const relationDisplay = ['label', 'legend'].includes(path.split('.')[0]) && resolveReference(result.normalized, target.file, occurrence?.target)?.record.category === 'relation';
        if (!['position', 'size', 'body', 'columns', 'pinned'].includes(path.split('.')[0]) && !relationDisplay)
            throw Error('An implicit occurrence supports only unambiguous appearance properties; author an explicit use occurrence for this property');
        const declaration = allNodes(result).find(n => !n.implicit && n.start === node.start && n.file === node.file);
        if (!declaration)
            throw Error('Implicit occurrence source is unavailable');
        node = declaration;
    }
    const document = result.documents.find(d => d.file.id === target.file);
    const entry = listRecords(result.normalized).find(record => record.ref.file === target.file && record.ref.id === target.id);
    const owner = entry?.kind === 'view' ? entry.record.kind === 'document' ? 'document' : 'view_definition' : { data: 'data_record', source: 'source_record', template: 'template_record' }[entry?.kind ?? ''] ?? entry?.kind ?? 'definition';
    const shape = ownerShape(owner, entry?.record ?? {}, path);
    const serializeValue = (key, value, indent) => serializePropertyRecord({ [key]: value }, indent, document.newline, () => shape);
    if (path === 'title' && node.titleStart !== undefined && node.titleEnd !== undefined)
        return [patch(result, target.file, node.titleStart, node.titleEnd, value === undefined ? '' : ': ' + scalar(value))];
    const properties = allNodes(result).filter(n => n.kind === 'property' && n.owner?.file === target.file && n.owner.id === target.id && (n.path === path || n.path?.startsWith(path + '.')));
    if (value === undefined) {
        // A parent reset covers both a nested block and separately authored
        // dotted leaves. Remove outer ranges once, never overlapping patches.
        let coveredThrough = -1;
        const ranges = properties.sort((a, b) => a.start - b.start || b.end - a.end).filter(property => {
            if (property.end <= coveredThrough)
                return false;
            coveredThrough = property.end;
            return true;
        });
        return ranges.map(property => patch(result, target.file, property.start, property.end, ''));
    }
    const property = properties.find(n => n.path === path);
    if (property) {
        const key = property.path.split('.').at(-1);
        const rawKey = document.file.text.slice(property.start, property.valueStart).trim();
        const authoredKey = words(rawKey)[0] ? decodeText(words(rawKey)[0].raw) : key;
        return [patch(result, target.file, property.start, property.end, serializeValue(authoredKey, value, ' '.repeat(property.indent)))];
    }
    const withNode = node.children.find(n => n.kind === 'with');
    const withIndent = withNode?.indent ?? childIndent(result, node);
    const propertyIndent = withNode ? childIndent(result, withNode) : withIndent + (withIndent - node.indent);
    const at = withNode?.end ?? node.end;
    const indent = ' '.repeat(propertyIndent);
    const previous = document.file.text.slice(0, at);
    const text = (previous && !previous.endsWith('\n') ? document.newline : '') + (withNode ? '' : ' '.repeat(withIndent) + 'with' + document.newline) + serializeValue(path, value, indent);
    return [patch(result, target.file, at, at, text)];
}
export function deleteDeclaration(result, target) {
    const node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    if (node.generated || node.implicit)
        throw Error('Generated or implicit content must be edited through its owning source declaration');
    const document = result.documents.find(d => d.file.id === target.file);
    return [patch(result, target.file, node.start === 0 && document.bom ? 1 : node.start, node.end, '')];
}
export function renameDeclaration(result, target, name) {
    name = name.normalize('NFC');
    if (!name.trim())
        throw Error('Name must not be empty');
    if (listRecords(result.normalized).some(x => x.file === target.file && x.record.name === name && x.ref.id !== target.id))
        throw Error('Duplicate declared name');
    const node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    const changes = [];
    if (node.nameStart !== undefined && node.nameEnd !== undefined)
        changes.push(patch(result, target.file, node.nameStart, node.nameEnd, (node.nameStart === node.nameEnd ? quoteText(name) + ' ' : quoteText(name))));
    else {
        const doc = result.documents.find(d => d.file.id === target.file);
        const text = ' '.repeat(node.indent + 4) + 'with' + doc.newline + ' '.repeat(node.indent + 8) + 'name ' + quoteText(name) + doc.newline;
        changes.push(patch(result, target.file, node.end, node.end, text));
    }
    for (const site of result.references)
        if (site.target?.file === target.file && site.target.id === target.id && site.kind === 'reference') {
            if (site.spelling === 'id')
                continue;
            if (site.spelling === 'cell') {
                const source = result.documents.find(d => d.file.id === site.file).file.text;
                const value = decodeText(source.slice(site.start, site.end));
                const at = site.reference.file === site.file ? -1 : value.lastIndexOf('::');
                changes.push(patch(result, site.file, site.start, site.end, quoteText((at < 0 ? '' : value.slice(0, at + 2)) + name)));
                continue;
            }
            const source = result.documents.find(d => d.file.id === site.file).file.text;
            const raw = source.slice(site.start, site.end), last = splitDelimited(raw, '::').at(-1);
            const lead = /^\s*/.exec(last)[0].length, trail = /\s*$/.exec(last)[0].length;
            changes.push(patch(result, site.file, site.end - last.length + lead, site.end - trail, quoteText(name)));
        }
    return changes;
}
export function appendDeclaration(result, file, text, parent) {
    const doc = result.documents.find(d => d.file.id === file);
    if (!doc)
        throw Error('Source is unavailable');
    const node = parent ? findNode(result, parent) : undefined;
    if (parent && !node)
        throw Error('Parent source is unavailable');
    const at = node?.end ?? doc.file.text.length;
    if (node && (node.generated || node.implicit || node.file !== file))
        throw Error('Parent must be an authored declaration in the selected file');
    const indent = ' '.repeat(node ? childIndent(result, node) : 0);
    const body = text.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n').map(line => indent + line).join(doc.newline) + doc.newline;
    return [patch(result, file, at, at, (at && !doc.file.text.slice(0, at).endsWith('\n') ? doc.newline : '') + body)];
}
export function encodeDefinition(record) {
    const role = asString(record.role, 'object'), name = typeof record.name === 'string' ? ' ' + quoteText(record.name) : '';
    const header = 'element' + name + ' as ' + quoteText(role) + (typeof record.title === 'string' ? ' : ' + quoteText(record.title) : '');
    const properties = { ...record };
    delete properties.name;
    delete properties.role;
    delete properties.title;
    delete properties.category;
    return header + (Object.keys(properties).length ? '\n    with\n' + serializePropertyRecord(properties, '        ', '\n', key => ownerShape('definition', record, key)) : '\n');
}
export function sourceText(result, target) { return findNode(result, target)?.raw; }
/** Named datasets use the same typed property notation as other declarations. */
export function replaceRecordData(result, target, columns, rows) {
    const node = findNode(result, target), record = findRecord(result.normalized, target);
    if (!node || node.kind !== 'data' || !record)
        throw Error('Named dataset source is unavailable');
    if (record.source)
        throw Error('A provider-bound dataset must be edited through its provider');
    const document = result.documents.find(d => d.file.id === target.file);
    // Retain declaration identity, metadata and comments when moving compact rows to
    // typed rows. No other declaration's bytes or source spans are changed.
    const properties = { ...record, columns: columns, rows: rows };
    delete properties.name;
    const comments = document.file.text.slice(node.bodyStart, node.end).split(/\r?\n/).filter(line => line.trimStart().startsWith('//'));
    const indent = ' '.repeat(node.indent + 4);
    const text = (comments.length ? comments.join(document.newline) + document.newline : '') + indent + 'with' + document.newline + serializePropertyRecord(properties, indent + '    ', document.newline, key => ownerShape('data_record', record, key));
    return [patch(result, target.file, node.bodyStart, node.end, text)];
}
/** Replace only authored table input, retaining any original free-form draft. */
export function replaceDataBody(result, target, data) {
    const node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    const doc = result.documents.find(d => d.file.id === target.file);
    if (node.kind !== 'element')
        throw Error('Table body belongs to an element declaration');
    const supported = new Set(['id', 'alignment', 'percentage', 'min_chars', 'max_lines']);
    for (const row of data.rows)
        if (row.length > data.columns.length)
            throw Error('More cells than declared columns');
    const compact = data.columns.length > 0 && data.columns.every(c => Object.keys(c).every(k => supported.has(k))) && data.rows.every(row => row.every(cell => cell === null || typeof cell === 'string') && (data.columns.length > 1 || row.some(cell => cell !== null)));
    const old = node.children.filter(n => n.kind === 'data' || n.kind === 'fields' || n.kind === 'field-row');
    if (!compact) {
        // Typed rows retain otherwise unrepresentable values, including a one-column null row.
        const value = { columns: data.columns, rows: data.rows };
        return [...old.map(n => patch(result, target.file, n.start, n.end, '')), ...patchProperty(result, target, 'data', value)];
    }
    const depth = old[0]?.indent ?? childIndent(result, node);
    const indent = ' '.repeat(depth), rowIndent = ' '.repeat(old[0] && old[0].kind !== 'field-row' ? literalIndent(result, old[0]) : depth + (depth - node.indent));
    const header = data.columns.map(c => {
        const parts = [quoteText(asString(c.id))];
        const values = [c.alignment, c.percentage, c.min_chars, c.max_lines];
        let last = values.length - 1;
        while (last >= 0 && values[last] === undefined)
            last--;
        for (let i = 0; i <= last; i++)
            parts.push(values[i] === undefined ? '' : typeof values[i] === 'number' && String(values[i]).includes('.') ? quoteText(String(values[i])) : String(values[i]));
        return parts.join(':');
    }).join('.');
    const text = indent + 'data' + doc.newline + rowIndent + header + doc.newline + data.rows.map(row => rowIndent + Array.from({ length: data.columns.length }, (_, i) => row[i] === undefined || row[i] === null ? '' : quoteCell(row[i])).join('.') + doc.newline).join('');
    const cleanup = patchProperty(result, target, 'data', undefined);
    if (old.length)
        return [...cleanup, ...old.map((n, i) => patch(result, target.file, n.start, n.end, i === 0 ? text : ''))];
    const prefix = node.end && !doc.file.text.slice(0, node.end).endsWith('\n') ? doc.newline : '';
    return [...cleanup, patch(result, target.file, node.end, node.end, prefix + text)];
}
export function replaceDraftBody(result, target, text, format = 'text') {
    const node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    const doc = result.documents.find(d => d.file.id === target.file);
    const old = node.children.find(n => n.kind === 'draft');
    const depth = old?.indent ?? childIndent(result, node), indent = ' '.repeat(depth);
    const bodyIndent = ' '.repeat(old ? literalIndent(result, old) : depth + (depth - node.indent));
    const raw = indent + 'draft' + (format === 'text' ? '' : ' ' + format) + doc.newline + text.replace(/\r\n/g, '\n').split('\n').map(line => bodyIndent + line).join(doc.newline) + doc.newline;
    return [patch(result, target.file, old?.start ?? node.end, old?.end ?? node.end, (!old && node.end && !doc.file.text.slice(0, node.end).endsWith('\n') ? doc.newline : '') + raw)];
}
/** Edit a raw note body without replacing its header, stable identity or siblings. */
export function replaceNoteBody(result, target, text) {
    const node = findNode(result, target);
    if (!node || node.kind !== 'notes' || node.generated)
        throw Error('Raw note source is unavailable');
    const doc = result.documents.find(d => d.file.id === target.file);
    const indent = ' '.repeat(literalIndent(result, node));
    const prefix = node.bodyStart && !doc.file.text.slice(0, node.bodyStart).endsWith('\n') ? doc.newline : '';
    const body = text.replace(/\r\n/g, '\n').split('\n').map(line => indent + line).join(doc.newline) + doc.newline;
    return [patch(result, target.file, node.bodyStart, node.end, prefix + body)];
}
//# sourceMappingURL=index.js.map