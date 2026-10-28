/**
 * An application menu bar (WAI-ARIA menubar pattern). Items are described as
 * data and rendered when a menu opens, so enabled and checked states are always
 * current. Unavailable items stay visible and focusable, explaining why they
 * are unavailable, so the layout is the same in every edition and mode.
 */
export type MenuItem = {
    readonly kind?: 'command';
    readonly label: string;
    readonly shortcut?: string;
    readonly run?: () => void | Promise<void>;
    readonly enabled?: () => boolean;
    readonly checked?: () => boolean | undefined;
    readonly radio?: boolean;
    readonly hint?: string;
    readonly badge?: string;
} | {
    readonly kind: 'separator';
} | {
    readonly kind: 'heading';
    readonly label: string;
} | {
    readonly kind: 'submenu';
    readonly label: string;
    readonly items: () => readonly MenuItem[];
    readonly enabled?: () => boolean;
    readonly hint?: string;
};
export interface MenuSpec {
    readonly label: string;
    readonly items: () => readonly MenuItem[];
}
export interface MenuBar {
    readonly element: HTMLElement;
    close(): void;
    refresh(): void;
    isOpen(): boolean;
}
/** A one-level popup menu anchored to a control (for example the status-bar zoom level). */
export declare function openPopupMenu(anchor: HTMLElement, items: readonly MenuItem[], label: string, onError: (error: unknown) => void): void;
export declare function createMenuBar(document: Document, specs: readonly MenuSpec[], options: {
    readonly label: string;
    readonly onError: (error: unknown) => void;
}): MenuBar;
