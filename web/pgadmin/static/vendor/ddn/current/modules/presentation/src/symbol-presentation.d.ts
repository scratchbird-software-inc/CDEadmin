import type { Bounds, Diagnostic, Primitive } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type DataRecord, type LocatedRecord } from './model.js';
export interface StandalonePresentation {
    readonly mode: 'image' | 'text';
    readonly electricalIcon?: string;
}
export interface AssetSize {
    readonly width: number;
    readonly height: number;
}
export declare function notePrimitives(value: string, x: number, y: number, width: number, size: number, color: string, measure: (s: string) => number, formatted: boolean, maxLines?: number, bodyFont?: string): {
    primitives: Primitive[];
    height: number;
};
/** Auto recognition is limited to declared artwork, never a decorative background alone. */
export declare function standaloneChoice(effective: DataRecord, definition: LocatedRecord, origins?: Readonly<Record<string, string>>): {
    mode: 'image' | 'text';
    image?: unknown;
    electricalIcon?: string;
} | undefined;
/** Produce paint bounds and routing/hit bounds independently. The latter must
 * never acquire caption margins when a graph lays out or routes this item. */
export declare function standaloneNode(input: {
    definition: LocatedRecord;
    appearance?: LocatedRecord;
    effective: DataRecord;
    origins: Readonly<Record<string, string>>;
    all: readonly LocatedRecord[];
    x: number;
    y: number;
    measure: (value: string, size: number, font: string) => number;
    assetSizes?: ReadonlyMap<string, AssetSize>;
}): {
    presentation: StandalonePresentation;
    bounds: Bounds;
    body: Bounds;
    primitives: Primitive[];
    diagnostics: Diagnostic[];
    unavailable: string[];
} | undefined;
type Point = readonly [number, number];
/** Terminals are the visible lead endpoints of the bundled 24-unit SVGs.
 * This is attachment geometry, not an electrical/circuit verification model. */
export declare function symbolTerminals(entry: ProjectedRecord): readonly {
    point: Point;
    direction: Point;
    side: string;
}[];
export declare function symbolTerminal(entry: ProjectedRecord, other: ProjectedRecord, side?: string, fraction?: number): Point | undefined;
export declare function electricalWireWithoutLabel(edge: ProjectedRecord, from: ProjectedRecord, to: ProjectedRecord): boolean;
export {};
