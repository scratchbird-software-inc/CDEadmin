/** Bounded text formatting. Raw HTML and executable destinations are never interpreted. */
export interface InlineRun {
    readonly text: string;
    readonly bold?: boolean;
    readonly italic?: boolean;
    readonly underline?: boolean;
    readonly code?: boolean;
    readonly href?: string;
}
export interface TextBlock {
    readonly runs: readonly InlineRun[];
    readonly heading: number;
    readonly list: boolean;
    readonly quote: boolean;
    readonly code: boolean;
}
export declare function safeURL(value: string): string | undefined;
export declare function inlineMarkdown(text: string, depth?: number): InlineRun[];
export declare function markdownBlocks(text: string, formatted?: boolean): TextBlock[];
