import { type DataRecord } from './model.js';
/** Finite declared scales return no color for missing values; missing never means zero. */
export declare function matrixEncoding(encoding: DataRecord, values: readonly unknown[]): (value: unknown) => string;
