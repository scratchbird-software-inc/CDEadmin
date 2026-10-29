import type { Ref } from '../../types/src/core.js';
import type { Bounds, Viewport } from '../../types/src/browser.js';
/** A standalone document has no camera space outside its sole view. */
export declare function constrainStandaloneViewport(viewport: Viewport, extent: Bounds, view?: Ref): Viewport;
/** Preserve fit-to-view while its content grows or shrinks; retain a deliberately zoomed camera. */
export declare function sameBounds(a: Bounds, b: Bounds): boolean;
