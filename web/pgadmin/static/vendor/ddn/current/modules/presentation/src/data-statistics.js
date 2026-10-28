import { quantile, sum, interpolate } from './data-common.js';
/** R-7 quantiles retain interpolation contributors rather than inventing observations. */
export function quantileContributors(values, probability) {
    const ordered = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value || a.index - b.index);
    if (!ordered.length)
        throw new Error('Quantiles require observations.');
    const position = Math.max(0, Math.min(ordered.length - 1, (ordered.length - 1) * probability));
    const lo = Math.floor(position), hi = Math.ceil(position), a = ordered[lo], b = ordered[hi];
    return { value: interpolate(a.value, b.value, position - lo), indices: lo === hi ? [a.index] : [a.index, b.index], weights: lo === hi ? [1] : [1 - (position - lo), position - lo] };
}
export function histogramBins(values, count, domain) {
    if (!values.length || !Number.isInteger(count) || count < 2 || count > 100)
        throw new Error('Histogram needs data and 2..100 bins.');
    const minimum = domain?.[0] ?? Math.min(...values), maximum = domain?.[1] ?? Math.max(...values);
    const low = minimum === maximum ? minimum - .5 : minimum, high = minimum === maximum ? maximum + .5 : maximum;
    if (!(high > low))
        throw new Error('Histogram domain must increase.');
    const bins = Array.from({ length: count }, (_, i) => ({ low: interpolate(low, high, i / count), high: interpolate(low, high, (i + 1) / count), count: 0, indices: [] }));
    values.forEach((value, index) => {
        if (value < low || value > high)
            return;
        // Compare the actual boundaries: normalization can round an exact
        // boundary down (e.g. 45 in [30,150] / 8) into the preceding bin.
        let first = 0, last = count;
        while (first + 1 < last) {
            const middle = (first + last) >>> 1;
            if (value < bins[middle].low)
                last = middle;
            else
                first = middle;
        }
        const bin = bins[first];
        bin.count++;
        bin.indices.push(index);
    });
    return bins;
}
export function kernelDensity(values, points = 81) {
    if (values.length < 2)
        throw new Error('KDE is UNKNOWN with fewer than two observations.');
    const mean = sum(values) / values.length, sd = Math.sqrt(sum(values.map(value => (value - mean) ** 2)) / values.length);
    const bandwidth = 1.06 * sd * values.length ** -.2;
    if (!(bandwidth > 0))
        throw new Error('KDE is UNKNOWN for zero-variance samples.');
    const low = Math.min(...values) - 3 * bandwidth, high = Math.max(...values) + 3 * bandwidth;
    return { bandwidth, points: Array.from({ length: points }, (_, i) => { const x = low + (high - low) * i / (points - 1), y = sum(values.map(v => Math.exp(-.5 * ((x - v) / bandwidth) ** 2))) / (values.length * bandwidth * Math.sqrt(2 * Math.PI)); return [x, y]; }) };
}
/** Acklam's deterministic inverse-normal approximation; probability is strictly inside (0,1). */
export function inverseNormal(p) {
    if (!(p > 0 && p < 1))
        throw new Error('Normal quantile probability must be in (0,1).');
    const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
    const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
    const c = [-.00778489400243029, -.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
    const d = [.00778469570904146, .32246712907004, 2.445134137143, 3.75440866190742];
    const poly = (coefficients, x) => coefficients.reduce((value, coefficient) => value * x + coefficient, 0);
    if (p < .02425) {
        const q = Math.sqrt(-2 * Math.log(p));
        return poly(c, q) / (poly(d, q) * q + 1);
    }
    if (p > .97575) {
        const q = Math.sqrt(-2 * Math.log(1 - p));
        return -poly(c, q) / (poly(d, q) * q + 1);
    }
    const q = p - .5, r = q * q;
    return poly(a, r) * q / (poly(b, r) * r + 1);
}
export function fiveNumber(values, minmax = false) {
    const q1 = quantile(values, .25), median = quantile(values, .5), q3 = quantile(values, .75), iqr = q3 - q1;
    const inside = values.filter(value => minmax || value >= q1 - 1.5 * iqr && value <= q3 + 1.5 * iqr);
    return { q1, median, q3, low: Math.min(...inside), high: Math.max(...inside), outliers: values.map((value, index) => ({ value, index })).filter(item => !minmax && (item.value < q1 - 1.5 * iqr || item.value > q3 + 1.5 * iqr)) };
}
export function linearTrend(points) {
    const n = points.length, mx = sum(points.map(p => p[0])) / n, my = sum(points.map(p => p[1])) / n;
    const denominator = sum(points.map(p => (p[0] - mx) ** 2));
    if (n < 2 || denominator === 0)
        throw new Error('Linear trend is UNKNOWN without distinct x coordinates.');
    const slope = sum(points.map(p => (p[0] - mx) * (p[1] - my))) / denominator;
    return { slope, intercept: my - slope * mx };
}
/** Deterministic degree-one LOESS, tricube weights, 2/3 span, no robust
 * residual iterations. At most 201 evaluation points bound rendering cost. */
export function loessTrend(points) {
    if (points.length < 3 || points.length > 10000 || points.some(point => !point.every(Number.isFinite)))
        throw new Error('LOESS requires 3..10000 finite observations.');
    const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]), coordinates = [...new Set(sorted.map(point => point[0]))];
    if (coordinates.length < 2)
        throw new Error('LOESS is UNKNOWN without distinct x coordinates.');
    const count = Math.max(3, Math.ceil(sorted.length * 2 / 3));
    const evaluation = coordinates.length <= 201 ? coordinates : Array.from({ length: 201 }, (_, index) => coordinates[Math.round(index * (coordinates.length - 1) / 200)]);
    return evaluation.map(x => {
        const distances = sorted.map(point => Math.abs(point[0] - x)).sort((a, b) => a - b), radius = distances[Math.min(count - 1, distances.length - 1)] || distances.find(distance => distance > 0);
        // Slight expansion keeps a three-point neighborhood nonsingular while
        // retaining exactly zero influence beyond the selected distance.
        const bandwidth = radius * (1 + 1e-12);
        const weighted = sorted.map(point => ({ dx: point[0] - x, y: point[1], weight: Math.abs(point[0] - x) <= radius ? (1 - (Math.abs(point[0] - x) / bandwidth) ** 3) ** 3 : 0 }));
        const total = sum(weighted.map(point => point.weight)), meanX = sum(weighted.map(point => point.weight * point.dx)) / total, meanY = sum(weighted.map(point => point.weight * point.y)) / total;
        const variance = sum(weighted.map(point => point.weight * (point.dx - meanX) ** 2)), covariance = sum(weighted.map(point => point.weight * (point.dx - meanX) * (point.y - meanY)));
        const y = variance > 0 ? meanY - covariance / variance * meanX : meanY;
        if (!Number.isFinite(y))
            throw new Error('LOESS arithmetic exceeded the finite numeric range.');
        return [x, y];
    });
}
export function histogramPlan(values, options = {}) {
    if (values.length < 2)
        throw new Error('Histogram requires at least two samples.');
    let low = options.minimum ?? Math.min(...values), high = options.maximum ?? Math.max(...values);
    if (low === high && options.minimum === undefined && options.maximum === undefined) {
        low -= .5;
        high += .5;
    }
    if (!Number.isFinite(low) || !Number.isFinite(high) || !(high > low))
        throw new Error('Histogram domain must be finite and increasing.');
    let count = options.count ?? Math.min(40, Math.max(5, Math.ceil(Math.sqrt(values.length))));
    if (options.step !== undefined) {
        const exact = high / options.step - low / options.step;
        if (!(options.step > 0) || !Number.isFinite(exact) || Math.abs(exact - Math.round(exact)) > 1e-10)
            throw new Error('Bin step must divide the declared domain into equal-width bins.');
        if (options.count !== undefined && options.count !== Math.round(exact))
            throw new Error('Histogram count and step disagree.');
        count = Math.round(exact);
    }
    const selected = [];
    values.forEach((value, index) => {
        if (value < low || value > high) {
            if ((options.outside ?? 'error') === 'error')
                throw new Error('A sample is outside the declared histogram domain.');
            if (options.outside === 'drop')
                return;
            value = Math.max(low, Math.min(high, value));
        }
        selected.push({ value, index });
    });
    if (!selected.length)
        throw new Error('Histogram range excluded every sample.');
    return histogramBins(selected.map(item => item.value), count, [low, high]).map(bin => ({ ...bin, indices: bin.indices.map(index => selected[index].index), value: options.normalize === true || options.normalize === 'probability' ? bin.count / selected.length : options.normalize === 'density' ? bin.count / selected.length / (bin.high - bin.low) : bin.count }));
}
//# sourceMappingURL=data-statistics.js.map