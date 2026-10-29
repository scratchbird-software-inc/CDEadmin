/** R-7 quantiles retain interpolation contributors rather than inventing observations. */
export declare function quantileContributors(values: readonly number[], probability: number): {
    value: number;
    indices: number[];
    weights: number[];
};
export interface Bin {
    low: number;
    high: number;
    count: number;
    indices: number[];
}
export declare function histogramBins(values: readonly number[], count: number, domain?: readonly [
    number,
    number
]): Bin[];
export declare function kernelDensity(values: readonly number[], points?: number): {
    bandwidth: number;
    points: [
        number,
        number
    ][];
};
/** Acklam's deterministic inverse-normal approximation; probability is strictly inside (0,1). */
export declare function inverseNormal(p: number): number;
export declare function fiveNumber(values: readonly number[], minmax?: boolean): {
    q1: number;
    median: number;
    q3: number;
    low: number;
    high: number;
    outliers: {
        value: number;
        index: number;
    }[];
};
export declare function linearTrend(points: readonly (readonly [
    number,
    number
])[]): {
    slope: number;
    intercept: number;
};
/** Deterministic degree-one LOESS, tricube weights, 2/3 span, no robust
 * residual iterations. At most 201 evaluation points bound rendering cost. */
export declare function loessTrend(points: readonly (readonly [number, number])[]): [number, number][];
export interface HistogramPlanOptions {
    count?: number;
    minimum?: number;
    maximum?: number;
    step?: number;
    outside?: 'error' | 'clip' | 'drop';
    normalize?: boolean | 'count' | 'probability' | 'density';
}
export declare function histogramPlan(values: readonly number[], options?: HistogramPlanOptions): (Bin & {
    value: number;
})[];
