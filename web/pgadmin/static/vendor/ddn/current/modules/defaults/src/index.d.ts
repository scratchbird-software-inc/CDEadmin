import type { Diagnostic, Json, ModelSnapshot, Ref } from '../../types/src/core.js';
export interface DefaultSelector {
    owner?: string;
    category?: string;
    file?: string;
    method?: string;
    profile?: string;
    catalogue?: string;
    /** Typed selectors use an ancestor lineage; CSS scalar hooks match one ancestor. */
    subtype?: string | readonly string[];
    role?: string;
    classes?: readonly string[];
    id?: string;
}
export interface DefaultRule {
    selector: DefaultSelector;
    declarations: Readonly<Record<string, Json>>;
}
export interface StyleRule extends DefaultRule {
    important?: readonly string[];
    specificity?: number;
    /** Parser metadata: CSS ID, class/attribute, and type counts, compared lexicographically. */
    specificityTuple?: readonly [number, number, number];
}
export interface ResolutionContext {
    theme?: string;
    /** Standard fallback inherited from a fixed dashboard view, before CSS/file settings. */
    surfacePreset?: string;
    surfaceTypography?: {
        font: string;
        fontSize: number;
    };
    file?: string;
    method?: string;
    profile?: string;
    subtype?: string | readonly string[];
    catalogue?: string;
    role?: string;
    category?: string;
    definition?: Record<string, Json>;
    appearance?: Record<string, Json>;
    fileDefaults?: readonly DefaultRule[];
    workareaDefaults?: readonly DefaultRule[];
    viewDefaults?: readonly DefaultRule[];
    styles?: readonly StyleRule[];
}
export interface Resolution {
    values: Record<string, Json>;
    properties: {
        path: string;
        value: Json;
        origin: string;
    }[];
    diagnostics: Diagnostic[];
}
/** Checks a single supplied setting using the exact generated owner/role schema. */
export declare function validateProperty(owner: string, path: string, value: Json, context?: Pick<ResolutionContext, 'role' | 'profile' | 'category'>): Diagnostic[];
/** Resolves omission without mutating source or manufacturing missing semantic facts. */
export declare function resolve(record: Record<string, Json>, owner: string, context?: ResolutionContext): Resolution;
export declare function resolveProperties(snapshot: ModelSnapshot, target: Ref, context?: {
    view?: Ref;
    appearance?: Ref;
    styles?: readonly StyleRule[];
}): Resolution;
export declare const previewPaths: readonly string[];
export declare function validatePreview(value: Readonly<Record<string, Json>>): Diagnostic[];
export declare function createDefaultsResolver(options: {
    defaultsVersion: string;
    styles?: readonly StyleRule[];
}): {
    resolve: (record: Record<string, Json>, owner: string, context?: ResolutionContext) => Resolution;
};
/** Author percentages are retained; this returns the logical rendered allocations. */
export declare function allocateColumnPercentages(percentages: readonly (number | null | undefined)[]): number[];
/** Parse the registered virtual CSS hooks without DOM access or network loading. */
export declare function parseStylesheet(text: string): {
    rules: StyleRule[];
    diagnostics: Diagnostic[];
};
