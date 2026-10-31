import type { Bounds } from '@ddn/types';
import type { Viewer } from '@ddn/types/browser';
import type { ViewerHandle } from '../../viewer/src/native.js';
import { type ProjectedRecord } from '../../presentation/src/native.js';
export type ResizeDirection = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
/** Screen-sized editing affordances; capture uses the scene, never these DOM controls. */
export declare function mountResizeHandles(viewer: Viewer, handle: ViewerHandle, options: {
    bounds(entry: ProjectedRecord): Bounds;
    allowed(entry: ProjectedRecord): boolean;
    start(entry: ProjectedRecord, event: PointerEvent, direction?: ResizeDirection): void;
    step(entry: ProjectedRecord, dx: number, dy: number): void;
}): () => void;
