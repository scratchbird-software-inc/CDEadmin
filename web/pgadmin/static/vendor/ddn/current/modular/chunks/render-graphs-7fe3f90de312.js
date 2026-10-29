/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"render-graphs-7fe3f90de312","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-5331ef8070e8","shared-6cf9d24a4527","shared-89ca0b52749b","shared-8f37b97a0edc","shared-98e37fe0f266","shared-aea9ceabbf71"],"modules":[{"id":"presentation/src/family-graphs.js","bytes":766,"sha256":"0b09628ea7cb2850c0b68a4cd9969d5fc16b0dc85ddb32e2eba3fc97c2055e54","dependencies":["presentation/src/adapters.js","presentation/src/graph-profiles.js","profiles/src/analysis-profile.js"]},{"id":"presentation/src/graph-catalogue.js","bytes":4325,"sha256":"a36aa7e85df6325afb9d692ac2834594f9f5bf0e09d73bbd6a5e75bd5bf9a4ed","dependencies":[]},{"id":"presentation/src/graph-profiles.js","bytes":88461,"sha256":"f07fca587f50b23558dbbb68f8f79aab1a3301daaf47a50cc2d25cec62d9e613","dependencies":["presentation/src/node-dimensions.js","presentation/src/relation-presentation.js","presentation/src/graph-common.js","presentation/src/graph-native.js","profiles/src/core.js","presentation/src/model.js","presentation/src/graph-layouts.js","presentation/src/table.js","presentation/src/graph-catalogue.js","presentation/src/graph-glyphs.js"]},{"id":"standalone/src/families/graphs.js","bytes":203,"sha256":"d2f80209da2a0b908c69c6a0c6c3297ee11758d56ac78a3122218187adcd51ab","dependencies":["presentation/src/family-graphs.js"]}],"hash":"b8d129fa40910da92c50c010fc3202b32311da5e6235e4df5bedf2b0e5de539f"},{"presentation/src/family-graphs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.graphsPresentation = void 0;
exports.installGraphsPresentation = installGraphsPresentation;
const adapters_js_1 = require("presentation/src/adapters.js");
const graph_profiles_js_1 = require("presentation/src/graph-profiles.js");
const analysis_profile_js_1 = require("profiles/src/analysis-profile.js");
exports.graphsPresentation = Object.freeze({ id: 'graphs', version: '1.0.0', language: 'ddn-next-1', profiles: graph_profiles_js_1.graphProfileIds, kind: 'graph', graph: graph_profiles_js_1.projectGraphProfile, analyze: analysis_profile_js_1.analyzeProfile });
function installGraphsPresentation() { (0, adapters_js_1.installPresentationFamily)(exports.graphsPresentation); }

},
"presentation/src/graph-catalogue.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.graphCatalogue = void 0;
exports.graphCatalogue = { "flow.basic@1": { "projection": "graph" }, "dfd.gane_sarson@1": { "projection": "graph" }, "dfd.yourdon@1": { "projection": "graph" }, "uml.structure@1": { "projection": "graph" }, "uml.structure@2": { "projection": "graph" }, "uml.deployment@1": { "projection": "graph" }, "uml.composite@1": { "projection": "graph" }, "uml.usecase@1": { "projection": "graph" }, "requirements.basic@1": { "projection": "graph" }, "chen.basic@1": { "projection": "chen" }, "fishbone.basic@1": { "projection": "fishbone" }, "state.flat@1": { "projection": "graph" }, "uml.usecase@2": { "projection": "graph" }, "uml.usecase@3": { "projection": "graph" }, "chen.binary@2": { "projection": "chen" }, "chen.nary@3": { "projection": "chen" }, "flow.documented@2": { "projection": "graph" }, "c4.context@1": { "projection": "graph" }, "c4.container@1": { "projection": "graph" }, "c4.component@1": { "projection": "graph" }, "org.tree@1": { "projection": "graph" }, "wbs.tree@1": { "projection": "graph" }, "epc.basic@1": { "projection": "graph" }, "erd.crowfoot@1": { "projection": "graph" }, "uml.sequence@1": { "projection": "sequence" }, "uml.sequence@2": { "projection": "sequence" }, "uml.communication@1": { "projection": "graph" }, "uml.communication@2": { "projection": "graph" }, "uml.object@1": { "projection": "graph" }, "uml.object@2": { "projection": "graph" }, "state.composite@1": { "projection": "graph" }, "uml.statemachine@1": { "projection": "graph" }, "uml.activity@1": { "projection": "graph" }, "uml.activity@2": { "projection": "graph" }, "bpmn.basic@1": { "projection": "graph" }, "bpmn.process@1": { "projection": "graph" }, "bpmn.choreography@1": { "projection": "graph" }, "bpmn.conversation@1": { "projection": "graph" }, "uml.timing@1": { "projection": "timing" }, "uml.timing@2": { "projection": "timing" }, "uml.interaction_overview@1": { "projection": "graph" }, "uml.interaction_overview@2": { "projection": "graph" }, "uml.profile@1": { "projection": "graph" }, "cmmn.basic@1": { "projection": "graph" }, "cmmn.complete@1": { "projection": "graph" }, "sysml.bdd@1": { "projection": "graph" }, "sysml.ibd@1": { "projection": "graph" }, "sysml.parametric@1": { "projection": "graph" }, "archimate.basic@1": { "projection": "graph" }, "pert.cpm@1": { "projection": "graph" }, "fault.tree@1": { "projection": "graph" }, "event.tree@1": { "projection": "graph" }, "network.basic@1": { "projection": "graph" }, "network.rack@1": { "projection": "graph" }, "wireframe.ui@1": { "projection": "graph" }, "family.tree@1": { "projection": "graph" }, "sysml.requirements@1": { "projection": "graph" }, "sysml.bdd@2": { "projection": "graph" }, "sysml.ibd@2": { "projection": "graph" }, "sysml.parametric@2": { "projection": "graph" }, "sysml.package@1": { "projection": "graph" }, "sysml.usecase@1": { "projection": "graph" }, "sysml.activity@1": { "projection": "graph" }, "sysml.sequence@1": { "projection": "sequence" }, "sysml.statemachine@1": { "projection": "graph" }, "dmn.drd@1": { "projection": "graph" }, "soaml.services@1": { "projection": "graph" }, "uaf.strategic@1": { "projection": "graph" }, "uaf.operational@1": { "projection": "graph" }, "uaf.services@1": { "projection": "graph" }, "uaf.systems@1": { "projection": "graph" }, "uaf.personnel@1": { "projection": "graph" }, "uaf.resources@1": { "projection": "graph" }, "uaf.security@1": { "projection": "graph" }, "uaf.projects@1": { "projection": "graph" }, "uaf.standards@1": { "projection": "graph" }, "uaf.actualresources@1": { "projection": "graph" }, "uaf.dictionary@1": { "projection": "graph" }, "uaf.summary@1": { "projection": "graph" }, "flow.iso5807@1": { "projection": "graph" }, "c4.deployment@1": { "projection": "graph" }, "c4.dynamic@1": { "projection": "graph" }, "epc.complete@1": { "projection": "graph" }, "msc.basic@1": { "projection": "sequence" }, "idef0.basic@1": { "projection": "graph" }, "petri.basic@1": { "projection": "graph" }, "orm.basic@1": { "projection": "graph" }, "vsm.basic@1": { "projection": "graph" }, "sdl.basic@1": { "projection": "graph" }, "sdl.process@1": { "projection": "graph" }, "fbd.basic@1": { "projection": "graph" }, "ladder.basic@1": { "projection": "graph" } };

},
"presentation/src/graph-profiles.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.graphProfileIds = void 0;
exports.projectGraphProfile = projectGraphProfile;
const node_dimensions_js_1 = require("presentation/src/node-dimensions.js");
const relation_presentation_js_1 = require("presentation/src/relation-presentation.js");
const graph_common_js_1 = require("presentation/src/graph-common.js");
const graph_native_js_1 = require("presentation/src/graph-native.js");
const core_js_1 = require("profiles/src/core.js");
const model_js_1 = require("presentation/src/model.js");
const graph_layouts_js_1 = require("presentation/src/graph-layouts.js");
const table_js_1 = require("presentation/src/table.js");
const graph_catalogue_js_1 = require("presentation/src/graph-catalogue.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
exports.graphProfileIds = Object.freeze(Object.keys(graph_catalogue_js_1.graphCatalogue));
function dimensions(entry, profile) {
    return (0, node_dimensions_js_1.graphNodeDimensions)((0, model_js_1.str)(entry.definition.record.role), profile, entry.item.bounds, entry.definition.record, typeof entry.appearance?.record.size === 'object');
}
function compartmentRows(entry, all, profile) {
    const result = [];
    const record = entry.definition.record, requirement = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_requirement')), diagram = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_diagram'));
    if (profile.startsWith('chen.'))
        return [];
    if (['req.requirement', 'sysml.requirement'].includes((0, model_js_1.str)(record.role))) {
        for (const key of ['code', 'text'])
            if (diagram[key])
                result.push({ group: 'requirement', label: String(diagram[key]), style: {} });
    }
    for (const key of ['id', 'owner', 'acceptance', 'state'])
        if (requirement[key])
            result.push({ group: 'requirement', label: `${key} = ${typeof requirement[key] === 'string' ? requirement[key] : JSON.stringify(requirement[key])}`, style: {} });
    const recordMeta = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_record'));
    if (recordMeta.reference)
        result.push({ group: 'reference', label: (0, model_js_1.str)(recordMeta.reference), style: {} });
    const state = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_state'));
    for (const key of ['entry', 'do', 'exit'])
        if (state[key])
            result.push({ group: 'behavior', label: `${key} / ${(0, model_js_1.str)(state[key])}`, style: {} });
    for (const item of (0, model_js_1.array)(state.internal))
        result.push({ group: 'internal', label: (0, model_js_1.str)(item), style: {} });
    const members = (0, graph_common_js_1.memberRecords)(entry, all);
    for (const member of members) {
        const meta = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_member')), content = (0, model_js_1.object)(member.record.content), block = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_block'));
        if ((0, model_js_1.str)(member.record.role).toLowerCase().includes('port') || (0, graph_glyphs_js_1.metadata)(member.record, 'x_pin') || profile === 'orm.basic@1' && record.role === 'orm.facttype')
            continue;
        const kind = (0, model_js_1.str)(meta.kind, 'attribute');
        const visibility = { public: '+', private: '-', protected: '#', package: '~' }[(0, model_js_1.str)(meta.visibility)] ?? '';
        const part = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_part')), flow = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_flow'));
        const classifier = (0, model_js_1.resolveRecord)(all, part.classifier, member.file) ?? (part.classifier ? all.find(candidate => candidate.file === member.file && (candidate.ref.id === part.classifier || candidate.record.name === part.classifier)) : undefined);
        const suffix = (0, model_js_1.str)(content.type) || (0, model_js_1.str)(content.datatype) || (classifier ? (0, model_js_1.titleOf)(classifier.record) : (0, model_js_1.str)(part.classifier).replace(/^declared-classifier:/, '')), multiplicity = (0, model_js_1.str)(meta.multiplicity, (0, model_js_1.str)(part.multiplicity)), modifiers = (0, model_js_1.array)(meta.modifiers).map(String);
        const value = content.value, unit = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_unit'));
        const text = `${flow.direction ? (0, model_js_1.str)(flow.direction) + ' ' : ''}${visibility}${meta.derived ? '/' : ''}${(0, model_js_1.titleOf)(member.record)}${kind === 'operation' && !(0, model_js_1.titleOf)(member.record).includes('(') ? '()' : ''}${suffix ? ': ' + suffix : ''}${multiplicity ? ' [' + multiplicity + ']' : ''}${value !== undefined ? ' = ' + String(value) : ''}${modifiers.length ? ' {' + modifiers.join(', ') + '}' : ''}${unit.unit ? ' [' + (0, model_js_1.str)(unit.unit) + (unit.quantity ? '; ' + (0, model_js_1.str)(unit.quantity) : '') + ']' : ''}`;
        result.push({ group: (0, model_js_1.str)(block.compartment, kind === 'operation' ? 'operations' : kind === 'literal' ? 'literals' : 'attributes'), label: text, style: { ...(meta.static ? { 'text-decoration': 'underline' } : {}), ...(meta.abstract ? { 'font-style': 'italic' } : {}) }, source: member });
    }
    const vsm = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_vsm'));
    for (const key of ['va', 'nva'])
        if (vsm[key] !== undefined)
            result.push({ group: 'process data', label: `${key.toUpperCase()}: ${String(vsm[key])} ${(0, model_js_1.str)(vsm.unit)}`, style: {} });
    const rawValues = (0, graph_glyphs_js_1.metadata)(record, 'x_values'), values = (0, model_js_1.array)(Array.isArray(rawValues) ? rawValues : (0, model_js_1.object)(rawValues).values);
    if (values.length)
        result.push({ group: 'value constraints', label: '{' + values.map(String).join(', ') + '}', style: {} });
    const derive = (0, graph_glyphs_js_1.metadata)(record, 'x_derive');
    if (derive)
        result.push({ group: 'derivation', label: typeof derive === 'string' ? derive : (0, model_js_1.str)((0, model_js_1.object)(derive).text), style: {} });
    if (profile === 'family.tree@1') {
        const birth = (0, graph_glyphs_js_1.metadata)(record, 'x_birth'), death = (0, graph_glyphs_js_1.metadata)(record, 'x_death');
        if (birth !== undefined || death !== undefined)
            result.push({ group: 'dates', label: `${birth ?? '?'} – ${death ?? ''}`, style: {} });
    }
    const instance = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_instance')), classifier = (0, model_js_1.resolveRecord)(all, instance.classifier, entry.definition.file);
    if (classifier)
        result.push({ group: 'instance', label: ': ' + (0, model_js_1.titleOf)(classifier.record), style: {} });
    for (const [name, value] of Object.entries((0, model_js_1.object)(instance.slots)))
        result.push({ group: 'slots', label: `${name} = ${typeof value === 'string' ? value : JSON.stringify(value)}`, style: {} });
    for (const extension of (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_usecase')).extension_points))
        result.push({ group: 'extension points', label: (0, model_js_1.str)(extension), style: {} });
    if (profile === 'erd.crowfoot@1' && !members.length && entry.appearance?.record.body !== 'title') {
        let data = (0, model_js_1.object)(record.data);
        const source = (0, model_js_1.resolveRecord)(all, data.source, entry.definition.file);
        if (source?.owner === 'data')
            data = source.record;
        if (!Array.isArray(data.rows))
            data = (0, model_js_1.object)(data.snapshot);
        const columns = (0, model_js_1.array)(data.columns).map(model_js_1.object), visibility = { ...(0, model_js_1.object)(record.column_visibility), ...(0, model_js_1.object)(entry.appearance?.record.column_visibility) };
        for (const row of (0, model_js_1.array)(data.rows))
            result.push({ group: 'fields', label: (0, model_js_1.array)(row).filter((_, index) => visibility[(0, model_js_1.str)(columns[index]?.id)] !== 'hidden').map(value => value === null ? '' : String(value)).join('  '), style: {} });
    }
    const boxed = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_boxed'));
    if (boxed.form === 'literal' || boxed.form === 'invocation')
        result.push({ group: 'boxed ' + (0, model_js_1.str)(boxed.form), label: (0, model_js_1.str)(boxed.text), style: {} });
    if (boxed.form === 'context' || boxed.form === 'relation')
        for (const entry of (0, model_js_1.array)(boxed.entries).map(model_js_1.object))
            result.push({ group: 'boxed ' + (0, model_js_1.str)(boxed.form), label: `${(0, model_js_1.str)(entry.name)}: ${(0, model_js_1.str)(entry.text)}`, style: {}, cells: [(0, model_js_1.str)(entry.name), (0, model_js_1.str)(entry.text)] });
    const pack = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_pack')), ownerPackage = (0, model_js_1.resolveRecord)(all, pack.package, entry.definition.file);
    if (pack.visibility || ownerPackage)
        result.push({ group: 'package', label: [pack.visibility, ownerPackage ? 'package ' + (0, model_js_1.titleOf)(ownerPackage.record) : ''].filter(Boolean).join(' · '), style: {} });
    const evidence = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_evidence'));
    if (evidence.result)
        result.push({ group: 'evidence', label: `${(0, model_js_1.str)(evidence.result)} · ${(0, model_js_1.str)(evidence.observed_at)}`, style: {} });
    const choreography = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_contract')).choreography, entry.definition.file);
    if (choreography)
        result.push({ group: 'service contract', label: 'choreography: ' + (0, model_js_1.titleOf)(choreography.record), style: {} });
    const continuation = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_continuation'));
    if (continuation.key)
        result.push({ group: 'continuation', label: `${(0, model_js_1.str)(continuation.side)} ${(0, model_js_1.str)(continuation.key)}${recordMeta.continuation_page ? ' · page ' + String(recordMeta.continuation_page) : ''}`.trim(), style: {} });
    const jump = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_jump')).target, entry.definition.file);
    if (jump)
        result.push({ group: 'control', label: 'jump ' + (0, model_js_1.titleOf)(jump.record), style: {} });
    const c4 = (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_c4tag')).tags);
    if (c4.length)
        result.push({ group: 'tags', label: c4.map(String).join(', '), style: {} });
    const interfaces = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_interfaces'));
    for (const key of ['provides', 'requires']) {
        const names = (0, model_js_1.array)(interfaces[key]).map(ref => (0, model_js_1.resolveRecord)(all, ref, entry.definition.file)).filter((record) => !!record).map(record => (0, model_js_1.titleOf)(record.record));
        if (names.length)
            result.push({ group: 'interfaces', label: key + ': ' + names.join(', '), style: {} });
    }
    const sentry = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_sentry'));
    if (sentry.if_part)
        result.push({ group: 'criterion', label: '[' + (0, model_js_1.str)(sentry.if_part) + ']', style: {} });
    if (state.submachine) {
        const view = (0, model_js_1.resolveRecord)(all, state.submachine, entry.definition.file);
        if (view)
            result.push({ group: 'behavior', label: 'ref ' + (0, model_js_1.titleOf)(view.record), style: {} });
    }
    for (const constraint of (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(record, 'x_timeconstraint')))
        result.push({ group: 'time constraints', label: (0, model_js_1.str)(constraint), style: {} });
    return result.flatMap(row => {
        if (row.cells)
            return [row];
        const words = row.label.split(/\s+/), lines = [];
        for (const word of words) {
            const last = lines.at(-1);
            if (last && last.length + word.length < 65)
                lines[lines.length - 1] = last + ' ' + word;
            else
                lines.push(word);
        }
        return lines.map(label => ({ ...row, label }));
    });
}
function glyphStyle(entry, profile) {
    const render = (0, core_js_1.roleDescriptor)((0, model_js_1.str)(entry.definition.record.role))?.render ?? {}, borderWidth = (0, model_js_1.num)((0, graph_common_js_1.styled)(entry, 'border.width', 0));
    return { fill: (0, model_js_1.str)((0, graph_common_js_1.styled)(entry, 'background.color', (0, graph_common_js_1.styled)(entry, 'symbol.fill', render.fill)), profile === 'wireframe.ui@1' ? '#f8fafc' : '#fff'), stroke: (0, model_js_1.str)((0, graph_common_js_1.styled)(entry, borderWidth > 0 ? 'border.color' : 'symbol.color', render.colour), '#475569'), width: borderWidth > 0 ? borderWidth : (0, model_js_1.num)((0, graph_common_js_1.styled)(entry, 'symbol.width', 1.5), 1.5), look: (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'style.look')), seed: (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.seed'), 42), roughness: (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.roughness'), 1) };
}
function decorateNode(entry, all, profile, preserveBounds = false) {
    if (entry.standalone)
        return entry;
    const record = entry.definition.record, role = (0, model_js_1.str)(record.role), effective = entry.effective;
    if (profile === 'erd.crowfoot@1' && entry.item.primitives.length && ['columns', 'draft', 'notes'].includes((0, model_js_1.str)(entry.appearance?.record.body, (0, model_js_1.str)(effective.body))))
        return entry;
    let bounds = preserveBounds ? entry.item.bounds : dimensions(entry, profile);
    const rows = compartmentRows(entry, all, profile), { fill, stroke, width } = glyphStyle(entry, profile), textScale = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.font_size'), 16) / 16;
    const nativeCard = !role.includes('.') && !!(0, core_js_1.roleDescriptor)(role), title = (0, model_js_1.str)(entry.appearance?.record.title) || (0, model_js_1.titleOf)(record), decorated = rows.length > 0 && !role.startsWith('ladder.');
    if (nativeCard && !profile.startsWith('chen.')) {
        const header = (0, graph_glyphs_js_1.coreCardText)(role, title, bounds.width, textScale);
        if (!preserveBounds && (0, model_js_1.pathValue)(effective, 'size.height') === undefined)
            bounds = { ...bounds, height: Math.max(bounds.height, header.height) };
    }
    if (role === 'orm.facttype')
        bounds = { ...bounds, height: Math.max(bounds.height, 112 + rows.length * 24) };
    if (decorated)
        bounds = { ...bounds, height: Math.max(bounds.height, (58 + rows.length * 23 + new Set(rows.map(r => r.group)).size * 18) * Math.max(1, textScale) + (nativeCard ? (0, graph_glyphs_js_1.coreCardText)(role, title, bounds.width, textScale).height : 0)), width: Math.max(bounds.width, ...rows.map(r => Math.min(520, r.label.length * 7 * textScale + 24))) };
    const typed = role.startsWith('uaf.') || role.startsWith('req.') || role.startsWith('sysml.') || role.startsWith('soaml.') || ['uml.class', 'uml.device', 'uml.executionenv', 'uml.artifact', 'uml.interface', 'uml.enumeration', 'uml.stereotype', 'uml.metaclass', 'c4.component', 'c4.deploymentnode', 'sdl.signalset', 'sdl.procedure', 'flow.offpage', 'idef0.activity'].includes(role);
    const actorType = (0, core_js_1.roleDescriptor)(role)?.render.silhouette === 'actor';
    const typeName = (0, model_js_1.str)((0, core_js_1.roleDescriptor)(role)?.render.text_label, role.slice(role.indexOf('.') + 1));
    const typeLines = typed ? (0, table_js_1.wrapCell)(`«${typeName}»`, Math.max(8, bounds.width - 24), value => value.length * 11 * textScale * .6, 64).lines : [];
    const titleLines = (0, table_js_1.wrapCell)(title, Math.max(8, bounds.width - 24), value => value.length * 15 * textScale * .6, 64).lines;
    const typeHeight = typeLines.length * 13 * textScale;
    const header = nativeCard ? (0, graph_glyphs_js_1.coreCardText)(role, title, bounds.width, textScale) : undefined;
    const headingHeight = header?.height ?? (12 + typeHeight + titleLines.length * 18 * textScale + 10);
    if (!preserveBounds && (0, model_js_1.pathValue)(effective, 'size.height') === undefined && (decorated || typed && !actorType))
        bounds = { ...bounds, height: Math.max(bounds.height, headingHeight + (decorated ? (rows.length * 23 + new Set(rows.map(row => row.group)).size * 18 + 8) * Math.max(1, textScale) : 0)) };
    let primitives = (0, graph_glyphs_js_1.nodeGlyph)(role, record, bounds, { profile, title: decorated || typed && !actorType ? '' : title, textScale, ...glyphStyle(entry, profile) });
    if (typed)
        for (const [i, value] of typeLines.entries())
            primitives.push((0, graph_glyphs_js_1.label)(value, bounds.x + bounds.width / 2, actorType ? bounds.y - 8 - (typeLines.length - 1 - i) * 13 * textScale : bounds.y + 16 * textScale + i * 13 * textScale, 11, stroke, { 'text-anchor': 'middle' }));
    if (decorated || typed && !actorType) {
        const lines = header?.titleLines ?? titleLines, titleX = header ? bounds.x + header.titleOffset + header.titleWidth / 2 : bounds.x + bounds.width / 2;
        const firstY = decorated ? bounds.y + (header ? 20 * textScale : 12 + typeHeight + 15 * textScale) : bounds.y + Math.max(12 + typeHeight + 15 * textScale, typeHeight + (bounds.height - typeHeight) / 2 - (lines.length - 1) * 9 * textScale + 5 * textScale);
        for (const [i, value] of lines.entries())
            primitives.push((0, graph_glyphs_js_1.label)(value, titleX, firstY + i * 18 * textScale, 15, '#1e293b', { 'text-anchor': 'middle', 'font-weight': 600, ...(profile.startsWith('uml.object') ? { 'text-decoration': 'underline' } : {}) }));
    }
    if (decorated) {
        let y = bounds.y + headingHeight, group = '';
        for (const row of rows) {
            if (group !== row.group) {
                primitives.push((0, graph_glyphs_js_1.line)([bounds.x, y], [bounds.x + bounds.width, y], stroke, .8));
                if (profile.startsWith('sysml.') || profile.startsWith('soaml.') || profile.startsWith('uml.') || profile === 'orm.basic@1') {
                    y += 14 * Math.max(1, textScale);
                    primitives.push((0, graph_glyphs_js_1.label)(row.group.toUpperCase(), bounds.x + 8, y, 10, '#64748b'));
                }
                group = row.group;
            }
            y += 22 * Math.max(1, textScale);
            if (row.cells) {
                const split = bounds.x + bounds.width * .35;
                primitives.push((0, graph_glyphs_js_1.box)({ x: bounds.x, y: y - 17, width: bounds.width, height: 22 }, 'none', stroke, .7), (0, graph_glyphs_js_1.line)([split, y - 17], [split, y + 5], stroke, .7), (0, graph_glyphs_js_1.label)(row.cells[0] ?? '', bounds.x + 8, y, 12), (0, graph_glyphs_js_1.label)(row.cells[1] ?? '', split + 8, y, 12));
            }
            else
                primitives.push((0, graph_glyphs_js_1.label)(row.label, bounds.x + 10, y, 13, '#1e293b', row.style));
        }
    }
    const template = (0, graph_glyphs_js_1.metadata)(record, 'x_template');
    if (template) {
        const parameters = typeof template === 'string' ? [template] : (0, model_js_1.array)((0, model_js_1.object)(template).parameters).map(value => typeof value === 'string' ? value : [(0, model_js_1.object)(value).name, (0, model_js_1.object)(value).type ? ': ' + (0, model_js_1.str)((0, model_js_1.object)(value).type) : '', (0, model_js_1.object)(value).default ? ' = ' + String((0, model_js_1.object)(value).default) : ''].join(''));
        const values = parameters.length ? parameters : ['template'], height = values.length * 14 + 10, top = bounds.y - height + 8, width = Math.max(80, Math.min(bounds.width, Math.max(...values.map(value => value.length)) * 6 + 12)), left = bounds.x + bounds.width - width + 10;
        primitives.push((0, graph_glyphs_js_1.box)({ x: left, y: top, width, height }, '#fff', stroke, 1, '4 3'), ...values.map((value, i) => (0, graph_glyphs_js_1.label)(value, left + 6, top + 14 + i * 14, 10)));
    }
    if (role === 'orm.facttype') {
        const roles = (0, graph_common_js_1.memberRecords)(entry, all), cellWidth = Math.min(80, (bounds.width - 24) / Math.max(2, roles.length));
        roles.forEach((member, i) => {
            const flags = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_role'));
            primitives.push((0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(member.record), bounds.x + 12 + (i + .5) * cellWidth, bounds.y + bounds.height - 14, 12, stroke, { 'text-anchor': 'middle' }));
            if (flags.uniqueness)
                primitives.push((0, graph_glyphs_js_1.line)([bounds.x + 12 + i * cellWidth + 3, bounds.y + bounds.height - 34], [bounds.x + 12 + (i + 1) * cellWidth - 3, bounds.y + bounds.height - 34], '#475569', 2));
            if (flags.mandatory)
                primitives.push((0, graph_glyphs_js_1.oval)({ x: bounds.x + 12 + (i + .5) * cellWidth - 3, y: bounds.y + bounds.height - 4, width: 6, height: 6 }, '#334155', '#334155'));
        });
        const objectified = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_objectified'));
        if (objectified.name)
            primitives.push((0, graph_glyphs_js_1.box)({ x: bounds.x - 12, y: bounds.y - 20, width: bounds.width + 24, height: bounds.height + 32 }, 'none', '#475569', 1, '5 3'), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(objectified.name), bounds.x + 3, bounds.y - 6, 12));
    }
    const subdiagram = (0, graph_glyphs_js_1.metadata)(record, 'x_subdiagram');
    if (subdiagram) {
        const raw = (0, model_js_1.object)(subdiagram).view, target = (0, model_js_1.resolveRecord)(all, raw, entry.definition.file) ?? all.find(item => item.file === entry.definition.file && (item.ref.id === raw || item.record.name === raw));
        primitives.push((0, graph_glyphs_js_1.label)('ref ' + (target ? (0, model_js_1.titleOf)(target.record) : (0, model_js_1.str)(raw)), bounds.x + 7, bounds.y + bounds.height - 6, 11, stroke));
    }
    const use = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_use'));
    if (use.arguments)
        primitives.push((0, graph_glyphs_js_1.label)('(' + (0, model_js_1.array)(use.arguments).map(String).join(', ') + ')', bounds.x + 8, bounds.y + bounds.height + 16, 11, stroke));
    if (use.gates)
        (0, model_js_1.array)(use.gates).forEach((gate, i) => primitives.push((0, graph_glyphs_js_1.box)({ x: bounds.x - 4, y: bounds.y + 18 + i * 18, width: 8, height: 8 }, '#fff', stroke), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(gate), bounds.x + 9, bounds.y + 25 + i * 18, 10)));
    const ports = (0, graph_common_js_1.memberRecords)(entry, all).filter(member => /port/i.test((0, model_js_1.str)(member.record.role)) || (0, graph_glyphs_js_1.metadata)(member.record, 'x_port') || (0, graph_glyphs_js_1.metadata)(member.record, 'x_fbd') || (0, graph_glyphs_js_1.metadata)(member.record, 'x_icom') || (0, graph_glyphs_js_1.metadata)(member.record, 'x_pin'));
    ports.forEach((port, i) => {
        const content = (0, model_js_1.object)(port.record.content), p = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(port.record, 'x_port')), fbd = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(port.record, 'x_fbd')), icom = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(port.record, 'x_icom'));
        const side = (0, model_js_1.str)(content.side, (0, model_js_1.str)((0, model_js_1.pathValue)(port.record, 'properties.side'), (0, model_js_1.str)(icom.type, (0, model_js_1.str)(content.direction) === 'output' ? 'east' : 'west')));
        const fraction = (0, model_js_1.num)(content.fraction, (0, model_js_1.num)((0, model_js_1.pathValue)(port.record, 'properties.fraction'), (i + 1) / (ports.length + 1)));
        const x = side === 'north' || side === 'control' || side === 'south' || side === 'mechanism' ? bounds.x + bounds.width * fraction : side === 'east' || side === 'output' ? bounds.x + bounds.width : bounds.x;
        const y = side === 'north' || side === 'control' ? bounds.y : side === 'south' || side === 'mechanism' ? bounds.y + bounds.height : bounds.y + bounds.height * fraction;
        const pb = { x: x - 6, y: y - 6, width: 12, height: 12 };
        primitives.push((0, graph_glyphs_js_1.box)(pb, p.type === 'full' ? '#cbd5e1' : '#fff', stroke), (0, graph_glyphs_js_1.label)(`${p.type ? '«' + (0, model_js_1.str)(p.type) + '» ' : ''}${p.conjugated ? '~' : ''}${(0, model_js_1.titleOf)(port.record)}${p.multiplicity ? ' [' + (0, model_js_1.str)(p.multiplicity) + ']' : ''}${fbd.type ? ': ' + (0, model_js_1.str)(fbd.type) : ''}`, x + 10, y - 6, 10, stroke));
        if (fbd.negated)
            primitives.push((0, graph_glyphs_js_1.oval)({ x: x - 4, y: y - 4, width: 8, height: 8 }, '#fff', stroke));
        const service = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(port.record, 'x_service'));
        if (service.kind)
            primitives.push((0, graph_glyphs_js_1.label)(service.kind === 'request' ? '«Request»' : '«Service»', x + 8, y + 16, 9, stroke));
        if ((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(port.record, 'x_pin')).streaming)
            primitives.push((0, graph_glyphs_js_1.label)('≫', x - 5, y + 4, 10, stroke));
        (0, model_js_1.array)(p.nested).forEach((nested, index) => { primitives.push((0, graph_glyphs_js_1.box)({ x: x + index * 11 - 4, y: y + 12, width: 9, height: 9 }, '#fff', stroke), (0, graph_glyphs_js_1.label)((0, model_js_1.str)((0, model_js_1.object)(nested).name), x + index * 11, y + 31, 8)); });
    });
    if (role === 'ladder.jump') {
        const target = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_jump')).target, entry.definition.file);
        if (target)
            primitives.push((0, graph_glyphs_js_1.label)('→ ' + (0, model_js_1.titleOf)(target.record), bounds.x + 4, bounds.y + bounds.height + 16, 11, stroke));
    }
    const status = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'design.state'), 'draft');
    primitives.push({ kind: 'ellipse', bounds: { x: bounds.x + bounds.width - 10, y: bounds.y - 4, width: 8, height: 8 }, paint: { fill: status === 'accepted' ? '#15803d' : status === 'in-review' ? '#7c3aed' : status === 'in-progress' ? '#2563eb' : '#d97706', stroke: '#fff', 'stroke-width': 1, 'ddn-design-status': status } });
    const imageRef = (0, model_js_1.pathValue)(effective, 'background.image'), asset = imageRef ? (0, model_js_1.resolveRecord)(all, imageRef, entry.definition.file) : undefined;
    if (asset)
        primitives.push({ kind: 'image', assetId: (0, model_js_1.refKey)(asset.ref), bounds: { x: bounds.x + 8, y: bounds.y + 8, width: 24, height: 24 } });
    const look = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'style.look'));
    if (look === 'neo' && primitives[0]) {
        const shadow = (0, graph_glyphs_js_1.shadowPrimitive)(primitives[0]);
        if (shadow)
            primitives.unshift(shadow);
    }
    return (0, graph_common_js_1.changed)(entry, bounds, primitives, `${profile}; ${role}; ${status}`);
}
function chen(entries, all, profile, diagnostics, unavailable, view, frame, effective) {
    const direct = (owner) => (0, graph_common_js_1.memberRecords)(owner, all).filter(member => { const parent = (0, model_js_1.resolveRecord)(all, member.record.parent ?? (0, model_js_1.pathValue)(member.record, 'content.parent'), member.file); return !parent || (0, model_js_1.refKey)(parent.ref) === (0, model_js_1.refKey)(owner.definition.ref); });
    const span = (owner, level = 0, trail = new Set()) => {
        const key = (0, model_js_1.refKey)(owner.definition.ref);
        if (level > 8 || trail.has(key))
            return 155;
        const next = new Set(trail);
        next.add(key);
        const children = direct(owner);
        return Math.max(155, children.reduce((sum, member) => sum + span({ ...owner, definition: member }, level + 1, next), 0));
    };
    const originals = entries.filter(e => e.definition.record.category !== 'relation'), attributeWidth = Math.max(240, ...originals.map(node => span(node))), edges = entries.filter(e => e.definition.record.category === 'relation'), nodes = layoutGraph(originals, edges, all, profile, frame, view, { ...effective, layout: { ...(0, model_js_1.object)(effective?.layout ?? view.record.layout), gap: attributeWidth + 80, row_gap: 360 } });
    const result = nodes.map(node => decorateNode(node, all, profile, true));
    for (const node of [...result]) {
        const b = node.item.bounds, weak = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_chen')).weak;
        if (weak && !node.standalone)
            result[result.indexOf(node)] = (0, graph_common_js_1.changed)(node, b, [...node.item.primitives, (0, graph_glyphs_js_1.box)({ x: b.x + 5, y: b.y + 5, width: b.width - 10, height: b.height - 10 }, 'none')]);
        const visit = (parent, parentBounds, members, level, trail) => {
            const spans = members.map(member => span({ ...node, definition: member }, level, trail)), total = spans.reduce((sum, value) => sum + value, 0);
            let cursor = parentBounds.x + parentBounds.width / 2 - total / 2;
            members.forEach((member, i) => {
                const key = (0, model_js_1.refKey)(member.ref);
                if (trail.has(key) || level > 8) {
                    diagnostics.push({ code: 'chen-attribute-depth', severity: 'warning', message: 'Attribute expansion is cyclic or exceeds eight nested levels.', target: member.ref });
                    unavailable.push('chen-attributes:' + key);
                    return;
                }
                const next = new Set(trail);
                next.add(key);
                const meta = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(member.record, 'x_chen')), bounds = { x: cursor + (spans[i] - 135) / 2, y: parentBounds.y + parentBounds.height + 70, width: 135, height: 48 };
                cursor += spans[i];
                const ps = [(0, graph_glyphs_js_1.line)((0, graph_common_js_1.boundaryPoint)(parentBounds, (0, graph_common_js_1.center)(bounds)), (0, graph_common_js_1.boundaryPoint)(bounds, (0, graph_common_js_1.center)(parentBounds))), (0, graph_glyphs_js_1.oval)(bounds, '#fff', '#64748b', 1.3, meta.derived ? '5 3' : undefined)];
                if (meta.multivalued)
                    ps.push((0, graph_glyphs_js_1.oval)({ x: bounds.x + 4, y: bounds.y + 4, width: bounds.width - 8, height: bounds.height - 8 }, 'none', '#64748b'));
                ps.push((0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(member.record), bounds.x + bounds.width / 2, bounds.y + 29, 13, '#1e293b', { 'text-anchor': 'middle', ...(meta.key || (0, model_js_1.pathValue)(member.record, 'content.key') === 'primary' ? { 'text-decoration': 'underline' } : {}) }));
                if (meta.partial_key)
                    ps.push((0, graph_glyphs_js_1.line)([bounds.x + 18, bounds.y + 34], [bounds.x + bounds.width - 18, bounds.y + 34], '#475569', 1, '4 3'));
                result.push((0, graph_common_js_1.mark)(node, member, 'attribute:' + key, bounds, ps, `Generated Chen attribute of ${(0, model_js_1.titleOf)(parent.record)}; source field identity`));
                const childEntry = { ...node, definition: member };
                visit(member, bounds, direct(childEntry), level + 1, next);
            });
        };
        visit(node.definition, b, direct(node), 0, new Set([(0, model_js_1.refKey)(node.definition.ref)]));
    }
    for (const edge of edges) {
        const participants = [(0, graph_common_js_1.endEntry)(edge, 0, nodes, all), (0, graph_common_js_1.endEntry)(edge, 1, nodes, all)].filter((v) => !!v);
        for (const end of (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_nary')).ends)) {
            const target = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).element, edge.definition.file);
            const node = target && nodes.find(n => (0, model_js_1.refKey)(n.definition.ref) === (0, model_js_1.refKey)(target.ref));
            if (node && !participants.includes(node))
                participants.push(node);
        }
        if (participants.length < 2)
            continue;
        const centers = participants.map(n => (0, graph_common_js_1.center)(n.item.bounds)), x = centers.reduce((sum, p) => sum + p[0], 0) / centers.length, y = centers.reduce((sum, p) => sum + p[1], 0) / centers.length;
        const b = { x: x - 58, y: y - 32, width: 116, height: 64 }, ps = [];
        const meta = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_chen'));
        participants.forEach((node, i) => {
            const p = (0, graph_common_js_1.center)(node.item.bounds);
            ps.push((0, graph_glyphs_js_1.line)((0, graph_common_js_1.boundaryPoint)(b, p), (0, graph_common_js_1.boundaryPoint)(node.item.bounds, [x, y])));
            const cardinality = (0, model_js_1.object)(meta[i === 0 ? 'from' : 'to']);
            const extra = (0, model_js_1.object)((0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_nary')).ends)[i - 2]);
            const annotation = i > 1 ? [extra.role, extra.multiplicity].filter(Boolean).join(' ') : cardinality.min !== undefined || cardinality.max !== undefined ? `(${cardinality.min ?? '?'},${cardinality.max ?? '?'})` : '';
            if (annotation)
                ps.push((0, graph_glyphs_js_1.label)(annotation, (x + p[0]) / 2, (y + p[1]) / 2 - 5, 11));
        });
        ps.push((0, graph_glyphs_js_1.polygon)([[x, b.y], [b.x + b.width, y], [x, b.y + b.height], [b.x, y]]));
        if (meta.identifying)
            ps.push((0, graph_glyphs_js_1.polygon)([[x, b.y + 5], [b.x + b.width - 8, y], [x, b.y + b.height - 5], [b.x + 8, y]], 'none'));
        const caption = (0, relation_presentation_js_1.relationCaption)(edge, (0, graph_common_js_1.edgeLabel)(edge, all), effective);
        if (caption)
            ps.push((0, graph_glyphs_js_1.label)(caption, x, y + 4, 11, '#1e293b', { 'text-anchor': 'middle' }));
        const edgeBounds = (0, graph_common_js_1.finiteBounds)([Math.min(b.x, ...centers.map(p => p[0])), Math.min(b.y, ...centers.map(p => p[1]))], [Math.max(b.x + b.width, ...centers.map(p => p[0])), Math.max(b.y + b.height, ...centers.map(p => p[1]))], 12);
        result.push((0, graph_common_js_1.changed)(edge, edgeBounds, ps, `Chen relationship; ${participants.length} participants`));
    }
    const shift = Math.max(0, frame.x + 32 - Math.min(...result.map(entry => entry.item.bounds.x)));
    return result.map(entry => ({ ...entry, item: { ...entry.item, bounds: { ...entry.item.bounds, x: entry.item.bounds.x + shift }, transform: [entry.item.transform[0], entry.item.transform[1], entry.item.transform[2], entry.item.transform[3], entry.item.transform[4] + shift, entry.item.transform[5]], hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: { ...hit.bounds, x: hit.bounds.x + shift } })) } }));
}
function sequence(entries, all, profile, frame, diagnostics, unavailable, viewProperties) {
    const participants = entries.filter(e => e.definition.record.category !== 'relation'), edges = entries.filter(e => e.definition.record.category === 'relation'), result = [];
    const messageY = new Map();
    edges.forEach((edge, i) => messageY.set((0, model_js_1.refKey)(edge.definition.ref), frame.y + 170 + i * 65));
    const positions = new Map();
    const yEnd = frame.y + 210 + Math.max(1, edges.length) * 65;
    participants.forEach((entry, i) => {
        if (entry.definition.record.role === 'msc.hmscref') {
            const b = { x: frame.x + 45 + participants.filter(p => p.definition.record.role === 'msc.hmscref').indexOf(entry) * 380, y: yEnd + 30, width: 350, height: 95 }, sub = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_subdiagram')), params = (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_hmscref')).params);
            result.push((0, graph_common_js_1.changed)(entry, b, [(0, graph_glyphs_js_1.box)(b, '#fff', '#475569'), (0, graph_glyphs_js_1.path)(`M${b.x},${b.y + 25}H${b.x + 40}L${b.x + 50},${b.y + 15}V${b.y}`, 'none'), (0, graph_glyphs_js_1.label)('ref', b.x + 8, b.y + 17, 11), (0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(entry.definition.record), b.x + 15, b.y + 48, 14), (0, graph_glyphs_js_1.label)(params.length ? '(' + params.map(String).join(', ') + ')' : '', b.x + 15, b.y + 73, 12)], 'HMSC reference with declared actual parameters'));
            return;
        }
        const b = { x: frame.x + 45 + participants.filter(p => p.definition.record.role !== 'msc.hmscref').indexOf(entry) * 245, y: frame.y + 60, width: 180, height: 60 }, x = b.x + b.width / 2;
        positions.set((0, model_js_1.refKey)(entry.definition.ref), b);
        const creation = edges.find(edge => (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_message')).sort === 'create' && (0, graph_common_js_1.endEntry)(edge, 1, participants, all) === entry);
        if (creation)
            b.y = (messageY.get((0, model_js_1.refKey)(creation.definition.ref)) ?? b.y) - b.height / 2;
        const deletion = edges.find(edge => (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_message')).sort === 'delete' && (0, graph_common_js_1.endEntry)(edge, 1, participants, all) === entry), end = deletion ? messageY.get((0, model_js_1.refKey)(deletion.definition.ref)) ?? yEnd : yEnd;
        const ps = (0, graph_glyphs_js_1.nodeGlyph)((0, model_js_1.str)(entry.definition.record.role), entry.definition.record, b, { title: (0, model_js_1.titleOf)(entry.definition.record), profile, ...glyphStyle(entry, profile) });
        for (const [index, constraint] of (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_timeconstraint')).entries())
            ps.push((0, graph_glyphs_js_1.label)((0, model_js_1.str)(constraint), b.x + 4, b.y + b.height + 15 + index * 14, 10, '#475569'));
        ps.push((0, graph_glyphs_js_1.line)([x, b.y + b.height], [x, end], '#64748b', 1, '6 5'));
        if (deletion)
            ps.push((0, graph_glyphs_js_1.line)([x - 9, end - 9], [x + 9, end + 9], '#334155', 2), (0, graph_glyphs_js_1.line)([x + 9, end - 9], [x - 9, end + 9], '#334155', 2));
        const activations = (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_activation'));
        if (activations.length)
            activations.forEach((value, index) => {
                const activation = (0, model_js_1.object)(value), from = (0, model_js_1.resolveRecord)(all, activation.from, entry.definition.file), to = (0, model_js_1.resolveRecord)(all, activation.to, entry.definition.file);
                const start = from && messageY.get((0, model_js_1.refKey)(from.ref)), stop = to && messageY.get((0, model_js_1.refKey)(to.ref));
                if (start !== undefined && stop !== undefined)
                    ps.push((0, graph_glyphs_js_1.box)({ x: x - 6 + index * 3, y: Math.min(start, stop), width: 12, height: Math.max(15, Math.abs(stop - start)) }, '#e2e8f0', '#475569'));
            });
        else {
            const calls = edges.filter(edge => (0, graph_common_js_1.endEntry)(edge, 1, participants, all) === entry && !['reply', 'delete', 'create', 'lost'].includes((0, model_js_1.str)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_message')).sort)));
            for (const edge of calls) {
                const start = messageY.get((0, model_js_1.refKey)(edge.definition.ref)), caller = (0, graph_common_js_1.endEntry)(edge, 0, participants, all);
                const reply = edges.find(candidate => messageY.get((0, model_js_1.refKey)(candidate.definition.ref)) > start && (0, graph_common_js_1.endEntry)(candidate, 0, participants, all) === entry && (0, graph_common_js_1.endEntry)(candidate, 1, participants, all) === caller && ((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(candidate.definition.record, 'x_message')).sort === 'reply' || (0, graph_glyphs_js_1.metadata)(candidate.definition.record, 'x_return') === true));
                const stop = reply ? messageY.get((0, model_js_1.refKey)(reply.definition.ref)) : Math.max(start + 32, ...edges.filter(candidate => (0, graph_common_js_1.endEntry)(candidate, 0, participants, all) === entry).map(candidate => messageY.get((0, model_js_1.refKey)(candidate.definition.ref))));
                ps.push((0, graph_glyphs_js_1.box)({ x: x - 6, y: start, width: 12, height: Math.max(24, stop - start) }, '#e2e8f0', '#475569'));
            }
        }
        for (const value of (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_invariant'))) {
            const invariant = (0, model_js_1.object)(value), after = (0, model_js_1.resolveRecord)(all, invariant.after, entry.definition.file), yy = (after && messageY.get((0, model_js_1.refKey)(after.ref)) || b.y + b.height) + 20;
            if (invariant.role)
                ps.push((0, graph_glyphs_js_1.label)((0, model_js_1.str)(invariant.role), x - 70, yy - 3, 9, '#64748b'));
            ps.push((0, graph_glyphs_js_1.polygon)([[x - 70, yy], [x + 70, yy], [x + 80, yy + 12], [x + 70, yy + 24], [x - 70, yy + 24], [x - 80, yy + 12]], '#fff'), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(invariant.label), x, yy + 16, 11, '#334155', { 'text-anchor': 'middle' }));
        }
        result.push((0, graph_common_js_1.changed)(entry, { ...b, height: end - b.y + 10 }, ps, `Participant lifeline; ${profile}`));
    });
    for (const edge of edges) {
        const a = (0, graph_common_js_1.endEntry)(edge, 0, participants, all), b = (0, graph_common_js_1.endEntry)(edge, 1, participants, all);
        if (!a || !b)
            continue;
        const ab = positions.get((0, model_js_1.refKey)(a.definition.ref)), bb = positions.get((0, model_js_1.refKey)(b.definition.ref)), y = messageY.get((0, model_js_1.refKey)(edge.definition.ref));
        if (!ab || !bb) {
            diagnostics.push({ code: 'sequence-participant-required', severity: 'error', message: 'Messages require participant lifelines, not reference boxes.', target: edge.definition.ref });
            unavailable.push('sequence-message:' + (0, model_js_1.refKey)(edge.definition.ref));
            continue;
        }
        const message = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_message')), sort = (0, model_js_1.str)(message.sort, (0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_return') ? 'reply' : 'synch');
        let x1 = ab.x + ab.width / 2, x2 = bb.x + bb.width / 2;
        if (sort === 'create')
            x2 = bb.x;
        if (sort === 'lost')
            x2 = x1 + (x2 >= x1 ? 110 : -110);
        if (sort === 'found')
            x1 = x2 + (x1 > x2 ? 110 : -110);
        const ps = [], self = a === b && !['lost', 'found'].includes(sort);
        if (self)
            ps.push((0, graph_glyphs_js_1.path)(`M${x1},${y}H${x1 + 70}V${y + 25}H${x1}`, 'none', '#475569', 1.5, sort === 'reply' ? '6 4' : undefined), ...(0, graph_glyphs_js_1.arrowMarker)([x1, y + 25], [x1 + 70, y + 25], sort === 'synch' ? 'filled' : 'open'));
        else
            ps.push((0, graph_glyphs_js_1.line)([x1, y], [x2, y], '#475569', 1.5, sort === 'reply' ? '6 4' : undefined), ...(0, graph_glyphs_js_1.arrowMarker)([x2, y], [x1, y], sort === 'synch' ? 'filled' : 'open'));
        if (sort === 'lost' || sort === 'found') {
            const x = sort === 'lost' ? x2 : x1;
            ps.push((0, graph_glyphs_js_1.oval)({ x: x - 5, y: y - 5, width: 10, height: 10 }, '#334155', '#334155'));
        }
        const caption = (0, relation_presentation_js_1.relationCaption)(edge, (message.seq ? '' : String(edges.indexOf(edge) + 1) + ': ') + (0, graph_common_js_1.edgeLabel)(edge, all), viewProperties);
        if (caption)
            ps.push((0, graph_glyphs_js_1.label)(caption, (x1 + x2) / 2 + (self ? 35 : 0), y - 8, 12, '#334155', { 'text-anchor': 'middle' }));
        const bounds = (0, graph_common_js_1.finiteBounds)([x1, y], [x2 + (self ? 70 : 0), y + 25], 12);
        result.push((0, graph_common_js_1.changed)(edge, bounds, ps, `Message ${sort}; declaration order ${edges.indexOf(edge) + 1}`));
        const fragment = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_fragment'));
        const drawFragment = (data, level) => {
            if (level > 12) {
                diagnostics.push({ code: 'sequence-fragment-depth', severity: 'warning', message: 'Fragment projection exceeds twelve nested levels.', target: edge.definition.ref });
                unavailable.push('sequence-fragment:' + (0, model_js_1.refKey)(edge.definition.ref));
                return;
            }
            const ys = (0, model_js_1.array)(data.operands).flatMap(value => (0, model_js_1.array)((0, model_js_1.object)(value).messages).map(reference => (0, model_js_1.resolveRecord)(all, reference, edge.definition.file)).filter((r) => !!r).map(r => messageY.get((0, model_js_1.refKey)(r.ref))).filter((v) => v !== undefined));
            if (!ys.length)
                return;
            const fb = { x: frame.x + 18 + level * 8, y: Math.min(...ys) - 27, width: Math.max(260, participants.length * 245 - 8 - level * 16), height: Math.max(...ys) - Math.min(...ys) + 65 }, fps = [(0, graph_glyphs_js_1.box)(fb, 'none', '#64748b'), (0, graph_glyphs_js_1.polygon)([[fb.x, fb.y], [fb.x + 70, fb.y], [fb.x + 70, fb.y + 14], [fb.x + 60, fb.y + 24], [fb.x, fb.y + 24]], '#f8fafc', '#64748b'), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(data.operator), fb.x + 6, fb.y + 16, 11)];
            (0, model_js_1.array)(data.operands).forEach((value, index) => {
                const operand = (0, model_js_1.object)(value), referenced = (0, model_js_1.array)(operand.messages).map(ref => (0, model_js_1.resolveRecord)(all, ref, edge.definition.file)).filter((r) => !!r), points = referenced.map(r => messageY.get((0, model_js_1.refKey)(r.ref))).filter((v) => v !== undefined), yy = points.length ? Math.min(...points) - 24 : fb.y;
                if (index)
                    fps.push((0, graph_glyphs_js_1.line)([fb.x, yy], [fb.x + fb.width, yy], '#64748b', 1, '5 4'));
                if (operand.guard)
                    fps.push((0, graph_glyphs_js_1.label)('[' + (0, model_js_1.str)(operand.guard) + ']', fb.x + 80, yy + 16, 11));
                for (const nested of (0, model_js_1.array)(operand.fragments))
                    drawFragment((0, model_js_1.object)(nested), level + 1);
            });
            result.push((0, graph_common_js_1.mark)(edge, edge.definition, `fragment:${level}:${result.length}`, fb, fps, `Combined fragment ${(0, model_js_1.str)(data.operator)}`));
        };
        if (fragment.operator)
            drawFragment(fragment, 0);
    }
    return result;
}
function timing(entries, all, profile, frame, diagnostics, unavailable, viewProperties) {
    const nodes = entries.filter(e => e.definition.record.category !== 'relation'), edges = entries.filter(e => e.definition.record.category === 'relation');
    const parsed = nodes.map(node => ({ node, states: (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_states')).map((value) => Array.isArray(value) ? { at: value[0], state: value[1] } : (0, model_js_1.object)(value)).map(value => ({ at: (0, model_js_1.num)(value.at, (0, model_js_1.num)(value.time, NaN)), state: (0, model_js_1.str)(value.state, (0, model_js_1.str)(value.value)), duration: (0, model_js_1.str)(value.duration), slew: (0, model_js_1.str)(value.slew) })) }));
    const times = parsed.flatMap(row => [...row.states.map(state => state.at), ...row.states.flatMap(state => (state.duration.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number)), ...(0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(row.node.definition.record, 'x_timeconstraint')).flatMap(value => (String(value).match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number))]).filter(Number.isFinite), min = Math.min(0, ...times), max = Math.max(1, ...times), plotX = frame.x + 170, plotW = Math.max(600, frame.width - 210), result = [];
    const sx = (time) => plotX + (time - min) / (max - min) * plotW;
    parsed.forEach(({ node, states }, row) => {
        const b = { x: frame.x + 25, y: frame.y + 65 + row * 165, width: plotW + 150, height: 145 }, labels = [...new Set(states.map(v => v.state))];
        if (!states.length || states.some((state, i) => !Number.isFinite(state.at) || !state.state || i > 0 && state.at <= states[i - 1].at)) {
            diagnostics.push({ code: 'timing-states-invalid', severity: 'error', target: node.definition.ref, message: 'Timing states require named values at finite, strictly increasing declared times.' });
            unavailable.push('timing:' + (0, model_js_1.refKey)(node.definition.ref));
            result.push((0, graph_common_js_1.changed)(node, b, [(0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(node.definition.record), b.x, b.y + 20), (0, graph_glyphs_js_1.label)('Incomplete timing states', plotX, b.y + 60, 13, '#9f1239')]));
            return;
        }
        const sy = (state) => b.y + 32 + labels.indexOf(state) * 70 / Math.max(1, labels.length - 1), ps = [(0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(node.definition.record), b.x, b.y + 16, 14), (0, graph_glyphs_js_1.line)([plotX, b.y + 118], [plotX + plotW, b.y + 118], '#94a3b8')];
        labels.forEach(state => ps.push((0, graph_glyphs_js_1.label)(state, plotX - 10, sy(state) + 4, 11, '#64748b', { 'text-anchor': 'end' })));
        let d = `M${sx(states[0].at)},${sy(states[0].state)}`;
        states.forEach((state, i) => {
            if (i)
                d += `H${sx(state.at)}V${sy(state.state)}`;
            if (state.duration)
                ps.push((0, graph_glyphs_js_1.label)(state.duration, sx(state.at) + 10, sy(state.state) - 23, 11, '#475569'));
            if (state.slew)
                ps.push((0, graph_glyphs_js_1.label)(state.slew, sx(state.at) + 10, sy(state.state) + 20, 10, '#475569'));
            const until = states[i + 1]?.at ?? max;
            if (until > state.at)
                ps.push((0, graph_glyphs_js_1.label)(state.state, (sx(state.at) + sx(until)) / 2, sy(state.state) - 8, 11, '#334155', { 'text-anchor': 'middle' }));
            ps.push((0, graph_glyphs_js_1.line)([sx(state.at), b.y + 115], [sx(state.at), b.y + 122], '#64748b'), (0, graph_glyphs_js_1.label)(String(state.at), sx(state.at), b.y + 138, 10, '#475569', { 'text-anchor': 'middle' }));
        });
        d += `H${plotX + plotW}`;
        ps.push((0, graph_glyphs_js_1.path)(d, 'none', glyphStyle(node, profile).stroke, 2));
        const constraint = (0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_timeconstraint');
        if (constraint)
            ps.push((0, graph_glyphs_js_1.label)(typeof constraint === 'string' ? constraint : Array.isArray(constraint) ? constraint.map(String).join('; ') : (0, model_js_1.str)((0, model_js_1.object)(constraint).text, (0, model_js_1.str)((0, model_js_1.object)(constraint).label)), plotX, b.y + 155, 10, '#475569'));
        for (const value of (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_duration'))) {
            const span = (0, model_js_1.object)(value), from = (0, model_js_1.num)(span.from), to = (0, model_js_1.num)(span.to);
            const yy = b.y + 12;
            ps.push((0, graph_glyphs_js_1.line)([sx(from), yy], [sx(to), yy]), (0, graph_glyphs_js_1.line)([sx(from), yy - 4], [sx(from), yy + 4]), (0, graph_glyphs_js_1.line)([sx(to), yy - 4], [sx(to), yy + 4]), (0, graph_glyphs_js_1.label)((0, model_js_1.str)(span.label, `{${from}..${to}}`), (sx(from) + sx(to)) / 2, yy - 7, 11, '#475569', { 'text-anchor': 'middle' }));
        }
        result.push((0, graph_common_js_1.changed)(node, b, ps, `Timing band; ${states.length} state changes; ${profile}`));
    });
    for (const edge of edges) {
        const a = (0, graph_common_js_1.endEntry)(edge, 0, nodes, all), b = (0, graph_common_js_1.endEntry)(edge, 1, nodes, all), at = (0, model_js_1.num)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(edge.definition.record, 'x_message')).at, NaN);
        if (!a || !b || !Number.isFinite(at))
            continue;
        const y1 = frame.y + 115 + nodes.indexOf(a) * 165, y2 = frame.y + 115 + nodes.indexOf(b) * 165, x = sx(at);
        result.push((0, graph_common_js_1.changed)(edge, (0, graph_common_js_1.finiteBounds)([x, y1], [x, y2], 15), [(0, graph_glyphs_js_1.line)([x, y1], [x, y2]), ...(0, graph_glyphs_js_1.arrowMarker)([x, y2], [x, y1]), ...((0, relation_presentation_js_1.relationCaption)(edge, (0, graph_common_js_1.edgeLabel)(edge, all), viewProperties) ? [(0, graph_glyphs_js_1.label)((0, relation_presentation_js_1.relationCaption)(edge, (0, graph_common_js_1.edgeLabel)(edge, all), viewProperties), x + 8, (y1 + y2) / 2, 11)] : [])], 'Timestamp-anchored lifeline message'));
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
        const node = (0, graph_common_js_1.endEntry)(edge, 0, nodes, all), parent = (0, graph_common_js_1.endEntry)(edge, 1, nodes, all);
        if (!node || !parent)
            continue;
        const key = (0, model_js_1.refKey)(parent.definition.ref), list = incoming.get(key) ?? [];
        list.push({ node, edge });
        incoming.set(key, list);
    }
    let occurrence = 0, limited = false;
    const expand = (node, edge, level, ancestors) => {
        const key = (0, model_js_1.refKey)(node.definition.ref);
        if (ancestors.has(key) || level > 4 || occurrence >= 250) {
            limited = true;
            return;
        }
        const id = occurrence++, next = new Set([...ancestors, key]);
        const children = (incoming.get(key) ?? []).flatMap(pair => { const branch = expand(pair.node, pair.edge, level + 1, next); return branch ? [branch] : []; });
        return { node, edge, children, level, rows: 1 + children.reduce((sum, child) => sum + child.rows, 0), row: 0, y: 0, width: 0, occurrence: id };
    };
    const categories = (incoming.get((0, model_js_1.refKey)(effect.definition.ref)) ?? []).flatMap(pair => { const branch = expand(pair.node, pair.edge, 0, new Set([(0, model_js_1.refKey)(effect.definition.ref)])); return branch ? [branch] : []; });
    if (limited) {
        unavailable.push('fishbone:bounded-traversal');
        diagnostics.push({ code: 'fishbone-bounded-traversal', severity: 'error', message: 'Fishbone requires acyclic cause branches within four cause levels and 250 occurrences.' });
    }
    const fontScale = (entry) => Math.max(.25, (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.font_size'), 16) / 16);
    const textWidth = (branch) => (0, graph_common_js_1.graphLabelBounds)((0, model_js_1.titleOf)(branch.node.definition.record), 0, 0, (branch.level ? 14 : 17) * fontScale(branch.node)).width;
    const maxRows = Math.max(1, ...categories.map(category => category.rows - 1)), rowHeight = Math.max(44, ...nodes.map(node => 30 * fontScale(node))), halfHeight = Math.max(260, (maxRows + 1) * rowHeight);
    const top = frame.y + Math.max(100, ...categories.map(category => 17 * fontScale(category.node) + 76)), spineY = top + halfHeight, slope = .5, indent = 28;
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
    const effectStyle = glyphStyle(effect, profile), result = [(0, graph_common_js_1.changed)(effect, effectBounds, (0, graph_glyphs_js_1.nodeGlyph)('quality.effect', effect.definition.record, effectBounds, { title: (0, model_js_1.titleOf)(effect.definition.record), profile, ...effectStyle }))];
    const spineStart = [frame.x + 40, spineY], spineEnd = [effectBounds.x, spineY];
    const spineStyle = categories[0]?.edge ?? effect, relationColour = (entry) => (0, model_js_1.str)((0, graph_common_js_1.styled)(entry, 'stroke.color', (0, core_js_1.roleDescriptor)('quality.cause', 'relation')?.render.colour), '#2563eb');
    const weight = (entry, fallback) => (0, model_js_1.num)((0, graph_common_js_1.styled)(entry, 'stroke.weight', (0, graph_common_js_1.styled)(entry, 'stroke.width', fallback)), fallback);
    const spinePaint = relationColour(spineStyle);
    const spine = (0, graph_common_js_1.mark)(effect, effect.definition, 'spine', (0, graph_common_js_1.finiteBounds)(spineStart, spineEnd, 8), [(0, graph_glyphs_js_1.line)(spineStart, spineEnd, spinePaint, weight(spineStyle, 2.4)), ...(0, graph_glyphs_js_1.arrowMarker)(spineEnd, spineStart, 'filled', spinePaint)], 'Fishbone main spine to the selected effect');
    result.push({ ...spine, item: { ...spine.item, layer: 'relations' } });
    const addLabel = (branch, x, y, category = false) => {
        const size = category ? 17 : 14, align = category ? 'middle' : 'start', bounds = (0, graph_common_js_1.graphLabelBounds)((0, model_js_1.titleOf)(branch.node.definition.record), x, y, size * fontScale(branch.node), align);
        result.push((0, graph_common_js_1.mark)(branch.node, branch.node.definition, `cause:${branch.occurrence}`, bounds, [(0, graph_glyphs_js_1.label)((0, model_js_1.titleOf)(branch.node.definition.record), x, y, size, '#1e293b', { 'text-anchor': align, ...(category ? { 'font-weight': 700 } : {}) })], `Fishbone level ${branch.level}; source identity retained`));
    };
    const addBone = (branch, points) => {
        const xs = points.map(point => point[0]), ys = points.map(point => point[1]), bounds = { x: Math.min(...xs) - 4, y: Math.min(...ys) - 4, width: Math.max(...xs) - Math.min(...xs) + 8, height: Math.max(...ys) - Math.min(...ys) + 8 };
        const dash = (0, graph_common_js_1.styled)(branch.edge, 'stroke.dash', 'solid'), dashPattern = Array.isArray(dash) ? dash.join(' ') : dash === 'dashed' ? '6 4' : dash === 'dotted' ? '2 3' : typeof dash === 'string' && dash !== 'solid' ? dash : undefined;
        const primitives = [(0, graph_glyphs_js_1.path)('M' + points.map(point => point.join(',')).join('L'), 'none', relationColour(branch.edge), weight(branch.edge, branch.level === 0 ? 1.8 : 1.2), dashPattern)];
        const caption = (0, relation_presentation_js_1.relationCaption)(branch.edge, (0, graph_common_js_1.edgeLabel)(branch.edge, all), viewProperties);
        if (caption) {
            const first = points[0], last = points.at(-1), x = (first[0] + last[0]) / 2, y = (first[1] + last[1]) / 2 + 17;
            const textBounds = (0, graph_common_js_1.graphLabelBounds)(caption, x, y, 11, 'middle');
            primitives.push((0, graph_glyphs_js_1.box)(textBounds, (0, model_js_1.str)((0, model_js_1.pathValue)(viewProperties, 'background.color'), '#fff'), 'none', 0), (0, graph_glyphs_js_1.label)(caption, x, y, 11, '#334155', { 'text-anchor': 'middle' }));
            const right = Math.max(bounds.x + bounds.width, textBounds.x + textBounds.width), bottom = Math.max(bounds.y + bounds.height, textBounds.y + textBounds.height);
            bounds.x = Math.min(bounds.x, textBounds.x);
            bounds.y = Math.min(bounds.y, textBounds.y);
            bounds.width = right - bounds.x;
            bounds.height = bottom - bounds.y;
        }
        result.push((0, graph_common_js_1.mark)(branch.edge, branch.edge.definition, `cause-edge:${branch.occurrence}`, bounds, primitives, 'Fishbone cause relationship; original relation identity'));
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
    return result.map(entry => ({ ...entry, item: { ...entry.item, primitives: entry.item.primitives.map((primitive, i) => primitive.kind === 'path' && (0, model_js_1.str)((0, model_js_1.pathValue)(entry.effective, 'style.look')) === 'handdrawn' ? (0, graph_glyphs_js_1.sketchPrimitive)(primitive, (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.seed'), 42) + i, (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'style.roughness'), 1)) : primitive) } }));
}
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
    let positioned = nodes.map(node => decorateNode(node, all, profile));
    const declared = (0, model_js_1.object)(effective?.layout ?? view.record.layout), hierarchical = /^(org|wbs|family|fault|event)\./.test(profile);
    let algorithm = (0, model_js_1.str)(declared.algorithm, hierarchical ? 'tree' : 'layered');
    if (algorithm === 'auto')
        algorithm = hierarchical ? 'tree' : 'layered';
    const direction = (0, model_js_1.str)(declared.direction, hierarchical ? 'down' : 'right');
    const regions = (0, model_js_1.array)(view.record.regions).map(model_js_1.object), key = (entry) => (0, model_js_1.refKey)(entry.definition.ref);
    const regionMembers = (region) => new Set((0, model_js_1.array)(region.members).map(ref => (0, model_js_1.resolveRecord)(all, ref, view.file)).filter((r) => !!r).map(r => (0, model_js_1.refKey)(r.ref)));
    const groups = new Map();
    for (const node of positioned) {
        if (node.definition.record.role === 'uml.subject' && positioned.some(child => (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(child.definition.record, 'x_usecase')).subjects).some(ref => (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, ref, child.definition.file)?.ref ?? { file: '', id: '' }) === key(node))))
            continue;
        const subject = (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_usecase')).subjects)[0], owner = (0, model_js_1.resolveRecord)(all, subject, node.definition.file);
        const matching = regions.filter(region => regionMembers(region).has(key(node)) || (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, region.scope, view.file)?.ref ?? { file: '', id: '' }) === key(node)).sort((a, b) => (0, model_js_1.array)(a.members).length - (0, model_js_1.array)(b.members).length);
        const group = owner ? 'subject:' + (0, model_js_1.refKey)(owner.ref) : (0, model_js_1.str)(matching[0]?.id, (0, model_js_1.str)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_partition')).lane, 'outside'));
        const bucket = groups.get(group) ?? [];
        bucket.push(node);
        groups.set(group, bucket);
    }
    const links = edges.flatMap(edge => { const a = (0, graph_common_js_1.endEntry)(edge, 0, positioned, all), b = (0, graph_common_js_1.endEntry)(edge, 1, positioned, all); return a && b ? [{ from: a.item.occurrence, to: b.item.occurrence }] : []; });
    const root = (0, model_js_1.resolveRecord)(all, declared.root, view.file), settings = { algorithm, direction, gap: (0, model_js_1.num)(declared.gap, 88), row_gap: (0, model_js_1.num)(declared.row_gap, 76), columns: (0, model_js_1.num)(declared.columns, 3), width: frame.width, height: frame.height, ...(root ? { root: positioned.find(n => key(n) === (0, model_js_1.refKey)(root.ref))?.item.occurrence ?? '' } : {}) };
    let offset = 0;
    const locations = new Map();
    const ancestry = (id, trail = new Set()) => {
        const region = regions.find(r => r.id === id);
        if (!region || trail.has(id))
            return '0000/' + id;
        const next = new Set(trail);
        next.add(id);
        const rank = String(regions.indexOf(region) + 1).padStart(4, '0');
        return region.parent ? ancestry((0, model_js_1.str)(region.parent), next) + '/' + rank : rank;
    };
    for (const [, group] of [...groups].sort(([a], [b]) => ancestry(a).localeCompare(ancestry(b)))) {
        const positions = (0, graph_layouts_js_1.graphLayout)(group.map(node => ({ id: node.item.occurrence, bounds: { ...node.item.bounds, x: node.item.bounds.x - frame.x, y: node.item.bounds.y - frame.y }, pinned: typeof node.appearance?.record.position === 'object' && node.appearance.record.pinned !== false })), links, settings);
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
        const incoming = new Set(edges.map(edge => (0, graph_common_js_1.endEntry)(edge, 1, positioned, all)).filter(Boolean).map(node => (0, model_js_1.refKey)(node.definition.ref))), roots = positioned.filter(node => !incoming.has((0, model_js_1.refKey)(node.definition.ref)));
        const rung = new Map(), level = new Map();
        roots.forEach((root, ri) => {
            const visit = (node, depth, trail) => {
                const key = (0, model_js_1.refKey)(node.definition.ref);
                if (trail.has(key) || depth > 64)
                    return;
                const next = new Set(trail);
                next.add(key);
                rung.set(key, ri);
                level.set(key, Math.max(depth, level.get(key) ?? 0));
                for (const edge of edges)
                    if ((0, graph_common_js_1.endEntry)(edge, 0, positioned, all) === node) {
                        const to = (0, graph_common_js_1.endEntry)(edge, 1, positioned, all);
                        if (to)
                            visit(to, depth + 1, next);
                    }
            };
            visit(root, 0, new Set());
        });
        const counts = new Map();
        positioned = positioned.map(node => { const key = (0, model_js_1.refKey)(node.definition.ref), ri = rung.get(key) ?? 0, depth = level.get(key) ?? 0, bucket = ri + ':' + depth, branch = counts.get(bucket) ?? 0; counts.set(bucket, branch + 1); return specializedBounds(node, { ...node.item.bounds, x: frame.x + (node.definition.record.role === 'ladder.coil' ? Math.max(760, frame.width - 150) : 70 + depth * 175), y: frame.y + 100 + ri * 210 + branch * 75 }); });
    }
    if (profile === 'network.rack@1') {
        const racks = positioned.filter(n => n.definition.record.role === 'network.rack');
        positioned = positioned.map(node => {
            if (node.definition.record.role === 'network.rack')
                return node;
            const region = (0, model_js_1.array)(node.view.record.regions).map(model_js_1.object).find(region => (0, model_js_1.array)(region.members).some(member => (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, member, node.view.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(node.definition.ref))), scope = region && (0, model_js_1.resolveRecord)(all, region.scope, node.view.file);
            const rack = racks.find(r => scope && (0, model_js_1.refKey)(r.definition.ref) === (0, model_js_1.refKey)(scope.ref)) ?? racks.find(r => (0, graph_common_js_1.memberRecords)(r, all).some(member => (0, model_js_1.refKey)(member.ref) === (0, model_js_1.refKey)(node.definition.ref)));
            const unit = (0, model_js_1.num)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_rack')).unit);
            if (!rack || !unit)
                return node;
            const units = (0, model_js_1.num)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(rack.definition.record, 'x_rack')).units, 42), rb = rack.item.bounds, h = (rb.height - 30) / units;
            return specializedBounds(node, { x: rb.x + 32, y: rb.y + rb.height - h * unit, width: rb.width - 45, height: Math.max(8, h) });
        });
    }
    positioned = positioned.map(node => {
        const event = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_event')), sentry = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_sentry')), attached = (0, model_js_1.resolveRecord)(all, event.position === 'boundary' ? event.on : sentry.attach, node.definition.file), owner = attached && positioned.find(entry => (0, model_js_1.refKey)(entry.definition.ref) === (0, model_js_1.refKey)(attached.ref));
        if (owner) {
            const size = sentry.attach ? 22 : 40, b = owner.item.bounds;
            return specializedBounds(node, { x: b.x + b.width - size * 1.5, y: b.y + b.height - size / 2, width: size, height: size });
        }
        if (node.definition.record.role === 'uml.subject') {
            const contained = positioned.filter(entry => (0, model_js_1.array)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(entry.definition.record, 'x_usecase')).subjects).some(ref => (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, ref, entry.definition.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(node.definition.ref)));
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
    const invalid = nodes.filter(node => { const duration = (0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_estimate'); return typeof duration !== 'number' || !Number.isFinite(duration) || duration < 0; });
    if (invalid.length) {
        for (const node of invalid)
            diagnostics.push({ code: 'cpm-duration-incomplete', severity: 'warning', target: node.definition.ref, message: 'Critical-path analysis requires a supplied finite, nonnegative day estimate.' });
        unavailable.push('analysis:cpm:durations');
        return [...entries];
    }
    const keys = nodes.map(n => (0, model_js_1.refKey)(n.definition.ref)), duration = new Map(nodes.map(n => [(0, model_js_1.refKey)(n.definition.ref), (0, model_js_1.num)((0, graph_glyphs_js_1.metadata)(n.definition.record, 'x_estimate'))])), parents = new Map(keys.map(k => [k, []])), children = new Map(keys.map(k => [k, []]));
    for (const edge of edges) {
        const a = (0, graph_common_js_1.endEntry)(edge, 0, nodes, all), b = (0, graph_common_js_1.endEntry)(edge, 1, nodes, all);
        if (a && b) {
            parents.get((0, model_js_1.refKey)(b.definition.ref)).push((0, model_js_1.refKey)(a.definition.ref));
            children.get((0, model_js_1.refKey)(a.definition.ref)).push((0, model_js_1.refKey)(b.definition.ref));
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
        const k = (0, model_js_1.refKey)(entry.definition.ref);
        if (!es.has(k)) {
            const a = (0, graph_common_js_1.endEntry)(entry, 0, nodes, all), b = (0, graph_common_js_1.endEntry)(entry, 1, nodes, all), ak = a && (0, model_js_1.refKey)(a.definition.ref), bk = b && (0, model_js_1.refKey)(b.definition.ref);
            if (ak && bk && ls.get(ak) === es.get(ak) && ls.get(bk) === es.get(bk) && ef.get(ak) === es.get(bk))
                return (0, graph_common_js_1.changed)(entry, entry.item.bounds, entry.item.primitives.map(p => 'paint' in p ? { ...p, paint: { ...p.paint, stroke: '#2563eb', 'stroke-width': 2.5 } } : p), 'Critical precedence edge');
            return entry;
        }
        const b = entry.item.bounds, slack = ls.get(k) - es.get(k);
        return (0, graph_common_js_1.changed)(entry, { ...b, height: b.height + 62 }, [...entry.item.primitives, (0, graph_glyphs_js_1.box)({ x: b.x, y: b.y + b.height, width: b.width, height: 62 }, '#fff', slack === 0 ? '#2563eb' : '#94a3b8'), (0, graph_glyphs_js_1.label)(`Duration ${duration.get(k)} d`, b.x + 6, b.y + b.height + 17, 11), (0, graph_glyphs_js_1.label)(`ES ${es.get(k)}  EF ${ef.get(k)}  LS ${ls.get(k)}  LF ${lf.get(k)}`, b.x + 6, b.y + b.height + 36, 11), (0, graph_glyphs_js_1.label)(`Slack ${slack} d${slack === 0 ? ' · critical' : ''}`, b.x + 6, b.y + b.height + 53, 11, slack === 0 ? '#2563eb' : '#475569')], 'Deterministic CPM over declared day estimates');
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
    const caption = (0, graph_common_js_1.mark)(entries[0], view, 'method-caption', bounds, lines.map((lineText, i) => (0, graph_glyphs_js_1.label)(lineText, left, top + 13 + i * 17, 12, (0, model_js_1.str)((0, model_js_1.pathValue)(entries[0].effective, 'text.color'), '#64748b'))), 'Interpretation of the supplied method data');
    return [...entries, { ...caption, item: { ...caption.item, layer: 'annotations' } }];
}
function projectGraphProfile(snapshot, view, entries, options = {}) {
    const profile = (0, model_js_1.str)(view.record.profile), native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
    if (native)
        return (0, graph_native_js_1.projectNativeGraph)(snapshot, view, entries, options, projectGraphProfile, id => !!graph_catalogue_js_1.graphCatalogue[id]);
    const contract = graph_catalogue_js_1.graphCatalogue[profile], diagnostics = [], unavailable = [];
    if (!contract)
        return { entries, diagnostics, unavailable };
    const frame = options.bounds ?? { x: 0, y: 0, width: 960, height: 680 }, all = (0, model_js_1.records)(snapshot);
    entries = (0, relation_presentation_js_1.prepareRelationPresentation)(entries, all, options.viewProperties ?? view.record);
    const pending = (0, graph_common_js_1.provisionalNodes)(entries, all);
    if (pending.length) {
        const waiting = new Set(pending);
        const connected = entries.filter(entry => !waiting.has(entry));
        const result = connected.length ? projectGraphProfile(snapshot, view, connected, options) : { entries: [], diagnostics: [], unavailable: [] };
        return { ...result, entries: [...result.entries, ...(0, graph_common_js_1.resolvedText)(pending.map(node => decorateNode(node, all, profile)), profile)] };
    }
    if (contract.projection === 'chen')
        return { entries: (0, graph_common_js_1.resolvedText)(chen(entries, all, profile, diagnostics, unavailable, view, frame, options.viewProperties), profile), diagnostics, unavailable };
    if (contract.projection === 'sequence')
        return { entries: methodCaption((0, graph_common_js_1.inlineInteractions)(snapshot, view, (0, graph_common_js_1.resolvedText)(sequence(entries, all, profile, frame, diagnostics, unavailable, options.viewProperties), profile), all, options, diagnostics, unavailable, projectGraphProfile, id => !!graph_catalogue_js_1.graphCatalogue[id]), view, `Declaration order, not a verified protocol · ${entries.filter(e => e.definition.record.category !== 'relation' && e.definition.record.role !== 'msc.hmscref').length} participants · ${entries.filter(e => e.definition.record.category === 'relation').length} messages · dashed arrows are returns · bars are receiver activations.`), diagnostics, unavailable };
    if (contract.projection === 'timing')
        return { entries: methodCaption((0, graph_common_js_1.resolvedText)(timing(entries, all, profile, frame, diagnostics, unavailable, options.viewProperties), profile), view, `Supplied time points, not a simulation · ${entries.filter(e => e.definition.record.category !== 'relation').length} participants · abstract numeric time axis in the author's unit.`), diagnostics, unavailable };
    if (contract.projection === 'fishbone')
        return { entries: methodCaption((0, graph_common_js_1.resolvedText)(fishbone(entries, all, frame, diagnostics, unavailable, options.viewProperties), profile), view, 'Possible causes, not proven causality · branches are source relationships · repeated appearances retain one identity.'), diagnostics, unavailable };
    const originalNodes = entries.filter(e => e.definition.record.category !== 'relation'), originalEdges = entries.filter(e => e.definition.record.category === 'relation');
    const nodes = layoutGraph(originalNodes, originalEdges, all, profile, frame, view, options.viewProperties).map(node => decorateNode(node, all, profile, true));
    const reservedLabels = [], labelObstacles = [{ x: frame.x, y: frame.y, width: frame.width, height: 45 }, ...nodes.flatMap(node => [...(node.definition.record.role === 'uml.subject' ? [] : [node.item.bounds]), ...node.item.primitives.flatMap(primitive => primitive.kind === 'text' ? primitive.runs.map(run => (0, graph_common_js_1.graphLabelBounds)(run.text, run.x, run.y, (0, model_js_1.num)(run.style['font-size'], 14) * (0, model_js_1.num)((0, model_js_1.pathValue)(node.effective, 'style.font_size'), 16) / 16, (0, model_js_1.str)(run.style['text-anchor'], 'start'))) : [])])];
    const priorRoutes = [];
    let output = [...originalEdges.map(edge => (0, graph_common_js_1.decorateEdge)(edge, nodes, all, profile, frame, labelObstacles, reservedLabels, priorRoutes, (0, model_js_1.str)((0, model_js_1.pathValue)(options.viewProperties ?? view.record, 'layout.crossings'), 'gap'), options.viewProperties)), ...nodes];
    if (profile === 'pert.cpm@1')
        output = cpm(output, nodes, originalEdges, all, diagnostics, unavailable);
    if (profile === 'ladder.basic@1' && nodes.length) {
        const y1 = frame.y + 70, y2 = Math.max(...nodes.map(n => n.item.bounds.y + n.item.bounds.height)) + 40, left = frame.x + 35, right = frame.x + Math.max(900, frame.width - 20);
        const rail = nodes[0];
        output.unshift((0, graph_common_js_1.mark)(rail, view, 'power-rails', { x: left, y: y1, width: right - left, height: y2 - y1 }, [(0, graph_glyphs_js_1.line)([left, y1], [left, y2], '#334155', 3), (0, graph_glyphs_js_1.line)([right, y1], [right, y2], '#334155', 3)], 'Ladder power rails'));
        for (const node of nodes) {
            const hasParent = originalEdges.some(edge => (0, graph_common_js_1.endEntry)(edge, 1, nodes, all) === node);
            if (!hasParent)
                output.push((0, graph_common_js_1.mark)(node, node.definition, 'rail-feed', (0, graph_common_js_1.finiteBounds)([left, (0, graph_common_js_1.center)(node.item.bounds)[1]], [node.item.bounds.x, (0, graph_common_js_1.center)(node.item.bounds)[1]]), [(0, graph_glyphs_js_1.line)([left, (0, graph_common_js_1.center)(node.item.bounds)[1]], [node.item.bounds.x, (0, graph_common_js_1.center)(node.item.bounds)[1]])], 'Ladder rung feed'));
            if (node.definition.record.role === 'ladder.coil')
                output.push((0, graph_common_js_1.mark)(node, node.definition, 'rail-return', (0, graph_common_js_1.finiteBounds)([node.item.bounds.x + node.item.bounds.width, (0, graph_common_js_1.center)(node.item.bounds)[1]], [right, (0, graph_common_js_1.center)(node.item.bounds)[1]]), [(0, graph_glyphs_js_1.line)([node.item.bounds.x + node.item.bounds.width, (0, graph_common_js_1.center)(node.item.bounds)[1]], [right, (0, graph_common_js_1.center)(node.item.bounds)[1]])], 'Ladder rung return'));
        }
    }
    if (profile === 'vsm.basic@1') {
        const processes = nodes.filter(node => node.definition.record.role === 'vsm.process');
        if (processes.length) {
            const y = Math.max(...nodes.map(n => n.item.bounds.y + n.item.bounds.height)) + 50, ps = [];
            let x = frame.x + 30;
            for (const node of processes) {
                const values = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_vsm'));
                ps.push((0, graph_glyphs_js_1.path)(`M${x},${y}H${x + 70}V${y + 25}H${x + 140}V${y}`, 'none'), (0, graph_glyphs_js_1.label)(`${(0, model_js_1.num)(values.nva)} ${(0, model_js_1.str)(values.unit)}`, x + 3, y - 8, 11), (0, graph_glyphs_js_1.label)(`${(0, model_js_1.num)(values.va)} ${(0, model_js_1.str)(values.unit)}`, x + 75, y + 43, 11));
                x += 140;
            }
            ps.push((0, graph_glyphs_js_1.label)('VA / NVA timeline · Σ ' + processes.reduce((sum, node) => { const values = (0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(node.definition.record, 'x_vsm')); return sum + (0, model_js_1.num)(values.va) + (0, model_js_1.num)(values.nva); }, 0), frame.x + 30, y + 70, 12));
            output.push((0, graph_common_js_1.mark)(processes[0], view, 'vsm-timeline', { x: frame.x + 30, y: y - 15, width: x - frame.x, height: 90 }, ps, 'Declared non-value-added and value-added timeline ladder'));
        }
    }
    return { entries: (0, graph_common_js_1.inlineInteractions)(snapshot, view, (0, graph_common_js_1.resolvedText)((0, graph_common_js_1.graphAdornments)(output, view, all, profile), profile), all, options, diagnostics, unavailable, projectGraphProfile, id => !!graph_catalogue_js_1.graphCatalogue[id]), diagnostics, unavailable };
}

},
"standalone/src/families/graphs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const family_graphs_js_1 = require("presentation/src/family-graphs.js");
(0, family_graphs_js_1.installGraphsPresentation)();

}});})();
