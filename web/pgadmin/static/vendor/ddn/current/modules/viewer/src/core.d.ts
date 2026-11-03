import type { Runtime, Ref, Diagnostic } from '@ddn/types';
import type { Viewer, ViewerOptions, Viewport, Bounds } from '@ddn/types/browser';
import type { Primitive } from '@ddn/types/scene';
import { type Projection, type ProjectedRecord } from '../../presentation/src/native.js';
export { setUITheme, installUITheme, UI_THEME_NAMES, UI_THEME_TOKEN_NAMES } from './ui-theme.js';
export { installFontResources, listFonts, loadFontFile, getFontResources } from './fonts.js';
export interface ViewerHandle {
    readonly runtime: Runtime;
    readonly element: HTMLElement;
    readonly surface: SVGSVGElement;
    readonly container: HTMLElement;
    readonly overlays: HTMLElement;
    readonly stage: HTMLElement;
    readonly ownerDocument: Document;
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
    /** Verify on each refresh. The designer enables it while attached: the
     *  verifier checks user edits, and a viewer alone renders DDN that is
     *  already verified (owner direction 2026-11-03). */
    setVerification(enabled: boolean): void;
    whenRendered(): Promise<void>;
    diagnostics(): readonly Diagnostic[];
    toWorld(x: number, y: number): {
        x: number;
        y: number;
    };
    announce(message: string): void;
}
export declare function getViewerHandle(viewer: Viewer): ViewerHandle;
/** Small UI previews use the same SVG realization as the canvas, without assets
 * or a second viewer/runtime. Input consists of trusted local glyph primitives. */
export declare function renderPreviewPrimitives(document: Document, primitives: readonly Primitive[], bounds: Bounds): SVGGElement;
export declare function createViewer(element: HTMLElement, options: ViewerOptions): Viewer;
