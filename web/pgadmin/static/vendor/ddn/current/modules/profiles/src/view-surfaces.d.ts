/** Versioned view-surface recipes for the unreleased ddn-next-1 defaults. */
export interface ViewSurfacePreset {
    readonly id: string;
    readonly label: string;
    readonly description: string;
    readonly width: number | null;
    readonly height: number | null;
    /** Pixel scale relative to the 1080-line logical dashboard surface. */
    readonly scale: number;
}
export declare const VIEW_SURFACE_PRESETS: readonly ViewSurfacePreset[];
export declare function getViewSurfacePreset(id: unknown): ViewSurfacePreset | undefined;
