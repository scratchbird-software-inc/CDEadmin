import type { Runtime, RuntimeOptions, SourceSet, ModelSnapshot, OpenResult, TaskOptions, Ref, Scope, RevisionVector, VersionSet, Json, Diagnostic, Coverage, CommandService, AuthorityProvider } from './core.js';
import type { Bounds, SceneItem } from './scene.js';
export type { Bounds, Matrix, Viewport, TextRun, Primitive, SceneItem, ScenePatch } from './scene.js';
import type { Viewport } from './scene.js';
export type ViewerOptions = (
  { readonly runtime: Runtime; readonly runtimeOptions?: never } |
  { readonly runtime?: never; readonly runtimeOptions: RuntimeOptions }
) & {
  readonly controls?: 'standard' | 'host'; readonly assets?: AssetProvider;
  readonly outputs?: readonly OutputAdapter[];
}
export interface AssetProvider { read(id: string, options?: TaskOptions): Promise<{ readonly bytes: Uint8Array; readonly mime: string; readonly hash: string }> }
export type Navigation =
  | { readonly kind: 'fit-workarea' | 'back' | 'forward' | 'restore' }
  | { readonly kind: 'focus' | 'fit-view' | 'expand-view'; readonly target: Ref };
export interface Inspection {
  readonly target: Ref; readonly revision: RevisionVector;
  readonly properties: readonly { readonly path: string; readonly explicit?: Json; readonly effective?: Json; readonly origin: string }[];
  readonly diagnostics: readonly Diagnostic[];
}
export interface CaptureRequest extends TaskOptions {
  readonly scope: Scope; readonly format: string;
  readonly extent: 'content' | 'viewport' | Bounds;
  readonly includePreview: boolean; readonly partial: 'reject' | 'label'; readonly stale: 'reject' | 'label';
  readonly options?: Json;
}
export interface CaptureManifest {
  readonly revision: RevisionVector; readonly versions: VersionSet; readonly coverage: Coverage;
  readonly styleGeneration: string; readonly fontGeneration: string;
  readonly assets: Readonly<Record<string, string>>; readonly previewIncluded: boolean;
  readonly warnings: readonly Diagnostic[];
}
export type CaptureResult =
  | { readonly ok: true; readonly artifacts: readonly { readonly name: string; readonly mime: string; readonly blob: Blob }[]; readonly manifest: CaptureManifest }
  | { readonly ok: false; readonly reason: 'unsupported' | 'incomplete' | 'invalid' | 'stale' | 'cancelled' | 'budget-exceeded'; readonly diagnostics: readonly Diagnostic[] };
export interface OutputAdapter {
  readonly id: string; readonly version: string; readonly formats: readonly string[];
  readonly supportedProfiles: readonly string[]; readonly supportedFeatures: readonly string[];
  readonly requirements: readonly string[]; readonly limitations: readonly string[];
  capture(input: Readonly<{ snapshot: ModelSnapshot; scene: readonly SceneItem[]; manifest: CaptureManifest }>, request: CaptureRequest): Promise<CaptureResult>;
}
export interface ViewerEvent { readonly kind: 'ready' | 'viewport' | 'selection' | 'diagnostics' | 'pending' | 'disposed'; readonly target?: Ref; readonly revision?: RevisionVector; readonly diagnostics?: readonly Diagnostic[] }
export interface Viewer {
  open(input: SourceSet | ModelSnapshot, options?: TaskOptions): Promise<OpenResult>;
  setViewport(viewport: Viewport): void;
  navigate(request: Navigation): Promise<void>;
  inspect(target: Ref): Promise<Inspection>;
  /** Keys restricted to codex viewer paint-preview allowlist. Undefined resets. */
  setPreview(properties?: Readonly<Record<string, Json>>): void;
  capture(request: CaptureRequest): Promise<CaptureResult>;
  subscribe(listener: (event: ViewerEvent) => void): () => void;
  destroy(): void;
}
export interface DesignerOptions {
  readonly controls?: 'standard' | 'host'; readonly authority: AuthorityProvider;
  readonly history?: { readonly maxCommands: number; readonly maxBytes: number };
}
export interface SaveArtifact { readonly name: string; readonly blob: Blob; readonly revision: RevisionVector }
export interface Designer {
  readonly commands: CommandService;
  /** Produces artifacts; does not claim browser/OS persistence succeeded. */
  save(options?: TaskOptions): Promise<readonly SaveArtifact[]>;
  isDirty(): boolean;
  /** Releases editing overlays/controllers, leaving the supplied viewer alive. */
  destroy(): void;
}
export declare function createViewer(element: HTMLElement, options: ViewerOptions): Viewer;
export declare function createDesigner(viewer: Viewer, options: DesignerOptions): Designer;
