/** Separate type and name columns share geometry in sizing and painting. */
export declare function cardTextLayout(type: string, title: string, width: number, measure: (text: string, size: number) => number, typeSize: number, titleSize: number, padding?: number): {
    typeWidth: number;
    typeLines: readonly string[];
    titleOffset: number;
    titleWidth: number;
    titleLines: readonly string[];
};
