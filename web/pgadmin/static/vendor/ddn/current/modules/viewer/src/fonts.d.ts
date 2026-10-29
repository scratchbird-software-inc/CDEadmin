/** Optional, entirely local browser font resources. No network font loader is used. */
export type FontCategory = 'sans' | 'serif' | 'monospace' | 'handwriting' | 'custom';
export type FontStyle = 'normal' | 'italic' | 'oblique';
export interface FontResource {
    readonly family: string;
    readonly dataURL: string;
    readonly weight?: string;
    readonly style?: FontStyle;
    readonly category?: FontCategory;
    readonly source?: 'standard' | 'custom';
    /** Copyright and license notice retained in exported font CSS when supplied. */
    readonly license?: string;
}
export interface FontOption {
    readonly key: string;
    readonly family: string;
    readonly label: string;
    readonly category: FontCategory;
    readonly source: 'system' | 'standard' | 'custom';
    readonly available: boolean;
    readonly weights: readonly string[];
    readonly styles: readonly FontStyle[];
}
export interface LocalFontOptions {
    readonly family?: string;
    readonly weight?: string;
    readonly style?: FontStyle;
}
/** Existing generic aliases keep their system defaults, whether or not the pack is installed. */
export declare function fontFamily(key: string): string;
/** Standard entries report availability after installation; generic choices always remain usable. */
export declare function listFonts(document: Document): readonly FontOption[];
/** Install an explicit local resource pack (or the page's DDN_FONT_RESOURCES) without fetching. */
export declare function installFontResources(document: Document, resources?: readonly FontResource[]): Promise<readonly FontOption[]>;
/** Register a user-selected local binary; no file upload, storage or source-document mutation occurs. */
export declare function loadFontFile(document: Document, file: File, options?: LocalFontOptions): Promise<FontOption>;
/** Copy loaded local resources for host-managed persistence, optionally limited to used font keys. */
export declare function getFontResources(document: Document, usedFontKeys?: Iterable<string>): readonly FontResource[];
/** Embed only selected, successfully loaded local resources in a standalone SVG style element. */
export declare function fontCSS(document: Document, usedFontKeys: Iterable<string>): string;
