/** Interface preferences only: these tokens never enter a DDN document. */
export declare const UI_THEME_NAMES: readonly ["light", "dark", "midnight", "warm"];
export type UIThemeName = typeof UI_THEME_NAMES[number];
declare const colourTokens: readonly ["bg", "surface", "input", "text", "muted", "border", "accent", "accent-text", "danger", "shadow"];
declare const metrics: {
    readonly 'font-size': readonly [13, 11, 16];
    readonly 'control-height': readonly [32, 28, 40];
    readonly radius: readonly [12, 0, 16];
    readonly 'dialog-width': readonly [480, 280, 560];
};
type TokenName = typeof colourTokens[number] | keyof typeof metrics;
export type UIThemeToken = `--ddn-ui-${TokenName}`;
export type UITokenOverrides = Partial<Record<UIThemeToken, string | number>>;
export declare const UI_THEME_TOKEN_NAMES: readonly UIThemeToken[];
/** Install once per document without overriding any inherited theme. */
export declare function installUITheme(host: HTMLElement): void;
/** Reject unknown/unbounded values atomically; switching theme clears old overrides. */
export declare function setUITheme(host: HTMLElement, name: UIThemeName, overrides?: UITokenOverrides): void;
export {};
