/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-8776885c04b2","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-0e2e62c8ac26","shared-4788c79b979a","shared-4dfa2129e2cc","shared-53be1a54a3de","shared-646a07aa4889","shared-9019e1da906d","shared-c435f270a427","shared-cca37dc67bcd","shared-e2b9b2a21e0e"],"modules":[{"id":"presentation/src/graph-isometric.js","bytes":3789,"sha256":"a458b27f75d167c39970168dbc09ee997341a5d3fab6f05c293a886e1801a324","dependencies":["presentation/src/model.js"]},{"id":"presentation/src/native-render.js","bytes":17599,"sha256":"79179f31a81135c22666628adf2d21215ae9639d2ae018a4de544065cb19d89f","dependencies":["profiles/src/core.js","presentation/src/model.js","presentation/src/graph-glyphs.js"]},{"id":"presentation/src/native.js","bytes":1282,"sha256":"4ebdd36f10c8ddd5799185eb245be5d12c9d8e11168a6e812a929bd9786bc613","dependencies":["presentation/src/model.js","presentation/src/table.js","presentation/src/markdown.js","presentation/src/project-core.js","presentation/src/records.js","presentation/src/publication.js","presentation/src/adapters.js","presentation/src/relation-presentation.js"]},{"id":"presentation/src/project-core.js","bytes":67751,"sha256":"d300d594a707bd9199ec20ffa01f69c55b2a174eb1137ef27ea83ac1b304743f","dependencies":["presentation/src/card-text.js","presentation/src/view-surface.js","presentation/src/model.js","presentation/src/table.js","presentation/src/symbol-presentation.js","presentation/src/records.js","presentation/src/graph-native.js","presentation/src/adapters.js","profiles/src/core.js","profiles/src/mindmap.js","presentation/src/graph-isometric.js","presentation/src/stationery.js","presentation/src/native-render.js","presentation/src/publication.js","presentation/src/relation-presentation.js","presentation/src/graph-common.js"]},{"id":"presentation/src/publication.js","bytes":8455,"sha256":"6ece9d615ade311ff9fb5d5a82223707cb4a70369354061651031c5b86e65837","dependencies":["presentation/src/table.js","presentation/src/model.js"]},{"id":"presentation/src/records.js","bytes":5727,"sha256":"d806dcbe4e441eb4e7e41c1b179c05794fba3b7cd73d2bad9d4e5c4a2a327229","dependencies":["presentation/src/model.js"]},{"id":"presentation/src/view-surface.js","bytes":5069,"sha256":"eb76f7c3c5e18906220371e9b5cc68daa5963cd56793cbf9ace75b0f4d43d26b","dependencies":["presentation/src/model.js"]},{"id":"runtime/src/guards.js","bytes":5217,"sha256":"599cd434abf3b85bb5814937ae390fc6b57f455f4d408fbbc2d763a3dc439589","dependencies":["model/src/index.js","profiles/src/schema-core.js","execution/src/index.js"]},{"id":"runtime/src/native.js","bytes":985,"sha256":"53321a5cca5ec40e70ee24d31791ce3d74ba74bc03cb0d6dcde740a78a6de8ec","dependencies":["runtime/src/runtime.js","runtime/src/registry.js","profiles/src/native.js"]},{"id":"runtime/src/profile-loading.js","bytes":541,"sha256":"e9cb562d4cef187d290d1695f7e69f7bc866115b708bb9d748be2acbc56a03c2","dependencies":[]},{"id":"runtime/src/providers.js","bytes":8553,"sha256":"c90061d15a06952fec543029b176dc30fb5084095147bdbb56c87291dd023020","dependencies":["model/src/index.js","execution/src/index.js"]},{"id":"runtime/src/registry.js","bytes":4873,"sha256":"4abe1d53ff14597c50ff699fd26d734630e85f7f4c7db59952f315a1850534c3","dependencies":["execution/src/index.js"]},{"id":"runtime/src/runtime.js","bytes":25454,"sha256":"0a0b790e28bd6fb33fc44f83f1ea51ef4c815504a15b21b3b9547c528f11caa9","dependencies":["language/src/index.js","model/src/index.js","verifier/src/index.js","execution/src/index.js","runtime/src/registry.js","runtime/src/guards.js","runtime/src/providers.js","execution/src/compute.js","runtime/src/versions.js"]},{"id":"standalone/src/modular-runtime.js","bytes":6782,"sha256":"5d7d2d8290f806a86532eec337e3779191d2ad3410ce126555e18652a17f96f6","dependencies":["profiles/src/core.js","profiles/src/family-packs.js","runtime/src/runtime.js","runtime/src/registry.js","runtime/src/profile-loading.js","model/src/index.js","standalone/src/modular-loading.js"]},{"id":"standalone/src/modular-viewer.js","bytes":1190,"sha256":"8772434629795c388056bfb4f8dc0294418a0de5f22aa4f7804551e72d222bcd","dependencies":["viewer/src/native.js","standalone/src/modular-runtime.js","standalone/src/modular-loading.js"]},{"id":"viewer/src/core.js","bytes":107696,"sha256":"0211c0badd6df4a0ef5552bee9774b9dbf10812efb8c0cb06be82a0d882a08a9","dependencies":["viewer/src/drawer.js","viewer/src/side-tabs.js","viewer/src/svg-assets.js","presentation/src/adapters.js","runtime/src/registry.js","runtime/src/native.js","defaults/src/index.js","presentation/src/native.js","viewer/src/ui-theme.js","viewer/src/ui-icons.js","viewer/src/dialogs.js","viewer/src/fonts.js","viewer/src/texture.js","viewer/src/ui-commands.js","viewer/src/grid.js","viewer/src/status-hint.js","viewer/src/standalone-viewport.js"]},{"id":"viewer/src/grid.js","bytes":842,"sha256":"bd759a47212a66d8a0b0dc9983a2468a34a4576e3cf76714038f2b3fa5430bc1","dependencies":["presentation/src/native.js"]},{"id":"viewer/src/native.js","bytes":811,"sha256":"48e0d16af58c7ebfd2f8079bbfbcf203cca5626ab0e2961dcdc39ebe86d3f8fa","dependencies":["viewer/src/core.js"]},{"id":"viewer/src/side-tabs.js","bytes":4583,"sha256":"4332c26a2cc389c117bbc3c9ca8b49e0d0d8fb49f5d1d5e14e7f7cb44112cfeb","dependencies":["viewer/src/ui-icons.js"]},{"id":"viewer/src/standalone-viewport.js","bytes":933,"sha256":"41752ca40630e30e022ba9c29ef5785a18735f288b92406b3fe9162fc0da06dc","dependencies":[]},{"id":"viewer/src/status-hint.js","bytes":3555,"sha256":"c82bdfba8f4beabac5af5826e1b2aa84f025bee991ec54f5ae44cde48eb7b467","dependencies":[]},{"id":"viewer/src/svg-assets.js","bytes":2956,"sha256":"1772e521ce6e40afd96b1a50adecd89884f168f286eb39b34a07b7375f5dacd9","dependencies":[]}],"hash":"3fff5578d65ef4808744066e476d259c93a18f05eb3a26ed47a5e35e8c768e7e"},{"presentation/src/graph-isometric.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isometricGraph = isometricGraph;
const model_js_1 = require("presentation/src/model.js");
const ground = [Math.sqrt(3) / 2, .5, -Math.sqrt(3) / 2, .5, 0, 0];
const inverse = (m) => { const d = m[0] * m[3] - m[1] * m[2]; return [m[3] / d, -m[1] / d, -m[2] / d, m[0] / d, (m[2] * m[5] - m[3] * m[4]) / d, (m[1] * m[4] - m[0] * m[5]) / d]; };
const compose = (a, b) => [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]];
function transformed(b, m) {
    const points = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].map(([x, y]) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]);
    const x = Math.min(...points.map(p => p[0])), y = Math.min(...points.map(p => p[1]));
    return { x, y, width: Math.max(...points.map(p => p[0])) - x, height: Math.max(...points.map(p => p[1])) - y };
}
function isometricGraph(entries, frame, defaultDepth) {
    if (!entries.length)
        return [];
    const projected = entries.map(entry => {
        const relation = entry.definition.record.category === 'relation' || entry.definition.owner === 'view' || entry.item.layer === 'views' || /:(region|package|subject|fragment):/.test(entry.item.occurrence);
        const depth = relation ? 0 : Math.max(0, Math.min(2000, (0, model_js_1.num)((0, model_js_1.pathValue)(entry.effective, 'properties.depth'), (0, model_js_1.num)((0, model_js_1.pathValue)(entry.definition.record, 'properties.depth'), defaultDepth))));
        const matrix = [ground[0], ground[1], ground[2], ground[3], 0, -depth];
        const top = transformed(entry.item.bounds, matrix);
        return { entry, depth, matrix, bounds: { ...top, height: top.height + depth } };
    });
    const dx = frame.x + 24 - Math.min(...projected.map(p => p.bounds.x)), dy = frame.y + 60 - Math.min(...projected.map(p => p.bounds.y));
    return projected.sort((a, b) => Number(b.entry.definition.record.category === 'relation') - Number(a.entry.definition.record.category === 'relation') || a.bounds.y - b.bounds.y).map(({ entry, depth, matrix, bounds }) => {
        const local = inverse(entry.item.transform);
        const semantic = entry.item.hitTargets.find(hit => hit.target.file === entry.item.target.file && hit.target.id === entry.item.target.id)?.bounds ?? entry.item.bounds;
        const { x, y, width: w, height: h } = transformed(semantic, local);
        const ex = (local[0] + local[2]) * depth, ey = (local[1] + local[3]) * depth;
        const faces = depth ? [
            { kind: 'path', d: `M${x + w},${y}L${x + w + ex},${y + ey}L${x + w + ex},${y + h + ey}L${x + w},${y + h}Z`, paint: { fill: '#aac2d0', stroke: '#64748b', 'stroke-width': 1 } },
            { kind: 'path', d: `M${x},${y + h}L${x + ex},${y + h + ey}L${x + w + ex},${y + h + ey}L${x + w},${y + h}Z`, paint: { fill: '#c9dae3', stroke: '#64748b', 'stroke-width': 1 } },
        ] : [];
        const placed = [matrix[0], matrix[1], matrix[2], matrix[3], dx, dy - depth];
        const itemBounds = { ...bounds, x: bounds.x + dx, y: bounds.y + dy };
        return { ...entry, item: { ...entry.item, bounds: itemBounds, ...(entry.item.clip ? { clip: transformed(entry.item.clip, placed) } : {}), transform: compose(placed, entry.item.transform), primitives: [...faces, ...entry.item.primitives], hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: transformed(hit.bounds, placed) })), accessible: { ...entry.item.accessible, description: [entry.item.accessible.description, depth ? `isometric depth ${depth}` : 'isometric ground route'].filter(Boolean).join('; ') } } };
    });
}

},
"presentation/src/native-render.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.nativeCode = void 0;
exports.nativeIcon = nativeIcon;
exports.nativeContour = nativeContour;
exports.nativeBadges = nativeBadges;
exports.badgePrimitives = badgePrimitives;
exports.originRank = originRank;
exports.inheritedPresentation = inheritedPresentation;
const core_js_1 = require("profiles/src/core.js");
const model_js_1 = require("presentation/src/model.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
const codes = { object: 'OBJ', entity: 'ENT', table: 'TBL', history: 'HIST', term: 'TERM', domain: 'DOM', binding: 'BIND', identity: 'KEY', activity: 'ACT', pipeline: 'PIP', application: 'APP', dataset: 'DST', document: 'DOC', collection: 'COL', array: 'ARR', sample: 'SMP', note: 'NOTE', 'note.sticky': 'NOTE', procedure: 'PRC', function: 'FUN', service: 'SRV', database: 'DB', schema: 'SCM', context: 'CTX', topic: 'TOP', queue: 'QUE', record: 'REC', view: 'VIW', materialized_view: 'MV', rule: 'RULE', test: 'TEST', cloud: 'CLOUD', replica: 'RPL', shard: 'SHD', cache: 'CAC', graph_node: 'NOD', graph_edge: 'EDG', key_value: 'KVS', report: 'RPT', dashboard: 'DSH', data_product: 'DPR', contract: 'CTRT', team: 'TEAM', fact: 'FCT', dimension: 'DIM', vector: 'VEC', backup: 'BAK', recovery: 'RCP', external_actor: 'ACTOR' };
const nativeCode = (role) => codes[role] ?? role.split('.').at(-1).replaceAll('_', ' ').toUpperCase();
exports.nativeCode = nativeCode;
function nativeIcon(glyph, b, color) {
    const { x, y, width: w, height: h } = b, cx = x + w / 2, cy = y + h / 2;
    const p = (d) => (0, graph_glyphs_js_1.path)(d, 'none', color, 1.4), l = (a, c, d, e) => (0, graph_glyphs_js_1.line)([x + a * w, y + c * h], [x + d * w, y + e * h], color, 1.4);
    if (glyph === 'server')
        return [(0, graph_glyphs_js_1.rounded)(b, 'none', color, 2), l(0, .33, 1, .33), l(0, .66, 1, .66), ...[[.18, .18], [.18, .5], [.18, .82]].map(([a, c]) => (0, graph_glyphs_js_1.oval)({ x: x + a * w - 1, y: y + c * h - 1, width: 2, height: 2 }, color, color))];
    if (['backup', 'restore', 'cache'].includes(glyph))
        return [(0, graph_glyphs_js_1.oval)({ x, y: y + h * .1, width: w * .75, height: h * .28 }, 'none', color), p(`M${x},${y + h * .25}V${y + h * .8}Q${x + w * .35},${y + h} ${x + w * .75},${y + h * .8}V${y + h * .25}`), ...(glyph === 'cache' ? [p(`M${x + w * .7},${y + h * .4}L${x + w * .45},${y + h * .7}H${x + w * .7}L${x + w * .6},${y + h}L${x + w},${y + h * .6}H${x + w * .8}Z`)] : [p(`M${x + w * .55},${y + h * .75}A${w * .25},${h * .25} 0 1 ${glyph === 'restore' ? 0 : 1} ${x + w},${y + h * .75} M${x + w * .75},${y + h * .55}L${x + w},${y + h * .75}L${x + w * .75},${y + h * .85}`)])];
    if (glyph === 'export')
        return [(0, graph_glyphs_js_1.box)({ x, y, width: w * .65, height: h }, 'none', color), l(.4, .5, 1, .5), l(.75, .25, 1, .5), l(.75, .75, 1, .5)];
    if (glyph === 'zone')
        return [(0, graph_glyphs_js_1.box)(b, 'none', color, 1.4, '3 2'), (0, graph_glyphs_js_1.oval)({ x: x + w * .3, y: y + h * .3, width: w * .4, height: h * .4 }, 'none', color)];
    if (glyph === 'copy')
        return [(0, graph_glyphs_js_1.box)({ x: x + w * .25, y: y + h * .25, width: w * .75, height: h * .75 }, 'none', color), p(`M${x + w * .15},${y + h * .75}H${x}V${y}H${x + w * .75}V${y + h * .15}`)];
    if (glyph === 'keyvalue')
        return [(0, graph_glyphs_js_1.oval)({ x, y, width: w * .35, height: h * .35 }, 'none', color), l(.3, .3, .7, .7), l(.5, .5, .65, .35), l(.65, .8, 1, .8), l(.65, 1, 1, 1)];
    if (glyph === 'people')
        return [[.2, .35], [.8, .35], [.5, .12]].flatMap(([a, c]) => [(0, graph_glyphs_js_1.oval)({ x: x + a * w - w * .12, y: y + c * h, width: w * .24, height: h * .24 }, 'none', color), p(`M${x + (a - .2) * w},${y + (c + .6) * h}V${y + (c + .4) * h}Q${x + a * w},${y + (c + .2) * h} ${x + (a + .2) * w},${y + (c + .4) * h}V${y + (c + .6) * h}`)]);
    if (glyph === 'product')
        return [p(`M${cx},${y}L${x + w},${y + h * .25}V${y + h * .75}L${cx},${y + h}L${x},${y + h * .75}V${y + h * .25}Z M${x},${y + h * .25}L${cx},${cy}L${x + w},${y + h * .25} M${cx},${cy}V${y + h}`)];
    if (glyph === 'contract')
        return [(0, graph_glyphs_js_1.box)(b, 'none', color), l(.2, .2, .8, .2), l(.2, .4, .8, .4), (0, graph_glyphs_js_1.oval)({ x: x + w * .45, y: y + h * .6, width: w * .4, height: h * .3 }, 'none', color), l(.15, .8, .4, .6)];
    if (['table', 'sample', 'dataset', 'record', 'field', 'widecolumn', 'fact', 'dimension', 'bridge'].includes(glyph))
        return [(0, graph_glyphs_js_1.box)(b, 'none', color, 1.3), l(0, .3, 1, .3), l(.32, 0, .32, 1), l(0, .65, 1, .65), ...(glyph === 'dimension' ? [l(.65, 0, .65, 1)] : [])];
    if (['database', 'service', 'registry', 'keyspace'].includes(glyph))
        return [p(`M${x},${y + h * .2}V${y + h * .8}C${x},${y + h * 1.06} ${x + w},${y + h * 1.06} ${x + w},${y + h * .8}V${y + h * .2}`), (0, graph_glyphs_js_1.oval)({ x, y, width: w, height: h * .4 }, 'none', color, 1.3)];
    if (['book', 'catalog', 'semantic'].includes(glyph))
        return [p(`M${cx},${y + h * .15}Q${x + w * .25},${y - h * .05} ${x},${y + h * .1}V${y + h * .9}Q${x + w * .25},${y + h * .75} ${cx},${y + h}Q${x + w * .75},${y + h * .75} ${x + w},${y + h * .9}V${y + h * .1}Q${x + w * .75},${y - h * .05} ${cx},${y + h * .15}V${y + h}`)];
    if (['gear', 'pipeline', 'job', 'test', 'hand'].includes(glyph)) {
        const points = Array.from({ length: 24 }, (_, i) => { const a = i * Math.PI / 12, r = i % 3 === 0 ? .5 : .38; return `${cx + Math.cos(a) * w * r},${cy + Math.sin(a) * h * r}`; });
        return [p('M' + points.join('L') + 'Z'), (0, graph_glyphs_js_1.oval)({ x: x + w * .33, y: y + h * .33, width: w * .34, height: h * .34 }, 'none', color)];
    }
    if (['history', 'clock', 'timeseries', 'schedule', 'calendar', 'recovery'].includes(glyph))
        return [(0, graph_glyphs_js_1.oval)(b, 'none', color), l(.5, .18, .5, .5), l(.5, .5, .78, .62)];
    if (['key', 'identity'].includes(glyph))
        return [(0, graph_glyphs_js_1.oval)({ x, y, width: w * .45, height: h * .45 }, 'none', color), l(.38, .38, 1, 1), l(.65, .65, .8, .5), l(.8, .8, .95, .65)];
    if (['concept', 'domain', 'type', 'sql_domain', 'variant', 'binding'].includes(glyph))
        return [p(`M${cx},${y}L${x + w},${cy}L${cx},${y + h}L${x},${cy}Z`), ...(glyph === 'binding' ? [l(0, .65, 1, .65)] : [(0, graph_glyphs_js_1.oval)({ x: x + w * .34, y: y + h * .34, width: w * .32, height: h * .32 }, 'none', color, 1)])];
    if (['note', 'document', 'file', 'manifest', 'report', 'policy'].includes(glyph))
        return [p(`M${x},${y}H${x + w * .65}L${x + w},${y + h * .32}V${y + h}H${x}Z M${x + w * .65},${y}V${y + h * .32}H${x + w}`), l(.2, .55, .8, .55), l(.2, .75, .7, .75)];
    if (['folder', 'schema', 'package', 'context', 'workspace'].includes(glyph))
        return [p(`M${x},${y + h * .22}V${y}H${cx}L${x + w * .65},${y + h * .22}H${x + w}V${y + h}H${x}Z`)];
    if (['check', 'constraint'].includes(glyph))
        return [l(.05, .5, .35, .85), l(.35, .85, .95, .1)];
    if (['eye', 'materialized', 'search', 'query'].includes(glyph))
        return glyph === 'search' ? [(0, graph_glyphs_js_1.oval)({ x, y, width: w * .7, height: h * .7 }, 'none', color), l(.6, .6, 1, 1)] : [p(`M${x},${cy}Q${cx},${y - h * .3} ${x + w},${cy}Q${cx},${y + h * 1.3} ${x},${cy}Z`), (0, graph_glyphs_js_1.oval)({ x: x + w * .35, y: y + h * .35, width: w * .3, height: h * .3 }, 'none', color)];
    if (['topic', 'queue', 'publish', 'subscribe', 'consumers'].includes(glyph))
        return [l(.2, 0, .2, 1), l(.4, .25, 1, .25), l(.4, .5, 1, .5), l(.4, .75, 1, .75), (0, graph_glyphs_js_1.oval)({ x: x - w * .04, y: y + h * .4, width: w * .2, height: h * .2 }, 'none', color)];
    if (['message', 'command', 'interface', 'endpoint', 'port', 'application'].includes(glyph))
        return [(0, graph_glyphs_js_1.box)(b, 'none', color), l(0, .25, 1, .25), ...(glyph === 'message' ? [l(0, .25, .5, .65), l(.5, .65, 1, .25)] : [l(.2, .55, .4, .7), l(.4, .7, .2, .85), l(.55, .8, .85, .8)])];
    if (['node', 'graph', 'edge', 'rdf', 'tensor', 'federation'].includes(glyph))
        return [l(.2, .2, .8, .3), l(.8, .3, .5, .85), l(.5, .85, .2, .2), ...[[.2, .2], [.8, .3], [.5, .85]].map(([a, c]) => (0, graph_glyphs_js_1.oval)({ x: x + a * w - 2, y: y + c * h - 2, width: 4, height: 4 }, color, color))];
    if (['chart', 'vector', 'metric', 'model', 'dashboard'].includes(glyph))
        return [l(0, 0, 0, 1), l(0, 1, 1, 1), p(`M${x + w * .15},${y + h * .75}L${x + w * .4},${y + h * .4}L${x + w * .65},${y + h * .6}L${x + w * .95},${y + h * .1}`)];
    if (['cloud', 'bucket'].includes(glyph))
        return [p(`M${x + w * .2},${y + h * .85}C${x - w * .2},${y + h * .8} ${x},${y + h * .3} ${x + w * .25},${y + h * .4}C${x + w * .2},${y - h * .1} ${x + w * .85},${y - h * .1} ${x + w * .8},${y + h * .4}C${x + w * 1.15},${y + h * .25} ${x + w * 1.25},${y + h * .9} ${x + w * .8},${y + h * .85}Z`)];
    if (['bolt', 'trigger'].includes(glyph))
        return [p(`M${x + w * .6},${y}L${x},${y + h * .6}H${x + w * .45}L${x + w * .3},${y + h}L${x + w},${y + h * .4}H${cx}Z`)];
    if (['list', 'array', 'set', 'collection', 'files', 'shard', 'replica'].includes(glyph))
        return [(0, graph_glyphs_js_1.box)({ x, y, width: w * .8, height: h * .8 }, 'none', color), p(`M${x + w * .2},${y + h * .85}V${y + h}H${x + w}V${y + h * .2}`), l(.15, .25, .65, .25), l(.15, .5, .65, .5)];
    if (['link', 'alias', 'plug', 'connector'].includes(glyph))
        return [(0, graph_glyphs_js_1.oval)({ x, y: y + h * .1, width: w * .65, height: h * .5 }, 'none', color), (0, graph_glyphs_js_1.oval)({ x: x + w * .35, y: y + h * .4, width: w * .65, height: h * .5 }, 'none', color)];
    if (['function', 'procedure', 'operator'].includes(glyph))
        return [(0, graph_glyphs_js_1.label)(glyph === 'function' ? 'ƒ' : glyph === 'operator' ? '±' : '≡', cx, y + h * .85, h, color, { 'text-anchor': 'middle', 'font-weight': 600 })];
    return [(0, graph_glyphs_js_1.box)(b, 'none', color, 1.4)];
}
function nativeContour(role, record, b, fill, stroke, weight, look, roughness, seed) {
    const descriptor = (0, core_js_1.roleDescriptor)(role)?.render, shape = (0, model_js_1.str)(descriptor?.shape, 'card'), out = [];
    if (look === 'neo')
        out.push((0, graph_glyphs_js_1.box)({ ...b, x: b.x + 4, y: b.y + 5 }, '#00000020', 'none', 0));
    if (['external_actor', 'uml.actor'].includes(role)) {
        const cx = b.x + b.width / 2, y = b.y + 8, h = Math.max(65, b.height - 44);
        return [(0, graph_glyphs_js_1.oval)({ x: cx - 12, y, width: 24, height: 24 }, fill, stroke, weight), (0, graph_glyphs_js_1.line)([cx, y + 24], [cx, y + h * .68], stroke, weight), (0, graph_glyphs_js_1.line)([cx - 25, y + h * .4], [cx + 25, y + h * .4], stroke, weight), (0, graph_glyphs_js_1.line)([cx, y + h * .68], [cx - 25, y + h], stroke, weight), (0, graph_glyphs_js_1.line)([cx, y + h * .68], [cx + 25, y + h], stroke, weight)];
    }
    if ((role.startsWith('flow.') || role.startsWith('state.') || role.startsWith('uml.') || role.startsWith('dfd.')) && !(role === 'flow.process' && look === 'handdrawn'))
        return [...out, ...(0, graph_glyphs_js_1.nodeGlyph)(role, record, b, { title: '', profile: 'flow.basic@1', fill, stroke, width: weight })];
    if (look === 'handdrawn') {
        let state = seed >>> 0;
        const rnd = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return (state / 4294967296 - .5) * roughness * 3; };
        const points = [[b.x, b.y], [b.x + b.width, b.y], [b.x + b.width, b.y + b.height], [b.x, b.y + b.height], [b.x, b.y]].map(([x, y]) => `${x + rnd()},${y + rnd()}`);
        out.push((0, graph_glyphs_js_1.path)('M' + points.join('L') + 'Z', fill, stroke, weight));
        for (let d = 12; d < b.width + b.height; d += 12) {
            const start = [b.x + Math.max(0, d - b.height), b.y + Math.min(d, b.height)], end = [b.x + Math.min(d, b.width), b.y + Math.max(0, d - b.width)];
            out.push({ kind: 'path', d: `M${start[0]},${start[1]}L${end[0]},${end[1]}`, paint: { fill: 'none', stroke, 'stroke-width': .5, opacity: .1 } });
        }
    }
    else if (shape === 'activity')
        out.push((0, graph_glyphs_js_1.rounded)(b, fill, stroke, 12, weight));
    else if (shape === 'note')
        out.push((0, graph_glyphs_js_1.path)(`M${b.x},${b.y}H${b.x + b.width - 16}L${b.x + b.width},${b.y + 16}V${b.y + b.height}H${b.x}Z M${b.x + b.width - 16},${b.y}V${b.y + 16}H${b.x + b.width}`, fill, stroke, weight));
    else
        out.push((0, graph_glyphs_js_1.rounded)(b, fill, stroke, shape === 'card' ? 5 : 0, weight));
    if (shape === 'frame')
        out.push((0, graph_glyphs_js_1.box)({ x: b.x + 5, y: b.y + 5, width: b.width - 10, height: b.height - 10 }, 'none', stroke, .7, '2 2'));
    return out;
}
const badgeNames = { AUTH: 'AUTHORITATIVE', DER: 'DERIVED', BT: 'BITEMPORAL', EVH: 'EVENT HISTORY', VT: 'VALID TIME', RT: 'RECORDED TIME', CACHE: 'CACHE', PITR: 'PITR' };
function nativeBadges(record, appearance, view) {
    const facets = (0, model_js_1.object)(record.facets), result = [];
    for (const [group, values] of Object.entries(facets))
        if ((group === 'maturity' ? (0, model_js_1.pathValue)(view, 'display.maturity') : (0, model_js_1.pathValue)(view, 'display.badges')) !== 'none')
            result.push(...(0, model_js_1.array)(values).map(v => badgeNames[(0, model_js_1.str)(v)] ?? (0, model_js_1.str)(v)));
    result.push(...(0, model_js_1.array)(appearance?.marks).map(String));
    const distribution = (0, model_js_1.pathValue)(record, 'properties.distribution');
    if (distribution && (0, model_js_1.pathValue)(view, 'display.badges') !== 'none')
        result.push(String(distribution).toUpperCase());
    return [...new Set(result)];
}
function badgePrimitives(values, b, size, color, fill) {
    let x = b.x + 12;
    const result = [];
    for (const value of values) {
        const w = value.length * size * .6 + 10;
        result.push((0, graph_glyphs_js_1.rounded)({ x, y: b.y + b.height - 22, width: w, height: 16 }, fill, color, 3, .7), (0, graph_glyphs_js_1.label)(value, x + 5, b.y + b.height - 10, size, color, { 'font-weight': 600 }));
        x += w + 6;
    }
    return result;
}
function originRank(origin, level) {
    if (!origin || origin.startsWith('standard:'))
        return 0;
    if (origin === 'css:workarea')
        return 1;
    if (origin === 'css:view')
        return 2;
    if (origin === 'css:element')
        return 3;
    if (origin === 'css')
        return level === 'workarea' ? 1 : level === 'view' ? 2 : 3;
    if (origin === 'file:defaults')
        return 4;
    if (origin === 'file:workarea defaults')
        return 5;
    if (origin === 'file:workarea' || level === 'workarea')
        return 6;
    if (origin === 'file:view defaults')
        return 7;
    if (origin === 'file:view' || level === 'view')
        return 8;
    if (origin === 'file:definition defaults')
        return 9;
    if (origin === 'file:definition')
        return 10;
    if (origin === 'file:occurrence')
        return 11;
    return 10;
}
const INHERITABLE_STYLE_KEYS = ['look', 'font', 'font_size', 'seed', 'roughness', 'theme', 'hachure'];
function inheritedPresentation(values, properties, view, viewOrigins, targetOrigins, level = 'element') {
    const result = { ...values };
    const parentLevel = level === 'view' ? 'workarea' : 'view';
    const groups = level === 'view' ? ['style', 'text', 'border'] : ['style', 'text'];
    for (const group of groups) {
        const next = { ...(0, model_js_1.object)(values[group]) };
        for (const [key, value] of Object.entries((0, model_js_1.object)(view[group]))) {
            if (group === 'style' && !INHERITABLE_STYLE_KEYS.includes(key))
                continue;
            const path = group + '.' + key;
            const origin = targetOrigins?.[path] ?? properties.find(p => p.path === path)?.origin;
            const parentOrigin = viewOrigins ? viewOrigins[path] : 'file:view';
            if (originRank(parentOrigin, parentLevel) > originRank(origin, level)) {
                next[key] = value;
                if (targetOrigins) {
                    const inheritedOrigin = !parentOrigin || parentOrigin.startsWith('standard:')
                        ? origin ?? ('standard:' + level)
                        : parentOrigin.startsWith('css')
                            ? (parentOrigin === 'css:workarea' || parentLevel === 'workarea' ? 'css:workarea' : 'css:view')
                            : (parentOrigin === 'file:workarea' || parentLevel === 'workarea' ? 'file:workarea' : 'file:view');
                    targetOrigins[path] = inheritedOrigin;
                }
            }
        }
        result[group] = next;
    }
    if (level === 'view' && view.shadow && typeof view.shadow === 'object') {
        const shadowOrigin = targetOrigins?.shadow ?? properties.find(p => p.path === 'shadow' || p.path.startsWith('shadow.'))?.origin;
        const parentShadowOrigin = viewOrigins?.shadow ?? Object.entries(viewOrigins ?? {}).find(([k]) => k.startsWith('shadow.'))?.[1];
        if (originRank(parentShadowOrigin, 'workarea') > originRank(shadowOrigin, 'view')) {
            result.shadow = { ...(0, model_js_1.object)(view.shadow) };
            if (targetOrigins && parentShadowOrigin)
                targetOrigins.shadow = parentShadowOrigin.startsWith('css') ? 'css:workarea' : 'file:workarea';
        }
    }
    return result;
}

},
"presentation/src/native.js":function(module,exports,require){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
__exportStar(require("presentation/src/model.js"), exports);
__exportStar(require("presentation/src/table.js"), exports);
__exportStar(require("presentation/src/markdown.js"), exports);
__exportStar(require("presentation/src/project-core.js"), exports);
__exportStar(require("presentation/src/records.js"), exports);
__exportStar(require("presentation/src/publication.js"), exports);
__exportStar(require("presentation/src/adapters.js"), exports);
__exportStar(require("presentation/src/relation-presentation.js"), exports);

},
"presentation/src/project-core.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.inheritedPresentation = exports.availableProjectionProfiles = void 0;
exports.unionBounds = unionBounds;
exports.projectSnapshot = projectSnapshot;
const card_text_js_1 = require("presentation/src/card-text.js");
const view_surface_js_1 = require("presentation/src/view-surface.js");
const model_js_1 = require("presentation/src/model.js");
const table_js_1 = require("presentation/src/table.js");
const symbol_presentation_js_1 = require("presentation/src/symbol-presentation.js");
const records_js_1 = require("presentation/src/records.js");
const graph_native_js_1 = require("presentation/src/graph-native.js");
const adapters_js_1 = require("presentation/src/adapters.js");
var adapters_js_2 = require("presentation/src/adapters.js");
Object.defineProperty(exports, "availableProjectionProfiles", { enumerable: true, get: function () { return adapters_js_2.availableProjectionProfiles; } });
const core_js_1 = require("profiles/src/core.js");
const mindmap_js_1 = require("profiles/src/mindmap.js");
const graph_isometric_js_1 = require("presentation/src/graph-isometric.js");
const stationery_js_1 = require("presentation/src/stationery.js");
const native_render_js_1 = require("presentation/src/native-render.js");
var native_render_js_2 = require("presentation/src/native-render.js");
Object.defineProperty(exports, "inheritedPresentation", { enumerable: true, get: function () { return native_render_js_2.inheritedPresentation; } });
const publication_js_1 = require("presentation/src/publication.js");
const relation_presentation_js_1 = require("presentation/src/relation-presentation.js");
const graph_common_js_1 = require("presentation/src/graph-common.js");
const identity = [1, 0, 0, 1, 0, 0];
function unionBounds(items) {
    if (!items.length)
        return { x: 0, y: 0, width: 640, height: 480 };
    const x = Math.min(...items.map(i => i.x)), y = Math.min(...items.map(i => i.y));
    return { x, y, width: Math.max(1, Math.max(...items.map(i => i.x + i.width)) - x), height: Math.max(1, Math.max(...items.map(i => i.y + i.height)) - y) };
}
function intersectBounds(a, b) {
    const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y);
    return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) };
}
const rect = (bounds, fill, stroke, width = 1) => ({ kind: 'rect', bounds, paint: { fill, stroke, 'stroke-width': width } });
const text = (value, x, y, size, color, extra = {}, font = 'sans') => ({ kind: 'text', runs: [{ text: value, x, y, fontKey: font, style: { 'font-size': size, fill: color, ...extra } }] });
function sketch(bounds, fill, stroke, seed, roughness) { let state = seed >>> 0; const random = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return (state / 4294967296 - .5) * Math.max(0, roughness) * 2; }; const { x, y, width: w, height: h } = bounds; const points = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]].map(([px, py]) => `${px + random()},${py + random()}`); return { kind: 'path', d: 'M' + points.join('L') + 'Z', paint: { fill, stroke, 'stroke-width': 1.2, 'stroke-linejoin': 'round' } }; }
function merge(a, b) {
    const result = { ...a };
    for (const [key, value] of Object.entries(b))
        result[key] = value && typeof value === 'object' && !Array.isArray(value) ? merge((0, model_js_1.object)(a[key]), (0, model_js_1.object)(value)) : value;
    return result;
}
function withPreview(values, preview) {
    const copy = merge({}, values);
    for (const [path, value] of Object.entries(preview ?? {})) {
        const parts = path.split('.');
        let current = copy;
        for (const part of parts.slice(0, -1)) {
            current[part] = { ...(0, model_js_1.object)(current[part]) };
            current = (0, model_js_1.object)(current[part]);
        }
        current[parts.at(-1) ?? path] = value;
    }
    return copy;
}
function mindmapLocations(nodes, all) {
    const ids = new Set(nodes.map(node => (0, model_js_1.refKey)(node.ref))), children = new Map(), parents = new Set();
    for (const relation of all.filter(record => record.record.category === 'relation')) {
        const endpoints = (0, model_js_1.array)(relation.record.endpoints).map(endpoint => (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(endpoint).definition, relation.file));
        if (endpoints.length !== 2 || !endpoints[0] || !endpoints[1])
            continue;
        const from = (0, model_js_1.refKey)(endpoints[0].ref), to = (0, model_js_1.refKey)(endpoints[1].ref);
        if (!ids.has(from) || !ids.has(to) || from === to)
            continue;
        const next = children.get(from) ?? [];
        if (!next.includes(to))
            next.push(to);
        children.set(from, next);
        parents.add(to);
    }
    const root = nodes.find(node => !parents.has((0, model_js_1.refKey)(node.ref))) ?? nodes[0];
    if (!root)
        return new Map();
    const rootId = (0, model_js_1.refKey)(root.ref), positions = new Map(), seen = new Set([rootId]);
    const branches = children.get(rootId) ?? [];
    let maxLeftDepth = 0;
    const counts = [0, 0];
    const visit = (id, depth, side) => {
        if (seen.has(id))
            return Math.max(0, counts[side] - 1) * 170;
        seen.add(id);
        if (side === 0)
            maxLeftDepth = Math.max(maxLeftDepth, depth);
        const nested = (children.get(id) ?? []).filter(child => !seen.has(child));
        const ys = nested.map(child => visit(child, depth + 1, side));
        const y = ys.length ? (Math.min(...ys) + Math.max(...ys)) / 2 : counts[side]++ * 170;
        positions.set(id, { x: (side === 0 ? -1 : 1) * depth * 310, y });
        return y;
    };
    for (const [index, branch] of branches.entries())
        visit(branch, 1, index % 2);
    const rootY = Math.max(0, Math.max(...counts) - 1) * 85;
    const rootX = 32 + maxLeftDepth * 310;
    positions.set(rootId, { x: rootX, y: 64 + rootY });
    for (const [id, position] of positions)
        if (id !== rootId) {
            const side = position.x < 0 ? 0 : 1;
            positions.set(id, { x: rootX + position.x, y: 64 + position.y + rootY - Math.max(0, counts[side] - 1) * 85 });
        }
    return positions;
}
function recordTablePrimitives(columns, rows, x, y, width, effective, measure) {
    const size = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.font_size'), 16), font = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'style.font'), 'sans'), color = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'text.color'), '#1f2933');
    const header = (0, model_js_1.pathValue)(effective, 'table.header') !== false;
    const table = (0, table_js_1.layoutTable)(columns, rows, width, value => measure(value, size, font), { header, minChars: (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'table.min_chars'), 1), maxLines: (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'table.max_lines'), 6), lineHeight: size * 1.3 });
    const primitives = [];
    if (!table.fits)
        return { primitives: [rect({ x, y, width: 24, height: 24 }, '#9ca3af', '#4b5563'), text('Table cannot fit', x + 32, y + 18, size, color)], height: 32 };
    let top = y;
    for (const [rowIndex, row] of table.rows.entries()) {
        let left = x;
        for (const [index, cell] of row.cells.entries()) {
            const width = table.widths[index] ?? 0, alignment = columns[index]?.alignment ?? 'lt';
            primitives.push(rect({ x: left, y: top, width, height: row.height }, header && rowIndex === 0 ? '#eef2f6' : rowIndex % 2 ? '#ffffff' : '#f5f7fb', '#cbd5e1', .6));
            const tx = alignment[0] === 'r' ? left + width - 8 : alignment[0] === 'c' ? left + width / 2 : left + 8;
            const anchor = alignment[0] === 'r' ? 'end' : alignment[0] === 'c' ? 'middle' : 'start';
            const offset = alignment[1] === 'b' ? row.height - cell.lines.length * size * 1.3 - 4 : alignment[1] === 'm' ? (row.height - cell.lines.length * size * 1.3) / 2 : 4;
            for (const [lineIndex, line] of cell.lines.entries())
                primitives.push(text(line, tx, top + offset + size + lineIndex * size * 1.3, size, color, { 'text-anchor': anchor, ...(header && rowIndex === 0 ? { 'font-weight': 600 } : {}) }, font));
            left += width;
        }
        top += row.height;
    }
    const caption = (0, symbol_presentation_js_1.notePrimitives)('Source-bound table · no expression or decision-rule execution is implied.', x + 8, y + table.height + 22, width - 16, 11, color, value => measure(value, 11, font), false, 4, font);
    primitives.push(...caption.primitives);
    return { primitives, height: table.height + caption.height + 26 };
}
function projectSnapshot(snapshot, options) {
    const all = (0, model_js_1.records)(snapshot), views = all.filter(r => r.owner === 'view' && (!options.onlyView || (0, model_js_1.refKey)(r.ref) === (0, model_js_1.refKey)(options.onlyView)) && (!options.profiles || options.profiles.includes((0, model_js_1.str)(r.record.profile))));
    const entries = [];
    const diagnostics = [];
    const unavailable = [];
    const measure = options.measure ?? ((s, size) => s.length * size * .58);
    const workarea = all.find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
    const wr = workarea ? options.resolve(workarea.ref) : undefined;
    if (wr)
        diagnostics.push(...wr.diagnostics);
    const workareaOrigins = Object.fromEntries((wr?.properties ?? []).map(p => [p.path, p.origin]));
    let nextViewX = 0, nextViewY = 0, rowBottom = 0;
    for (const [viewIndex, view] of views.entries()) {
        const vr = options.resolve(view.ref);
        diagnostics.push(...vr.diagnostics);
        const profile = (0, model_js_1.str)(view.record.profile);
        const placement = all.find(r => r.owner === 'placement' && (0, model_js_1.resolveRecord)(all, r.record.target, r.file)?.ref.id === view.ref.id && (0, model_js_1.resolveRecord)(all, r.record.target, r.file)?.file === view.file);
        const pr = placement ? options.resolve(placement.ref) : undefined;
        const pv = pr?.values ?? {};
        const placedPaper = Object.fromEntries((pr?.properties ?? []).filter(p => (p.path === 'style.paper' || p.path === 'background.color' || p.path === 'background.texture' || p.path.startsWith('background.texture.') || p.path === 'decorations' || p.path === 'shadow' || p.path.startsWith('shadow.')) &&
            (p.origin.startsWith('file:') || p.origin === 'css' || p.origin === 'standard:paper' && !vr.properties.some(v => v.path === 'background.color' && !v.origin.startsWith('standard:')))).map(p => [p.path, p.value]));
        const viewOrigins = Object.fromEntries(vr.properties.map(p => [p.path, p.origin]));
        const cascadedView = wr ? (0, native_render_js_1.inheritedPresentation)(vr.values, vr.properties, wr.values, workareaOrigins, viewOrigins, 'view') : vr.values;
        const effectiveView = withPreview(withPreview(cascadedView, placedPaper), options.preview);
        const surface = (0, view_surface_js_1.fixedViewSurface)(effectiveView);
        const vp = (0, model_js_1.object)(pv.position);
        const vs = (0, model_js_1.object)(pv.size);
        const fixedWidth = typeof (0, model_js_1.pathValue)(placement?.record, 'size.width') === 'number' || pr?.properties.some(p => p.path === 'size.width' && !p.origin.startsWith('standard:'));
        const fixedHeight = typeof (0, model_js_1.pathValue)(placement?.record, 'size.height') === 'number' || pr?.properties.some(p => p.path === 'size.height' && !p.origin.startsWith('standard:'));
        const viewX = (0, model_js_1.num)(vp.x, nextViewX), viewY = (0, model_js_1.num)(vp.y, nextViewY);
        let viewWidth = surface ? surface.width / surface.scale : (0, model_js_1.num)(vs.width, 960), viewHeight = surface ? surface.height / surface.scale : (0, model_js_1.num)(vs.height, 680);
        const title = (0, model_js_1.titleOf)(view.record);
        const viewPrimitives = [];
        const firstEntry = entries.length;
        const supported = adapters_js_1.availableProjectionProfiles.has(profile) && (options.supports?.(profile) ?? true);
        const isDocument = view.record.kind === 'document' || !!view.record.publication && profile === '';
        const appearances = all.filter(r => r.owner === 'appearance' && (0, model_js_1.resolveRecord)(all, r.record.parent, r.file)?.ref.id === view.ref.id && (0, model_js_1.resolveRecord)(all, r.record.parent, r.file)?.file === view.file);
        const excluded = new Set((0, model_js_1.array)((0, model_js_1.pathValue)(view.record, 'selection.exclude')).map(ref => (0, model_js_1.resolveRecord)(all, ref, view.file)).filter((record) => !!record).map(record => (0, model_js_1.refKey)(record.ref)));
        const selected = (0, model_js_1.array)((0, model_js_1.pathValue)(view.record, 'selection.include')).map(r => (0, model_js_1.resolveRecord)(all, r, view.file)).filter((v) => !!v && !excluded.has((0, model_js_1.refKey)(v.ref)));
        const candidates = [];
        for (const definition of selected) {
            const occurrences = appearances.filter(a => (0, model_js_1.refKey)((0, model_js_1.resolveRecord)(all, a.record.target, a.file)?.ref ?? { file: '', id: '' }) === (0, model_js_1.refKey)(definition.ref));
            if (occurrences.length)
                candidates.push(...occurrences.map(appearance => ({ definition, appearance })));
            else
                candidates.push({ definition, appearance: undefined });
        }
        for (const appearance of appearances) {
            const definition = (0, model_js_1.resolveRecord)(all, appearance.record.target, appearance.file);
            if (definition && !excluded.has((0, model_js_1.refKey)(definition.ref)) && !candidates.some(c => c.appearance === appearance))
                candidates.push({ definition, appearance });
        }
        const selectedDefinitionKeys = new Set(candidates.filter(candidate => candidate.definition).map(candidate => (0, model_js_1.refKey)(candidate.definition.ref)));
        const mindmapTopicKeys = new Set(candidates.filter(candidate => candidate.definition && (0, mindmap_js_1.isMindmapTopic)(candidate.definition.record)).map(candidate => (0, mindmap_js_1.mindmapKey)(candidate.definition)));
        if (profile === 'mindmap.basic@1')
            for (const candidate of [...candidates]) {
                const relation = candidate.definition;
                if (relation?.record.category !== 'relation')
                    continue;
                const ends = (0, model_js_1.array)(relation.record.endpoints).map(end => (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).definition, relation.file));
                if ((0, mindmap_js_1.mindmapRelationKind)(ends[0], ends[1], mindmapTopicKeys) !== 'external')
                    continue;
                for (const definition of ends)
                    if (definition && !excluded.has((0, model_js_1.refKey)(definition.ref)) && !candidates.some(item => item.definition && (0, model_js_1.refKey)(item.definition.ref) === (0, model_js_1.refKey)(definition.ref)))
                        candidates.push({ definition, appearance: undefined });
            }
        const positioned = [];
        const relations = [];
        if (!supported && !isDocument) {
            unavailable.push(`profile:${profile}`);
            diagnostics.push({ code: 'profile-unavailable', severity: 'warning', message: `No installed projection for ${profile}.`, target: view.ref });
            viewPrimitives.push(text(`Unsupported profile: ${profile}`, viewX + 20, viewY + 70, 16, '#8a4b08'));
        }
        else if (profile === 'table.records@1') {
            const data = (0, records_js_1.recordTableData)(snapshot, view);
            diagnostics.push(...data.diagnostics);
            if (data.diagnostics.length)
                unavailable.push('table:' + (0, model_js_1.refKey)(view.ref));
            const settings = (0, model_js_1.object)((0, model_js_1.pathValue)(view.record, 'projection.options'));
            const width = (0, model_js_1.num)(settings.width, Math.max(32, viewWidth - 64));
            const effective = withPreview(effectiveView, options.preview);
            const table = recordTablePrimitives(data.columns, data.rows, viewX + 32, viewY + 58, width, effective, measure);
            const bounds = { x: viewX + 32, y: viewY + 58, width, height: table.height };
            const occurrence = 'records:' + (0, model_js_1.refKey)(view.ref);
            const item = { occurrence, target: view.ref, view: view.ref, layer: 'content', bounds, transform: identity, primitives: table.primitives, hitTargets: [{ id: occurrence, target: view.ref, bounds }], accessible: { role: 'graphics-object', label: title + ' table', description: `${data.rows.length} records, ${data.columns.length} columns` }, evidence: data.diagnostics.length ? 'partial' : 'current' };
            entries.push({ item, definition: view, view, ...(placement ? { placement } : {}), effective });
            viewWidth = Math.max(viewWidth, width + 64);
            viewHeight = Math.max(fixedHeight ? viewHeight : 0, table.height + 90);
        }
        else if ((0, adapters_js_1.isDataProfile)(profile)) {
            const projected = (0, adapters_js_1.dataProjector)(profile)(snapshot, view, { x: viewX + 32, y: viewY + 58, width: viewWidth - 64, height: viewHeight - 90 }, effectiveView, {
                resolve: options.resolve, measure, ...(options.geography ? { geography: options.geography } : {}),
                projectChild(child, destination) {
                    const path = [...(options.inclusionPath ?? []), (0, model_js_1.refKey)(view.ref)];
                    if (path.includes((0, model_js_1.refKey)(child.ref)) || (options.panelDepth ?? 0) >= 1)
                        return {
                            entries: [], bounds: destination, unavailable: ['panel-inclusion:' + (0, model_js_1.refKey)(child.ref)],
                            diagnostics: [{ code: 'panel-inclusion-depth', severity: 'error', message: 'Composed panels permit one child-view level without cycles.', target: child.ref }],
                        };
                    const { profiles: _profiles, ...childOptions } = options;
                    const projected = projectSnapshot(snapshot, { ...childOptions, onlyView: child.ref, inclusionPath: path, panelDepth: (options.panelDepth ?? 0) + 1, deferOpacity: true });
                    const scale = 1;
                    const tx = destination.x - projected.bounds.x;
                    const ty = destination.y - projected.bounds.y;
                    const childBounds = { ...projected.bounds, x: destination.x, y: destination.y };
                    const bounds = (b) => ({ x: b.x * scale + tx, y: b.y * scale + ty, width: b.width * scale, height: b.height * scale });
                    const entries = projected.entries.map(entry => {
                        const m = entry.item.transform;
                        return { ...entry, item: { ...entry.item, view: view.ref, occurrence: 'panel:' + (0, model_js_1.refKey)(view.ref) + ':' + entry.item.occurrence,
                                bounds: bounds(entry.item.bounds), clip: entry.item.clip ? intersectBounds(childBounds, bounds(entry.item.clip)) : childBounds,
                                hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: bounds(hit.bounds) })),
                                transform: [m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4] * scale + tx, m[5] * scale + ty],
                            } };
                    });
                    return { entries, bounds: childBounds, diagnostics: [...projected.diagnostics], unavailable: [...projected.coverage.unavailable] };
                },
            });
            if (projected) {
                entries.push(...projected.entries);
                diagnostics.push(...projected.diagnostics);
                unavailable.push(...projected.unavailable);
                viewWidth = Math.max(fixedWidth ? viewWidth : 0, projected.bounds.x + projected.bounds.width - viewX + 32);
                viewHeight = Math.max(fixedHeight ? viewHeight : 0, projected.bounds.y + projected.bounds.height - viewY + 32);
            }
        }
        else {
            let nodeIndex = 0;
            const mindmap = profile === 'mindmap.basic@1' ? mindmapLocations(candidates.map(candidate => candidate.definition).filter((record) => !!record && record.record.category !== 'relation'), all) : new Map();
            for (const candidate of candidates) {
                const definition = candidate.definition;
                if (!definition)
                    continue;
                if (definition.record.category === 'relation') {
                    relations.push(candidate);
                    continue;
                }
                const appearance = candidate.appearance;
                const resolved = options.resolve(definition.ref, { view: view.ref, ...(appearance ? { appearance: appearance.ref } : {}) });
                diagnostics.push(...resolved.diagnostics);
                const propertyOrigins = Object.fromEntries(resolved.properties.map(p => [p.path, p.origin]));
                let effective = withPreview((0, native_render_js_1.inheritedPresentation)(resolved.values, resolved.properties, effectiveView, viewOrigins, propertyOrigins, 'element'), options.preview);
                let fontSize = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.font_size'), 16);
                const font = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'style.font'), 'sans');
                const color = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'text.color'), '#1f2933');
                const p = (0, model_js_1.object)(effective.position);
                const sz = (0, model_js_1.object)(effective.size);
                const layout = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'layout.algorithm'));
                const col = nodeIndex % 3, row = Math.floor(nodeIndex / 3);
                const automatic = mindmap.get((0, model_js_1.refKey)(definition.ref));
                const x = viewX + (0, model_js_1.num)(p.x, automatic?.x ?? (layout === 'mindmap' ? (nodeIndex === 0 ? viewWidth / 2 - 140 : nodeIndex % 2 ? 40 : viewWidth - 320) : 32 + col * 300));
                const y = viewY + (0, model_js_1.num)(p.y, automatic?.y ?? (layout === 'mindmap' ? (nodeIndex === 0 ? viewHeight / 2 - 50 : 65 + Math.floor((nodeIndex - 1) / 2) * 170) : 64 + row * 220));
                const standalone = (0, symbol_presentation_js_1.standaloneNode)({ definition, ...(appearance ? { appearance } : {}), effective, origins: propertyOrigins, all, x, y, measure, ...(options.assetSizes ? { assetSizes: options.assetSizes } : {}) });
                if (standalone) {
                    diagnostics.push(...standalone.diagnostics);
                    unavailable.push(...standalone.unavailable);
                    const occurrence = appearance?.ref.id ?? `${(0, model_js_1.refKey)(view.ref)}:${(0, model_js_1.refKey)(definition.ref)}`, status = (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'design.state'), 'draft');
                    const item = { occurrence, target: definition.ref, view: view.ref, layer: (0, model_js_1.str)(effective.layer, 'content'), bounds: standalone.bounds, transform: identity, primitives: standalone.primitives, hitTargets: [{ id: occurrence, target: definition.ref, bounds: standalone.body }], accessible: { role: 'graphics-symbol', label: (0, model_js_1.str)(appearance?.record.title) || (0, model_js_1.titleOf)(definition.record), description: `${(0, model_js_1.str)(definition.record.role)}; ${status}; standalone ${standalone.presentation.mode}` }, status, evidence: snapshot.coverage.complete && !standalone.unavailable.length ? 'current' : 'partial' };
                    positioned.push({ item, definition, view, ...(appearance ? { appearance } : {}), ...(placement ? { placement } : {}), effective, propertyOrigins, standalone: standalone.presentation, ...(profile === 'mindmap.basic@1' ? { mindmapTopic: mindmapTopicKeys.has((0, mindmap_js_1.mindmapKey)(definition)) } : {}) });
                    nodeIndex++;
                    continue;
                }
                const role = (0, model_js_1.str)(definition.record.role), native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
                const showKind = (0, model_js_1.pathValue)(effectiveView, 'display.kind') !== 'none', roleWidth = native ? (showKind ? Math.min(96, Math.max(30, measure((0, native_render_js_1.nativeCode)(role), 10.5, font))) + 12 : 0) : Math.min(130, Math.max(38, measure(role, 9, 'monospace') + 12));
                let width = (0, model_js_1.num)(sz.width, Math.max(248, Math.min(360, measure((0, model_js_1.titleOf)(definition.record), fontSize, font) + roleWidth + 48)));
                const titleText = (0, model_js_1.str)(appearance?.record.title) || (0, model_js_1.titleOf)(definition.record);
                const primitives = [];
                const explicitBody = propertyOrigins.body ? !propertyOrigins.body.startsWith('standard:') : appearance?.record.body !== undefined || definition.record.body !== undefined;
                const contentText = (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'content.text')) || (0, model_js_1.str)(definition.record.description) || (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'content.meaning'));
                const defaultBody = definition.record.data || (0, model_js_1.array)(definition.record.members).length ? 'columns' : (0, model_js_1.pathValue)(definition.record, 'draft.text') ? 'draft' : contentText ? 'notes' : 'title';
                const body = explicitBody ? (0, model_js_1.str)(effective.body, defaultBody) : defaultBody;
                const fit = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'text.fit'), 'auto'), maxWidth = Math.min((0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'text.max_width'), 4000), (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'max_size.width'), 4000)), maxHeight = Math.min((0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'text.max_height'), 4000), (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'max_size.height'), 4000));
                width = Math.min(maxWidth, Math.max(width, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'min_size.width'), 0)));
                if (fit === 'grow' && sz.width === undefined)
                    width = Math.min(maxWidth, Math.max(width, measure(titleText, fontSize, font) + roleWidth + 48));
                const actor = ['external_actor', 'uml.actor'].includes(role), centred = actor || role.startsWith('flow.') || role.startsWith('state.') || ['uml.usecase', 'dfd.process', 'dfd.store'].includes(role);
                const kindLayout = native && showKind && !centred ? (0, card_text_js_1.cardTextLayout)((0, native_render_js_1.nativeCode)(role), titleText, width, (value, size) => measure(value, size, font), 10.5, fontSize, 14) : undefined;
                const titleWidth = () => kindLayout?.titleWidth ?? Math.max(20, width - roleWidth - 44);
                const titleLimit = () => {
                    const available = Math.min(maxHeight, (0, model_js_1.num)(sz.height, maxHeight)) - (native && showKind ? 38 : 22);
                    return Math.max(1, Math.min(64, Math.floor(available / (fontSize * 1.25))));
                };
                let titleLayout = (0, table_js_1.wrapCell)(titleText, titleWidth(), txt => measure(txt, fontSize, font), titleLimit());
                if (fit === 'shrink')
                    while (titleLayout.truncated && fontSize > (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'text.min_font'), 8)) {
                        fontSize = Math.max((0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'text.min_font'), 8), fontSize - 1);
                        titleLayout = (0, table_js_1.wrapCell)(titleText, titleWidth(), txt => measure(txt, fontSize, font), titleLimit());
                    }
                const titleLines = titleLayout.lines;
                const headerHeight = Math.max(kindLayout ? 48 + kindLayout.typeLines.length * 13 : native && showKind ? 60 : 40, 18 + titleLines.length * fontSize * 1.25);
                let bodyHeight = 0;
                const members = (0, model_js_1.array)(definition.record.members).map(r => (0, model_js_1.resolveRecord)(all, r, definition.file)).filter((r) => !!r);
                if (body === 'columns') {
                    const data = (0, model_js_1.tableData)(snapshot, definition);
                    const visibility = { ...(0, model_js_1.object)(effective.column_visibility), ...(0, model_js_1.object)(definition.record.column_visibility), ...(0, model_js_1.object)(appearance?.record.column_visibility) };
                    const order = (0, model_js_1.array)(effective.columns);
                    const nativeFields = data.columns.some(c => c.id === 'field') && native;
                    const shown = data.columns.map((c, i) => ({ c, i })).filter(({ c }) => visibility[(0, model_js_1.str)(c.id)] === 'shown' || visibility[(0, model_js_1.str)(c.id)] !== 'hidden' && (!nativeFields || (0, model_js_1.str)(c.id) === 'field' || Object.keys(visibility).length > 0 && visibility[(0, model_js_1.str)(c.id)] !== 'on_demand'));
                    const ordered = order.map(c => shown.find(x => x.c.id === (typeof c === 'string' ? c : (0, model_js_1.str)((0, model_js_1.object)(c).id)))).filter((v) => !!v);
                    const picked = [...ordered, ...shown.filter(item => !ordered.includes(item))];
                    const columns = picked.map(({ c }) => c);
                    const rows = data.rows.map((row, ri) => picked.map(({ i, c }) => {
                        const member = members[ri];
                        let value = row[i];
                        if (nativeFields && c.id === 'field' && member) {
                            let depth = 0, parent = (0, model_js_1.resolveRecord)(all, (0, model_js_1.pathValue)(member.record, 'content.parent'), member.file);
                            const seen = new Set();
                            while (parent && parent.record.role === 'field' && !seen.has((0, model_js_1.refKey)(parent.ref))) {
                                seen.add((0, model_js_1.refKey)(parent.ref));
                                depth++;
                                parent = (0, model_js_1.resolveRecord)(all, (0, model_js_1.pathValue)(parent.record, 'content.parent'), parent.file);
                            }
                            const key = (0, model_js_1.pathValue)(member.record, 'content.key') ?? (0, model_js_1.pathValue)(member.record, 'properties.key');
                            const nullable = (0, model_js_1.pathValue)(member.record, 'content.nullable') ?? (0, model_js_1.pathValue)(member.record, 'properties.nullable');
                            const presence = (0, model_js_1.pathValue)(member.record, 'properties.presence');
                            const shape = (0, model_js_1.str)((0, model_js_1.pathValue)(member.record, 'properties.shape')), shapeMark = shape === 'array' ? ' []' : shape === 'object' ? ' {}' : shape === 'variant' ? ' <variant>' : '';
                            value = '  '.repeat(depth) + (depth ? '↳ ' : '') + (key && key !== 'none' ? '⚿ ' : '') + (0, model_js_1.str)(value) + shapeMark + (nullable === true || presence === 'optional' ? ' ?' : nullable === false ? ' !' : '');
                        }
                        if (role === 'sample')
                            value = value === null ? 'null' : (0, model_js_1.object)(value).$missing === true || (0, model_js_1.object)(value).$state === 'missing' ? 'missing' : value;
                        return value;
                    }));
                    width = (0, model_js_1.num)(sz.width, Math.max(width, columns.length * 95, role === 'sample' ? Math.min(1000, columns.length * Math.max(80, ...rows.flatMap(row => row.map(v => measure(String(v ?? ''), fontSize, font) + 18)))) : 0));
                    const header = (0, model_js_1.pathValue)(effective, 'table.header') !== false;
                    const table = (0, table_js_1.layoutTable)(columns, rows, width, txt => measure(txt, fontSize, font), { minChars: (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'table.min_chars'), 1), maxLines: (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'table.max_lines'), 6), header, lineHeight: fontSize * 1.3 });
                    if (!table.fits) {
                        primitives.push(rect({ x: x + 12, y: y + headerHeight + 8, width: 24, height: 24 }, '#9ca3af', '#4b5563'));
                        bodyHeight = 40;
                    }
                    else {
                        let ty = y + headerHeight;
                        for (const [ri, tableRow] of table.rows.entries()) {
                            let tx = x;
                            for (const [ci, cell] of tableRow.cells.entries()) {
                                const cw = table.widths[ci] ?? 0, align = columns[ci]?.alignment ?? 'lt';
                                primitives.push(rect({ x: tx, y: ty, width: cw, height: tableRow.height }, header && ri === 0 ? ['dark', 'night', 'blueprint'].includes((0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.theme'))) ? '#334155' : '#eef2f6' : 'transparent', '#d4dbe3', .6));
                                const txText = align[0] === 'r' ? tx + cw - 8 : align[0] === 'c' ? tx + cw / 2 : tx + 8, anchor = align[0] === 'r' ? 'end' : align[0] === 'c' ? 'middle' : 'start';
                                const vertical = align[1] === 'b' ? tableRow.height - cell.lines.length * fontSize * 1.3 : align[1] === 'm' ? (tableRow.height - cell.lines.length * fontSize * 1.3) / 2 : 4;
                                for (const [li, value] of cell.lines.entries())
                                    primitives.push(text(value, txText, ty + vertical + fontSize + li * fontSize * 1.3, fontSize, color, { 'text-anchor': anchor, ...(header && ri === 0 ? { 'font-weight': 600 } : {}) }, font));
                                tx += cw;
                            }
                            ty += tableRow.height;
                        }
                        bodyHeight = table.height;
                    }
                }
                if (body === 'draft' || body === 'notes' || body === 'columns' && contentText) {
                    const raw = body === 'draft' ? (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'draft.text')) || contentText : contentText || (0, model_js_1.array)(definition.record.notes).filter(n => !(0, model_js_1.str)((0, model_js_1.object)(n).title).startsWith('Additional source')).map(n => (0, model_js_1.str)((0, model_js_1.object)(n).text)).join('\n\n');
                    const bodySize = body === 'draft' ? 13.333 : Math.max(12, fontSize * .82), bodyFont = body === 'draft' ? 'monospace' : font;
                    const maxHeight = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'note.height'), 180), maxLines = Math.max(1, Math.floor(maxHeight / (bodySize * 1.4)));
                    const blocks = (0, symbol_presentation_js_1.notePrimitives)(raw, x + 14, y + headerHeight + bodyHeight + bodySize + 10, width - 28, bodySize, color, txt => measure(txt, bodySize, bodyFont), body !== 'draft' && (0, model_js_1.pathValue)(definition.record, 'content.format') !== 'plain', maxLines, bodyFont);
                    primitives.push(...blocks.primitives);
                    bodyHeight += blocks.height + (raw ? 20 : 0);
                }
                if (role === 'sample' && body === 'columns') {
                    const caption = (0, model_js_1.pathValue)(definition.record, 'properties.mode') === 'synthetic' ? 'Synthetic · illustrative · not a constraint' : 'Sample data';
                    primitives.push(text(caption, x + 12, y + headerHeight + bodyHeight + 16, 10, color));
                    bodyHeight += 24;
                }
                const badges = native ? (0, native_render_js_1.nativeBadges)(definition.record, appearance?.record, effectiveView) : [];
                const naturalHeight = Math.max(actor ? 145 : (0, model_js_1.pathValue)(effective, 'background.image') ? 220 : native ? 100 : 60, headerHeight + bodyHeight + (badges.length ? 28 : 8));
                const height = Math.min(maxHeight, (0, model_js_1.num)(sz.height, Math.max(naturalHeight, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'min_size.height'), 0))));
                const overflow = titleLayout.truncated || headerHeight + bodyHeight + (badges.length ? 28 : 8) > height + 1;
                const bounds = { x, y, width, height }, status = (0, model_js_1.str)((0, model_js_1.pathValue)(definition.record, 'design.state'), 'draft');
                const rendering = (0, core_js_1.roleDescriptor)(role)?.render ?? {};
                const authored = (path) => propertyOrigins[path] && !propertyOrigins[path].startsWith('standard:');
                const background = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'background.color'));
                const themed = ['neutral', 'dark', 'night', 'blueprint'].includes((0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.theme')));
                const fill = authored('background.color') || themed ? background : (0, model_js_1.str)(rendering.fill, background || '#ffffff');
                const symbolColor = authored('symbol.color') || themed ? (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'symbol.color'), '#64748b') : (0, model_js_1.str)(rendering.colour, (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'symbol.color'), '#64748b'));
                const borderWidth = (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'border.width')), outlineWidth = borderWidth > 0 ? borderWidth : (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'symbol.width'), (0, model_js_1.num)(rendering.width, 1.2));
                const border = borderWidth > 0 ? (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'border.color'), symbolColor) : symbolColor;
                const look = (0, model_js_1.str)((0, model_js_1.pathValue)(effective, 'style.look'), (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.look')));
                const outline = native ? (0, native_render_js_1.nativeContour)(role, definition.record, bounds, fill, border, outlineWidth, look, (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.roughness'), 1), (0, model_js_1.num)((0, model_js_1.pathValue)(effective, 'style.seed'), 42) + nodeIndex) : [rect(bounds, fill, border, outlineWidth)];
                const borderStyle = (0, model_js_1.pathValue)(effective, 'border.style');
                if (borderStyle === 'dashed' || borderStyle === 'dotted')
                    for (let i = 0; i < outline.length; i++) {
                        const p = outline[i];
                        if ('paint' in p)
                            outline[i] = { ...p, paint: { ...p.paint, 'stroke-dasharray': borderStyle === 'dashed' ? '6 4' : '2 3' } };
                    }
                primitives.unshift(...outline);
                const imageRef = (0, model_js_1.pathValue)(effective, 'background.image');
                if (imageRef) {
                    const asset = (0, model_js_1.resolveRecord)(all, imageRef, definition.file);
                    if (asset)
                        primitives.splice(outline.length, 0, { kind: 'image', assetId: (0, model_js_1.refKey)(asset.ref), bounds: { x: x + 12, y: y + headerHeight + 6, width: width - 24, height: Math.max(24, height - headerHeight - 16) } });
                }
                if (native && showKind && !centred) {
                    primitives.push(...(0, native_render_js_1.nativeIcon)((0, model_js_1.str)(rendering.glyph, role), { x: x + 14, y: y + 16, width: 20, height: 20 }, symbolColor));
                    for (const [i, code] of (kindLayout?.typeLines ?? [(0, native_render_js_1.nativeCode)(role)]).entries())
                        primitives.push(text(code, x + 14, y + 48 + i * 13, 10.5, symbolColor, { 'font-weight': 700 }, font));
                }
                for (const [i, line] of titleLines.entries())
                    primitives.push(text(line, centred ? x + width / 2 : x + (kindLayout?.titleOffset ?? 14 + roleWidth), centred ? (actor ? y + height - 12 : y + height / 2) + (i - (titleLines.length - 1) / 2) * fontSize * 1.25 : y + 18 + fontSize * .8 + i * fontSize * 1.25, fontSize, color, { 'font-weight': 600, ...(centred ? { 'text-anchor': 'middle' } : {}) }, font));
                primitives.push({ kind: 'ellipse', bounds: { x: x + width - 17, y: y + 9, width: 7, height: 7 }, paint: { fill: status === 'accepted' ? '#15803d' : status === 'in-review' ? '#7c3aed' : status === 'in-progress' ? '#2563eb' : '#d97706', stroke: '#ffffff', 'stroke-width': 1, 'ddn-design-status': status } });
                if (bodyHeight > 0)
                    primitives.push({ kind: 'path', d: `M${x},${y + headerHeight}H${x + width}`, paint: { stroke: border, 'stroke-width': .8, fill: 'none' } });
                primitives.push(...(0, native_render_js_1.badgePrimitives)(badges, bounds, 9, symbolColor, fill));
                const textStyle = {};
                for (const [key, attr] of [['weight', 'font-weight'], ['italic', 'font-style'], ['variant', 'font-variant'], ['decoration', 'text-decoration']]) {
                    const value = (0, model_js_1.pathValue)(effective, 'text.' + key);
                    if (value !== undefined && (authored('text.' + key) || vr.properties.some(p => p.path === 'text.' + key && !p.origin.startsWith('standard:'))))
                        textStyle[attr] = key === 'italic' ? (value ? 'italic' : 'normal') : key === 'variant' && value === 'small_caps' ? 'small-caps' : key === 'decoration' && value === 'strike' ? 'line-through' : value;
                }
                for (let i = 0; i < primitives.length; i++) {
                    const p = primitives[i];
                    if (p.kind === 'text')
                        primitives[i] = { ...p, runs: p.runs.map(run => ({ ...run, style: { ...run.style, ...textStyle } })) };
                }
                if (overflow) {
                    diagnostics.push({ code: 'text-overflow', severity: 'warning', message: 'Text exceeds its declared bounds; the visible text is clipped and marked with an ellipsis.', target: definition.ref });
                    primitives.push(rect({ x: x + width - 26, y: y + height - 20, width: 24, height: 18 }, fill, 'none', 0), text('…', x + width - 23, y + height - 7, 14, color));
                }
                const occurrence = appearance?.ref.id ?? `${(0, model_js_1.refKey)(view.ref)}:${(0, model_js_1.refKey)(definition.ref)}`;
                const item = { occurrence, target: definition.ref, view: view.ref, layer: (0, model_js_1.str)(effective.layer, 'content'), bounds, ...(overflow ? { clip: bounds } : {}), transform: identity, primitives, hitTargets: [{ id: occurrence, target: definition.ref, bounds }], accessible: { role: 'graphics-symbol', label: titleText, description: `${(0, model_js_1.str)(definition.record.role)}; ${status}` }, status, evidence: snapshot.coverage.complete ? 'current' : 'partial' };
                const entry = { item, definition, view, ...(appearance ? { appearance } : {}), ...(placement ? { placement } : {}), effective, propertyOrigins };
                positioned.push({ ...entry, ...(profile === 'mindmap.basic@1' ? { mindmapTopic: mindmapTopicKeys.has((0, mindmap_js_1.mindmapKey)(definition)) } : {}) });
                nodeIndex++;
            }
            const byTarget = new Map(positioned.map(e => [(0, model_js_1.refKey)(e.definition.ref), e]));
            const byAppearance = new Map(positioned.filter(entry => entry.appearance).map(entry => [(0, model_js_1.refKey)(entry.appearance.ref), entry]));
            const selectedRelationRecords = all.filter(r => r.owner === 'definition' && r.record.category === 'relation' && !excluded.has((0, model_js_1.refKey)(r.ref)) && (0, model_js_1.pathValue)(view.record, 'selection.relations') !== 'none' && (0, model_js_1.array)(r.record.endpoints).every(end => { const target = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).definition ?? (0, model_js_1.object)(end).target ?? (0, model_js_1.object)(end).ref ?? end, r.file); return target && byTarget.has((0, model_js_1.refKey)(target.ref)) && (profile !== 'mindmap.basic@1' || selectedDefinitionKeys.has((0, model_js_1.refKey)(target.ref))); }));
            for (const relation of selectedRelationRecords)
                if (!relations.some(c => c.definition === relation))
                    relations.push({ definition: relation, appearance: undefined });
            for (const { definition, appearance } of relations) {
                if (!definition)
                    continue;
                const ends = (0, model_js_1.array)(definition.record.endpoints).map((end, index) => {
                    const semantic = (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(end).definition ?? (0, model_js_1.object)(end).target ?? (0, model_js_1.object)(end).ref ?? end, definition.file);
                    const explicit = index < 2 ? (0, model_js_1.pathValue)(appearance?.record, index === 0 ? 'route.from' : 'route.to') : undefined;
                    if (explicit !== undefined) {
                        const occurrence = (0, model_js_1.resolveRecord)(all, explicit, appearance?.file ?? definition.file);
                        const selected = occurrence ? byAppearance.get((0, model_js_1.refKey)(occurrence.ref)) : undefined;
                        if (selected && semantic && (0, model_js_1.refKey)(selected.definition.ref) === (0, model_js_1.refKey)(semantic.ref))
                            return selected;
                        diagnostics.push({ code: 'relation-occurrence-unavailable', severity: 'warning', message: 'The selected connection occurrence is unavailable in this view or does not represent its semantic endpoint.', target: appearance?.ref ?? definition.ref });
                        unavailable.push('relation-occurrence:' + (0, model_js_1.refKey)(appearance?.ref ?? definition.ref));
                        return undefined;
                    }
                    return semantic ? byTarget.get((0, model_js_1.refKey)(semantic.ref)) : undefined;
                });
                if (ends.length < 2 || !ends[0] || !ends[1])
                    continue;
                const from = ends[0], to = ends[1];
                const a = from.item.bounds, b = to.item.bounds;
                const horizontal = Math.abs(b.x + b.width / 2 - a.x - a.width / 2) >= Math.abs(b.y + b.height / 2 - a.y - a.height / 2);
                const right = b.x + b.width / 2 >= a.x + a.width / 2, down = b.y + b.height / 2 >= a.y + a.height / 2;
                const x1 = horizontal ? a.x + (right ? a.width : 0) : a.x + a.width / 2, y1 = horizontal ? a.y + a.height / 2 : a.y + (down ? a.height : 0), x2 = horizontal ? b.x + (right ? 0 : b.width) : b.x + b.width / 2, y2 = horizontal ? b.y + b.height / 2 : b.y + (down ? 0 : b.height);
                const route = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'layout.routing'), 'orthogonal');
                const d = route === 'straight' ? `M${x1},${y1}L${x2},${y2}` : route === 'curved' ? `M${x1},${y1}C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}` : `M${x1},${y1}H${(x1 + x2) / 2}V${y2}H${x2}`;
                const bounds = { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.max(1, Math.abs(x2 - x1)), height: Math.max(1, Math.abs(y2 - y1)) };
                const resolved = options.resolve(definition.ref, { view: view.ref, ...(appearance ? { appearance: appearance.ref } : {}) });
                const relOrigins = Object.fromEntries(resolved.properties.map(p => [p.path, p.origin]));
                const relEffective = (0, native_render_js_1.inheritedPresentation)(resolved.values, resolved.properties, effectiveView, viewOrigins, relOrigins, 'element');
                const item = { occurrence: appearance?.ref.id ?? `${(0, model_js_1.refKey)(view.ref)}:${(0, model_js_1.refKey)(definition.ref)}`, target: definition.ref, view: view.ref, layer: 'relations', bounds, transform: identity, primitives: [{ kind: 'path', d, paint: { fill: 'none', stroke: (0, model_js_1.str)((0, model_js_1.pathValue)(relEffective, 'stroke.color'), '#64748b'), 'stroke-width': 1.5 } }, text((0, model_js_1.str)(definition.record.title) || (0, model_js_1.str)(definition.record.name), bounds.x + bounds.width / 2, bounds.y - 5, 12, '#334155', { 'text-anchor': 'middle' })], hitTargets: [{ id: definition.ref.id, target: definition.ref, bounds }], accessible: { role: 'graphics-symbol', label: (0, model_js_1.titleOf)(definition.record) }, evidence: snapshot.coverage.complete ? 'current' : 'partial' };
                entries.push({ item, definition, view, ...(appearance ? { appearance } : {}), effective: relEffective, propertyOrigins: relOrigins });
            }
            const contentBounds = unionBounds(positioned.map(e => e.item.bounds));
            if (positioned.length && (0, model_js_1.pathValue)(effectiveView, 'layout.frame_overflow') !== 'confine') {
                viewWidth = Math.max(viewWidth, contentBounds.x + contentBounds.width - viewX + 32);
                viewHeight = Math.max(viewHeight, contentBounds.y + contentBounds.height - viewY + 32);
            }
            entries.push(...positioned);
            entries.splice(firstEntry, entries.length - firstEntry, ...(0, relation_presentation_js_1.prepareRelationPresentation)(entries.slice(firstEntry), all, effectiveView));
            if ((0, adapters_js_1.isGraphProfile)(profile) || ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile)) {
                const publication = (0, model_js_1.resolveRecord)(all, view.record.publication, view.file), page = (0, model_js_1.object)(publication ? options.resolve(publication.ref).values.page : undefined);
                if (page.fit === 'reflow' && ['grid', 'fit_grid'].includes((0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'layout.algorithm'))) && !positioned.some(entry => entry.appearance?.record.position && entry.appearance.record.position !== 'auto')) {
                    const [pageWidth] = (0, publication_js_1.publicationPageSize)(page, { width: 1280, height: 800 }), margins = (0, model_js_1.object)(page.margin), gap = (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'layout.gap'), 64), legend = (0, relation_presentation_js_1.relationLegendVisible)(effectiveView) && (0, model_js_1.pathValue)(effectiveView, 'legend.placement') === 'right' && entries.slice(firstEntry).some(e => (0, relation_presentation_js_1.relationPresentation)(e, effectiveView).inLegend) ? (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'legend.width'), 310) + 32 : 0;
                    const width = Math.max(1, pageWidth - (0, model_js_1.num)(margins.left, 32) - (0, model_js_1.num)(margins.right, 32) - legend - 64), nodeWidth = Math.max(248, ...positioned.map(entry => entry.item.bounds.width));
                    effectiveView.layout = { ...(0, model_js_1.object)(effectiveView.layout), algorithm: 'grid', columns: Math.max(1, Math.floor((width + gap) / (nodeWidth + gap))) };
                }
                const projected = ((0, adapters_js_1.graphProjector)(profile) ?? graph_native_js_1.projectNativeGraph)(snapshot, view, entries.slice(firstEntry), {
                    bounds: { x: viewX, y: viewY, width: viewWidth, height: viewHeight },
                    viewProperties: effectiveView,
                    ...(options.inclusionPath ? { ancestors: options.inclusionPath } : {}),
                    projectInline(childSnapshot, targetView, _bounds, ancestors) {
                        const { profiles: _profiles, ...childOptions } = options;
                        const result = projectSnapshot(childSnapshot, { ...childOptions, onlyView: targetView.ref, inclusionPath: ancestors, deferOpacity: true });
                        return { entries: result.entries, diagnostics: result.diagnostics, unavailable: result.coverage.unavailable };
                    },
                });
                entries.splice(firstEntry, entries.length - firstEntry, ...projected.entries);
                diagnostics.push(...projected.diagnostics);
                unavailable.push(...(projected.unavailable ?? []));
                if (projected.entries.length) {
                    const extent = unionBounds(projected.entries.map(entry => entry.item.bounds));
                    viewWidth = Math.max(fixedWidth ? viewWidth : 0, extent.x + extent.width - viewX + 32);
                    viewHeight = Math.max(fixedHeight ? viewHeight : 0, extent.y + extent.height - viewY + 32);
                }
            }
        }
        if (!(0, adapters_js_1.isDataProfile)(profile) && profile !== 'table.records@1') {
            const decorated = entries.slice(firstEntry).map(entry => entry.standalone ? entry : (0, stationery_js_1.decoratePaper)(entry));
            entries.splice(firstEntry, entries.length - firstEntry, ...decorated);
            if (decorated.length && (0, model_js_1.pathValue)(effectiveView, 'layout.frame_overflow') !== 'confine') {
                const extent = unionBounds(decorated.map(entry => entry.item.bounds));
                viewWidth = Math.max(fixedWidth ? viewWidth : 0, extent.x + extent.width - viewX + 32);
                viewHeight = Math.max(fixedHeight ? viewHeight : 0, extent.y + extent.height - viewY + 32);
            }
        }
        if ((0, model_js_1.pathValue)(effectiveView, 'projection.options.iso') === true && (profile === 'ddn@1' || (0, adapters_js_1.isGraphProfile)(profile))) {
            const projected = (0, graph_isometric_js_1.isometricGraph)(entries.slice(firstEntry), { x: viewX, y: viewY, width: viewWidth, height: viewHeight }, (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'projection.options.depth'), 18));
            entries.splice(firstEntry, entries.length - firstEntry, ...projected);
            if (projected.length) {
                const extent = unionBounds(projected.map(entry => entry.item.bounds));
                viewWidth = Math.max(viewWidth, extent.x + extent.width - viewX + 24);
                viewHeight = Math.max(viewHeight, extent.y + extent.height - viewY + 24);
            }
        }
        const chrome = (0, model_js_1.object)(effectiveView.chrome), chromeColor = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'text.color'), '#243449');
        const banner = chrome.banner !== false, showTitle = chrome.title !== false, footer = chrome.footer !== false;
        if (!(0, adapters_js_1.isDataProfile)(profile) && profile !== 'table.records@1' && entries.length > firstEntry) {
            const content = entries.slice(firstEntry), extent = unionBounds(content.map(e => e.item.bounds));
            const dx = Math.max(0, viewX + 20 - extent.x), dy = Math.max(0, viewY + (showTitle ? 64 : banner ? 32 : 16) - extent.y);
            if (dx || dy) {
                const shift = (b) => ({ ...b, x: b.x + dx, y: b.y + dy });
                entries.splice(firstEntry, content.length, ...content.map(entry => ({ ...entry, item: { ...entry.item, bounds: shift(entry.item.bounds), transform: [entry.item.transform[0], entry.item.transform[1], entry.item.transform[2], entry.item.transform[3], entry.item.transform[4] + dx, entry.item.transform[5] + dy], ...(entry.item.clip ? { clip: shift(entry.item.clip) } : {}), hitTargets: entry.item.hitTargets.map(hit => ({ ...hit, bounds: shift(hit.bounds) })) } })));
                viewWidth += dx;
                viewHeight += dy;
            }
        }
        const legendPlacement = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'legend.placement'), 'right');
        if ((0, relation_presentation_js_1.relationLegendVisible)(effectiveView)) {
            const members = new Map();
            for (const entry of entries.slice(firstEntry)) {
                if (!(0, relation_presentation_js_1.relationPresentation)(entry, effectiveView).inLegend)
                    continue;
                const key = (0, model_js_1.refKey)(entry.definition.ref), previous = members.get(key);
                if (!previous || (0, relation_presentation_js_1.relationPresentation)(entry, effectiveView).mode === 'numbers')
                    members.set(key, entry);
            }
            if (members.size) {
                const lw = (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'legend.width'), 310), lx = legendPlacement === 'right' ? viewX + viewWidth + 16 : viewX + 24, ly = legendPlacement === 'right' ? viewY + 80 : viewY + viewHeight + 16;
                viewPrimitives.push(text('RELATIONSHIP KEY', lx, ly, 11, chromeColor, { 'font-weight': 600 }));
                let cursor = ly + 26;
                for (const edge of members.values()) {
                    const kind = (0, model_js_1.str)(edge.definition.record.role), descriptor = (0, core_js_1.roleDescriptor)(kind, 'relation')?.render ?? {}, state = (0, relation_presentation_js_1.relationPresentation)(edge, effectiveView);
                    const token = state.mode === 'numbers' ? state.number : state.mode === 'tokens' ? kind : '';
                    const ends = (0, model_js_1.array)(edge.definition.record.endpoints).map(e => (0, model_js_1.resolveRecord)(all, (0, model_js_1.object)(e).definition, edge.definition.file)).filter((r) => !!r);
                    const semantic = (0, graph_common_js_1.edgeLabel)(edge, all) || (0, model_js_1.str)(edge.definition.record.description) || (0, model_js_1.str)(descriptor.text_label, kind);
                    const label = `${token ? token + '  ' : ''}${ends[0] ? (0, model_js_1.titleOf)(ends[0].record) : ''} → ${ends[1] ? (0, model_js_1.titleOf)(ends[1].record) : ''}: ${semantic}`;
                    const legendColor = ['dark', 'night', 'blueprint', 'neutral'].includes((0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.theme'))) ? chromeColor : (0, model_js_1.str)(descriptor.colour, chromeColor);
                    const body = (0, symbol_presentation_js_1.notePrimitives)(label, lx, cursor, lw - 20, 11, legendColor, t => measure(t, 11, 'sans'), false, 5);
                    viewPrimitives.push(...body.primitives);
                    cursor += body.height + 10;
                }
                if (legendPlacement === 'right') {
                    viewWidth += lw + 32;
                    viewHeight = Math.max(viewHeight, cursor - viewY + 20);
                }
                else
                    viewHeight = cursor - viewY + 20;
            }
        }
        if (footer)
            viewHeight += 30;
        if (showTitle && !fixedWidth)
            viewWidth = Math.max(viewWidth, measure((0, model_js_1.str)(chrome.title_text) || title, Math.min(24, (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'style.font_size'), 16) + 8), (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.font'), 'sans')) + 40);
        let surfaceTransform;
        if (surface) {
            const fitted = (0, view_surface_js_1.fitSurfaceContent)(entries.slice(firstEntry), viewPrimitives, surface, { x: viewX, y: viewY }, chrome, measure);
            entries.splice(firstEntry, entries.length - firstEntry, ...fitted.entries);
            viewPrimitives.splice(0, viewPrimitives.length, ...fitted.annotations);
            surfaceTransform = fitted.matrix;
            viewWidth = surface.width;
            viewHeight = surface.height;
            if (fitted.clipped)
                diagnostics.push({ code: 'surface-overflow', severity: 'warning', message: 'Content outside the fixed view surface is clipped; use surface.fit contain to fit the complete diagram.', target: view.ref });
        }
        const bounds = { x: viewX, y: viewY, width: viewWidth, height: viewHeight };
        const imageRef = (0, model_js_1.pathValue)(effectiveView, 'background.image');
        if (imageRef) {
            const asset = (0, model_js_1.resolveRecord)(all, imageRef, view.file);
            if (asset)
                viewPrimitives.push({ kind: 'image', assetId: (0, model_js_1.refKey)(asset.ref), bounds });
            else
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: 'View background image does not resolve.', target: view.ref });
        }
        const viewFill = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'background.color'), '#f8fafc');
        const viewBorderStyle = (0, model_js_1.pathValue)(effectiveView, 'border.style');
        const viewStroke = viewBorderStyle === 'none' ? 'none' : (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'border.color'), '#cbd5e1');
        const viewBorderWidth = (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'border.width')) > 0 ? (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'border.width')) : 1;
        const viewBorderDash = viewBorderStyle === 'dashed' ? '6 4' : viewBorderStyle === 'dotted' ? '2 3' : undefined;
        let frameOutline = (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.look')) === 'handdrawn'
            ? sketch(bounds, viewFill, viewStroke, (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'style.seed'), 42) + viewIndex, (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'style.roughness'), 1))
            : rect(bounds, viewFill, viewStroke, viewBorderWidth);
        if ('paint' in frameOutline && (viewBorderWidth !== 1 || viewBorderDash))
            frameOutline = { ...frameOutline, paint: { ...frameOutline.paint, 'stroke-width': viewBorderWidth, ...(viewBorderDash ? { 'stroke-dasharray': viewBorderDash } : {}) } };
        viewPrimitives.unshift(frameOutline);
        const chromeScale = surface?.scale ?? 1;
        if (banner)
            viewPrimitives.push(text((0, model_js_1.str)(chrome.banner_text) || 'DDN / ' + profile + ' / ddn-next-1', viewX + 20 * chromeScale, viewY + 16 * chromeScale, 10 * chromeScale, chromeColor, { 'font-weight': 600 }));
        if (showTitle)
            viewPrimitives.push(text((0, model_js_1.str)(chrome.title_text) || title, viewX + 20 * chromeScale, viewY + (banner ? 40 : 31) * chromeScale, Math.min(24, (0, model_js_1.num)((0, model_js_1.pathValue)(effectiveView, 'style.font_size'), 16) + 8) * chromeScale, chromeColor, { 'font-weight': 700 }, (0, model_js_1.str)((0, model_js_1.pathValue)(effectiveView, 'style.font'), 'sans')));
        if (footer) {
            viewPrimitives.push({ kind: 'path', d: `M${viewX + 20 * chromeScale},${viewY + viewHeight - 30 * chromeScale}H${viewX + viewWidth - 20 * chromeScale}`, paint: { fill: 'none', stroke: chromeColor, 'stroke-width': .5 * chromeScale, opacity: .3 } }, text((0, model_js_1.str)(chrome.footer_text) || profile, viewX + 20 * chromeScale, viewY + viewHeight - 12 * chromeScale, 10 * chromeScale, chromeColor));
        }
        const frame = { occurrence: `view:${(0, model_js_1.refKey)(view.ref)}`, target: view.ref, view: view.ref, layer: 'views', bounds, transform: identity, primitives: viewPrimitives, hitTargets: [{ id: view.ref.id, target: view.ref, bounds }], accessible: { role: 'graphics-object', label: `${title}, ${profile || 'document'}` }, evidence: supported || isDocument ? snapshot.coverage.complete ? 'current' : 'partial' : 'invalid' };
        let decoratedFrame = (0, stationery_js_1.decoratePaper)({ item: frame, definition: view, view, ...(placement ? { placement } : {}), effective: effectiveView, propertyOrigins: viewOrigins });
        if (surface)
            decoratedFrame = { ...decoratedFrame, surfaceTransform: surfaceTransform, item: { ...decoratedFrame.item, bounds, clip: bounds, hitTargets: frame.hitTargets } };
        const viewEntries = entries.slice(firstEntry);
        const hasPaper = [decoratedFrame, ...viewEntries].some(entry => entry.item.primitives.some(p => 'paint' in p && p.paint['ddn-decoration']));
        let paintedFrame = decoratedFrame.item.bounds;
        if (hasPaper && !surface) {
            const extent = unionBounds([paintedFrame, ...viewEntries.map(entry => entry.item.bounds)]);
            const dx = typeof vp.x === 'number' ? 0 : Math.max(0, viewX - extent.x);
            const dy = typeof vp.y === 'number' ? 0 : Math.max(0, viewY - extent.y);
            const moveBounds = (b) => ({ ...b, x: b.x + dx, y: b.y + dy });
            const move = (entry) => {
                const item = entry.item, m = item.transform;
                return { ...entry, item: { ...item, bounds: moveBounds(item.bounds), ...(item.clip ? { clip: moveBounds(item.clip) } : {}),
                        hitTargets: item.hitTargets.map(hit => ({ ...hit, bounds: moveBounds(hit.bounds) })),
                        transform: [m[0], m[1], m[2], m[3], m[4] + dx, m[5] + dy],
                    } };
            };
            if (dx || dy) {
                decoratedFrame = move(decoratedFrame);
                entries.splice(firstEntry, viewEntries.length, ...viewEntries.map(move));
            }
            paintedFrame = moveBounds(extent);
        }
        entries.unshift(decoratedFrame);
        rowBottom = Math.max(rowBottom, paintedFrame.y + paintedFrame.height);
        if (viewIndex % 2 === 0)
            nextViewX = paintedFrame.x + paintedFrame.width + 80;
        else {
            nextViewX = 0;
            nextViewY = rowBottom + 80;
        }
    }
    const painted = options.deferOpacity ? entries : entries.map(entry => {
        const opacity = (0, model_js_1.num)(options.preview?.opacity, (0, model_js_1.num)(entry.effective.opacity, 1));
        if (opacity === 1)
            return entry;
        if (entry.item.primitives.some(primitive => primitive.kind === 'image')) {
            diagnostics.push({ code: 'image-opacity-unavailable', severity: 'warning', message: 'Opacity on image primitives is not supported by this scene contract; image opacity is unchanged.', target: entry.definition.ref });
            unavailable.push('image-opacity:' + entry.item.occurrence);
        }
        const primitives = entry.item.primitives.map((primitive) => {
            if (primitive.kind === 'text')
                return { ...primitive, runs: primitive.runs.map(run => ({ ...run, style: { ...run.style, opacity: (0, model_js_1.num)(run.style.opacity, 1) * opacity } })) };
            if ('paint' in primitive)
                return { ...primitive, paint: { ...primitive.paint, opacity: (0, model_js_1.num)(primitive.paint.opacity, 1) * opacity } };
            return primitive;
        });
        return { ...entry, item: { ...entry.item, primitives } };
    });
    return { items: painted.map(e => e.item), entries: painted, views, bounds: unionBounds(painted.map(e => e.item.bounds)), coverage: { ...snapshot.coverage, complete: snapshot.coverage.complete && !unavailable.length, unavailable: [...snapshot.coverage.unavailable, ...unavailable] }, diagnostics };
}

},
"presentation/src/publication.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.publicationPageSize = publicationPageSize;
exports.publicationScene = publicationScene;
const table_js_1 = require("presentation/src/table.js");
const model_js_1 = require("presentation/src/model.js");
function publicationPageSize(page, content) {
    const measure = (value, fallback) => { const q = (0, model_js_1.object)(value); return typeof value === 'number' ? value : (0, model_js_1.num)(q.value, fallback) * ({ px: 1, pt: 96 / 72, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 }[(0, model_js_1.str)(q.unit, 'px')] ?? 1); };
    const paper = { letter: [816, 1056], legal: [816, 1344], a4: [793.7, 1122.52], a3: [1122.52, 1587.4], tabloid: [1056, 1632] };
    let [width, height] = paper[(0, model_js_1.str)(page.size)] ?? [measure(page.width, content.width), measure(page.height, content.height)];
    if (page.orientation === 'landscape' && width < height)
        [width, height] = [height, width];
    return [width, height];
}
function publicationScene(items, content, publication, title, date) {
    const record = publication.record, page = (0, model_js_1.object)(record.page), size = (0, model_js_1.str)(page.size, 'content');
    const measure = (value, fallback) => { const q = (0, model_js_1.object)(value); return typeof value === 'number' ? value : (0, model_js_1.num)(q.value, fallback) * ({ px: 1, pt: 96 / 72, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 }[(0, model_js_1.str)(q.unit, 'px')] ?? 1); };
    let [width, height] = publicationPageSize(page, content);
    const margins = (0, model_js_1.object)(page.margin), left = (0, model_js_1.num)(margins.left, 32), right = (0, model_js_1.num)(margins.right, 32), top = (0, model_js_1.num)(margins.top, 32), bottom = (0, model_js_1.num)(margins.bottom, 32);
    const tokens = { title, date, page: String((0, model_js_1.num)(page.number_start, 1)), pages: '1', figure: '1', view_id: items[0]?.view.id ?? '' };
    const contentScale = (0, model_js_1.num)(page.content_scale, 1);
    if (size === 'content')
        width = content.width * contentScale + left + right;
    const band = (input) => {
        const data = (0, model_js_1.object)(input);
        if (data.visible === false)
            return [];
        const entries = Object.entries((0, model_js_1.object)(data.runs)), center = entries.some(([position, value]) => (0, model_js_1.str)((0, model_js_1.object)(value).align, position) === 'center'), slotWidth = Math.max(1, (width - left - right) / (entries.length <= 1 ? 1 : center ? 3 : 2) - 12);
        return entries.map(([position, value]) => { const run = (0, model_js_1.object)(value), fontSize = measure(run.size, 12), label = (0, model_js_1.str)(run.text).replace(/\$(title|date|pages|page|figure|view_id)\b/g, (_, key) => tokens[key]); return { run, position, fontSize, lines: (0, table_js_1.wrapCell)(label, slotWidth, value => value.length * fontSize * .6, (0, model_js_1.num)(run.lines, 1)).lines }; });
    };
    const header = band(record.header), footer = band(record.footer), bandHeight = (items) => items.length ? Math.max(...items.map(item => item.lines.length * item.fontSize * 1.3)) + 12 : 0, headerHeight = bandHeight(header), footerHeight = bandHeight(footer);
    if (size === 'content')
        height = content.height * contentScale + top + bottom + headerHeight + footerHeight;
    const destination = { x: left, y: top + headerHeight, width: Math.max(1, width - left - right), height: Math.max(1, height - top - bottom - headerHeight - footerHeight) };
    const fit = (0, model_js_1.str)(page.fit, 'contain'), scale = fit === 'none' ? contentScale : Math.min(destination.width / content.width, destination.height / content.height);
    const tx = destination.x + (destination.width - content.width * scale) / 2 - content.x * scale, ty = destination.y + (destination.height - content.height * scale) / 2 - content.y * scale;
    const move = (b) => ({ x: b.x * scale + tx, y: b.y * scale + ty, width: b.width * scale, height: b.height * scale });
    const intersect = (a, b) => { const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y); return { x, y, width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - x), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - y) }; };
    const transformed = items.map(item => { const m = item.transform; return { ...item, bounds: move(item.bounds), clip: item.clip ? intersect(move(item.clip), destination) : destination, hitTargets: item.hitTargets.map(h => ({ ...h, bounds: move(h.bounds) })), transform: [m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4] * scale + tx, m[5] * scale + ty] }; });
    const bounds = { x: 0, y: 0, width, height };
    const primitives = [{ kind: 'rect', bounds, paint: { fill: (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'background.color'), '#ffffff'), stroke: 'none', rx: 0 } }];
    const border = (0, model_js_1.num)((0, model_js_1.pathValue)(record, 'border.width'));
    const look = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'style.look'));
    const defaultFont = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'style.font'), 'sans');
    if (border > 0) {
        const b = { x: left / 2, y: top / 2, width: width - (left + right) / 2, height: height - (top + bottom) / 2 }, stroke = (0, model_js_1.str)((0, model_js_1.pathValue)(record, 'border.color'), '#475569');
        if (look === 'handdrawn') {
            let state = (0, model_js_1.num)((0, model_js_1.pathValue)(record, 'style.seed'), 42) >>> 0;
            const roughness = (0, model_js_1.num)((0, model_js_1.pathValue)(record, 'style.roughness'), 1), rnd = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return (state / 4294967296 - .5) * roughness * 2; };
            const pts = [[b.x, b.y], [b.x + b.width, b.y], [b.x + b.width, b.y + b.height], [b.x, b.y + b.height], [b.x, b.y]].map(([px, py]) => `${px + rnd()},${py + rnd()}`);
            primitives.push({ kind: 'path', d: 'M' + pts.join('L') + 'Z', paint: { fill: 'none', stroke, 'stroke-width': border } });
        }
        else
            primitives.push({ kind: 'rect', bounds: b, paint: { fill: 'none', stroke, 'stroke-width': border, rx: 0 } });
    }
    for (const [items, y] of [[header, top], [footer, height - bottom - footerHeight]]) {
        for (const { run, position, fontSize, lines } of items) {
            const align = (0, model_js_1.str)(run.align, position);
            primitives.push({ kind: 'text', runs: lines.map((text, index) => ({ text, x: align === 'right' ? width - right : align === 'center' ? width / 2 : left, y: y + 6 + fontSize + index * fontSize * 1.3, fontKey: (0, model_js_1.str)(run.font, defaultFont), style: { 'font-size': fontSize, fill: (0, model_js_1.str)(run.color, '#334155'), 'text-anchor': align === 'right' ? 'end' : align === 'center' ? 'middle' : 'start', 'font-weight': (0, model_js_1.num)(run.weight, 400), ...(run.italic ? { 'font-style': 'italic' } : {}), ...(run.decoration === 'strike' ? { 'text-decoration': 'line-through' } : {}), ...(run.variant === 'small_caps' ? { 'font-variant': 'small-caps' } : {}) } })) });
        }
    }
    const frame = { occurrence: 'publication:' + publication.ref.id, target: publication.ref, view: items[0]?.view ?? publication.ref, layer: 'views', bounds, transform: [1, 0, 0, 1, 0, 0], primitives, hitTargets: [], accessible: { role: 'graphics-object', label: title }, evidence: 'current' };
    const diagnostics = [];
    if (content.width * scale > destination.width + .01 || content.height * scale > destination.height + .01)
        diagnostics.push({ code: 'publication-overflow', severity: page.overflow === 'report' ? 'warning' : 'error', message: page.overflow === 'tile' ? 'This capture requires a tiled publication output adapter.' : 'Content exceeds the page content area at the requested scale.', target: publication.ref });
    const fonts = items.flatMap(i => i.primitives.flatMap(p => p.kind === 'text' ? p.runs.map(r => (0, model_js_1.num)(r.style['font-size'], 16) * scale * (0, model_js_1.num)(page.embedding_scale, 1)) : []));
    if (fonts.length && Math.min(...fonts) < (0, model_js_1.num)(page.minimum_text, 0))
        diagnostics.push({ code: 'publication-minimum-text', severity: 'warning', message: 'Page fitting places some text below the publication minimum text size.', target: publication.ref });
    return { items: [frame, ...transformed], bounds, diagnostics };
}

},
"presentation/src/records.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.recordTableData = recordTableData;
const model_js_1 = require("presentation/src/model.js");
function recordTableData(snapshot, view) {
    const all = (0, model_js_1.records)(snapshot), options = (0, model_js_1.object)((0, model_js_1.pathValue)(view.record, 'projection.options'));
    const references = Array.isArray(options.records) ? options.records : options.records ? [options.records] : [];
    let descriptors = [];
    let values = [];
    const diagnostics = [];
    const issue = (message) => diagnostics.push({ code: 'table-projection', severity: 'warning', message, target: view.ref });
    for (const reference of references) {
        const target = (0, model_js_1.resolveRecord)(all, reference, view.file);
        if (!target) {
            issue('A table record reference is unavailable.');
            continue;
        }
        if (target.owner === 'view') {
            issue('A record table cannot use another view as a scalar record.');
            continue;
        }
        let data = target.owner === 'data' ? target.record : (0, model_js_1.object)(target.record.data);
        if (data.source) {
            const bound = (0, model_js_1.resolveRecord)(all, data.source, target.file);
            if (bound?.owner === 'data')
                data = bound.record;
        }
        if (!Array.isArray(data.columns) && Array.isArray((0, model_js_1.object)(data.snapshot).columns))
            data = (0, model_js_1.object)(data.snapshot);
        if (Array.isArray(data.columns)) {
            const columns = (0, model_js_1.array)(data.columns).map(model_js_1.object);
            if (!descriptors.length)
                descriptors = columns;
            values.push(...(0, model_js_1.array)(data.rows).map(row => ({ record: Object.fromEntries(columns.map((column, index) => [(0, model_js_1.str)(column.id), (0, model_js_1.array)(row)[index] ?? null])), target: target.ref })));
        }
        else
            values.push({ record: target.record, target: target.ref });
    }
    let columns;
    if (Array.isArray(options.columns) && options.columns.length) {
        columns = options.columns.map(value => {
            const descriptor = (0, model_js_1.object)(value);
            if (descriptor.file || descriptor.name && !descriptor.id) {
                const field = (0, model_js_1.resolveRecord)(all, descriptor, view.file);
                if (!field) {
                    issue('A table column reference is unavailable.');
                    return { id: (0, model_js_1.str)(descriptor.id, (0, model_js_1.str)(descriptor.name)) };
                }
                return { id: (0, model_js_1.str)(field.record.name, field.ref.id), path: (0, model_js_1.str)((0, model_js_1.pathValue)(field.record, 'content.path'), (0, model_js_1.str)(field.record.name)), label: (0, model_js_1.titleOf)(field.record) };
            }
            return { ...descriptor };
        });
    }
    else if (descriptors.length)
        columns = descriptors;
    else
        columns = [...new Set(values.flatMap(({ record }) => Object.keys(record).filter(key => record[key] === null || typeof record[key] !== 'object')))].map(id => ({ id }));
    if (typeof options.columns === 'number')
        columns = columns.slice(0, Math.max(0, Math.floor(options.columns)));
    columns = columns.filter(column => column.visibility !== 'hidden' && column.visibility !== 'on_demand');
    const read = (record, key) => Object.hasOwn(record, key) ? record[key] : (0, model_js_1.pathValue)(record, key);
    for (const filter of (0, model_js_1.array)(options.filter).map(model_js_1.object))
        values = values.filter(({ record }) => {
            const actual = read(record, (0, model_js_1.str)(filter.key));
            return filter.op === 'in' ? (0, model_js_1.array)(filter.value).some(value => Object.is(value, actual)) : Object.is(filter.value, actual);
        });
    const order = (0, model_js_1.array)(options.order).map(model_js_1.object);
    if (order.length)
        values = values.map((value, index) => ({ ...value, index })).sort((a, b) => {
            for (const term of order) {
                const left = read(a.record, (0, model_js_1.str)(term.key)), right = read(b.record, (0, model_js_1.str)(term.key));
                let compared = 0;
                if (left === right)
                    continue;
                if (left === undefined || left === null)
                    compared = -1;
                else if (right === undefined || right === null)
                    compared = 1;
                else if (typeof left === 'number' && typeof right === 'number')
                    compared = left - right;
                else
                    compared = String(left) < String(right) ? -1 : 1;
                if (compared)
                    return term.direction === 'desc' ? -compared : compared;
            }
            return a.index - b.index;
        });
    const missing = (0, model_js_1.str)(options.missing, 'error'), rows = [], targets = [];
    for (const value of values) {
        const row = columns.map(column => read(value.record, (0, model_js_1.str)(column.path, (0, model_js_1.str)(column.id))));
        if (row.some(cell => cell === undefined)) {
            if (missing === 'skip')
                continue;
            if (missing === 'error')
                issue('A record is missing a declared table column.');
        }
        rows.push(row.map(cell => cell ?? null));
        targets.push(value.target);
    }
    if (!columns.length)
        issue('Choose table columns to display records.');
    return { columns, rows, targets, diagnostics };
}

},
"presentation/src/view-surface.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.fixedViewSurface = fixedViewSurface;
exports.surfaceBounds = surfaceBounds;
exports.fitSurfaceContent = fitSurfaceContent;
const model_js_1 = require("presentation/src/model.js");
const positive = (value) => typeof value === 'number' && Number.isFinite(value) && value > 0;
function fixedViewSurface(effective) {
    const surface = (0, model_js_1.object)(effective.surface);
    if (!positive(surface.width) || !positive(surface.height))
        return undefined;
    return { width: surface.width, height: surface.height, scale: positive(surface.scale) ? surface.scale : 1,
        padding: Math.max(0, (0, model_js_1.num)(surface.padding, 32)), fit: surface.fit === 'none' ? 'none' : 'contain' };
}
function surfaceBounds(bounds, matrix) {
    return { x: bounds.x * matrix[0] + matrix[4], y: bounds.y * matrix[3] + matrix[5], width: bounds.width * matrix[0], height: bounds.height * matrix[3] };
}
function intersect(a, b) {
    const left = Math.max(a.x, b.x), top = Math.max(a.y, b.y);
    return { x: Math.max(b.x, Math.min(b.x + b.width, left)), y: Math.max(b.y, Math.min(b.y + b.height, top)), width: Math.max(0, Math.min(a.x + a.width, b.x + b.width) - left), height: Math.max(0, Math.min(a.y + a.height, b.y + b.height) - top) };
}
function annotationsBounds(primitives, measure) {
    return primitives.flatMap(primitive => {
        if (primitive.kind !== 'text')
            return 'bounds' in primitive ? [primitive.bounds] : [];
        return primitive.runs.map(run => {
            const size = (0, model_js_1.num)(run.style['font-size'], 12), width = measure(run.text, size, run.fontKey);
            const shift = run.style['text-anchor'] === 'middle' ? width / 2 : run.style['text-anchor'] === 'end' ? width : 0;
            return { x: run.x - shift, y: run.y - size, width, height: size * 1.3 };
        });
    });
}
function fitSurfaceContent(entries, annotations, surface, origin, chrome, measure) {
    const { width, height, scale: preferred, padding } = surface;
    const padX = Math.min(padding * preferred, width / 4), padY = Math.min(padding * preferred, height / 4);
    const header = (chrome.title !== false ? 64 : chrome.banner !== false ? 32 : 0) * preferred;
    const footer = chrome.footer !== false ? 30 * preferred : 0;
    const top = Math.min(height / 2, Math.max(padY, header));
    const bottom = Math.min(height / 4, Math.max(padY, footer));
    const drawable = { x: origin.x + padX, y: origin.y + top, width: Math.max(1, width - padX * 2), height: Math.max(1, height - top - bottom) };
    const logicalLeft = origin.x + padX / preferred, logicalTop = origin.y + top / preferred;
    const extents = [...entries.map(entry => entry.item.bounds), ...annotationsBounds(annotations, measure)];
    const left = Math.min(logicalLeft, ...extents.map(bounds => bounds.x)), upper = Math.min(logicalTop, ...extents.map(bounds => bounds.y));
    const right = Math.max(logicalLeft + 1, ...extents.map(bounds => bounds.x + bounds.width));
    const lower = Math.max(logicalTop + 1, ...extents.map(bounds => bounds.y + bounds.height));
    const factor = surface.fit === 'none' ? preferred : Math.min(preferred, drawable.width / (right - left), drawable.height / (lower - upper));
    const matrix = surface.fit === 'none' ? [factor, 0, 0, factor, origin.x * (1 - factor), origin.y * (1 - factor)]
        : [factor, 0, 0, factor, drawable.x - left * factor, drawable.y - upper * factor];
    const clipped = extents.some(bounds => {
        const b = surfaceBounds(bounds, matrix);
        return b.x < drawable.x - .01 || b.y < drawable.y - .01 || b.x + b.width > drawable.x + drawable.width + .01 || b.y + b.height > drawable.y + drawable.height + .01;
    });
    const transformed = entries.map(entry => {
        const item = entry.item, m = item.transform;
        const clip = intersect(item.clip ? surfaceBounds(item.clip, matrix) : drawable, drawable);
        return { ...entry, surfaceTransform: matrix, item: { ...item, bounds: intersect(surfaceBounds(item.bounds, matrix), drawable), clip,
                transform: [m[0] * factor, m[1] * factor, m[2] * factor, m[3] * factor, m[4] * factor + matrix[4], m[5] * factor + matrix[5]],
                hitTargets: item.hitTargets.map(hit => ({ ...hit, bounds: intersect(surfaceBounds(hit.bounds, matrix), drawable) })).filter(hit => hit.bounds.width > 0 && hit.bounds.height > 0) } };
    });
    const transformedAnnotations = annotations.map(primitive => primitive.kind === 'text'
        ? { ...primitive, runs: primitive.runs.map(run => ({ ...run, x: run.x * factor + matrix[4], y: run.y * factor + matrix[5], style: { ...run.style, 'font-size': (0, model_js_1.num)(run.style['font-size'], 12) * factor } })) }
        : 'bounds' in primitive ? { ...primitive, bounds: surfaceBounds(primitive.bounds, matrix) } : primitive);
    return { entries: transformed, annotations: transformedAnnotations, matrix, drawable, clipped, bounds: { x: origin.x, y: origin.y, width, height } };
}

},
"runtime/src/guards.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.referenceGraph = referenceGraph;
exports.checkLifecycleMutation = checkLifecycleMutation;
exports.affectedProtected = affectedProtected;
const index_js_1 = require("model/src/index.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const index_js_2 = require("execution/src/index.js");
const key = (ref) => ref.file + '\0' + ref.id;
const status = (record) => (0, index_js_1.asString)((0, index_js_1.asRecord)(record.design).state, 'draft');
const paint = new Set(['style', 'text', 'background', 'border', 'shadow', 'padding', 'opacity', 'position', 'size', 'min_size', 'max_size', 'aspect_ratio', 'layer', 'order', 'visible', 'locked', 'include_in_output', 'pinned', 'rotation', 'route', 'body', 'sections', 'section_order', 'columns', 'column_visibility', 'stroke', 'symbol', 'table', 'layout', 'display', 'legend', 'grid', 'snap', 'guides', 'rulers', 'navigation', 'chrome', 'animation', 'title']);
const semantic = (record) => Object.fromEntries(Object.entries(record).filter(([name]) => (!paint.has(name) || name === 'title' && record.role !== undefined) && !['acceptance', 'acceptance_history', 'design'].includes(name)));
function referenceGraph(normalized) {
    const graph = new Map();
    for (const file of (0, index_js_1.normalizedFiles)(normalized))
        (0, schema_core_js_1.validateSchema)('file', file.document, { maxIssues: 0, reference(value, path) {
                const segments = path.split('/');
                const collection = segments[1];
                const owner = collection === 'workarea' ? (0, index_js_1.asRecord)(file.document.workarea) : (0, index_js_1.asRecord)((0, index_js_1.asArray)(file.document[collection ?? ''])[Number(segments[2])]);
                if (typeof owner.id !== 'string')
                    return;
                const target = (0, index_js_1.resolveReference)(normalized, file.location, value);
                if (!target)
                    return;
                const id = key((0, index_js_1.recordRef)(file.location, owner)), references = graph.get(id) ?? new Set();
                references.add(key(target.ref));
                graph.set(id, references);
            } });
    return graph;
}
function checkLifecycleMutation(beforeNormalized, afterNormalized) {
    const previous = new Map((0, index_js_1.listRecords)(beforeNormalized).map(entry => [key(entry.ref), entry]));
    const result = [];
    for (const entry of (0, index_js_1.listRecords)(afterNormalized)) {
        const before = previous.get(key(entry.ref));
        const changed = before
            ? status(before.record) !== status(entry.record) || (0, index_js_2.canonical)(before.record.acceptance) !== (0, index_js_2.canonical)(entry.record.acceptance) || (0, index_js_2.canonical)(before.record.acceptance_history) !== (0, index_js_2.canonical)(entry.record.acceptance_history)
            : status(entry.record) !== 'draft' || entry.record.acceptance !== undefined || entry.record.acceptance_history !== undefined;
        if (changed)
            result.push({ code: 'runtime.lifecycle', severity: 'error', message: 'Use an authorized lifecycle command to change status or acceptance evidence.', target: entry.ref });
    }
    return result;
}
function affectedProtected(snapshot, afterNormalized) {
    const before = (0, index_js_1.listRecords)(snapshot.normalized), after = (0, index_js_1.listRecords)(afterNormalized);
    const previous = new Map(before.map(entry => [key(entry.ref), entry]));
    const next = new Map(after.map(entry => [key(entry.ref), entry]));
    const changed = new Set();
    for (const id of new Set([...previous.keys(), ...next.keys()])) {
        if ((0, index_js_2.canonical)(semantic(previous.get(id)?.record ?? {})) !== (0, index_js_2.canonical)(semantic(next.get(id)?.record ?? {})))
            changed.add(id);
    }
    const dependencies = referenceGraph(snapshot.normalized);
    let grew = true;
    while (grew) {
        grew = false;
        for (const entry of before)
            if (!changed.has(key(entry.ref)) && [...(dependencies.get(key(entry.ref)) ?? [])].some(id => changed.has(id))) {
                changed.add(key(entry.ref));
                grew = true;
            }
    }
    return before.filter(entry => {
        if (!['accepted', 'in-review'].includes(status(entry.record)))
            return false;
        if (entry.kind === 'workarea' && entry.file !== snapshot.rootFile)
            return false;
        const acceptance = (0, index_js_1.asRecord)(entry.record.acceptance);
        const explicitlyScoped = (0, index_js_1.asArray)(acceptance.scope).some(reference => { const target = (0, index_js_1.resolveReference)(snapshot.normalized, entry.file, reference); return !!target && changed.has(key(target.ref)); });
        const presentationProtected = typeof acceptance.presentation_digest === 'string' && (0, index_js_2.canonical)(entry.record) !== (0, index_js_2.canonical)(next.get(key(entry.ref))?.record);
        return entry.kind === 'workarea' && changed.size > 0 || changed.has(key(entry.ref)) || explicitlyScoped || presentationProtected;
    }).map(entry => entry.ref);
}

},
"runtime/src/native.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.registrations = exports.STANDARD_VERSIONS = exports.createRuntime = void 0;
exports.createNativeRuntimeOptions = createNativeRuntimeOptions;
var runtime_js_1 = require("runtime/src/runtime.js");
Object.defineProperty(exports, "createRuntime", { enumerable: true, get: function () { return runtime_js_1.createRuntime; } });
Object.defineProperty(exports, "STANDARD_VERSIONS", { enumerable: true, get: function () { return runtime_js_1.STANDARD_VERSIONS; } });
var registry_js_1 = require("runtime/src/registry.js");
Object.defineProperty(exports, "registrations", { enumerable: true, get: function () { return registry_js_1.registrations; } });
const native_js_1 = require("profiles/src/native.js");
const runtime_js_2 = require("runtime/src/runtime.js");
function createNativeRuntimeOptions() {
    return { versions: runtime_js_2.STANDARD_VERSIONS, packs: [(0, native_js_1.createNativePack)()] };
}

},
"runtime/src/profile-loading.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.attachProfileLoadingHost = attachProfileLoadingHost;
exports.profileLoadingHost = profileLoadingHost;
exports.prepareRuntimeProfiles = prepareRuntimeProfiles;
const hosts = new WeakMap();
function attachProfileLoadingHost(runtime, host) { hosts.set(runtime, host); }
function profileLoadingHost(runtime) { return hosts.get(runtime); }
async function prepareRuntimeProfiles(runtime, input, options) {
    await hosts.get(runtime)?.ensure(input, options);
}

},
"runtime/src/providers.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.applyProviderOverlays = applyProviderOverlays;
exports.stageProviderChanges = stageProviderChanges;
const index_js_1 = require("model/src/index.js");
const index_js_2 = require("execution/src/index.js");
const identity = (ref) => ref.file + '\0' + ref.id;
function bindings(normalized, source) {
    return (0, index_js_1.listRecords)(normalized).flatMap(entry => {
        const data = entry.kind === 'data' ? entry.record : entry.kind === 'definition' ? (0, index_js_1.asRecord)(entry.record.data) : undefined;
        if (!data)
            return [];
        const target = (0, index_js_1.resolveReference)(normalized, entry.file, data.source);
        return target?.kind === 'source' && identity(target.ref) === identity(source) ? [{ entry, data }] : [];
    });
}
function columnsOf(schema) {
    const values = Array.isArray(schema) ? schema : (0, index_js_1.asRecord)(schema).columns;
    if (!Array.isArray(values) || !values.length || values.some(value => !(0, index_js_1.isRecord)(value) || typeof value.id !== 'string' || !value.id))
        throw Error('Provider schema requires nonempty column descriptors.');
    const columns = (0, index_js_2.clone)(values);
    if (new Set(columns.map(column => column.id)).size !== columns.length)
        throw Error('Provider column identities must be unique.');
    return columns;
}
function rowOf(row, columns) {
    if (Array.isArray(row)) {
        if (row.length > columns.length)
            throw Error('Provider row has more cells than its schema.');
        return columns.map((_, index) => (0, index_js_2.clone)(row[index] ?? null));
    }
    if ((0, index_js_1.isRecord)(row)) {
        if (Object.keys(row).some(key => !columns.some(column => column.id === key)))
            throw Error('Provider row contains an undeclared column.');
        return columns.map(column => (0, index_js_2.clone)(row[(0, index_js_1.asString)(column.id)] ?? null));
    }
    throw Error('Provider rows must be positional arrays or objects keyed by declared columns.');
}
function sourceKeys(targets, columns) {
    const keys = targets.map(({ data }) => (0, index_js_1.asArray)(data.key).map(value => (0, index_js_1.asString)((0, index_js_1.asRecord)(data.mapping)[(0, index_js_1.asString)(value)], (0, index_js_1.asString)(value))));
    if (!keys[0]?.length)
        throw Error('Keyed updates require declared dataset key columns.');
    if (keys.some(value => (0, index_js_2.canonical)(value) !== (0, index_js_2.canonical)(keys[0])))
        throw Error('Datasets bound to one keyed source must agree on its source keys.');
    if (keys[0].some(key => !columns.some(column => column.id === key)))
        throw Error('A keyed update names an unavailable key column.');
    return keys[0];
}
function rowKey(row, columns, keys) {
    const values = keys.map(key => row[columns.findIndex(column => column.id === key)]);
    if (values.some(value => value === null || value === undefined || typeof value === 'object' || value === ''))
        throw Error('Provider keys must be nonempty scalar values.');
    return values.length === 1 ? String(values[0]) : (0, index_js_2.canonical)(values);
}
function applyProviderOverlays(normalized, overlays) {
    for (const overlay of overlays.values())
        for (const { data } of bindings(normalized, overlay.ref)) {
            const mapping = (0, index_js_1.asRecord)(data.mapping);
            if (Object.keys(mapping).length) {
                const columns = Array.isArray(data.columns) && data.columns.length ? (0, index_js_2.clone)(data.columns) : Object.keys(mapping).map(id => ({ id }));
                const indices = columns.map(column => overlay.columns.findIndex(source => source.id === (0, index_js_1.asString)(mapping[(0, index_js_1.asString)(column.id)], (0, index_js_1.asString)(column.id))));
                if (indices.some(index => index < 0))
                    throw Error('A dataset mapping names a missing provider column.');
                data.columns = columns;
                data.rows = overlay.rows.map(row => indices.map(index => (0, index_js_2.clone)(row[index] ?? null)));
            }
            else {
                data.columns = (0, index_js_2.clone)(overlay.columns);
                data.rows = (0, index_js_2.clone)(overlay.rows);
            }
            data.revision = overlay.revision;
        }
}
async function stageProviderChanges(normalized, prior, dataRevisions, changes, context) {
    const overlays = new Map(prior), revisions = { ...dataRevisions };
    const changed = new Set();
    applyProviderOverlays(normalized, overlays);
    for (const change of changes) {
        await context.checkpoint(1);
        const matches = (0, index_js_1.listRecords)(normalized).filter(entry => entry.kind === 'source' && (entry.record.name === change.source || entry.record.id === change.source || entry.record.channel === change.source || entry.file + '::' + entry.record.name === change.source || entry.file + '::' + entry.ref.id === change.source));
        if (matches.length !== 1)
            throw Error('Unknown or ambiguous provider source: ' + change.source);
        const producer = matches[0], id = identity(producer.ref), previous = overlays.get(id), revisionKey = previous?.revisionKey ?? change.source;
        if (changed.has(id))
            throw Error('A coherent update contains one change per provider source.');
        changed.add(id);
        if (!change.next || change.next === (previous?.revision ?? revisions[revisionKey]))
            throw Error('Provider update must advance its revision.');
        const targets = bindings(normalized, producer.ref);
        if (!targets.length)
            throw Error('No dataset is bound to this provider source.');
        let columns, rows;
        if (change.kind === 'replace') {
            columns = columnsOf(change.schema);
            rows = [];
            for (const row of change.rows) {
                await context.checkpoint(1);
                rows.push(rowOf(row, columns));
            }
        }
        else {
            if (change.base !== (previous?.revision ?? revisions[revisionKey]))
                throw Error('Keyed update base does not match the provider data revision.');
            if (!previous && Object.keys((0, index_js_1.asRecord)(targets[0].data.mapping)).length)
                throw Error('A mapped keyed source requires an initial provider replacement.');
            columns = previous?.columns ?? columnsOf(targets[0].data.columns ?? []);
            const keys = sourceKeys(targets, columns), existing = previous?.rows ?? (0, index_js_1.asArray)(targets[0].data.rows).map(row => rowOf(row, columns));
            const keyed = new Map();
            for (const row of existing) {
                const key = rowKey(row, columns, keys);
                if (keyed.has(key))
                    throw Error('Provider rows contain duplicate keys.');
                keyed.set(key, (0, index_js_2.clone)(row));
            }
            const operated = new Set();
            for (const operation of change.operations) {
                await context.checkpoint(1);
                if (operated.has(operation.key))
                    throw Error('A keyed batch repeats an operation key.');
                operated.add(operation.key);
                if (operation.op === 'delete')
                    keyed.delete(operation.key);
                else {
                    const row = rowOf(operation.row, columns);
                    if (rowKey(row, columns, keys) !== operation.key)
                        throw Error('Upsert key differs from its row key.');
                    keyed.set(operation.key, row);
                }
            }
            rows = [...keyed.values()];
        }
        if (targets.some(({ data }) => (0, index_js_1.asArray)(data.key).length)) {
            const keys = sourceKeys(targets, columns), seen = new Set();
            for (const row of rows) {
                const key = rowKey(row, columns, keys);
                if (seen.has(key))
                    throw Error('Provider rows contain duplicate keys.');
                seen.add(key);
            }
        }
        overlays.set(id, { ref: producer.ref, revisionKey, revision: change.next, columns: (0, index_js_2.clone)(columns), rows });
        revisions[revisionKey] = change.next;
    }
    applyProviderOverlays(normalized, overlays);
    context.check();
    return { overlays, revisions };
}

},
"runtime/src/registry.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.registryPacks = registryPacks;
exports.registrations = registrations;
exports.createRegistry = createRegistry;
const index_js_1 = require("execution/src/index.js");
const registryData = new WeakMap();
const packData = new WeakMap();
function registryPacks(registry) { return packData.get(registry)?.() ?? []; }
function registrations(registry) {
    const read = registryData.get(registry);
    if (!read)
        throw new Error('Registry does not belong to this DDN implementation');
    return read();
}
function createRegistry(versions, onChange = () => { }) {
    const installed = new Map();
    function merged() {
        const packs = [...installed.values()];
        return (0, index_js_1.freeze)({
            profiles: packs.flatMap(p => p.registrations.profiles ?? []),
            rules: packs.flatMap(p => p.registrations.rules ?? []),
            commands: packs.flatMap(p => p.registrations.commands ?? []),
            projections: packs.flatMap(p => p.registrations.projections ?? []),
            schemas: Object.assign({}, ...packs.map(p => p.registrations.schemas ?? {})),
        });
    }
    const registry = {
        install(pack) {
            const m = pack.manifest;
            if (!m || !m.id || !m.version || !m.hash || m.api !== '1.0' || !Array.isArray(m.languages) || !Array.isArray(m.defaults) || !Array.isArray(m.dependencies) || !Array.isArray(m.profiles) || !Array.isArray(m.capabilities))
                throw new TypeError('Malformed pack manifest');
            if (!m.languages.includes(versions.language) || !m.defaults.includes(versions.defaults))
                throw new Error('Unsupported pack contract: ' + m.id);
            const expected = versions.packs[m.id];
            if (expected !== undefined && expected !== m.version)
                throw new Error('Pack version differs from selected version: ' + m.id);
            const existing = installed.get(m.id);
            if (existing) {
                if (existing.manifest.version === m.version && existing.manifest.hash === m.hash)
                    return;
                throw new Error('Incompatible duplicate pack: ' + m.id);
            }
            for (const dependency of m.dependencies)
                if (dependency === m.id || !installed.has(dependency))
                    throw new Error('Missing or cyclic pack dependency: ' + dependency);
            const current = merged(), incoming = pack.registrations;
            for (const key of ['profiles', 'rules', 'commands', 'projections']) {
                const identities = new Set((current[key] ?? []).map(v => v.id));
                for (const value of incoming[key] ?? []) {
                    if (!value.id || identities.has(value.id))
                        throw new Error('Duplicate ' + key + ' registration: ' + value.id);
                    identities.add(value.id);
                    if (key === 'profiles' && !m.profiles.includes(value.id))
                        throw new Error('Undeclared profile registration: ' + value.id);
                }
            }
            for (const name of Object.keys(incoming.schemas ?? {}))
                if (Object.hasOwn(current.schemas ?? {}, name))
                    throw new Error('Duplicate schema registration: ' + name);
            const copy = { manifest: (0, index_js_1.freeze)((0, index_js_1.clone)(m)), registrations: (0, index_js_1.freeze)({
                    ...(incoming.profiles ? { profiles: incoming.profiles.map(p => (0, index_js_1.freeze)((0, index_js_1.clone)(p))) } : {}),
                    ...(incoming.rules ? { rules: incoming.rules.map(p => (0, index_js_1.freeze)({ ...p, profiles: [...p.profiles], levels: [...p.levels], purposes: [...p.purposes], readPaths: [...p.readPaths] })) } : {}),
                    ...(incoming.commands ? { commands: incoming.commands.map(p => (0, index_js_1.freeze)({ ...p, profiles: [...p.profiles], propertyPaths: [...p.propertyPaths] })) } : {}),
                    ...(incoming.projections ? { projections: incoming.projections.map(p => (0, index_js_1.freeze)({ ...p, profiles: [...p.profiles], readPaths: [...p.readPaths] })) } : {}),
                    ...(incoming.schemas ? { schemas: (0, index_js_1.freeze)((0, index_js_1.clone)(incoming.schemas)) } : {}),
                }) };
            installed.set(m.id, copy);
            onChange();
        },
        describe() { return (0, index_js_1.freeze)([...installed.values()].map(p => p.manifest)); },
        supports(capability, profile) { return [...installed.values()].some(p => p.manifest.capabilities.includes(capability) && (!profile || p.manifest.profiles.includes(profile))); },
    };
    registryData.set(registry, merged);
    packData.set(registry, () => [...installed.values()]);
    return registry;
}

},
"runtime/src/runtime.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.STANDARD_VERSIONS = void 0;
exports.runtimeState = runtimeState;
exports.copySources = copySources;
exports.createRuntime = createRuntime;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("model/src/index.js");
const index_js_3 = require("verifier/src/index.js");
const index_js_4 = require("execution/src/index.js");
const registry_js_1 = require("runtime/src/registry.js");
const guards_js_1 = require("runtime/src/guards.js");
const providers_js_1 = require("runtime/src/providers.js");
const compute_js_1 = require("execution/src/compute.js");
const versions_js_1 = require("runtime/src/versions.js");
var versions_js_2 = require("runtime/src/versions.js");
Object.defineProperty(exports, "STANDARD_VERSIONS", { enumerable: true, get: function () { return versions_js_2.STANDARD_VERSIONS; } });
const states = new WeakMap();
function runtimeState(runtime) {
    const state = states.get(runtime);
    if (!state || state.disposed)
        throw new Error('Runtime is disposed or belongs to another implementation');
    return state;
}
function copySources(input) {
    return { entry: (0, index_js_2.normalizeLocation)(input.entry), files: input.files.map(file => {
            if (typeof file.text !== 'string' || typeof file.revision !== 'string' || !file.revision || file.encoding !== 'utf-8' || typeof file.writable !== 'boolean')
                throw Error('Malformed source file');
            const bytes = file.originalBytes === undefined ? undefined : new Uint8Array(file.originalBytes);
            if (bytes) {
                const decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
                if (decoded !== file.text && !(decoded.startsWith('\ufeff') && decoded.slice(1) === file.text))
                    throw Error('Source bytes do not match the decoded text');
            }
            return { ...file, id: (0, index_js_2.normalizeLocation)(file.id), ...(bytes ? { originalBytes: bytes } : {}) };
        }) };
}
const emptyCoverage = () => ({ scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: [] });
const diagnostic = (code, message) => ({ code, severity: 'error', message });
let sessionSequence = 0;
function createRuntime(inputOptions) {
    const options = { ...inputOptions, versions: (0, index_js_4.freeze)((0, index_js_4.clone)(inputOptions.versions)), packs: [...inputOptions.packs], ...(inputOptions.limits ? { limits: (0, index_js_4.freeze)((0, index_js_4.clone)(inputOptions.limits)) } : {}) };
    const listeners = new Set();
    let verifier;
    let overlays = new Map();
    let pendingSourceDiagnostics = [];
    const sessionId = 'ddn-runtime-' + (++sessionSequence);
    let jobSequence = 0;
    const state = { options, diagnostics: [], disposed: false, generation: 0, counter: 0, emit, materialize, async commitSources(source, task, expected, boundary) {
            let committed = false;
            const result = await openSources(source, task, false, true, expected, { check: () => boundary.check(), published(result) { committed = true; boundary.published(result); } });
            return { ...result, committed };
        } };
    function emit(event) {
        for (const listener of [...listeners]) {
            try {
                listener((0, index_js_4.freeze)(event));
            }
            catch { }
        }
    }
    const registry = (0, registry_js_1.createRegistry)(options.versions, () => {
        state.generation++;
        verifier?.destroy();
        verifier = undefined;
        if (!state.disposed)
            emit({ kind: 'capabilities' });
    });
    for (const pack of options.packs)
        registry.install(pack);
    const getVerifier = () => {
        if (state.disposed)
            throw new Error('Runtime is disposed');
        verifier ??= (0, index_js_3.createVerifier)({ ...options, packs: (0, registry_js_1.registryPacks)(registry) });
        return verifier;
    };
    const facade = { verifySources: (...args) => getVerifier().verifySources(...args), verifyModel: (snapshot, settings) => verify(snapshot, settings), checkTransition: (...args) => getVerifier().checkTransition(...args), destroy() { verifier?.destroy(); verifier = undefined; } };
    function failure(diagnostics, unavailable = [], publish = true) {
        const values = (0, index_js_4.freeze)([...diagnostics]);
        if (publish && !state.disposed) {
            state.diagnostics = values;
            emit({ kind: 'diagnostics', diagnostics: values });
        }
        return { revision: state.current?.revision ?? { model: '0', sources: {}, data: {} }, ...(state.current ? { snapshot: state.current } : {}), diagnostics: values, coverage: { ...emptyCoverage(), unavailable } };
    }
    function materialize(decoded) {
        if (!overlays.size)
            return decoded;
        const normalized = (0, index_js_4.clone)(decoded.normalized);
        (0, providers_js_1.applyProviderOverlays)(normalized, overlays);
        return { ...decoded, normalized };
    }
    function retainedEvidence(normalized) {
        return state.diagnostics.filter(item => {
            if (item.code !== 'runtime.acceptance-stale' || !item.target)
                return false;
            const record = (0, index_js_2.findRecord)(normalized, item.target), previous = state.current ? (0, index_js_2.findRecord)(state.current.normalized, item.target) : undefined;
            return !!record && ['accepted', 'in-review'].includes((0, index_js_2.asString)((0, index_js_2.asRecord)(record.design).state)) && (0, index_js_4.canonical)(record.acceptance) === (0, index_js_4.canonical)(previous?.acceptance);
        });
    }
    function effectiveTask(task) { return { ...(options.limits ? { budget: options.limits } : {}), ...task }; }
    async function decode(source, task) {
        if (!options.executor)
            return (0, index_js_1.decodeSources)(source, { ...task, ...(state.decoded ? { previous: state.decoded } : {}) });
        const request = { protocol: 1, sessionId, jobId: String(++jobSequence), kind: 'decode', revision: state.current?.revision ?? { model: '0', sources: {}, data: {} }, versions: options.versions, dependencyFingerprint: (0, index_js_4.fingerprint)(source.files.map(({ originalBytes: _, ...file }) => file)), fontGeneration: '0', styleGeneration: '0', payload: (0, compute_js_1.decodePayload)(source, state.decoded) };
        const result = await options.executor.run(request, task), { payload: _, ...echo } = request;
        if ((0, index_js_4.canonical)(result.request) !== (0, index_js_4.canonical)(echo))
            throw Error('Executor returned a mismatched request envelope.');
        if (result.outcome === 'cancelled' || result.outcome === 'budget-exceeded')
            throw new index_js_4.ComputationStopped(result.outcome, result.diagnostics.map(d => d.message).join('; '));
        const value = (0, index_js_2.asRecord)(result.payload);
        if (!(0, index_js_2.isRecord)(value.decoded))
            throw Error(result.diagnostics.map(d => d.message).join('; ') || 'Executor returned no decoded source.');
        const decoded = value.decoded;
        if (value.fingerprint !== (0, index_js_4.fingerprint)(decoded.normalized))
            throw Error('Executor returned an inconsistent decoded fingerprint.');
        return decoded;
    }
    async function verify(snapshot, settings) {
        const currentPacks = (0, registry_js_1.registryPacks)(registry);
        if (!options.executor || (0, index_js_4.canonical)(currentPacks.map(pack => pack.manifest)) !== (0, index_js_4.canonical)(options.packs.map(pack => pack.manifest)))
            return getVerifier().verifyModel(snapshot, settings);
        const { cancel, budget, ...plain } = settings;
        const request = { protocol: 1, sessionId, jobId: String(++jobSequence), kind: 'verify', revision: snapshot.revision, versions: snapshot.versions, dependencyFingerprint: snapshot.semanticFingerprint, fontGeneration: settings.measurement?.fontGeneration ?? '0', styleGeneration: '0', payload: { snapshot: snapshot, options: plain } };
        const result = await options.executor.run(request, { ...(cancel ? { cancel } : {}), ...(budget ? { budget } : {}) }), { payload: _, ...echo } = request;
        if ((0, index_js_4.canonical)(result.request) !== (0, index_js_4.canonical)(echo))
            throw Error('Executor returned a mismatched verification envelope.');
        const payload = (0, index_js_2.asRecord)(result.payload);
        if (!payload.requestId)
            return (0, index_js_4.freeze)({ requestId: 'execution-' + request.jobId, outcome: result.outcome, revision: snapshot.revision, versions: snapshot.versions, dependencyFingerprint: snapshot.semanticFingerprint, scope: settings.scope, purpose: settings.purpose, level: settings.level, coverage: result.coverage, diagnostics: result.diagnostics, missing: result.coverage.unavailable, ruleVersions: {}, reviewEligible: false, stats: { elapsedMs: 0, workUnits: 0, cacheHits: 0 } });
        const report = payload;
        if ((0, index_js_4.canonical)(report.revision) !== (0, index_js_4.canonical)(snapshot.revision) || report.dependencyFingerprint !== snapshot.semanticFingerprint || (0, index_js_4.canonical)(report.versions) !== (0, index_js_4.canonical)(snapshot.versions) || (0, index_js_4.canonical)(report.scope) !== (0, index_js_4.canonical)(settings.scope) || report.purpose !== settings.purpose || report.level !== settings.level || report.outcome !== result.outcome)
            throw Error('Executor verification evidence does not match the requested snapshot.');
        return (0, index_js_4.freeze)(report);
    }
    function supported() { return options.versions.api === '1.0' && options.versions.language === 'ddn-next-1' && options.versions.defaults === 'ddn-next-1'; }
    async function openSources(input, task = {}, retainBrokenBuffer = true, preserveData = false, expectedFingerprint, boundary) {
        if (state.disposed)
            return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
        if (!supported())
            return failure([diagnostic('runtime.contract', 'Unsupported language/default contract')]);
        const generation = ++state.generation;
        try {
            const context = (0, index_js_4.createContext)(options.versions, effectiveTask(task));
            context.check();
            context.accountMemory(input.files.reduce((n, f) => n + f.text.length * 2, 0));
            const source = copySources(input);
            if (new Set(source.files.map(f => f.id)).size !== source.files.length)
                return failure([diagnostic('runtime.files', 'Ambiguous duplicate logical file identities')]);
            const raw = await decode(source, effectiveTask(task));
            const parsed = preserveData ? materialize(raw) : raw;
            await context.checkpoint(source.files.length);
            if (generation !== state.generation)
                return failure([diagnostic('runtime.stale', 'A newer source operation superseded this request')], [], false);
            if (!parsed.syntaxValid) {
                if (retainBrokenBuffer) {
                    state.source = source;
                    pendingSourceDiagnostics = (0, index_js_4.freeze)([...parsed.diagnostics]);
                }
                return failure(parsed.diagnostics, parsed.coverage.unavailable);
            }
            const digest = (0, index_js_4.fingerprint)(parsed.normalized);
            const modelRevision = state.current?.semanticFingerprint === digest ? state.current.revision.model : String(state.counter + 1);
            const candidate = (0, index_js_4.freeze)({ contract: 'ddn-next-1', rootFile: parsed.normalized.entry, normalized: parsed.normalized, versions: options.versions, semanticFingerprint: digest, revision: { model: modelRevision, sources: Object.fromEntries(source.files.map(f => [f.id, f.revision])), data: preserveData ? state.current?.revision.data ?? {} : {} }, coverage: parsed.coverage });
            if (expectedFingerprint && candidate.semanticFingerprint !== expectedFingerprint)
                return failure([diagnostic('runtime.prepared-mismatch', 'Prepared model differs from the candidate; no edit was committed.')]);
            const report = await verify(candidate, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...effectiveTask(task) });
            context.check();
            if (generation !== state.generation)
                return failure([diagnostic('runtime.stale', 'A newer source operation superseded this request')], [], false);
            const diagnostics = [...parsed.diagnostics, ...report.diagnostics, ...(preserveData ? retainedEvidence(candidate.normalized) : [])];
            if (report.outcome === 'cancelled' || report.outcome === 'budget-exceeded' || report.outcome === 'invalid' || report.outcome === 'stale') {
                if (retainBrokenBuffer && report.outcome === 'invalid') {
                    state.source = source;
                    pendingSourceDiagnostics = (0, index_js_4.freeze)(diagnostics);
                }
                return failure(diagnostics, report.missing);
            }
            if (boundary) {
                const rejected = await boundary.check();
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'A newer operation superseded command publication')], [], false);
                if (rejected.length)
                    return failure(rejected);
            }
            if (!preserveData)
                overlays.clear();
            pendingSourceDiagnostics = [];
            state.source = source;
            state.counter = Math.max(state.counter, Number(modelRevision) || 0);
            state.decoded = parsed;
            state.current = candidate;
            state.diagnostics = (0, index_js_4.freeze)(diagnostics);
            const result = { snapshot: candidate, revision: candidate.revision, diagnostics: state.diagnostics, coverage: candidate.coverage };
            boundary?.published(result);
            emit({ kind: 'revision', revision: candidate.revision });
            emit({ kind: 'diagnostics', diagnostics: state.diagnostics, revision: candidate.revision });
            return result;
        }
        catch (error) {
            return failure([diagnostic(error instanceof index_js_4.ComputationStopped ? 'runtime.' + error.outcome : 'runtime.open', error instanceof Error ? error.message : 'Unable to open source')], [], generation === state.generation && !state.disposed);
        }
    }
    const runtime = {
        registry, verifier: facade,
        async open(input, task = {}) {
            if ('entry' in input)
                return openSources(input, task);
            if (state.disposed)
                return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
            const generation = ++state.generation;
            try {
                if (!supported() || input.contract !== 'ddn-next-1' || input.versions.language !== options.versions.language || input.versions.defaults !== options.versions.defaults)
                    return failure([diagnostic('runtime.contract', 'Snapshot version is unsupported')]);
                const context = (0, index_js_4.createContext)(options.versions, effectiveTask(task));
                context.check();
                context.accountMemory((0, index_js_4.canonical)(input.normalized).length * 2);
                const snapshot = (0, index_js_4.freeze)({ ...(0, index_js_4.clone)(input), semanticFingerprint: (0, index_js_4.fingerprint)(input.normalized) });
                const report = await verify(snapshot, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...effectiveTask(task) });
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'A newer operation superseded this snapshot')], [], false);
                if (['invalid', 'cancelled', 'budget-exceeded', 'stale'].includes(report.outcome))
                    return failure(report.diagnostics, report.missing);
                overlays.clear();
                pendingSourceDiagnostics = [];
                state.counter = Math.max(state.counter, Number(snapshot.revision.model) || 0);
                state.current = snapshot;
                delete state.source;
                delete state.decoded;
                state.diagnostics = report.diagnostics;
                emit({ kind: 'revision', revision: snapshot.revision });
                emit({ kind: 'diagnostics', diagnostics: report.diagnostics });
                return { snapshot, revision: snapshot.revision, diagnostics: report.diagnostics, coverage: snapshot.coverage };
            }
            catch (error) {
                return failure([diagnostic(error instanceof index_js_4.ComputationStopped ? 'runtime.' + error.outcome : 'runtime.snapshot', error instanceof Error ? error.message : 'Invalid snapshot')], [], generation === state.generation && !state.disposed);
            }
        },
        snapshot() { return state.current; },
        sources() { return state.source ? (0, index_js_4.freeze)(copySources(state.source)) : undefined; },
        async ingest(input, task = {}) {
            if (state.disposed)
                return failure([diagnostic('runtime.disposed', 'Runtime is disposed')]);
            let update;
            try {
                const { sources, ...data } = input;
                (0, index_js_4.canonical)(data);
                update = { ...(0, index_js_4.clone)(data), ...(sources ? { sources: copySources({ entry: state.source?.entry ?? '', files: sources }).files } : {}) };
            }
            catch (error) {
                return failure([diagnostic('data.update', error instanceof Error ? error.message : 'Invalid provider update')]);
            }
            const previous = state.current;
            if (!previous || (0, index_js_4.canonical)(update.base) !== (0, index_js_4.canonical)(previous.revision))
                return failure([diagnostic('runtime.conflict', 'External update does not match the current revision vector')]);
            if (!update.origin)
                return failure([diagnostic('runtime.origin', 'External update must identify its provider')]);
            const generation = ++state.generation;
            task = effectiveTask(task);
            try {
                const context = (0, index_js_4.createContext)(options.versions, task);
                context.check();
                let source = state.source ? copySources(state.source) : undefined, decoded = state.decoded;
                const pendingBuffer = !update.sources?.length && !!source && !!decoded && decoded.documents.some(document => source.files.find(file => file.id === document.file.id)?.text !== document.file.text);
                if (update.sources?.length) {
                    if (!source)
                        throw Error('No editable source set is loaded.');
                    const replacements = new Map();
                    for (const file of update.sources) {
                        const id = (0, index_js_2.normalizeLocation)(file.id);
                        if (replacements.has(id))
                            throw Error('External update repeats a source file.');
                        const old = source.files.find(value => value.id === id);
                        if (!old)
                            throw Error('External update targets an unavailable file: ' + id);
                        if (!file.revision || file.text !== old.text && file.revision === old.revision)
                            throw Error('Changed source text requires a new revision.');
                        replacements.set(id, { ...file, id });
                    }
                    source = copySources({ entry: source.entry, files: source.files.map(file => replacements.get(file.id) ?? file) });
                    context.accountMemory(source.files.reduce((size, file) => size + file.text.length * 2, 0));
                    decoded = await decode(source, task);
                    if (generation !== state.generation || state.disposed)
                        return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                    if (!decoded.syntaxValid)
                        return failure(decoded.diagnostics, decoded.coverage.unavailable);
                }
                const normalized = (0, index_js_4.clone)(decoded ? decoded.normalized : previous.normalized);
                context.accountMemory((0, index_js_4.canonical)(normalized).length * 2 + (0, index_js_4.canonical)(update.data ?? []).length * 2);
                (0, providers_js_1.applyProviderOverlays)(normalized, overlays);
                const lifecycle = (0, guards_js_1.checkLifecycleMutation)(previous.normalized, normalized);
                if (lifecycle.length)
                    return failure(lifecycle);
                const protectedScopes = (0, guards_js_1.affectedProtected)(previous, normalized);
                if (protectedScopes.length)
                    return failure(protectedScopes.map(target => ({ ...diagnostic('runtime.protected', 'Reopen this protected scope before changing its authored dependencies.'), target })));
                const staged = await (0, providers_js_1.stageProviderChanges)(normalized, overlays, previous.revision.data, update.data ?? [], context);
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                const staleEvidence = (0, guards_js_1.affectedProtected)(previous, normalized).map(target => ({ code: 'runtime.acceptance-stale', severity: 'warning', message: 'Live data changed. Stored design status is retained; review or acceptance evidence requires fresh verification.', target }));
                const digest = (0, index_js_4.fingerprint)(normalized), model = previous.semanticFingerprint === digest ? previous.revision.model : String(state.counter + 1);
                const next = (0, index_js_4.freeze)({ ...previous, normalized, semanticFingerprint: digest, coverage: decoded?.coverage ?? previous.coverage, revision: { model, sources: source && !pendingBuffer ? Object.fromEntries(source.files.map(file => [file.id, file.revision])) : previous.revision.sources, data: staged.revisions } });
                const report = await verify(next, { scope: { kind: 'workarea' }, purpose: 'design', level: 'structural', ...task });
                context.check();
                if (generation !== state.generation || state.disposed)
                    return failure([diagnostic('runtime.stale', 'Provider update was superseded.')], [], false);
                if (['invalid', 'cancelled', 'budget-exceeded', 'stale'].includes(report.outcome))
                    return failure(report.diagnostics, report.missing);
                const retained = retainedEvidence(normalized);
                overlays = staged.overlays;
                state.counter = Math.max(state.counter, Number(model) || 0);
                state.current = next;
                if (!pendingBuffer)
                    pendingSourceDiagnostics = [];
                if (source)
                    state.source = source;
                if (decoded)
                    state.decoded = { ...decoded, normalized: normalized };
                state.diagnostics = (0, index_js_4.freeze)([...(decoded?.diagnostics ?? []), ...pendingSourceDiagnostics, ...report.diagnostics, ...retained.filter(old => !staleEvidence.some(current => (0, index_js_4.canonical)(current.target) === (0, index_js_4.canonical)(old.target))), ...staleEvidence]);
                emit({ kind: 'revision', revision: next.revision });
                emit({ kind: 'diagnostics', ...(!pendingBuffer ? { revision: next.revision } : {}), diagnostics: state.diagnostics });
                return { snapshot: next, revision: next.revision, coverage: next.coverage, diagnostics: state.diagnostics };
            }
            catch (error) {
                return failure([diagnostic(error instanceof index_js_4.ComputationStopped ? 'runtime.' + error.outcome : 'data.update', error instanceof Error ? error.message : 'Provider update failed')], [], generation === state.generation && !state.disposed);
            }
        },
        subscribe(listener) {
            if (state.disposed)
                return () => { };
            listeners.add(listener);
            return () => { listeners.delete(listener); };
        },
        destroy() {
            if (state.disposed)
                return;
            state.disposed = true;
            state.generation++;
            verifier?.destroy();
            options.executor?.destroy();
            emit({ kind: 'disposed' });
            listeners.clear();
            overlays.clear();
            delete state.source;
            delete state.decoded;
            delete state.current;
        },
    };
    states.set(runtime, state);
    return runtime;
}

},
"standalone/src/modular-runtime.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createModularRuntime = createModularRuntime;
exports.attachModularRuntime = attachModularRuntime;
const core_js_1 = require("profiles/src/core.js");
const family_packs_js_1 = require("profiles/src/family-packs.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const registry_js_1 = require("runtime/src/registry.js");
const profile_loading_js_1 = require("runtime/src/profile-loading.js");
const index_js_1 = require("model/src/index.js");
const modular_loading_js_1 = require("standalone/src/modular-loading.js");
function createModularRuntime(options = (0, modular_loading_js_1.createModularBrowserOptions)(), drawing = true) {
    return attachModularRuntime((0, runtime_js_1.createRuntime)(options), drawing);
}
function openFailure(runtime, error) {
    const snapshot = runtime.snapshot();
    return { ...(snapshot ? { snapshot } : {}), revision: snapshot?.revision ?? { model: '0', sources: {}, data: {} }, diagnostics: [(0, modular_loading_js_1.loadingDiagnostic)(error)], coverage: { scope: { kind: 'workarea' }, complete: false, checked: [], unavailable: ['profile-loading'] } };
}
const managed = new WeakMap();
function attachModularRuntime(runtime, drawing = true) {
    const previous = managed.get(runtime);
    if (previous) {
        previous.drawing ||= drawing;
        return runtime;
    }
    const state = { drawing, disposed: false, sequence: 0 }, modelState = (0, runtime_js_1.runtimeState)(runtime), options = modelState.options;
    managed.set(runtime, state);
    const effective = (task = {}) => ({ ...(options.limits ? { budget: options.limits } : {}), ...task });
    const live = () => {
        if (state.disposed)
            throw new modular_loading_js_1.HostStopped('disposed', 'Runtime is disposed.');
    };
    const ensure = async (input, task = {}, guard = live) => {
        live();
        guard();
        const drawingBefore = state.drawing;
        await (0, modular_loading_js_1.ensureProfileInput)(input, drawingBefore, task);
        live();
        guard();
        if (state.drawing && !drawingBefore)
            await (0, modular_loading_js_1.ensureProfileInput)(input, true, task);
        live();
        guard();
        const installed = runtime.registry.describe(), ids = new Set(installed.map(pack => pack.id));
        const profiles = new Set(((0, registry_js_1.registrations)(runtime.registry).profiles ?? []).map(profile => profile.id));
        for (const pack of (0, family_packs_js_1.loadedProfilePacks)()) {
            if (ids.has(pack.manifest.id) || pack.manifest.profiles.every(profile => profiles.has(profile)))
                continue;
            runtime.registry.install(pack);
        }
    };
    (0, profile_loading_js_1.attachProfileLoadingHost)(runtime, { profiles: core_js_1.completeProfileIds.map(id => ({ id, method: (0, core_js_1.knownProfile)(id).method })), ensure: (input, task) => ensure(input, effective(task)) });
    const open = runtime.open.bind(runtime), ingest = runtime.ingest.bind(runtime), destroy = runtime.destroy.bind(runtime);
    const operation = () => {
        const sequence = ++state.sequence;
        if (!state.disposed)
            modelState.generation++;
        return () => {
            live();
            if (sequence !== state.sequence)
                throw new modular_loading_js_1.HostStopped('stale', 'A newer operation superseded profile loading.');
        };
    };
    runtime.open = async (input, task) => {
        const guard = operation(), started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget, guard);
            guard();
            return open(input, (0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)));
        }
        catch (error) {
            return openFailure(runtime, error);
        }
    };
    runtime.ingest = async (update, task) => {
        const guard = operation(), started = Date.now(), budget = effective(task);
        try {
            guard();
            const source = runtime.sources();
            let units = 0;
            if (update.sources?.length && source) {
                const changes = new Map(update.sources.map(file => [(0, index_js_1.normalizeLocation)(file.id), { ...file, id: (0, index_js_1.normalizeLocation)(file.id) }]));
                const merged = { ...source, files: source.files.map(file => changes.get(file.id) ?? file) };
                units = (0, modular_loading_js_1.scanUnits)(merged);
                await ensure(merged, budget, guard);
            }
            guard();
            return ingest(update, (0, modular_loading_js_1.remainingTask)(budget, started, units));
        }
        catch (error) {
            return openFailure(runtime, error);
        }
    };
    const sourceVerify = runtime.verifier.verifySources.bind(runtime.verifier), modelVerify = runtime.verifier.verifyModel.bind(runtime.verifier), transition = runtime.verifier.checkTransition.bind(runtime.verifier);
    runtime.verifier.verifySources = async (input, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return sourceVerify(input, { ...task, ...(0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)) });
        }
        catch (error) {
            return (0, modular_loading_js_1.verificationFailure)(input, task, options.versions, error, started);
        }
    };
    runtime.verifier.verifyModel = async (input, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return modelVerify(input, { ...task, ...(0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)) });
        }
        catch (error) {
            return (0, modular_loading_js_1.verificationFailure)(input, task, options.versions, error, started);
        }
    };
    runtime.verifier.checkTransition = async (input, request, task) => {
        const started = Date.now(), budget = effective(task);
        try {
            await ensure(input, budget);
            return transition(input, request, (0, modular_loading_js_1.remainingTask)(budget, started, (0, modular_loading_js_1.scanUnits)(input)));
        }
        catch (error) {
            return { allowed: false, diagnostics: [(0, modular_loading_js_1.loadingDiagnostic)(error, 'DDN-PROFILE-LOAD')] };
        }
    };
    runtime.destroy = () => {
        if (state.disposed)
            return;
        state.disposed = true;
        state.sequence++;
        destroy();
    };
    return runtime;
}

},
"standalone/src/modular-viewer.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getViewerHandle = void 0;
exports.createViewer = createViewer;
const native_js_1 = require("viewer/src/native.js");
Object.defineProperty(exports, "getViewerHandle", { enumerable: true, get: function () { return native_js_1.getViewerHandle; } });
const modular_runtime_js_1 = require("standalone/src/modular-runtime.js");
const modular_loading_js_1 = require("standalone/src/modular-loading.js");
function createViewer(element, options = { runtimeOptions: (0, modular_loading_js_1.createModularBrowserOptions)() }) {
    const owned = !options.runtime;
    const runtime = options.runtime ? (0, modular_runtime_js_1.attachModularRuntime)(options.runtime) : (0, modular_runtime_js_1.createModularRuntime)(options.runtimeOptions ?? (0, modular_loading_js_1.createModularBrowserOptions)());
    const { runtime: _, runtimeOptions: __, ...settings } = options;
    const viewer = (0, native_js_1.createViewer)(element, { ...settings, runtime });
    if (owned) {
        const destroy = viewer.destroy.bind(viewer);
        viewer.destroy = () => { destroy(); runtime.destroy(); };
    }
    return viewer;
}

},
"viewer/src/core.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFontResources = exports.loadFontFile = exports.listFonts = exports.installFontResources = exports.UI_THEME_TOKEN_NAMES = exports.UI_THEME_NAMES = exports.installUITheme = exports.setUITheme = void 0;
exports.getViewerHandle = getViewerHandle;
exports.renderPreviewPrimitives = renderPreviewPrimitives;
exports.createViewer = createViewer;
const drawer_js_1 = require("viewer/src/drawer.js");
const side_tabs_js_1 = require("viewer/src/side-tabs.js");
const svg_assets_js_1 = require("viewer/src/svg-assets.js");
const adapters_js_1 = require("presentation/src/adapters.js");
const registry_js_1 = require("runtime/src/registry.js");
const native_js_1 = require("runtime/src/native.js");
const index_js_1 = require("defaults/src/index.js");
const native_js_2 = require("presentation/src/native.js");
const ui_theme_js_1 = require("viewer/src/ui-theme.js");
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
const dialogs_js_1 = require("viewer/src/dialogs.js");
const fonts_js_1 = require("viewer/src/fonts.js");
const texture_js_1 = require("viewer/src/texture.js");
const ui_commands_js_1 = require("viewer/src/ui-commands.js");
const grid_js_1 = require("viewer/src/grid.js");
const status_hint_js_1 = require("viewer/src/status-hint.js");
const standalone_viewport_js_1 = require("viewer/src/standalone-viewport.js");
var ui_theme_js_2 = require("viewer/src/ui-theme.js");
Object.defineProperty(exports, "setUITheme", { enumerable: true, get: function () { return ui_theme_js_2.setUITheme; } });
Object.defineProperty(exports, "installUITheme", { enumerable: true, get: function () { return ui_theme_js_2.installUITheme; } });
Object.defineProperty(exports, "UI_THEME_NAMES", { enumerable: true, get: function () { return ui_theme_js_2.UI_THEME_NAMES; } });
Object.defineProperty(exports, "UI_THEME_TOKEN_NAMES", { enumerable: true, get: function () { return ui_theme_js_2.UI_THEME_TOKEN_NAMES; } });
var fonts_js_2 = require("viewer/src/fonts.js");
Object.defineProperty(exports, "installFontResources", { enumerable: true, get: function () { return fonts_js_2.installFontResources; } });
Object.defineProperty(exports, "listFonts", { enumerable: true, get: function () { return fonts_js_2.listFonts; } });
Object.defineProperty(exports, "loadFontFile", { enumerable: true, get: function () { return fonts_js_2.loadFontFile; } });
Object.defineProperty(exports, "getFontResources", { enumerable: true, get: function () { return fonts_js_2.getFontResources; } });
const NS = 'http://www.w3.org/2000/svg';
function displayTableData(snapshot, item) { return item.record.profile === 'table.records@1' ? (0, native_js_2.recordTableData)(snapshot, item) : (0, native_js_2.tableData)(snapshot, item); }
const handles = new WeakMap();
function getViewerHandle(viewer) {
    const handle = handles.get(viewer);
    if (!handle)
        throw new Error('Viewer is not active');
    return handle;
}
function cssPaint(value) { const valueString = String(value); return /url\s*\(|expression\s*\(|[<>]/i.test(valueString) ? 'none' : valueString; }
function backgroundPrimitive(bounds, fill, texture) { return { kind: 'path', d: `M${bounds.x},${bounds.y}h${bounds.width}v${bounds.height}h${-bounds.width}Z`, paint: { fill: cssPaint(fill), ...(texture ? { 'ddn-texture': texture } : {}) } }; }
function svgElement(document, name, attrs = {}) {
    const element = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs))
        element.setAttribute(key, String(value));
    return element;
}
function realize(document, primitive, assets, effect) {
    let result;
    if (primitive.kind === 'path')
        result = svgElement(document, 'path', { d: primitive.d });
    else if (primitive.kind === 'rect')
        result = svgElement(document, 'rect', { ...primitive.bounds, rx: 4 });
    else if (primitive.kind === 'ellipse') {
        const b = primitive.bounds;
        result = svgElement(document, 'ellipse', { cx: b.x + b.width / 2, cy: b.y + b.height / 2, rx: b.width / 2, ry: b.height / 2 });
    }
    else if (primitive.kind === 'text') {
        result = svgElement(document, 'text');
        for (const run of primitive.runs) {
            const span = svgElement(document, 'tspan', { x: run.x, y: run.y, 'font-family': (0, fonts_js_1.fontFamily)(run.fontKey) });
            span.textContent = run.text;
            for (const [key, value] of Object.entries(run.style))
                if (['font-size', 'font-weight', 'font-style', 'font-variant', 'text-decoration', 'text-anchor', 'fill', 'opacity'].includes(key))
                    span.setAttribute(key, cssPaint(value));
            result.append(span);
        }
        return result;
    }
    else if (primitive.kind === 'image' && assets.has(primitive.assetId)) {
        result = svgElement(document, 'image', { ...primitive.bounds, href: assets.get(primitive.assetId).dataURL, preserveAspectRatio: 'xMidYMid meet' });
        return result;
    }
    else {
        result = svgElement(document, 'g');
        result.append(svgElement(document, 'rect', { ...primitive.bounds, fill: '#e5e7eb', stroke: '#94a3b8' }));
        const title = svgElement(document, 'title');
        title.textContent = `Asset ${'assetId' in primitive ? primitive.assetId : 'unknown'} requires a supplied provider`;
        result.append(title);
        return result;
    }
    if ('paint' in primitive)
        for (const [key, value] of Object.entries(primitive.paint))
            if (['fill', 'fill-rule', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'fill-opacity', 'stroke-opacity', 'rx', 'ry'].includes(key))
                result.setAttribute(key, cssPaint(value));
    if ('paint' in primitive) {
        const state = primitive.paint['ddn-design-status'];
        if (typeof state === 'string') {
            const title = svgElement(document, 'title');
            title.textContent = (0, status_hint_js_1.statusHint)(state);
            result.append(title);
            result.setAttribute('data-status-dot', state);
            result.setAttribute('aria-label', title.textContent);
            result.setAttribute('role', 'img');
        }
        const pattern = (0, texture_js_1.createTexturePattern)(document, effect.id + '-texture', primitive.paint['ddn-texture'], cssPaint(primitive.paint.fill ?? 'transparent'));
        if (pattern) {
            const group = svgElement(document, 'g'), defs = svgElement(document, 'defs');
            defs.append(pattern);
            result.setAttribute('fill', `url(#${pattern.id})`);
            group.append(defs, result);
            return group;
        }
        const decoration = primitive.paint['ddn-decoration'];
        if (decoration === 'shadow' || decoration === 'attachment') {
            result.setAttribute('pointer-events', 'none');
            result.setAttribute('aria-hidden', 'true');
        }
        const blur = primitive.paint.blur;
        if (typeof blur === 'number' && Number.isFinite(blur) && blur > 0 && blur <= 128) {
            const group = svgElement(document, 'g'), defs = svgElement(document, 'defs');
            const filter = svgElement(document, 'filter', { id: effect.id, filterUnits: 'userSpaceOnUse', ...effect.bounds, 'color-interpolation-filters': 'sRGB' });
            filter.append(svgElement(document, 'feGaussianBlur', { stdDeviation: blur }));
            defs.append(filter);
            result.setAttribute('filter', `url(#${effect.id})`);
            group.append(defs, result);
            return group;
        }
    }
    return result;
}
function renderPreviewPrimitives(document, primitives, bounds) {
    const group = svgElement(document, 'g');
    const assets = new Map();
    for (const primitive of primitives)
        group.append(realize(document, primitive, assets, { id: 'ddn-glyph-preview', bounds }));
    return group;
}
function serializeScene(document, items, bounds, assets = new Map(), background = 'transparent', texture) {
    const svg = svgElement(document, 'svg', { viewBox: `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`, width: bounds.width, height: bounds.height, role: 'img' });
    const css = (0, fonts_js_1.fontCSS)(document, items.flatMap(item => item.primitives.flatMap(p => p.kind === 'text' ? p.runs.map(run => run.fontKey) : [])));
    if (css) {
        const style = svgElement(document, 'style');
        style.textContent = css;
        svg.append(style);
    }
    svg.append(texture
        ? realize(document, backgroundPrimitive(bounds, background, texture), assets, { id: 'ddn-export-background', bounds })
        : svgElement(document, 'rect', { ...bounds, fill: cssPaint(background) }));
    for (const item of items) {
        const group = svgElement(document, 'g', { 'data-occurrence': item.occurrence });
        const title = svgElement(document, 'title');
        title.textContent = item.accessible.label;
        group.append(title);
        appendItem(document, group, item, assets);
        svg.append(group);
    }
    const Serializer = document.defaultView?.XMLSerializer ?? XMLSerializer;
    return new Serializer().serializeToString(svg);
}
function appendItem(document, group, item, assets, clipPrefix = 'ddn-export') {
    const content = svgElement(document, 'g', { transform: `matrix(${item.transform.join(' ')})` });
    const hasBlur = item.primitives.some(p => 'paint' in p && typeof p.paint.blur === 'number' && p.paint.blur > 0);
    const encoded = item.clip || hasBlur || item.primitives.some(p => 'paint' in p && p.paint['ddn-texture']) ? Array.from(item.occurrence).map(c => c.codePointAt(0).toString(16)).join('-') : '';
    const localBounds = hasBlur ? localPaintBounds(item) : item.bounds;
    for (const [index, primitive] of item.primitives.entries())
        content.append(realize(document, primitive, assets, { id: `${clipPrefix}-blur-${encoded}-${index}`, bounds: localBounds }));
    if (item.clip) {
        const id = clipPrefix + '-clip-' + encoded;
        const defs = svgElement(document, 'defs'), clip = svgElement(document, 'clipPath', { id, clipPathUnits: 'userSpaceOnUse' });
        clip.append(svgElement(document, 'rect', { ...item.clip }));
        defs.append(clip);
        group.append(defs);
        const clipped = svgElement(document, 'g', { 'clip-path': `url(#${id})` });
        clipped.append(content);
        group.append(clipped);
    }
    else
        group.append(content);
}
function localPaintBounds(item) {
    const [a, b, c, d, tx, ty] = item.transform, determinant = a * d - b * c;
    if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12)
        return item.bounds;
    const box = item.bounds;
    const points = [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]].map(([x, y]) => ({ x: (d * (x - tx) - c * (y - ty)) / determinant, y: (-b * (x - tx) + a * (y - ty)) / determinant }));
    const x = Math.min(...points.map(p => p.x)), y = Math.min(...points.map(p => p.y));
    return { x, y, width: Math.max(1, ...points.map(p => p.x - x)), height: Math.max(1, ...points.map(p => p.y - y)) };
}
function intersects(a, b) { return a.x <= b.x + b.width && a.x + a.width >= b.x && a.y <= b.y + b.height && a.y + a.height >= b.y; }
function createViewer(element, options) {
    const document = element.ownerDocument, win = document.defaultView;
    if (!win)
        throw new Error('Viewer needs a browser document');
    const clipPrefix = 'ddn-viewer-' + (win.crypto?.randomUUID?.() ?? Date.now().toString(36) + Math.random().toString(36).slice(2));
    const ownsRuntime = !options.runtime;
    const runtime = options.runtime ?? (0, native_js_1.createRuntime)(options.runtimeOptions);
    let disposed = false, projection, currentSnapshot, selection, selectedOccurrence;
    const selectedOccurrences = new Set();
    let spaceHeld = false, announceHoldUntil = 0;
    let viewport = { bounds: { x: 0, y: 0, width: 1280, height: 800 }, zoom: 1 };
    let preview;
    let stale = false, diagnostics = [];
    let runtimeDiagnostics = [];
    let generation = 0;
    let styleGeneration = 0, fontGeneration = 0;
    let rendering = Promise.resolve();
    let workareaBackground = '#f2f4f7';
    let workareaTexture;
    const fontsReady = (0, fonts_js_1.installFontResources)(document);
    const assets = new Map();
    const assetSizes = () => new Map([...assets].flatMap(([id, asset]) => asset.intrinsicSize ? [[id, asset.intrinsicSize]] : []));
    const geography = new Map();
    const geographyHashes = new Map();
    const geographyVersions = new Map();
    const assetFailures = new Set();
    const openListeners = new Set();
    const listeners = new Set(), selectionListeners = new Set();
    const cleanups = [];
    const history = [];
    let historyIndex = -1;
    let restored;
    let drag;
    let expandedView;
    let standalone = false;
    let miniCards;
    const pointers = new Map();
    let pinch;
    let gestureStart;
    const LOD_SCALE = 0.32;
    const container = document.createElement('section');
    container.className = 'ddn-viewer';
    (0, ui_theme_js_1.installUITheme)(container);
    container.style.height = element.clientHeight > 0 ? '100%' : '600px';
    container.setAttribute('aria-label', 'DDN diagram viewer');
    container.tabIndex = -1;
    const style = document.createElement('style');
    style.textContent = `
.ddn-viewer{font:var(--ddn-ui-font-size) Inter,system-ui,sans-serif;color:var(--ddn-ui-text);display:grid;grid-template-columns:250px minmax(0,1fr);grid-template-rows:auto minmax(200px,1fr) auto;min-height:420px;position:relative;overflow:hidden;background:var(--ddn-ui-bg);border:1px solid var(--ddn-ui-border);border-radius:12px}
.ddn-viewer *{box-sizing:border-box}.ddn-viewer button,.ddn-viewer input,.ddn-viewer select,.ddn-viewer textarea{font:inherit}
.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid transparent;border-radius:8px;background:transparent;color:inherit;padding:6px 8px;min-height:32px;cursor:pointer;font-size:12px;font-weight:500}
.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 10%,var(--ddn-ui-surface));color:var(--ddn-ui-accent)}.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button:disabled{opacity:.45;cursor:default}.ddn-viewer button:focus-visible,.ddn-viewer [tabindex]:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-viewer-toolbar{grid-column:1/-1;display:flex;gap:4px;align-items:center;padding:8px 10px;background:var(--ddn-ui-surface);border-bottom:1px solid var(--ddn-ui-border);flex-wrap:wrap}
.ddn-viewer .ddn-viewer-toolbar button[hidden]{display:none}
.ddn-viewer .ddn-viewer-toolbar [data-primary]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface));color:var(--ddn-ui-accent);font-weight:650}
.ddn-toolbar-group{display:flex;align-items:center;flex-wrap:wrap;gap:3px;padding-right:7px;margin-right:3px;border-right:1px solid var(--ddn-ui-border)}.ddn-toolbar-group:last-child{border-right:0;margin-right:0;padding-right:0}
.ddn-viewer-outline{grid-column:1;overflow:auto;padding:14px 10px;border-right:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 70%,var(--ddn-ui-bg));scrollbar-width:thin;scrollbar-color:var(--ddn-ui-border) transparent}
.ddn-outline-heading{font-size:10px;font-weight:650;letter-spacing:.11em;text-transform:uppercase;color:var(--ddn-ui-muted);margin:0 0 12px 4px}.ddn-outline-search{display:flex;align-items:center;gap:6px;background:var(--ddn-ui-input);border:1px solid var(--ddn-ui-border);border-radius:8px;padding:0 8px;color:var(--ddn-ui-muted);margin-bottom:10px}
.ddn-viewer-outline input{min-width:0;width:100%;padding:8px 0;border:0;background:transparent;color:var(--ddn-ui-text);font-size:12px;outline-offset:1px}.ddn-viewer .ddn-viewer-outline .ddn-panel-section>button{display:block;text-align:left;width:100%;margin-top:4px;font-size:12px;overflow-wrap:anywhere;padding:8px 10px;line-height:1.4;color:var(--ddn-ui-muted)}.ddn-viewer-outline button[aria-current=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 13%,var(--ddn-ui-surface));color:var(--ddn-ui-accent);font-weight:650}
.ddn-viewer-stage{grid-column:2;position:relative;min-width:0;min-height:300px;overflow:hidden;background:#ffffff}.ddn-viewer-stage>svg{display:block;width:100%;height:100%;min-height:300px;touch-action:none;user-select:none;-webkit-user-select:none;cursor:grab}.ddn-viewer-stage>svg.ddn-panning{cursor:grabbing}.ddn-viewer-stage>svg [data-ref]{cursor:pointer}.ddn-viewer:not([data-ddn-editing]) .ddn-viewer-stage>svg [data-view-frame=true]{cursor:grab}.ddn-viewer[data-ddn-editing] .ddn-viewer-stage>svg [data-ref][data-movable=true]{cursor:move}.ddn-viewer-stage [data-selected=true]{filter:drop-shadow(0 0 3px #2563eb)}.ddn-viewer-stage>svg .ddn-hit{fill:none;stroke:transparent;stroke-width:14;pointer-events:stroke}.ddn-viewer-stage>svg[data-expanded] g[data-occurrence]:not([data-in-expanded=true]){display:none}.ddn-viewer-stage>svg[data-lod=mini] g[data-occurrence]:not([data-view-frame=true]){display:none}.ddn-viewer-stage>svg[data-lod=mini] g[data-view-frame=true]>g{display:none}.ddn-mini-card{cursor:pointer}.ddn-mini-card .ddn-mini-paper{fill:#ffffff;stroke:#94a3b8;stroke-width:1}.ddn-mini-card[data-active=true] .ddn-mini-paper{stroke:#2563eb;stroke-width:2}.ddn-mini-card text{fill:#1f2933;font-family:Inter,system-ui,sans-serif;font-weight:600}.ddn-mini-card .ddn-mini-meta{fill:#64748b;font-weight:400}.ddn-toolbar-group[aria-label=Zoom]{flex-wrap:nowrap;flex:none}.ddn-zoom-readout{min-width:48px;font-variant-numeric:tabular-nums;color:var(--ddn-ui-muted);font-size:11px;justify-content:center}.ddn-viewer-hint{width:min(420px,calc(100% - 32px));position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);max-width:min(420px,calc(100% - 32px));padding:16px 18px;border-radius:12px;background:color-mix(in srgb,var(--ddn-ui-surface) 94%,transparent);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);box-shadow:0 10px 30px color-mix(in srgb,var(--ddn-ui-shadow) 55%,transparent);font-size:13px;line-height:1.5;text-align:center;pointer-events:none}.ddn-viewer-hint button{pointer-events:auto}.ddn-placing .ddn-viewer-hint{width:min(420px,calc(100% - 32px));display:none}.ddn-viewer-hint p{margin:0 0 10px}.ddn-viewer-hint .ddn-hint-actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}.ddn-viewer-hint button{border:1px solid var(--ddn-ui-border);background:var(--ddn-ui-input);color:var(--ddn-ui-text);border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer}.ddn-viewer-hint button[data-primary]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.ddn-viewer-hint small{display:block;margin-top:8px;color:var(--ddn-ui-muted);font-size:11px}
.ddn-viewer-inspector{overflow-wrap:anywhere}.ddn-viewer-inspector>h3{margin:0 0 6px}.ddn-viewer-inspector details{margin-top:12px}.ddn-viewer-inspector summary{cursor:pointer;font-weight:600}.ddn-viewer-inspector dt{font-weight:600;margin-top:8px}.ddn-viewer-inspector dd{margin:2px 0 8px;font:12px 'JetBrains Mono',ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-viewer-status{grid-column:1/-1;padding:8px 12px;border-top:1px solid var(--ddn-ui-border);white-space:pre-wrap;font-size:11px;color:var(--ddn-ui-muted);background:var(--ddn-ui-surface)}.ddn-viewer-status[data-tone=error]{color:var(--ddn-ui-danger)}.ddn-viewer-status[data-tone=warning]{color:#d97706}.ddn-viewer-stage>svg.ddn-space-pan{cursor:grab}.ddn-viewer-stage>svg.ddn-space-pan.ddn-panning{cursor:grabbing}.ddn-viewer-overlays{position:absolute;inset:0;pointer-events:none}.ddn-viewer-overlays>*:not(.ddn-ui-layer):not(.ddn-viewer-hint){pointer-events:auto}
.ddn-viewer[data-controls=host]{grid-template-columns:1fr}.ddn-viewer[data-controls=host] .ddn-viewer-stage{grid-column:1}.ddn-viewer[data-controls=host]>.ddn-viewer-toolbar,.ddn-viewer[data-controls=host]>.ddn-viewer-outline{display:none}
.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left]){grid-template-columns:minmax(0,1fr)}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])>.ddn-viewer-stage{grid-column:1}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr) 320px}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]>.ddn-designer-dock-right{grid-column:2}
@media(max-width:760px){.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr)}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]>.ddn-designer-dock-right{grid-column:1}.ddn-viewer{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto minmax(340px,1fr) auto;overflow:auto}.ddn-viewer-outline{grid-column:1;grid-row:2;max-height:120px;padding:10px;border-right:0;border-bottom:1px solid var(--ddn-ui-border)}.ddn-outline-heading{display:none}.ddn-viewer-stage{grid-column:1;grid-row:3;min-height:340px}.ddn-viewer-status{grid-row:4}.ddn-viewer-toolbar{padding:6px;gap:3px;min-width:0;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}.ddn-viewer-toolbar button{white-space:nowrap;flex:none}.ddn-toolbar-group{padding-right:4px;margin-right:0;flex-wrap:nowrap;flex:none}}
`;
    const toolbar = document.createElement('div');
    toolbar.className = 'ddn-viewer-toolbar';
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', 'Diagram navigation');
    const outline = document.createElement('nav');
    outline.className = 'ddn-viewer-outline';
    outline.setAttribute('aria-label', 'Semantic outline');
    const search = document.createElement('input');
    search.type = 'search';
    search.placeholder = 'Find a view or element';
    search.setAttribute('aria-label', 'Search diagram');
    const outlineList = document.createElement('div');
    const outlineHeading = document.createElement('div');
    outlineHeading.className = 'ddn-outline-heading';
    outlineHeading.textContent = 'Navigator';
    outlineHeading.style.cssText = 'display:flex;align-items:center;gap:4px;letter-spacing:normal';
    const searchGroup = document.createElement('div');
    searchGroup.className = 'ddn-outline-search';
    searchGroup.append((0, ui_icons_js_1.uiIcon)(document, 'search'), search);
    const outlineSections = document.createElement('div');
    outlineSections.className = 'ddn-panel-sections';
    outlineList.className = 'ddn-panel-section';
    let outlineSection = 'all';
    const outlineTabs = (0, side_tabs_js_1.sideTabs)(outlineSections, 'Navigator sections', [{ id: 'all', label: 'All items', icon: 'layers' }, { id: 'views', label: 'Views', icon: 'grid' }, { id: 'elements', label: 'Elements', icon: 'table' }, { id: 'relations', label: 'Connections', icon: 'link' }], outlineSection, id => { outlineSection = id; outlineTabs.label(outlineList); renderOutline(); });
    outlineTabs.connect(outlineList);
    outlineSections.append(outlineList);
    outline.append(outlineHeading, searchGroup, outlineSections);
    const stage = document.createElement('div');
    stage.className = 'ddn-viewer-stage';
    const svg = svgElement(document, 'svg', { role: 'graphics-document', 'aria-label': 'Diagram workarea', tabindex: 0 });
    stage.append(svg);
    const overlays = document.createElement('div');
    overlays.className = 'ddn-viewer-overlays';
    stage.append(overlays);
    const statusTooltip = (0, status_hint_js_1.installStatusHint)(svg, overlays, clipPrefix + '-status-hint');
    cleanups.push(statusTooltip.destroy);
    const inspector = document.createElement('section');
    let inspectionDialog;
    inspector.className = 'ddn-viewer-inspector';
    inspector.setAttribute('aria-label', 'Item inspection');
    const status = document.createElement('div');
    status.className = 'ddn-viewer-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    container.dataset.controls = options.controls ?? 'standard';
    container.append(style, toolbar, outline, stage, status);
    element.append(container);
    const navigatorDrawer = (0, drawer_js_1.createDrawer)(outline, { id: 'navigator', title: 'Navigator', container, header: outlineHeading, width: 380, onMode(mode) { container.dataset.ddnNavigator = mode; }, onBlocked() { announce('The browser blocked the new window. The navigator floats here; allow pop-ups to move it to another monitor.'); } });
    cleanups.push(() => navigatorDrawer.destroy());
    const emit = (event) => {
        for (const listener of [...listeners])
            listener(event);
    };
    const ensure = () => {
        if (disposed)
            throw new Error('Viewer is destroyed');
    };
    const on = (target, type, listener, settings) => { target.addEventListener(type, listener, settings); cleanups.push(() => target.removeEventListener(type, listener, settings)); };
    const setStatusText = (message, tone, holdMs = 0) => {
        status.textContent = message;
        if (tone)
            status.dataset.tone = tone;
        else if (/not authorized|denied|failed|error|invalid|cannot/i.test(message))
            status.dataset.tone = 'error';
        else if (/stale|partial|warning|last valid/i.test(message))
            status.dataset.tone = 'warning';
        else
            delete status.dataset.tone;
        if (holdMs > 0)
            announceHoldUntil = Date.now() + holdMs;
    };
    const announce = (message, tone) => {
        setStatusText(message, tone, tone === 'error' || tone === 'warning' ? 2000 : 900);
    };
    function viewBox() { return { x: viewport.bounds.x, y: viewport.bounds.y, width: viewport.bounds.width / viewport.zoom, height: viewport.bounds.height / viewport.zoom }; }
    function screenScale(view = viewport) {
        const rect = svg.getBoundingClientRect();
        return Math.min(rect.width / view.bounds.width, rect.height / view.bounds.height) * view.zoom || 1;
    }
    function toWorld(x, y) {
        const matrix = svg.getScreenCTM();
        if (matrix) {
            const point = svg.createSVGPoint();
            point.x = x;
            point.y = y;
            const local = point.matrixTransform(matrix.inverse());
            return { x: local.x, y: local.y };
        }
        const rect = svg.getBoundingClientRect(), visible = viewBox(), scale = screenScale();
        return { x: visible.x + visible.width / 2 + (x - rect.left - rect.width / 2) / scale, y: visible.y + visible.height / 2 + (y - rect.top - rect.height / 2) / scale };
    }
    function viewFrame(ref) {
        return projection?.entries.find(entry => entry.item.occurrence === `view:${(0, native_js_2.refKey)(ref)}`);
    }
    function updatePaper() {
        let paper = workareaBackground;
        if (expandedView && currentSnapshot) {
            const resolved = styledResolve(currentSnapshot, expandedView).values;
            const declared = (0, native_js_2.str)((0, native_js_2.pathValue)(resolved, 'background.color'));
            const frame = viewFrame(expandedView);
            const painted = frame?.item.primitives.find(p => 'paint' in p && typeof p.paint.fill === 'string' && !['none', 'transparent'].includes(p.paint.fill));
            paper = declared && !['none', 'transparent'].includes(declared) ? declared : painted && 'paint' in painted ? (0, native_js_2.str)(painted.paint.fill, '#ffffff') : '#ffffff';
        }
        stage.style.backgroundColor = cssPaint(paper);
    }
    function draw() {
        statusTooltip.hide();
        if (disposed || !projection)
            return;
        const visible = viewBox();
        svg.setAttribute('viewBox', `${visible.x} ${visible.y} ${visible.width} ${visible.height}`);
        svg.querySelector('[data-ddn-background]')?.remove();
        updatePaper();
        if (workareaTexture && !expandedView) {
            const background = svgElement(document, 'g', { 'data-ddn-background': '', 'pointer-events': 'none', 'aria-hidden': 'true' });
            background.append(realize(document, backgroundPrimitive(visible, workareaBackground, workareaTexture), assets, { id: clipPrefix + '-background', bounds: visible }));
            svg.prepend(background);
        }
        const overscan = { x: visible.x - 200, y: visible.y - 200, width: visible.width + 400, height: visible.height + 400 };
        const existing = new Map(Array.from(svg.children).filter(child => child.hasAttribute('data-occurrence')).map(child => [child.getAttribute('data-occurrence'), child]));
        const entryOf = new Map(projection.entries.map(e => [e.item.occurrence, e]));
        const scale = screenScale();
        const expandedKey = expandedView ? (0, native_js_2.refKey)(expandedView) : undefined;
        const lod = (0, grid_js_1.viewSetting)(container, 'lod');
        const mini = !expandedKey && projection.views.length > 0 && lod !== 'full' && (lod === 'frames' || scale < LOD_SCALE);
        drawGrid(visible, scale);
        if (expandedKey)
            svg.setAttribute('data-expanded', expandedKey);
        else
            svg.removeAttribute('data-expanded');
        if (mini)
            svg.setAttribute('data-lod', 'mini');
        else
            svg.removeAttribute('data-lod');
        for (const item of projection.items) {
            if (!intersects(item.bounds, overscan))
                continue;
            let group = existing.get(item.occurrence);
            existing.delete(item.occurrence);
            if (!group) {
                group = svgElement(document, 'g', { 'data-occurrence': item.occurrence, tabindex: 0, role: item.accessible.role });
                svg.append(group);
            }
            const entry = entryOf.get(item.occurrence);
            group.setAttribute('data-ref', JSON.stringify(item.target));
            group.setAttribute('aria-label', item.accessible.label);
            group.setAttribute('data-selected', String(selectedOccurrences.has(item.occurrence) || item.occurrence === selectedOccurrence || !selectedOccurrence && !selectedOccurrences.size && !!selection && (0, native_js_2.refKey)(item.target) === (0, native_js_2.refKey)(selection)));
            group.setAttribute('data-view-frame', String(item.occurrence === `view:${(0, native_js_2.refKey)(item.view)}`));
            group.setAttribute('data-movable', String(!!(entry?.appearance ?? entry?.placement)));
            if (expandedKey)
                group.setAttribute('data-in-expanded', String(!!item.view && (0, native_js_2.refKey)(item.view) === expandedKey));
            else
                group.removeAttribute('data-in-expanded');
            group.replaceChildren();
            const title = svgElement(document, 'title');
            title.textContent = item.accessible.label + (item.accessible.description ? ` — ${item.accessible.description}` : '');
            group.append(title);
            appendItem(document, group, item, assets, clipPrefix);
            const record = entry?.definition.record;
            for (const dot of group.querySelectorAll('[data-status-dot]')) {
                dot.setAttribute('tabindex', '0');
                dot.style.cursor = 'help';
            }
            if (record && (record.category === 'relation' || Array.isArray(record.endpoints))) {
                const content = group.querySelector('g[transform]');
                if (content)
                    for (const path of Array.from(content.querySelectorAll('path'))) {
                        if (path.closest('defs'))
                            continue;
                        const hit = svgElement(document, 'path', { d: path.getAttribute('d') ?? '', class: 'ddn-hit', 'aria-hidden': 'true', 'vector-effect': 'non-scaling-stroke' });
                        path.parentElement?.append(hit);
                    }
            }
        }
        for (const child of existing.values())
            child.remove();
        drawMiniCards(mini, scale);
    }
    function drawGrid(visible, scale) {
        svg.querySelector('[data-ddn-grid-lines]')?.remove();
        if ((0, grid_js_1.viewSetting)(container, 'grid') !== 'on')
            return;
        let step = (0, grid_js_1.gridStep)(currentSnapshot);
        while (step * scale < 8)
            step *= 2;
        const rect = svg.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            const topLeft = toWorld(rect.left, rect.top), bottomRight = toWorld(rect.right, rect.bottom);
            visible = { x: topLeft.x, y: topLeft.y, width: bottomRight.x - topLeft.x, height: bottomRight.y - topLeft.y };
        }
        if (standalone && projection) {
            const bounds = projection.bounds;
            const x = Math.max(bounds.x, visible.x), y = Math.max(bounds.y, visible.y);
            visible = { x, y, width: Math.max(0, Math.min(bounds.x + bounds.width, visible.x + visible.width) - x), height: Math.max(0, Math.min(bounds.y + bounds.height, visible.y + visible.height) - y) };
        }
        const round = standalone ? Math.ceil : Math.floor;
        const x0 = round(visible.x / step) * step, y0 = round(visible.y / step) * step;
        let d = '';
        for (let x = x0; x <= visible.x + visible.width; x += step)
            d += `M${x} ${visible.y}V${visible.y + visible.height}`;
        for (let y = y0; y <= visible.y + visible.height; y += step)
            d += `M${visible.x} ${y}H${visible.x + visible.width}`;
        const group = svgElement(document, 'g', { 'data-ddn-grid-lines': '', 'pointer-events': 'none', 'aria-hidden': 'true' });
        group.append(svgElement(document, 'path', { d, fill: 'none', stroke: '#94a3b8', 'stroke-opacity': .35, 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke' }));
        const background = svg.querySelector('[data-ddn-background]');
        if (background)
            background.after(group);
        else
            svg.prepend(group);
    }
    function drawMiniCards(mini, scale) {
        miniCards?.remove();
        miniCards = undefined;
        if (!mini || !projection)
            return;
        miniCards = svgElement(document, 'g', { 'data-ddn-mini': '' });
        const activeKey = viewport.activeView ? (0, native_js_2.refKey)(viewport.activeView) : undefined;
        for (const view of projection.views) {
            const frame = viewFrame(view.ref);
            const b = frame?.item.bounds;
            if (!b || !frame)
                continue;
            const count = projection.entries.filter(e => e.definition.owner !== 'view' && (0, native_js_2.refKey)(e.view.ref) === (0, native_js_2.refKey)(view.ref)).length;
            const card = svgElement(document, 'g', { class: 'ddn-mini-card', role: 'button', tabindex: 0, 'aria-label': `${(0, native_js_2.titleOf)(view.record)} — ${count} elements. Enter to expand view`, 'data-ref': JSON.stringify(view.ref), 'data-occurrence-ref': frame.item.occurrence, 'data-active': String(activeKey === (0, native_js_2.refKey)(view.ref)) });
            card.append(svgElement(document, 'rect', { x: b.x, y: b.y, width: b.width, height: b.height, rx: Math.min(24, 12 / scale), class: 'ddn-mini-paper' }));
            const size = Math.min(b.height / 10, b.width / 16, Math.max(14, 22 / scale)), glyph = Math.min(b.width / 3, size * 1.6);
            const gx = b.x + b.width / 2 - glyph / 2, gy = b.y + b.height * 0.22;
            const sw = Math.max(1.5, 2.5 / scale);
            card.append(svgElement(document, 'rect', { x: gx, y: gy, width: glyph, height: glyph * .8, rx: glyph * .06, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'rect', { x: gx, y: gy, width: glyph, height: glyph * .18, rx: glyph * .06, fill: '#2563eb', stroke: 'none' }));
            card.append(svgElement(document, 'rect', { x: gx + glyph * .14, y: gy + glyph * .32, width: glyph * .32, height: glyph * .3, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'rect', { x: gx + glyph * .54, y: gy + glyph * .32, width: glyph * .32, height: glyph * .3, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'path', { d: `M${gx + glyph * .46},${gy + glyph * .47}H${gx + glyph * .54}`, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            const label = (0, native_js_2.titleOf)(view.record) || view.ref.id;
            const title = svgElement(document, 'text', { x: b.x + b.width / 2, y: gy + glyph * 1.3 + size * 1.2, 'text-anchor': 'middle', 'font-size': size });
            title.textContent = label.length > 28 ? label.slice(0, 27) + '…' : label;
            card.append(title);
            const meta = svgElement(document, 'text', { x: b.x + b.width / 2, y: gy + glyph * 1.3 + size * 2.4, 'text-anchor': 'middle', 'font-size': size * 0.7, class: 'ddn-mini-meta' });
            meta.textContent = `${count} element${count === 1 ? '' : 's'} · double-click to open`;
            card.append(meta);
            card.addEventListener('dblclick', () => { void viewer.navigate({ kind: 'expand-view', target: view.ref }); });
            card.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    void viewer.navigate({ kind: 'expand-view', target: view.ref });
                }
            });
            miniCards.append(card);
        }
        svg.append(miniCards);
    }
    function outlineLabel(entry) {
        const record = entry.definition.record;
        const own = (0, native_js_2.str)(record.title);
        if (own)
            return own;
        if (Array.isArray(record.endpoints) && currentSnapshot) {
            const all = (0, native_js_2.records)(currentSnapshot);
            const names = record.endpoints.map(end => {
                const target = (0, native_js_2.object)(end).target ?? (0, native_js_2.object)(end).definition ?? end;
                const found = (0, native_js_2.resolveRecord)(all, target, entry.definition.file);
                return found ? (0, native_js_2.titleOf)(found.record) : undefined;
            }).filter((name) => !!name);
            if (names.length >= 2)
                return `${names[0]} → ${names.slice(1).join(', ')}`;
        }
        const generic = (0, native_js_2.titleOf)(record);
        return /^ddn-[0-9a-f]{12,}$/.test(generic) ? `${(0, native_js_2.str)(record.role, 'connection')} (unnamed)` : generic;
    }
    function renderOutline() {
        const q = search.value.toLocaleLowerCase();
        outlineList.replaceChildren();
        const seen = new Set();
        for (const entry of projection?.entries ?? []) {
            const key = (0, native_js_2.refKey)(entry.definition.ref);
            if (seen.has(key))
                continue;
            seen.add(key);
            const category = entry.definition.owner === 'view' ? 'views' : entry.definition.record.category === 'relation' ? 'relations' : 'elements';
            if (!q && outlineSection !== 'all' && outlineSection !== category)
                continue;
            const label = outlineLabel(entry);
            if (q && !`${label} ${entry.definition.file}`.toLocaleLowerCase().includes(q))
                continue;
            const button = document.createElement('button');
            button.textContent = label;
            button.title = `${entry.definition.file} :: ${entry.definition.ref.id}`;
            button.dataset.ref = JSON.stringify(entry.definition.ref);
            if (selection && (0, native_js_2.refKey)(selection) === key)
                button.setAttribute('aria-current', 'true');
            button.addEventListener('click', () => { select(entry.definition.ref, entry.item.occurrence); void viewer.navigate({ kind: 'focus', target: entry.definition.ref }); });
            outlineList.append(button);
        }
    }
    function openInspection() {
        if (inspectionDialog) {
            inspectionDialog.element.focus();
            return;
        }
        inspectionDialog = (0, dialogs_js_1.createStandardDialog)(overlays, { title: 'Item details', modal: false, onClose() { inspectionDialog = undefined; } });
        inspectionDialog.body.append(inspector);
        renderInspection();
    }
    function renderInspection() {
        if (!inspectionDialog)
            return;
        inspector.replaceChildren();
        if (!selection || !currentSnapshot) {
            inspector.textContent = 'Select an item to inspect its full values and inherited settings.';
            return;
        }
        const found = (0, native_js_2.findRecord)(currentSnapshot, selection);
        if (!found)
            return;
        const heading = document.createElement('h3');
        heading.textContent = (0, native_js_2.titleOf)(found.record);
        inspector.append(heading);
        const id = document.createElement('p');
        id.textContent = `${found.file} :: ${found.ref.id}`;
        const summary = document.createElement('p');
        summary.textContent = [(0, native_js_2.str)(found.record.type), (0, native_js_2.str)((0, native_js_2.pathValue)(found.record, 'design.state')), (0, native_js_2.str)(found.record.profile)].filter(Boolean).join(' · ');
        inspector.append(summary);
        renderAnalysis(found.ref);
        const details = document.createElement('details'), detailsLabel = document.createElement('summary');
        detailsLabel.textContent = 'All properties and inheritance';
        details.append(detailsLabel, id);
        const list = document.createElement('dl');
        const resolved = styledResolve(currentSnapshot, selection);
        for (const property of resolved.properties) {
            const term = document.createElement('dt');
            term.textContent = property.path;
            const value = document.createElement('dd');
            value.textContent = `${typeof property.value === 'string' ? property.value : JSON.stringify(property.value)} (${property.origin})`;
            list.append(term, value);
        }
        if (found.record.data || found.record.draft || found.record.content || found.record.projection) {
            const term = document.createElement('dt');
            term.textContent = 'Complete content';
            const value = document.createElement('dd');
            value.textContent = JSON.stringify({ data: found.record.data, draft: found.record.draft, content: found.record.content, ...(found.record.profile === 'table.records@1' ? { projectedTable: (0, native_js_2.recordTableData)(currentSnapshot, found) } : {}) }, null, 2);
            list.append(term, value);
        }
        details.append(list);
        inspector.append(details);
    }
    function renderAnalysis(target) {
        if (!currentSnapshot)
            return;
        const analysis = (0, native_js_2.object)((0, adapters_js_1.analyzePresentedProfile)(currentSnapshot.normalized, target));
        if (analysis.kind === 'none')
            return;
        const section = document.createElement('section');
        section.setAttribute('aria-label', 'Profile analysis');
        const title = document.createElement('h4');
        title.textContent = analysis.kind === 'decision' ? 'Decision analysis' : analysis.kind === 'flat-state' ? 'Declared trace analysis' : 'Critical path';
        const result = document.createElement('pre');
        result.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px';
        result.setAttribute('aria-live', 'polite');
        result.textContent = JSON.stringify(analysis, null, 2);
        section.append(title);
        if (analysis.kind === 'decision' && Array.isArray(analysis.inputs)) {
            const controls = [];
            for (const raw of analysis.inputs) {
                const domain = (0, native_js_2.object)(raw), name = (0, native_js_2.str)(domain.name);
                const label = document.createElement('label');
                label.style.display = 'block';
                const enabled = document.createElement('input');
                enabled.type = 'checkbox';
                enabled.checked = domain.optional !== true;
                enabled.setAttribute('aria-label', 'Supply ' + name);
                label.append(enabled, ' ' + name + ' ');
                const choices = domain.type === 'boolean' ? [false, true] : Array.isArray(domain.values) ? [...domain.values] : [];
                if (domain.nullable === true)
                    choices.push(null);
                let read;
                if (domain.type !== 'number') {
                    const input = document.createElement('select');
                    input.setAttribute('aria-label', 'Decision input ' + name);
                    for (const [index, value] of choices.entries()) {
                        const option = document.createElement('option');
                        option.value = String(index);
                        option.textContent = value === null ? 'null' : String(value);
                        input.append(option);
                    }
                    label.append(input);
                    read = () => choices[Number(input.value)];
                }
                else {
                    const input = document.createElement('input');
                    input.type = 'number';
                    input.step = 'any';
                    input.setAttribute('aria-label', 'Decision input ' + name);
                    if (typeof domain.min === 'number') {
                        input.min = String(domain.min);
                        input.value = String(domain.min);
                    }
                    if (typeof domain.max === 'number')
                        input.max = String(domain.max);
                    label.append(input);
                    const nullValue = document.createElement('input');
                    nullValue.type = 'checkbox';
                    nullValue.setAttribute('aria-label', 'Null ' + name);
                    if (domain.nullable === true)
                        label.append(nullValue, ' null');
                    read = () => nullValue.checked ? null : input.value !== '' && input.checkValidity() ? Number(input.value) : (() => { throw Error('Enter a number within the declared range for ' + name); })();
                }
                section.append(label);
                controls.push({ name, enabled, read });
            }
            const calculate = document.createElement('button');
            calculate.type = 'button';
            calculate.textContent = 'Match inputs';
            calculate.addEventListener('click', () => {
                try {
                    const values = {};
                    for (const control of controls)
                        if (control.enabled.checked)
                            values[control.name] = control.read();
                    result.textContent = JSON.stringify((0, adapters_js_1.analyzePresentedProfile)(currentSnapshot.normalized, target, values), null, 2);
                }
                catch (error) {
                    result.textContent = String(error);
                }
            });
            section.append(calculate);
        }
        section.append(result);
        inspector.append(section);
    }
    function select(ref, occurrence, additive = false) {
        if (!ref) {
            clearSelection();
            return;
        }
        if (standalone && !projection?.entries.some(entry => occurrence ? entry.item.occurrence === occurrence && (0, native_js_2.refKey)(entry.definition.ref) === (0, native_js_2.refKey)(ref) : (0, native_js_2.refKey)(entry.definition.ref) === (0, native_js_2.refKey)(ref)))
            return;
        if (additive && occurrence) {
            if (selectedOccurrences.has(occurrence) && selectedOccurrences.size > 1) {
                selectedOccurrences.delete(occurrence);
                if (selectedOccurrence === occurrence) {
                    const lastOcc = [...selectedOccurrences].at(-1);
                    const lastEntry = projection?.entries.find(e => e.item.occurrence === lastOcc);
                    selectedOccurrence = lastOcc;
                    selection = lastEntry?.definition.ref ?? ref;
                }
            }
            else {
                if (selectedOccurrence && !selectedOccurrences.size)
                    selectedOccurrences.add(selectedOccurrence);
                selectedOccurrences.add(occurrence);
                selection = ref;
                selectedOccurrence = occurrence;
            }
        }
        else {
            selectedOccurrences.clear();
            if (occurrence)
                selectedOccurrences.add(occurrence);
            selection = ref;
            selectedOccurrence = occurrence;
        }
        for (const group of Array.from(svg.children)) {
            const occ = group.getAttribute('data-occurrence');
            const selected = (occ && selectedOccurrences.has(occ)) || (occurrence ? occ === selectedOccurrence : group.getAttribute('data-ref') === JSON.stringify(selection));
            group.setAttribute('data-selected', String(!!selected));
        }
        for (const button of outlineList.querySelectorAll('button')) {
            if (button.dataset.ref && selection && (0, native_js_2.refKey)(JSON.parse(button.dataset.ref)) === (0, native_js_2.refKey)(selection))
                button.setAttribute('aria-current', 'true');
            else
                button.removeAttribute('aria-current');
        }
        renderInspection();
        for (const listener of [...selectionListeners])
            listener(selection);
        updateToolbarState();
        renderHint();
        emit({ kind: 'selection', ...(selection ? { target: selection } : {}), ...(currentSnapshot ? { revision: currentSnapshot.revision } : {}) });
    }
    function cameraState() { return { viewport, expandedView, restored }; }
    function rememberCamera(state) {
        history.splice(historyIndex + 1);
        history.push(state);
        historyIndex = history.length - 1;
    }
    function setCamera(next, remember = true, mode) {
        if (!Number.isFinite(next.zoom) || next.zoom <= 0 || Object.values(next.bounds).some(v => !Number.isFinite(v)) || next.bounds.width <= 0 || next.bounds.height <= 0)
            throw new Error('Invalid viewport');
        if (remember)
            rememberCamera(cameraState());
        if (mode) {
            expandedView = mode.expandedView;
            restored = mode.restored;
        }
        viewport = { ...next, bounds: { ...next.bounds }, zoom: Math.min(32, Math.max(.05, next.zoom)) };
        if (standalone && projection) {
            expandedView = projection.views[0]?.ref;
            restored = undefined;
            viewport = (0, standalone_viewport_js_1.constrainStandaloneViewport)(viewport, projection.bounds, expandedView);
        }
        draw();
        updateToolbarState();
        renderHint();
        emit({ kind: 'viewport', ...(viewport.activeView ? { target: viewport.activeView } : {}) });
    }
    function zoomAt(factor, clientX, clientY, remember = false) {
        const before = viewBox(), anchor = toWorld(clientX, clientY);
        const zoom = Math.min(32, Math.max(.05, viewport.zoom * factor));
        const ratio = viewport.zoom / zoom;
        const x = anchor.x - (anchor.x - before.x) * ratio, y = anchor.y - (anchor.y - before.y) * ratio;
        setCamera({ ...viewport, zoom, bounds: { x, y, width: viewport.bounds.width, height: viewport.bounds.height } }, remember);
    }
    function clearSelection() {
        if (!selection && !selectedOccurrence && !selectedOccurrences.size)
            return;
        selection = undefined;
        selectedOccurrence = undefined;
        selectedOccurrences.clear();
        for (const group of Array.from(svg.children))
            if (group.hasAttribute('data-selected'))
                group.setAttribute('data-selected', 'false');
        for (const button of outlineList.querySelectorAll('button'))
            button.removeAttribute('aria-current');
        renderInspection();
        for (const listener of [...selectionListeners])
            listener(undefined);
        emit({ kind: 'selection', ...(currentSnapshot ? { revision: currentSnapshot.revision } : {}) });
        updateToolbarState();
    }
    function fit(bounds, target, mode) { const pad = standalone ? 0 : 24; setCamera({ bounds: { x: bounds.x - pad, y: bounds.y - pad, width: bounds.width + pad * 2, height: bounds.height + pad * 2 }, zoom: 1, ...(target ? { activeView: target } : {}) }, true, mode); }
    const cssCache = new Map();
    function styledResolve(snapshot, target, context = {}) {
        const files = Array.isArray((0, native_js_2.object)(snapshot.normalized).files) ? (0, native_js_2.object)(snapshot.normalized).files : [];
        const rootDocument = (0, native_js_2.object)(files.map(native_js_2.object).find(f => f.location === snapshot.rootFile)?.document);
        const ownDocument = (0, native_js_2.object)(files.map(native_js_2.object).find(f => f.location === target.file)?.document);
        const view = context.view ? (0, native_js_2.findRecord)(snapshot, context.view)?.record : (0, native_js_2.findRecord)(snapshot, target)?.owner === 'view' ? (0, native_js_2.findRecord)(snapshot, target)?.record : undefined;
        const sheets = [];
        for (const [owner, file] of [[rootDocument, snapshot.rootFile], [ownDocument, target.file], [view, context.view?.file ?? target.file]]) {
            const listed = (0, native_js_2.pathValue)(owner, 'style.sheets');
            if (Array.isArray(listed))
                for (const sheet of listed)
                    sheets.push([sheet, file]);
        }
        const seen = new Set();
        const rules = [];
        const problems = [];
        for (const [reference, file] of sheets) {
            const record = typeof reference === 'object' ? (0, native_js_2.records)(snapshot).find(r => r.owner === 'asset' && (r.ref.id === (0, native_js_2.object)(reference).id || r.record.name === (0, native_js_2.object)(reference).name) && r.file === (0, native_js_2.str)((0, native_js_2.object)(reference).file, file)) : undefined;
            const name = typeof reference === 'string' ? reference : (0, native_js_2.str)(record?.record.path, (0, native_js_2.str)((0, native_js_2.object)(reference).name, (0, native_js_2.str)((0, native_js_2.object)(reference).id)));
            const parts = record ? [] : file.split('/').slice(0, -1);
            for (const part of name.split('/')) {
                if (part === '..')
                    parts.pop();
                else if (part && part !== '.')
                    parts.push(part);
            }
            const location = parts.join('/');
            if (seen.has(location))
                continue;
            seen.add(location);
            const source = runtime.sources()?.files.find(f => f.id === location);
            if (!source) {
                problems.push({ code: 'style-unavailable', severity: 'warning', message: `Selected stylesheet ${location} is unavailable.`, target });
                continue;
            }
            const key = source.id + '@' + source.revision;
            let parsed = cssCache.get(key);
            if (!parsed) {
                parsed = (0, index_js_1.parseStylesheet)(source.text);
                cssCache.set(key, parsed);
                if (cssCache.size > 128)
                    cssCache.delete(cssCache.keys().next().value);
            }
            rules.push(...parsed.rules);
            problems.push(...parsed.diagnostics);
        }
        const result = (0, index_js_1.resolveProperties)(snapshot, target, { ...context, styles: rules });
        return { ...result, diagnostics: [...problems, ...result.diagnostics] };
    }
    const canvas = document.createElement('canvas');
    const measure = (value, size, font) => {
        const context = canvas.getContext('2d');
        if (!context)
            return value.length * size * .58;
        context.font = `${size}px ${(0, fonts_js_1.fontFamily)(font)}`;
        return context.measureText(value).width;
    };
    async function loadAssets(scene) {
        let sizesChanged = false;
        const ids = [...new Set(scene.items.flatMap(item => item.primitives.filter((p) => p.kind === 'image').map(p => p.assetId)))];
        for (const id of ids) {
            if (assets.has(id) || assetFailures.has(id))
                continue;
            if (!options.assets) {
                assetFailures.add(id);
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: `Asset ${id} needs an explicit local asset provider.` });
                continue;
            }
            try {
                const result = await options.assets.read(id);
                if (result.bytes.byteLength > 16 * 1024 * 1024)
                    throw new Error('Asset exceeds the local image budget');
                let bytes = new Uint8Array(result.bytes).buffer;
                let mime = result.mime;
                let intrinsicSize;
                if (mime === 'image/svg+xml') {
                    const parser = new win.DOMParser();
                    const svgDocument = parser.parseFromString(new TextDecoder().decode(bytes), 'image/svg+xml');
                    if (svgDocument.querySelector('parsererror') || svgDocument.documentElement.localName !== 'svg')
                        throw new Error('Invalid SVG asset');
                    (0, svg_assets_js_1.sanitizeSvgAsset)(svgDocument, document);
                    const root = svgDocument.documentElement, dimension = (name) => {
                        const raw = root.getAttribute(name)?.trim() ?? '';
                        return /^(?:\d+(?:\.\d*)?|\.\d+)(?:px)?$/.test(raw) ? Number.parseFloat(raw) : NaN;
                    };
                    const width = dimension('width'), height = dimension('height'), viewBox = (root.getAttribute('viewBox') ?? '').trim().split(/[\s,]+/).map(Number);
                    if (width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))
                        intrinsicSize = { width, height };
                    else if (viewBox.length === 4 && viewBox.every(Number.isFinite) && viewBox[2] > 0 && viewBox[3] > 0)
                        intrinsicSize = { width: viewBox[2], height: viewBox[3] };
                    bytes = new TextEncoder().encode(new win.XMLSerializer().serializeToString(svgDocument.documentElement)).buffer;
                }
                else if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(mime))
                    throw new Error('Unsupported image media type');
                const blob = new Blob([bytes], { type: mime });
                const dataURL = await new Promise((resolve, reject) => { const reader = new win.FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('Asset encoding failed')); reader.readAsDataURL(blob); });
                if (!intrinsicSize) {
                    const image = new win.Image();
                    image.src = dataURL;
                    await image.decode();
                    if (image.naturalWidth > 0 && image.naturalHeight > 0)
                        intrinsicSize = { width: image.naturalWidth, height: image.naturalHeight };
                }
                assets.set(id, { dataURL, hash: result.hash, ...(intrinsicSize ? { intrinsicSize } : {}) });
                sizesChanged ||= !!intrinsicSize;
            }
            catch (error) {
                assetFailures.add(id);
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: `Asset ${id}: ${String(error)}` });
            }
        }
        for (const id of assets.keys())
            if (!ids.includes(id))
                assets.delete(id);
        return sizesChanged;
    }
    async function loadGeography(snapshot) {
        const problems = [], all = (0, native_js_2.records)(snapshot);
        const requested = all.filter(r => r.owner === 'view' && (0, native_js_2.str)(r.record.profile).startsWith('geo.')).map(r => ({ view: r, name: (0, native_js_2.str)((0, native_js_2.pathValue)(r.record, 'projection.options.geography')) }));
        for (const { view, name } of requested) {
            const separator = name.indexOf('::');
            const file = separator >= 0 ? name.slice(0, separator) : view.file;
            const localName = separator >= 0 ? name.slice(separator + 2) : name;
            const asset = all.find(r => r.owner === 'asset' && ((0, native_js_2.refKey)(r.ref) === name || r.file === file && [r.ref.id, r.record.name, r.record.path].includes(localName)));
            if (!asset || asset.record.bytes !== undefined || !options.assets)
                continue;
            const key = (0, native_js_2.refKey)(asset.ref), version = JSON.stringify(asset.record);
            if (geographyVersions.get(key) === version)
                continue;
            try {
                const result = await options.assets.read(key);
                if (result.bytes.byteLength > 16 * 1024 * 1024)
                    throw Error('Geography exceeds the local 16 MiB asset budget');
                if (!['application/json', 'application/geo+json', 'application/geojson', 'application/octet-stream', 'text/plain'].includes(result.mime))
                    throw Error('Geography asset must contain JSON');
                const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(result.bytes));
                geography.set(key, value);
                for (const alias of [asset.ref.id, (0, native_js_2.str)(asset.record.name), (0, native_js_2.str)(asset.record.path)])
                    if (alias)
                        geography.set(asset.file + '::' + alias, value);
                geographyVersions.set(key, version);
                geographyHashes.set(key, result.hash);
                assetFailures.delete(key);
            }
            catch (error) {
                assetFailures.add(key);
                problems.push({ code: 'geography-unavailable', severity: 'warning', message: error instanceof Error ? error.message : 'Geography could not be loaded', target: view.ref });
            }
        }
        return problems;
    }
    async function refresh() {
        const ticket = ++generation;
        await fontsReady;
        const snapshot = runtime.snapshot();
        if (!snapshot || disposed)
            return;
        emit({ kind: 'pending', revision: snapshot.revision });
        const report = await runtime.verifier.verifyModel(snapshot, { scope: { kind: 'workarea' }, purpose: 'display', level: 'structural' });
        if (disposed || ticket !== generation)
            return;
        const all = (0, native_js_2.records)(snapshot);
        const workarea = all.find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
        const nextStandalone = workarea?.record.mode === 'standalone';
        const onlyView = nextStandalone ? all.find(r => r.owner === 'view')?.ref : undefined;
        if (workarea) {
            const resolved = styledResolve(snapshot, workarea.ref).values;
            workareaBackground = (0, native_js_2.str)((0, native_js_2.pathValue)(resolved, 'background.color'), '#f2f4f7');
            workareaTexture = (0, native_js_2.pathValue)(resolved, 'background.texture');
            stage.style.backgroundColor = cssPaint(workareaBackground);
        }
        else {
            workareaBackground = '#f2f4f7';
            workareaTexture = undefined;
        }
        diagnostics = [...runtimeDiagnostics, ...report.diagnostics];
        diagnostics.push(...await loadGeography(snapshot));
        if (disposed || ticket !== generation)
            return;
        const project = () => (0, native_js_2.projectSnapshot)(snapshot, { ...(onlyView ? { onlyView } : {}), resolve: (target, context) => styledResolve(snapshot, target, context), measure, geography, assetSizes: assetSizes(), ...(preview ? { preview } : {}), supports: profile => native_js_2.availableProjectionProfiles.has(profile) && !!(0, registry_js_1.registrations)(runtime.registry).profiles?.some(p => p.id === profile) });
        let nextProjection = project();
        const sizesChanged = await loadAssets(nextProjection);
        if (disposed || ticket !== generation)
            return;
        if (sizesChanged)
            nextProjection = project();
        diagnostics.push(...nextProjection.diagnostics);
        const modeChanged = standalone !== nextStandalone;
        const wasFitted = projection && (0, standalone_viewport_js_1.sameBounds)(viewBox(), projection.bounds);
        const viewChanged = nextStandalone && (0, native_js_2.refKey)(projection?.views[0]?.ref ?? { file: '', id: '' }) !== (0, native_js_2.refKey)(nextProjection.views[0]?.ref ?? { file: '', id: '' });
        currentSnapshot = snapshot;
        projection = nextProjection;
        standalone = nextStandalone;
        container.dataset.ddnDocumentMode = standalone ? 'standalone' : 'workarea';
        svg.setAttribute('aria-label', standalone ? 'Standalone diagram view' : 'Diagram workarea');
        if (modeChanged || viewChanged) {
            history.length = 0;
            historyIndex = -1;
            restored = undefined;
            expandedView = undefined;
        }
        if (standalone) {
            expandedView = projection.views[0]?.ref;
            restored = undefined;
            if (modeChanged || viewChanged || wasFitted)
                viewport = { bounds: { ...projection.bounds }, zoom: 1 };
            viewport = (0, standalone_viewport_js_1.constrainStandaloneViewport)(viewport, projection.bounds, expandedView);
            if (selection && !projection.entries.some(entry => (0, native_js_2.refKey)(entry.definition.ref) === (0, native_js_2.refKey)(selection)))
                clearSelection();
        }
        if (expandedView && !projection.views.some(v => (0, native_js_2.refKey)(v.ref) === (0, native_js_2.refKey)(expandedView)))
            expandedView = undefined;
        draw();
        renderOutline();
        renderInspection();
        renderHint();
        updateToolbarState();
        const messages = [stale ? 'Showing the last valid version; the source has an error.' : '', !projection.coverage.complete ? 'Partial display: ' + projection.coverage.unavailable.join(', ') : '', ...diagnostics.filter(d => d.severity !== 'info').slice(0, 5).map(d => d.message)].filter(Boolean);
        const elements = projection.entries.length - projection.views.length;
        if (messages.length || Date.now() >= announceHoldUntil || !status.textContent)
            setStatusText(messages.join('\n') || `${projection.views.length} view${projection.views.length === 1 ? '' : 's'} · ${elements} element${elements === 1 ? '' : 's'}`);
        emit({ kind: 'diagnostics', revision: snapshot.revision, diagnostics });
        emit({ kind: 'ready', revision: snapshot.revision });
    }
    let renderKey = '', queued = false, openGeneration = 0;
    const schedule = () => {
        const key = JSON.stringify([runtime.snapshot()?.revision, styleGeneration, fontGeneration, runtime.registry.describe(), runtimeDiagnostics]);
        if (key === renderKey)
            return;
        renderKey = key;
        if (queued)
            return;
        queued = true;
        rendering = Promise.resolve().then(async () => { queued = false; await refresh(); }).catch(error => { diagnostics.push({ code: 'render-failed', severity: 'error', message: String(error) }); announce(`Display failed: ${String(error)}`); emit({ kind: 'diagnostics', diagnostics }); });
    };
    const unsubscribe = runtime.subscribe(event => {
        if (event.kind === 'disposed') {
            announce('Runtime closed.');
            return;
        }
        if (event.kind === 'diagnostics') {
            runtimeDiagnostics = [...(event.diagnostics ?? [])];
            diagnostics = [...runtimeDiagnostics];
            stale = !event.revision && diagnostics.some(d => d.severity === 'error');
        }
        if (event.kind === 'revision' || event.kind === 'diagnostics' || event.kind === 'capabilities')
            schedule();
    });
    cleanups.push(unsubscribe);
    const toolbarGroup = (name) => { const group = document.createElement('div'); group.className = 'ddn-toolbar-group'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', name); toolbar.append(group); return group; };
    const navGroups = { details: toolbarGroup('Details'), fit: toolbarGroup('Fit and expand'), history: toolbarGroup('Position history'), zoom: toolbarGroup('Zoom') };
    const button = (label, action, group, title) => {
        const item = document.createElement('button');
        item.textContent = label;
        const icon = { 'Item details': 'info', 'Fit all': 'fit', 'Fit view': 'fit', 'Expand view': 'expand', 'Shrink to workarea': 'layers', 'Back': 'arrow-left', 'Forward': 'arrow-right' }[label];
        if (icon)
            item.prepend((0, ui_icons_js_1.uiIcon)(document, icon));
        item.type = 'button';
        if (title)
            item.title = title;
        item.addEventListener('click', action);
        (group ?? toolbar).append(item);
        return item;
    };
    const currentViewRef = () => selection ? projection?.entries.find(e => (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(selection))?.view.ref ?? viewport.activeView ?? projection?.views[0]?.ref : viewport.activeView ?? projection?.views[0]?.ref;
    const detailsButton = button('Item details', openInspection, navGroups.details, 'Show every property of the selected element, with where each value comes from');
    const fitAllButton = button('Fit all', () => void viewer.navigate({ kind: 'fit-workarea' }), navGroups.fit, 'Show the whole workarea — every view (0)');
    const fitViewButton = button('Fit view', () => {
        const ref = currentViewRef();
        if (ref)
            void viewer.navigate({ kind: 'fit-view', target: ref });
    }, navGroups.fit, 'Frame the current view inside the workarea');
    const expandButton = button('Expand view', () => {
        if (expandedView) {
            void viewer.navigate({ kind: 'restore' });
            return;
        }
        const ref = currentViewRef();
        if (ref)
            void viewer.navigate({ kind: 'expand-view', target: ref });
    }, navGroups.fit, 'Fill the viewing area with the current view and hide the workarea; press again to shrink back');
    const backButton = button('Back', () => void viewer.navigate({ kind: 'back' }), navGroups.history, 'Previous position and zoom');
    const forwardButton = button('Forward', () => void viewer.navigate({ kind: 'forward' }), navGroups.history, 'Next position and zoom');
    button('−', () => { const rect = svg.getBoundingClientRect(); zoomAt(1 / 1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true); }, navGroups.zoom, 'Zoom out (−). Mouse wheel zooms at the pointer; pinch on touch');
    const zoomReadout = document.createElement('button');
    zoomReadout.type = 'button';
    zoomReadout.className = 'ddn-zoom-readout';
    zoomReadout.title = 'Current zoom — click to fit all';
    zoomReadout.textContent = '100%';
    zoomReadout.addEventListener('click', () => void viewer.navigate({ kind: 'fit-workarea' }));
    navGroups.zoom.append(zoomReadout);
    button('+', () => { const rect = svg.getBoundingClientRect(); zoomAt(1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true); }, navGroups.zoom, 'Zoom in (+)');
    function updateToolbarState() {
        const views = projection?.views.length ?? 0;
        const percent = Math.round(screenScale() * 100);
        zoomReadout.textContent = percent + '%';
        fitAllButton.hidden = standalone;
        expandButton.hidden = standalone;
        fitAllButton.disabled = !projection || standalone;
        zoomReadout.title = standalone ? 'Current zoom — click to fit view' : 'Current zoom — click to fit all';
        fitAllButton.title = views ? `Show the whole workarea — ${views} view${views === 1 ? '' : 's'}` : 'Show the whole workarea';
        fitViewButton.disabled = !views || !!expandedView && !standalone;
        fitViewButton.title = standalone ? 'Frame the standalone view' : 'Frame the current view inside the workarea';
        expandButton.disabled = !views || standalone;
        expandButton.replaceChildren((0, ui_icons_js_1.uiIcon)(document, expandedView ? 'layers' : 'expand'), document.createTextNode(expandedView ? 'Shrink to workarea' : 'Expand view'));
        expandButton.setAttribute('aria-pressed', String(!!expandedView));
        backButton.disabled = historyIndex < 0;
        forwardButton.disabled = !history[historyIndex + 2];
        detailsButton.disabled = !projection;
        (0, ui_commands_js_1.notifyUICommands)(container);
    }
    function toScreen(x, y) {
        const matrix = svg.getScreenCTM(), rect = svg.getBoundingClientRect();
        if (!matrix)
            return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        const point = svg.createSVGPoint();
        point.x = x;
        point.y = y;
        const screen = point.matrixTransform(matrix);
        return { x: screen.x, y: screen.y };
    }
    function zoomAnchor() {
        const rect = svg.getBoundingClientRect(), centre = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        const entry = selection ? projection?.entries.find(e => selectedOccurrence ? e.item.occurrence === selectedOccurrence : (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(selection)) : undefined;
        if (!entry)
            return centre;
        const b = entry.item.bounds, point = toScreen(b.x + b.width / 2, b.y + b.height / 2);
        return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom ? point : centre;
    }
    const zoomBy = (factor) => { const anchor = zoomAnchor(); zoomAt(factor, anchor.x, anchor.y, true); };
    const zoomTo = (percent) => {
        if (Number.isFinite(percent) && percent > 0)
            zoomBy(percent / 100 / screenScale());
    };
    const views = () => projection?.views.length ?? 0;
    cleanups.push((0, ui_commands_js_1.registerUICommands)(container, [
        { id: 'view.details', label: 'Item details', run: openInspection, enabled: () => !!projection },
        { id: 'view.fit-workarea', label: 'Fit workarea', run: () => void viewer.navigate({ kind: 'fit-workarea' }), enabled: () => !!projection && !standalone },
        { id: 'view.fit-view', label: 'Fit current view', run: () => fitViewButton.click(), enabled: () => !!views() && (!expandedView || standalone) },
        { id: 'view.fit-selection', label: 'Fit selection', hint: 'Select an element first.', run: () => {
                if (selection)
                    void viewer.navigate({ kind: 'focus', target: selection });
            }, enabled: () => !!selection && !!projection },
        { id: 'view.expand', label: 'Expand view', run: () => expandButton.click(), enabled: () => !!views() && !standalone, checked: () => !!expandedView },
        { id: 'view.back', label: 'Back', run: () => void viewer.navigate({ kind: 'back' }), enabled: () => historyIndex >= 0 },
        { id: 'view.forward', label: 'Forward', run: () => void viewer.navigate({ kind: 'forward' }), enabled: () => !!history[historyIndex + 2] },
        { id: 'view.zoom-in', label: 'Zoom in', run: () => zoomBy(1.2), enabled: () => !!projection },
        { id: 'view.zoom-out', label: 'Zoom out', run: () => zoomBy(1 / 1.2), enabled: () => !!projection },
        { id: 'view.zoom', label: 'Zoom', run: value => zoomTo(Number(value)), enabled: () => !!projection, value: () => Math.round(screenScale() * 100) + '%' },
        { id: 'view.actual-size', label: 'Actual size', run: () => zoomTo(100), enabled: () => !!projection },
        { id: 'edit.find', label: 'Find…', run: () => { search.focus(); search.select(); }, enabled: () => !!projection },
        { id: 'view.selection', label: 'Selection', run: () => { }, enabled: () => !!selection, value: () => selection ? JSON.stringify(selection) : '' },
        { id: 'view.redraw', label: 'Redraw', run: () => { draw(); updateToolbarState(); emit({ kind: 'viewport', ...(viewport.activeView ? { target: viewport.activeView } : {}) }); } },
    ]));
    let hintElement;
    const configuredEmptyViews = new Map();
    const viewTypeChosen = (event) => {
        const requested = (0, native_js_2.object)((0, native_js_2.object)(event.detail).view);
        const view = projection?.views.find(candidate => candidate.ref.file === requested.file && candidate.ref.id === requested.id);
        if (view)
            configuredEmptyViews.set((0, native_js_2.refKey)(view.ref), (0, native_js_2.str)(view.record.profile));
        renderHint();
    };
    container.addEventListener('ddn:view-type-chosen', viewTypeChosen);
    cleanups.push(() => container.removeEventListener('ddn:view-type-chosen', viewTypeChosen));
    function renderHint() {
        hintElement?.remove();
        hintElement = undefined;
        if (!projection || container.dataset.controls === 'host')
            return;
        const editing = container.hasAttribute('data-ddn-editing');
        const views = projection.views.length;
        const activeRef = currentViewRef();
        const active = activeRef ? projection.views.find(view => (0, native_js_2.refKey)(view.ref) === (0, native_js_2.refKey)(activeRef)) : undefined;
        if (editing && active && configuredEmptyViews.get((0, native_js_2.refKey)(active.ref)) === (0, native_js_2.str)(active.record.profile))
            return;
        if (active && ((0, adapters_js_1.isDataProfile)((0, native_js_2.str)(active.record.profile)) || active.record.profile === 'table.records@1' || active.record.kind === 'document'))
            return;
        const elements = activeRef ? projection.entries.filter(e => e.definition.owner !== 'view' && (0, native_js_2.refKey)(e.view.ref) === (0, native_js_2.refKey)(activeRef)).length : 0;
        if (views > 0 && (elements > 0 || !expandedView && !viewport.activeView && projection.entries.some(entry => entry.definition.owner !== 'view')))
            return;
        hintElement = document.createElement('div');
        hintElement.className = 'ddn-viewer-hint';
        hintElement.setAttribute('role', 'note');
        const text = document.createElement('p');
        const actions = document.createElement('div');
        actions.className = 'ddn-hint-actions';
        const action = (label, detail, primary = false) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            if (primary)
                b.dataset.primary = '';
            b.addEventListener('click', () => container.dispatchEvent(new CustomEvent('ddn:action', { detail, bubbles: true })));
            actions.append(b);
            return b;
        };
        if (editing) {
            const newDocument = !views && !runtime.sources()?.files.some(file => file.text.trim());
            text.textContent = newDocument ? 'Create a workarea or a standalone view.' : 'What kind of diagram or graph do you want this view to display?';
            action(newDocument ? 'New document…' : 'Choose diagram type…', { action: 'choose-view-type' }, true);
        }
        else {
            text.textContent = views ? 'This view has no elements.' : 'This document has no view to show.';
            action('Open a sample…', { action: 'open-sample' });
            action('Open files…', { action: 'open-files' });
        }
        const small = document.createElement('small');
        small.textContent = editing ? views ? 'Choose a diagram method and type to load its defaults and design tools.' : 'Choose how to organize your design, then pick a diagram method and type.' : 'You can also drop a .ddn file here.';
        hintElement.append(text, actions, small);
        overlays.append(hintElement);
    }
    container.addEventListener('ddn:action', event => {
        const detail = (0, native_js_2.object)(event.detail);
        if (detail.action === 'open-sample')
            document.dispatchEvent(new CustomEvent('ddn:open-sample'));
        else if (detail.action === 'open-files')
            document.dispatchEvent(new CustomEvent('ddn:open-files'));
    });
    const hintObserver = new MutationObserver(renderHint);
    hintObserver.observe(container, { attributes: true, attributeFilter: ['data-ddn-editing', 'data-controls'] });
    cleanups.push(() => hintObserver.disconnect());
    updateToolbarState();
    on(search, 'input', renderOutline);
    let dragMoved = false;
    const isEditableTarget = (target) => {
        const el = target;
        return !!el?.closest?.('input,textarea,select,[contenteditable="true"],button');
    };
    on(win, 'keydown', event => {
        if ((event.code === 'Space' || event.key === ' ') && !isEditableTarget(event.target)) {
            spaceHeld = true;
            svg.classList.add('ddn-space-pan');
        }
    });
    on(win, 'keyup', event => {
        if (event.code === 'Space' || event.key === ' ') {
            spaceHeld = false;
            svg.classList.remove('ddn-space-pan');
        }
    });
    on(svg, 'click', event => {
        if (dragMoved) {
            dragMoved = false;
            return;
        }
        const group = event.target.closest('[data-ref]');
        if (group) {
            const ref = JSON.parse(group.getAttribute('data-ref') ?? 'null');
            const occ = group.getAttribute('data-occurrence') ?? group.getAttribute('data-occurrence-ref') ?? undefined;
            select(ref, occ, event.shiftKey && group.getAttribute('data-view-frame') !== 'true');
        }
        else if (!event.shiftKey)
            clearSelection();
    });
    let wheelTimer;
    const finishWheel = () => {
        if (wheelTimer !== undefined)
            win.clearTimeout(wheelTimer);
        wheelTimer = undefined;
        updateToolbarState();
    };
    cleanups.push(finishWheel);
    on(svg, 'wheel', event => {
        event.preventDefault();
        if (pinch || drag)
            return;
        if (wheelTimer === undefined)
            rememberCamera(cameraState());
        else
            win.clearTimeout(wheelTimer);
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? svg.clientHeight : 1;
        const delta = event.deltaY * unit;
        if ((0, grid_js_1.viewSetting)(container, 'wheel') === 'pan' && !event.ctrlKey && !event.metaKey) {
            const scale = screenScale(), dx = (event.shiftKey && !event.deltaX ? event.deltaY : event.deltaX) * unit, dy = event.shiftKey && !event.deltaX ? 0 : delta;
            setCamera({ ...viewport, bounds: { ...viewport.bounds, x: viewport.bounds.x + dx / scale, y: viewport.bounds.y + dy / scale } }, false);
        }
        else
            zoomAt(Math.exp(-delta * (event.ctrlKey ? .01 : .0015)), event.clientX, event.clientY, false);
        wheelTimer = win.setTimeout(finishWheel, 180);
    }, { passive: false });
    const pinchState = () => {
        const [a, b] = [...pointers.values()];
        return a && b ? { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, midX: (a.x + b.x) / 2, midY: (a.y + b.y) / 2 } : undefined;
    };
    on(svg, 'pointerdown', event => {
        if (event.button !== 1 && event.button !== 0)
            return;
        finishWheel();
        if (!pointers.size) {
            gestureStart = cameraState();
            dragMoved = false;
        }
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY });
        if (pointers.size === 2) {
            drag = undefined;
            dragMoved = true;
            svg.classList.remove('ddn-panning');
            const state = pinchState();
            if (!state)
                return;
            pinch = { ...state, view: viewport, anchor: toWorld(state.midX, state.midY), scale: screenScale() };
            for (const id of pointers.keys())
                try {
                    if (!svg.hasPointerCapture(id))
                        svg.setPointerCapture(id);
                }
                catch { }
            container.dispatchEvent(new CustomEvent('ddn:gesture', { detail: { gesture: 'pinch-start' }, bubbles: true }));
            return;
        }
        if (event.target.closest('.ddn-ports'))
            return;
        const group = event.target.closest('[data-ref]');
        const readingPan = !container.hasAttribute('data-ddn-editing') && (event.pointerType === 'touch' || group?.getAttribute('data-view-frame') === 'true');
        if (pointers.size > 2 || group && !readingPan && event.button !== 1 && !spaceHeld)
            return;
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, view: viewport };
        if (!group || spaceHeld)
            try {
                svg.setPointerCapture(event.pointerId);
            }
            catch { }
        svg.classList.add('ddn-panning');
    });
    on(svg, 'pointermove', event => {
        const tracked = pointers.get(event.pointerId);
        if (tracked) {
            tracked.x = event.clientX;
            tracked.y = event.clientY;
            if (Math.abs(tracked.x - tracked.startX) + Math.abs(tracked.y - tracked.startY) > 3)
                dragMoved = true;
        }
        if (pinch && pointers.size >= 2) {
            const state = pinchState();
            if (!state)
                return;
            const zoom = Math.min(32, Math.max(.05, pinch.view.zoom * state.dist / pinch.dist));
            const ratio = pinch.view.zoom / zoom, scale = pinch.scale / ratio;
            const x = pinch.anchor.x - (pinch.anchor.x - pinch.view.bounds.x) * ratio - (state.midX - pinch.midX) / scale;
            const y = pinch.anchor.y - (pinch.anchor.y - pinch.view.bounds.y) * ratio - (state.midY - pinch.midY) / scale;
            setCamera({ ...pinch.view, zoom, bounds: { ...pinch.view.bounds, x, y } }, false);
            return;
        }
        if (!drag || drag.id !== event.pointerId)
            return;
        if (Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y) > 3) {
            dragMoved = true;
            try {
                if (!svg.hasPointerCapture(event.pointerId))
                    svg.setPointerCapture(event.pointerId);
            }
            catch { }
        }
        const scale = screenScale(drag.view);
        setCamera({ ...drag.view, bounds: { ...drag.view.bounds, x: drag.view.bounds.x - (event.clientX - drag.x) / scale, y: drag.view.bounds.y - (event.clientY - drag.y) / scale } }, false);
    });
    const endDrag = (event) => {
        const ids = event ? [event.pointerId] : [...pointers.keys()];
        for (const id of ids) {
            pointers.delete(id);
            if (svg.hasPointerCapture(id))
                svg.releasePointerCapture(id);
        }
        if (pinch && pointers.size < 2) {
            pinch = undefined;
            container.dispatchEvent(new CustomEvent('ddn:gesture', { detail: { gesture: 'pinch-end' }, bubbles: true }));
        }
        if (drag && (!event || drag.id === event.pointerId)) {
            drag = undefined;
            svg.classList.remove('ddn-panning');
        }
        if (!pinch && !drag && gestureStart) {
            if (dragMoved && gestureStart.viewport !== viewport)
                rememberCamera(gestureStart);
            gestureStart = undefined;
            updateToolbarState();
        }
    };
    on(win, 'pointerup', endDrag);
    on(win, 'pointercancel', endDrag);
    on(svg, 'lostpointercapture', endDrag);
    on(win, 'blur', () => { spaceHeld = false; svg.classList.remove('ddn-space-pan'); endDrag(); });
    on(svg, 'keydown', event => {
        if (event.key === 'Escape') {
            const wasGesture = !!drag || !!pinch;
            endDrag();
            if (!wasGesture && !container.hasAttribute('data-ddn-editing'))
                clearSelection();
            return;
        }
        if (['+', '=', '-', '0'].includes(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
            event.preventDefault();
            if (event.key === '0')
                void viewer.navigate({ kind: 'fit-workarea' });
            else {
                const rect = svg.getBoundingClientRect();
                zoomAt(event.key === '-' ? 1 / 1.2 : 1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true);
            }
        }
        if (event.key === 'Enter') {
            const group = event.target.closest('[data-ref]');
            if (group)
                select(JSON.parse(group.getAttribute('data-ref') ?? 'null'), group.getAttribute('data-occurrence') ?? undefined);
        }
    });
    if (typeof ResizeObserver !== 'undefined') {
        const observer = new ResizeObserver(() => { draw(); updateToolbarState(); });
        observer.observe(stage);
        cleanups.push(() => observer.disconnect());
    }
    const fonts = document.fonts;
    if (fonts) {
        const changed = () => { fontGeneration++; schedule(); };
        fonts.addEventListener('loadingdone', changed);
        cleanups.push(() => fonts.removeEventListener('loadingdone', changed));
    }
    const viewer = {
        async open(input, task) {
            ensure();
            inspectionDialog?.close();
            finishWheel();
            endDrag();
            const openTicket = ++openGeneration;
            emit({ kind: 'pending' });
            announce('Opening diagram…');
            generation++;
            renderKey = '';
            history.length = 0;
            historyIndex = -1;
            assets.clear();
            geography.clear();
            geographyHashes.clear();
            geographyVersions.clear();
            assetFailures.clear();
            cssCache.clear();
            selection = undefined;
            selectedOccurrence = undefined;
            selectedOccurrences.clear();
            announceHoldUntil = 0;
            restored = undefined;
            expandedView = undefined;
            configuredEmptyViews.clear();
            const result = await runtime.open(input, task);
            if (disposed || openTicket !== openGeneration)
                return result;
            for (const listener of [...openListeners])
                listener();
            runtimeDiagnostics = [...result.diagnostics];
            diagnostics = [...runtimeDiagnostics];
            stale = !!result.snapshot && result.coverage !== result.snapshot.coverage && result.diagnostics.some(d => d.severity === 'error');
            schedule();
            await rendering;
            if (projection && !stale)
                fit(projection.bounds);
            return result;
        },
        setViewport(next) { ensure(); setCamera(next); },
        async navigate(request) {
            ensure();
            finishWheel();
            await rendering;
            if (!projection)
                return;
            if (request.kind === 'fit-workarea')
                fit(projection.bounds, undefined, { expandedView: undefined, restored: undefined });
            else if (request.kind === 'restore') {
                if (restored)
                    setCamera(restored, true, { expandedView: undefined, restored: undefined });
                else
                    fit(projection.bounds, undefined, { expandedView: undefined, restored: undefined });
            }
            else if (request.kind === 'back') {
                const next = history[historyIndex];
                if (next) {
                    if (historyIndex === history.length - 1)
                        history.push(cameraState());
                    historyIndex--;
                    setCamera(next.viewport, false, next);
                }
            }
            else if (request.kind === 'forward') {
                const next = history[historyIndex + 2];
                if (next) {
                    historyIndex++;
                    setCamera(next.viewport, false, next);
                }
            }
            else if ('target' in request) {
                const entry = projection.entries.find(e => (0, native_js_2.refKey)(request.kind === 'focus' ? e.definition.ref : e.view.ref) === (0, native_js_2.refKey)(request.target));
                if (entry) {
                    const bounds = request.kind === 'focus' ? (entry.item.bounds.width > 0 && entry.item.bounds.height > 0 ? entry.item.bounds : viewFrame(entry.view.ref)?.item.bounds ?? projection.bounds) : standalone ? projection.bounds : viewFrame(entry.view.ref)?.item.bounds ?? entry.item.bounds;
                    if (request.kind === 'expand-view' || expandedView) {
                        const mode = { expandedView: entry.view.ref, restored: restored ?? viewport };
                        if (request.kind === 'focus')
                            fit(bounds, entry.view.ref, mode);
                        else
                            setCamera({ bounds: { ...bounds }, zoom: 1, activeView: entry.view.ref }, true, mode);
                    }
                    else
                        fit(bounds, entry.view.ref);
                }
            }
        },
        async inspect(target) {
            ensure();
            await rendering;
            const snapshot = runtime.snapshot();
            if (!snapshot)
                throw new Error('No workarea is open');
            const entry = (0, native_js_2.findRecord)(snapshot, target);
            if (!entry)
                throw new Error('Unknown inspection target');
            const resolved = styledResolve(snapshot, target);
            return { target, revision: snapshot.revision, properties: resolved.properties.map(p => { const explicit = (0, native_js_2.pathValue)(entry.record, p.path); return { path: p.path, effective: p.value, origin: p.origin, ...(explicit !== undefined ? { explicit: explicit } : {}) }; }), diagnostics: diagnostics.filter(d => !d.target || (0, native_js_2.refKey)(d.target) === (0, native_js_2.refKey)(target)) };
        },
        setPreview(properties) {
            ensure();
            const errors = (0, index_js_1.validatePreview)(properties ?? {});
            if (Array.isArray(errors) && errors.length)
                throw new Error(errors.map(d => d.message).join('; '));
            preview = properties ? { ...properties } : undefined;
            styleGeneration++;
            schedule();
        },
        async capture(request) {
            ensure();
            await rendering;
            if (request.cancel?.aborted)
                return { ok: false, reason: 'cancelled', diagnostics: [] };
            const snapshot = currentSnapshot;
            if (!snapshot || !projection)
                return { ok: false, reason: 'incomplete', diagnostics };
            if (stale && request.stale === 'reject')
                return { ok: false, reason: 'stale', diagnostics };
            if ((!projection.coverage.complete || assetFailures.size > 0) && request.partial === 'reject')
                return { ok: false, reason: 'incomplete', diagnostics };
            const scene = request.includePreview ? projection : (0, native_js_2.projectSnapshot)(snapshot, { ...(standalone && projection.views[0] ? { onlyView: projection.views[0].ref } : {}), resolve: (target, context) => styledResolve(snapshot, target, context), measure, geography, assetSizes: assetSizes(), supports: profile => native_js_2.availableProjectionProfiles.has(profile) && !!(0, registry_js_1.registrations)(runtime.registry).profiles?.some(p => p.id === profile) });
            let items = [...scene.items];
            if (request.scope.kind !== 'workarea') {
                const scope = request.scope;
                items = items.filter(item => scope.kind === 'item' ? (0, native_js_2.refKey)(item.target) === (0, native_js_2.refKey)(scope.target) : (0, native_js_2.refKey)(item.view) === (0, native_js_2.refKey)(scope.target));
            }
            if (!items.length)
                return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture scope is unavailable.' }] };
            if (items.every(item => item.bounds.width <= 0 || item.bounds.height <= 0))
                return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture scope is clipped outside its fixed view surface.' }] };
            let bounds = typeof request.extent === 'object' ? request.extent : request.extent === 'viewport' ? viewBox() : (0, native_js_2.unionBounds)(items.map(i => i.bounds));
            if (standalone && typeof request.extent === 'object') {
                const extent = scene.bounds, x = Math.max(bounds.x, extent.x), y = Math.max(bounds.y, extent.y);
                bounds = { x, y, width: Math.min(bounds.x + bounds.width, extent.x + extent.width) - x, height: Math.min(bounds.y + bounds.height, extent.y + extent.height) - y };
                if (bounds.width <= 0 || bounds.height <= 0)
                    return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture extent is outside the standalone view.' }] };
            }
            const warnings = [...diagnostics];
            if (request.scope.kind === 'view' || request.scope.kind === 'document') {
                const target = (0, native_js_2.findRecord)(snapshot, request.scope.target), publication = target ? (0, native_js_2.resolveRecord)((0, native_js_2.records)(snapshot), target.record.publication, target.file) : undefined;
                if (publication && request.extent === 'content' && ['svg', 'png'].includes(request.format)) {
                    const resolvedPublication = styledResolve(snapshot, publication.ref);
                    const workareaRecord = (0, native_js_2.records)(snapshot).find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
                    const resolvedWorkarea = workareaRecord ? styledResolve(snapshot, workareaRecord.ref) : undefined;
                    const workareaOrigins = Object.fromEntries((resolvedWorkarea?.properties ?? []).map(p => [p.path, p.origin]));
                    const pubValues = resolvedWorkarea ? (0, native_js_2.inheritedPresentation)(resolvedPublication.values, resolvedPublication.properties, resolvedWorkarea.values, workareaOrigins, undefined, 'view') : resolvedPublication.values;
                    const published = (0, native_js_2.publicationScene)(items, bounds, { ...publication, record: pubValues }, (0, native_js_2.titleOf)(target.record), new Date().toISOString().slice(0, 10));
                    if (published.diagnostics.some(d => d.severity === 'error'))
                        return { ok: false, reason: 'invalid', diagnostics: published.diagnostics };
                    items = published.items;
                    bounds = published.bounds;
                    warnings.push(...published.diagnostics);
                }
            }
            if (stale)
                warnings.push({ code: 'capture-stale', severity: 'warning', message: 'Capture contains a prior valid revision.' });
            const manifest = { revision: snapshot.revision, versions: snapshot.versions, coverage: assetFailures.size ? { ...scene.coverage, complete: false, unavailable: [...scene.coverage.unavailable, ...[...assetFailures].map(id => 'asset:' + id)] } : scene.coverage, styleGeneration: String(styleGeneration), fontGeneration: String(fontGeneration), assets: Object.fromEntries([...geographyHashes, ...[...assets].map(([id, asset]) => [id, asset.hash])]), previewIncluded: request.includePreview, warnings };
            const adapter = options.outputs?.find(a => a.formats.includes(request.format));
            if (adapter)
                return adapter.capture({ snapshot, scene: items, manifest }, request);
            const output = (name, mime, content) => ({ ok: true, artifacts: [{ name, mime, blob: new Blob([content], { type: mime }) }], manifest });
            const viewBackground = standalone && scene.views[0] ? styledResolve(snapshot, scene.views[0].ref).values : undefined;
            const captureBackground = viewBackground ? (0, native_js_2.str)((0, native_js_2.pathValue)(viewBackground, 'background.color'), 'transparent') : workareaBackground;
            const captureTexture = standalone ? undefined : workareaTexture;
            if (request.format === 'svg')
                return output('diagram.svg', 'image/svg+xml', serializeScene(document, items, bounds, assets, captureBackground, captureTexture));
            if (request.format === 'json')
                return output('diagram.json', 'application/json', JSON.stringify(snapshot.normalized, null, 2));
            const targets = new Map(items.map(item => [(0, native_js_2.refKey)(item.target), (0, native_js_2.findRecord)(snapshot, item.target)]));
            if (request.format === 'markdown' || request.format === 'md') {
                const chunks = [];
                for (const record of targets.values()) {
                    if (!record)
                        continue;
                    chunks.push(`## ${(0, native_js_2.titleOf)(record.record)}`);
                    const data = displayTableData(snapshot, record);
                    if (data.rows.length) {
                        const clean = (v) => String(v ?? '').replaceAll('|', '\\|').replace(/\r?\n/g, ' ');
                        chunks.push('| ' + data.columns.map(c => clean(c.label ?? c.id)).join(' | ') + ' |', '| ' + data.columns.map(() => '---').join(' | ') + ' |', ...data.rows.map(row => '| ' + row.map(clean).join(' | ') + ' |'));
                    }
                    const note = (0, native_js_2.str)((0, native_js_2.pathValue)(record.record, 'draft.text')) || (0, native_js_2.str)((0, native_js_2.pathValue)(record.record, 'content.text'));
                    if (note)
                        chunks.push(note);
                    chunks.push('');
                }
                return output('diagram.md', 'text/markdown', chunks.join('\n'));
            }
            if (request.format === 'csv') {
                const candidates = [...targets.values()].filter((r) => !!r && (r.owner === 'definition' || r.record.profile === 'table.records@1') && displayTableData(snapshot, r).rows.length > 0);
                if (candidates.length !== 1)
                    return { ok: false, reason: 'unsupported', diagnostics: [{ code: 'csv-scope', severity: 'error', message: 'CSV capture requires one selected table.' }] };
                const data = displayTableData(snapshot, candidates[0]);
                const cell = (v) => '"' + String(v ?? '').replaceAll('"', '""') + '"';
                return output('table.csv', 'text/csv', [data.columns.map(c => c.label ?? c.id), ...data.rows].map(row => row.map(cell).join(',')).join('\r\n'));
            }
            if (request.format === 'png') {
                if (bounds.width > 16384 || bounds.height > 16384 || bounds.width * bounds.height > 64000000)
                    return { ok: false, reason: 'budget-exceeded', diagnostics: [] };
                const url = URL.createObjectURL(new Blob([serializeScene(document, items, bounds, assets, captureBackground, captureTexture)], { type: 'image/svg+xml' }));
                try {
                    const image = new win.Image();
                    image.src = url;
                    await image.decode();
                    const outputCanvas = document.createElement('canvas');
                    outputCanvas.width = Math.ceil(bounds.width);
                    outputCanvas.height = Math.ceil(bounds.height);
                    const context = outputCanvas.getContext('2d');
                    if (!context)
                        throw new Error('Canvas unavailable');
                    context.drawImage(image, 0, 0);
                    const blob = await new Promise((resolve, reject) => outputCanvas.toBlob(value => value ? resolve(value) : reject(new Error('PNG encoding failed')), 'image/png'));
                    return { ok: true, artifacts: [{ name: 'diagram.png', mime: 'image/png', blob }], manifest };
                }
                catch (error) {
                    return { ok: false, reason: 'invalid', diagnostics: [{ code: 'capture-failed', severity: 'error', message: String(error) }] };
                }
                finally {
                    URL.revokeObjectURL(url);
                }
            }
            return { ok: false, reason: 'unsupported', diagnostics: [{ code: 'output-unavailable', severity: 'error', message: `Output adapter ${request.format} is not installed.` }] };
        },
        subscribe(listener) { ensure(); listeners.add(listener); return () => listeners.delete(listener); },
        destroy() {
            inspectionDialog?.close();
            if (disposed)
                return;
            disposed = true;
            generation++;
            endDrag();
            for (const cleanup of cleanups)
                cleanup();
            container.remove();
            emit({ kind: 'disposed' });
            listeners.clear();
            selectionListeners.clear();
            openListeners.clear();
            assets.clear();
            geography.clear();
            geographyHashes.clear();
            geographyVersions.clear();
            assetFailures.clear();
            cssCache.clear();
            handles.delete(viewer);
            if (ownsRuntime)
                runtime.destroy();
        },
    };
    handles.set(viewer, { runtime, element, surface: svg, container, overlays, ownerDocument: document, selectedOccurrences, scene: () => projection, viewport: () => viewport, selected: () => selection, clearSelection, expanded: () => expandedView, stage, subscribeOpen(listener) { openListeners.add(listener); return () => openListeners.delete(listener); }, selectedEntry: () => projection?.entries.find(e => selectedOccurrence ? e.item.occurrence === selectedOccurrence : !!selection && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(selection)), select, subscribeSelection(listener) { selectionListeners.add(listener); return () => selectionListeners.delete(listener); }, refresh: async () => { schedule(); await rendering; }, whenRendered: () => rendering, diagnostics: () => diagnostics, toWorld, announce });
    if (runtime.snapshot())
        schedule();
    return viewer;
}

},
"viewer/src/grid.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.gridStep = gridStep;
exports.viewSetting = viewSetting;
const native_js_1 = require("presentation/src/native.js");
function gridStep(snapshot) {
    const workarea = snapshot ? (0, native_js_1.records)(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile) : undefined;
    const grid = workarea?.record.grid;
    const value = typeof grid === 'number' ? grid : (0, native_js_1.num)((0, native_js_1.object)(grid).size ?? (0, native_js_1.object)(grid).step ?? (0, native_js_1.object)(grid).spacing, 16);
    return Number.isFinite(value) && value >= 2 && value <= 1000 ? value : 16;
}
function viewSetting(element, name) {
    return element.closest(`[data-ddn-${name}]`)?.getAttribute(`data-ddn-${name}`) ?? undefined;
}

},
"viewer/src/native.js":function(module,exports,require){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
__exportStar(require("viewer/src/core.js"), exports);

},
"viewer/src/side-tabs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sideTabs = sideTabs;
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
let serial = 0;
const CSS = `.ddn-panel-sections[hidden]{display:none!important}.ddn-panel-sections{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;min-width:0}.ddn-side-tabs{display:flex;flex-direction:column;gap:3px;align-items:stretch;align-self:start;position:sticky;top:40px;min-width:0;border-right:1px solid var(--ddn-ui-border);padding-right:6px}.ddn-viewer .ddn-side-tabs[role=tablist] button,.ddn-side-tabs[role=tablist] button{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4px;margin:0;width:100%;padding:7px 4px;min-height:44px;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--ddn-ui-muted);font:500 10px/1.3 system-ui,sans-serif;text-align:center;overflow-wrap:normal;word-break:normal;hyphens:none;cursor:pointer}.ddn-side-tabs[role=tablist] button[aria-selected=true]{color:var(--ddn-ui-accent);border-color:color-mix(in srgb,var(--ddn-ui-accent) 45%,transparent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-ui-surface))}.ddn-side-tabs[role=tablist] button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:-2px}.ddn-side-tabs small{font-size:9px;opacity:.8}.ddn-panel-section{min-width:0}.ddn-panel-section>[hidden],.ddn-panel-section[hidden]{display:none!important}.ddn-side-tabs svg{width:16px;height:16px}.ddn-side-tab-label{display:block;max-width:100%;white-space:normal;text-wrap:balance}.ddn-side-tabs svg{flex:none}`;
function sideTabs(container, label, tabs, selected, onSelect) {
    const document = container.ownerDocument;
    if (!document.querySelector('style[data-ddn-side-tabs]')) {
        const style = document.createElement('style');
        style.dataset.ddnSideTabs = '';
        style.textContent = CSS;
        document.head.append(style);
    }
    const element = document.createElement('div');
    element.className = 'ddn-side-tabs';
    element.setAttribute('role', 'tablist');
    element.setAttribute('aria-label', label);
    element.setAttribute('aria-orientation', 'vertical');
    const group = 'ddn-sections-' + (++serial), buttons = new Map();
    function choose(id, notify = true) {
        selected = id;
        for (const [key, button] of buttons) {
            button.setAttribute('aria-selected', String(key === id));
            button.tabIndex = key === id ? 0 : -1;
        }
        if (notify)
            onSelect(id);
    }
    for (const tab of tabs) {
        const button = document.createElement('button');
        button.type = 'button';
        button.id = group + '-' + tab.id.replace(/[^\w-]/g, '-');
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-label', tab.label);
        button.title = tab.label + (tab.count === undefined ? '' : ` · ${tab.count} available`);
        const label = document.createElement('span');
        label.className = 'ddn-side-tab-label';
        label.textContent = tab.label;
        button.append((0, ui_icons_js_1.uiIcon)(document, tab.icon ?? 'grid'), label);
        if (tab.count !== undefined) {
            const count = document.createElement('small');
            count.textContent = String(tab.count);
            button.append(count);
        }
        button.addEventListener('click', () => choose(tab.id));
        buttons.set(tab.id, button);
        element.append(button);
    }
    element.addEventListener('keydown', event => {
        if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key))
            return;
        const keys = [...buttons.keys()], index = keys.indexOf(selected);
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? keys.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + keys.length) % keys.length;
        const id = keys[next];
        if (id) {
            choose(id);
            buttons.get(id).focus();
        }
    });
    choose(selected, false);
    container.append(element);
    return { element, select: (id) => choose(id), connect(panel) {
            panel.setAttribute('role', 'tabpanel');
            panel.id = group + '-panel';
            for (const button of buttons.values())
                button.setAttribute('aria-controls', panel.id);
            panel.setAttribute('aria-labelledby', buttons.get(selected)?.id ?? '');
        }, label(panel) { panel.setAttribute('aria-labelledby', buttons.get(selected)?.id ?? ''); } };
}

},
"viewer/src/standalone-viewport.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.constrainStandaloneViewport = constrainStandaloneViewport;
exports.sameBounds = sameBounds;
function constrainStandaloneViewport(viewport, extent, view) {
    const width = Math.min(extent.width, viewport.bounds.width / viewport.zoom);
    const height = Math.min(extent.height, viewport.bounds.height / viewport.zoom);
    return {
        bounds: {
            x: Math.max(extent.x, Math.min(viewport.bounds.x, extent.x + extent.width - width)),
            y: Math.max(extent.y, Math.min(viewport.bounds.y, extent.y + extent.height - height)),
            width: width * viewport.zoom,
            height: height * viewport.zoom,
        },
        zoom: viewport.zoom,
        ...(view ? { activeView: view } : {}),
    };
}
function sameBounds(a, b) {
    return ['x', 'y', 'width', 'height'].every(key => Math.abs(a[key] - b[key]) < .001);
}

},
"viewer/src/status-hint.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.statusHint = statusHint;
exports.installStatusHint = installStatusHint;
const descriptions = {
    draft: 'Draft — free-form design; information may be incomplete.',
    'in-progress': 'In progress — structured design; information may still be incomplete.',
    'in-review': 'In review — complete and verified, awaiting acceptance.',
    accepted: 'Accepted — accepted by an authorized user; acceptance details are recorded.',
};
function statusHint(state) {
    return 'Design status: ' + (descriptions[state] ?? descriptions.draft);
}
function installStatusHint(surface, overlays, id) {
    const document = surface.ownerDocument, tooltip = document.createElement('div');
    tooltip.id = id;
    tooltip.setAttribute('role', 'tooltip');
    tooltip.hidden = true;
    tooltip.style.cssText = 'position:absolute;z-index:20;pointer-events:none;max-width:min(300px,calc(100% - 16px));box-sizing:border-box;padding:8px 10px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);box-shadow:0 4px 14px #0003;font:12px/1.45 Inter,system-ui,sans-serif;overflow-wrap:anywhere';
    overlays.append(tooltip);
    let hovered, focused, described;
    const dot = (target) => target?.closest?.('[data-status-dot]') ?? undefined;
    const update = () => {
        described?.removeAttribute('aria-describedby');
        described = undefined;
        const active = hovered ?? focused;
        if (!active?.isConnected) {
            tooltip.hidden = true;
            return;
        }
        tooltip.textContent = statusHint(active.getAttribute('data-status-dot') ?? 'draft');
        tooltip.hidden = false;
        active.setAttribute('aria-describedby', id);
        described = active;
        const parent = overlays.getBoundingClientRect(), anchor = active.getBoundingClientRect(), size = tooltip.getBoundingClientRect();
        tooltip.style.left = Math.max(8, Math.min(anchor.left - parent.left + anchor.width / 2 - size.width / 2, parent.width - size.width - 8)) + 'px';
        const above = anchor.top - parent.top - size.height - 8;
        tooltip.style.top = Math.max(8, Math.min(above >= 8 ? above : anchor.bottom - parent.top + 8, parent.height - size.height - 8)) + 'px';
    };
    const hide = () => { hovered = focused = undefined; update(); };
    const over = (event) => { hovered = dot(event.target); update(); };
    const out = (event) => { hovered = dot(event.relatedTarget); update(); };
    const focus = (event) => { focused = dot(event.target); update(); };
    const blur = (event) => { focused = dot(event.relatedTarget); update(); };
    const key = (event) => {
        if (event.key === 'Escape')
            hide();
    };
    surface.addEventListener('pointerover', over);
    surface.addEventListener('pointerout', out);
    surface.addEventListener('focusin', focus);
    surface.addEventListener('focusout', blur);
    surface.addEventListener('pointerdown', hide);
    surface.addEventListener('keydown', key);
    return { hide, destroy() {
            hide();
            tooltip.remove();
            surface.removeEventListener('pointerover', over);
            surface.removeEventListener('pointerout', out);
            surface.removeEventListener('focusin', focus);
            surface.removeEventListener('focusout', blur);
            surface.removeEventListener('pointerdown', hide);
            surface.removeEventListener('keydown', key);
        } };
}

},
"viewer/src/svg-assets.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sanitizeSvgAsset = sanitizeSvgAsset;
const elements = new Set(['svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'text', 'tspan', 'defs', 'linearGradient', 'radialGradient', 'stop', 'clipPath', 'mask', 'pattern', 'title', 'desc', 'use']);
const presentation = new Set([
    'color', 'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-opacity', 'stroke-width',
    'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset',
    'opacity', 'stop-color', 'stop-opacity', 'flood-color', 'flood-opacity', 'display', 'visibility', 'overflow',
    'clip-path', 'clip-rule', 'mask', 'filter', 'marker', 'marker-start', 'marker-mid', 'marker-end',
    'font-family', 'font-size', 'font-style', 'font-weight', 'font-variant', 'letter-spacing', 'word-spacing',
    'text-anchor', 'text-decoration', 'dominant-baseline', 'alignment-baseline', 'paint-order', 'vector-effect',
    'shape-rendering', 'text-rendering', 'color-interpolation', 'color-interpolation-filters',
]);
function safePaint(value) {
    if (/[\\{}<>@\u0000-\u001f]/.test(value) || /\/\*|\*\//.test(value))
        return undefined;
    if (/url\s*\(/i.test(value)) {
        const match = /^url\(\s*(?:"(#[a-zA-Z0-9_.:-]+)"|'(#[a-zA-Z0-9_.:-]+)'|(#[a-zA-Z0-9_.:-]+))\s*\)$/i.exec(value);
        return match ? 'url(' + (match[1] ?? match[2] ?? match[3]) + ')' : undefined;
    }
    for (const call of value.matchAll(/([a-zA-Z_-][a-zA-Z0-9_-]*)\s*\(/g))
        if (!['rgb', 'rgba', 'hsl', 'hsla'].includes(call[1].toLowerCase()))
            return undefined;
    return value;
}
function sanitizeSvgAsset(svgDocument, hostDocument) {
    const parsed = hostDocument.createElement('span').style;
    for (const node of [svgDocument.documentElement, ...Array.from(svgDocument.querySelectorAll('*'))]) {
        if (!elements.has(node.localName)) {
            node.remove();
            continue;
        }
        parsed.cssText = node.getAttribute('style') ?? '';
        for (let index = 0; index < parsed.length; index++) {
            const name = parsed.item(index);
            if (!presentation.has(name))
                continue;
            const value = safePaint(parsed.getPropertyValue(name).trim());
            if (value !== undefined)
                node.setAttribute(name, value);
        }
        for (const attribute of Array.from(node.attributes)) {
            const name = attribute.localName, value = attribute.value;
            if (/^on/i.test(name) || name === 'style' || name === 'src' || name === 'base' ||
                (name === 'href' && !/^#[a-zA-Z0-9_.:-]+$/.test(value)) ||
                (presentation.has(name) && safePaint(value) === undefined) ||
                (/url\s*\(/i.test(value) && safePaint(value) === undefined))
                node.removeAttributeNode(attribute);
        }
    }
}

}});})();
