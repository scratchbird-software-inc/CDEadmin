import type { Bounds, Matrix, SceneItem, ModelSnapshot, Ref, Json, Diagnostic, Coverage } from '@ddn/types';
import { type DataRecord, type LocatedRecord } from './model.js';
import { type StandalonePresentation, type AssetSize } from './symbol-presentation.js';
export { availableProjectionProfiles } from './adapters.js';
export interface Resolved {
    readonly values: Record<string, Json>;
    readonly properties: readonly {
        path: string;
        value: Json;
        origin: string;
    }[];
    readonly diagnostics: readonly Diagnostic[];
}
export type Resolve = (target: Ref, context?: {
    view?: Ref;
    appearance?: Ref;
}) => Resolved;
export interface ProjectedRecord {
    readonly item: SceneItem;
    readonly definition: LocatedRecord;
    readonly view: LocatedRecord;
    readonly appearance?: LocatedRecord;
    readonly placement?: LocatedRecord;
    readonly effective: DataRecord;
    readonly propertyOrigins?: Readonly<Record<string, string>>;
    /** False for a context endpoint brought into a mind map by an external link. */
    readonly mindmapTopic?: boolean;
    readonly standalone?: StandalonePresentation;
    readonly wireWithoutLabel?: boolean;
    /** Profile restriction and stable per-view key, assigned before filtering. */
    readonly relationLabelAllowed?: boolean;
    readonly relationNumber?: string;
    /** Logical pre-surface world coordinates to rendered world coordinates. */
    readonly surfaceTransform?: Matrix;
}
export interface Projection {
    readonly items: readonly SceneItem[];
    readonly entries: readonly ProjectedRecord[];
    readonly views: readonly LocatedRecord[];
    readonly bounds: Bounds;
    readonly coverage: Coverage;
    readonly diagnostics: readonly Diagnostic[];
}
export interface ProjectionOptions {
    readonly resolve: Resolve;
    readonly measure?: (text: string, size: number, font: string) => number;
    readonly preview?: Readonly<Record<string, Json>>;
    readonly supports?: (profile: string) => boolean;
    readonly geography?: ReadonlyMap<string, unknown>;
    readonly assetSizes?: ReadonlyMap<string, AssetSize>;
    readonly onlyView?: Ref;
    readonly profiles?: readonly string[];
    readonly inclusionPath?: readonly string[];
    readonly panelDepth?: number;
    readonly deferOpacity?: boolean;
}
export declare function unionBounds(items: readonly Bounds[]): Bounds;
export declare function projectSnapshot(snapshot: ModelSnapshot, options: ProjectionOptions): Projection;
