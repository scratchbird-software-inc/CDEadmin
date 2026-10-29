/** Table geometry follows the source codex: percentages share, minima never disappear. */
export interface TableColumn {
    readonly id: string;
    readonly label?: string;
    readonly percentage?: number;
    readonly min_chars?: number;
    readonly max_chars?: number;
    readonly max_lines?: number;
    readonly alignment?: string;
    readonly format?: string;
    readonly visibility?: string;
}
export interface CellLayout {
    readonly value: string;
    readonly lines: readonly string[];
    readonly truncated: boolean;
}
export interface TableLayout {
    readonly fits: boolean;
    readonly widths: readonly number[];
    readonly percentages: readonly number[];
    readonly rows: readonly {
        readonly cells: readonly CellLayout[];
        readonly height: number;
    }[];
    readonly height: number;
}
export declare function columnPercentages(columns: readonly TableColumn[]): number[];
export declare function wrapCell(value: unknown, width: number, measure: (text: string) => number, maxLines?: number): CellLayout;
export declare function layoutTable(columns: readonly TableColumn[], rows: readonly (readonly unknown[])[], width: number, measure: (text: string) => number, options?: {
    minChars?: number;
    maxLines?: number;
    lineHeight?: number;
    header?: boolean;
}): TableLayout;
