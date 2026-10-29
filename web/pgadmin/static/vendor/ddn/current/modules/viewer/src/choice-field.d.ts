export interface ChoiceOption {
    readonly value: string;
    readonly label?: string;
    readonly description?: string;
    readonly preview?: (document: Document) => Node;
}
export interface ChoiceFieldOptions {
    readonly kind?: string;
    readonly compact?: boolean;
}
/** Small examples use the same texture generator and font aliases as the viewer. */
export declare function choicePreview(document: Document, value: string, kind: string): Node;
export declare function syncChoiceField(select: HTMLSelectElement): void;
/** Buttons are the visible control. The hidden select keeps value/event integration simple. */
export declare function choiceField(container: HTMLElement, label: string, choices: readonly (string | ChoiceOption)[], value: string, options?: ChoiceFieldOptions): HTMLSelectElement;
