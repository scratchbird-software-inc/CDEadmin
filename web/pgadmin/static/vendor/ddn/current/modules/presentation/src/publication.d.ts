import type { Bounds, Diagnostic, SceneItem } from '@ddn/types';
import { type LocatedRecord, type DataRecord } from './model.js';
export declare function publicationPageSize(page: DataRecord, content: Pick<Bounds, 'width' | 'height'>): readonly [number, number];
/** Page composition is independent of DOM, capture format and diagram method. */
export declare function publicationScene(items: readonly SceneItem[], content: Bounds, publication: LocatedRecord, title: string, date: string): {
    items: SceneItem[];
    bounds: Bounds;
    diagnostics: Diagnostic[];
};
