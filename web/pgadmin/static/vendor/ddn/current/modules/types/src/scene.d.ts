import type { Ref, RevisionVector, VersionSet, Json, Coverage } from './core.js';
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
