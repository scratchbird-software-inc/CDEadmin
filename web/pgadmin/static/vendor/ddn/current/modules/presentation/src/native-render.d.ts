import type { Bounds, Primitive } from '@ddn/types';
import { type DataRecord } from './model.js';
export declare const nativeCode: (role: string) => string;
/** Small semantic symbols use retained primitives and stay independent of browser assets. */
export declare function nativeIcon(glyph: string, b: Bounds, color: string): Primitive[];
export declare function nativeContour(role: string, record: DataRecord, b: Bounds, fill: string, stroke: string, weight: number, look: string, roughness: number, seed: number): Primitive[];
export declare function nativeBadges(record: DataRecord, appearance: DataRecord | undefined, view: DataRecord): string[];
export declare function badgePrimitives(values: string[], b: Bounds, size: number, color: string, fill: string): Primitive[];
export declare function inheritedPresentation(values: DataRecord, properties: readonly {
    path: string;
    origin: string;
}[], view: DataRecord): DataRecord;
