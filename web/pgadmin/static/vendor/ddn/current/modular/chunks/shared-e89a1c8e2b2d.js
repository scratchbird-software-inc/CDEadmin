/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-e89a1c8e2b2d","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-89ca0b52749b"],"modules":[{"id":"profiles/src/family-packs.js","bytes":2368,"sha256":"5f3f65cd8a2edecbfb6372b823fd1a240fd456214654ddf70c156def1535c3e0","dependencies":["profiles/src/schema-core.js","profiles/src/core.js","profiles/src/generated-families.js","profiles/src/native.js","profiles/src/rules.js"]},{"id":"profiles/src/native.js","bytes":1057,"sha256":"c5060cfb0032efb88064e71bb879a02c8c181531eb8e1ae2a15efbe483252d08","dependencies":["profiles/src/schema-core.js","profiles/src/core.js","profiles/src/rules.js"]},{"id":"profiles/src/rules.js","bytes":4442,"sha256":"4d69afec113b090971b8fac832ac6857cf66b9e23bbb56a669f36ffdd06c9348","dependencies":["profiles/src/core.js","profiles/src/schema-core.js"]}],"hash":"50621f2128363c4d3e3d646e4a9d9144c4621cf3f175df7aed3e2d9cbdb4e0af"},{"profiles/src/family-packs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerProfileFamily = registerProfileFamily;
exports.loadedProfilePacks = loadedProfilePacks;
const schema_core_js_1 = require("profiles/src/schema-core.js");
const core_js_1 = require("profiles/src/core.js");
const generated_families_js_1 = require("profiles/src/generated-families.js");
const native_js_1 = require("profiles/src/native.js");
const rules_js_1 = require("profiles/src/rules.js");
const families = new Map();
const evaluators = new Map();
function registerProfileFamily(id, profiles, evaluate) {
    const packId = 'ddn-' + id;
    const expected = generated_families_js_1.catalogueFamilies[id];
    if (!expected || id === 'native' || profiles.length !== expected.profiles.length || new Set(profiles).size !== profiles.length || profiles.some(profile => !expected.profiles.includes(profile)))
        throw new Error('Invalid profile family manifest: ' + id);
    if (families.has(packId)) {
        if (evaluators.get(packId) !== evaluate)
            throw new Error('Conflicting profile family: ' + id);
        return;
    }
    if (!profiles.length || new Set(profiles).size !== profiles.length || profiles.some(profile => core_js_1.nativeProfileIds.includes(profile) || !(0, core_js_1.profileDescriptor)(profile)))
        throw new Error('Missing or invalid catalogue data for family: ' + id);
    const occupied = new Set([...families.values()].flatMap(pack => pack.manifest.profiles));
    if (profiles.some(profile => occupied.has(profile)))
        throw new Error('Duplicate profile family: ' + id);
    evaluators.set(packId, evaluate);
    families.set(packId, (0, core_js_1.freezeProfileData)({
        manifest: (0, core_js_1.freezeProfileData)({ id: packId, version: '1.0.0', api: '1.0', hash: expected.hash, languages: [core_js_1.contractVersion], defaults: [core_js_1.contractVersion], profiles: [...expected.profiles], dependencies: ['ddn-native'], capabilities: ['ddn.family.descriptors', 'ddn.family.verification'] }),
        registrations: (0, core_js_1.freezeProfileData)({ profiles: expected.profiles.map(profile => (0, core_js_1.profileDescriptor)(profile)), rules: (0, rules_js_1.rulesFor)(expected.profiles, evaluate) }),
    }));
}
function loadedProfilePacks() { return [(0, native_js_1.createNativePack)(), ...families.values()]; }

},
"profiles/src/native.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.nativeRules = void 0;
exports.createNativePack = createNativePack;
const schema_core_js_1 = require("profiles/src/schema-core.js");
const core_js_1 = require("profiles/src/core.js");
const rules_js_1 = require("profiles/src/rules.js");
exports.nativeRules = (0, rules_js_1.rulesFor)(core_js_1.nativeProfileIds);
function createNativePack(registrations = {}) {
    return (0, core_js_1.freezeProfileData)({ manifest: (0, core_js_1.freezeProfileData)({ id: 'ddn-native', version: '1.0.0', api: '1.0', hash: schema_core_js_1.codex.sourceHashes['ddn.schema.json'] ?? '', languages: [core_js_1.contractVersion], defaults: [core_js_1.contractVersion], profiles: [...core_js_1.nativeProfileIds], dependencies: [], capabilities: ['ddn.native.descriptors', 'ddn.native.verification'] }), registrations: { ...registrations, profiles: core_js_1.nativeProfileIds.map(id => (0, core_js_1.profileDescriptor)(id)), rules: [...exports.nativeRules, ...(registrations.rules ?? [])] } });
}

},
"profiles/src/rules.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.rulesFor = rulesFor;
const core_js_1 = require("profiles/src/core.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
function rulesFor(ids, additional) {
    return ids.map(id => ({
        id: (core_js_1.nativeProfileIds.includes(id) ? 'ddn.native.' : 'ddn.profile.') + id, version: id === 'mindmap.basic@1' ? '1.0.1' : '1.0.0', profiles: [id], levels: ['semantic', 'review', 'publication'], purposes: ['*'],
        readPaths: ['views', 'definitions', 'appearances', 'data'], globalScope: true,
        async evaluate(input, options, context) {
            const records = (0, core_js_1.indexRecords)(input.normalized);
            const target = options.scope.kind === 'workarea' ? undefined : (0, core_js_1.resolveRecord)(records, options.scope.target.file, options.scope.target);
            const key = (r) => r.file + '\0' + r.ref.id;
            const selectedViews = new Set();
            if (target?.owner === 'view_definition')
                selectedViews.add(key(target));
            const documents = target?.owner === 'document' ? [target] : [];
            const seenDocuments = new Set(documents.map(key));
            for (let i = 0; i < documents.length; i++) {
                const document = documents[i], sections = document.record.sections;
                await context.checkpoint(Array.isArray(sections) ? sections.length + 1 : 1);
                for (const section of Array.isArray(sections) ? sections.filter(schema_core_js_1.isRecord) : []) {
                    if (section.kind !== 'view')
                        continue;
                    const included = (0, core_js_1.resolveRecord)(records, document.file, section.target);
                    if (included?.owner === 'view_definition')
                        selectedViews.add(key(included));
                    else if (included?.owner === 'document' && !seenDocuments.has(key(included))) {
                        seenDocuments.add(key(included));
                        documents.push(included);
                    }
                }
            }
            if (target?.owner === 'appearance') {
                const view = (0, core_js_1.resolveRecord)(records, target.file, target.record.parent);
                if (view)
                    selectedViews.add(key(view));
            }
            if (target?.owner === 'definition') {
                const owners = new Set((0, core_js_1.enclosingDefinitions)(records, target).map(key));
                for (const occurrence of records.filter(r => r.owner === 'appearance')) {
                    const definition = (0, core_js_1.resolveRecord)(records, occurrence.file, occurrence.record.target);
                    if (definition && owners.has(key(definition))) {
                        const view = (0, core_js_1.resolveRecord)(records, occurrence.file, occurrence.record.parent);
                        if (view)
                            selectedViews.add(key(view));
                    }
                }
            }
            const views = records.filter(r => r.owner === 'view_definition' && (r.record.profile ?? 'ddn@1') === id && (options.scope.kind === 'workarea' || selectedViews.has(key(r))));
            const diagnostics = [];
            for (const view of views) {
                await context.checkpoint(records.length);
                const review = options.level === 'review' || options.level === 'publication';
                diagnostics.push(...(0, core_js_1.nativeProfileDiagnostics)(input.normalized, view, records, review));
                if (additional && !core_js_1.nativeProfileIds.includes(id))
                    diagnostics.push(...additional(view, records, review));
                await context.checkpoint(1);
            }
            const unavailable = diagnostics.filter(d => d.code === 'DDN-TABLE-INCOMPLETE' || d.code.endsWith('-INCOMPLETE') || d.code.endsWith('-UNKNOWN') || d.code === 'DDN-ANALYSIS-BUDGET').map(d => d.message);
            return { outcome: diagnostics.some(d => d.severity === 'error') ? 'invalid' : unavailable.length ? 'incomplete' : 'valid', diagnostics, dependencies: views.map(r => ({ target: r.ref, path: '*', fingerprint: input.semanticFingerprint })), coverage: { scope: options.scope, complete: unavailable.length === 0, checked: views.map(r => r.ref), unavailable } };
        }
    }));
}

}});})();
