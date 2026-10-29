import type { Bounds } from '@ddn/types';
export interface LayoutNode {
    readonly id: string;
    readonly bounds: Bounds;
    readonly pinned?: boolean;
    readonly group?: string;
}
export interface LayoutLink {
    readonly from: string;
    readonly to: string;
    readonly side?: 'left' | 'right';
}
export interface LayoutSettings {
    readonly algorithm?: string;
    readonly gap?: number;
    readonly row_gap?: number;
    readonly columns?: number;
    readonly direction?: string;
    readonly root?: string;
    readonly width?: number;
    readonly height?: number;
    readonly mindmapProfile?: boolean;
}
/** Deterministic client-side layouts. Every loop is bounded by model size or an
 * explicit relaxation count; authored pins always win over automatic placement. */
export declare function graphLayout(nodes: readonly LayoutNode[], links: readonly LayoutLink[], settings?: LayoutSettings): ReadonlyMap<string, Bounds>;
