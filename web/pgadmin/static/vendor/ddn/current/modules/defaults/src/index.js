import { codex, getPath, isRecord, setPath, validateSchema } from '../../profiles/src/schema-core.js';
import { bundleFiles, getProfile, indexRecords, resolveRecord, roleDescriptor, coreTypeDescriptor, coreDescriptor } from '../../profiles/src/core.js';
import { getViewSurfacePreset } from '../../profiles/src/view-surfaces.js';
import { methodNames } from './method-names.js';
const aliases = { element: 'definition', relation: 'definition', view: 'view_definition' };
const schemas = { data: 'data_record', source: 'source_record', asset: 'asset_record', template: 'template_record', publication: 'publication', file: 'file' };
const copy = (v) => JSON.parse(JSON.stringify(v));
const own = (v, k) => Object.prototype.hasOwnProperty.call(v, k);
// Versioned presentation presets. File and CSS paint settings retain priority.
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
/** Snapshot-local lookup indexes are reused only for actually immutable inputs.
 * Mutable host snapshots retain fresh resolution on every call. */
function recordsFor(snapshot) {
    const cached = snapshotRecords.get(snapshot);
    if (cached)
        return cached;
    const records = indexRecords(snapshot.normalized), files = bundleFiles(snapshot.normalized);
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
            if (!isRecord(reference))
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
let definitionsReady = false;
function ownerDefinitions(owner) {
    if (!definitionsReady) {
        for (const p of codex.properties) {
            const list = defs.get(p.owner) ?? [];
            list.push(p);
            defs.set(p.owner, list);
        }
        definitionsReady = true;
    }
    return defs.get(owner);
}
function merge(target, value, origin, origins, prefix = '') {
    for (const [key, v] of Object.entries(value)) {
        if (['__proto__', 'prototype', 'constructor'].includes(key))
            continue;
        const path = prefix ? prefix + '.' + key : key;
        if (isRecord(v)) {
            // Empty records contribute no leaves and cannot replace null with a container.
            if (!leaves(v).length)
                continue;
            if (!isRecord(target[key]))
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
        return isRecord(v) ? leaves(v, path) : [[path, v]];
    });
}
function definition(owner, path) { return ownerDefinitions(owner)?.find(p => path === p.path) ?? ownerDefinitions(owner)?.find(p => path.startsWith(p.path + '.')); }
function canonicalOwner(owner) { return aliases[owner] ?? owner; }
/** Checks a single supplied setting using the exact generated owner/role schema. */
export function validateProperty(owner, path, value, context = {}) {
    owner = canonicalOwner(owner);
    if (!path || path.split('.').some(k => ['__proto__', 'constructor', 'prototype'].includes(k)))
        return [{ code: 'DDN-PROPERTY-PATH', severity: 'error', message: 'Invalid property path' }];
    const property = definition(owner, path);
    if (property && !property.settable)
        return [{ code: 'DDN-PROPERTY-READONLY', severity: 'error', message: `${owner}.${path} is not author-settable` }];
    const record = {};
    setPath(record, path, value);
    if (context.role && owner === 'definition')
        record.role = context.role;
    if (context.profile && (owner === 'view_definition' || owner === 'document'))
        record.profile = context.profile;
    if (context.category && owner === 'definition')
        record.category = context.category;
    const role = owner === 'definition' && context.role ? roleDescriptor(context.role, context.category) : undefined;
    const coreType = owner === 'definition' && context.role ? coreTypeDescriptor(context.role, context.category) : undefined;
    const payload = context.category === 'relation' ? 'qualifiers' : 'content';
    if (coreType && (path === payload || path.startsWith(payload + '.'))) {
        const relative = '/' + path.slice(payload.length + 1).replaceAll('.', '/');
        return validateSchema(coreType.schema, record[payload] ?? {}).filter(issue => issue.keyword !== 'required' || issue.path.startsWith(relative)).map(issue => ({ code: 'DDN-PROPERTY-' + issue.keyword.toUpperCase(), severity: 'error', message: `${owner}.${path}: ${issue.message}` }));
    }
    const roleSchema = ['content', 'metadata', 'properties', 'qualifiers'].includes(path.split('.')[0]) ? role?.schema ?? (coreType ? (schemas[owner] ?? owner) : undefined) : undefined;
    const issues = roleSchema !== undefined ? validateSchema(roleSchema, record).filter(issue => issue.keyword !== 'required' || issue.path.startsWith('/' + path.replaceAll('.', '/'))) : property && path === property.path ? validateSchema(property.schema, value) : validateSchema(schemas[owner] ?? owner, record).filter(issue => issue.keyword !== 'required' || issue.path.startsWith('/' + path.replaceAll('.', '/')));
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
    const classes = getPath(record, 'style.classes');
    return !selector.classes || selector.classes.every(c => Array.isArray(classes) && classes.includes(c));
}
function ruleDeclarations(rule) {
    return Object.entries(rule.declarations).flatMap(([path, value]) => isRecord(value) ? leaves(value, path) : [[path, value]]);
}
function specificity(rule) {
    if (rule.specificityTuple)
        return rule.specificityTuple;
    if (rule.specificity === undefined) {
        const attributes = ['owner', 'category', 'file', 'method', 'profile', 'catalogue', 'subtype', 'role'];
        return [rule.selector.id === undefined ? 0 : 1, (rule.selector.classes?.length ?? 0) + attributes.filter(key => rule.selector[key] !== undefined).length, 0];
    }
    // Preserve the numeric API's ordering; parsed CSS carries unbounded counts.
    const score = rule.specificity;
    return [Math.floor(score / 100), Math.floor((score % 100) / 10), score % 10];
}
/** Resolves omission without mutating source or manufacturing missing semantic facts. */
export function resolve(record, owner, context = {}) {
    owner = canonicalOwner(owner);
    context = { ...context, ...(context.role ? {} : typeof record.role === 'string' ? { role: record.role } : {}), category: context.category ?? (typeof record.category === 'string' ? record.category : 'element') };
    const values = {}, origins = new Map(), diagnostics = [];
    const set = (path, value, origin) => {
        setPath(values, path, copy(value));
        for (const [p] of isRecord(value) ? leaves(value, path) : [[path, value]])
            origins.set(p, origin);
    };
    for (const p of ownerDefinitions(owner) ?? [])
        if (p.default.kind === 'literal' && p.default.value !== undefined && !(p.path.startsWith('draft.') && record.draft === undefined))
            set(p.path, p.default.value, 'standard:' + owner);
    const role = context.role ? roleDescriptor(context.role, context.category) : undefined;
    const coreType = context.role ? coreTypeDescriptor(context.role, context.category) : undefined;
    const render = role?.render ?? (coreType ? coreDescriptor(coreType.core)?.render : undefined);
    if (render && owner === 'appearance') {
        for (const [path, key] of [['symbol.color', 'colour'], ['symbol.fill', 'fill'], ['symbol.width', 'width']]) {
            const value = render[key] ?? (key === 'colour' ? render.stroke : undefined);
            if (value !== undefined)
                set(path, value, 'standard:role ' + context.role);
        }
    }
    const profile = context.profile ? getProfile(context.profile) : undefined;
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
        else if (getPath(context.definition, 'draft.text'))
            set('body', 'draft', 'standard:content');
    }
    if (owner === 'workarea' && !own(record, 'allow_foreign_views'))
        set('allow_foreign_views', (record.method ?? context.method ?? 'ddn') === 'ddn', 'standard:context');
    if (owner === 'source' && !own(record, 'refresh'))
        set('refresh', record.mode === 'host' ? 'supplied' : 'manual', 'standard:context');
    const surface = getViewSurfacePreset(owner === 'view_definition' ? getPath(record, 'surface.preset') : context.surfacePreset);
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
    // CSS order is independent of file priority. Importance only ranks inside CSS.
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
        // Target-view defaults already enter through viewDefaults. Element
        // defaults are a separate shared-definition layer for item appearances.
        if (owner === 'appearance')
            for (const rule of rules(context.definition.defaults))
                apply(rule, 'file:definition defaults', false);
        const inherited = {};
        for (const p of ownerDefinitions(owner) ?? []) {
            if (!p.defaultable)
                continue;
            const v = getPath(context.definition, p.path);
            if (v !== undefined)
                setPath(inherited, p.path, v);
        }
        merge(values, inherited, 'file:definition', origins);
    }
    merge(values, record, owner === 'appearance' || owner === 'view_placement' ? 'file:occurrence' : 'file:definition', origins);
    const theme = String(origins.get('style.theme')?.startsWith('file:') || origins.get('style.theme') === 'css' ? getPath(values, 'style.theme') : context.theme ?? getPath(values, 'style.theme'));
    const paint = themePaint[theme];
    if (paint && ['definition', 'appearance', 'view_definition', 'workarea'].includes(owner)) {
        for (const [path, value] of Object.entries({ 'background.color': owner === 'view_definition' || owner === 'workarea' ? paint.background : paint.surface, 'text.color': paint.ink, 'border.color': paint.rule, 'symbol.color': paint.accent, 'symbol.fill': paint.surface, 'stroke.color': paint.accent })) {
            if (!origins.has(path) || origins.get(path)?.startsWith('standard:'))
                set(path, value, 'standard:theme ' + theme);
        }
    }
    if (['note', 'pad'].includes(String(getPath(values, 'style.paper'))) && ['definition', 'appearance', 'view_definition', 'view_placement', 'document'].includes(owner)) {
        const origin = origins.get('background.color');
        if (!origin || origin.startsWith('standard:'))
            set('background.color', '#fff59d', 'standard:paper');
    }
    if (owner === 'view_definition' && profile?.projection === 'chart') {
        const transform = getPath(values, 'projection.options.transform');
        if (['histogram', 'pareto', 'waterfall', 'boxplot'].includes(String(transform))) {
            const options = getPath(values, 'projection.options');
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
    for (const p of ownerDefinitions(owner) ?? []) {
        const value = getPath(record, p.path);
        if (value !== undefined)
            diagnostics.push(...validateProperty(owner, p.path, value, context));
    }
    if (owner === 'view_definition') {
        const width = getPath(values, 'surface.width'), height = getPath(values, 'surface.height');
        if ((width === null) !== (height === null))
            diagnostics.push({ code: 'DDN-SURFACE-SIZE', severity: 'error', message: 'Fixed view surfaces require both width and height; dynamic surfaces use null for both.' });
        if (typeof width === 'number' && typeof height === 'number') {
            const inset = Number(getPath(values, 'surface.padding')) * Number(getPath(values, 'surface.scale')) * 2;
            if (inset >= Math.min(width, height))
                diagnostics.push({ code: 'DDN-SURFACE-PADDING', severity: 'error', message: 'Surface padding must leave a positive drawable width and height.' });
        }
    }
    return { values, properties: leaves(values).map(([path, value]) => ({ path, value, origin: origins.get(path) ?? 'file' })), diagnostics };
}
function rules(v) { return Array.isArray(v) ? v.filter(isRecord).filter(x => isRecord(x.selector) && isRecord(x.declarations)) : []; }
export function resolveProperties(snapshot, target, context = {}) {
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
    const wa = isRecord(root?.workarea) ? root.workarea : undefined;
    const styleRules = [...(context.styles ?? [])];
    // File-level sheet locations are loaded by the host into context.styles.
    // Typed Style references resolve against the file declaring each attachment.
    const typedRules = (provider, kind) => {
        if (provider?.owner !== 'definition' || provider.record.role !== 'core::Style' || provider.record.category === 'relation')
            return [];
        const content = provider.record.content;
        return isRecord(content) && content.kind === kind ? rules(content.rules) : [];
    };
    const attached = new Set();
    for (const [provider, fileId] of [[wa, snapshot.rootFile], [view?.record, view?.file], [definitionRecord?.record, definitionRecord?.file], [item.record, item.file]]) {
        if (!provider || !fileId || attached.has(provider))
            continue;
        attached.add(provider);
        const sheets = getPath(provider, 'style.sheets');
        if (Array.isArray(sheets))
            for (const ref of sheets)
                styleRules.push(...typedRules(resolveRecord(records, fileId, ref), 'css'));
    }
    const providerDiagnostics = [];
    const defaultProviders = (value, fileId) => {
        const result = rules(value);
        if (Array.isArray(value))
            for (const ref of value) {
                // Direct runtime/parser rules are already collected above.
                if (isRecord(ref) && isRecord(ref.selector) && isRecord(ref.declarations))
                    continue;
                const provider = resolveRecord(records, fileId, ref);
                if (provider?.owner !== 'definition' || provider.record.role !== 'core::Style' || provider.record.category === 'relation' || getPath(provider.record, 'content.kind') !== 'defaults') {
                    providerDiagnostics.push({ code: 'DDN-DEFAULT-PROVIDER', severity: 'error', message: 'A defaults reference must resolve to a core::Style definition with content.kind defaults' });
                    continue;
                }
                // Its own definition.defaults concern that Style's appearances,
                // not the recipients of this explicit reusable concern.
                result.push(...typedRules(provider, 'defaults'));
            }
        return result;
    };
    const profile = typeof view?.record.profile === 'string' ? view.record.profile : typeof item.record.profile === 'string' ? item.record.profile : 'ddn@1';
    const method = view ? methodNames[getProfile(profile)?.method ?? ''] : typeof wa?.method === 'string' ? wa.method : 'ddn';
    let theme, surfaceTypography;
    const surfacePreset = getPath(view?.record, 'surface.preset');
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
            const surface = getViewSurfacePreset(surfacePreset);
            settings = { theme: String(getPath(values, 'style.theme') ?? 'default'), ...(surface && surface.id !== 'dynamic' ? { typography: { font: String(getPath(values, 'style.font') ?? 'sans'), fontSize: Number(getPath(values, 'style.font_size') ?? 24) } } : {}) };
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
export const previewPaths = Object.freeze(['background.color', 'border.color', 'opacity', 'text.color']);
export function validatePreview(value) {
    return Object.entries(value).flatMap(([path, v]) => !previewPaths.includes(path) ? [{ code: 'DDN-PREVIEW', severity: 'error', message: `${path} is not a paint-preview property` }] : validateProperty('appearance', path, v));
}
export function createDefaultsResolver(options) {
    if (options.defaultsVersion !== 'ddn-next-1')
        throw new Error('Unsupported defaults version ' + options.defaultsVersion);
    return { resolve: (record, owner, context = {}) => resolve(record, owner, { ...context, styles: context.styles ?? options.styles ?? [] }) };
}
/** Author percentages are retained; this returns the logical rendered allocations. */
export function allocateColumnPercentages(percentages) {
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
/** Parse the registered virtual CSS hooks without DOM access or network loading. */
export function parseStylesheet(text) {
    const diagnostics = [];
    const result = [];
    const fail = (message) => diagnostics.push({ code: 'DDN-CSS', severity: 'error', message });
    const escaped = (source, at) => {
        let slashes = 0;
        while (at > 0 && source[--at] === '\\')
            slashes++;
        return slashes % 2 === 1;
    };
    // CSS comments are syntax only outside quoted values/selectors.
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
            const binding = codex.cssMap[key];
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
            // Parse class/id tokens independently so compound hooks have normal CSS meaning.
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
//# sourceMappingURL=index.js.map