import { array, object, str, num } from './model.js';
import { finite, unique, scale } from './data-common.js';
/** Finite declared scales return no color for missing values; missing never means zero. */
export function matrixEncoding(encoding, values) {
    const mode = str(encoding.mode, 'numeric'), palette = array(encoding.colors).filter((value) => typeof value === 'string'), named = str(encoding.scale, 'blue');
    if (!['numeric', 'categorical', 'threshold'].includes(mode))
        throw new Error('Heatmap mode must be numeric, categorical or threshold.');
    if (!['blue', 'diverging', 'linear'].includes(named))
        throw new Error('Heatmap scale must be blue, diverging or linear.');
    const numeric = values.filter(finite), domain = object(encoding.domain), hasDomain = Object.keys(domain).length > 0;
    if (hasDomain && (!finite(domain.min) || !finite(domain.max) || domain.min >= domain.max))
        throw new Error('Heatmap numeric domain must be finite and increasing.');
    const minimum = num(domain.min, Math.min(...numeric, 0)), maximum = num(domain.max, Math.max(...numeric, 1));
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
        const labels = Array.isArray(encoding.labels) ? array(encoding.labels) : unique(values);
        if (!labels.length || labels.length > 12 || labels.some(value => typeof value !== 'string' && typeof value !== 'boolean' && !finite(value)) || unique(labels).length !== labels.length)
            throw new Error('Categorical heatmaps require 1..12 distinct finite scalar labels.');
        return value => {
            const index = labels.findIndex(label => Object.is(label, value));
            if (index < 0)
                throw new Error('Heatmap value is outside the declared labels.');
            return palette.length ? palette[index % palette.length] : ramp(labels.length === 1 ? .5 : index / (labels.length - 1));
        };
    }
    const boundaries = array(encoding.boundaries);
    if (boundaries.length && (boundaries.length < 2 || boundaries.length > 13 || boundaries.some((value, index) => !finite(value) || index > 0 && value <= boundaries[index - 1])))
        throw new Error('Threshold boundaries require 2..13 strictly increasing finite numbers.');
    const range = object(encoding.range);
    if (mode === 'threshold' && !boundaries.length && Object.keys(range).length && (!finite(range.min) || !finite(range.max) || range.min >= range.max))
        throw new Error('Threshold range must be finite and increasing.');
    return value => {
        if (!finite(value))
            throw new Error('Numeric and threshold heatmap cells require finite values.');
        if (hasDomain && (value < minimum || value > maximum))
            throw new Error('Heatmap value is outside the declared domain.');
        if (mode === 'numeric')
            return ramp(minimum === maximum ? .5 : scale([minimum, maximum], [0, 1])(value));
        if (boundaries.length) {
            if (value < boundaries[0] || value > boundaries.at(-1))
                throw new Error('Heatmap value is outside the declared boundaries.');
            const index = value === boundaries.at(-1) ? boundaries.length - 2 : boundaries.findIndex((boundary, i) => i < boundaries.length - 1 && value >= boundary && value < boundaries[i + 1]);
            return palette[index] ?? ramp(boundaries.length === 2 ? .5 : index / (boundaries.length - 2));
        }
        const index = value < num(range.min, minimum) ? 0 : value < num(range.max, maximum) ? 1 : 2;
        return palette[index] ?? ramp(index / 2);
    };
}
//# sourceMappingURL=data-encoding.js.map