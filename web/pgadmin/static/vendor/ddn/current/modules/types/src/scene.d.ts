import type { Ref, RevisionVector, VersionSet, Json, Coverage, Diagnostic } from './core.js';
export interface Bounds { readonly x: number; readonly y: number; readonly width: number; readonly height: number }
export type Matrix = readonly [number, number, number, number, number, number];
export interface Viewport { readonly bounds: Bounds; readonly zoom: number; readonly activeView?: Ref }
export interface TextRun { readonly text: string; readonly x: number; readonly y: number; readonly fontKey: string; readonly style: Readonly<Record<string, Json>> }
export type Primitive =
  | { readonly kind: 'path'; readonly d: string; readonly paint: Readonly<Record<string, Json>> }
  | { readonly kind: 'rect' | 'ellipse'; readonly bounds: Bounds; readonly paint: Readonly<Record<string, Json>> }
  | { readonly kind: 'text'; readonly runs: readonly TextRun[] }
  | { readonly kind: 'image'; readonly assetId: string; readonly bounds: Bounds };
export interface SceneItem {
  readonly occurrence: string; readonly target: Ref; readonly view: Ref;
  readonly layer: string; readonly bounds: Bounds; readonly transform: Matrix;
  readonly clip?: Bounds; readonly primitives: readonly Primitive[];
  readonly hitTargets: readonly { readonly id: string; readonly target: Ref; readonly bounds: Bounds }[];
  readonly accessible: { readonly role: string; readonly label: string; readonly description?: string };
  readonly status?: string; readonly evidence: 'current' | 'stale' | 'partial' | 'invalid';
}
export interface ScenePatch {
  readonly baseGeneration: string; readonly generation: string; readonly revision: RevisionVector;
  readonly dependencyFingerprint: string; readonly versions: VersionSet;
  readonly fontGeneration: string; readonly styleGeneration: string;
  readonly upsert: readonly SceneItem[]; readonly remove: readonly string[]; readonly coverage: Coverage;
}
/** A record of a normalized model, located in its source file. */
export interface LocatedRecord { readonly file: string; readonly record: Readonly<Record<string, unknown>>; readonly owner: string; readonly ref: Ref }
export interface StandalonePresentation { readonly mode: 'image' | 'text'; readonly electricalIcon?: string }
/** One projected scene item with the records it was projected from. */
export interface ProjectedRecord {
  readonly item: SceneItem;
  readonly definition: LocatedRecord; readonly view: LocatedRecord;
  readonly appearance?: LocatedRecord; readonly placement?: LocatedRecord;
  /** The effective record after appearance, placement and defaults. */
  readonly effective: Readonly<Record<string, unknown>>;
  readonly propertyOrigins?: Readonly<Record<string, string>>;
  /** False for a context endpoint brought into a mind map by an external link. */
  readonly mindmapTopic?: boolean;
  readonly standalone?: StandalonePresentation;
  readonly wireWithoutLabel?: boolean;
  /** Profile restriction and stable per-view key, assigned before filtering. */
  readonly relationLabelAllowed?: boolean; readonly relationNumber?: string;
  /** Logical pre-surface world coordinates to rendered world coordinates. */
  readonly surfaceTransform?: Matrix;
}
/** A projected view: its scene items, their records, the views shown, bounds and coverage. */
export interface Projection {
  readonly items: readonly SceneItem[]; readonly entries: readonly ProjectedRecord[];
  readonly views: readonly LocatedRecord[]; readonly bounds: Bounds;
  readonly coverage: Coverage; readonly diagnostics: readonly Diagnostic[];
}
