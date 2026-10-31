/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-86dfe18929a0","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-4dfa2129e2cc","shared-9019e1da906d","shared-c435f270a427"],"modules":[{"id":"presentation/src/node-dimensions.js","bytes":2660,"sha256":"67b709bdc955e942d77317da5f70d7b9559e6e69be43f377489976ed89d2c6df","dependencies":["profiles/src/core.js","presentation/src/model.js","presentation/src/graph-glyphs.js"]}],"hash":"64b5db3b6fc19b0016459a84b4b0047963c34769072e57fcbc67886bda37401d"},{"presentation/src/node-dimensions.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.graphNodeDimensions = graphNodeDimensions;
const core_js_1 = require("profiles/src/core.js");
const model_js_1 = require("presentation/src/model.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
function graphNodeDimensions(role, profile, original, record = {}, fixedSize = false) {
    if (fixedSize)
        return original;
    const b = { ...original, width: Math.max(160, Math.min(280, original.width)), height: Math.max(72, original.height) };
    if (!profile.startsWith('bpmn') && !profile.startsWith('uml.activity') && ['flow.start', 'flow.end'].includes(role))
        return { ...b, width: 130, height: 52 };
    if (/^(state\.(initial|final|junction|entrypoint|exitpoint|terminate|history_deep|history_shallow)|flow\.(start|end|intermediate|flowfinal)|petri\.place|epk\.connector)$/.test(role))
        return { ...b, width: 54, height: 54 };
    if (/^(flow\.(decision|gateway|merge)|state\.choice|cmmn\.sentry)$/.test(role))
        return { ...b, width: 88, height: 80 };
    if (role === 'uml.actor' || role === 'c4.person' || (0, core_js_1.roleDescriptor)(role)?.render.silhouette === 'actor')
        return { ...b, width: 100, height: 116 };
    if (role === 'petri.transition')
        return { ...b, width: 80, height: 30 };
    if (role === 'family.union')
        return { ...b, width: 110, height: 110 };
    if (role === 'flow.forkjoin' || role === 'state.forkjoin')
        return { ...b, width: 160, height: 15 };
    if (role === 'network.rack' && profile === 'network.rack@1')
        return { ...b, width: 300, height: 560 };
    if (role === 'network.bus')
        return { ...b, width: 640, height: 30 };
    if (role.startsWith('ladder.'))
        return { ...b, width: 100, height: 55 };
    if (role === 'tree.event')
        return { ...b, width: 140, height: 140 };
    if (profile === 'dfd.yourdon@1' && role === 'dfd.process')
        return { ...b, width: 170, height: 170 };
    if (profile.startsWith('dfd.'))
        return { ...b, width: 170, height: role === 'dfd.process' ? 100 : 65 };
    if (role === 'flow.choreotask')
        return { ...b, height: Math.max(b.height, 88 + (0, model_js_1.array)((0, graph_glyphs_js_1.metadata)(record, 'x_bands')).length * 18) };
    if (['inline', 'thumbnail'].includes((0, model_js_1.str)((0, model_js_1.object)((0, graph_glyphs_js_1.metadata)(record, 'x_subdiagram')).display, profile === 'uml.interaction_overview@2' ? 'inline' : '')) && (0, graph_glyphs_js_1.metadata)(record, 'x_subdiagram'))
        return { ...b, width: 600, height: 400 };
    return b;
}

}});})();
