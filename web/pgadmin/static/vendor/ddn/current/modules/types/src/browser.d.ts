import type { Runtime, RuntimeOptions, SourceSet, ModelSnapshot, OpenResult, TaskOptions, Ref, Scope, RevisionVector, VersionSet, Json, Diagnostic, Coverage, CommandService, AuthorityProvider, Verifier, VerifyOptions, VerificationReport } from './core.js';
import type { Bounds, SceneItem, Primitive, Projection, ProjectedRecord } from './scene.js';
export type { Bounds, Matrix, Viewport, TextRun, Primitive, SceneItem, ScenePatch, LocatedRecord, StandalonePresentation, ProjectedRecord, Projection } from './scene.js';
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
/** Browser editions also export these headless functions and their types from the core contract. */
export { createRuntime, createVerifier, verifySourcesWithModel, verifyDecodedSources, verifyDecoded, createNativePack, createCompletePack, createCompletePresentationPack, createNativeCommandPack, createNativeRuntimeOptions, createCompleteRuntimeOptions, createCommandService, analyzeProfile, parsePresetPack, serializePresetPack } from './core.js';
export type { VerifiedModel, VerifiedSources, PresetTarget, AppearancePreset, PresetPack } from './core.js';
/** The edition's profile packs with its worker-backed browser executor. */
export declare function createBrowserRuntimeOptions(): RuntimeOptions;
/** Modular editions: the profile packs loaded so far, without a browser executor. */
export declare function createModularRuntimeOptions(): RuntimeOptions;
/** The live viewer's host handle: its runtime, DOM surfaces, projection, selection and rendering state. */
export interface ViewerHandle {
  readonly runtime: Runtime;
  readonly element: HTMLElement; readonly surface: SVGSVGElement; readonly container: HTMLElement;
  readonly overlays: HTMLElement; readonly stage: HTMLElement; readonly ownerDocument: Document;
  scene(): Projection | undefined;
  viewport(): Viewport;
  selected(): Ref | undefined;
  expanded(): Ref | undefined;
  clearSelection(): void;
  selectedEntry(): ProjectedRecord | undefined;
  select(ref: Ref, occurrence?: string): void;
  subscribeOpen(listener: () => void): () => void;
  subscribeSelection(listener: (ref: Ref | undefined) => void): () => void;
  refresh(): Promise<void>;
  /** Verify on each refresh. A designer enables it while attached: the verifier checks user
   *  edits, and a viewer alone renders DDN that is already verified. */
  setVerification(enabled: boolean): void;
  whenRendered(): Promise<void>;
  diagnostics(): readonly Diagnostic[];
  toWorld(x: number, y: number): { x: number; y: number };
  announce(message: string): void;
}
/** The handle of an active viewer; throws once the viewer is destroyed. */
export declare function getViewerHandle(viewer: Viewer): ViewerHandle;
/** Interface preferences only: these tokens never enter a DDN document. */
export declare const UI_THEME_NAMES: readonly ['light', 'dark', 'midnight', 'warm'];
export type UIThemeName = typeof UI_THEME_NAMES[number];
export type UIThemeToken = `--ddn-ui-${'bg' | 'surface' | 'input' | 'text' | 'muted' | 'border' | 'accent' | 'accent-text' | 'danger' | 'shadow' | 'font-size' | 'control-height' | 'radius' | 'dialog-width'}`;
export type UITokenOverrides = Partial<Record<UIThemeToken, string | number>>;
export declare const UI_THEME_TOKEN_NAMES: readonly UIThemeToken[];
export declare function installUITheme(host: HTMLElement): void;
export declare function setUITheme(host: HTMLElement, name: UIThemeName, overrides?: UITokenOverrides): void;
/** Optional, entirely local browser font resources. No network font loader is used. */
export type FontCategory = 'sans' | 'serif' | 'monospace' | 'handwriting' | 'custom';
export type FontStyle = 'normal' | 'italic' | 'oblique';
export interface FontResource {
  readonly family: string; readonly dataURL: string;
  readonly weight?: string; readonly style?: FontStyle; readonly category?: FontCategory;
  readonly source?: 'standard' | 'custom';
  /** Copyright and license notice retained in exported font CSS when supplied. */
  readonly license?: string;
}
export interface FontOption {
  readonly key: string; readonly family: string; readonly label: string; readonly category: FontCategory;
  readonly source: 'system' | 'standard' | 'custom'; readonly available: boolean;
  readonly weights: readonly string[]; readonly styles: readonly FontStyle[];
}
export interface LocalFontOptions { readonly family?: string; readonly weight?: string; readonly style?: FontStyle }
export declare function listFonts(document: Document): readonly FontOption[];
export declare function installFontResources(document: Document, resources?: readonly FontResource[]): Promise<readonly FontOption[]>;
export declare function loadFontFile(document: Document, file: File, options?: LocalFontOptions): Promise<FontOption>;
export declare function getFontResources(document: Document, usedFontKeys?: Iterable<string>): readonly FontResource[];
/** Renders scene primitives into an SVG group sized to `bounds`, for previews. */
export declare function renderPreviewPrimitives(document: Document, primitives: readonly Primitive[], bounds: Bounds): SVGGElement;
export interface StandardDialogOptions {
  readonly title: string;
  readonly onApply?: () => void | Promise<void>;
  readonly onClose?: () => void;
  /** Drain pending live edits before user dismissal. Programmatic teardown bypasses it. */
  readonly beforeClose?: () => void | Promise<void>;
  readonly applyLabel?: string; readonly cancelLabel?: string;
  /** Keep user dismissal disabled until an asynchronous Apply finishes. */
  readonly lockWhileApplying?: boolean;
  /** Modeless forms leave the diagram available. Modal is the default. */
  readonly modal?: boolean;
  /** Drag the title or focus it and use the arrow keys. Enabled by default. */
  readonly movable?: boolean;
}
export interface StandardDialog {
  readonly element: HTMLElement; readonly body: HTMLElement; readonly footer: HTMLElement;
  readonly applyButton?: HTMLButtonElement;
  close(): void;
  showError(message: unknown): void;
}
export declare function createStandardDialog(host: HTMLElement, options: StandardDialogOptions): StandardDialog;
export interface ColourFieldOptions { readonly dialogHost?: HTMLElement }
/** A colour text field with a native swatch and palette; the text stays the source value. */
export declare function colourField(container: HTMLElement, label: string, value: string, options?: ColourFieldOptions): HTMLInputElement;
