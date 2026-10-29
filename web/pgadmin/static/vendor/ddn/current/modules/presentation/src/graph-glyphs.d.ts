import type { Bounds, Json, Primitive } from '@ddn/types';
import { type DataRecord } from './model.js';
export type Point = readonly [
    number,
    number
];
export declare const line: (a: Point, b: Point, stroke?: string, width?: number, dash?: string) => Primitive;
export declare const label: (value: string, x: number, y: number, size?: number, color?: string, extra?: Record<string, Json>) => Primitive;
export declare const box: (bounds: Bounds, fill?: string, stroke?: string, width?: number, dash?: string) => Primitive;
export declare const oval: (bounds: Bounds, fill?: string, stroke?: string, width?: number, dash?: string) => Primitive;
export declare const path: (d: string, fill?: string, stroke?: string, width?: number, dash?: string) => Primitive;
export declare const polygon: (points: readonly Point[], fill?: string, stroke?: string, width?: number) => Primitive;
export declare function rounded(b: Bounds, fill: string, stroke: string, radius?: number, width?: number, dash?: string): Primitive;
export declare const metadata: (record: DataRecord, key: string) => unknown;
export interface GlyphOptions {
    readonly fill?: string;
    readonly stroke?: string;
    readonly width?: number;
    readonly title: string;
    readonly profile: string;
    readonly look?: string;
    readonly seed?: number;
    readonly roughness?: number;
    readonly textScale?: number;
}
export declare const coreCardCode: (role: string) => string;
export declare function coreCardText(role: string, title: string, width: number, scale?: number): {
    height: number;
    typeWidth: number;
    typeLines: readonly string[];
    titleOffset: number;
    titleWidth: number;
    titleLines: readonly string[];
};
/** Small deterministic contour variation preserves the same semantic symbol. */
export declare function sketchPrimitive(primitive: Primitive, seed?: number, roughness?: number): Primitive;
export declare function shadowPrimitive(primitive: Primitive, dx?: number, dy?: number): Primitive | undefined;
/** Profile shapes are ordinary retained SVG primitives, never embedded markup. */
export declare function nodeGlyph(role: string, record: DataRecord, b: Bounds, options: GlyphOptions): Primitive[];
export declare function arrowMarker(point: Point, toward: Point, kind?: string, stroke?: string): Primitive[];
