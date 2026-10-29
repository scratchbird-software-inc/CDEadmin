/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-75a64c87e8fc","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-6502a4606789","shared-6cf9d24a4527"],"modules":[{"id":"presentation/src/data-encoding.js","bytes":4907,"sha256":"cb72a934fb5a49c18ccb87bf1ec62cb564cf72799694d93945ffdacfc5a0ed9e","dependencies":["presentation/src/model.js","presentation/src/data-common.js"]}],"hash":"96054e000d6bf1dc8a27443324d0e70ed345ecafb36a0dd987b2b50e99475254"},{"presentation/src/data-encoding.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.matrixEncoding = matrixEncoding;
const model_js_1 = require("presentation/src/model.js");
const data_common_js_1 = require("presentation/src/data-common.js");
function matrixEncoding(encoding, values) {
    const mode = (0, model_js_1.str)(encoding.mode, 'numeric'), palette = (0, model_js_1.array)(encoding.colors).filter((value) => typeof value === 'string'), named = (0, model_js_1.str)(encoding.scale, 'blue');
    if (!['numeric', 'categorical', 'threshold'].includes(mode))
        throw new Error('Heatmap mode must be numeric, categorical or threshold.');
    if (!['blue', 'diverging', 'linear'].includes(named))
        throw new Error('Heatmap scale must be blue, diverging or linear.');
    const numeric = values.filter(data_common_js_1.finite), domain = (0, model_js_1.object)(encoding.domain), hasDomain = Object.keys(domain).length > 0;
    if (hasDomain && (!(0, data_common_js_1.finite)(domain.min) || !(0, data_common_js_1.finite)(domain.max) || domain.min >= domain.max))
        throw new Error('Heatmap numeric domain must be finite and increasing.');
    const minimum = (0, model_js_1.num)(domain.min, Math.min(...numeric, 0)), maximum = (0, model_js_1.num)(domain.max, Math.max(...numeric, 1));
    const ramp = (fraction) => {
        const defaultPalette = named === 'diverging' ? ['#2166ac', '#f7f7f7', '#b2182b'] : ['#E5F0FB', '#225784'], steps = palette.length >= 2 ? palette : defaultPalette;
        const position = Math.max(0, Math.min(1, fraction)) * (steps.length - 1), index = Math.min(steps.length - 2, Math.floor(position)), ratio = position - index;
        const parse = (color) => { const full = /^#[0-9a-f]{3}$/i.test(color) ? '#' + [...color.slice(1)].map(c => c + c).join('') : color; return /^#[0-9a-f]{6}$/i.test(full) ? [1, 3, 5].map(offset => parseInt(full.slice(offset, offset + 2), 16)) : undefined; };
        const a = parse(steps[index]), b = parse(steps[index + 1]);
        if (!a || !b)
            return steps[Math.round(position)];
        return `rgb(${a.map((value, channel) => Math.round(value * (1 - ratio) + b[channel] * ratio)).join(',')})`;
    };
    if (mode === 'categorical') {
        const labels = Array.isArray(encoding.labels) ? (0, model_js_1.array)(encoding.labels) : (0, data_common_js_1.unique)(values);
        if (!labels.length || labels.length > 12 || labels.some(value => typeof value !== 'string' && typeof value !== 'boolean' && !(0, data_common_js_1.finite)(value)) || (0, data_common_js_1.unique)(labels).length !== labels.length)
            throw new Error('Categorical heatmaps require 1..12 distinct finite scalar labels.');
        return value => {
            const index = labels.findIndex(label => Object.is(label, value));
            if (index < 0)
                throw new Error('Heatmap value is outside the declared labels.');
            return palette.length ? palette[index % palette.length] : ramp(labels.length === 1 ? .5 : index / (labels.length - 1));
        };
    }
    const boundaries = (0, model_js_1.array)(encoding.boundaries);
    if (boundaries.length && (boundaries.length < 2 || boundaries.length > 13 || boundaries.some((value, index) => !(0, data_common_js_1.finite)(value) || index > 0 && value <= boundaries[index - 1])))
        throw new Error('Threshold boundaries require 2..13 strictly increasing finite numbers.');
    const range = (0, model_js_1.object)(encoding.range);
    if (mode === 'threshold' && !boundaries.length && Object.keys(range).length && (!(0, data_common_js_1.finite)(range.min) || !(0, data_common_js_1.finite)(range.max) || range.min >= range.max))
        throw new Error('Threshold range must be finite and increasing.');
    return value => {
        if (!(0, data_common_js_1.finite)(value))
            throw new Error('Numeric and threshold heatmap cells require finite values.');
        if (hasDomain && (value < minimum || value > maximum))
            throw new Error('Heatmap value is outside the declared domain.');
        if (mode === 'numeric')
            return ramp(minimum === maximum ? .5 : (0, data_common_js_1.scale)([minimum, maximum], [0, 1])(value));
        if (boundaries.length) {
            if (value < boundaries[0] || value > boundaries.at(-1))
                throw new Error('Heatmap value is outside the declared boundaries.');
            const index = value === boundaries.at(-1) ? boundaries.length - 2 : boundaries.findIndex((boundary, i) => i < boundaries.length - 1 && value >= boundary && value < boundaries[i + 1]);
            return palette[index] ?? ramp(boundaries.length === 2 ? .5 : index / (boundaries.length - 2));
        }
        const index = value < (0, model_js_1.num)(range.min, minimum) ? 0 : value < (0, model_js_1.num)(range.max, maximum) ? 1 : 2;
        return palette[index] ?? ramp(index / 2);
    };
}

}});})();
