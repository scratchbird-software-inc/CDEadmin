/** Built-in textures contain only locally generated vector geometry. The same
 * tile is used by SVG shapes, captures and the CSS workarea background. */
export type TextureKind = 'paper' | 'linen' | 'grid' | 'dots';
export interface TextureSettings {
    readonly kind: TextureKind;
    readonly color: string;
    readonly opacity: number;
    readonly scale: number;
    readonly seed: number;
}
/** Null/absence is off; an empty record selects the versioned paper defaults. */
export declare function normalizeTexture(value: unknown): TextureSettings | undefined;
/** id is a renderer-owned identifier, never an authored resource reference. */
export declare function createTexturePattern(document: Document, id: string, value: unknown, baseFill?: string): SVGPatternElement | undefined;
/** SVG data is assembled solely from the closed, validated geometry above.
 * The returned image is already a CSS url(...) value; size is in logical px. */
export declare function textureBackground(value: unknown, baseFill?: string): {
    image: string;
    size: string;
} | undefined;
