export interface StandardDialogOptions {
    readonly title: string;
    readonly onApply?: () => void | Promise<void>;
    readonly onClose?: () => void;
    /** Drain pending live edits before user dismissal. Programmatic teardown bypasses it. */
    readonly beforeClose?: () => void | Promise<void>;
    readonly applyLabel?: string;
    readonly cancelLabel?: string;
    /** Keep user dismissal disabled until an asynchronous Apply finishes. */
    readonly lockWhileApplying?: boolean;
    /** Modeless forms leave the diagram available. Modal is the default. */
    readonly modal?: boolean;
    /** Drag the title or focus it and use the arrow keys. Enabled by default. */
    readonly movable?: boolean;
}
export interface StandardDialog {
    readonly element: HTMLElement;
    readonly body: HTMLElement;
    readonly footer: HTMLElement;
    readonly applyButton?: HTMLButtonElement;
    close(): void;
    showError(message: unknown): void;
}
/** A movable, viewport-bounded form. Populate body synchronously after creation. */
export declare function createStandardDialog(host: HTMLElement, options: StandardDialogOptions): StandardDialog;
export interface NumberFieldOptions {
    readonly min: number;
    readonly max: number;
    readonly step?: number | 'any';
}
/** Refresh a programmatic value without emitting an edit. */
export declare function syncNumberField(input: HTMLInputElement): void;
/** A bounded slider with an exact numeric entry. Both represent one source value. */
export declare function numberField(container: HTMLElement, label: string, value: number | string, options: NumberFieldOptions): HTMLInputElement;
/** Refresh after a programmatic default change without marking the field edited. */
export declare function syncColourField(input: HTMLInputElement): void;
export interface ColourFieldOptions {
    readonly dialogHost?: HTMLElement;
}
/** Text stays the source value; the native swatch preserves an existing alpha. */
export declare function colourField(container: HTMLElement, label: string, value: string, options?: ColourFieldOptions): HTMLInputElement;
