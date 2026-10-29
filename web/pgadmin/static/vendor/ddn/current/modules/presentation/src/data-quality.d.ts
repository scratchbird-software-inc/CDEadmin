import { DataScene, type Datum } from './data-common.js';
import { type Bin } from './data-statistics.js';
export interface QualityBin extends Bin {
    value: number;
}
export declare function boundaryHistogram(values: readonly number[], boundaries: readonly number[], normalization?: string, outside?: string): QualityBin[];
export interface ParetoValue {
    label: string;
    value: number;
    indices: number[];
    cumulative: number;
    cumulativeIndices: number[];
}
export declare function paretoPlan(values: readonly {
    label: string;
    value: number;
}[]): ParetoValue[];
export interface WaterfallStep {
    kind: 'delta' | 'subtotal' | 'total';
    start: number;
    end: number;
    value: number;
    index: number;
    indices: number[];
}
export declare function waterfallPlan(values: readonly number[], steps: readonly unknown[], baseline?: number): WaterfallStep[];
/** The retained quality operations use raw measurements and an explicit bounded transform. */
export declare function drawQuality(scene: DataScene, mark: string, transform: string, data: readonly Datum[]): void;
