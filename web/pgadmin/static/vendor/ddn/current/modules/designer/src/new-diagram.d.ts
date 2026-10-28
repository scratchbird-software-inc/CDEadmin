import type { Viewer } from '../../types/src/browser.js';
/** Document hosts own replacement and persistence; this wizard only chooses new source. */
export declare function newDiagramDialog(viewer: Viewer, create: (source: string) => Promise<void>): void;
