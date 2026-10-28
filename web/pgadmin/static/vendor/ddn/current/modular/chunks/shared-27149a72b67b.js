/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-27149a72b67b","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":["shared-da593b1d80b5"],"modules":[{"id":"defaults/src/index.js","bytes":36886,"sha256":"14acd964f86cad4cbcf930b48e97c24dd0cf25e022b52aed632ab6200979918e","dependencies":["profiles/src/schema-core.js","profiles/src/core.js","profiles/src/view-surfaces.js","defaults/src/method-names.js"]},{"id":"defaults/src/method-names.js","bytes":708,"sha256":"ae651ed9a4cf426dbc6577a4a8824efbd2a45ee90e172d2a59466f419e96585a","dependencies":[]},{"id":"execution/src/compute.js","bytes":3539,"sha256":"77700d3fb5bd5ddc261864f5ccd456630d1a00a2b56cfc9642d969a8435b85f5","dependencies":["language/src/index.js","verifier/src/index.js","execution/src/index.js"]},{"id":"execution/src/index.js","bytes":10957,"sha256":"15ecd00834ea6e1403abaacf606aaf98894b4b4640d4565afe143bf95f5cd4cc","dependencies":[]},{"id":"language/src/index.js","bytes":122870,"sha256":"5c6fe8eb773feaf99d792b8ec78d9553dc1867ffb5f9ca80762804b2866020cf","dependencies":["model/src/index.js","language/src/schema.js"]},{"id":"language/src/schema.js","bytes":1572,"sha256":"edc9dfd9697f21ec59d860804243265333142daeae550ea4500d43545e91135a","dependencies":["profiles/src/schema-core.js"]},{"id":"model/src/index.js","bytes":7704,"sha256":"ef309bcf235d6d10ec6c21c889c43882ecbb36956a62c56c93ba16c68f3bda7d","dependencies":[]},{"id":"profiles/src/view-surfaces.js","bytes":1426,"sha256":"c31c88b49fc8263b9e98dd49fafa9266bfc2ce7d06f7eee2833eb1c3a828b296","dependencies":[]},{"id":"verifier/src/index.js","bytes":69282,"sha256":"3709c98b354ba804a89aee63e2257d9f278f9b65403b945bb6408aee8b101368","dependencies":["language/src/index.js","execution/src/index.js","model/src/index.js","profiles/src/core.js","profiles/src/schema-core.js","defaults/src/index.js"]}],"hash":"9097d25ebdbbff04888d374027330b0778a324d2a8cf548e2d1b3961b314281c"},{"defaults/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.previewPaths = void 0;
exports.validateProperty = validateProperty;
exports.resolve = resolve;
exports.resolveProperties = resolveProperties;
exports.validatePreview = validatePreview;
exports.createDefaultsResolver = createDefaultsResolver;
exports.allocateColumnPercentages = allocateColumnPercentages;
exports.parseStylesheet = parseStylesheet;
const schema_core_js_1 = require("profiles/src/schema-core.js");
const core_js_1 = require("profiles/src/core.js");
const view_surfaces_js_1 = require("profiles/src/view-surfaces.js");
const method_names_js_1 = require("defaults/src/method-names.js");
const aliases = { element: 'definition', relation: 'definition', view: 'view_definition' };
const schemas = { data: 'data_record', source: 'source_record', asset: 'asset_record', template: 'template_record', publication: 'publication', file: 'file' };
const copy = (v) => JSON.parse(JSON.stringify(v));
const own = (v, k) => Object.prototype.hasOwnProperty.call(v, k);
const viewThemes = new WeakMap();
const snapshotRecords = new WeakMap();
function deeplyFrozen(value, seen = new Set()) {
    if (!value || typeof value !== 'object' || seen.has(value))
        return true;
    if (!Object.isFrozen(value) || ![Object.prototype, Array.prototype, null].includes(Object.getPrototypeOf(value)))
        return false;
    seen.add(value);
    return Object.values(Object.getOwnPropertyDescriptors(value)).every(field => 'value' in field && deeplyFrozen(field.value, seen));
}
function recordsFor(snapshot) {
    const cached = snapshotRecords.get(snapshot);
    if (cached)
        return cached;
    const records = (0, core_js_1.indexRecords)(snapshot.normalized), files = (0, core_js_1.bundleFiles)(snapshot.normalized);
    const ids = new Map(), names = new Map();
    for (const record of records) {
        const id = record.file + '\0' + record.ref.id, found = ids.get(id);
        if (found)
            found.push(record);
        else
            ids.set(id, [record]);
        if (typeof record.record.name === 'string') {
            const key = record.file + '\0' + record.record.name, rows = names.get(key);
            if (rows)
                rows.push(record);
            else
                names.set(key, [record]);
        }
    }
    const result = { records, files, resolve(file, reference) {
            if (!(0, schema_core_js_1.isRecord)(reference))
                return undefined;
            const targetFile = typeof reference.file === 'string' ? reference.file : file;
            const id = typeof reference.id === 'string', name = typeof reference.name === 'string';
            const candidates = id ? ids.get(targetFile + '\0' + reference.id) : name ? names.get(targetFile + '\0' + reference.name) : undefined;
            const matches = id && name ? candidates?.filter(row => row.record.name === reference.name) : candidates;
            return matches?.length === 1 ? matches[0] : undefined;
        } };
    const normalized = Object.getOwnPropertyDescriptor(snapshot, 'normalized');
    if (Object.isFrozen(snapshot) && normalized && 'value' in normalized && deeplyFrozen(normalized.value))
        snapshotRecords.set(snapshot, result);
    return result;
}
const themePaint = {
    base: { background: '#ffffff', surface: '#ffffff', ink: '#17263d', rule: '#d8e1eb', accent: '#244cb4' },
    neutral: { background: '#ffffff', surface: '#ffffff', ink: '#222222', rule: '#bbbbbb', accent: '#303030' },
    dark: { background: '#202c3e', surface: '#2a3a50', ink: '#edf3fc', rule: '#7389a5', accent: '#abcbff' },
    night: { background: '#2d3b50', surface: '#394b63', ink: '#f1f5fc', rule: '#93a8c1', accent: '#c3daff' },
    forest: { background: '#f2f6ef', surface: '#fbfdf9', ink: '#20342b', rule: '#d6e0d0', accent: '#375a42' },
};
const defs = new Map();
for (const p of schema_core_js_1.codex.properties) {
    const list = defs.get(p.owner) ?? [];
    list.push(p);
    defs.set(p.owner, list);
}
function merge(target, value, origin, origins, prefix = '') {
    for (const [key, v] of Object.entries(value)) {
        if (['__proto__', 'prototype', 'constructor'].includes(key))
            continue;
        const path = prefix ? prefix + '.' + key : key;
        if ((0, schema_core_js_1.isRecord)(v)) {
            if (!leaves(v).length)
                continue;
            if (!(0, schema_core_js_1.isRecord)(target[key]))
                target[key] = {};
            merge(target[key], v, origin, origins, path);
        }
        else {
            target[key] = copy(v);
            origins.set(path, origin);
        }
    }
}
function leaves(value, prefix = '') {
    return Object.entries(value).flatMap(([key, v]) => {
        const path = prefix ? prefix + '.' + key : key;
        return (0, schema_core_js_1.isRecord)(v) ? leaves(v, path) : [[path, v]];
    });
}
function definition(owner, path) { return defs.get(owner)?.find(p => path === p.path) ?? defs.get(owner)?.find(p => path.startsWith(p.path + '.')); }
function canonicalOwner(owner) { return aliases[owner] ?? owner; }
function validateProperty(owner, path, value, context = {}) {
    owner = canonicalOwner(owner);
    if (!path || path.split('.').some(k => ['__proto__', 'constructor', 'prototype'].includes(k)))
        return [{ code: 'DDN-PROPERTY-PATH', severity: 'error', message: 'Invalid property path' }];
    const property = definition(owner, path);
    if (property && !property.settable)
        return [{ code: 'DDN-PROPERTY-READONLY', severity: 'error', message: `${owner}.${path} is not author-settable` }];
    const record = {};
    (0, schema_core_js_1.setPath)(record, path, value);
    if (context.role && owner === 'definition')
        record.role = context.role;
    if (context.profile && (owner === 'view_definition' || owner === 'document'))
        record.profile = context.profile;
    if (context.category && owner === 'definition')
        record.category = context.category;
    const role = owner === 'definition' && context.role ? (0, core_js_1.roleDescriptor)(context.role, context.category) : undefined;
    const coreType = owner === 'definition' && context.role ? (0, core_js_1.coreTypeDescriptor)(context.role, context.category) : undefined;
    const payload = context.category === 'relation' ? 'qualifiers' : 'content';
    if (coreType && (path === payload || path.startsWith(payload + '.'))) {
        const relative = '/' + path.slice(payload.length + 1).replaceAll('.', '/');
        return (0, schema_core_js_1.validateSchema)(coreType.schema, record[payload] ?? {}).filter(issue => issue.keyword !== 'required' || issue.path.startsWith(relative)).map(issue => ({ code: 'DDN-PROPERTY-' + issue.keyword.toUpperCase(), severity: 'error', message: `${owner}.${path}: ${issue.message}` }));
    }
    const roleSchema = ['content', 'metadata', 'properties', 'qualifiers'].includes(path.split('.')[0]) ? role?.schema ?? (coreType ? (schemas[owner] ?? owner) : undefined) : undefined;
    const issues = roleSchema !== undefined ? (0, schema_core_js_1.validateSchema)(roleSchema, record).filter(issue => issue.keyword !== 'required' || issue.path.startsWith('/' + path.replaceAll('.', '/'))) : property && path === property.path ? (0, schema_core_js_1.validateSchema)(property.schema, value) : (0, schema_core_js_1.validateSchema)(schemas[owner] ?? owner, record).filter(issue => issue.keyword !== 'required' || issue.path.startsWith('/' + path.replaceAll('.', '/')));
    return issues.map(issue => ({ code: 'DDN-PROPERTY-' + issue.keyword.toUpperCase(), severity: 'error', message: `${owner}.${path}: ${issue.message}` }));
}
function matches(selector, record, owner, context) {
    if (selector.owner && canonicalOwner(selector.owner) !== owner && !(owner === 'appearance' && context.definition && canonicalOwner(selector.owner) === 'definition'))
        return false;
    if (selector.owner === 'element' && context.category === 'relation')
        return false;
    if (selector.owner === 'relation' && context.category !== 'relation')
        return false;
    const candidates = { file: context.file, method: context.method, profile: context.profile, catalogue: context.catalogue, subtype: context.subtype, category: context.category, role: context.role ?? record.role, id: record.id };
    if (Array.isArray(selector.subtype)) {
        const lineage = Array.isArray(context.subtype) ? context.subtype : context.subtype === undefined ? [] : [context.subtype];
        if (!selector.subtype.every((part, index) => lineage[index] === part))
            return false;
    }
    for (const key of ['file', 'method', 'profile', 'catalogue', 'subtype', 'category', 'role', 'id'])
        if (key === 'subtype' && Array.isArray(selector.subtype))
            continue;
        else if (selector[key] !== undefined && (Array.isArray(candidates[key]) ? !candidates[key].includes(selector[key]) : selector[key] !== candidates[key]))
            return false;
    const classes = (0, schema_core_js_1.getPath)(record, 'style.classes');
    return !selector.classes || selector.classes.every(c => Array.isArray(classes) && classes.includes(c));
}
function ruleDeclarations(rule) {
    return Object.entries(rule.declarations).flatMap(([path, value]) => (0, schema_core_js_1.isRecord)(value) ? leaves(value, path) : [[path, value]]);
}
function specificity(rule) {
    if (rule.specificityTuple)
        return rule.specificityTuple;
    if (rule.specificity === undefined) {
        const attributes = ['owner', 'category', 'file', 'method', 'profile', 'catalogue', 'subtype', 'role'];
        return [rule.selector.id === undefined ? 0 : 1, (rule.selector.classes?.length ?? 0) + attributes.filter(key => rule.selector[key] !== undefined).length, 0];
    }
    const score = rule.specificity;
    return [Math.floor(score / 100), Math.floor((score % 100) / 10), score % 10];
}
function resolve(record, owner, context = {}) {
    owner = canonicalOwner(owner);
    context = { ...context, ...(context.role ? {} : typeof record.role === 'string' ? { role: record.role } : {}), category: context.category ?? (typeof record.category === 'string' ? record.category : 'element') };
    const values = {}, origins = new Map(), diagnostics = [];
    const set = (path, value, origin) => {
        (0, schema_core_js_1.setPath)(values, path, copy(value));
        for (const [p] of (0, schema_core_js_1.isRecord)(value) ? leaves(value, path) : [[path, value]])
            origins.set(p, origin);
    };
    for (const p of defs.get(owner) ?? [])
        if (p.default.kind === 'literal' && p.default.value !== undefined && !(p.path.startsWith('draft.') && record.draft === undefined))
            set(p.path, p.default.value, 'standard:' + owner);
    const role = context.role ? (0, core_js_1.roleDescriptor)(context.role, context.category) : undefined;
    const coreType = context.role ? (0, core_js_1.coreTypeDescriptor)(context.role, context.category) : undefined;
    const render = role?.render ?? (coreType ? (0, core_js_1.coreDescriptor)(coreType.core)?.render : undefined);
    if (render && owner === 'appearance') {
        for (const [path, key] of [['symbol.color', 'colour'], ['symbol.fill', 'fill'], ['symbol.width', 'width']]) {
            const value = render[key] ?? (key === 'colour' ? render.stroke : undefined);
            if (value !== undefined)
                set(path, value, 'standard:role ' + context.role);
        }
    }
    const profile = context.profile ? (0, core_js_1.getProfile)(context.profile) : undefined;
    if (profile) {
        if (owner === 'view_definition')
            for (const [path, value] of Object.entries(profile.standard_overrides)) {
                const canonical = path.startsWith('projection.') && !['projection.kind', 'projection.profile'].includes(path) && !path.startsWith('projection.options.') ? 'projection.options.' + path.slice(11) : path;
                if (canonical !== 'projection.kind' && canonical !== 'projection.profile' && definition(owner, canonical)) {
                    const rule = profile.defaults[canonical];
                    if (rule?.kind === 'derived') {
                        if (rule.authored_default !== undefined)
                            set(canonical, rule.authored_default, 'standard:profile ' + profile.id);
                    }
                    else
                        set(canonical, value, 'standard:profile ' + profile.id);
                }
            }
        if (owner === 'definition') {
            const role = context.role ?? '';
            const metadataDefaults = [
                ['petri.tokens', 'metadata.x_petri.tokens', role === 'petri.place'],
                ['petri.weight', 'metadata.x_petri.weight', ['petri.arc', 'petri.testarc'].includes(role)],
                ['contact.form', 'metadata.x_contact.form', role === 'ladder.contact'],
                ['coil.mode', 'metadata.x_coil.mode', role === 'ladder.coil'],
                ['compatibility.mode', 'metadata.x_compatibility.mode', context.category === 'relation' && role.startsWith('soaml.')],
            ];
            for (const [key, path, applies] of metadataDefaults) {
                const value = profile.standard_overrides[key];
                if (applies && value !== undefined)
                    set(path, value, 'standard:profile ' + profile.id);
            }
        }
        for (const [path, d] of Object.entries(profile.defaults))
            if (d.kind === 'literal' && d.value !== undefined) {
                if (path.startsWith(owner + '.'))
                    set(path.slice(owner.length + 1), d.value, 'standard:profile ' + profile.id);
                else if (owner === 'view_definition' && definition(owner, path))
                    set(path, d.value, 'standard:profile ' + profile.id);
            }
    }
    if (owner === 'appearance' && context.definition) {
        if (context.definition.data)
            set('body', 'columns', 'standard:content');
        else if ((0, schema_core_js_1.getPath)(context.definition, 'draft.text'))
            set('body', 'draft', 'standard:content');
    }
    if (owner === 'workarea' && !own(record, 'allow_foreign_views'))
        set('allow_foreign_views', (record.method ?? context.method ?? 'ddn') === 'ddn', 'standard:context');
    if (owner === 'source' && !own(record, 'refresh'))
        set('refresh', record.mode === 'host' ? 'supplied' : 'manual', 'standard:context');
    const surface = (0, view_surfaces_js_1.getViewSurfacePreset)(owner === 'view_definition' ? (0, schema_core_js_1.getPath)(record, 'surface.preset') : context.surfacePreset);
    if (surface && surface.id !== 'dynamic') {
        const origin = 'standard:surface ' + surface.id;
        if (['view_definition', 'definition', 'appearance'].includes(owner)) {
            set('style.font', context.surfaceTypography?.font ?? 'sans', origin);
            set('style.font_size', context.surfaceTypography?.fontSize ?? 24, origin);
            set('style.theme', 'neutral', origin);
        }
        if (owner === 'view_definition') {
            set('surface.width', surface.width, origin);
            set('surface.height', surface.height, origin);
            set('surface.scale', surface.scale, origin);
            set('background.color', '#ffffff', origin);
            set('text.color', '#222222', origin);
            set('chrome.banner', false, origin);
            set('chrome.footer', false, origin);
            set('chrome.title', true, origin);
        }
    }
    const apply = (rule, origin, css) => {
        if (!matches(rule.selector, record, owner, context))
            return;
        for (const [path, value] of ruleDeclarations(rule)) {
            const p = definition(owner, path);
            if (!p || !p.defaultable || (css && !p.css)) {
                diagnostics.push({ code: 'DDN-DEFAULT-INELIGIBLE', severity: 'error', message: `${origin} cannot set ${owner}.${path}` });
                continue;
            }
            const errors = validateProperty(owner, path, value, context);
            diagnostics.push(...errors);
            set(path, value, origin);
        }
    };
    const css = (context.styles ?? []).flatMap((rule, order) => ruleDeclarations(rule).map(([path, value]) => ({
        rule: { ...rule, declarations: { [path]: value } },
        important: rule.important?.some(p => path === p || path.startsWith(p + '.')) ? 1 : 0,
        specificity: specificity(rule), order,
    }))).sort((a, b) => a.important - b.important || a.specificity[0] - b.specificity[0] || a.specificity[1] - b.specificity[1] || a.specificity[2] - b.specificity[2] || a.order - b.order);
    for (const { rule } of css)
        apply(rule, 'css', true);
    for (const [rules, origin] of [[context.fileDefaults, 'file:defaults'], [context.workareaDefaults, 'file:workarea defaults'], [context.viewDefaults, 'file:view defaults']])
        for (const rule of [...(rules ?? [])].sort((a, b) => Number(!!(a.selector.role || a.selector.profile)) - Number(!!(b.selector.role || b.selector.profile)) || Object.keys(a.selector).filter(k => !['owner', 'category'].includes(k)).length - Object.keys(b.selector).filter(k => !['owner', 'category'].includes(k)).length))
            apply(rule, origin, false);
    if (context.definition && (owner === 'appearance' || owner === 'view_placement')) {
        if (owner === 'appearance')
            for (const rule of rules(context.definition.defaults))
                apply(rule, 'file:definition defaults', false);
        const inherited = {};
        for (const p of defs.get(owner) ?? []) {
            if (!p.defaultable)
                continue;
            const v = (0, schema_core_js_1.getPath)(context.definition, p.path);
            if (v !== undefined)
                (0, schema_core_js_1.setPath)(inherited, p.path, v);
        }
        merge(values, inherited, 'file:definition', origins);
    }
    merge(values, record, owner === 'appearance' || owner === 'view_placement' ? 'file:occurrence' : 'file:definition', origins);
    const theme = String(origins.get('style.theme')?.startsWith('file:') || origins.get('style.theme') === 'css' ? (0, schema_core_js_1.getPath)(values, 'style.theme') : context.theme ?? (0, schema_core_js_1.getPath)(values, 'style.theme'));
    const paint = themePaint[theme];
    if (paint && ['definition', 'appearance', 'view_definition', 'workarea'].includes(owner)) {
        for (const [path, value] of Object.entries({ 'background.color': owner === 'view_definition' || owner === 'workarea' ? paint.background : paint.surface, 'text.color': paint.ink, 'border.color': paint.rule, 'symbol.color': paint.accent, 'symbol.fill': paint.surface, 'stroke.color': paint.accent })) {
            if (!origins.has(path) || origins.get(path)?.startsWith('standard:'))
                set(path, value, 'standard:theme ' + theme);
        }
    }
    if (['note', 'pad'].includes(String((0, schema_core_js_1.getPath)(values, 'style.paper'))) && ['definition', 'appearance', 'view_definition', 'view_placement', 'document'].includes(owner)) {
        const origin = origins.get('background.color');
        if (!origin || origin.startsWith('standard:'))
            set('background.color', '#fff59d', 'standard:paper');
    }
    if (owner === 'view_definition' && profile?.projection === 'chart') {
        const transform = (0, schema_core_js_1.getPath)(values, 'projection.options.transform');
        if (['histogram', 'pareto', 'waterfall', 'boxplot'].includes(String(transform))) {
            const options = (0, schema_core_js_1.getPath)(values, 'projection.options');
            for (const name of ['aggregate', 'arrangement', 'series_missing', 'series', 'layers']) {
                const path = 'projection.options.' + name;
                if (origins.get(path)?.startsWith('standard:')) {
                    delete options[name];
                    origins.delete(path);
                }
            }
            if (origins.get('projection.options.mark')?.startsWith('standard:'))
                set('projection.options.mark', transform === 'boxplot' ? 'boxplot' : 'bar', 'standard:transform');
        }
    }
    for (const p of defs.get(owner) ?? []) {
        const value = (0, schema_core_js_1.getPath)(record, p.path);
        if (value !== undefined)
            diagnostics.push(...validateProperty(owner, p.path, value, context));
    }
    if (owner === 'view_definition') {
        const width = (0, schema_core_js_1.getPath)(values, 'surface.width'), height = (0, schema_core_js_1.getPath)(values, 'surface.height');
        if ((width === null) !== (height === null))
            diagnostics.push({ code: 'DDN-SURFACE-SIZE', severity: 'error', message: 'Fixed view surfaces require both width and height; dynamic surfaces use null for both.' });
        if (typeof width === 'number' && typeof height === 'number') {
            const inset = Number((0, schema_core_js_1.getPath)(values, 'surface.padding')) * Number((0, schema_core_js_1.getPath)(values, 'surface.scale')) * 2;
            if (inset >= Math.min(width, height))
                diagnostics.push({ code: 'DDN-SURFACE-PADDING', severity: 'error', message: 'Surface padding must leave a positive drawable width and height.' });
        }
    }
    return { values, properties: leaves(values).map(([path, value]) => ({ path, value, origin: origins.get(path) ?? 'file' })), diagnostics };
}
function rules(v) { return Array.isArray(v) ? v.filter(schema_core_js_1.isRecord).filter(x => (0, schema_core_js_1.isRecord)(x.selector) && (0, schema_core_js_1.isRecord)(x.declarations)) : []; }
function resolveProperties(snapshot, target, context = {}) {
    const index = recordsFor(snapshot);
    const resolveRecord = (_records, file, reference) => index.resolve(file, reference);
    const records = index.records;
    let item = resolveRecord(records, target.file, target);
    if (!item)
        return { values: {}, properties: [], diagnostics: [{ code: 'DDN-REFERENCE', severity: 'error', message: 'Target does not resolve', target }] };
    const occurrence = context.appearance ? resolveRecord(records, context.appearance.file, context.appearance) : item.owner === 'appearance' ? item : undefined;
    const placement = !occurrence && item.owner === 'view_placement' ? item : undefined;
    const definitionRecord = occurrence ? resolveRecord(records, occurrence.file, occurrence.record.target) : placement ? resolveRecord(records, placement.file, placement.record.target) : item.owner === 'definition' ? item : undefined;
    const view = context.view ? resolveRecord(records, context.view.file, context.view) : occurrence ? resolveRecord(records, occurrence.file, occurrence.record.parent) : placement ? definitionRecord : item.owner === 'view_definition' || item.owner === 'document' ? item : undefined;
    if (occurrence)
        item = occurrence;
    const files = index.files;
    const root = files.find(f => f.location === snapshot.rootFile)?.document;
    const file = files.find(f => f.location === (definitionRecord?.file ?? item.file))?.document;
    const wa = (0, schema_core_js_1.isRecord)(root?.workarea) ? root.workarea : undefined;
    const styleRules = [...(context.styles ?? [])];
    const typedRules = (provider, kind) => {
        if (provider?.owner !== 'definition' || provider.record.role !== 'core::Style' || provider.record.category === 'relation')
            return [];
        const content = provider.record.content;
        return (0, schema_core_js_1.isRecord)(content) && content.kind === kind ? rules(content.rules) : [];
    };
    const attached = new Set();
    for (const [provider, fileId] of [[wa, snapshot.rootFile], [view?.record, view?.file], [definitionRecord?.record, definitionRecord?.file], [item.record, item.file]]) {
        if (!provider || !fileId || attached.has(provider))
            continue;
        attached.add(provider);
        const sheets = (0, schema_core_js_1.getPath)(provider, 'style.sheets');
        if (Array.isArray(sheets))
            for (const ref of sheets)
                styleRules.push(...typedRules(resolveRecord(records, fileId, ref), 'css'));
    }
    const providerDiagnostics = [];
    const defaultProviders = (value, fileId) => {
        const result = rules(value);
        if (Array.isArray(value))
            for (const ref of value) {
                if ((0, schema_core_js_1.isRecord)(ref) && (0, schema_core_js_1.isRecord)(ref.selector) && (0, schema_core_js_1.isRecord)(ref.declarations))
                    continue;
                const provider = resolveRecord(records, fileId, ref);
                if (provider?.owner !== 'definition' || provider.record.role !== 'core::Style' || provider.record.category === 'relation' || (0, schema_core_js_1.getPath)(provider.record, 'content.kind') !== 'defaults') {
                    providerDiagnostics.push({ code: 'DDN-DEFAULT-PROVIDER', severity: 'error', message: 'A defaults reference must resolve to a core::Style definition with content.kind defaults' });
                    continue;
                }
                result.push(...typedRules(provider, 'defaults'));
            }
        return result;
    };
    const profile = typeof view?.record.profile === 'string' ? view.record.profile : typeof item.record.profile === 'string' ? item.record.profile : 'ddn@1';
    const method = view ? method_names_js_1.methodNames[(0, core_js_1.getProfile)(profile)?.method ?? ''] : typeof wa?.method === 'string' ? wa.method : 'ddn';
    let theme, surfaceTypography;
    const surfacePreset = (0, schema_core_js_1.getPath)(view?.record, 'surface.preset');
    if (view && item.owner !== 'view_definition' && item.owner !== 'document') {
        let cache = viewThemes.get(snapshot);
        if (!cache) {
            cache = new Map();
            viewThemes.set(snapshot, cache);
        }
        const key = JSON.stringify([view.ref, context.styles ?? []]);
        let settings = cache.get(key);
        if (settings === undefined) {
            const values = resolveProperties(snapshot, view.ref, { styles: context.styles ?? [] }).values;
            const surface = (0, view_surfaces_js_1.getViewSurfacePreset)(surfacePreset);
            settings = { theme: String((0, schema_core_js_1.getPath)(values, 'style.theme') ?? 'default'), ...(surface && surface.id !== 'dynamic' ? { typography: { font: String((0, schema_core_js_1.getPath)(values, 'style.font') ?? 'sans'), fontSize: Number((0, schema_core_js_1.getPath)(values, 'style.font_size') ?? 24) } } : {}) };
            if (cache.size > 512)
                cache.clear();
            cache.set(key, settings);
        }
        theme = settings.theme;
        surfaceTypography = settings.typography;
    }
    const resolved = resolve(item.record, item.owner, { ...(typeof theme === 'string' ? { theme } : {}), ...(typeof surfacePreset === 'string' ? { surfacePreset } : {}), ...(surfaceTypography ? { surfaceTypography } : {}), file: definitionRecord?.file ?? item.file, ...(method ? { method } : {}), profile, ...(typeof view?.record.subtype === 'string' ? { subtype: view.record.subtype } : Array.isArray(view?.record.subtype) ? { subtype: view.record.subtype.filter((x) => typeof x === 'string') } : {}), ...(typeof view?.record.catalogue === 'string' ? { catalogue: view.record.catalogue } : {}), ...(typeof definitionRecord?.record.role === 'string' ? { role: definitionRecord.record.role } : {}), ...(typeof definitionRecord?.record.category === 'string' ? { category: definitionRecord.record.category } : {}), ...(definitionRecord ? { definition: definitionRecord.record } : {}), fileDefaults: rules(file?.defaults), workareaDefaults: defaultProviders(wa?.defaults, snapshot.rootFile), viewDefaults: [...defaultProviders(view?.record.defaults, view?.file ?? item.file), ...rules(view?.record.role_defaults)], styles: styleRules });
    resolved.diagnostics.unshift(...providerDiagnostics);
    return resolved;
}
exports.previewPaths = Object.freeze(['background.color', 'border.color', 'opacity', 'text.color']);
function validatePreview(value) {
    return Object.entries(value).flatMap(([path, v]) => !exports.previewPaths.includes(path) ? [{ code: 'DDN-PREVIEW', severity: 'error', message: `${path} is not a paint-preview property` }] : validateProperty('appearance', path, v));
}
function createDefaultsResolver(options) {
    if (options.defaultsVersion !== 'ddn-next-1')
        throw new Error('Unsupported defaults version ' + options.defaultsVersion);
    return { resolve: (record, owner, context = {}) => resolve(record, owner, { ...context, styles: context.styles ?? options.styles ?? [] }) };
}
function allocateColumnPercentages(percentages) {
    if (percentages.some(p => p != null && (!Number.isFinite(p) || p < 0)))
        throw new RangeError('Column percentages must be finite and nonnegative');
    if (!percentages.length)
        return [];
    const result = percentages.map(p => p ?? 0);
    let sum = result.reduce((a, b) => a + b, 0);
    if (sum > 100) {
        const levels = [...new Set(result)].sort((a, b) => b - a);
        for (let i = 0; i < levels.length && sum > 100; i++) {
            const top = levels[i];
            const next = levels[i + 1] ?? 0;
            const leaders = result.map((v, k) => v >= top ? k : -1).filter(k => k >= 0);
            const reduction = Math.min(top - next, (sum - 100) / leaders.length);
            for (const k of leaders)
                result[k] = result[k] - reduction;
            sum -= reduction * leaders.length;
        }
    }
    const automatic = percentages.map((p, i) => p == null ? i : -1).filter(i => i >= 0);
    if (automatic.length) {
        const share = Math.max(0, 100 - result.reduce((a, b) => a + b, 0)) / automatic.length;
        for (const i of automatic)
            result[i] = share;
    }
    else
        result[result.length - 1] = result.at(-1) + Math.max(0, 100 - result.reduce((a, b) => a + b, 0));
    return result;
}
function parseStylesheet(text) {
    const diagnostics = [];
    const result = [];
    const fail = (message) => diagnostics.push({ code: 'DDN-CSS', severity: 'error', message });
    const escaped = (source, at) => {
        let slashes = 0;
        while (at > 0 && source[--at] === '\\')
            slashes++;
        return slashes % 2 === 1;
    };
    let source = '', commentQuote = '';
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (commentQuote) {
            source += c;
            if (c === commentQuote && !escaped(text, i))
                commentQuote = '';
        }
        else if (c === '"' || c === "'") {
            commentQuote = c;
            source += c;
        }
        else if (c === '/' && text[i + 1] === '*') {
            const end = text.indexOf('*/', i + 2);
            if (end < 0) {
                fail('Unterminated CSS comment');
                break;
            }
            i = end + 1;
        }
        else
            source += c;
    }
    let position = 0;
    while (position < source.length) {
        const open = source.indexOf('{', position);
        if (open < 0) {
            if (source.slice(position).trim())
                fail('Unterminated CSS rule');
            break;
        }
        const header = source.slice(position, open).trim();
        let end = open + 1, depth = 1, quote = '';
        for (; end < source.length && depth; end++) {
            const c = source[end];
            if (quote) {
                if (c === quote && !escaped(source, end))
                    quote = '';
            }
            else if (c === '"' || c === "'")
                quote = c;
            else if (c === '{')
                depth++;
            else if (c === '}')
                depth--;
        }
        if (depth) {
            fail('Unterminated CSS declaration block');
            break;
        }
        position = end;
        if (header.startsWith('@')) {
            fail('CSS at-rules and imports are not available to DDN styles');
            continue;
        }
        const body = source.slice(open + 1, end - 1), declarations = {}, important = [];
        const fragments = [];
        let start = 0;
        quote = '';
        depth = 0;
        for (let i = 0; i <= body.length; i++) {
            const c = body[i];
            if (quote) {
                if (c === quote && !escaped(body, i))
                    quote = '';
            }
            else if (c === '"' || c === "'")
                quote = c;
            else if (c === '[' || c === '{')
                depth++;
            else if (c === ']' || c === '}')
                depth--;
            else if ((c === ';' || c === undefined) && !depth) {
                fragments.push(body.slice(start, i));
                start = i + 1;
            }
        }
        for (const declaration of fragments) {
            if (!declaration.trim())
                continue;
            const colon = declaration.indexOf(':');
            if (colon < 0) {
                fail('CSS declaration needs a colon');
                continue;
            }
            const key = declaration.slice(0, colon).trim();
            const binding = schema_core_js_1.codex.cssMap[key];
            if (!binding) {
                fail('Unregistered CSS custom property ' + key);
                continue;
            }
            let raw = declaration.slice(colon + 1).trim();
            const isImportant = /!important\s*$/i.test(raw);
            if (isImportant) {
                raw = raw.replace(/!important\s*$/i, '').trim();
            }
            let value = raw;
            if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'")))
                value = raw.slice(1, -1).replace(/\\(["'\\])/g, '$1');
            else if (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw))
                value = Number(raw);
            else if (raw === 'true' || raw === 'false' || raw === 'null' || raw.startsWith('[') || raw.startsWith('{')) {
                try {
                    value = JSON.parse(raw);
                }
                catch {
                    fail('Invalid typed CSS value for ' + key);
                    continue;
                }
            }
            if (!isImportant && important.includes(binding.path))
                continue;
            declarations[binding.path] = value;
            if (isImportant && !important.includes(binding.path))
                important.push(binding.path);
        }
        for (const rawSelector of header.split(',')) {
            const selector = {};
            const classes = [];
            let specificity = 0;
            const specificityTuple = [0, 0, 0];
            let rest = rawSelector.trim();
            let invalid = false;
            const tokens = rest.match(/#[\w-]+|\.[\w@.-]+|\[[^\]]+\]|[^\s]+/g) ?? [];
            rest = rest.replace(/\[([\w-]+)\s*=\s*(["']?)([^"'\]]+)\2\]/g, (_whole, key, _q, value) => {
                const name = key.replace(/^data-ddn-/, '');
                if (['owner', 'method', 'profile', 'subtype', 'role', 'category', 'id', 'file', 'catalogue'].includes(name)) {
                    selector[name] = value.trim();
                    specificity += 10;
                    specificityTuple[1]++;
                }
                else {
                    fail('Unsupported CSS selector attribute ' + key);
                    invalid = true;
                }
                return '';
            });
            rest = rest.replace(/([.#])((?:\\.|[\w@-])+)/g, (_whole, prefix, value) => {
                value = value.replace(/\\(.)/g, '$1');
                if (prefix === '#') {
                    selector.id = value;
                    specificity += 100;
                    specificityTuple[0]++;
                }
                else {
                    specificity += 10;
                    specificityTuple[1]++;
                    const hook = /^(method|profile|subtype|role|owner|category|catalogue)-(.+)$/.exec(value);
                    if (hook)
                        selector[hook[1]] = hook[2];
                    else
                        classes.push(value);
                }
                return '';
            });
            if (rest.trim() && rest.trim() !== '*') {
                fail('Unsupported CSS selector ' + rawSelector.trim());
                invalid = true;
            }
            if (classes.length)
                selector.classes = classes;
            if (!invalid && tokens.length)
                result.push({ selector, declarations: { ...declarations }, important: [...important], specificity, specificityTuple });
        }
    }
    return { rules: result, diagnostics };
}

},
"defaults/src/method-names.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.methodNames = exports.methodNamesSourceHash = void 0;
exports.methodNamesSourceHash = "6b8da242f1d4a1baf754e38efd49051286bcc739c769d4ed36137a4dd5d58d07";
exports.methodNames = Object.freeze({
    "MT01": "ddn",
    "MT02": "uml",
    "MT03": "chen",
    "MT04": "flowchart",
    "MT05": "bpmn",
    "MT06": "cmmn",
    "MT07": "dmn",
    "MT08": "c4",
    "MT09": "dfd",
    "MT10": "sysml",
    "MT11": "archimate",
    "MT12": "epc",
    "MT13": "idef0",
    "MT14": "petri",
    "MT15": "orm",
    "MT16": "vsm",
    "MT17": "sdl",
    "MT18": "msc",
    "MT19": "soaml",
    "MT20": "uaf",
    "MT21": "electrical"
});

},
"execution/src/compute.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.decodePayload = decodePayload;
exports.createComputeExecutor = createComputeExecutor;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("verifier/src/index.js");
const index_js_3 = require("execution/src/index.js");
function decodePayload(sources, previous) {
    const files = sources.files.map(({ originalBytes: _, ...file }) => file);
    const old = previous ? { ...previous, documents: previous.documents.map(document => ({ ...document, file: (({ originalBytes: _, ...file }) => file)(document.file) })) } : undefined;
    return { sources: { entry: sources.entry, files }, ...(old ? { previous: old } : {}) };
}
function result(request, payload, outcome, diagnostics, coverage) {
    const { payload: _, ...echo } = request;
    return { request: echo, payload, outcome, diagnostics, coverage };
}
function record(value) { return !!value && typeof value === 'object' && !Array.isArray(value); }
async function decode(request, context) {
    if (!record(request.payload) || !record(request.payload.sources) || !Array.isArray(request.payload.sources.files))
        throw Error('Decode requires a sources payload');
    const payload = request.payload;
    let bytes = 0;
    for (const file of payload.sources.files) {
        if (typeof file.text !== 'string')
            throw Error('Source text must be a string');
        bytes += file.text.length * 2;
        context.accountMemory(bytes);
        await context.checkpoint(file.text.length);
    }
    const decoded = (0, index_js_1.decodeSources)(payload.sources, { ...context.task, ...(payload.previous ? { previous: payload.previous } : {}) });
    context.check();
    const digest = (0, index_js_3.fingerprint)(decoded.normalized);
    context.check();
    return result(request, { decoded, fingerprint: digest }, decoded.syntaxValid ? (decoded.diagnostics.some(d => d.severity === 'error') ? 'incomplete' : 'valid') : 'invalid', decoded.diagnostics, decoded.coverage);
}
function createComputeExecutor(options) {
    const { executor: _, ...localOptions } = options;
    const verifier = (0, index_js_2.createVerifier)(localOptions);
    const executor = (0, index_js_3.createExecutor)({
        decode: async (request, context) => {
            if ((0, index_js_3.fingerprint)(request.versions) !== (0, index_js_3.fingerprint)(options.versions))
                throw Error('Compute version set does not match the executor');
            return decode(request, context);
        },
        verify: async (request, context) => {
            if ((0, index_js_3.fingerprint)(request.versions) !== (0, index_js_3.fingerprint)(options.versions))
                throw Error('Compute version set does not match the executor');
            if (!record(request.payload) || !record(request.payload.snapshot) || !record(request.payload.options))
                throw Error('Verify requires snapshot and options payloads');
            const payload = request.payload;
            const report = await (0, index_js_2.verifyDecoded)(verifier, payload.snapshot, { ...payload.options, ...context.task }, payload.diagnostics ?? []);
            context.check();
            return result(request, report, report.outcome, report.diagnostics, report.coverage);
        },
    });
    return { run: (request, task = {}) => executor.run(request, { ...(options.limits ? { budget: options.limits } : {}), ...task }), destroy() { executor.destroy(); verifier.destroy(); } };
}

},
"execution/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ComputationStopped = exports.fingerprint = void 0;
exports.sha256 = sha256;
exports.canonical = canonical;
exports.clone = clone;
exports.freeze = freeze;
exports.createContext = createContext;
exports.createExecutor = createExecutor;
function sha256(text) {
    const bytes = [];
    for (const character of text) {
        let n = character.codePointAt(0);
        if (n >= 0xd800 && n <= 0xdfff)
            n = 0xfffd;
        if (n < 128)
            bytes.push(n);
        else if (n < 2048)
            bytes.push(192 | n >> 6, 128 | n & 63);
        else if (n < 65536)
            bytes.push(224 | n >> 12, 128 | n >> 6 & 63, 128 | n & 63);
        else
            bytes.push(240 | n >> 18, 128 | n >> 12 & 63, 128 | n >> 6 & 63, 128 | n & 63);
    }
    const bits = bytes.length * 8;
    bytes.push(128);
    while (bytes.length % 64 !== 56)
        bytes.push(0);
    for (let i = 7; i >= 0; i--)
        bytes.push(Math.floor(bits / 2 ** (8 * i)) & 255);
    const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const k = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    const rotate = (n, b) => n >>> b | n << 32 - b;
    for (let offset = 0; offset < bytes.length; offset += 64) {
        const w = new Int32Array(64);
        for (let i = 0; i < 16; i++) {
            const p = offset + i * 4;
            w[i] = bytes[p] << 24 | bytes[p + 1] << 16 | bytes[p + 2] << 8 | bytes[p + 3];
        }
        for (let i = 16; i < 64; i++) {
            const a = w[i - 15], b = w[i - 2];
            w[i] = w[i - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ a >>> 3) + w[i - 7] + (rotate(b, 17) ^ rotate(b, 19) ^ b >>> 10) | 0;
        }
        let [a, b, c, d, e, f, g, j] = h;
        for (let i = 0; i < 64; i++) {
            const t1 = j + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + (e & f ^ ~e & g) + k[i] + w[i] | 0;
            const t2 = (rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + (a & b ^ a & c ^ b & c) | 0;
            j = g;
            g = f;
            f = e;
            e = d + t1 | 0;
            d = c;
            c = b;
            b = a;
            a = t1 + t2 | 0;
        }
        const parts = [a, b, c, d, e, f, g, j];
        for (let i = 0; i < 8; i++)
            h[i] = h[i] + parts[i] | 0;
    }
    return h.map(n => (n >>> 0).toString(16).padStart(8, '0')).join('');
}
function jsonData(value, sorted) {
    const active = new Set();
    const encode = (item) => {
        if (item === null || typeof item === 'string' || typeof item === 'boolean')
            return JSON.stringify(item);
        if (typeof item === 'number') {
            if (!Number.isFinite(item))
                throw new TypeError('DDN values must be finite');
            return JSON.stringify(item);
        }
        if (!item || typeof item !== 'object' || (!Array.isArray(item) && Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null))
            throw new TypeError('Expected plain JSON data');
        if (active.has(item))
            throw new TypeError('Cyclic JSON data');
        active.add(item);
        try {
            const descriptors = Object.getOwnPropertyDescriptors(item);
            if (Object.getOwnPropertySymbols(item).some(key => Object.getOwnPropertyDescriptor(item, key)?.enumerable))
                throw new TypeError('JSON data cannot have symbol keys');
            if (Array.isArray(item)) {
                const cells = [];
                for (let index = 0; index < item.length; index++) {
                    const descriptor = descriptors[String(index)];
                    if (!descriptor || !('value' in descriptor))
                        throw new TypeError('Expected dense JSON array data');
                    cells.push(encode(descriptor.value));
                }
                if (Object.keys(item).some(key => !/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= item.length))
                    throw new TypeError('JSON arrays cannot have named data properties');
                return '[' + cells.join(',') + ']';
            }
            const keys = Object.keys(item);
            if (sorted)
                keys.sort();
            const fields = [];
            for (const key of keys) {
                const descriptor = descriptors[key];
                if (!('value' in descriptor))
                    throw new TypeError('JSON data cannot contain accessors');
                if (descriptor.value !== undefined)
                    fields.push(JSON.stringify(key) + ':' + encode(descriptor.value));
            }
            return '{' + fields.join(',') + '}';
        }
        finally {
            active.delete(item);
        }
    };
    return encode(value);
}
function canonical(value) { return value === undefined ? 'null' : jsonData(value, true); }
const fingerprint = (value) => sha256(canonical(value));
exports.fingerprint = fingerprint;
function clone(value) { return JSON.parse(jsonData(value, false)); }
function freeze(value) {
    const seen = new Set();
    const visit = (item) => {
        if (!item || typeof item !== 'object' || ArrayBuffer.isView(item) || seen.has(item))
            return;
        seen.add(item);
        Object.freeze(item);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(item)))
            if ('value' in descriptor)
                visit(descriptor.value);
    };
    visit(value);
    return value;
}
class ComputationStopped extends Error {
    outcome;
    constructor(outcome, message) {
        super(message);
        this.outcome = outcome;
    }
}
exports.ComputationStopped = ComputationStopped;
const schedule = () => new Promise(resolve => {
    const host = globalThis;
    if (host.setTimeout)
        host.setTimeout(resolve, 0);
    else
        resolve();
});
function createContext(versions, task = {}) {
    const start = Date.now();
    let units = 0, memory = 0, slice = start;
    const budget = task.budget ? { ...task.budget } : undefined;
    if (budget && [budget.elapsedMs, budget.workUnits, budget.memoryBytes].some(n => !Number.isFinite(n) || n < 0))
        throw new RangeError('Invalid operation budget');
    if (budget)
        Object.freeze(budget);
    const capturedTask = Object.freeze({ ...(task.cancel ? { cancel: task.cancel } : {}), ...(budget ? { budget } : {}) });
    const capturedVersions = freeze(clone(versions));
    function check() {
        if (capturedTask.cancel?.aborted)
            throw new ComputationStopped('cancelled', 'Operation cancelled');
        if (budget && (Date.now() - start > budget.elapsedMs || units > budget.workUnits || memory > budget.memoryBytes))
            throw new ComputationStopped('budget-exceeded', 'Operation budget exhausted');
    }
    return {
        versions: capturedVersions, task: capturedTask, check,
        get stats() { return { elapsedMs: Date.now() - start, workUnits: units, memoryBytes: memory }; },
        accountMemory(bytes) {
            if (!Number.isFinite(bytes) || bytes < 0)
                throw new RangeError('Invalid memory accounting');
            memory = bytes;
            check();
        },
        async checkpoint(count) {
            if (!Number.isFinite(count) || count < 0)
                throw new RangeError('Invalid work accounting');
            units += count;
            check();
            if (Date.now() - slice >= 4) {
                await schedule();
                slice = Date.now();
                check();
            }
        },
    };
}
function createExecutor(handlers) {
    let disposed = false;
    const active = new Set();
    return {
        async run(request, options = {}) {
            const local = { aborted: disposed, listeners: new Set() };
            active.add(local);
            const upstreamCancel = options.cancel;
            const unlisten = upstreamCancel?.onAbort(() => {
                local.aborted = true;
                for (const fn of local.listeners)
                    fn();
            });
            const cancel = { get aborted() { return local.aborted || !!upstreamCancel?.aborted; }, onAbort(fn) { local.listeners.add(fn); return () => { local.listeners.delete(fn); }; } };
            try {
                request = freeze(clone(request));
                const context = createContext(request.versions, { ...options, cancel });
                context.check();
                const handler = ['decode', 'verify', 'project', 'layout', 'route', 'capture'].includes(request.kind) && Object.prototype.hasOwnProperty.call(handlers, request.kind) ? handlers[request.kind] : undefined;
                if (!handler)
                    return failed(request, 'unsupported', 'No handler for ' + request.kind);
                const result = await handler(request, context);
                context.check();
                return result;
            }
            catch (error) {
                if (error instanceof ComputationStopped)
                    return failed(request, error.outcome, error.message);
                return failed(request, 'invalid', error instanceof Error ? error.message : 'Computation failed');
            }
            finally {
                unlisten?.();
                active.delete(local);
            }
        },
        destroy() {
            disposed = true;
            for (const job of active) {
                job.aborted = true;
                for (const fn of job.listeners)
                    fn();
            }
            active.clear();
        },
    };
}
function failed(request, outcome, message) {
    const echo = Object.fromEntries(Object.entries(Object.getOwnPropertyDescriptors(request)).filter(([key, descriptor]) => key !== 'payload' && descriptor.enumerable && 'value' in descriptor).map(([key, descriptor]) => [key, descriptor.value]));
    return { request: echo, outcome, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: typeof echo.kind === 'string' ? [echo.kind] : [] }, diagnostics: [{ code: 'execution.' + outcome, severity: 'error', message }], payload: null };
}

},
"language/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.splitDelimited = splitDelimited;
exports.decodeText = decodeText;
exports.quoteText = quoteText;
exports.parseTableHeader = parseTableHeader;
exports.parseTableRow = parseTableRow;
exports.decodeSources = decodeSources;
exports.allNodes = allNodes;
exports.findNode = findNode;
exports.applySourcePatches = applySourcePatches;
exports.serializeProperties = serializeProperties;
exports.patchProperty = patchProperty;
exports.deleteDeclaration = deleteDeclaration;
exports.renameDeclaration = renameDeclaration;
exports.appendDeclaration = appendDeclaration;
exports.encodeDefinition = encodeDefinition;
exports.sourceText = sourceText;
exports.replaceRecordData = replaceRecordData;
exports.replaceDataBody = replaceDataBody;
exports.replaceDraftBody = replaceDraftBody;
exports.replaceNoteBody = replaceNoteBody;
const index_js_1 = require("model/src/index.js");
const schema_js_1 = require("language/src/schema.js");
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
function splitDelimited(text, delimiter) {
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
function decodeText(raw) {
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
function quoteText(text) {
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
    return unfold(schema_js_1.shapes[name], seen);
}
function variants(shape) { const s = unfold(shape); return s ? (s.type || s.properties) ? [s] : s.anyOf || s.oneOf ? (s.anyOf || s.oneOf).flatMap(x => variants(x)) : [s] : []; }
function childShape(shape, key) {
    for (const s of variants(shape)) {
        if (s.properties?.[key])
            return s.properties[key];
        if (typeof s.additionalProperties === 'object')
            return s.additionalProperties;
        if (s.additionalProperties === true)
            return schema_js_1.shapes.json_value;
    }
    return undefined;
}
function ownerShape(owner, record, path) {
    let shape = schema_js_1.shapes[owner];
    if (owner === 'view_definition' && path === 'projection') {
        const projection = childShape(shape, 'projection');
        return { ...unfold(projection), properties: { ...unfold(projection)?.properties, options: schema_js_1.shapes['profile_' + (0, index_js_1.asString)(record.profile)] ?? {} } };
    }
    if (owner === 'view_definition' && (path === 'projection.options' || path.startsWith('projection.options.'))) {
        let value = schema_js_1.shapes['profile_' + (0, index_js_1.asString)(record.profile)];
        for (const key of (0, index_js_1.safePath)(path).slice(2))
            value = childShape(value, key);
        return value;
    }
    if (owner === 'declaration_map')
        return schema_js_1.shapes.declaration_map?.properties?.[path];
    if (owner === 'definition') {
        const role = (0, index_js_1.asString)(record.role);
        const info = schema_js_1.coreTypes[role] || schema_js_1.roleTypes[(record.category === 'relation' ? 'relation::' : '') + role];
        if (info && ['content', 'metadata', 'properties', 'qualifiers'].includes(path.split('.')[0])) {
            if (role.startsWith('core::'))
                shape = { properties: { [record.category === 'relation' ? 'qualifiers' : 'content']: schema_js_1.shapes[info.schema], ...(role === 'core::Port' ? { metadata: schema_js_1.shapes.port_metadata, properties: schema_js_1.shapes.port_properties } : {}) } };
            else
                shape = schema_js_1.shapes[info.schema];
        }
    }
    for (const segment of (0, index_js_1.safePath)(path))
        shape = childShape(shape, segment);
    return shape;
}
function isReferenceShape(shape) { return variants(shape).some(v => v.properties?.name && v.properties?.file && v.properties?.id); }
function typedValue(raw, shape, file) {
    const text = decodeText(raw), quoted = /^["']/.test(raw.trim());
    const vs = variants(shape);
    const types = vs.flatMap(v => typeof v.type === 'string' ? [v.type] : v.type || []);
    if (!quoted && text === 'null' && types.includes('null'))
        return null;
    const reference = isReferenceShape(shape) && !(quoted && types.includes('string'));
    if (reference) {
        const bits = splitDelimited(raw, '::');
        return bits.length > 1 ? { file: (0, index_js_1.normalizeLocation)(decodeText(bits.slice(0, -1).join('::')), file), name: decodeText(bits.at(-1)) } : { file, name: text };
    }
    if (!quoted && text === 'null')
        return null;
    if (!quoted && text === 'empty list' && types.includes('array'))
        return [];
    if (!quoted && text === 'empty record' && types.includes('object'))
        return {};
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
function parseTableHeader(text) {
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
function parseTableRow(text, columns) {
    const cells = splitDelimited(text, '.');
    if (cells.length > columns.length)
        throw Error('More cells than declared columns');
    return columns.map((column, i) => {
        const cell = cells[i];
        if (cell === undefined || !cell.trim())
            return null;
        return typedValue(cell, schema_js_1.shapes[(0, index_js_1.asString)(column.type, 'text')], '');
    });
}
function resolveSourceReference(bundle, site, scoped = []) {
    const file = (0, index_js_1.asString)(site.reference.file, site.file), name = (0, index_js_1.asString)(site.reference.name), id = (0, index_js_1.asString)(site.reference.id);
    const local = scoped.filter(r => r.file === file && (id ? r.ref.id === id && (!name || r.record.name === name) : r.record.name === name));
    if (local.length)
        return local.length === 1 ? local[0] : undefined;
    const declared = (0, index_js_1.resolveReference)(bundle, site.file, site.reference);
    if (declared || id || !name)
        return declared;
    const globals = (0, index_js_1.listRecords)(bundle).filter(r => r.file === file);
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
            entry = (0, index_js_1.normalizeLocation)(entry);
        }
        catch { }
        this.bundle = { version: 'ddn-next-1', entry, files: [] };
        for (const f of input.files) {
            let id = f.id;
            try {
                id = (0, index_js_1.normalizeLocation)(id);
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
                    const first = this.ls.slice(i + 1, stop).find(child => child.text.trim() && !child.text.trimStart().startsWith('//'));
                    if (keyword !== 'data' || first?.text.trim() === 'with')
                        this.reserveAuthoredIds(i + 1, stop);
                }
            }
            catch { }
            i = stop;
        }
    }
    id(node, name) {
        const previous = this.options.previous?.documents.find(d => d.file.id === this.current.id);
        const flatten = (nodes) => nodes.flatMap(n => [n, ...flatten(n.children)]);
        const previousNodes = previous ? flatten(previous.nodes) : [];
        const previousIds = new Set(previousNodes.map(x => x.ref?.id));
        const candidates = previousNodes.filter(x => x.kind === node.kind && x.ref && !this.usedIds.has(x.ref.id));
        const exact = (node.identityKey ? candidates.find(x => x.identityKey === node.identityKey) : undefined) || candidates.find(x => x.raw === node.raw) || (name ? candidates.find(x => (0, index_js_1.findRecord)(this.options.previous?.normalized, x.ref)?.name === name) : undefined) || candidates.find(x => x.start === node.start && !this.current.text.includes(x.raw));
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
                this.names.set(record.name, (0, index_js_1.recordRef)(this.current.id, record));
        }
        node.ref = (0, index_js_1.recordRef)(this.current.id, record);
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
        const ref = { file: parts.length === 2 ? (0, index_js_1.normalizeLocation)(decodeText(parts[0]), this.current.id) : this.current.id, name };
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
        if (!(0, index_js_1.isRecord)(view.selection))
            view.selection = {};
        array(view.selection, 'include').push(target);
    }
    appearance(target, view, node, name, title) {
        const a = { target, parent: { file: this.current.id, id: (0, index_js_1.asString)(view.id) } };
        const own = { ...node, kind: node.kind === 'use' ? 'use' : 'appearance', children: [], implicit: true, identityKey: 'appearance:' + (0, index_js_1.asString)(view.id) + ':' + (0, index_js_1.asString)(target.file, this.current.id) + ':' + (0, index_js_1.asString)(target.id, (0, index_js_1.asString)(target.name)) };
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
            if (!prefix && key === 'shadow' && w.length === 2 && ['none', 'offset', 'centre', 'corners', 'corner'].includes(decodeText(w[1].raw)))
                path = 'shadow.kind';
            if (owner === 'definition' && record.category === 'relation' && /^(source|target)\./.test(path))
                path = 'qualifiers.' + path;
            (0, index_js_1.safePath)(path);
            const appearancePath = appearance && (['position', 'size', 'body', 'columns', 'pinned'].includes(path.split('.')[0]) || record.category === 'relation' && ['label', 'legend'].includes(path.split('.')[0]));
            const propertyRecord = appearancePath ? appearance : record, propertyOwner = appearancePath ? 'appearance' : owner;
            const n = this.node(line, stop, 'property');
            if (appearancePath)
                n.owner = (0, index_js_1.recordRef)(this.current.id, appearance);
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
                    (0, index_js_1.setPath)(destination, path, value);
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
                record.file = (0, index_js_1.normalizeLocation)(record.file, this.current.id);
            else
                record.file = this.current.id;
            const key = typeof record.name === 'string' ? 'name' : 'id';
            const property = node.children.find(n => n.path?.split('.').at(-1) === key);
            if (property?.valueStart !== undefined && property.valueEnd !== undefined)
                this.references.push({ file: this.current.id, start: property.valueStart, end: property.valueEnd, reference: record, kind: 'reference', spelling: key, ...(this.templateScope ? { scope: this.templateScope } : {}) });
        }
    }
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
        const data = (0, index_js_1.asRecord)(record.data), columns = (0, index_js_1.asArray)(data.columns), at = columns.findIndex(c => (0, index_js_1.asRecord)(c).id === 'field');
        if (at < 0)
            return;
        const members = [];
        const authoredMembers = (0, index_js_1.asArray)(record.members).map(ref => (0, index_js_1.findRecord)(this.bundle, (0, index_js_1.asRecord)(ref))).filter((field) => !!field && field.role === 'field');
        for (const [ordinal, row] of (0, index_js_1.asArray)(data.rows).entries()) {
            const label = (0, index_js_1.asArray)(row)[at];
            if (typeof label !== 'string' || !label)
                continue;
            const fieldNode = { ...node, kind: 'field', raw: label, children: [], generated: true, identityKey: 'field:' + (0, index_js_1.asString)(record.id) + ':' + label + ':' + (0, index_js_1.asArray)(data.rows).slice(0, ordinal).filter(r => (0, index_js_1.asArray)(r)[at] === label).length };
            node.children.push(fieldNode);
            const content = { parent: { file: this.current.id, id: (0, index_js_1.asString)(record.id) }, ordinal };
            const cell = (id) => { const index = columns.findIndex(c => (0, index_js_1.asRecord)(c).id === id); return index < 0 ? undefined : (0, index_js_1.asArray)(row)[index]; };
            const datatype = cell('type'), comment = cell('comment');
            if (typeof datatype === 'string')
                content.datatype = datatype;
            if (typeof comment === 'string')
                content.comment = comment;
            const existing = authoredMembers.find(field => (0, index_js_1.asRecord)(field.content).ordinal === ordinal) ?? authoredMembers.find(field => field.title === label);
            const field = existing ?? this.add('definition', { role: 'field', title: label, content }, fieldNode);
            if (existing) {
                const authored = (0, index_js_1.asRecord)(field.content);
                field.title = label;
                field.content = { ...authored, ...content, parent: authored.parent ?? content.parent };
            }
            const sites = Array.isArray(row) ? this.cellSources.get(row) : undefined;
            const site = (id) => sites?.[columns.findIndex(c => (0, index_js_1.asRecord)(c).id === id)];
            const domain = cell('domain'), key = cell('key'), constraints = cell('constraints') ?? cell('constraint'), domainSite = site('domain'), constraintsSite = site('constraints') ?? site('constraint');
            this.fieldBindings.push({ file: this.current.id, field, ...(this.templateScope ? { scope: this.templateScope } : {}), ...(domainSite ? { domainSite } : {}), ...(constraintsSite ? { constraintsSite } : {}), ...(domain !== undefined && domain !== null && domain !== '' ? { domain } : {}), ...(key !== undefined && key !== null && key !== '' ? { key } : {}), ...(constraints !== undefined && constraints !== null && constraints !== '' ? { constraints } : {}) });
            members.push({ file: this.current.id, id: (0, index_js_1.asString)(field.id) });
        }
        if (members.length)
            record.members = [...members, ...(0, index_js_1.asArray)(record.members).filter(ref => { const member = (0, index_js_1.findRecord)(this.bundle, (0, index_js_1.asRecord)(ref)); return member?.role !== 'field'; })];
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
            array(this.doc, 'includes').push((0, index_js_1.normalizeLocation)(decodeText(tail(1)), this.current.id));
            return;
        }
        if (keyword === 'style') {
            if (!['file', 'view', 'document'].includes(ctx.kind))
                throw Error('style is allowed at file or view scope');
            if (!(0, index_js_1.isRecord)(ctx.record.style))
                ctx.record.style = {};
            const location = (0, index_js_1.normalizeLocation)(decodeText(tail(1)), this.current.id);
            if (ctx.kind === 'file')
                array(ctx.record.style, 'sheets').push(location);
            else {
                const asset = this.add('asset', { media_type: 'text/css', path: location }, node);
                asset.name = '_stylesheet_' + (0, index_js_1.asString)(asset.id);
                array(ctx.record.style, 'sheets').push({ file: this.current.id, id: (0, index_js_1.asString)(asset.id) });
            }
            return;
        }
        if (keyword === 'with') {
            if (ctx.kind === 'file')
                throw Error('with needs an owning declaration');
            if (ctx.record.id)
                node.owner = (0, index_js_1.recordRef)(this.current.id, ctx.record);
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
            node.ref = (0, index_js_1.recordRef)(this.current.id, record);
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
            placement.identityKey = 'placement:' + (0, index_js_1.asString)(record.id);
            this.add('placement', { target: { file: this.current.id, id: (0, index_js_1.asString)(record.id) } }, placement);
            node.children.push(placement);
            let inputColumns;
            if (keyword === 'erd' && as >= 0) {
                inputColumns = parseTableHeader(tail(as + 1));
                record.table_schema = inputColumns;
            }
            if (keyword !== 'document' && !schema_js_1.profiles.includes(profile))
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
                generated.identityKey = 'mindmap-root:' + (0, index_js_1.asString)(record.id);
                node.children.push(generated);
                const root = this.add('definition', { role: 'object', title: parts.title ?? name }, generated);
                this.selection(record, { file: this.current.id, id: (0, index_js_1.asString)(root.id) });
                this.appearance({ file: this.current.id, id: (0, index_js_1.asString)(root.id) }, record, generated);
                next.root = root;
            }
            if (recipe === 'bar') {
                const dataNode = this.node(line, end, 'chartdata');
                dataNode.generated = true;
                node.children.push(dataNode);
                const data = this.add('data', { columns: [{ id: 'label', type: 'text' }, { id: 'value', type: 'number' }], rows: [] }, dataNode);
                data.name = '_bar_' + (0, index_js_1.asString)(data.id);
                record.projection = { options: { records: { file: this.current.id, id: (0, index_js_1.asString)(data.id) }, x: 'label', y: 'value', x_type: 'category', mark: 'bar' } };
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
                const number = typedValue(value.raw, schema_js_1.shapes.number, this.current.id);
                const label = decodeText(head.slice(0, value.start));
                const reference = (0, index_js_1.asRecord)((0, index_js_1.asRecord)(ctx.record.projection).options).records;
                const data = (0, index_js_1.asArray)(this.doc.data).find(d => (0, index_js_1.asRecord)(d).id === (0, index_js_1.asRecord)(reference).id);
                if (!(0, index_js_1.isRecord)(data))
                    throw Error('Chart recipe data is unavailable');
                array(data, 'rows').push([label, number]);
                return;
            }
            if (ctx.kind === 'element' && ctx.recipe === 'erd' && keyword !== 'element') {
                node.kind = 'field-row';
                node.owner = (0, index_js_1.recordRef)(this.current.id, ctx.record);
                const rows = this.parseData(index, end, node, ctx.inputColumns || ['field', 'type', 'domain', 'key', 'comment'].map(id => ({ id })));
                const existing = (0, index_js_1.asRecord)(ctx.record.data);
                ctx.record.data = Object.keys(existing).length ? { columns: existing.columns, rows: [...(0, index_js_1.asArray)(existing.rows), ...(0, index_js_1.asArray)(rows.rows)] } : rows;
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
            const info = schema_js_1.coreTypes[role] || schema_js_1.roleTypes[role];
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
                this.selection(ctx.view, { file: this.current.id, id: (0, index_js_1.asString)(record.id) });
                occurrence = this.appearance({ file: this.current.id, id: (0, index_js_1.asString)(record.id) }, ctx.view, node);
            }
            if (ctx.recipe === 'mindmap' && (ctx.parent || ctx.root)) {
                const parent = ctx.parent || ctx.root;
                const edgeNode = this.node(line, end, 'branch');
                edgeNode.generated = true;
                edgeNode.identityKey = 'branch:' + (0, index_js_1.asString)(parent.id) + ':' + (0, index_js_1.asString)(record.id);
                node.children.push(edgeNode);
                const edge = this.add('definition', { category: 'relation', role: 'assoc', endpoints: [{ definition: { file: this.current.id, id: (0, index_js_1.asString)(parent.id) } }, { definition: { file: this.current.id, id: (0, index_js_1.asString)(record.id) } }] }, edgeNode);
                if (ctx.view) {
                    this.selection(ctx.view, { file: this.current.id, id: (0, index_js_1.asString)(edge.id) });
                    this.appearance({ file: this.current.id, id: (0, index_js_1.asString)(edge.id) }, ctx.view, edgeNode);
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
            node.owner = (0, index_js_1.recordRef)(this.current.id, ctx.record);
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
                node.owner = (0, index_js_1.recordRef)(this.current.id, ctx.record);
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
                node.owner = (0, index_js_1.recordRef)(this.current.id, ctx.record);
                this.sequence(index + 1, end, line.indent, { kind: 'element', record: section, owner: 'inclusion' }, node.children);
            }
            else {
                this.selection(ctx.record, reference);
                node.kind = 'use';
                const occurrence = this.appearance(reference, ctx.record, node, name, parts.title);
                node.ref = (0, index_js_1.recordRef)(this.current.id, occurrence);
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
            const appearance = ctx.view ? this.appearance({ file: this.current.id, id: (0, index_js_1.asString)(record.id) }, ctx.view, node) : undefined;
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
                this.selection(ctx.view, { file: this.current.id, id: (0, index_js_1.asString)(record.id) });
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
                    this.names.set(name, (0, index_js_1.recordRef)(this.current.id, note));
                }
                node.ref = (0, index_js_1.recordRef)(this.current.id, note);
                array(ctx.record, 'notes').push(note);
            }
            else if (ctx.kind === 'file') {
                const view = this.add('view', { profile: 'ddn@1', subtype: ['notes'], notes: [note], ...(parts.title !== undefined ? { title: parts.title } : {}) }, node, name || undefined);
                const placement = this.node(line, end, 'placement');
                this.add('placement', { target: { file: this.current.id, id: (0, index_js_1.asString)(view.id) } }, placement);
            }
            else {
                const text = this.add('definition', { role: 'core::Text', content: { text: note.text, format: 'markdown' }, ...(parts.title !== undefined ? { title: parts.title } : {}) }, node, name || undefined);
                if (ctx.kind === 'document')
                    array(ctx.record, 'sections').push({ kind: 'text', target: { file: this.current.id, id: (0, index_js_1.asString)(text.id) } });
                else if (ctx.view) {
                    this.selection(ctx.view, { file: this.current.id, id: (0, index_js_1.asString)(text.id) });
                    this.appearance({ file: this.current.id, id: (0, index_js_1.asString)(text.id) }, ctx.view, node);
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
                record.path = (0, index_js_1.normalizeLocation)(decodeText(tail(from + 1)), this.current.id);
            }
            if (keyword === 'template') {
                const outerDocument = this.doc, outerNames = this.names, outerScope = this.templateScope;
                this.doc = {};
                this.names = new Map();
                this.templateScope = node.ref;
                try {
                    this.sequence(index + 1, end, line.indent, { kind: 'template', record, owner: 'template_record' }, node.children);
                    if (Object.keys(this.doc).length) {
                        const fragment = (0, index_js_1.asRecord)(record.fragment);
                        for (const [key, values] of Object.entries(this.doc))
                            fragment[key] = [...(0, index_js_1.asArray)(fragment[key]), ...(0, index_js_1.asArray)(values)];
                        record.fragment = fragment;
                    }
                    const fragment = (0, index_js_1.asRecord)(record.fragment);
                    for (const collection of ['definitions', 'views', 'appearances'])
                        for (const [ordinal, item] of (0, index_js_1.asArray)(fragment[collection]).entries())
                            if ((0, index_js_1.isRecord)(item)) {
                                if (!item.id)
                                    item.id = 'fragment-' + collection + '-' + ordinal;
                                for (const [noteIndex, note] of (0, index_js_1.asArray)(item.notes).entries())
                                    if ((0, index_js_1.isRecord)(note) && !note.id)
                                        note.id = (0, index_js_1.asString)(item.id) + '-note-' + noteIndex;
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
        const includes = (0, index_js_1.asArray)(this.doc.includes).filter((x) => typeof x === 'string');
        for (const include of includes)
            this.parseFile(include);
    }
    resolve() {
        const remap = new Map();
        for (const item of this.allocations) {
            const current = (0, index_js_1.asString)(item.record.id);
            if (current !== item.initial)
                remap.set(item.file + '\0' + item.initial, current);
            item.node.ref = { file: item.file, id: current };
        }
        const rewrite = (value) => {
            if (Array.isArray(value)) {
                for (const item of value)
                    rewrite(item);
            }
            else if ((0, index_js_1.isRecord)(value)) {
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
        for (const r of (0, index_js_1.listRecords)(this.bundle)) {
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
            const template = site.scope ? (0, index_js_1.findRecord)(this.bundle, site.scope) : undefined;
            const fragment = (0, index_js_1.asRecord)(template?.fragment);
            const scoped = template ? (0, index_js_1.listRecords)({ version: 'ddn-next-1', entry: site.file, files: [{ location: site.file, document: fragment }] }) : [];
            const match = resolveSourceReference(this.bundle, site, scoped);
            if (match) {
                site.reference.id = match.ref.id;
                site.target = match.ref;
            }
            else
                this.diagnostics.push({ code: 'reference.unresolved', severity: 'error', message: 'Unresolved or ambiguous reference: ' + (0, index_js_1.asString)(site.reference.name), source: { file: site.file, revision: this.sourceMap.get(site.file)?.revision || '', start: site.start, end: site.end } });
        }
    }
    resolveFieldBindings() {
        this.references = this.references.filter(site => !site.boundCell);
        const allowedKeys = new Set(['primary', 'candidate', 'business', 'partition', 'clustering', 'foreign']);
        for (const binding of this.fieldBindings) {
            const content = (0, index_js_1.asRecord)(binding.field.content), target = (0, index_js_1.recordRef)(binding.file, binding.field);
            const derived = ['content.domain', 'content.key', 'content.constraints'];
            const retained = (0, index_js_1.asArray)(binding.field.incomplete).filter(item => !derived.includes((0, index_js_1.asString)((0, index_js_1.asRecord)(item).path)));
            if (retained.length)
                binding.field.incomplete = retained;
            else
                delete binding.field.incomplete;
            this.diagnostics = this.diagnostics.filter(d => !(d.target?.file === target.file && d.target.id === target.id && ['field.domain', 'field.key', 'field.constraints'].includes(d.code)));
            const template = binding.scope ? (0, index_js_1.findRecord)(this.bundle, binding.scope) : undefined;
            const scoped = template ? (0, index_js_1.listRecords)({ version: 'ddn-next-1', entry: binding.file, files: [{ location: binding.file, document: (0, index_js_1.asRecord)(template.fragment) }] }) : [];
            const incomplete = (path, value, reason) => { const raw = typeof value === 'string' ? value : JSON.stringify(value); array(binding.field, 'incomplete').push({ path, raw, reason }); this.diagnostics.push({ code: 'field.' + path.split('.').at(-1), severity: 'warning', message: reason, target }); };
            const resolve = (value) => {
                if ((0, index_js_1.isRecord)(value))
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
                        file = (0, index_js_1.normalizeLocation)(decodeText(parts[0]), binding.file);
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
                if ((0, index_js_1.isRecord)(value)) {
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
                const descriptor = domain && (schema_js_1.roleTypes[(0, index_js_1.asString)(domain.record.role)] || schema_js_1.coreTypes[(0, index_js_1.asString)(domain.record.role)]);
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
                    const descriptor = constraint && (schema_js_1.roleTypes[(0, index_js_1.asString)(constraint.record.role)] || schema_js_1.coreTypes[(0, index_js_1.asString)(constraint.record.role)]);
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
        for (const entry of (0, index_js_1.listRecords)(this.bundle)) {
            if (entry.kind === 'view' && (0, index_js_1.isRecord)(entry.record.selection) && Array.isArray(entry.record.selection.include)) {
                const seen = new Set();
                const selection = entry.record.selection;
                selection.include = selection.include.filter(reference => {
                    const target = (0, index_js_1.resolveReference)(this.bundle, entry.file, reference);
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
                for (const [endpointIndex, endpoint] of (0, index_js_1.asArray)(entry.record.endpoints).entries()) {
                    const ep = (0, index_js_1.asRecord)(endpoint);
                    let definition = (0, index_js_1.resolveReference)(this.bundle, entry.file, ep.definition);
                    if (definition?.kind === 'appearance') {
                        if (definition.file !== entry.file) {
                            this.diagnostics.push({ code: 'reference.appearance-scope', severity: 'error', message: 'An endpoint occurrence must be local to the relationship file', target: entry.ref });
                        }
                        else {
                            const selected = (0, index_js_1.resolveReference)(this.bundle, definition.file, definition.record.target);
                            if (selected?.kind === 'definition') {
                                const occurrence = definition;
                                ep.definition = { file: selected.file, id: selected.ref.id };
                                definition = selected;
                                const parent = (0, index_js_1.resolveReference)(this.bundle, occurrence.file, occurrence.record.parent);
                                const appearances = (0, index_js_1.listRecords)(this.bundle).filter(item => item.kind === 'appearance' && (0, index_js_1.resolveReference)(this.bundle, item.file, item.record.target)?.ref.id === entry.ref.id && (0, index_js_1.resolveReference)(this.bundle, item.file, item.record.target)?.file === entry.file && (0, index_js_1.resolveReference)(this.bundle, item.file, item.record.parent)?.ref.id === parent?.ref.id && (0, index_js_1.resolveReference)(this.bundle, item.file, item.record.parent)?.file === parent?.file);
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
                    if ((0, index_js_1.isRecord)(ep.member) && definition) {
                        const id = (0, index_js_1.asString)(ep.member.id), name = (0, index_js_1.asString)(ep.member.name, id), file = (0, index_js_1.asString)(ep.member.file, definition.file);
                        const candidates = (0, index_js_1.asArray)(definition.record.members).map(ref => (0, index_js_1.resolveReference)(this.bundle, definition.file, ref)).filter(x => x && x.file === file && (id ? x.record.id === id : x.record.id === name || x.record.title === name || x.record.name === name));
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
                for (const section of (0, index_js_1.asArray)(entry.record.sections)) {
                    const s = (0, index_js_1.asRecord)(section), target = (0, index_js_1.resolveReference)(this.bundle, entry.file, s.target);
                    if (target)
                        s.kind = target.kind === 'data' ? 'data' : target.kind === 'asset' ? 'asset' : target.kind === 'definition' ? 'text' : 'view';
                }
        }
    }
    expandTemplates() {
        const expanded = new Set(), stack = new Set();
        const copy = (value) => Array.isArray(value) ? value.map(copy) : (0, index_js_1.isRecord)(value) ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, copy(v)])) : value;
        const error = (code, message, target) => { this.diagnostics.push({ code: 'template.' + code, severity: 'error', message, target }); };
        const compatible = (value, shape) => variants(shape).some(s => {
            const types = typeof s.type === 'string' ? [s.type] : s.type || [];
            if (value === null)
                return types.includes('null');
            if (Array.isArray(value))
                return types.includes('array') && value.every(v => compatible(v, s.items));
            if ((0, index_js_1.isRecord)(value))
                return (types.includes('object') || !!s.properties) && Object.entries(value).every(([k, v]) => { const child = childShape(s, k); return !!child && compatible(v, child); });
            return types.includes(typeof value) || (typeof value === 'number' && Number.isInteger(value) && types.includes('integer'));
        });
        const expand = (file, record, ancestry = []) => {
            const key = file + '\0' + (0, index_js_1.asString)(record.id), target = (0, index_js_1.recordRef)(file, record);
            if (expanded.has(key) || !record.template)
                return;
            const template = (0, index_js_1.resolveReference)(this.bundle, file, record.template);
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
            const parameters = (0, index_js_1.asRecord)(template.record.parameters), arguments_ = (0, index_js_1.asRecord)(record.arguments), bindings = {};
            for (const name of Object.keys(arguments_))
                if (!Object.hasOwn(parameters, name))
                    error('argument', 'Unknown template argument: ' + name, target);
            for (const [name, raw] of Object.entries(parameters)) {
                const parameter = (0, index_js_1.asRecord)(raw), value = Object.hasOwn(arguments_, name) ? arguments_[name] : parameter.default;
                if (value === undefined) {
                    if (parameter.required === true)
                        error('required', 'Missing required template argument: ' + name, target);
                    continue;
                }
                const type = (0, index_js_1.asString)(parameter.type, 'text'), shape = type === 'json' ? schema_js_1.shapes.json_value : schema_js_1.shapes[type];
                if (!shape || !compatible(value, shape)) {
                    error('argument-type', 'Invalid template argument type for ' + name, target);
                    continue;
                }
                bindings[name] = copy(value);
            }
            const bind = (value) => {
                if ((0, index_js_1.isRecord)(value) && typeof value.parameter === 'string' && Object.keys(value).length === 1) {
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
                if ((0, index_js_1.isRecord)(value)) {
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
            for (const [path, raw] of Object.entries((0, index_js_1.asRecord)(template.record.settings))) {
                if (['id', 'name', 'acceptance', 'acceptance_history', 'access'].includes(path.split('.')[0]) || path === 'design.state' && raw === 'accepted') {
                    error('authority', 'Template setting cannot supply identity or acceptance authority: ' + path, target);
                    continue;
                }
                if ((0, index_js_1.getPath)(record, path) !== undefined)
                    continue;
                const value = bind(raw);
                if (value === undefined)
                    continue;
                const shape = ownerShape('definition', record, path);
                if (!shape || !compatible(value, shape)) {
                    error('property-type', 'Template setting has the wrong registered type: ' + path, target);
                    continue;
                }
                (0, index_js_1.setPath)(record, path, value);
            }
            const fragment = (0, index_js_1.asRecord)(template.record.fragment), local = new Map();
            const generated = { definitions: [], views: [], appearances: [] };
            const bindingCopies = new Map();
            for (const collection of ['definitions', 'views', 'appearances'])
                for (const [ordinal, raw] of (0, index_js_1.asArray)(fragment[collection]).entries()) {
                    if (!(0, index_js_1.isRecord)(raw))
                        continue;
                    const child = copy(raw), old = (0, index_js_1.asString)(raw.id, 'fragment-' + collection + '-' + ordinal);
                    if (local.has(old)) {
                        error('identity', 'Duplicate identity inside template fragment: ' + old, target);
                        continue;
                    }
                    child.id = (0, index_js_1.asString)(record.id) + '--' + old;
                    local.set(old, (0, index_js_1.asString)(child.id));
                    if (typeof raw.name === 'string')
                        child.name = (0, index_js_1.asString)(record.name, (0, index_js_1.asString)(record.id)) + '::' + raw.name;
                    for (const [noteIndex, note] of (0, index_js_1.asArray)(child.notes).entries())
                        if ((0, index_js_1.isRecord)(note)) {
                            const original = (0, index_js_1.asString)(note.id, old + '-note-' + noteIndex);
                            const mutable = note;
                            mutable.id = (0, index_js_1.asString)(record.id) + '--' + original;
                            local.set(original, (0, index_js_1.asString)(mutable.id));
                            if (typeof mutable.name === 'string')
                                mutable.name = (0, index_js_1.asString)(record.name, (0, index_js_1.asString)(record.id)) + '::' + mutable.name;
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
                else if ((0, index_js_1.isRecord)(value)) {
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
            const instanceAppearances = (0, index_js_1.listRecords)(this.bundle).filter(entry => entry.kind === 'appearance' && (0, index_js_1.asRecord)(entry.record.target).id === record.id && (0, index_js_1.asString)((0, index_js_1.asRecord)(entry.record.target).file, entry.file) === file);
            const children = [];
            for (const collection of ['definitions', 'views', 'appearances'])
                for (const child of generated[collection]) {
                    for (const value of Object.values(child))
                        remap(value);
                    if ((0, index_js_1.listRecords)(this.bundle).some(existing => existing.file === file && (existing.record.id === child.id || child.name && existing.record.name === child.name))) {
                        error('collision', 'Generated template child identity or name collision', target);
                        continue;
                    }
                    array(document, collection).push(child);
                    if (collection === 'definitions')
                        children.push(child);
                    const binding = bindingCopies.get(child), content = (0, index_js_1.asRecord)(child.content);
                    if (binding)
                        this.fieldBindings.push({ file, field: child, ...(binding.domain !== undefined ? { domain: content.domain ?? binding.domain } : {}), ...(binding.key !== undefined ? { key: binding.key } : {}), ...(binding.constraints !== undefined ? { constraints: content.constraints ?? binding.constraints } : {}) });
                    if (collection === 'views')
                        array(document, 'placements').push({ id: (0, index_js_1.asString)(child.id) + '--placement', target: { file, id: (0, index_js_1.asString)(child.id) } });
                }
            const explicitlyPlaced = new Set(generated.appearances.map(a => (0, index_js_1.asString)((0, index_js_1.asRecord)(a.target).id)));
            for (const child of children) {
                if (!explicitlyPlaced.has((0, index_js_1.asString)(child.id)))
                    for (const occurrence of instanceAppearances) {
                        const parent = (0, index_js_1.asRecord)(occurrence.record.parent), owner = this.bundle.files.find(f => f.location === occurrence.file).document;
                        array(owner, 'appearances').push({ id: occurrence.ref.id + '--' + (0, index_js_1.asString)(child.id), target: { file, id: (0, index_js_1.asString)(child.id) }, parent });
                        const viewFile = (0, index_js_1.asString)(parent.file, occurrence.file), viewDocument = this.bundle.files.find(f => f.location === viewFile)?.document;
                        const view = (0, index_js_1.asArray)(viewDocument?.views).find(v => (0, index_js_1.asRecord)(v).id === parent.id);
                        if ((0, index_js_1.isRecord)(view))
                            this.selection(view, { file, id: (0, index_js_1.asString)(child.id) });
                    }
                expand(file, child, [...ancestry, templateKey]);
            }
            if (children.length) {
                const members = array(record, 'members');
                for (const child of children)
                    if (child.category !== 'relation' && !members.some(m => (0, index_js_1.asRecord)(m).file === file && (0, index_js_1.asRecord)(m).id === child.id))
                        members.push({ file, id: (0, index_js_1.asString)(child.id) });
            }
            stack.delete(key);
            expanded.add(key);
        };
        for (const item of (0, index_js_1.listRecords)(this.bundle))
            if (item.kind === 'definition')
                expand(item.file, item.record);
    }
    run() { this.parseFile(this.bundle.entry); this.resolve(); this.resolveFieldBindings(); this.expandTemplates(); this.resolveFieldBindings(); this.resolveChildren(); const checked = (0, index_js_1.listRecords)(this.bundle).filter(r => typeof r.record.id === 'string' && r.record.id.length > 0).map(r => r.ref); const unavailable = this.diagnostics.filter(d => ['include.missing', 'reference.unresolved', 'version.unsupported'].includes(d.code)).map(d => d.message); return { syntaxValid: !this.diagnostics.some(d => d.severity === 'error' && /^(syntax|property|table)\./.test(d.code)), normalized: this.bundle, documents: this.documents, diagnostics: this.diagnostics, coverage: { scope: { kind: 'workarea' }, complete: !this.diagnostics.some(d => d.severity === 'error'), checked, unavailable }, references: this.references }; }
}
function decodeSources(input, options = {}) {
    if (options.cancel?.aborted)
        return { syntaxValid: false, normalized: { version: 'ddn-next-1', entry: input.entry, files: [] }, documents: [], diagnostics: [{ code: 'decode.cancelled', severity: 'info', message: 'Decoding was cancelled' }], coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: ['cancelled'] }, references: [] };
    return new Decoder(input, options).run();
}
function allNodes(result) { const flatten = (nodes) => nodes.flatMap(n => [n, ...flatten(n.children)]); return result.documents.flatMap(d => flatten(d.nodes)); }
function findNode(result, target) { return allNodes(result).find(n => n.ref?.file === target.file && n.ref.id === target.id); }
function applySourcePatches(input, patches) {
    const selected = new Map();
    for (const file of input.files) {
        const location = (0, index_js_1.normalizeLocation)(file.id);
        if (selected.has(location))
            throw Error('Duplicate selected source location: ' + location);
        selected.set(location, file);
    }
    const planned = new Map();
    for (const patch of patches) {
        const location = (0, index_js_1.normalizeLocation)(patch.file), file = selected.get(location);
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
            const edits = planned.get((0, index_js_1.normalizeLocation)(file.id));
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
    if ((0, index_js_1.isRecord)(value) && (typeof value.id === 'string' || typeof value.name === 'string'))
        return (value.file ? quoteText((0, index_js_1.asString)(value.file)) + '::' : '') + quoteText((0, index_js_1.asString)(value.name, (0, index_js_1.asString)(value.id)));
    throw Error('Expected scalar value');
}
function quoteCell(text) {
    if (text.includes('\n'))
        throw Error('A quoted table cell cannot contain a line break');
    return '"' + text.replaceAll('"', '""') + '"';
}
function textBodyShape(shape) {
    const choices = variants(shape), types = choices.flatMap(choice => typeof choice.type === 'string' ? [choice.type] : choice.type ?? []);
    return types.includes('string') && !types.includes('object') && !types.includes('array') && !choices.some(choice => choice.properties);
}
function serializeList(values, indent, newline, shape) {
    return values.map(value => Array.isArray(value)
        ? value.length ? indent + 'item' + newline + serializeList(value, indent + '    ', newline, variants(shape).find(choice => choice.type === 'array')?.items) : indent + 'item empty list' + newline
        : (0, index_js_1.isRecord)(value)
            ? Object.keys(value).length ? indent + 'item' + newline + serializePropertyRecord(value, indent + '    ', newline, key => childShape(shape, key)) : indent + 'item empty record' + newline
            : indent + 'item ' + scalar(value) + newline).join('');
}
function serializePropertyRecord(properties, indent, newline, resolve) {
    return Object.entries(properties).map(([key, value]) => {
        (0, index_js_1.safePath)(key);
        const label = key === 'item' || /[\s"']/.test(key) ? quoteText(key) : key;
        const shape = resolve(key);
        if (Array.isArray(value))
            return value.length ? indent + label + newline + serializeList(value, indent + '    ', newline, variants(shape).find(choice => choice.type === 'array')?.items) : indent + label + ' empty list' + newline;
        if ((0, index_js_1.isRecord)(value))
            return Object.keys(value).length ? indent + label + newline + serializePropertyRecord(value, indent + '    ', newline, child => childShape(shape, child)) : indent + label + ' empty record' + newline;
        if (typeof value === 'string' && /[\r\n]/.test(value)) {
            if (!textBodyShape(shape))
                throw Error('Multiline text requires an unambiguous registered text-body property');
            return indent + label + newline + value.replace(/\r\n/g, '\n').split('\n').map(line => indent + '    ' + line).join(newline) + newline;
        }
        return indent + label + ' ' + scalar(value) + newline;
    }).join('');
}
function serializeProperties(properties, indent = '    ', newline = '\n') {
    return serializePropertyRecord(properties, indent, newline, key => ownerShape('definition', properties, key));
}
function patchProperty(result, target, path, value) {
    (0, index_js_1.safePath)(path);
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
        return replaceDraftBody(result, target, value, (0, index_js_1.asString)((0, index_js_1.asRecord)((0, index_js_1.findRecord)(result.normalized, target)?.draft).format, 'text'));
    if (node.implicit) {
        const occurrence = (0, index_js_1.findRecord)(result.normalized, target);
        const relationDisplay = ['label', 'legend'].includes(path.split('.')[0]) && (0, index_js_1.resolveReference)(result.normalized, target.file, occurrence?.target)?.record.category === 'relation';
        if (!['position', 'size', 'body', 'columns', 'pinned'].includes(path.split('.')[0]) && !relationDisplay)
            throw Error('An implicit occurrence supports only unambiguous appearance properties; author an explicit use occurrence for this property');
        const declaration = allNodes(result).find(n => !n.implicit && n.start === node.start && n.file === node.file);
        if (!declaration)
            throw Error('Implicit occurrence source is unavailable');
        node = declaration;
    }
    const document = result.documents.find(d => d.file.id === target.file);
    const entry = (0, index_js_1.listRecords)(result.normalized).find(record => record.ref.file === target.file && record.ref.id === target.id);
    const owner = entry?.kind === 'view' ? entry.record.kind === 'document' ? 'document' : 'view_definition' : { data: 'data_record', source: 'source_record', template: 'template_record' }[entry?.kind ?? ''] ?? entry?.kind ?? 'definition';
    const shape = ownerShape(owner, entry?.record ?? {}, path);
    const serializeValue = (key, value, indent) => serializePropertyRecord({ [key]: value }, indent, document.newline, () => shape);
    if (path === 'title' && node.titleStart !== undefined && node.titleEnd !== undefined)
        return [patch(result, target.file, node.titleStart, node.titleEnd, value === undefined ? '' : ': ' + scalar(value))];
    const properties = allNodes(result).filter(n => n.kind === 'property' && n.owner?.file === target.file && n.owner.id === target.id && (n.path === path || n.path?.startsWith(path + '.')));
    if (value === undefined) {
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
function deleteDeclaration(result, target) {
    const node = findNode(result, target);
    if (!node)
        throw Error('Declaration source is unavailable');
    if (node.generated || node.implicit)
        throw Error('Generated or implicit content must be edited through its owning source declaration');
    const document = result.documents.find(d => d.file.id === target.file);
    return [patch(result, target.file, node.start === 0 && document.bom ? 1 : node.start, node.end, '')];
}
function renameDeclaration(result, target, name) {
    name = name.normalize('NFC');
    if (!name.trim())
        throw Error('Name must not be empty');
    if ((0, index_js_1.listRecords)(result.normalized).some(x => x.file === target.file && x.record.name === name && x.ref.id !== target.id))
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
function appendDeclaration(result, file, text, parent) {
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
function encodeDefinition(record) {
    const role = (0, index_js_1.asString)(record.role, 'object'), name = typeof record.name === 'string' ? ' ' + quoteText(record.name) : '';
    const header = 'element' + name + ' as ' + quoteText(role) + (typeof record.title === 'string' ? ' : ' + quoteText(record.title) : '');
    const properties = { ...record };
    delete properties.name;
    delete properties.role;
    delete properties.title;
    delete properties.category;
    return header + (Object.keys(properties).length ? '\n    with\n' + serializePropertyRecord(properties, '        ', '\n', key => ownerShape('definition', record, key)) : '\n');
}
function sourceText(result, target) { return findNode(result, target)?.raw; }
function replaceRecordData(result, target, columns, rows) {
    const node = findNode(result, target), record = (0, index_js_1.findRecord)(result.normalized, target);
    if (!node || node.kind !== 'data' || !record)
        throw Error('Named dataset source is unavailable');
    if (record.source)
        throw Error('A provider-bound dataset must be edited through its provider');
    const document = result.documents.find(d => d.file.id === target.file);
    const properties = { ...record, columns: columns, rows: rows };
    delete properties.name;
    const comments = document.file.text.slice(node.bodyStart, node.end).split(/\r?\n/).filter(line => line.trimStart().startsWith('//'));
    const indent = ' '.repeat(node.indent + 4);
    const text = (comments.length ? comments.join(document.newline) + document.newline : '') + indent + 'with' + document.newline + serializePropertyRecord(properties, indent + '    ', document.newline, key => ownerShape('data_record', record, key));
    return [patch(result, target.file, node.bodyStart, node.end, text)];
}
function replaceDataBody(result, target, data) {
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
        const value = { columns: data.columns, rows: data.rows };
        return [...old.map(n => patch(result, target.file, n.start, n.end, '')), ...patchProperty(result, target, 'data', value)];
    }
    const depth = old[0]?.indent ?? childIndent(result, node);
    const indent = ' '.repeat(depth), rowIndent = ' '.repeat(old[0] && old[0].kind !== 'field-row' ? literalIndent(result, old[0]) : depth + (depth - node.indent));
    const header = data.columns.map(c => {
        const parts = [quoteText((0, index_js_1.asString)(c.id))];
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
function replaceDraftBody(result, target, text, format = 'text') {
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
function replaceNoteBody(result, target, text) {
    const node = findNode(result, target);
    if (!node || node.kind !== 'notes' || node.generated)
        throw Error('Raw note source is unavailable');
    const doc = result.documents.find(d => d.file.id === target.file);
    const indent = ' '.repeat(literalIndent(result, node));
    const prefix = node.bodyStart && !doc.file.text.slice(0, node.bodyStart).endsWith('\n') ? doc.newline : '';
    const body = text.replace(/\r\n/g, '\n').split('\n').map(line => indent + line).join(doc.newline) + doc.newline;
    return [patch(result, target.file, node.bodyStart, node.end, prefix + body)];
}

},
"language/src/schema.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.profiles = exports.coreTypes = exports.roleTypes = exports.shapes = void 0;
const schema_core_js_1 = require("profiles/src/schema-core.js");
function unfold(shape) {
    const seen = new Set();
    while (shape?.$ref) {
        const key = shape.$ref.split('/').at(-1);
        if (seen.has(key))
            break;
        seen.add(key);
        shape = schema_core_js_1.lexicalShapes[key];
    }
    return shape;
}
const genericOptions = unfold(unfold(schema_core_js_1.lexicalShapes.view_definition)?.properties?.projection)?.properties?.options;
const aliases = { boolean: 'bool', timestamp: 'instant' };
exports.shapes = new Proxy(schema_core_js_1.lexicalShapes, {
    get(target, key) {
        if (typeof key !== 'string')
            return undefined;
        const value = target[aliases[key] ?? key];
        if (value)
            return value;
        if (key.startsWith('profile_') && Object.hasOwn(schema_core_js_1.codex.knownProfiles, key.slice(8)))
            return genericOptions;
        return undefined;
    },
});
const descriptor = (entry) => ({ category: entry.category, schema: 'n' + entry.schema, core: entry.core });
exports.roleTypes = Object.fromEntries(Object.entries(schema_core_js_1.codex.roles).map(([key, value]) => [key, descriptor(value)]));
exports.coreTypes = Object.fromEntries(Object.entries(schema_core_js_1.codex.coreTypes).map(([key, value]) => [key, descriptor(value)]));
exports.profiles = Object.keys(schema_core_js_1.codex.knownProfiles);

},
"model/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.recordRef = exports.asString = exports.asArray = exports.asRecord = exports.isRecord = void 0;
exports.normalizedFiles = normalizedFiles;
exports.normalizeLocation = normalizeLocation;
exports.listRecords = listRecords;
exports.resolveReference = resolveReference;
exports.findRecord = findRecord;
exports.getPath = getPath;
exports.safePath = safePath;
exports.setPath = setPath;
exports.canonicalJson = canonicalJson;
const isRecord = (value) => value !== null && typeof value === 'object' && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
exports.isRecord = isRecord;
const asRecord = (value) => (0, exports.isRecord)(value) ? value : {};
exports.asRecord = asRecord;
const asArray = (value) => Array.isArray(value) ? value : [];
exports.asArray = asArray;
const asString = (value, fallback = '') => typeof value === 'string' ? value : fallback;
exports.asString = asString;
const recordRef = (file, record) => ({ file, id: (0, exports.asString)(record.id) });
exports.recordRef = recordRef;
function normalizedFiles(value) {
    if (!(0, exports.isRecord)(value) || !Array.isArray(value.files))
        return [];
    return value.files.filter(x => (0, exports.isRecord)(x) && typeof x.location === 'string' && (0, exports.isRecord)(x.document));
}
const scheme = /^[a-z][a-z0-9+.-]*:/i;
const hierarchical = /^[a-z][a-z0-9+.-]*:\//i;
function urlPath(value) {
    const remainder = value.replace(scheme, '');
    return (remainder.startsWith('//') ? remainder.slice(2).replace(/^[^/?#]*/, '') : remainder).split(/[?#]/, 1)[0];
}
function checkUrlNamespace(path) {
    let depth = 0;
    for (const part of path.split('/').slice(path.startsWith('/') ? 1 : 0)) {
        const dot = part.replace(/%2e/gi, '.');
        if (dot === '.')
            continue;
        if (dot === '..') {
            if (!depth)
                throw new Error('Location escapes selected file namespace');
            depth--;
        }
        else
            depth++;
    }
}
function normalizeLocation(value, fromFile = '') {
    if (typeof value !== 'string' || !value || typeof fromFile !== 'string' || /[\u0000-\u001f\u007f]/.test(value + fromFile))
        throw new Error('Location must be nonempty text without control characters');
    value = value.replaceAll('\\', '/');
    fromFile = fromFile.replaceAll('\\', '/');
    if (scheme.test(value) && !hierarchical.test(value))
        return value;
    if (hierarchical.test(value) || scheme.test(fromFile)) {
        if (!scheme.test(value) && !hierarchical.test(fromFile))
            throw new Error('Relative reference needs a hierarchical file location');
        const base = scheme.test(value) ? undefined : new URL(normalizeLocation(fromFile));
        const path = urlPath(value);
        const resolvedPath = scheme.test(value) || value.startsWith('/') || !base ? path
            : path ? base.pathname.slice(0, base.pathname.lastIndexOf('/') + 1) + path : base.pathname;
        checkUrlNamespace(resolvedPath);
        const resolved = new URL(value.replaceAll(' ', '%20'), base);
        if (resolved.host && (scheme.test(value) || value.startsWith('//')) && !/^(?:[a-z][a-z0-9+.-]*:)?\/\/[^/?#]+/i.test(value))
            throw new Error('Hierarchical URL authority must be explicit');
        if (resolved.hostname)
            resolved.hostname = resolved.hostname.toLowerCase();
        return resolved.href;
    }
    const base = fromFile.includes('/') ? fromFile.slice(0, fromFile.lastIndexOf('/') + 1) : '';
    const parts = [];
    for (const part of (value.startsWith('/') ? value : base + value).split('/')) {
        if (!part || part === '.')
            continue;
        if (part === '..') {
            if (!parts.length)
                throw new Error('Location escapes selected file namespace');
            parts.pop();
        }
        else
            parts.push(part.normalize('NFC'));
    }
    if (!parts.length)
        throw new Error('Location must not be empty');
    return (value.startsWith('/') || base.startsWith('/') ? '/' : '') + parts.join('/');
}
const collections = [['definitions', 'definition'], ['views', 'view'], ['placements', 'placement'], ['appearances', 'appearance'], ['data', 'data'], ['sources', 'source'], ['assets', 'asset'], ['templates', 'template'], ['publications', 'publication']];
function listRecords(bundle) {
    const records = [];
    for (const { location: file, document } of normalizedFiles(bundle)) {
        const add = (record, kind) => {
            records.push({ file, kind, record, ref: (0, exports.recordRef)(file, record) });
            for (const note of (0, exports.asArray)(record.notes))
                if ((0, exports.isRecord)(note))
                    records.push({ file, kind: 'note', record: note, ref: (0, exports.recordRef)(file, note) });
        };
        if ((0, exports.isRecord)(document.workarea))
            add(document.workarea, 'workarea');
        for (const [key, kind] of collections)
            for (const record of (0, exports.asArray)(document[key]))
                if ((0, exports.isRecord)(record))
                    add(record, kind);
    }
    return records;
}
function resolveReference(bundle, fromFile, reference) {
    if (!(0, exports.isRecord)(reference))
        return undefined;
    const file = (0, exports.asString)(reference.file, fromFile);
    const id = (0, exports.asString)(reference.id), name = (0, exports.asString)(reference.name).normalize('NFC');
    if (!file || (!id && !name) || (reference.id !== undefined && !id) || (reference.name !== undefined && !name)
        || (reference.file !== undefined && typeof reference.file !== 'string'))
        return undefined;
    const records = listRecords(bundle).filter(x => x.file === file);
    const byId = id ? records.filter(x => x.record.id === id) : [];
    const byName = name ? records.filter(x => typeof x.record.name === 'string' && x.record.name.normalize('NFC') === name) : [];
    if ((id && byId.length !== 1) || (name && byName.length !== 1))
        return undefined;
    if (id && name && byId[0] !== byName[0])
        return undefined;
    const target = id ? byId[0] : byName[0];
    if (!target?.ref.id || (!id && records.filter(x => x.record.id === target.ref.id).length !== 1))
        return undefined;
    return target;
}
function findRecord(bundle, ref) {
    return resolveReference(bundle, ref.file, { file: ref.file, id: ref.id })?.record;
}
function getPath(value, path) {
    let current = value;
    for (const key of safePath(path))
        current = (0, exports.isRecord)(current) ? current[key] : undefined;
    return current;
}
function safePath(path) {
    const parts = path.split('.');
    if (parts.some(x => !x || ['__proto__', 'constructor', 'prototype'].includes(x)))
        throw new Error('Unsafe or empty property path');
    return parts;
}
function setPath(record, path, value) {
    const parts = safePath(path);
    let current = record;
    for (const key of parts.slice(0, -1)) {
        if (!(0, exports.isRecord)(current[key]))
            current[key] = {};
        current = current[key];
    }
    const key = parts[parts.length - 1];
    if (value === undefined)
        delete current[key];
    else
        current[key] = value;
}
function canonicalJson(value) {
    if (Array.isArray(value))
        return '[' + value.map(canonicalJson).join(',') + ']';
    if ((0, exports.isRecord)(value))
        return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonicalJson(value[k])).join(',') + '}';
    return JSON.stringify(value) ?? 'null';
}

},
"profiles/src/view-surfaces.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.VIEW_SURFACE_PRESETS = void 0;
exports.getViewSurfacePreset = getViewSurfacePreset;
exports.VIEW_SURFACE_PRESETS = Object.freeze([
    { id: 'dynamic', label: 'Dynamic', description: 'The view grows and shrinks with its diagram content.', width: null, height: null, scale: 1 },
    { id: 'tv-hd', label: 'HD', description: '1280 × 720 pixels · 16:9 dashboard for an HD display.', width: 1280, height: 720, scale: 2 / 3 },
    { id: 'tv-fhd', label: 'Full HD', description: '1920 × 1080 pixels · 16:9 dashboard for a Full HD display.', width: 1920, height: 1080, scale: 1 },
    { id: 'tv-2k', label: '2K', description: '2048 × 1080 pixels · the 2K format, distinct from 2560 × 1440 QHD.', width: 2048, height: 1080, scale: 1 },
    { id: 'tv-qhd', label: 'QHD', description: '2560 × 1440 pixels · 16:9 dashboard for a QHD display.', width: 2560, height: 1440, scale: 4 / 3 },
    { id: 'tv-4k', label: '4K UHD', description: '3840 × 2160 pixels · 16:9 dashboard for a 4K UHD display.', width: 3840, height: 2160, scale: 2 },
    { id: 'tv-8k', label: '8K UHD', description: '7680 × 4320 pixels · 16:9 dashboard for an 8K UHD display.', width: 7680, height: 4320, scale: 4 },
].map(preset => Object.freeze(preset)));
function getViewSurfacePreset(id) {
    return exports.VIEW_SURFACE_PRESETS.find(preset => preset.id === id);
}

},
"verifier/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.verifyDecoded = verifyDecoded;
exports.createVerifier = createVerifier;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("execution/src/index.js");
const index_js_3 = require("model/src/index.js");
const core_js_1 = require("profiles/src/core.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const index_js_4 = require("defaults/src/index.js");
const levelOrder = ['decode', 'structural', 'semantic', 'review', 'publication'];
const decodedVerifiers = new WeakMap();
function verifyDecoded(verifier, input, options, diagnostics) {
    const run = decodedVerifiers.get(verifier);
    if (!run)
        throw new TypeError('Expected an instance created by createVerifier');
    return run(input, options, diagnostics);
}
const refKey = (r) => r.file + '\0' + r.id;
const equal = (a, b) => (0, schema_core_js_1.stableStringify)(a) === (0, schema_core_js_1.stableStringify)(b);
const severity = (diagnostics) => diagnostics.some(d => d.severity === 'error');
function issue(code, message, target) { return { code, severity: 'error', message, ...(target ? { target } : {}) }; }
const recordIndexes = new WeakMap();
function indexCapturedRecords(records) {
    const result = { ids: new Map(), names: new Map(), paths: new Map(), collections: new Map() };
    const append = (map, key, record) => {
        const found = map.get(key);
        if (found)
            found.push(record);
        else
            map.set(key, [record]);
    };
    for (const record of records) {
        append(result.ids, refKey(record.ref), record);
        if (typeof record.record.name === 'string')
            append(result.names, record.file + '\0' + record.record.name, record);
        const path = record.file + '\0' + record.path;
        if (record.path && !result.paths.has(path))
            result.paths.set(path, record);
        const collection = record.file + '\0' + record.collection + '\0' + (record.collection === 'workarea' ? 0 : record.index);
        if (!result.collections.has(collection))
            result.collections.set(collection, record);
    }
    recordIndexes.set(records, result);
    return result;
}
function resolveRecord(records, file, reference) {
    const index = recordIndexes.get(records);
    if (!index)
        return (0, core_js_1.resolveRecord)(records, file, reference);
    if (!(0, schema_core_js_1.isRecord)(reference))
        return undefined;
    const targetFile = typeof reference.file === 'string' ? reference.file : file;
    const id = typeof reference.id === 'string', name = typeof reference.name === 'string';
    const candidates = id ? index.ids.get(targetFile + '\0' + reference.id) : name ? index.names.get(targetFile + '\0' + reference.name) : undefined;
    const matches = id && name ? candidates?.filter(record => record.record.name === reference.name) : candidates;
    return matches?.length === 1 ? matches[0] : undefined;
}
function containingRecord(records, file, path) {
    const lookup = recordIndexes.get(records);
    if (lookup) {
        let parent = path;
        while (parent) {
            const found = lookup.paths.get(file + '\0' + parent);
            if (found)
                return found;
            parent = parent.slice(0, parent.lastIndexOf('/'));
        }
        const parts = path.split('/'), collection = parts[1];
        return lookup.collections.get(file + '\0' + collection + '\0' + (collection === 'workarea' ? 0 : Number(parts[2])));
    }
    const nested = records.filter(r => r.file === file && r.path && (path === r.path || path.startsWith(r.path + '/'))).sort((a, b) => (b.path?.length ?? 0) - (a.path?.length ?? 0))[0];
    if (nested)
        return nested;
    const parts = path.split('/');
    const collection = parts[1], index = Number(parts[2]);
    if (collection === 'workarea')
        return records.find(x => x.file === file && x.collection === 'workarea');
    return records.find(x => x.file === file && x.collection === collection && x.index === index);
}
function status(record) { const value = (0, schema_core_js_1.getPath)(record, 'design.state'); return typeof value === 'string' ? value : 'draft'; }
function captureOptions(input) {
    if (!input || typeof input !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(input)))
        throw Error('Expected plain verification options');
    const descriptors = Object.getOwnPropertyDescriptors(input);
    if (Object.values(descriptors).some(descriptor => !('value' in descriptor)))
        throw Error('Verification options cannot contain accessors');
    const { cancel, ...data } = input;
    return Object.freeze({ ...(0, index_js_2.freeze)((0, index_js_2.clone)(data)), ...(cancel ? { cancel } : {}) });
}
function validRef(value) { return (0, schema_core_js_1.isRecord)(value) && typeof value.file === 'string' && !!value.file && typeof value.id === 'string' && !!value.id; }
function validScope(value) { return (0, schema_core_js_1.isRecord)(value) && (value.kind === 'workarea' || ['item', 'view', 'document'].includes(String(value.kind)) && validRef(value.target)); }
function boundedClone(value, context, account = () => { }) {
    const active = new Set(), stack = [{ value, depth: 0 }];
    let bytes = 0, units = 0;
    while (stack.length) {
        context.check();
        const item = stack.pop(), current = item.value;
        if (item.exit) {
            active.delete(current);
            continue;
        }
        units++;
        if (item.depth > 136 || context.task.budget && units + context.stats.workUnits > context.task.budget.workUnits)
            throw new index_js_2.ComputationStopped('budget-exceeded', 'Verification input exceeds the bounded capture budget');
        if (current && typeof current === 'object') {
            if (active.has(current))
                throw Error('Cyclic verification input');
            if (!Array.isArray(current) && ![Object.prototype, null].includes(Object.getPrototypeOf(current)))
                throw Error('Expected plain verification data');
            active.add(current);
            stack.push({ value: current, depth: item.depth, exit: true });
            for (const [key, descriptor] of Object.entries(Object.getOwnPropertyDescriptors(current))) {
                if (!descriptor.enumerable)
                    continue;
                if (!('value' in descriptor))
                    throw Error('Verification data cannot contain accessors');
                bytes += key.length * 2;
                stack.push({ value: descriptor.value, depth: item.depth + 1 });
            }
        }
        else
            bytes += typeof current === 'string' ? current.length * 2 : 8;
        context.accountMemory(bytes);
    }
    const copy = (0, index_js_2.clone)(value);
    account(units);
    return copy;
}
function captureSources(input, context) {
    const data = (value) => {
        if (!value || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
            throw Error('Expected plain source records');
        const fields = Object.getOwnPropertyDescriptors(value);
        if (Object.values(fields).some(field => !('value' in field)))
            throw Error('Source records cannot contain accessors');
        return fields;
    };
    const root = data(input), entry = (0, index_js_3.normalizeLocation)(root.entry?.value);
    const values = root.files?.value;
    if (!Array.isArray(values))
        throw Error('Source files must be an array');
    const fields = Object.getOwnPropertyDescriptors(values);
    const files = [];
    let bytes = 0;
    for (let i = 0; i < values.length; i++) {
        const item = fields[String(i)];
        if (!item || !('value' in item))
            throw Error('Source files must be dense data');
        const file = data(item.value), id = (0, index_js_3.normalizeLocation)(file.id?.value), text = file.text?.value, revision = file.revision?.value;
        if (typeof text !== 'string' || typeof revision !== 'string' || !revision || file.encoding?.value !== 'utf-8' || typeof file.writable?.value !== 'boolean')
            throw Error('Malformed source file');
        bytes += text.length * 2;
        context.accountMemory(bytes);
        context.check();
        const original = file.originalBytes?.value;
        if (original !== undefined) {
            if (!(original instanceof Uint8Array))
                throw Error('Source bytes must be Uint8Array');
            context.accountMemory(bytes + original.byteLength);
            const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(original);
            if (decoded !== text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === text))
                throw Error('Source bytes do not match decoded text');
        }
        files.push({ id, text, revision, encoding: 'utf-8', writable: file.writable.value });
    }
    return { entry, files };
}
function reachedFiles(input) {
    const files = new Map((0, core_js_1.bundleFiles)(input.normalized).map(file => [file.location, file]));
    const reached = new Set(), pending = [input.rootFile];
    while (pending.length) {
        const next = pending.pop();
        if (reached.has(next) || !files.has(next))
            continue;
        reached.add(next);
        const includes = files.get(next).document.includes;
        for (const value of Array.isArray(includes) ? includes : [])
            if (typeof value === 'string') {
                const location = files.has(value) ? value : (0, core_js_1.safeLocation)(next, value);
                if (location)
                    pending.push(location);
            }
    }
    return reached;
}
function ruleResult(value, options, input, records, selected) {
    const result = (0, index_js_2.freeze)((0, index_js_2.clone)(value));
    const reference = (ref) => validRef(ref) && selected.has(refKey(ref)) && !!resolveRecord(records, ref.file, ref);
    const span = (value) => (0, schema_core_js_1.isRecord)(value) && typeof value.file === 'string' && typeof value.revision === 'string' && input.revision.sources[value.file] === value.revision && records.some(record => record.file === value.file && selected.has(refKey(record.ref))) && Number.isSafeInteger(value.start) && Number.isSafeInteger(value.end) && Number(value.start) >= 0 && Number(value.end) >= Number(value.start);
    if (!result || !['valid', 'invalid', 'incomplete', 'unsupported', 'budget-exceeded', 'cancelled', 'stale'].includes(result.outcome)
        || !Array.isArray(result.diagnostics) || !Array.isArray(result.dependencies) || !(0, schema_core_js_1.isRecord)(result.coverage)
        || !equal(result.coverage.scope, options.scope) || typeof result.coverage.complete !== 'boolean'
        || !Array.isArray(result.coverage.checked) || !result.coverage.checked.every(reference)
        || !Array.isArray(result.coverage.unavailable) || result.coverage.unavailable.some(item => typeof item !== 'string' || !item)
        || result.coverage.complete && result.coverage.unavailable.length)
        throw Error('Rule returned malformed or inconsistent coverage/outcome');
    for (const diagnostic of result.diagnostics) {
        if (!(0, schema_core_js_1.isRecord)(diagnostic) || typeof diagnostic.code !== 'string' || !diagnostic.code || typeof diagnostic.message !== 'string' || !['info', 'warning', 'error'].includes(String(diagnostic.severity))
            || diagnostic.target !== undefined && !reference(diagnostic.target) || diagnostic.source !== undefined && !span(diagnostic.source)
            || diagnostic.related !== undefined && (!Array.isArray(diagnostic.related) || !diagnostic.related.every(span)))
            throw Error('Rule returned an invalid diagnostic');
    }
    for (const dependency of result.dependencies)
        if (!(0, schema_core_js_1.isRecord)(dependency) || !reference(dependency.target) || typeof dependency.path !== 'string' || typeof dependency.fingerprint !== 'string' || !dependency.fingerprint)
            throw Error('Rule returned an unavailable or malformed dependency');
    return result;
}
function createVerifier(runtimeOptions) {
    let destroyed = false, serial = 0;
    const packs = runtimeOptions.packs.map(pack => ({ manifest: (0, index_js_2.freeze)((0, index_js_2.clone)(pack.manifest)), registrations: {
            profiles: (0, index_js_2.freeze)((0, index_js_2.clone)(pack.registrations.profiles ?? [])),
            rules: (pack.registrations.rules ?? []).map(rule => { const { evaluate, ...data } = rule; return (0, index_js_2.freeze)({ ...(0, index_js_2.clone)(data), evaluate }); }),
        } }));
    const profileDescriptors = new Map(packs.flatMap(p => p.registrations.profiles ?? []).map(p => [p.id, p]));
    const rules = packs.flatMap(p => p.registrations.rules ?? []);
    const versions = (0, index_js_2.freeze)((0, index_js_2.clone)(runtimeOptions.versions));
    const limits = runtimeOptions.limits ? (0, index_js_2.freeze)((0, index_js_2.clone)(runtimeOptions.limits)) : undefined;
    const destroyListeners = new Set();
    const liveTask = (options) => ({ ...options, cancel: {
            get aborted() { return destroyed || !!options.cancel?.aborted; },
            onAbort(handler) { destroyListeners.add(handler); const stop = options.cancel?.onAbort(handler); return () => { destroyListeners.delete(handler); stop?.(); }; },
        } });
    const capabilities = [];
    if (versions.api !== '1.0' || versions.language !== 'ddn-next-1' || versions.defaults !== 'ddn-next-1')
        capabilities.push(issue('DDN-VERSION', 'Unsupported utility API, language or defaults version'));
    const ids = new Set();
    for (const pack of packs) {
        if (ids.has(pack.manifest.id))
            capabilities.push(issue('DDN-PACK-DUPLICATE', 'Duplicate pack ' + pack.manifest.id));
        ids.add(pack.manifest.id);
        if (versions.packs[pack.manifest.id] !== undefined && versions.packs[pack.manifest.id] !== pack.manifest.version)
            capabilities.push(issue('DDN-PACK-VERSION', 'Installed pack differs from selected version: ' + pack.manifest.id));
        if (pack.manifest.api !== versions.api || !pack.manifest.languages.includes(versions.language) || !pack.manifest.defaults.includes(versions.defaults))
            capabilities.push(issue('DDN-PACK-VERSION', 'Incompatible pack ' + pack.manifest.id));
    }
    for (const id of Object.keys(versions.packs))
        if (!ids.has(id))
            capabilities.push(issue('DDN-PACK-MISSING', 'Selected pack is unavailable: ' + id));
    for (const pack of packs)
        for (const dependency of pack.manifest.dependencies)
            if (!ids.has(dependency))
                capabilities.push(issue('DDN-PACK-DEPENDENCY', 'Missing pack dependency ' + dependency));
    const graph = new Map(packs.map(p => [p.manifest.id, p.manifest.dependencies]));
    const walked = new Set(), active = new Set();
    function checkPack(id) {
        if (active.has(id)) {
            capabilities.push(issue('DDN-PACK-CYCLE', 'Pack dependency cycle at ' + id));
            return;
        }
        if (walked.has(id))
            return;
        active.add(id);
        for (const next of graph.get(id) ?? [])
            checkPack(next);
        active.delete(id);
        walked.add(id);
    }
    for (const id of graph.keys())
        checkPack(id);
    const seenRules = new Set(['ddn.structure', 'ddn.lifecycle']);
    for (const rule of rules) {
        if (seenRules.has(rule.id))
            capabilities.push(issue('DDN-RULE-DUPLICATE', 'Duplicate rule ' + rule.id));
        seenRules.add(rule.id);
        if (!rule.id || !rule.version || typeof rule.evaluate !== 'function' || !Array.isArray(rule.readPaths) || rule.readPaths.some(path => typeof path !== 'string') || !Array.isArray(rule.levels) || rule.levels.some(level => !levelOrder.includes(level)) || !Array.isArray(rule.purposes) || !Array.isArray(rule.profiles))
            capabilities.push(issue('DDN-RULE-REGISTRATION', 'Malformed rule registration: ' + rule.id));
    }
    const seenProfiles = new Set();
    for (const pack of packs)
        for (const profile of pack.registrations.profiles) {
            if (seenProfiles.has(profile.id))
                capabilities.push(issue('DDN-PROFILE-DUPLICATE', 'Duplicate profile ' + profile.id));
            seenProfiles.add(profile.id);
            if (!pack.manifest.profiles.includes(profile.id) || !Array.isArray(profile.ruleIds) || profile.ruleIds.some(id => typeof id !== 'string' || !id))
                capabilities.push(issue('DDN-PROFILE-REGISTRATION', 'Malformed or undeclared profile ' + profile.id));
        }
    const cache = new Map();
    const ruleCache = new Map();
    async function verify(inputArgument, optionsArgument, decodeDiagnostics = []) {
        const requestId = 'verify-' + (++serial);
        const started = Date.now();
        let input = { contract: 'ddn-next-1', rootFile: '', revision: { model: '', sources: {}, data: {} }, versions, semanticFingerprint: '', normalized: null, coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: [] } };
        let options = { scope: { kind: 'workarea' }, purpose: '', level: 'decode' };
        const diagnostics = [];
        const missing = new Set();
        const checked = [];
        let task = {};
        let context = (0, index_js_2.createContext)(versions);
        let outcome = 'valid';
        let complete = true;
        let pendingWork = 0;
        const ruleVersions = { 'ddn.structure': '1.0.0', 'ddn.lifecycle': '1.0.0' };
        const schemaAccount = (units) => {
            pendingWork += units;
            context.check();
            if (task.budget && context.stats.workUnits + pendingWork > task.budget.workUnits)
                throw new index_js_2.ComputationStopped('budget-exceeded', 'Schema work budget exhausted');
        };
        let reviewEligible = false;
        let cacheHits = 0;
        const report = () => (0, index_js_2.freeze)({ requestId, outcome, revision: input.revision, versions: input.versions, dependencyFingerprint: input.semanticFingerprint, scope: options.scope, purpose: options.purpose, level: options.level, coverage: { scope: options.scope, complete, checked: [...new Map(checked.map(r => [refKey(r), r])).values()], unavailable: [...missing] }, diagnostics, missing: [...missing], ruleVersions, reviewEligible, stats: { elapsedMs: Date.now() - started, workUnits: context.stats.workUnits + pendingWork, cacheHits } });
        try {
            options = captureOptions(optionsArgument);
            task = { ...options, ...(!options.budget && limits ? { budget: limits } : {}) };
            const cacheAllowed = !task.budget && !task.cancel;
            context = (0, index_js_2.createContext)(versions, liveTask(task));
            context.check();
            const captured = boundedClone(inputArgument, context, units => pendingWork += units);
            if (!(0, schema_core_js_1.isRecord)(captured) || typeof captured.rootFile !== 'string' || typeof captured.semanticFingerprint !== 'string' || !(0, schema_core_js_1.isRecord)(captured.revision)
                || typeof captured.revision.model !== 'string' || !(0, schema_core_js_1.isRecord)(captured.revision.sources) || !(0, schema_core_js_1.isRecord)(captured.revision.data)
                || Object.values(captured.revision.sources).some(value => typeof value !== 'string') || Object.values(captured.revision.data).some(value => typeof value !== 'string')
                || !(0, schema_core_js_1.isRecord)(captured.versions) || !(0, schema_core_js_1.isRecord)(captured.coverage) || !validScope(captured.coverage.scope) || typeof captured.coverage.complete !== 'boolean'
                || !Array.isArray(captured.coverage.checked) || !captured.coverage.checked.every(validRef) || !Array.isArray(captured.coverage.unavailable)
                || captured.coverage.unavailable.some(value => typeof value !== 'string'))
                throw Error('Malformed model snapshot envelope');
            input = (0, index_js_2.freeze)(captured);
            diagnostics.push(...(0, index_js_2.clone)(decodeDiagnostics));
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            if (destroyed)
                throw new index_js_2.ComputationStopped('cancelled', 'Verifier has been destroyed');
            context.check();
            if (!levelOrder.includes(options.level))
                throw new Error('Unknown verification level');
            if (!validScope(options.scope) || typeof options.purpose !== 'string' || !options.purpose)
                throw Error('Verification requires an explicit valid scope and purpose');
            if (capabilities.length || input.contract !== 'ddn-next-1' || !equal(input.versions, versions)) {
                diagnostics.push(...capabilities, issue('DDN-VERSION', 'Snapshot version set must match this verifier'));
                outcome = 'unsupported';
                complete = false;
                missing.add('compatible-version-set');
                return report();
            }
            const activeValues = new Set();
            const scan = [{ value: input.normalized, depth: 0 }];
            let bytes = 0;
            while (scan.length) {
                const item = scan.pop();
                const value = item.value;
                context.check();
                if (item.exit) {
                    activeValues.delete(value);
                    continue;
                }
                if (item.depth > 128)
                    throw new index_js_2.ComputationStopped('budget-exceeded', 'Structured input depth exceeds the verifier bound');
                if (value && typeof value === 'object') {
                    if (activeValues.has(value))
                        throw new Error('Cyclic input is not JSON');
                    if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)
                        throw new Error('Only plain JSON records are permitted');
                    activeValues.add(value);
                    scan.push({ value, depth: item.depth, exit: true });
                    for (const [key, child] of Object.entries(value)) {
                        bytes += key.length * 2;
                        scan.push({ value: child, depth: item.depth + 1 });
                    }
                }
                else if (value === null || typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value))
                    bytes += typeof value === 'string' ? value.length * 2 : 8;
                else
                    throw new Error('Non-JSON value');
                context.accountMemory(bytes);
            }
            if (input.semanticFingerprint !== (0, index_js_2.fingerprint)(input.normalized)) {
                diagnostics.push(issue('DDN-SNAPSHOT-FINGERPRINT', 'Snapshot semantic fingerprint does not match its data'));
                outcome = 'invalid';
                complete = false;
                return report();
            }
            const key = (0, index_js_2.fingerprint)([input.rootFile, input.normalized, input.revision, input.coverage, options.scope, options.level, options.purpose, options.measurement ?? null, versions, packs.map(p => p.manifest)]);
            if (!decodeDiagnostics.length && cacheAllowed) {
                const previous = cache.get(key);
                if (previous)
                    return (0, index_js_2.freeze)({ ...previous, requestId, stats: { elapsedMs: Date.now() - started, workUnits: context.stats.workUnits + pendingWork, cacheHits: 1 } });
            }
            if (diagnostics.some(d => d.code === 'version.unsupported')) {
                outcome = 'unsupported';
                complete = false;
                missing.add('language-version');
                return report();
            }
            if (severity(diagnostics)) {
                outcome = 'invalid';
                complete = false;
                return report();
            }
            if (options.level === 'decode') {
                reviewEligible = false;
                complete = input.coverage.complete && !input.coverage.unavailable.length;
                for (const value of input.coverage.unavailable)
                    missing.add(value);
                return report();
            }
            const fileRows = (0, core_js_1.bundleFiles)(input.normalized);
            const records = (0, core_js_1.indexRecords)(input.normalized);
            const recordIndex = indexCapturedRecords(records);
            context.accountMemory((0, schema_core_js_1.stableStringify)(input.normalized).length * 2);
            const schemaReferences = [];
            const files = new Map(fileRows.map(f => [f.location, f]));
            if (!(0, schema_core_js_1.isRecord)(input.normalized) || input.normalized.entry !== input.rootFile)
                diagnostics.push(issue('DDN-ENTRY', 'Snapshot root must match the normalized entry file'));
            if (files.size !== fileRows.length)
                diagnostics.push(issue('DDN-FILE-DUPLICATE', 'Physical file locations must be unique'));
            if (!files.has(input.rootFile))
                diagnostics.push(issue('DDN-ENTRY', 'The entry file is unavailable'));
            const reachable = new Set(), pending = [input.rootFile];
            while (pending.length) {
                const name = pending.pop();
                if (reachable.has(name))
                    continue;
                reachable.add(name);
                const file = files.get(name);
                if (!file) {
                    missing.add(name);
                    continue;
                }
                await context.checkpoint(1);
                const includes = file.document.includes;
                if (Array.isArray(includes))
                    for (const value of includes) {
                        if (typeof value !== 'string')
                            continue;
                        const location = files.has(value) ? value : (0, core_js_1.safeLocation)(name, value);
                        if (location)
                            pending.push(location);
                        else
                            diagnostics.push(issue('DDN-INCLUDE-PATH', 'Invalid include location ' + value));
                    }
            }
            const validationFiles = (0, schema_core_js_1.isRecord)(input.normalized) && Array.isArray(input.normalized.files) ? input.normalized.files.filter(file => !(0, schema_core_js_1.isRecord)(file) || typeof file.location !== 'string' || reachable.has(file.location)) : undefined;
            const activeNormalized = (0, schema_core_js_1.isRecord)(input.normalized) ? { ...input.normalized, ...(validationFiles ? { files: validationFiles } : {}) } : input.normalized;
            const bundleIssues = (0, schema_core_js_1.validateSchema)('bundle', activeNormalized, { checkpoint: schemaAccount, maxIssues: 200 });
            if (bundleIssues.some(issue => issue.keyword === 'depth'))
                throw new index_js_2.ComputationStopped('budget-exceeded', 'Schema recursion bound exceeded');
            if (bundleIssues.length >= 200)
                throw new index_js_2.ComputationStopped('budget-exceeded', 'Schema diagnostic limit prevents proving complete scoped validation');
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            const root = files.get(input.rootFile)?.document;
            const wa = (0, schema_core_js_1.isRecord)(root?.workarea) ? root.workarea : {};
            const standaloneViews = wa.mode === 'standalone' ? records.filter(record => reachable.has(record.file) && (record.owner === 'view_definition' || record.owner === 'document')) : undefined;
            const activeWorkarea = records.find(record => record.file === input.rootFile && record.owner === 'workarea');
            if (standaloneViews && standaloneViews.length > 1)
                diagnostics.push(issue('DDN-STANDALONE-VIEWS', 'A standalone workarea can contain only one view or document across its included files', activeWorkarea?.ref));
            const method = typeof wa.method === 'string' ? wa.method : 'ddn';
            const allowedForeign = typeof wa.allow_foreign_views === 'boolean' ? wa.allow_foreign_views : method === 'ddn';
            const methodNames = { MT01: 'ddn', MT02: 'uml', MT03: 'chen', MT04: 'flowchart', MT05: 'bpmn', MT06: 'cmmn', MT07: 'dmn', MT08: 'c4', MT09: 'dfd', MT10: 'sysml', MT11: 'archimate', MT12: 'epc', MT13: 'idef0', MT14: 'petri', MT15: 'orm', MT16: 'vsm', MT17: 'sdl', MT18: 'msc', MT19: 'soaml', MT20: 'uaf', MT21: 'electrical' };
            const byIdentity = new Set(), byName = new Set();
            for (const record of records) {
                if (!reachable.has(record.file))
                    continue;
                await context.checkpoint(1);
                const k = refKey(record.ref);
                if (byIdentity.has(k))
                    diagnostics.push(issue('DDN-ID-DUPLICATE', 'Stable identity is repeated in its physical file', record.ref));
                byIdentity.add(k);
                if (typeof record.record.name === 'string') {
                    const nk = record.file + '\0' + record.record.name.normalize('NFC');
                    if (byName.has(nk))
                        diagnostics.push(issue('DDN-NAME-DUPLICATE', 'Declared names must be unique within a physical file', record.ref));
                    byName.add(nk);
                }
            }
            for (const file of fileRows) {
                if (!reachable.has(file.location))
                    continue;
                (0, schema_core_js_1.validateSchema)('file', file.document, { maxIssues: 0, checkpoint: schemaAccount, reference: (value, path) => schemaReferences.push({ file: file.location, path, value }) });
            }
            await context.checkpoint(pendingWork);
            pendingWork = 0;
            const dependencies = new Map();
            const target = options.scope.kind === 'workarea' ? undefined : resolveRecord(records, options.scope.target.file, options.scope.target);
            const selected = new Set();
            if (options.scope.kind === 'workarea') {
                for (const record of records)
                    if (reachable.has(record.file) && !(record.owner === 'workarea' && record.file !== input.rootFile))
                        selected.add(refKey(record.ref));
            }
            else if (target && reachable.has(target.file) && (options.scope.kind !== 'view' || target.owner === 'view_definition') && (options.scope.kind !== 'document' || target.owner === 'document') && (target.owner !== 'workarea' || target.file === input.rootFile)) {
                selected.add(refKey(target.ref));
                if (target.owner === 'view_definition' || target.owner === 'document')
                    for (const record of records) {
                        if (record.owner !== 'appearance')
                            continue;
                        const parent = resolveRecord(records, record.file, record.record.parent);
                        if (parent && refKey(parent.ref) === refKey(target.ref))
                            selected.add(refKey(record.ref));
                    }
            }
            else {
                diagnostics.push(issue('DDN-SCOPE', 'Requested scope does not resolve'));
                complete = false;
            }
            const referenceDiagnostics = [];
            for (const reference of schemaReferences) {
                const fragmentMatch = /^\/templates\/(\d+)\/fragment(?:\/|$)/.exec(reference.path);
                if (fragmentMatch) {
                    const template = records.find(r => r.file === reference.file && r.collection === 'templates' && r.index === Number(fragmentMatch[1]));
                    const fragment = template?.record.fragment;
                    if ((0, schema_core_js_1.isRecord)(fragment)) {
                        const local = (0, core_js_1.indexRecords)({ files: [{ location: reference.file, document: fragment }] });
                        if (resolveRecord(local, reference.file, reference.value))
                            continue;
                    }
                }
                const owner = containingRecord(records, reference.file, reference.path);
                const destination = resolveRecord(records, reference.file, reference.value);
                const file = typeof reference.value.file === 'string' ? reference.value.file : reference.file;
                if (!reachable.has(file) || !destination) {
                    referenceDiagnostics.push({ owner, diagnostic: issue('DDN-REFERENCE', 'Reference does not resolve within the supplied include closure' + (reference.path ? ' at ' + reference.path : ''), owner?.ref) });
                    continue;
                }
                if (owner) {
                    const set = dependencies.get(refKey(owner.ref)) ?? new Set();
                    set.add(refKey(destination.ref));
                    dependencies.set(refKey(owner.ref), set);
                }
                if (typeof reference.value.revision === 'string' && reference.value.revision !== input.revision.sources[file])
                    referenceDiagnostics.push({ owner, diagnostic: issue('DDN-REFERENCE-REVISION', 'Pinned reference revision is unavailable', owner?.ref) });
            }
            if (target && target.owner === 'definition') {
                const owners = new Set((0, core_js_1.enclosingDefinitions)(records, target).map(r => refKey(r.ref)));
                for (const owner of owners)
                    selected.add(owner);
                for (const occurrence of records.filter(r => r.owner === 'appearance')) {
                    const definition = resolveRecord(records, occurrence.file, occurrence.record.target);
                    if (definition && owners.has(refKey(definition.ref))) {
                        selected.add(refKey(occurrence.ref));
                        const parent = resolveRecord(records, occurrence.file, occurrence.record.parent);
                        if (parent)
                            selected.add(refKey(parent.ref));
                    }
                }
            }
            const children = new Map();
            const addChild = (parent, child) => {
                const key = refKey(parent.ref), values = children.get(key);
                if (values)
                    values.push(refKey(child.ref));
                else
                    children.set(key, [refKey(child.ref)]);
            };
            for (const record of records) {
                if (record.owner === 'appearance') {
                    const parent = resolveRecord(records, record.file, record.record.parent);
                    if (parent && (parent.owner === 'view_definition' || parent.owner === 'document'))
                        addChild(parent, record);
                }
                else if (record.owner === 'note' && record.path) {
                    for (let at = record.path.indexOf('/notes/'); at >= 0; at = record.path.indexOf('/notes/', at + 1)) {
                        const parent = recordIndex.paths.get(record.file + '\0' + record.path.slice(0, at));
                        if (parent)
                            addChild(parent, record);
                    }
                }
            }
            const expanded = new Set();
            const expandClosure = () => {
                const closure = [...selected];
                for (let i = 0; i < closure.length; i++) {
                    const current = closure[i];
                    if (expanded.has(current))
                        continue;
                    expanded.add(current);
                    for (const key of [...children.get(current) ?? [], ...dependencies.get(current) ?? []])
                        if (!selected.has(key)) {
                            selected.add(key);
                            closure.push(key);
                        }
                }
            };
            expandClosure();
            const reachableRecords = new Set(records.filter(record => reachable.has(record.file) && (record.owner !== 'workarea' || record.file === input.rootFile)).map(record => refKey(record.ref)));
            const ruleNormalized = activeNormalized;
            const ruleInput = (0, index_js_2.freeze)({ ...input, normalized: ruleNormalized, semanticFingerprint: (0, index_js_2.fingerprint)(ruleNormalized), coverage: { ...input.coverage, checked: input.coverage.checked.filter(ref => reachableRecords.has(refKey(ref))) } });
            const evaluated = new Map();
            let discovered = true;
            const evaluate = async (rule, callOptions) => {
                const invocation = rule.id + '\0' + (0, index_js_2.fingerprint)(callOptions.scope);
                if (evaluated.has(invocation))
                    return;
                await context.checkpoint(1);
                const semanticKey = (0, index_js_2.fingerprint)([input.rootFile, input.semanticFingerprint, input.revision.model, input.revision.data, input.versions, input.coverage, callOptions.scope, callOptions.level, callOptions.purpose, callOptions.measurement ?? null, packs.map(pack => pack.manifest), rule.id, rule.version, rule.readPaths, rule.globalScope]);
                const canReuse = cacheAllowed && input.coverage.complete && levelOrder.indexOf(options.level) >= 2 && !rule.readPaths.some(path => /^(?:revision|source|sources)(?:[./]|$)/.test(path));
                const reused = canReuse ? ruleCache.get(semanticKey) : undefined;
                const callbackOptions = Object.freeze({ ...callOptions, scope: (0, index_js_2.freeze)((0, index_js_2.clone)(callOptions.scope)) });
                const raw = reused ?? await rule.evaluate(ruleInput, callbackOptions, context);
                context.check();
                const result = ruleResult(raw, callOptions, ruleInput, records, reachableRecords);
                if (reused)
                    cacheHits++;
                evaluated.set(invocation, { rule, result });
                for (const reference of [...result.coverage.checked, ...result.dependencies.map(dependency => dependency.target)]) {
                    if (!selected.has(refKey(reference))) {
                        selected.add(refKey(reference));
                        discovered = true;
                    }
                }
                expandClosure();
                if (!reused && canReuse && result.coverage.complete && ['valid', 'invalid'].includes(result.outcome) && !result.diagnostics.some(d => d.source || d.related?.length) && !result.dependencies.some(d => /^(?:revision|source|sources)(?:[./]|$)/.test(d.path)) && ruleCache.size < 128)
                    ruleCache.set(semanticKey, result);
            };
            while (discovered) {
                discovered = false;
                for (const rule of rules) {
                    if (!rule.levels.includes(options.level) || rule.purposes.length && !rule.purposes.includes('*') && !rule.purposes.includes(options.purpose))
                        continue;
                    if (rule.profiles.length && !records.some(record => selected.has(refKey(record.ref)) && record.owner === 'view_definition' && rule.profiles.includes(typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1')))
                        continue;
                    await evaluate(rule, options);
                    for (const view of records.filter(record => selected.has(refKey(record.ref)) && record.owner === 'view_definition')) {
                        const descriptor = profileDescriptors.get(typeof view.record.profile === 'string' ? view.record.profile : 'ddn@1');
                        if (descriptor?.ruleIds.includes(rule.id) && ![...evaluated.values()].some(entry => entry.rule.id === rule.id && entry.result.coverage.checked.some(ref => refKey(ref) === refKey(view.ref))))
                            await evaluate(rule, { ...options, scope: { kind: 'view', target: view.ref } });
                    }
                }
            }
            for (const { owner, diagnostic } of referenceDiagnostics)
                if (options.scope.kind === 'workarea' || !owner || selected.has(refKey(owner.ref)))
                    diagnostics.push(diagnostic);
            for (const error of bundleIssues) {
                const path = /^\/files\/(\d+)\/document(.*)$/.exec(error.path);
                const sourceFile = path ? validationFiles?.[Number(path[1])] : undefined;
                const file = (0, schema_core_js_1.isRecord)(sourceFile) && typeof sourceFile.location === 'string' ? { location: sourceFile.location } : undefined;
                if (file && !reachable.has(file.location))
                    continue;
                const owner = file && path ? containingRecord(records, file.location, path[2]) : undefined;
                if (options.scope.kind === 'workarea' || !owner || selected.has(refKey(owner.ref)))
                    diagnostics.push(issue('DDN-SCHEMA-' + error.keyword.toUpperCase(), error.path + ': ' + error.message, owner?.ref));
            }
            const scopeRecords = records.filter(r => selected.has(refKey(r.ref)));
            const requiredRules = new Map();
            for (const record of scopeRecords) {
                await context.checkpoint(1);
                checked.push(record.ref);
                const state = status(record.record);
                if (state === 'accepted') {
                    const acceptance = record.record.acceptance;
                    if (!(0, schema_core_js_1.isRecord)(acceptance) || (0, schema_core_js_1.validateSchema)('acceptance_entry', acceptance).length)
                        diagnostics.push(issue('DDN-ACCEPTANCE', 'Accepted content requires valid acceptance time and user attribution', record.ref));
                }
                else if (record.record.acceptance !== undefined)
                    diagnostics.push(issue('DDN-ACCEPTANCE-STATE', 'Only accepted content may have a current acceptance event', record.ref));
                if (record.owner === 'definition' && record.record.category === 'relation') {
                    const ends = Array.isArray(record.record.endpoints) ? record.record.endpoints.filter(schema_core_js_1.isRecord) : [];
                    for (const end of ends) {
                        if (end.pending_name !== undefined) {
                            missing.add('endpoint:' + refKey(record.ref));
                            continue;
                        }
                        const owner = resolveRecord(records, record.file, end.definition);
                        if (end.member !== undefined && owner) {
                            const member = resolveRecord(records, record.file, end.member);
                            const members = Array.isArray(owner.record.members) ? owner.record.members : [];
                            if (!member || !members.some(ref => resolveRecord(records, owner.file, ref) === member))
                                diagnostics.push(issue('DDN-MEMBER-ENDPOINT', 'Endpoint member must belong to its endpoint definition', record.ref));
                        }
                    }
                }
                if (record.owner === 'view_definition') {
                    const profileId = typeof record.record.profile === 'string' ? record.record.profile : 'ddn@1';
                    const descriptor = profileDescriptors.get(profileId);
                    const native = (0, core_js_1.getProfile)(profileId);
                    if (!descriptor) {
                        missing.add('profile:' + profileId);
                        continue;
                    }
                    if (!allowedForeign && methodNames[descriptor.method] !== method)
                        diagnostics.push(issue('DDN-WORKAREA-METHOD', 'View profile is not admitted by the active workarea method', record.ref));
                    if (Array.isArray(wa.allowed_profiles) && wa.allowed_profiles.length && !wa.allowed_profiles.includes(profileId))
                        diagnostics.push(issue('DDN-WORKAREA-PROFILE', 'View profile is excluded by workarea allowed_profiles', record.ref));
                    if (!descriptor.ruleIds.length || !descriptor.ruleIds.every(id => rules.some(rule => rule.id === id)))
                        missing.add('rules:' + profileId);
                    if (levelOrder.indexOf(options.level) >= 2)
                        for (const id of descriptor.ruleIds) {
                            const required = requiredRules.get(id) ?? new Set();
                            required.add(refKey(record.ref));
                            requiredRules.set(id, required);
                        }
                }
                const resolved = (0, index_js_4.resolveProperties)(input, record.ref);
                diagnostics.push(...resolved.diagnostics.map(d => ({ ...d, target: record.ref })));
            }
            const ownership = new Map();
            for (const record of scopeRecords) {
                if (record.owner !== 'definition')
                    continue;
                const members = Array.isArray(record.record.members) ? record.record.members : [];
                for (const ref of members) {
                    const child = resolveRecord(records, record.file, ref);
                    if (child) {
                        const k = refKey(child.ref);
                        ownership.set(k, [...(ownership.get(k) ?? []), refKey(record.ref)]);
                    }
                }
            }
            for (const [child, owners] of ownership)
                if (new Set(owners).size > 1)
                    diagnostics.push(issue('DDN-MEMBER-OWNER', 'A semantic member has more than one owner', scopeRecords.find(x => refKey(x.ref) === child)?.ref));
            for (const start of ownership.keys()) {
                const path = new Set();
                let current = start;
                while (current) {
                    if (path.has(current)) {
                        diagnostics.push(issue('DDN-OWNERSHIP-CYCLE', 'Semantic ownership cannot be cyclic'));
                        break;
                    }
                    path.add(current);
                    current = ownership.get(current)?.[0];
                }
            }
            let incomplete = false;
            if (standaloneViews?.length === 0 && (levelOrder.indexOf(options.level) >= 3 || ['in-review', 'accepted'].includes(status(wa)))) {
                incomplete = true;
                missing.add('standalone-view');
                diagnostics.push({ code: 'DDN-STANDALONE-VIEW-MISSING', severity: 'warning', message: 'A standalone workarea needs one view or document before review', ...(activeWorkarea ? { target: activeWorkarea.ref } : {}) });
            }
            for (const record of scopeRecords) {
                const pending = record.record.incomplete;
                const reviewRequested = levelOrder.indexOf(options.level) >= 3 || ['in-review', 'accepted'].includes(status(record.record));
                if (!reviewRequested)
                    continue;
                if (Array.isArray(pending) && pending.length) {
                    incomplete = true;
                    missing.add('content:' + refKey(record.ref));
                }
                const hasStructuredData = Array.isArray((0, schema_core_js_1.getPath)(record.record, 'data.columns')) && Array.isArray((0, schema_core_js_1.getPath)(record.record, 'data.rows'));
                if (!hasStructuredData && typeof (0, schema_core_js_1.getPath)(record.record, 'draft.text') === 'string' && String((0, schema_core_js_1.getPath)(record.record, 'draft.text')).trim()) {
                    incomplete = true;
                    missing.add('draft:' + refKey(record.ref));
                }
                if (record.owner === 'definition') {
                    const name = typeof record.record.role === 'string' ? record.record.role : 'object', category = record.record.category === 'relation' ? 'relation' : 'element';
                    const role = (0, core_js_1.roleDescriptor)(name, category) ?? (0, core_js_1.coreTypeDescriptor)(name, category);
                    const core = role ? (0, core_js_1.coreDescriptor)(role.core) : undefined;
                    if (core) {
                        const checks = (0, schema_core_js_1.validateSchema)(core.complete, record.record.content ?? {});
                        if (checks.length) {
                            incomplete = true;
                            missing.add('complete:' + refKey(record.ref));
                            diagnostics.push({ code: 'DDN-COMPLETENESS', severity: 'warning', message: checks.map(c => c.message).join('; '), target: record.ref });
                        }
                    }
                    if (options.purpose === 'physical-schema' && (record.record.role === 'entity' || record.record.role === 'table')) {
                        const fields = Array.isArray(record.record.members) ? record.record.members.map(ref => resolveRecord(records, record.file, ref)).filter((r) => !!r) : [];
                        const columns = (0, schema_core_js_1.getPath)(record.record, 'data.columns'), rows = (0, schema_core_js_1.getPath)(record.record, 'data.rows');
                        const typeIndex = Array.isArray(columns) ? columns.findIndex(c => (0, schema_core_js_1.isRecord)(c) && c.id === 'type') : -1;
                        const fieldType = (field) => {
                            const explicit = (0, schema_core_js_1.getPath)(field.record, 'content.datatype') ?? (0, schema_core_js_1.getPath)(field.record, 'properties.datatype');
                            if (explicit !== undefined)
                                return explicit;
                            const ordinal = (0, schema_core_js_1.getPath)(field.record, 'content.ordinal');
                            const row = Array.isArray(rows) && typeof ordinal === 'number' ? rows[ordinal] : undefined;
                            return Array.isArray(row) && typeIndex >= 0 ? row[typeIndex] : undefined;
                        };
                        if (!fields.length || fields.some(field => { const value = fieldType(field); return value === undefined || value === null || typeof value === 'string' && !value.trim(); })) {
                            incomplete = true;
                            missing.add('physical-schema:' + refKey(record.ref));
                        }
                    }
                }
            }
            if (levelOrder.indexOf(options.level) >= 3 && !['design', 'review', 'display', 'conceptual', 'documentation', 'physical-schema'].includes(options.purpose) && !rules.some(r => r.purposes.includes(options.purpose))) {
                missing.add('purpose:' + options.purpose);
                outcome = 'unsupported';
            }
            const executed = new Set();
            for (const { rule, result } of evaluated.values()) {
                executed.add(rule.id);
                ruleVersions[rule.id] = rule.version;
                diagnostics.push(...result.diagnostics);
                checked.push(...result.coverage.checked);
                for (const item of result.coverage.unavailable)
                    missing.add(item);
                if (!result.coverage.complete) {
                    complete = false;
                }
                if (result.outcome === 'cancelled' || result.outcome === 'budget-exceeded')
                    throw new index_js_2.ComputationStopped(result.outcome, 'Rule ' + rule.id + ' stopped');
                if (result.outcome === 'unsupported') {
                    missing.add('rule:' + rule.id);
                    outcome = 'unsupported';
                }
                if (result.outcome === 'stale')
                    outcome = 'stale';
                if (result.outcome === 'incomplete')
                    incomplete = true;
                if (result.outcome === 'invalid' && !severity(result.diagnostics))
                    diagnostics.push(issue('DDN-RULE-INVALID', 'Rule ' + rule.id + ' rejected the scope'));
            }
            for (const id of requiredRules.keys())
                if (!executed.has(id))
                    missing.add('rules:' + id + ':not-executed');
            for (const [id, required] of requiredRules)
                for (const target of required)
                    if (![...evaluated.values()].some(entry => entry.rule.id === id && entry.result.coverage.checked.some(ref => refKey(ref) === target)))
                        missing.add('rules:' + id + ':coverage');
            const providerScope = input.coverage.scope;
            const coversScope = providerScope.kind === 'workarea' || equal(providerScope, options.scope) || options.scope.kind === 'item' && ['view', 'document'].includes(providerScope.kind);
            const coversReads = providerScope.kind === 'workarea' || checked.every(ref => input.coverage.checked.some(provided => equal(provided, ref)));
            if (!coversScope || !coversReads) {
                missing.add('input-scope-coverage');
                complete = false;
            }
            if (!input.coverage.complete || input.coverage.unavailable.length) {
                complete = false;
                for (const item of input.coverage.unavailable)
                    missing.add(item);
                if (input.coverage.unavailable.length === 0)
                    missing.add('complete-input-coverage');
            }
            if (options.level === 'publication') {
                const documents = scopeRecords.filter(record => record.owner === 'document');
                if (!documents.length) {
                    missing.add('publication-output-format');
                    incomplete = true;
                }
                for (const document of documents) {
                    const format = typeof document.record.format === 'string' ? document.record.format : schema_core_js_1.codex.properties.find(p => p.owner === 'document' && p.path === 'format')?.default.value;
                    if (typeof format !== 'string') {
                        missing.add('publication-output-format');
                        incomplete = true;
                    }
                    else if (!['svg', 'png', 'json', 'markdown', 'csv'].includes(format)) {
                        missing.add('output:' + format);
                        outcome = 'unsupported';
                        diagnostics.push({ code: 'DDN-PUBLICATION-OUTPUT', severity: 'warning', message: 'No native publication adapter evidence is available for ' + format, target: document.ref });
                    }
                }
                if (!options.measurement) {
                    missing.add('publication-measurement');
                    incomplete = true;
                }
                else if (!equal(options.measurement.revision, input.revision) || !equal(options.measurement.versions, input.versions)) {
                    outcome = 'stale';
                    diagnostics.push(issue('DDN-MEASUREMENT-STALE', 'Publication measurements do not belong to this snapshot'));
                }
                else if (typeof options.measurement.fingerprint !== 'string' || !options.measurement.fingerprint.trim() || typeof options.measurement.fontGeneration !== 'string' || !options.measurement.fontGeneration
                    || options.measurement.measurements === undefined || !options.measurement.coverage || !equal(options.measurement.coverage.scope, options.scope) || !options.measurement.coverage.complete
                    || !Array.isArray(options.measurement.coverage.unavailable) || options.measurement.coverage.unavailable.length
                    || !Array.isArray(options.measurement.coverage.checked) || !checked.every(ref => options.measurement.coverage.checked.some(provided => equal(provided, ref)))) {
                    incomplete = true;
                    missing.add('publication-measurement-coverage');
                }
            }
            if (severity(diagnostics) && outcome !== 'stale' && outcome !== 'unsupported')
                outcome = 'invalid';
            else if (outcome !== 'stale' && outcome !== 'unsupported')
                outcome = [...missing].some(x => x.startsWith('profile:') || x.startsWith('rules:')) ? 'unsupported' : incomplete || missing.size || !complete ? 'incomplete' : 'valid';
            if (missing.size || incomplete)
                complete = false;
            reviewEligible = outcome === 'valid' && complete && levelOrder.indexOf(options.level) >= 3;
            context.check();
            const result = report();
            if (cacheAllowed && complete && cache.size < 128)
                cache.set(key, result);
            return result;
        }
        catch (error) {
            complete = false;
            reviewEligible = false;
            if (error instanceof index_js_2.ComputationStopped) {
                outcome = error.outcome;
                missing.add(options.level);
                diagnostics.push(issue('DDN-' + outcome.toUpperCase(), error.message));
            }
            else {
                outcome = 'invalid';
                diagnostics.push(issue('DDN-VERIFY-INPUT', error instanceof Error ? error.message : 'Invalid verification input'));
            }
            return report();
        }
    }
    async function checkTransition(inputArgument, transitionArgument, optionsArgument = {}) {
        const diagnostics = [];
        try {
            const started = Date.now(), capturedOptions = captureOptions(optionsArgument);
            const options = { ...capturedOptions, ...(!capturedOptions.budget && limits ? { budget: limits } : {}) };
            const context = (0, index_js_2.createContext)(versions, liveTask(options));
            context.check();
            let units = 0;
            const input = (0, index_js_2.freeze)(boundedClone(inputArgument, context, count => units += count));
            const transition = (0, index_js_2.freeze)(boundedClone(transitionArgument, context, count => units += count));
            await context.checkpoint(units + 1);
            if (!input || input.contract !== 'ddn-next-1' || !equal(input.versions, versions) || !(0, schema_core_js_1.isRecord)(input.normalized) || input.normalized.entry !== input.rootFile || input.semanticFingerprint !== (0, index_js_2.fingerprint)(input.normalized))
                throw Error('Transition requires a current consistent snapshot');
            if (!transition || !validRef(transition.target) || !Array.isArray(transition.grants) || transition.grants.some(grant => typeof grant !== 'string'))
                throw Error('Malformed transition request');
            const record = resolveRecord((0, core_js_1.indexRecords)(input.normalized), transition.target.file, transition.target);
            if (!record || !['definition', 'view_definition', 'document', 'workarea'].includes(record.owner) || !reachedFiles(input).has(record.file) || record.owner === 'workarea' && record.file !== input.rootFile)
                return { allowed: false, diagnostics: [issue('DDN-TRANSITION-TARGET', 'Transition target does not resolve', transition.target)] };
            if (status(record.record) !== transition.from)
                diagnostics.push(issue('DDN-TRANSITION-STALE', 'Current lifecycle state differs from the supplied base', transition.target));
            if (!['draft', 'in-progress', 'in-review', 'accepted'].includes(transition.from) || !['draft', 'in-progress', 'in-review', 'accepted'].includes(transition.to))
                return (0, index_js_2.freeze)({ allowed: false, diagnostics: [issue('DDN-TRANSITION', 'Unknown lifecycle state', transition.target)] });
            if (transition.from === transition.to)
                return { allowed: diagnostics.length === 0, diagnostics };
            const matrix = { 'draft': ['in-progress'], 'in-progress': ['in-review'], 'in-review': ['in-progress', 'accepted'], 'accepted': ['in-review', 'in-progress'] };
            if (!matrix[transition.from]?.includes(transition.to))
                diagnostics.push(issue('DDN-TRANSITION', 'Requested lifecycle transition is not permitted', transition.target));
            if (transition.from === 'accepted' && !transition.grants.includes('lifecycle.reopen'))
                diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Reopening accepted content requires lifecycle.reopen authority', transition.target));
            if (transition.to === 'in-review' && !transition.grants.includes('lifecycle.review'))
                diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Review transition requires lifecycle.review authority', transition.target));
            if (transition.to === 'in-review' || transition.to === 'accepted') {
                const report = transition.report;
                if (!report || report.outcome !== 'valid' || !report.reviewEligible || !['review', 'publication'].includes(report.level) || !validScope(report.scope)
                    || !report.coverage?.complete || !equal(report.coverage.scope, report.scope) || !Array.isArray(report.coverage.unavailable) || report.coverage.unavailable.length
                    || !Array.isArray(report.missing) || report.missing.length || !Array.isArray(report.diagnostics) || severity(report.diagnostics)
                    || !equal(report.revision, input.revision) || report.dependencyFingerprint !== input.semanticFingerprint || !equal(report.versions, input.versions)
                    || !Array.isArray(report.coverage.checked) || !report.coverage.checked.some(r => equal(r, transition.target)))
                    diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'Current complete review verification covering the target is required', transition.target));
                if (report) {
                    const remaining = options.budget ? { ...options.budget, elapsedMs: Math.max(0, options.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, options.budget.workUnits - context.stats.workUnits) } : undefined;
                    const actual = await verify(input, { ...options, ...(remaining ? { budget: remaining } : {}), scope: report.scope, purpose: report.purpose, level: 'review' });
                    await context.checkpoint(actual.stats.workUnits);
                    if (!actual.reviewEligible || actual.outcome !== 'valid' || !actual.coverage.checked.some(r => equal(r, transition.target)))
                        diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'The current model does not pass independently recomputed review verification', transition.target));
                    const known = new Map([['ddn.structure', '1.0.0'], ['ddn.lifecycle', '1.0.0'], ...rules.map(rule => [rule.id, rule.version])]);
                    if (!(0, schema_core_js_1.isRecord)(report.ruleVersions) || Object.entries(report.ruleVersions).some(([id, version]) => known.get(id) !== version)
                        || Object.entries(actual.ruleVersions).some(([id, version]) => report.ruleVersions?.[id] !== version))
                        diagnostics.push(issue('DDN-TRANSITION-EVIDENCE', 'Review rule versions do not match the current required rules', transition.target));
                }
            }
            if (transition.to === 'accepted') {
                const event = transition.acceptance;
                if (!event || typeof event.user !== 'string' || !event.user.trim() || typeof event.authorityContext !== 'string' || !event.authorityContext.trim() || typeof event.timestamp !== 'string' || (0, schema_core_js_1.validateSchema)('instant', event.timestamp).length)
                    diagnostics.push(issue('DDN-TRANSITION-ACCEPTANCE', 'Acceptance requires user, offset-qualified timestamp and authority context', transition.target));
                if (!transition.grants.includes('lifecycle.accept'))
                    diagnostics.push(issue('DDN-TRANSITION-AUTHORITY', 'Acceptance requires lifecycle.accept authority', transition.target));
            }
            context.check();
            return (0, index_js_2.freeze)({ allowed: diagnostics.length === 0, diagnostics });
        }
        catch (error) {
            return (0, index_js_2.freeze)({ allowed: false, diagnostics: [...diagnostics, issue(error instanceof index_js_2.ComputationStopped ? 'DDN-' + error.outcome.toUpperCase() : 'DDN-TRANSITION-INPUT', error instanceof Error ? error.message : 'Invalid transition input')] });
        }
    }
    const verifier = {
        async verifySources(inputArgument, optionsArgument) {
            const started = Date.now();
            let input = { entry: 'unavailable.ddn', files: [] };
            let options = { scope: { kind: 'workarea' }, level: 'decode', purpose: '' };
            let normalized = { version: 'ddn-next-1', entry: input.entry, files: [] };
            let sourceUnits = 0;
            let diagnostics = [];
            let coverage = { scope: options.scope, complete: false, checked: [], unavailable: [] };
            let stopped;
            let task = options;
            const spans = new Map();
            try {
                options = captureOptions(optionsArgument);
                task = { ...options, ...(!options.budget && limits ? { budget: limits } : {}) };
                if (destroyed)
                    throw new index_js_2.ComputationStopped('cancelled', 'Verifier has been destroyed');
                const context = (0, index_js_2.createContext)(versions, liveTask(task));
                context.check();
                input = captureSources(inputArgument, context);
                sourceUnits = input.files.reduce((n, f) => n + f.text.length, 0);
                context.accountMemory(sourceUnits * 2);
                await context.checkpoint(sourceUnits);
                const decoded = (0, index_js_1.decodeSources)(input, task);
                context.check();
                normalized = decoded.normalized;
                diagnostics = decoded.diagnostics;
                coverage = decoded.coverage;
                for (const node of (0, index_js_1.allNodes)(decoded))
                    if (node.ref && !spans.has(refKey(node.ref)))
                        spans.set(refKey(node.ref), { file: node.file, revision: input.files.find(file => file.id === node.file).revision, start: node.start, end: node.end });
            }
            catch (error) {
                stopped = error instanceof index_js_2.ComputationStopped ? error.outcome : 'invalid';
                diagnostics = [issue('DDN-DECODE-' + stopped.toUpperCase(), error instanceof Error ? error.message : 'Source decoding failed')];
            }
            const digest = (0, index_js_2.fingerprint)(normalized);
            const snapshot = { contract: 'ddn-next-1', rootFile: input.entry, revision: { model: digest, sources: Object.fromEntries(input.files.map(f => [f.id, f.revision])), data: {} }, versions, semanticFingerprint: digest, normalized, coverage };
            const remaining = task.budget ? { ...task.budget, elapsedMs: Math.max(0, task.budget.elapsedMs - (Date.now() - started)), workUnits: Math.max(0, task.budget.workUnits - sourceUnits) } : undefined;
            const result = await verify(snapshot, { ...task, ...(remaining ? { budget: remaining } : {}) }, diagnostics);
            const located = result.diagnostics.map(diagnostic => {
                if (diagnostic.source)
                    return diagnostic;
                const span = diagnostic.target ? spans.get(refKey(diagnostic.target)) : undefined;
                const root = input.files.find(file => file.id === input.entry);
                return span ? { ...diagnostic, source: span } : root ? { ...diagnostic, source: { file: root.id, revision: root.revision, start: 0, end: root.text.length } } : diagnostic;
            });
            return (0, index_js_2.freeze)({ ...result, diagnostics: located, ...(stopped ? { outcome: stopped, reviewEligible: false, coverage: { ...result.coverage, complete: false } } : {}), stats: { ...result.stats, elapsedMs: Date.now() - started, workUnits: sourceUnits + result.stats.workUnits } });
        },
        verifyModel: verify, checkTransition, destroy() {
            destroyed = true;
            cache.clear();
            ruleCache.clear();
            for (const listener of destroyListeners) {
                try {
                    listener();
                }
                catch { }
            }
            destroyListeners.clear();
        },
    };
    decodedVerifiers.set(verifier, verify);
    return verifier;
}

}});})();
