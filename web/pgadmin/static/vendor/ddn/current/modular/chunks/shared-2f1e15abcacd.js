/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-2f1e15abcacd","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":[],"modules":[{"id":"presentation/src/adapters.js","bytes":2783,"sha256":"35f6d7adc10f2b976962aaac89687ba4a369aa3bbdeaf5912df5e985abc8504a","dependencies":[]},{"id":"presentation/src/model.js","bytes":5180,"sha256":"77dd604924958dd7f7f42b1a287cca08f66bef006f85d1bf1b594609cacb30bc","dependencies":[]}],"hash":"a853d86d6228d8daecedfe686d68dc439ad6ab818b406cc55c1ddc55df8ff86f"},{"presentation/src/adapters.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.dataProjector = exports.graphProjector = exports.isDataProfile = exports.isGraphProfile = exports.availableProjectionProfiles = void 0;
exports.installPresentationFamily = installPresentationFamily;
exports.installedPresentationFamilies = installedPresentationFamilies;
exports.analyzePresentedProfile = analyzePresentedProfile;
const installed = new Map();
const owners = new Map();
const nativeProfiles = ['ddn@1', 'mindmap.basic@1', 'concept.map@1', 'table.records@1'];
const available = new Set(nativeProfiles);
exports.availableProjectionProfiles = available;
function installPresentationFamily(family) {
    if (!['graphs', 'charts', 'geography', 'surfaces'].includes(family.id) || family.version !== '1.0.0' || family.language !== 'ddn-next-1' || !family.profiles.length || new Set(family.profiles).size !== family.profiles.length || (family.kind === 'graph' ? typeof family.graph !== 'function' || !!family.data : family.kind === 'data' ? typeof family.data !== 'function' || !!family.graph : true))
        throw new TypeError('Unsupported presentation family: ' + family.id);
    const previous = installed.get(family.id);
    if (previous) {
        if (previous.version === family.version && previous.language === family.language && previous.graph === family.graph && previous.data === family.data && previous.analyze === family.analyze && previous.profiles.join('\0') === family.profiles.join('\0'))
            return;
        throw new Error('Conflicting presentation family: ' + family.id);
    }
    for (const profile of family.profiles)
        if (available.has(profile))
            throw new Error('Duplicate presentation profile: ' + profile);
    const copy = Object.freeze({ ...family, profiles: Object.freeze([...family.profiles]) });
    installed.set(family.id, copy);
    for (const profile of copy.profiles) {
        available.add(profile);
        owners.set(profile, copy);
    }
}
function installedPresentationFamilies() { return Object.freeze([...installed.values()]); }
const isGraphProfile = (profile) => owners.get(profile)?.kind === 'graph';
exports.isGraphProfile = isGraphProfile;
const isDataProfile = (profile) => owners.get(profile)?.kind === 'data';
exports.isDataProfile = isDataProfile;
const graphProjector = (profile) => owners.get(profile)?.graph;
exports.graphProjector = graphProjector;
const dataProjector = (profile) => owners.get(profile)?.data;
exports.dataProjector = dataProjector;
function analyzePresentedProfile(normalized, target, values) {
    const analyzer = [...installed.values()].find(family => family.analyze)?.analyze;
    return analyzer ? analyzer(normalized, target, values) : { kind: 'none', outcome: 'not-applicable' };
}

},
"presentation/src/model.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.num = exports.str = exports.array = exports.object = void 0;
exports.pathValue = pathValue;
exports.refKey = refKey;
exports.records = records;
exports.resolveRecord = resolveRecord;
exports.findRecord = findRecord;
exports.titleOf = titleOf;
exports.tableData = tableData;
exports.asJson = asJson;
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {};
exports.object = object;
const array = (value) => Array.isArray(value) ? value : [];
exports.array = array;
const str = (value, fallback = '') => typeof value === 'string' ? value : fallback;
exports.str = str;
const num = (value, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
exports.num = num;
function pathValue(value, path) { return path.split('.').reduce((v, key) => (0, exports.object)(v)[key], value); }
function refKey(ref) { return JSON.stringify([ref.file, ref.id]); }
function records(snapshot) {
    const result = [];
    for (const raw of (0, exports.array)((0, exports.object)(snapshot.normalized).files)) {
        const item = (0, exports.object)(raw);
        const file = (0, exports.str)(item.location);
        const document = (0, exports.object)(item.document);
        if (document.workarea) {
            const record = (0, exports.object)(document.workarea);
            result.push({ file, record, owner: 'workarea', ref: { file, id: (0, exports.str)(record.id, (0, exports.str)(record.name, 'workarea')) } });
        }
        for (const [plural, owner] of Object.entries({ definitions: 'definition', views: 'view', appearances: 'appearance', placements: 'placement', data: 'data', sources: 'source', assets: 'asset', templates: 'template', publications: 'publication' }))
            for (const rawRecord of (0, exports.array)(document[plural])) {
                const record = (0, exports.object)(rawRecord);
                result.push({ file, record, owner, ref: { file, id: (0, exports.str)(record.id, (0, exports.str)(record.name)) } });
            }
    }
    return result;
}
function resolveRecord(all, reference, declaringFile) {
    const ref = (0, exports.object)(reference);
    const file = (0, exports.str)(ref.file, declaringFile);
    const id = (0, exports.str)(ref.id);
    const name = (0, exports.str)(ref.name);
    return all.find(item => item.file === file && (id ? item.ref.id === id : name ? item.record.name === name : false));
}
function findRecord(snapshot, ref) { return records(snapshot).find(item => item.file === ref.file && item.ref.id === ref.id); }
function titleOf(record) { return (0, exports.str)(record.title) || (0, exports.str)(record.name) || ((0, exports.str)(record.role) === 'entity' || (0, exports.str)(record.role) === 'table' ? '<table>' : `<${(0, exports.str)(record.role, 'item')}>`); }
function tableData(snapshot, item) {
    const all = records(snapshot);
    const definition = item.record;
    let data = (0, exports.object)(definition.data), dataFile = item.file;
    if (data.source) {
        const source = resolveRecord(all, data.source, item.file);
        if (source?.owner === 'data') {
            data = source.record;
            dataFile = source.file;
        }
    }
    const displayed = (source) => {
        const columns = (0, exports.array)(source.columns).map(exports.object);
        const rows = (0, exports.array)(source.rows).map(row => (0, exports.array)(row).map((cell, index) => {
            if (columns[index]?.id !== 'domain')
                return cell;
            const domain = typeof cell === 'string' ? all.find(record => record.file === dataFile && (record.ref.id === cell || record.record.name === cell)) : resolveRecord(all, cell, dataFile);
            return domain?.record.role === 'domain' ? titleOf(domain.record) : cell;
        }));
        return { columns, rows };
    };
    if (Array.isArray(data.columns))
        return displayed(data);
    const captured = (0, exports.object)(data.snapshot);
    if (Array.isArray(captured.columns))
        return displayed(captured);
    const members = (0, exports.array)(definition.members).map(ref => resolveRecord(all, ref, item.file)).filter((value) => !!value);
    return { columns: ['field', 'type', 'domain', 'constraint', 'key', 'comment'].map(id => ({ id })), rows: members.map(member => {
            const content = (0, exports.object)(member.record.content);
            const properties = (0, exports.object)(member.record.properties);
            const domain = member.record.domain ?? content.domain;
            const domainRecord = resolveRecord(all, domain, member.file);
            return [titleOf(member.record), content.datatype ?? content.type ?? properties.datatype ?? properties.type ?? '', domainRecord ? titleOf(domainRecord.record) : (0, exports.str)(domain), (0, exports.array)(member.record.constraints).map(value => typeof value === 'string' ? value : JSON.stringify(value)).join(', '), content.key ?? properties.key ?? '', content.comment ?? member.record.description ?? ''];
        }) };
}
function asJson(value) { return value; }

}});})();
