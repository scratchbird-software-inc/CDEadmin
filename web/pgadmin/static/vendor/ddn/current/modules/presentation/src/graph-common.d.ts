import type { Bounds, Diagnostic, ModelSnapshot, Primitive } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type LocatedRecord, type DataRecord } from './model.js';
import { type Point } from './graph-glyphs.js';
export interface GraphProjectionResult {
    readonly entries: readonly ProjectedRecord[];
    readonly diagnostics: readonly Diagnostic[];
    readonly unavailable: readonly string[];
}
export interface GraphProjectionOptions {
    readonly bounds?: Bounds;
    readonly viewProperties?: DataRecord;
    readonly ancestors?: readonly string[];
    readonly projectInline?: (snapshot: ModelSnapshot, targetView: LocatedRecord, bounds: Bounds, ancestors: readonly string[]) => GraphProjectionResult;
}
export declare const center: (b: Bounds) => Point;
export declare const identity: readonly [1, 0, 0, 1, 0, 0];
/** Unconnected palette drops wait outside the method layout until linked. */
export declare function provisionalNodes(entries: readonly ProjectedRecord[], all: readonly LocatedRecord[]): ProjectedRecord[];
export declare const finiteBounds: (a: Point, b: Point, padding?: number) => Bounds;
export declare const changed: (entry: ProjectedRecord, bounds: Bounds, primitives: readonly Primitive[], description?: string) => ProjectedRecord;
export declare function mark(owner: ProjectedRecord, target: LocatedRecord, suffix: string, bounds: Bounds, primitives: readonly Primitive[], description: string): ProjectedRecord;
export declare function memberRecords(entry: ProjectedRecord, all: readonly LocatedRecord[]): LocatedRecord[];
export declare function endEntry(edge: ProjectedRecord, at: number, nodes: readonly ProjectedRecord[], all: readonly LocatedRecord[]): ProjectedRecord | undefined;
export declare function endpoint(edge: ProjectedRecord, at: number, entry: ProjectedRecord, other: ProjectedRecord, all: readonly LocatedRecord[], shaped?: boolean): Point;
/** Styling reaches every generated graph label once, before any inline composition. */
export declare function resolvedText(entries: readonly ProjectedRecord[], profile: string): ProjectedRecord[];
/** Role defaults are subordinate to authored properties, including CSS. */
export declare function styled(entry: ProjectedRecord, key: string, fallback: unknown): unknown;
export declare function guardText(value: unknown): string;
export declare function edgeLabel(entry: ProjectedRecord, all?: readonly LocatedRecord[]): string;
export declare function orthogonalRoute(a: Point, b: Point, obstacles: readonly Bounds[]): Point[];
export declare function graphLabelBounds(value: string, x: number, y: number, size: number, anchor?: string): Bounds;
export declare function placeGraphLabel(value: string, points: readonly Point[], obstacles: readonly Bounds[], reserved: Bounds[], size: number, avoidRoute?: boolean): {
    bounds: Bounds;
    point: Point;
    leader?: Primitive;
};
export declare function roundedRoute(points: readonly Point[], radius: number): string;
export declare function cubicPoints(a: Point, c1: Point, c2: Point, b: Point): Point[];
export declare function roundedPoints(points: readonly Point[], radius: number): Point[];
export declare function routeIntersects(points: readonly Point[], bounds: Bounds): boolean;
/** Disconnect crossing tracks without changing semantic junctions/endpoints.
 * Arc-length intervals let a gap span sampled curve segments, including a
 * crossing exactly on a sample vertex. The source curve stays smooth elsewhere. */
export declare function crossingRoute(points: readonly Point[], prior: readonly (readonly Point[])[], mode: string): string;
export declare function cleanRoute(points: readonly Point[]): Point[];
export declare function decorateEdge(edge: ProjectedRecord, nodes: readonly ProjectedRecord[], all: readonly LocatedRecord[], profile: string, frame: Bounds, labelObstacles: readonly Bounds[], reservedLabels: Bounds[], priorRoutes: Point[][], crossings: string, viewProperties?: DataRecord, attachments?: {
    readonly source?: Point;
    readonly target?: Point;
    readonly horizontal?: boolean;
    readonly sourceDirection?: Point;
    readonly targetDirection?: Point;
}): ProjectedRecord;
export declare function boundaryPoint(bounds: Bounds, toward: Point): Point;
export declare function layoutNative(nodes: readonly ProjectedRecord[], edges: readonly ProjectedRecord[], all: readonly LocatedRecord[], view: LocatedRecord, frame: Bounds, effective?: DataRecord): ProjectedRecord[];
export declare function graphAdornments(entries: readonly ProjectedRecord[], view: LocatedRecord, all: readonly LocatedRecord[], profile: string): ProjectedRecord[];
export declare function inlineInteractions(snapshot: ModelSnapshot, view: LocatedRecord, input: readonly ProjectedRecord[], all: readonly LocatedRecord[], options: GraphProjectionOptions, diagnostics: Diagnostic[], unavailable: string[], fallback?: (snapshot: ModelSnapshot, view: LocatedRecord, entries: readonly ProjectedRecord[], options: GraphProjectionOptions) => GraphProjectionResult, supportsFallback?: (profile: string) => boolean): ProjectedRecord[];
