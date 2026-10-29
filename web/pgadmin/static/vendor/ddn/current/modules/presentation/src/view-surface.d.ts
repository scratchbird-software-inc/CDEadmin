import type { Bounds, Matrix, Primitive } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type DataRecord } from './model.js';
export interface FixedViewSurface {
    width: number;
    height: number;
    scale: number;
    padding: number;
    fit: 'contain' | 'none';
}
/** Null dimensions retain the existing content-sized view contract. */
export declare function fixedViewSurface(effective: DataRecord): FixedViewSurface | undefined;
export declare function surfaceBounds(bounds: Bounds, matrix: Matrix): Bounds;
/** Fit logical diagram geometry, preserving its origin and explicit positions when
 * they already fit. Source positions stay logical; surfaceTransform exposes the
 * inverse mapping to editors without changing semantic coordinates. */
export declare function fitSurfaceContent(entries: readonly ProjectedRecord[], annotations: readonly Primitive[], surface: FixedViewSurface, origin: {
    x: number;
    y: number;
}, chrome: DataRecord, measure: (text: string, size: number, font: string) => number): {
    entries: {
        surfaceTransform: Matrix;
        item: {
            bounds: Bounds;
            clip: Bounds;
            transform: Matrix;
            hitTargets: {
                bounds: Bounds;
                id: string;
                target: import("@ddn/types").Ref;
            }[];
            occurrence: string;
            target: import("@ddn/types").Ref;
            view: import("@ddn/types").Ref;
            layer: string;
            primitives: readonly Primitive[];
            accessible: {
                readonly role: string;
                readonly label: string;
                readonly description?: string;
            };
            status?: string;
            evidence: "current" | "stale" | "partial" | "invalid";
        };
        definition: import("./model.js").LocatedRecord;
        view: import("./model.js").LocatedRecord;
        appearance?: import("./model.js").LocatedRecord;
        placement?: import("./model.js").LocatedRecord;
        effective: DataRecord;
        propertyOrigins?: Readonly<Record<string, string>>;
        mindmapTopic?: boolean;
        standalone?: import("./symbol-presentation.js").StandalonePresentation;
        wireWithoutLabel?: boolean;
        relationLabelAllowed?: boolean;
        relationNumber?: string;
    }[];
    annotations: ({
        readonly kind: "path";
        readonly d: string;
        readonly paint: Readonly<Record<string, import("@ddn/types").Json>>;
    } | {
        runs: {
            x: number;
            y: number;
            style: {
                'font-size': number;
            };
            text: string;
            fontKey: string;
        }[];
        kind: "text";
    } | {
        bounds: Bounds;
        kind: "rect" | "ellipse";
        paint: Readonly<Record<string, import("@ddn/types").Json>>;
    } | {
        bounds: Bounds;
        kind: "image";
        assetId: string;
    })[];
    matrix: Matrix;
    drawable: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    clipped: boolean;
    bounds: {
        x: number;
        y: number;
        width: number;
        height: number;
    };
};
