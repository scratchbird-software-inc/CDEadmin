/**
 * Moves an existing panel into its own browser window (for a second monitor)
 * or into an in-page floating frame. The panel keeps its DOM, listeners and
 * state: it still runs on the opener's single runtime, so nothing is
 * re-created and no messaging layer is needed. Closing the window returns the
 * panel to where it came from.
 */
export interface DetachOptions {
    /** Window and frame title. */
    readonly title: string;
    /** Stable key used to remember size and position in this browser. */
    readonly name: string;
    /** Class names for the wrapper, so ancestor-scoped panel styles still apply. */
    readonly hostClass?: string;
    readonly width?: number;
    readonly height?: number;
    /** Keys pressed inside the detached panel, so host shortcuts keep working. */
    readonly onKeydown?: (event: KeyboardEvent) => void;
    /** The panel came back (its window was closed) or left (it was removed). */
    readonly onReturn?: () => void;
}
export interface Detached {
    readonly kind: 'window' | 'floating';
    readonly element: HTMLElement;
    readonly window?: Window;
    /** Puts the panel back where it was and closes the window or frame. */
    dock(): void;
    focus(): void;
}
/** Detached panels of a document (for a Window menu). */
export declare function detachedPanels(document: Document): readonly Detached[];
/** Re-applies theme tokens after an interface theme change. */
export declare function syncDetachedThemes(document: Document): void;
/**
 * Opens a same-origin window and moves the element into it. Returns undefined
 * when the browser blocks the window (popup blockers, sandboxed frames); the
 * caller then falls back to a floating frame.
 */
export declare function popOut(element: HTMLElement, options: DetachOptions): Detached | undefined;
/** An in-page floating frame with a keyboard Move control, clamped to the viewport. */
export declare function floatPanel(element: HTMLElement, options: DetachOptions & {
    readonly actions?: readonly {
        label: string;
        title: string;
        run(): void;
    }[];
}): Detached;
