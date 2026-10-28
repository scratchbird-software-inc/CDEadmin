import { getProfile, resolveRecord } from './core.js';
import { getPath, isRecord, stableStringify, validateSchema } from './schema-core.js';
import { analyzeDecision, calculateCriticalPath } from './analysis.js';
import { flatTraceAnalysis } from './analysis-profile.js';
import { projectionDiagnostics, projectionRows } from './projection-rules.js';
const object = (v) => isRecord(v) ? v : {};
const array = (v) => Array.isArray(v) ? v : [];
const text = (v) => typeof v === 'string' ? v : '';
const key = (v) => v.file + '\0' + v.ref.id;
const role = (v) => text(v.record.role);
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const meta = (v, name) => getPath(v.record, 'metadata.' + name);
export function profileSelection(view, records) {
    const selected = new Map();
    const resolve = (ref, owner = view) => typeof ref === 'string' ? records.find(r => r.file === owner.file && (r.record.name === ref || r.ref.id === ref)) : resolveRecord(records, owner.file, ref);
    const add = (r) => { if (r?.owner === 'definition')
        selected.set(key(r), r); };
    for (const appearance of records.filter(r => r.owner === 'appearance'))
        if (resolve(appearance.record.parent, appearance) === view)
            add(resolve(appearance.record.target, appearance));
    for (const path of ['sources', 'selection.items', 'selection.include', 'projection.inputs'])
        for (const ref of array(getPath(view.record, path)))
            add(resolve(ref));
    for (const ref of array(getPath(view.record, 'selection.exclude'))) {
        const item = resolve(ref);
        if (item)
            selected.delete(key(item));
    }
    const nodes = [...selected.values()].filter(r => r.record.category !== 'relation'), edges = [...selected.values()].filter(r => r.record.category === 'relation');
    const links = [];
    for (const item of edges) {
        const ends = array(item.record.endpoints).filter(isRecord), from = resolve(ends[0]?.definition, item), to = resolve(ends[1]?.definition, item);
        if (from && to)
            links.push({ item, from, to, ends });
    }
    return { nodes, edges, links, selected, resolve };
}
function topological(nodes, links) {
    const ids = new Set(nodes.map(key)), degree = new Map(nodes.map(n => [key(n), 0])), outgoing = new Map(nodes.map(n => [key(n), []]));
    for (const l of links)
        if (ids.has(key(l.from)) && ids.has(key(l.to))) {
            degree.set(key(l.to), degree.get(key(l.to)) + 1);
            outgoing.get(key(l.from)).push(key(l.to));
        }
    const queue = [...degree].filter(([, n]) => !n).map(([id]) => id);
    for (let i = 0; i < queue.length; i++)
        for (const next of outgoing.get(queue[i])) {
            degree.set(next, degree.get(next) - 1);
            if (!degree.get(next))
                queue.push(next);
        }
    return queue.length === nodes.length;
}
export function completeProfileDiagnostics(view, records, review = false) {
    const profileId = text(view.record.profile), profile = getProfile(profileId);
    if (!profile)
        return [];
    const result = [];
    const issue = (code, message, target = view.ref, severity = 'error') => result.push({ code, severity, message, target, rule: 'ddn.profile.' + profileId });
    const incomplete = (message, target = view.ref) => { if (review)
        issue('DDN-PROFILE-INCOMPLETE', message, target, 'warning'); };
    const { nodes, edges, links, selected, resolve } = profileSelection(view, records);
    const regions = array(view.record.regions).filter(isRecord);
    const regionOf = (n) => regions.find(region => array(region.members).some(ref => resolve(ref) === n));
    const regionOwner = (n) => { const region = regionOf(n); return region ? resolve(region.scope) : resolve(object(meta(n, 'x_diagram')).owner, n); };
    const regionKey = (n) => text(regionOf(n)?.id) || text(object(meta(n, 'x_diagram')).owner);
    const regionIds = new Set();
    for (const region of regions) {
        const id = text(region.id);
        if (regionIds.has(id))
            issue('DDN-REGION-ID', 'Region IDs must be unique');
        regionIds.add(id);
        for (const member of array(region.members))
            if (!resolve(member) || !selected.has(key(resolve(member))))
                issue('DDN-REGION-MEMBER', 'Region member must resolve to a selected item');
        if (region.scope !== undefined && !resolve(region.scope))
            issue('DDN-REGION-SCOPE', 'Region scope must resolve');
    }
    for (const region of regions) {
        const seen = new Set();
        let current = region;
        while (current) {
            const id = text(current.id);
            if (seen.has(id)) {
                issue('DDN-REGION-CYCLE', 'Region nesting must be acyclic');
                break;
            }
            seen.add(id);
            const parent = current.parent;
            if (parent !== undefined && !regionIds.has(text(parent))) {
                issue('DDN-REGION-PARENT', 'Region parent must exist');
                break;
            }
            current = parent === undefined ? undefined : regions.find(r => r.id === parent);
        }
    }
    const incoming = (n, within = links) => within.filter(l => key(l.to) === key(n));
    const outgoing = (n, within = links) => within.filter(l => key(l.from) === key(n));
    const members = (n) => array(n.record.members).map(r => resolve(r, n)).filter((r) => !!r);
    const selectedRef = (reference, owner, roles) => { const target = resolve(reference, owner); return target && selected.has(key(target)) && (!roles || roles.includes(role(target))) ? target : undefined; };
    const unique = (values, code, description) => { const defined = values.filter((v) => !!v); if (new Set(defined).size !== defined.length)
        issue(code, description); };
    const cycle = (subset, code) => { if (!topological(nodes, subset))
        issue(code, 'The declared relationship graph must be acyclic'); };
    // Metadata is typed by schema, but ownership and cross-reference predicates are semantic.
    for (const n of [...nodes, ...edges]) {
        const m = object(n.record.metadata), r = role(n);
        for (const [name, admitted] of Object.entries({ x_petri: ['petri.'], x_idef0: ['idef0.'], x_vsm: ['vsm.process'], x_contact: ['ladder.contact'], x_coil: ['ladder.coil'], x_gateway: ['flow.gateway'], x_event: ['flow.start', 'flow.end', 'flow.intermediate'], x_epc: ['epk.connector'], x_chen: ['entity', 'field', 'assoc', 'ref'], x_instance: ['object', 'record'], x_rack: ['network.rack', 'network.server', 'network.switch'], x_states: ['uml.', 'msc.', 'object', 'service', 'application'], x_gate: ['tree.gate'], x_activity: ['flow.process', 'flow.subprocess', 'flow.choreotask'], x_io: ['flow.datainput', 'flow.dataoutput'], x_bands: ['flow.choreotask'], x_sentry: ['cmmn.sentry'], x_boxed: ['dmn.decision', 'dmn.bkm'] })) {
            if (m[name] !== undefined && !admitted.some(a => a.endsWith('.') ? r.startsWith(a) : r === a))
                issue('DDN-METADATA-OWNER', name + ' is not legal on ' + r, n.ref);
        }
        if (m.x_petri !== undefined) {
            const p = object(m.x_petri);
            if (p.tokens !== undefined && r !== 'petri.place' || p.weight !== undefined && !['petri.arc', 'petri.testarc'].includes(r))
                issue('DDN-PETRI-OWNER', 'Tokens belong to places; weights belong to ordinary and test arcs', n.ref);
        }
        if (m.x_vsm !== undefined) {
            const v = object(m.x_vsm);
            if ((v.va !== undefined || v.nva !== undefined) && !text(v.unit))
                incomplete('VA/NVA durations require a declared unit', n.ref);
        }
        if (m.x_subdiagram !== undefined) {
            const child = resolve(object(m.x_subdiagram).view, n);
            if (!child || child.owner !== 'view_definition')
                issue('DDN-SUBDIAGRAM-TARGET', 'Subdiagram must reference a workspace view', n.ref);
            else if (key(child) === key(view))
                issue('DDN-SUBDIAGRAM-RECURSION', 'A view cannot embed itself', n.ref);
            else if (profileId === 'dmn.drd@1' && child.record.profile !== 'decision.rules@1')
                issue('DDN-DMN-DRILLDOWN', 'DMN decision drill-down must reference a decision table view', n.ref);
        }
        if (m.x_boxed !== undefined) {
            const boxed = object(m.x_boxed);
            if (['literal', 'invocation'].includes(text(boxed.form)) && !text(boxed.text) || ['context', 'relation'].includes(text(boxed.form)) && !array(boxed.entries).length)
                incomplete('Boxed expression requires text or entries for its declared presentation form', n.ref);
        }
        if (m.x_contract !== undefined) {
            const ref = object(m.x_contract).choreography;
            if (ref !== undefined) {
                const target = resolve(ref, n);
                if (!target || target.owner !== 'view_definition' || !['sequence', 'graph'].includes(getProfile(text(target.record.profile))?.projection ?? '') || !/sequence|statemachine/.test(text(target.record.profile)))
                    issue('DDN-SERVICE-CHOREOGRAPHY', 'Service choreography must reference a sequence or state-machine view', n.ref);
            }
        }
        if (m.x_sdl !== undefined && profileId === 'sdl.process@1') {
            const sdl = object(m.x_sdl);
            if (['priority', 'spontaneous', 'continuous', 'active'].some(p => sdl[p] !== undefined) && r !== 'sdl.input')
                issue('DDN-SDL-MARKER-OWNER', 'Input markers belong only to SDL input nodes', n.ref);
            if ((sdl.timer !== undefined || sdl.duration !== undefined) && !['sdl.set', 'sdl.reset'].includes(r))
                issue('DDN-SDL-TIMER-OWNER', 'Timer references belong to set/reset nodes', n.ref);
        }
        if (m.x_sdl !== undefined)
            for (const ref of array(object(m.x_sdl).signals))
                if (role(resolve(ref, n) ?? n) !== 'sdl.signal')
                    issue('DDN-SDL-SIGNAL', 'Signal references must resolve to sdl.signal', n.ref);
        if (m.x_jump !== undefined && !selectedRef(object(m.x_jump).target, n, ['ladder.label']))
            issue('DDN-LADDER-JUMP', 'Jump target must be a selected ladder label', n.ref);
        if (m.x_derive !== undefined && r !== 'orm.facttype')
            issue('DDN-ORM-DERIVATION', 'Derivation text belongs to a fact type', n.ref);
        if (m.x_planning !== undefined && !['cmmn.stage', 'cmmn.humantask'].includes(r))
            issue('DDN-CMMN-PLANNING', 'Planning tables belong to a stage or human task', n.ref);
    }
    // Core ports retain endpoint identity; their method metadata has exact standalone schemas.
    for (const owner of nodes)
        for (const member of members(owner))
            if (role(member) === 'core::Port') {
                const declared = resolve(getPath(member.record, 'content.owner'), member);
                if (declared && declared !== owner)
                    issue('DDN-PORT-OWNER', 'Port owner and containing member list must agree', member.ref);
                for (const [name, value] of Object.entries(object(member.record.metadata))) {
                    if (['x_fbd', 'x_icom', 'x_service', 'x_port', 'x_pin', 'x_interfaces'].includes(name)) {
                        for (const failure of validateSchema('meta_' + name + '_port', value))
                            issue('DDN-PORT-METADATA', name + ': ' + failure.message, member.ref);
                    }
                }
                const service = object(meta(member, 'x_service'));
                const serviceOwner = ['soaml.participant', 'soaml.agent'].includes(role(owner)) || role(owner) === 'soaml.serviceinterface' && service.kind === 'service';
                if (service.kind !== undefined && !serviceOwner)
                    issue('DDN-SERVICE-PORT', 'Service/request ports belong to participants or agents; a service interface may declare its provided service port', member.ref);
                if (meta(member, 'x_fbd') !== undefined && !['fbd.block', 'fbd.variable'].includes(role(owner)))
                    issue('DDN-FBD-PORT', 'FBD pins belong to blocks or variables', member.ref);
                if (meta(member, 'x_icom') !== undefined && role(owner) !== 'idef0.activity')
                    issue('DDN-IDEF0-PORT', 'ICOM ports belong to IDEF0 functions', member.ref);
                if (meta(member, 'x_pin') !== undefined && !['flow.process', 'flow.subprocess', 'flow.sendsignal', 'flow.acceptsignal'].includes(role(owner)))
                    issue('DDN-ACTIVITY-PIN', 'Activity pins belong to supported action kinds', member.ref);
                if (role(owner) === 'sdl.agent')
                    issue('DDN-SDL-GATE', 'SDL gates belong to blocks', member.ref);
            }
    // Optional interface assertions are explicit bounded compatibility claims.
    for (const link of links.filter(link => ['uml.assembly', 'uml.connector', 'uml.delegation'].includes(role(link.item)))) {
        const source = resolve(link.ends[0]?.member, link.item) ?? link.from, target = resolve(link.ends[1]?.member, link.item) ?? link.to;
        const assertions = (item, path) => array(object(meta(item, 'x_interfaces'))[path]).map(ref => resolve(ref, item)).filter((r) => !!r);
        const provided = assertions(source, 'provides'), required = assertions(target, 'requires');
        if (role(link.item) === 'uml.delegation' && role(source) !== 'core::Port')
            issue('DDN-DELEGATION-PORT', 'Delegation starts at a port', link.item.ref);
        const mode = text(object(meta(link.item, 'x_compatibility')).mode) || 'same';
        const compatible = (a, b) => {
            if (a === b)
                return true;
            if (mode === 'operation-coverage') {
                const signature = (field) => stableStringify({ name: field.record.name ?? '', datatype: getPath(field.record, 'content.datatype') ?? getPath(field.record, 'properties.datatype') ?? null, domain: getPath(field.record, 'content.domain') ?? getPath(field.record, 'properties.domain') ?? null, parameters: getPath(field.record, 'properties.parameters') ?? null });
                const signatures = new Set(members(a).filter(f => object(meta(f, 'x_member')).kind === 'operation').map(signature));
                return members(b).filter(f => object(meta(f, 'x_member')).kind === 'operation').every(f => signatures.has(signature(f)));
            }
            const roles = mode === 'specialization' ? ['uml.generalization'] : mode === 'realization' ? ['uml.realization', 'uml.generalization'] : [];
            const visited = new Set(), queue = [a];
            for (let i = 0; i < queue.length; i++) {
                const item = queue[i];
                if (item === b)
                    return true;
                if (visited.has(key(item)))
                    continue;
                visited.add(key(item));
                for (const edge of links)
                    if (edge.from === item && roles.includes(role(edge.item)))
                        queue.push(edge.to);
            }
            return false;
        };
        if (required.length && !required.every(r => provided.some(p => compatible(p, r))))
            issue('DDN-INTERFACE-COMPATIBILITY', 'Provided interfaces do not satisfy the declared required interface assertion', link.item.ref);
        const reverseRequired = assertions(source, 'requires'), reverseProvided = assertions(target, 'provides');
        if (reverseRequired.length && !reverseRequired.every(r => reverseProvided.some(p => compatible(p, r))))
            issue('DDN-INTERFACE-COMPATIBILITY', 'Reverse provided interfaces do not satisfy the declared required interface assertion', link.item.ref);
        if (profileId === 'soaml.services@1') {
            const service = object(meta(source, 'x_service')), request = object(meta(target, 'x_service'));
            const a = resolve(getPath(source.record, 'content.schema'), source), b = resolve(getPath(target.record, 'content.schema'), target);
            if (service.kind === 'service' && request.kind === 'request') {
                if (!a || !b)
                    incomplete('Service/request ports require interface types', link.item.ref);
                else if (!compatible(a, b))
                    issue('DDN-SERVICE-COMPATIBILITY', 'Service and request interface types are incompatible under the selected mode', link.item.ref);
            }
        }
    }
    const treeProfiles = ['org.tree@1', 'wbs.tree@1'];
    if (treeProfiles.includes(profileId)) {
        if (review && nodes.length && nodes.filter(n => !incoming(n).length).length !== 1)
            issue('DDN-TREE-ROOT', 'Exactly one decomposition root is required');
        if (nodes.some(n => incoming(n).length > 1))
            issue('DDN-TREE-PARENT', 'A child cannot have multiple parents');
        cycle(links, 'DDN-TREE-CYCLE');
    }
    if (profileId === 'family.tree@1') {
        const parents = links.filter(l => /parent/.test(role(l.item)));
        cycle(parents, 'DDN-FAMILY-CYCLE');
        for (const n of nodes)
            if (incoming(n, parents).length > 2)
                issue('DDN-FAMILY-PARENTS', 'At most two parents are supported', n.ref);
    }
    if (/^(flow\.|uml\.activity|sysml\.activity)/.test(profileId)) {
        const flow = links.filter(l => ['flow.next', 'flow.continues', 'uml.flow'].includes(role(l.item))), active = nodes.filter(n => !/annotation|note|data|lane|group/.test(role(n)));
        const starts = active.filter(n => /(?:^|\.)start$|initial$/.test(role(n))), ends = active.filter(n => /(?:^|\.)end$|final$|terminate$/.test(role(n)));
        if (review && active.length && (!starts.length || !ends.length))
            issue('DDN-FLOW-TERMINALS', 'Completed flow requires a start and an end');
        for (const n of starts)
            if (incoming(n, flow).length)
                issue('DDN-FLOW-START', 'Start cannot have incoming control flow', n.ref);
        for (const n of ends)
            if (outgoing(n, flow).length)
                issue('DDN-FLOW-END', 'End cannot have outgoing control flow', n.ref);
        for (const n of active) {
            const ins = incoming(n, flow), outs = outgoing(n, flow);
            if (/decision$/.test(role(n)) && review) {
                const labels = outs.map(l => text(getPath(l.item.record, 'metadata.x_diagram.branch')) || text(l.item.record.title));
                if (outs.length < 2 || labels.some(s => !s.trim()) || new Set(labels).size !== labels.length)
                    issue('DDN-FLOW-BRANCH', 'Decisions require at least two distinct nonempty branch labels', n.ref);
            }
            if (/forkjoin$/.test(role(n)) && review && !(ins.length === 1 && outs.length >= 2 || ins.length >= 2 && outs.length === 1))
                issue('DDN-ACTIVITY-FAN', 'Fork/join requires a valid split or join fan', n.ref);
            if (/merge$/.test(role(n)) && review && (ins.length < 2 || outs.length !== 1))
                issue('DDN-ACTIVITY-MERGE', 'Merge requires at least two incoming and exactly one outgoing flow', n.ref);
            if (/fork$/.test(role(n)) && review && (ins.length !== 1 || outs.length < 2) || /join$/.test(role(n)) && review && (ins.length < 2 || outs.length !== 1))
                issue('DDN-ACTIVITY-FAN', 'Fork and join fan counts are invalid', n.ref);
        }
        const reachable = (origins, reverse) => { const visited = new Set(origins.map(key)), queue = [...origins]; for (let i = 0; i < queue.length; i++)
            for (const l of reverse ? incoming(queue[i], flow) : outgoing(queue[i], flow)) {
                const next = reverse ? l.from : l.to;
                if (!visited.has(key(next))) {
                    visited.add(key(next));
                    queue.push(next);
                }
            } return visited; };
        if (review && starts.length && ends.length) {
            const from = reachable(starts, false), to = reachable(ends, true);
            for (const n of active)
                if (!from.has(key(n)) || !to.has(key(n)))
                    issue('DDN-FLOW-REACHABILITY', 'Every control node must be reachable from a start and able to reach an end', n.ref);
        }
        const continuations = nodes.filter(n => meta(n, 'x_continuation') !== undefined), groups = new Map();
        for (const n of continuations) {
            const k = text(object(meta(n, 'x_continuation')).key);
            groups.set(k, [...groups.get(k) ?? [], n]);
        }
        for (const [id, pair] of groups) {
            const source = pair.find(n => object(meta(n, 'x_continuation')).side === 'out'), target = pair.find(n => object(meta(n, 'x_continuation')).side === 'in');
            if (review && (pair.length !== 2 || !source || !target || !flow.some(l => role(l.item) === 'flow.continues' && l.from === source && l.to === target)))
                issue('DDN-FLOW-CONTINUATION', 'Continuation ' + id + ' requires one outgoing and one incoming connector joined by flow.continues');
        }
        const lanes = new Set([...nodes.filter(n => /lane$/.test(role(n))).flatMap(n => [n.ref.id, text(n.record.name)]), ...regions.flatMap(region => [text(region.id), text(region.name)])]);
        for (const n of nodes)
            if (meta(n, 'x_partition') !== undefined && !lanes.has(text(object(meta(n, 'x_partition')).lane)))
                issue('DDN-ACTIVITY-PARTITION', 'Partition must name a declared lane', n.ref);
    }
    if (profileId.startsWith('dfd.')) {
        const processes = nodes.filter(n => role(n) === 'dfd.process');
        unique(processes.map(n => text(object(meta(n, 'x_diagram')).number)), 'DDN-DFD-NUMBER', 'Process numbers must be unique');
        for (const n of processes)
            if (review && (!text(object(meta(n, 'x_diagram')).number) || !incoming(n).length || !outgoing(n).length))
                incomplete('Completed process needs a number and incoming/outgoing data flow', n.ref);
        for (const l of links)
            if (role(l.from) !== 'dfd.process' && role(l.to) !== 'dfd.process')
                issue('DDN-DFD-BYPASS', 'A data flow requires a process at one end', l.item.ref);
    }
    const composition = [];
    for (const link of links) {
        const sourceMark = getPath(link.item.record, 'qualifiers.source.mark'), targetMark = getPath(link.item.record, 'qualifiers.target.mark');
        const aggregates = ['diamond', 'filled-diamond'];
        if (aggregates.includes(text(sourceMark)) && aggregates.includes(text(targetMark)))
            issue('DDN-ASSOCIATION-AGGREGATION', 'Aggregation/composition may be declared at only one association end', link.item.ref);
        if (sourceMark === 'filled-diamond' || role(link.item) === 'sysml.composition')
            composition.push(link);
        else if (targetMark === 'filled-diamond')
            composition.push({ ...link, from: link.to, to: link.from });
        for (const side of ['source', 'target']) {
            const cardinality = object(getPath(link.item.record, 'qualifiers.' + side + '.cardinality'));
            if (finite(cardinality.min) && finite(cardinality.max) && cardinality.min > cardinality.max)
                issue('DDN-CARDINALITY-ORDER', 'Cardinality minimum cannot exceed maximum', link.item.ref);
        }
    }
    if (composition.length) {
        cycle(composition, 'DDN-COMPOSITION-CYCLE');
        for (const node of nodes)
            if (incoming(node, composition).length > 1)
                issue('DDN-COMPOSITION-OWNER', 'A composed part cannot have multiple composite owners', node.ref);
    }
    const generalizations = links.filter(l => /generaliz|\.extends$/.test(role(l.item)));
    if (generalizations.length) {
        cycle(generalizations, 'DDN-GENERALIZATION-CYCLE');
        for (const l of generalizations)
            if (role(l.from) !== role(l.to))
                issue('DDN-GENERALIZATION-KIND', 'Generalization endpoints must have the same classifier kind', l.item.ref);
    }
    if (/^uml\.|^sysml\.|^soaml\./.test(profileId)) {
        const sets = new Map();
        for (const link of links)
            if (meta(link.item, 'x_genset') !== undefined) {
                if (!generalizations.includes(link))
                    issue('DDN-GENERALIZATION-SET', 'Generalization sets belong only to generalization relations', link.item.ref);
                const name = text(object(meta(link.item, 'x_genset')).name);
                sets.set(name, [...sets.get(name) ?? [], link]);
            }
        for (const set of sets.values())
            if (set.some(link => link.to !== set[0].to || stableStringify(meta(link.item, 'x_genset') ?? null) !== stableStringify(meta(set[0].item, 'x_genset') ?? null)))
                issue('DDN-GENERALIZATION-SET', 'Members of a named generalization set must share a general classifier and flags', set[0].item.ref);
        for (const n of nodes) {
            if (meta(n, 'x_template') !== undefined && !['uml.class', 'uml.interface', 'uml.component', 'uml.enumeration', 'sysml.block', 'sysml.interfaceblock', 'sysml.valuetype'].includes(role(n)))
                issue('DDN-TEMPLATE-OWNER', 'Templates belong to classifiers', n.ref);
            for (const field of members(n)) {
                const kind = object(meta(field, 'x_member')).kind;
                if (kind === 'literal' && role(n) !== 'uml.enumeration' || role(n) === 'uml.enumeration' && kind !== undefined && kind !== 'literal')
                    issue('DDN-ENUMERATION-MEMBER', 'Enumeration members are literals and literal members belong to enumerations', field.ref);
                if (role(n) === 'uml.enumeration' && kind === undefined)
                    incomplete('Enumeration members require the literal member kind', field.ref);
                const part = object(meta(field, 'x_part'));
                if (part.classifier !== undefined) {
                    const classifier = resolve(part.classifier, field);
                    if (!classifier || !['uml.class', 'uml.interface', 'uml.component', 'uml.collaboration', 'sysml.block', 'sysml.interfaceblock', 'sysml.valuetype'].includes(role(classifier)))
                        issue('DDN-PART-CLASSIFIER', 'Composite part type must resolve to a classifier', field.ref);
                }
            }
        }
        const packageParent = (n) => resolve(object(meta(n, 'x_pack')).package, n);
        for (const n of nodes) {
            const seen = new Set([key(n)]);
            let parent = packageParent(n);
            while (parent) {
                if (seen.has(key(parent))) {
                    issue('DDN-PACKAGE-CYCLE', 'Package ownership cannot cycle', n.ref);
                    break;
                }
                seen.add(key(parent));
                parent = packageParent(parent);
            }
        }
        for (const l of links) {
            if (/import|access/.test(role(l.item)) && object(meta(l.to, 'x_pack')).visibility === 'private' && packageParent(l.from) !== packageParent(l.to))
                issue('DDN-PACKAGE-PRIVATE', 'Private package content cannot be imported from another package', l.item.ref);
            if (/merge/.test(role(l.item))) {
                let ancestor = l.from;
                const seen = new Set();
                while (ancestor && !seen.has(key(ancestor))) {
                    seen.add(key(ancestor));
                    if (ancestor === l.to) {
                        issue('DDN-PACKAGE-MERGE', 'A package cannot merge itself or an ancestor', l.item.ref);
                        break;
                    }
                    ancestor = packageParent(ancestor);
                }
            }
            if (meta(l.item, 'x_association_class') !== undefined && !selectedRef(object(meta(l.item, 'x_association_class')).class, l.item, ['uml.class', 'cls']))
                issue('DDN-ASSOCIATION-CLASS', 'Association class must resolve to a selected classifier', l.item.ref);
            if (/communication_path|communicationpath/.test(role(l.item)) && Object.values(object(meta(l.item, 'x_endlabels'))).some(v => object(v).qualifier !== undefined))
                issue('DDN-DEPLOYMENT-QUALIFIER', 'Communication paths cannot carry qualifiers', l.item.ref);
        }
    }
    if (/usecase/.test(profileId)) {
        cycle(links.filter(l => /include|generaliz/.test(role(l.item))), 'DDN-USECASE-CYCLE');
        if (!profileId.endsWith('@1') || profileId.startsWith('sysml.'))
            for (const l of links.filter(l => /include|extend/.test(role(l.item)))) {
                const subjects = (n) => array(object(meta(n, 'x_usecase')).subjects).map(ref => resolve(ref, n)).filter(Boolean);
                const a = subjects(l.from), b = subjects(l.to);
                if (review && (!a.length || !b.length))
                    incomplete('Use cases require declared subjects', l.item.ref);
                else if (a.length && !a.some(s => b.includes(s)))
                    issue('DDN-USECASE-SUBJECT', 'Include and extend endpoints must share a subject', l.item.ref);
                if (/extend/.test(role(l.item))) {
                    const detail = object(meta(l.item, 'x_usecase'));
                    if (detail.condition !== undefined && detail.condition_ref !== undefined)
                        issue('DDN-USECASE-CONDITION', 'Extend cannot have conflicting condition forms', l.item.ref);
                    if (!array(object(meta(l.to, 'x_usecase')).extension_points).includes(detail.extension_point ?? ''))
                        issue('DDN-USECASE-EXTENSION', 'Extend must target a declared extension point', l.item.ref);
                }
            }
    }
    if (profileId === 'requirements.basic@1' || profileId === 'sysml.requirements@1') {
        const requirements = nodes.filter(n => /requirement$/.test(role(n)));
        unique(requirements.map(n => text(object(meta(n, 'x_diagram')).code)), 'DDN-REQUIREMENT-CODE', 'Requirement codes must be unique');
        for (const n of requirements)
            if (review && (!text(object(meta(n, 'x_diagram')).code).trim() || !text(object(meta(n, 'x_diagram')).text).trim()))
                incomplete('A completed requirement needs nonempty code and text', n.ref);
    }
    if (profileId.startsWith('chen.')) {
        for (const l of links) {
            if (l.ends.some(e => e.member !== undefined))
                issue('DDN-CHEN-MEMBER', 'Chen relationships connect entities, not member endpoints', l.item.ref);
            const extras = array(object(meta(l.item, 'x_nary')).ends);
            if (extras.length && profileId !== 'chen.nary@3')
                issue('DDN-CHEN-NARY', 'N-ary associations require chen.nary@3', l.item.ref);
            if (extras.length) {
                const ends = [l.from, l.to, ...extras.map(v => selectedRef(object(v).element, l.item, ['entity']))];
                if (role(l.item) !== 'assoc' || ends.some(e => !e) || new Set(ends.filter((e) => !!e).map(key)).size !== ends.length)
                    issue('DDN-CHEN-NARY-ENDS', 'N-ary assoc ends must be distinct selected entities', l.item.ref);
            }
            if (profileId !== 'chen.basic@1' && review)
                for (const side of ['from', 'to']) {
                    const card = object(object(meta(l.item, 'x_chen'))[side]);
                    if (card.min === undefined || card.max === undefined)
                        incomplete('Chen participant ends require explicit min/max bounds', l.item.ref);
                }
        }
        const ownerLinks = [];
        for (const n of nodes) {
            const chen = object(meta(n, 'x_chen'));
            for (const field of members(n)) {
                const c = object(meta(field, 'x_chen'));
                if ((c.key || c.partial_key) && (c.derived || c.multivalued))
                    issue('DDN-CHEN-KEY', 'A key cannot be derived or multivalued', field.ref);
            }
            if (chen.weak) {
                const owner = selectedRef(chen.owner, n, ['entity']);
                if (!owner || owner === n)
                    issue('DDN-CHEN-OWNER', 'Weak entity requires a different selected entity owner', n.ref);
                else
                    ownerLinks.push({ from: owner, to: n, item: n, ends: [] });
                const identifying = links.filter(l => object(meta(l.item, 'x_chen')).identifying && [l.from, l.to].includes(n));
                if (review && (!members(n).some(f => object(meta(f, 'x_chen')).partial_key) || identifying.length !== 1))
                    incomplete('Weak entity requires a partial key and exactly one identifying relation', n.ref);
            }
        }
        cycle(ownerLinks, 'DDN-CHEN-OWNER-CYCLE');
    }
    if (profileId === 'erd.crowfoot@1')
        for (const l of links) {
            const ends = object(meta(l.item, 'x_endlabels'));
            for (const side of ['source', 'target']) {
                const card = object(object(meta(l.item, 'x_chen'))[side === 'source' ? 'from' : 'to']);
                const derived = card.min === 1 && card.max === 1 ? 'one' : card.min === 0 && card.max === 1 ? 'zeroone' : card.min === 1 && card.max === 'many' ? 'many' : card.min === 0 && card.max === 'many' ? 'zeromany' : undefined;
                const mark = getPath(l.item.record, 'properties.' + (side === 'source' ? 'source_mark' : 'target_mark')) ?? object(ends[side]).multiplicity ?? derived;
                if (mark === undefined)
                    incomplete('Crows-foot connections require both endpoint marks', l.item.ref);
                else if (!['one', 'zeroone', 'many', 'zeromany'].includes(String(mark)))
                    issue('DDN-CROWFOOT-MARK', 'Unknown crows-foot endpoint mark', l.item.ref);
            }
        }
    if (profileId === 'uml.deployment@1' || profileId === 'c4.deployment@1')
        for (const region of regions) {
            if (region.scope !== undefined) {
                const scope = resolve(region.scope);
                if (!scope || !['uml.node', 'uml.device', 'uml.executionenv'].includes(role(scope)))
                    issue('DDN-DEPLOYMENT-SCOPE', 'Deployment regions must scope a node, device or execution environment');
            }
        }
    if (profileId.startsWith('c4.')) {
        for (const link of links)
            if (link.ends.some(end => end.member !== undefined))
                issue('DDN-C4-MEMBER', 'C4 relationships connect elements, not fields or ports', link.item.ref);
        if (['c4.container@1', 'c4.component@1'].includes(profileId)) {
            const scopeRole = profileId === 'c4.container@1' ? 'c4.system' : 'c4.container';
            const scoped = regions.filter(region => { const owner = resolve(region.scope); return owner && role(owner) === scopeRole; });
            if (review && scoped.length !== 1)
                incomplete('C4 subtype requires exactly one region scoped to its parent ' + scopeRole);
            if (scoped.length === 1) {
                const members = new Set(array(scoped[0].members).map(ref => resolve(ref)).filter((n) => !!n).map(key));
                const inside = profileId === 'c4.container@1' ? ['c4.container', 'c4.store', 'c4.queue'] : ['c4.component'];
                for (const n of nodes.filter(n => inside.includes(role(n))))
                    if (!members.has(key(n)))
                        issue('DDN-C4-SCOPE', 'Interior element must belong to the enclosing scope', n.ref);
            }
        }
    }
    if (profileId.startsWith('epc.')) {
        const flow = links.filter(l => /flow|next/.test(role(l.item)));
        for (const l of flow)
            if (role(l.from) === role(l.to) && ['epk.event', 'epk.function'].includes(role(l.from)))
                issue('DDN-EPC-ALTERNATION', 'Events and functions cannot connect directly to their own kind', l.item.ref);
        for (const n of nodes.filter(n => role(n) === 'epk.connector')) {
            if (!['and', 'or', 'xor'].includes(text(object(meta(n, 'x_epc')).operator)))
                incomplete('EPC connectors require and/or/xor operator', n.ref);
            if (profileId === 'epc.complete@1' && review && !(incoming(n, flow).length === 1 && outgoing(n, flow).length >= 2 || incoming(n, flow).length >= 2 && outgoing(n, flow).length === 1))
                issue('DDN-EPC-FAN', 'Connector must be a split or a join', n.ref);
        }
    }
    if (profileId.startsWith('bpmn.')) {
        const pool = (n) => { const region = regionOf(n); if (region) {
            let current = region;
            const seen = new Set();
            while (current.parent !== undefined && !seen.has(text(current.id))) {
                seen.add(text(current.id));
                const parent = regions.find(r => r.id === current.parent);
                if (!parent)
                    break;
                current = parent;
            }
            return text(current.id);
        } return text(object(meta(n, 'x_diagram')).owner) || text(object(meta(n, 'x_partition')).lane); };
        for (const l of links) {
            if (/message/.test(role(l.item)) && pool(l.from) && pool(l.from) === pool(l.to))
                issue('DDN-BPMN-MESSAGE-POOL', 'Message flow must cross pool boundaries', l.item.ref);
            if (['flow.next', 'uml.flow'].includes(role(l.item)) && pool(l.from) && pool(l.to) && pool(l.from) !== pool(l.to))
                issue('DDN-BPMN-SEQUENCE-POOL', 'Sequence flow cannot cross pool boundaries', l.item.ref);
        }
        for (const n of nodes) {
            if (/gateway/.test(role(n)) && meta(n, 'x_gateway') === undefined)
                incomplete('Gateway type must be explicit', n.ref);
            if (role(n) === 'flow.gateway' && profileId !== 'bpmn.basic@1') {
                const control = links.filter(link => ['flow.next', 'uml.flow'].includes(role(link.item))), ins = incoming(n, control).length, outs = outgoing(n, control).length, type = object(meta(n, 'x_gateway')).type;
                if (review && (!ins || !outs || ins + outs < 3))
                    incomplete('Gateway needs incoming/outgoing sequence flow and a split or join', n.ref);
                if (['event', 'event_exclusive'].includes(text(type)) && (ins > 1 || review && outs < 2))
                    issue('DDN-BPMN-GATEWAY', 'Event gateways require one incoming flow and at least two outgoing flows', n.ref);
            }
            const event = object(meta(n, 'x_event'));
            if (Object.keys(event).length) {
                const position = text(event.position) || (/start/.test(role(n)) ? 'start' : /end/.test(role(n)) ? 'end' : /boundary/.test(role(n)) ? 'boundary' : 'intermediate');
                if (position === 'start' && ['terminate', 'cancel', 'error', 'compensation'].includes(text(event.type)) || position === 'end' && ['timer', 'conditional', 'link', 'parallel_multiple'].includes(text(event.type)))
                    issue('DDN-BPMN-TRIGGER', 'Event trigger is not legal at its position', n.ref);
                if (position === 'boundary') {
                    const target = selectedRef(event.on, n);
                    if (!target || !/process|activity|task/.test(role(target)))
                        issue('DDN-BPMN-BOUNDARY', 'Boundary event must attach to a selected activity', n.ref);
                }
            }
            if (/choreotask/.test(role(n))) {
                const bands = array(meta(n, 'x_bands'));
                if (review && (bands.length < 2 || bands.length > 6 || new Set(bands).size !== bands.length))
                    issue('DDN-BPMN-BANDS', 'Choreography requires 2..6 distinct participants', n.ref);
            }
        }
    }
    if (/^state\.|statemachine|^sdl\.process/.test(profileId)) {
        const initials = nodes.filter(n => /initial$|sdl.start$/.test(role(n))), terminals = nodes.filter(n => /final$|terminate$|stop$/.test(role(n)) || object(meta(n, 'x_state')).terminal === true);
        if (profileId === 'state.flat@1') {
            if (review && initials.length !== 1)
                issue('DDN-STATE-INITIAL', 'Flat state machine requires exactly one initial marker');
            if (review && !terminals.length)
                incomplete('Flat state machine requires a terminal state');
            for (const n of nodes)
                if (members(n).length)
                    issue('DDN-STATE-NESTING', 'Flat states do not contain members or regions', n.ref);
        }
        else {
            const regions = new Map();
            for (const n of initials) {
                const region = regionKey(n);
                regions.set(region, (regions.get(region) ?? 0) + 1);
            }
            if ([...regions.values()].some(n => n > 1))
                issue('DDN-STATE-REGION', 'Each region permits at most one initial marker');
        }
        for (const n of nodes) {
            const ins = incoming(n), outs = outgoing(n);
            if (initials.includes(n) && (ins.length || review && outs.length !== 1))
                issue('DDN-STATE-INITIAL-FLOW', 'Initial requires no incoming and one outgoing transition', n.ref);
            if (terminals.includes(n) && outs.length)
                issue('DDN-STATE-TERMINAL', 'Terminal state cannot have outgoing transitions', n.ref);
            if (/choice$/.test(role(n)) && review && outs.length < 2 || /junction$/.test(role(n)) && review && (!ins.length || !outs.length))
                issue('DDN-STATE-FAN', 'Pseudostate fan count is invalid', n.ref);
            if (/history|entrypoint|exitpoint|entry_point|exit_point/.test(role(n)) && !regionKey(n))
                incomplete('History and entry/exit points require a composite region', n.ref);
            const state = object(meta(n, 'x_state'));
            if (role(n) !== 'state.state' && ['entry', 'exit', 'do', 'internal'].some(name => state[name] !== undefined))
                issue('DDN-STATE-COMPARTMENT', 'State behavior compartments belong only to state.state', n.ref);
            const sub = state.submachine;
            if (sub !== undefined && (!resolve(sub, n) || resolve(sub, n) === n || role(resolve(sub, n)) !== 'state.state'))
                issue('DDN-STATE-SUBMACHINE', 'Submachine must reference a different state', n.ref);
        }
        if (profileId === 'state.flat@1' && review && initials.length && terminals.length) {
            const reachable = (origins, reverse) => { const seen = new Set(origins.map(key)), queue = [...origins]; for (let i = 0; i < queue.length; i++)
                for (const edge of reverse ? incoming(queue[i]) : outgoing(queue[i])) {
                    const next = reverse ? edge.from : edge.to;
                    if (!seen.has(key(next))) {
                        seen.add(key(next));
                        queue.push(next);
                    }
                } return seen; };
            const from = reachable(initials, false), to = reachable(terminals, true);
            for (const node of nodes)
                if (!from.has(key(node)) || !to.has(key(node)))
                    issue('DDN-STATE-REACHABILITY', 'Every state must be reachable and able to reach a terminal', node.ref);
        }
        if (profileId === 'state.flat@1') {
            const transitionGroups = new Map();
            for (const l of links) {
                const t = object(meta(l.item, 'x_transition'));
                if (initials.includes(l.from)) {
                    if (t.event || t.guard !== undefined || array(t.actions).length)
                        issue('DDN-STATE-INITIAL-EFFECT', 'Initial transition must be unconditional and action-free', l.item.ref);
                }
                else if (!text(t.event))
                    incomplete('Noninitial transition requires an event', l.item.ref);
                if (t.effect !== undefined || typeof t.guard === 'string')
                    issue('DDN-STATE-EXECUTABLE-TEXT', 'Flat state evaluation accepts typed guard data and referenced actions only', l.item.ref);
                for (const action of array(t.actions))
                    if (!resolve(action, l.item))
                        issue('DDN-STATE-ACTION', 'Flat transition actions must resolve as references', l.item.ref);
                if (t.guard !== undefined && typeof t.guard !== 'string') {
                    const domains = decisionDomains(view, records);
                    if (!domains.length)
                        incomplete('Typed transition guards require declared input domains', l.item.ref);
                    else {
                        const checked = analyzeDecision(domains, [{ id: l.item.ref.id, inputs: {}, guard: t.guard, outputs: { state: l.to.ref.id } }], { hitPolicy: 'first', coverage: 'none' });
                        if (checked.outcome === 'invalid')
                            issue('DDN-STATE-GUARD', checked.errors.join('; '), l.item.ref);
                    }
                }
                const group = key(l.from) + ':' + text(t.event);
                transitionGroups.set(group, [...transitionGroups.get(group) ?? [], l]);
            }
            for (const group of transitionGroups.values())
                if (group.length > 1) {
                    const domains = decisionDomains(view, records);
                    const rules = group.map(l => ({ id: l.item.ref.id, inputs: {}, guard: object(meta(l.item, 'x_transition')).guard, outputs: { state: l.to.ref.id } }));
                    const analysis = analyzeDecision(domains, rules, { hitPolicy: 'unique', coverage: 'none', budget: finite(getPath(view.record, 'projection.options.analysis_budget')) ? getPath(view.record, 'projection.options.analysis_budget') : 4096 });
                    if (analysis.outcome === 'budget_exceeded')
                        issue('DDN-ANALYSIS-BUDGET', 'Transition disjointness exceeded its bounded analysis budget', view.ref, 'warning');
                    else if (analysis.outcome === 'invalid')
                        issue('DDN-STATE-AMBIGUITY', 'Same-state/event alternatives are not provably disjoint', view.ref);
                }
        }
        if (profileId === 'sdl.process@1') {
            if (review && nodes.filter(n => role(n) === 'state.initial').length !== 1)
                issue('DDN-SDL-START', 'SDL process requires exactly one start');
            for (const n of nodes) {
                if (/^sdl\.(input|output|task|save|create|set|reset)$/.test(role(n)) && review && !outgoing(n).length)
                    incomplete('SDL process step needs an outgoing transition', n.ref);
                const timer = object(meta(n, 'x_sdl')).timer;
                if (timer !== undefined && role(resolve(timer, n) ?? n) !== 'sdl.timer')
                    issue('DDN-SDL-TIMER', 'Timer reference must resolve to sdl.timer', n.ref);
            }
        }
    }
    if (profileId.startsWith('uml.object'))
        for (const n of nodes.filter(n => role(n) === 'object' || meta(n, 'x_instance') !== undefined)) {
            const instance = object(meta(n, 'x_instance')), classifier = resolve(instance.classifier, n);
            if (!classifier) {
                incomplete('Instance must name a classifier', n.ref);
                continue;
            }
            const fields = members(classifier);
            for (const [name, value] of Object.entries(object(instance.slots))) {
                const field = fields.find(f => f.record.name === name);
                if (fields.length && !field)
                    issue('DDN-INSTANCE-SLOT', 'Slot does not belong to its declared classifier: ' + name, n.ref);
                if (field && profileId.endsWith('@2')) {
                    const type = text(getPath(field.record, 'content.datatype'));
                    if (/^(int|integer|number|float|double|real)/i.test(type) && !finite(value) || /^(bool)/i.test(type) && typeof value !== 'boolean')
                        issue('DDN-INSTANCE-TYPE', 'Slot value does not match the declared bounded datatype', n.ref);
                }
            }
        }
    if (/communication|c4.dynamic/.test(profileId)) {
        const numbers = [];
        for (const edge of edges) {
            const number = text(object(meta(edge, 'x_message')).seq);
            if (!/^\d+(?:\.\d+)*(?:[a-z])?$/.test(number))
                incomplete('Communication message requires explicit dotted sequence numbering', edge.ref);
            else
                numbers.push(number);
            if (object(meta(edge, 'x_message')).sort === 'reply' && number && !edges.some(request => request !== edge && object(meta(request, 'x_message')).sort !== 'reply' && number.startsWith(text(object(meta(request, 'x_message')).seq) + '.')))
                issue('DDN-MESSAGE-REPLY', 'Reply numbering must be dotted beneath an existing request number', edge.ref);
        }
        unique(numbers, 'DDN-MESSAGE-SEQUENCE', 'Communication sequence numbers must be unique');
    }
    if (profile.projection === 'sequence' || profile.projection === 'timing' || /communication|c4.dynamic/.test(profileId)) {
        for (const l of links) {
            if (!selected.has(key(l.from)) || !selected.has(key(l.to)) || l.ends.some(e => e.member !== undefined))
                issue('DDN-INTERACTION-ENDPOINT', 'Interaction endpoints must be selected participants', l.item.ref);
            const message = object(meta(l.item, 'x_message'));
            if (message.sort === 'lost' && message.gate !== 'target' || message.sort === 'found' && message.gate !== 'source')
                issue('DDN-MESSAGE-GATE', 'Lost/found messages require their respective target/source gate', l.item.ref);
        }
        for (const n of nodes) {
            if (profile.projection === 'sequence' && !incoming(n).length && !outgoing(n).length)
                issue('DDN-SEQUENCE-UNUSED', 'Selected lifeline has no messages', n.ref, 'warning');
            if (profile.projection === 'timing') {
                const states = array(meta(n, 'x_states'));
                let last = -Infinity;
                if (!states.length)
                    incomplete('Timing participants require state entries', n.ref);
                for (const state of states) {
                    const entry = object(state), at = Array.isArray(state) ? state[0] : entry.at ?? entry.time;
                    if (!finite(at) || at <= last || !(Array.isArray(state) ? typeof state[1] === 'string' : typeof (entry.state ?? entry.value) === 'string'))
                        issue('DDN-TIMING-ORDER', 'Timing states require named states and strictly increasing numeric times', n.ref);
                    else
                        last = at;
                }
            }
            for (const activation of array(meta(n, 'x_activation'))) {
                const a = resolve(object(activation).from, n), b = resolve(object(activation).to, n);
                if (!a || !b || !edges.includes(a) || !edges.includes(b) || edges.indexOf(a) > edges.indexOf(b))
                    issue('DDN-SEQUENCE-ACTIVATION', 'Activation anchors must resolve in message order', n.ref);
            }
            for (const invariant of array(meta(n, 'x_invariant')))
                if (!edges.includes(resolve(object(invariant).after, n)))
                    issue('DDN-SEQUENCE-INVARIANT', 'Invariant anchor must resolve to a selected message', n.ref);
        }
        const fragments = (value, owner, depth = 0) => { if (value === undefined)
            return; if (depth > 16) {
            issue('DDN-FRAGMENT-DEPTH', 'Fragment nesting exceeds 16', owner.ref);
            return;
        } const fragment = object(value), used = new Set(); for (const operand of array(fragment.operands)) {
            for (const ref of array(object(operand).messages)) {
                const message = resolve(ref, owner);
                if (!message || !edges.includes(message))
                    issue('DDN-FRAGMENT-MESSAGE', 'Fragment message must resolve to selected interaction', owner.ref);
                else if (used.has(key(message)))
                    issue('DDN-FRAGMENT-OVERLAP', 'Message cannot belong to overlapping sibling operands', owner.ref);
                else
                    used.add(key(message));
            }
            for (const child of array(object(operand).fragments))
                fragments(child, owner, depth + 1);
        } };
        for (const edge of edges)
            fragments(meta(edge, 'x_fragment'), edge);
    }
    if (profileId.startsWith('cmmn.')) {
        if (profileId === 'cmmn.complete@1' && review && nodes.filter(n => role(n) === 'cmmn.caseplan').length !== 1)
            issue('DDN-CMMN-CASEPLAN', 'Completed CMMN view requires exactly one case plan');
        for (const n of nodes.filter(n => role(n) === 'cmmn.sentry')) {
            const sentry = object(meta(n, 'x_sentry'));
            if (!['entry', 'exit'].includes(text(sentry.on)))
                incomplete('Sentry must declare entry or exit', n.ref);
            if ((!regionOwner(n) || role(regionOwner(n)) !== 'cmmn.stage'))
                incomplete('Sentry must belong to a stage', n.ref);
            for (const p of ['attach', 'on_part'])
                if (sentry[p] !== undefined && !selectedRef(sentry[p], n))
                    issue('DDN-CMMN-SENTRY', 'Sentry references must resolve in the selected case', n.ref);
        }
    }
    if (profileId.startsWith('sysml.')) {
        for (const n of nodes)
            for (const member of members(n))
                if (role(member) === 'core::Port' && meta(member, 'x_pin') === undefined && !(profileId.endsWith('@2') ? /^sysml\.(block|interfaceblock|constraint|valuetype|flowspec)$/.test(role(n)) : role(n) === 'sysml.block'))
                    issue('DDN-SYSML-PORT-OWNER', 'Port owner is not admitted by this SysML version', member.ref);
        if (profileId.startsWith('sysml.parametric'))
            for (const n of nodes.filter(n => role(n) === 'sysml.constraint')) {
                const bindings = links.filter(l => l.from === n || l.to === n);
                if (profileId.endsWith('@1') && bindings.length > 2)
                    issue('DDN-PARAMETRIC-BINDINGS', 'Version-1 constraints admit exactly two incident bindings', n.ref);
                else if (profileId.endsWith('@1') ? bindings.length < 2 : bindings.length < 1)
                    incomplete('Constraint has the wrong binding count for this profile version', n.ref);
            }
    }
    if (profileId === 'archimate.basic@1') {
        const layer = (n) => /business/.test(role(n)) ? 2 : /application/.test(role(n)) ? 1 : /technology/.test(role(n)) ? 0 : -1;
        for (const l of links)
            if (layer(l.from) > layer(l.to))
                issue('DDN-ARCHIMATE-LAYER', 'Only same-layer or upward serving relations are supported', l.item.ref);
    }
    if (profileId === 'pert.cpm@1') {
        try {
            if (review || nodes.every(n => finite(meta(n, 'x_estimate'))))
                calculateCriticalPath(nodes.map(n => ({ id: key(n), duration: meta(n, 'x_estimate') })), links.map(l => ({ id: key(l.item), from: key(l.from), to: key(l.to) })));
        }
        catch (error) {
            issue('DDN-CPM', error instanceof Error ? error.message : String(error));
        }
    }
    if (profileId === 'fault.tree@1' || profileId === 'event.tree@1') {
        cycle(links, 'DDN-GATE-CYCLE');
        for (const n of nodes.filter(n => /gate$/.test(role(n))))
            if (review && (!['and', 'or'].includes(text(object(meta(n, 'x_gate')).type)) || incoming(n).length < 2))
                incomplete('Gate needs an and/or type and at least two inputs', n.ref);
    }
    if (profileId.startsWith('network.')) {
        for (const l of links.filter(l => /attach/.test(role(l.item))))
            if (!/bus$/.test(role(l.to)) && !/bus$/.test(role(l.from)) && l.ends.every(e => e.member === undefined))
                issue('DDN-NETWORK-ATTACHMENT', 'Attachment requires a bus or declared port', l.item.ref);
        const slots = new Map();
        for (const n of nodes) {
            const rack = object(meta(n, 'x_rack'));
            if (rack.unit !== undefined && (profileId === 'network.rack@1' || regionOwner(n))) {
                const owner = regionOwner(n), max = owner && object(meta(owner, 'x_rack')).units;
                if (!owner || !finite(max) || !finite(rack.unit) || rack.unit > max)
                    issue('DDN-RACK-SLOT', 'Rack slot must be inside its declared rack', n.ref);
                else {
                    const used = slots.get(key(owner)) ?? new Set();
                    if (used.has(rack.unit))
                        issue('DDN-RACK-DUPLICATE', 'Rack slots must be unique', n.ref);
                    used.add(rack.unit);
                    slots.set(key(owner), used);
                }
            }
        }
    }
    if (profileId === 'wireframe.ui@1')
        for (const n of nodes.filter(n => role(n) !== 'ui.frame'))
            if ((!regionOwner(n) || role(regionOwner(n)) !== 'ui.frame'))
                issue('DDN-UI-FRAME', 'Control is not assigned to a UI frame', n.ref, 'warning');
    if (profileId === 'idef0.basic@1') {
        unique(nodes.map(n => text(object(meta(n, 'x_idef0')).node)), 'DDN-IDEF0-NUMBER', 'IDEF0 node codes must be unique');
        for (const n of nodes)
            for (const member of members(n)) {
                const icom = text(object(meta(member, 'x_icom')).type), rawSide = getPath(member.record, 'content.side') ?? getPath(member.record, 'properties.side'), side = { west: 'left', east: 'right', north: 'top', south: 'bottom' }[String(rawSide)] ?? rawSide;
                if (icom && side !== undefined && side !== { input: 'left', control: 'top', output: 'right', mechanism: 'bottom' }[icom])
                    issue('DDN-IDEF0-SIDE', 'ICOM pin type does not match its declared side', member.ref);
            }
    }
    if (profileId === 'petri.basic@1')
        for (const l of links)
            if (role(l.from) === role(l.to))
                issue('DDN-PETRI-BIPARTITE', 'Petri arcs must connect a place and transition', l.item.ref);
    if (profileId === 'orm.basic@1') {
        for (const n of nodes.filter(n => role(n) === 'orm.facttype'))
            if (!members(n).some(member => role(member) === 'field'))
                incomplete('Fact type requires at least one role field', n.ref);
        for (const link of links.filter(link => role(link.item) === 'orm.plays')) {
            const field = resolve(link.ends[0]?.member, link.item);
            if (!field)
                incomplete('ORM role-player relation requires a fact role field endpoint', link.item.ref);
            else if (role(field) !== 'field' || !members(link.from).includes(field) || link.ends[1]?.member !== undefined)
                issue('DDN-ORM-ROLE-ENDPOINT', 'ORM player links run from a fact role field to an entity/value player', link.item.ref);
        }
    }
    if (profileId === 'fbd.basic@1')
        for (const l of links) {
            const a = resolve(l.ends[0]?.member, l.item), b = resolve(l.ends[1]?.member, l.item);
            if (!a || !b)
                incomplete('Function block wires require pin endpoints', l.item.ref);
            else {
                const type = (n) => text(getPath(n.record, 'metadata.x_fbd.type'));
                for (const pin of [a, b])
                    if (getPath(pin.record, 'metadata.x_fbd.negated') === true && type(pin) !== 'BOOL')
                        issue('DDN-FBD-NEGATION', 'Only BOOL pins can be negated', pin.ref);
                if (type(a) !== type(b) || !['BOOL', 'INT', 'DINT', 'REAL', 'TIME', 'STRING', 'WORD'].includes(type(a)))
                    issue('DDN-FBD-TYPE', 'Wire pin datatypes must match the supported FBD types', l.item.ref);
            }
        }
    if (profileId === 'ladder.basic@1') {
        const layout = getPath(view.record, 'layout.algorithm');
        if (layout !== undefined && layout !== 'ladder')
            issue('DDN-LADDER-LAYOUT', 'Ladder diagrams require ladder layout');
        const rungs = new Map();
        for (const n of nodes) {
            const rung = regionKey(n);
            rungs.set(rung, [...rungs.get(rung) ?? [], n]);
        }
        for (const rung of rungs.values())
            if (review && rung.filter(n => role(n) === 'ladder.coil').length !== 1)
                issue('DDN-LADDER-COIL', 'Each rung requires exactly one output coil');
        for (const l of links)
            if (/series/.test(role(l.item)) && regionKey(l.from) !== regionKey(l.to))
                issue('DDN-LADDER-RUNG', 'Series links must stay in one rung', l.item.ref);
    }
    if (profileId === 'state.flat@1' && array(getPath(view.record, 'projection.options.traces')).length) {
        const traceResult = object(flatTraceAnalysis(view, records));
        if (traceResult.outcome === 'budget_exceeded')
            issue('DDN-ANALYSIS-BUDGET', 'Flat trace evaluation exceeded its work budget', view.ref, 'warning');
        else if (traceResult.outcome === 'incomplete')
            incomplete('Trace requires a declared expected final state');
        else if (traceResult.outcome !== 'valid')
            issue('DDN-STATE-TRACE', 'Declared trace failed input, transition or expected final-state validation');
    }
    else if (profileId !== 'state.flat@1' && array(getPath(view.record, 'projection.options.traces')).length)
        issue('DDN-STATE-TRACE-PROFILE', 'Trace evaluation is available only for state.flat@1');
    if (profileId === 'decision.rules@1') {
        const rules = decisionRules(view, records);
        for (const message of decisionOutputErrors(view, records, rules))
            issue('DDN-DECISION-OUTPUTS', message);
        const options = object(getPath(view.record, 'projection.options')), domains = decisionDomains(view, records);
        if (review || domains.length) {
            const analysis = analyzeDecision(domains, rules, { hitPolicy: text(options.hit_policy) || 'unique', coverage: text(options.coverage) || 'report', budget: finite(options.analysis_budget) ? options.analysis_budget : 4096 });
            if (analysis.outcome === 'budget_exceeded')
                issue('DDN-ANALYSIS-BUDGET', 'Decision proof exceeded its analysis budget', view.ref, 'warning');
            else if (analysis.outcome === 'invalid')
                issue('DDN-DECISION-RULES', analysis.errors.join('; ') || 'Decision overlap or coverage obligation failed');
            else if (analysis.uncovered.length)
                issue('DDN-DECISION-GAPS', 'Decision table has uncovered input cells', view.ref, 'warning');
        }
    }
    result.push(...projectionDiagnostics(view, records, review));
    return result;
}
export function decisionDomains(view, records) {
    const { resolve } = profileSelection(view, records);
    return array(getPath(view.record, 'projection.options.inputs')).flatMap((ref, index) => {
        const target = resolve(ref), raw = target && getPath(target.record, 'content.allowed_values');
        const name = typeof ref === 'string' ? ref : target ? text(target.record.name) || target.ref.id : '';
        if (!name || raw === undefined)
            return [{ name: name || 'input' + index, type: 'enum', values: [] }];
        if (Array.isArray(raw))
            return [{ name, type: 'enum', values: raw }];
        const d = object(raw);
        if (!['enum', 'boolean', 'number'].includes(text(d.type)))
            return [{ name, type: 'enum', values: [] }];
        return [{ name, type: d.type, ...(Array.isArray(d.values) ? { values: d.values } : {}), ...(finite(d.min) ? { min: d.min } : {}), ...(finite(d.max) ? { max: d.max } : {}), nullable: d.nullable === true, optional: d.optional === true }];
    });
}
export function decisionRules(view, records) {
    const { nodes } = profileSelection(view, records);
    if (getPath(view.record, 'projection.options.records') !== undefined)
        return projectionRows(view, records).map((row, index) => {
            const source = records.find(record => record.file === row.source.file && record.ref.id === row.source.id);
            const values = source?.owner === 'data' || source?.record.data !== undefined ? row.values : object(getPath(source?.record, 'metadata.x_rule'));
            return { id: row.source.file + '\0' + row.source.id + '#' + index, inputs: object(values.inputs), outputs: object(values.outputs) };
        });
    return nodes.filter(n => role(n) === 'rule.row').map(n => ({ id: key(n), inputs: object(object(meta(n, 'x_rule')).inputs), outputs: object(object(meta(n, 'x_rule')).outputs) }));
}
export function decisionOutputErrors(view, records, rules) {
    const declared = getPath(view.record, 'projection.options.outputs');
    if (declared === undefined)
        return [];
    const { resolve } = profileSelection(view, records), names = array(declared).map(reference => typeof reference === 'string' ? reference : text(resolve(reference)?.record.name) || resolve(reference)?.ref.id || '');
    if (!names.length || names.length > 20 || names.some(name => !name) || new Set(names).size !== names.length)
        return ['Output declarations require 1..20 unique names or resolved references'];
    return rules.some(rule => Object.keys(rule.outputs).length !== names.length || names.some(name => !Object.hasOwn(rule.outputs, name))) ? ['Every rule must supply exactly the declared output keys'] : [];
}
//# sourceMappingURL=semantic.js.map