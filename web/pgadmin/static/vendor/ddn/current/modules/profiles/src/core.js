import { codex, getPath, isRecord, validateSchema } from './schema-core.js';
import { isMindmapTopic, mindmapKey, mindmapRelationKind } from './mindmap.js';
export const contractVersion = 'ddn-next-1';
export const standardCommandIds = Object.freeze(['ddn.add-view', 'ddn.create-element', 'ddn.set-position', 'ddn.set-size', 'ddn.set-cell', 'ddn.add-row', 'ddn.remove-row', 'ddn.set-columns', 'ddn.add-note', 'ddn.set-note', 'ddn.set-draft', 'ddn.set-table', 'ddn.add-dataset', 'ddn.set-records']);
export const completeProfileIds = Object.freeze(Object.keys(codex.knownProfiles));
export const nativeProfileIds = Object.freeze([...codex.nativeProfiles]);
export function freezeProfileData(v) {
    if (v && typeof v === 'object' && !Object.isFrozen(v)) {
        Object.freeze(v);
        for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(v)))
            if ('value' in descriptor)
                freezeProfileData(descriptor.value);
    }
    return v;
}
freezeProfileData(codex);
const resolvedProfiles = new WeakMap();
/** External context reuses a profile contract without duplicating its catalogue data. */
export function getProfile(id) {
    const profile = codex.profiles[id];
    if (!profile)
        return undefined;
    const references = profile;
    if (!references.external_context_profile && !references.external_relation_profile)
        return profile;
    const cached = resolvedProfiles.get(profile);
    if (cached)
        return cached;
    const context = references.external_context_profile ? codex.profiles[references.external_context_profile] : undefined;
    const relations = references.external_relation_profile ? codex.profiles[references.external_relation_profile] : undefined;
    const contracts = new Map(profile.relation_endpoint_contracts.map(contract => [contract.role, contract]));
    for (const contract of relations?.relation_endpoint_contracts ?? [])
        contracts.set(contract.role, contract);
    const expanded = freezeProfileData({ ...profile,
        context_roles: [...new Set([...profile.context_roles, ...(context?.primary_palette ?? []), ...(context?.context_roles ?? [])])].filter(role => !profile.primary_palette.includes(role)),
        relation_roles: [...new Set([...profile.relation_roles, ...(relations?.relation_roles ?? [])])],
        relation_endpoint_contracts: [...contracts.values()],
    });
    resolvedProfiles.set(profile, expanded);
    return expanded;
}
export function knownProfile(id) { return codex.knownProfiles[id]; }
export function roleDescriptor(role, category = 'element') { return codex.roles[category === 'relation' ? 'relation::' + role : role]; }
export function coreDescriptor(id) { return codex.core[id]; }
export function coreTypeDescriptor(name, category = 'element') { const type = codex.coreTypes[name]; return type?.category === category ? type : undefined; }
export function profileDescriptor(id) {
    const p = getProfile(id);
    if (!p)
        return undefined;
    return freezeProfileData({ id: p.id, method: p.method, ...(p.inherits ? { inherits: p.inherits } : {}), roles: [...new Set([...p.primary_palette, ...p.context_roles])], relations: [...p.relation_roles], ruleIds: [(nativeProfileIds.includes(p.id) ? 'ddn.native.' : 'ddn.profile.') + p.id], projectionId: p.projection, commandIds: [...standardCommandIds], schemaIds: [p.projection_schema], codexHash: codex.sourceHashes['ddn.schema.json'] ?? '', boundedScope: p.scope, exclusions: [...p.exclusions] });
}
const owners = { definitions: 'definition', views: 'view_definition', placements: 'view_placement', appearances: 'appearance', data: 'data', sources: 'source', assets: 'asset', templates: 'template', publications: 'publication' };
export function bundleFiles(normalized) {
    if (!isRecord(normalized) || !Array.isArray(normalized.files))
        return [];
    return normalized.files.filter(isRecord).filter(f => typeof f.location === 'string' && isRecord(f.document)).map(f => ({ location: f.location, document: f.document }));
}
export function indexRecords(normalized) {
    const result = [];
    for (const { location: file, document } of bundleFiles(normalized)) {
        if (isRecord(document.workarea))
            result.push({ file, owner: 'workarea', record: document.workarea, ref: { file, id: typeof document.workarea.id === 'string' ? document.workarea.id : '@workarea' }, collection: 'workarea', index: 0 });
        for (const [collection, owner] of Object.entries(owners)) {
            const values = document[collection];
            if (!Array.isArray(values))
                continue;
            values.forEach((record, index) => {
                if (isRecord(record))
                    result.push({ file, owner: owner === 'view_definition' && record.kind === 'document' ? 'document' : owner, record, ref: { file, id: typeof record.id === 'string' ? record.id : `@${collection}/${index}` }, collection, index });
            });
        }
    }
    for (const parent of [...result]) {
        parent.path = parent.collection === 'workarea' ? '/workarea' : '/' + parent.collection + '/' + parent.index;
        const notes = parent.record.notes;
        if (!Array.isArray(notes))
            continue;
        notes.forEach((record, index) => {
            if (isRecord(record))
                result.push({ file: parent.file, owner: 'note', record, ref: { file: parent.file, id: typeof record.id === 'string' ? record.id : '@' + parent.path + '/notes/' + index }, collection: parent.collection + '/' + parent.index + '/notes', index, path: parent.path + '/notes/' + index });
        });
    }
    return result;
}
export function resolveRecord(records, file, reference) {
    if (!isRecord(reference))
        return undefined;
    const targetFile = typeof reference.file === 'string' ? reference.file : file;
    const matches = records.filter(x => x.file === targetFile && (typeof reference.id === 'string' ? x.ref.id === reference.id : true) && (typeof reference.name === 'string' ? x.record.name === reference.name : true));
    return (typeof reference.id === 'string' || typeof reference.name === 'string') && matches.length === 1 ? matches[0] : undefined;
}
/** Membership ownership is distinct from arbitrary inbound references. */
export function enclosingDefinitions(records, target) {
    const byId = new Map(records.map(record => [record.file + '\0' + record.ref.id, record]));
    const parents = new Map();
    for (const parent of records)
        if (parent.owner === 'definition' && Array.isArray(parent.record.members))
            for (const reference of parent.record.members) {
                const child = isRecord(reference) && typeof reference.id === 'string' ? byId.get((typeof reference.file === 'string' ? reference.file : parent.file) + '\0' + reference.id) : resolveRecord(records, parent.file, reference);
                if (child) {
                    const id = child.file + '\0' + child.ref.id;
                    parents.set(id, [...parents.get(id) ?? [], parent]);
                }
            }
    const result = [target], seen = new Set([target.file + '\0' + target.ref.id]);
    for (let i = 0; i < result.length; i++)
        for (const parent of parents.get(result[i].file + '\0' + result[i].ref.id) ?? []) {
            const id = parent.file + '\0' + parent.ref.id;
            if (!seen.has(id)) {
                seen.add(id);
                result.push(parent);
            }
        }
    return result;
}
export function normalizedReference(value) { return isRecord(value) && (typeof value.id === 'string' || typeof value.name === 'string'); }
export function safeLocation(from, target) {
    if (!target || /^[a-z][a-z0-9+.-]*:/i.test(target) || target.startsWith('/') || target.includes('\\'))
        return undefined;
    const parts = from.split('/').slice(0, -1);
    for (const piece of target.split('/')) {
        if (!piece || piece === '.')
            continue;
        if (piece === '..') {
            if (!parts.length)
                return undefined;
            parts.pop();
        }
        else
            parts.push(piece);
    }
    return parts.join('/');
}
export function nativeProfileDiagnostics(normalized, view, records, review = false) {
    const result = [];
    const profileId = typeof view.record.profile === 'string' ? view.record.profile : 'ddn@1';
    const profile = getProfile(profileId);
    if (!profile)
        return result;
    const issue = (code, message, target = view.ref) => result.push({ code, severity: 'error', message, target, rule: (nativeProfileIds.includes(profileId) ? 'ddn.native.' : 'ddn.profile.') + profileId });
    const selected = new Map();
    const add = (x) => {
        if (x && x.owner === 'definition')
            selected.set(x.file + '\0' + x.ref.id, x);
    };
    for (const appearance of records.filter(x => x.owner === 'appearance')) {
        const parent = resolveRecord(records, appearance.file, appearance.record.parent);
        if (parent?.ref.id === view.ref.id && parent.file === view.file)
            add(resolveRecord(records, appearance.file, appearance.record.target));
    }
    for (const path of ['sources', 'selection.items', 'selection.include', 'projection.inputs']) {
        const refs = getPath(view.record, path);
        if (Array.isArray(refs))
            for (const ref of refs)
                add(resolveRecord(records, view.file, ref));
    }
    const excluded = getPath(view.record, 'selection.exclude');
    if (Array.isArray(excluded))
        for (const ref of excluded) {
            const item = resolveRecord(records, view.file, ref);
            if (item)
                selected.delete(item.file + '\0' + item.ref.id);
        }
    const nodes = [...selected.values()].filter(x => x.record.category !== 'relation');
    const edges = [...selected.values()].filter(x => x.record.category === 'relation');
    const mindmap = profileId === 'mindmap.basic@1';
    const topics = mindmap ? nodes.filter(node => isMindmapTopic(node.record)) : [];
    const topicKeys = new Set(topics.map(mindmapKey));
    const resolvedEndpoints = new Map();
    const endpoints = (edge) => {
        const cached = resolvedEndpoints.get(edge);
        if (cached)
            return cached;
        const ends = Array.isArray(edge.record.endpoints) ? edge.record.endpoints.filter(isRecord) : [];
        const result = { ends, a: resolveRecord(records, edge.file, ends[0]?.definition), b: resolveRecord(records, edge.file, ends[1]?.definition) };
        resolvedEndpoints.set(edge, result);
        return result;
    };
    const contextKeys = new Set();
    const ddnProfile = mindmap ? getProfile('ddn@1') : undefined;
    const contextRoles = new Set([...(ddnProfile?.primary_palette ?? []), ...(ddnProfile?.context_roles ?? [])]);
    if (mindmap)
        for (const edge of edges) {
            const { a, b } = endpoints(edge);
            if (mindmapRelationKind(a, b, topicKeys) === 'external') {
                if (a && !topicKeys.has(mindmapKey(a)))
                    contextKeys.add(mindmapKey(a));
                if (b && !topicKeys.has(mindmapKey(b)))
                    contextKeys.add(mindmapKey(b));
            }
        }
    const allowed = new Set([...profile.primary_palette, ...profile.context_roles]);
    for (const node of nodes) {
        const role = typeof node.record.role === 'string' ? node.record.role : 'object';
        const linkedContext = mindmap && contextKeys.has(mindmapKey(node)) && contextRoles.has(role);
        if (mindmap ? !topicKeys.has(mindmapKey(node)) && !linkedContext : !allowed.has(role))
            issue('DDN-PROFILE-ROLE', `${role} is not allowed in ${profileId}`, node.ref);
    }
    for (const edge of edges) {
        const role = typeof edge.record.role === 'string' ? edge.record.role : 'assoc';
        const { ends, a, b } = endpoints(edge);
        const kind = mindmap ? mindmapRelationKind(a, b, topicKeys) : undefined;
        const external = kind === 'external';
        const relationProfile = external || kind === 'unresolved' ? ddnProfile : profile;
        if (kind === 'unrelated') {
            issue('DDN-MINDMAP-CONTEXT', 'A mind-map context relation must connect to a topic in this view', edge.ref);
            continue;
        }
        if ((kind === 'internal' && role !== 'assoc') || !relationProfile.relation_roles.includes(role)) {
            issue('DDN-PROFILE-RELATION', `${role} is not allowed in ${profileId}`, edge.ref);
            continue;
        }
        const contract = relationProfile.relation_endpoint_contracts.find(x => x.role === role);
        if (!contract)
            continue;
        if (ends.length !== 2) {
            issue('DDN-RELATION-ARITY', `${role} requires two endpoints`, edge.ref);
            continue;
        }
        if (!a || !b)
            continue;
        if (!contract.self_allowed && a.file === b.file && a.ref.id === b.ref.id)
            issue('DDN-RELATION-SELF', `${role} does not permit a self connection`, edge.ref);
        const ar = typeof a.record.role === 'string' ? a.record.role : 'object', br = typeof b.record.role === 'string' ? b.record.role : 'object';
        if (!contract.source_roles.includes(ar) || !contract.target_roles.includes(br))
            issue('DDN-RELATION-ENDPOINT', `Endpoint roles ${ar} → ${br} are not allowed for ${role}`, edge.ref);
        if (!contract.member_endpoints && ends.some(x => x.member !== undefined))
            issue('DDN-RELATION-MEMBER', `${role} does not permit member endpoints`, edge.ref);
    }
    if (mindmap) {
        const algorithm = getPath(view.record, 'layout.algorithm');
        if (algorithm !== undefined && algorithm !== 'mindmap')
            issue('DDN-MINDMAP-LAYOUT', 'Mind maps require the mindmap layout algorithm');
        const parents = new Map(topics.map(x => [mindmapKey(x), 0]));
        const incoming = new Map(topics.map(x => [mindmapKey(x), 0]));
        const adjacent = new Map();
        const internalEdges = new Set();
        for (const edge of edges) {
            const { a, b } = endpoints(edge);
            if (b && topicKeys.has(mindmapKey(b)))
                incoming.set(mindmapKey(b), (incoming.get(mindmapKey(b)) ?? 0) + 1);
            if (!a || !b || mindmapRelationKind(a, b, topicKeys) !== 'internal' || (edge.record.role ?? 'assoc') !== 'assoc')
                continue;
            internalEdges.add(mindmapKey(edge));
            const ak = mindmapKey(a), bk = mindmapKey(b);
            parents.set(bk, (parents.get(bk) ?? 0) + 1);
            adjacent.set(ak, [...(adjacent.get(ak) ?? []), bk]);
        }
        const roots = [...parents].filter(([, count]) => count === 0).map(([key]) => key);
        const routing = getPath(view.record, 'layout.routing');
        if (internalEdges.size && routing !== undefined && routing !== 'curved')
            issue('DDN-MINDMAP-ROUTING', 'Internal mind-map relationships require curved routing');
        for (const appearance of records.filter(record => record.owner === 'appearance')) {
            const parent = resolveRecord(records, appearance.file, appearance.record.parent);
            if (!parent || mindmapKey(parent) !== mindmapKey(view))
                continue;
            const edge = resolveRecord(records, appearance.file, appearance.record.target);
            if (!edge || edge.record.category !== 'relation' || !selected.has(mindmapKey(edge)))
                continue;
            const { a, b } = endpoints(edge);
            for (const [endpoint, property] of [[a, 'route.source_side'], [b, 'route.target_side']]) {
                if (!endpoint || !topicKeys.has(mindmapKey(endpoint)))
                    continue;
                const side = getPath(appearance.record, property);
                const rootIncoming = property === 'route.target_side' && roots.length === 1 && roots[0] === mindmapKey(endpoint) && mindmapRelationKind(a, b, topicKeys) === 'external';
                if ((side === 'north' || side === 'south') && !rootIncoming)
                    issue('DDN-MINDMAP-ATTACHMENT', 'Mind-map topics attach on the left or right; only the centre may receive an external relationship at the top or bottom', appearance.ref);
            }
            const appearanceRouting = getPath(appearance.record, 'route.routing');
            if (internalEdges.has(mindmapKey(edge)) && appearanceRouting !== undefined && appearanceRouting !== 'curved')
                issue('DDN-MINDMAP-ROUTING', 'Internal mind-map relationships require curved routing', appearance.ref);
        }
        if (topics.length && roots.length !== 1)
            issue('DDN-MINDMAP-ROOT', 'A mind map must have exactly one root');
        for (const topic of topics)
            if ((incoming.get(mindmapKey(topic)) ?? 0) > 1)
                issue('DDN-MINDMAP-PARENT', 'A mind-map topic may have only one incoming relationship', topic.ref);
        const degree = new Map(parents), queue = [...roots];
        let visited = 0;
        for (let i = 0; i < queue.length; i++) {
            const key = queue[i];
            visited++;
            for (const next of adjacent.get(key) ?? []) {
                const d = (degree.get(next) ?? 0) - 1;
                degree.set(next, d);
                if (d === 0)
                    queue.push(next);
            }
        }
        if (visited !== degree.size)
            issue('DDN-MINDMAP-CYCLE', 'A mind map cannot contain cycles');
        const specified = getPath(view.record, 'layout.root');
        if (specified !== undefined) {
            const r = resolveRecord(records, view.file, specified);
            if (!r || !roots.includes(r.file + '\0' + r.ref.id))
                issue('DDN-MINDMAP-ROOT', 'The explicit root must resolve to the actual root');
        }
    }
    if (profileId === 'concept.map@1')
        for (const edge of edges) {
            if (typeof edge.record.title !== 'string' || !edge.record.title.trim())
                issue('DDN-CONCEPT-LABEL', 'Concept-map connections need an explicit meaning label', edge.ref);
        }
    if (profileId === 'table.records@1') {
        const incomplete = (message) => {
            if (review)
                result.push({ code: 'DDN-TABLE-INCOMPLETE', severity: 'warning', message, target: view.ref, rule: (nativeProfileIds.includes(profileId) ? 'ddn.native.' : 'ddn.profile.') + profileId });
        };
        const authored = getPath(view.record, 'projection.options.records');
        const references = Array.isArray(authored) ? authored : authored === undefined ? [] : [authored];
        const providers = references.map(ref => resolveRecord(records, view.file, ref)).filter((r) => !!r);
        const firstData = providers.find(r => r.owner === 'data' || isRecord(r.record.data));
        const data = firstData?.owner === 'data' ? firstData.record : isRecord(firstData?.record.data) ? firstData.record.data : undefined;
        const authoredColumns = getPath(view.record, 'projection.options.columns');
        const inferredColumns = Array.isArray(data?.columns) ? data.columns : providers.length ? Object.keys(providers[0].record).filter(key => { const value = providers[0].record[key]; return value === null || typeof value !== 'object'; }).map(id => ({ id })) : [];
        const rawColumns = typeof authoredColumns === 'number' ? inferredColumns.slice(0, authoredColumns) : authoredColumns ?? inferredColumns;
        const columns = Array.isArray(rawColumns) ? rawColumns.map(column => {
            if (!isRecord(column))
                return column;
            if (column.file !== undefined || column.name !== undefined && column.id === undefined) {
                const field = resolveRecord(records, view.file, column);
                if (!field)
                    return column;
                const path = getPath(field.record, 'content.path') ?? field.record.name;
                return { id: field.record.name ?? field.ref.id, ...(typeof path === 'string' ? { path } : {}) };
            }
            return column;
        }) : rawColumns;
        if (!Array.isArray(columns) || !columns.length) {
            incomplete('Record table needs at least one explicit column');
        }
        else {
            const keys = columns.map(x => isRecord(x) ? x.id : undefined);
            if (columns.length > 30 || keys.some(x => typeof x !== 'string' || !x) || new Set(keys).size !== keys.length)
                issue('DDN-TABLE-COLUMNS', 'Record-table columns require 1..30 unique nonempty keys');
            const bound = columns.filter(isRecord).map(c => ({ key: String(c.id), path: typeof c.path === 'string' ? c.path : String(c.id) }));
            if (bound.some(c => c.path.split('.').some(p => ['__proto__', 'prototype', 'constructor'].includes(p))))
                issue('DDN-TABLE-BINDING', 'Unsafe record property binding');
            const missing = getPath(view.record, 'projection.options.missing') ?? 'error';
            for (const provider of providers) {
                const table = provider.owner === 'data' ? provider.record : isRecord(provider.record.data) ? provider.record.data : undefined;
                const rows = table?.rows;
                if (table) {
                    if (!Array.isArray(rows)) {
                        incomplete('Data rows are unavailable for ' + provider.ref.id);
                        continue;
                    }
                    const sourceColumns = Array.isArray(table.columns) ? table.columns.filter(isRecord) : [];
                    for (const row of rows)
                        for (const column of bound) {
                            const index = sourceColumns.findIndex(c => c.id === column.path);
                            const value = Array.isArray(row) ? index < 0 ? undefined : row[index] : getPath(row, column.path);
                            if (value === undefined && missing === 'error')
                                issue('DDN-TABLE-MISSING', 'Missing record value for ' + column.key, provider.ref);
                            else if (value !== undefined && value !== null && typeof value === 'object')
                                issue('DDN-TABLE-SCALAR', 'Record-table cells must be scalar', provider.ref);
                        }
                }
                else
                    for (const column of bound) {
                        const value = getPath(provider.record, column.path);
                        if (value === undefined && missing === 'error')
                            issue('DDN-TABLE-MISSING', 'Missing record value for ' + column.key, provider.ref);
                        else if (value !== undefined && value !== null && typeof value === 'object')
                            issue('DDN-TABLE-SCALAR', 'Record-table cells must be scalar', provider.ref);
                    }
            }
        }
        if (authored === undefined)
            incomplete('Record table needs a records binding or explicit empty records');
    }
    return result;
}
//# sourceMappingURL=core.js.map