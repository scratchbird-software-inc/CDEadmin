import type { Bounds, Diagnostic, Json, ModelSnapshot, Primitive, Ref } from '@ddn/types';
import type { ProjectedRecord, Resolve } from './project.js';
import { type DataRecord, type LocatedRecord } from './model.js';
export interface Datum {
    values: DataRecord;
    source: LocatedRecord;
    contributors: Ref[];
    ordinal: number;
    row?: number;
}
export interface DataProfileProjection {
    entries: ProjectedRecord[];
    bounds: Bounds;
    diagnostics: Diagnostic[];
    unavailable: string[];
}
export interface DataProjectionOptions {
    resolve?: Resolve;
    measure?: (text: string, size: number, font: string) => number;
    projectChild?: (view: LocatedRecord, bounds: Bounds) => DataProfileProjection;
}
export declare const colors: string[];
export declare const valueAt: (record: DataRecord, key: string) => unknown;
export declare const finite: (value: unknown) => value is number;
export declare const unique: <T>(values: readonly T[]) => T[];
export declare const sum: (values: readonly number[]) => number;
export declare const interpolate: (a: number, b: number, fraction: number) => number;
export declare function extent(values: readonly number[], zero?: boolean): [
    number,
    number
];
export declare const scale: (domain: readonly number[], range: readonly number[]) => (value: number) => number;
export declare const numberLabel: (n: number) => string;
export declare const box: (bounds: Bounds, fill?: string, stroke?: string, extra?: Record<string, Json>) => Primitive;
export declare const ellipse: (x: number, y: number, r: number, fill?: string, extra?: Record<string, Json>) => Primitive;
export declare const path: (d: string, stroke?: string, fill?: string, extra?: Record<string, Json>) => Primitive;
export declare const label: (text: string, x: number, y: number, size?: number, extra?: Record<string, Json>) => Primitive;
export declare const pointsPath: (points: readonly (readonly [number, number])[], close?: boolean) => string;
export declare function boundsOf(points: readonly (readonly [
    number,
    number
])[], padding?: number): Bounds;
export declare function colorScale(value: number, domain: readonly number[]): string;
export declare function arcPath(cx: number, cy: number, radius: number, start: number, end: number, inner?: number): string;
export declare class DataScene {
    readonly snapshot: ModelSnapshot;
    readonly view: LocatedRecord;
    readonly bounds: Bounds;
    readonly effective: DataRecord;
    readonly options: DataProjectionOptions;
    readonly all: LocatedRecord[];
    readonly result: DataProfileProjection;
    readonly settings: DataRecord;
    private count;
    private readonly allowTextOverride;
    readonly extrusionDepths: Map<string, number>;
    constructor(snapshot: ModelSnapshot, view: LocatedRecord, bounds: Bounds, effective: DataRecord, options: DataProjectionOptions);
    issue(message: string, code?: string, severity?: 'error' | 'warning', target?: Ref): void;
    add(name: string, bounds: Bounds, primitives: Primitive[], source?: LocatedRecord, contributors?: readonly Ref[], description?: string, paperSurface?: boolean): void;
    finish(): DataProfileProjection;
    /** Legend/caption entries belong to the view, never to measured records. */
    legend(items: readonly {
        label: string;
        color: string;
    }[], x?: number, y?: number, vertical?: boolean): void;
    caption(text: string): void;
    intensity(domain: readonly number[], unit?: string, x?: number, y?: number, ramp?: (value: number) => string): void;
    selection(): LocatedRecord[];
    data(): Datum[];
    wrap(text: string, width: number, size?: number): string[];
    measure(text: string, size?: number): number;
}
export declare function mergedDatum(values: DataRecord, rows: readonly Datum[]): Datum;
export declare function quantile(values: readonly number[], p: number): number;
export declare function numericDate(value: unknown): number | undefined;
