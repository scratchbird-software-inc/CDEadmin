import type { Viewer } from '@ddn/types/browser';
import type { Bounds } from '@ddn/types';
import type { ViewerHandle } from '../../viewer/src/native.js';
import { type ProjectedRecord } from '../../presentation/src/native.js';
export declare function mindmapSelection(handle: ViewerHandle, selected?: ProjectedRecord | undefined): {
    selected: ProjectedRecord;
    topics: ProjectedRecord[];
    internal: {
        entry: ProjectedRecord;
        from: import("@ddn/presentation").LocatedRecord;
        to: import("@ddn/presentation").LocatedRecord;
    }[];
    incoming: {
        entry: ProjectedRecord;
        from: import("@ddn/presentation").LocatedRecord;
        to: import("@ddn/presentation").LocatedRecord;
    } | undefined;
    left: boolean;
    right: boolean;
} | undefined;
/** Screen-sized editing controls live outside the capture scene. */
export declare function mountMindmapActions(viewer: Viewer, handle: ViewerHandle, bounds: (entry: ProjectedRecord) => Bounds, actions: {
    add(entry: ProjectedRecord, side: 'left' | 'right'): Promise<unknown>;
    remove(entry: ProjectedRecord): void;
    name(entry: ProjectedRecord): void;
    notes(entry: ProjectedRecord): void;
}): () => void;
