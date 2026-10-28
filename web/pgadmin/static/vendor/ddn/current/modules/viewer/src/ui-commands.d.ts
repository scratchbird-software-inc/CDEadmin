/**
 * Host-neutral UI command channel. The viewer and designer register the actions
 * their controls perform; a host shell builds menus, shortcuts and command
 * search from the same entries. One declaration per command keeps every
 * surface (toolbar, menu, context menu, search) in agreement.
 *
 * This is a browser-module convenience, not part of the utility ABI: hosts that
 * do not use it lose nothing, and the registered actions only call the same
 * functions as the visible controls.
 */
export interface UICommand {
    readonly id: string;
    readonly label: string;
    /** A short reason shown when the command is unavailable. */
    readonly hint?: string;
    run(argument?: unknown): void | Promise<void>;
    enabled?(): boolean;
    /** Checked state for toggles and radio choices; undefined for plain actions. */
    checked?(): boolean | undefined;
    /** A live display value, such as the zoom percentage. */
    value?(): string;
}
export declare const UI_COMMANDS_CHANGED = "ddn:commands-changed";
/** Registers commands on a host element; returns a function that removes them. */
export declare function registerUICommands(host: Element, commands: readonly UICommand[]): () => void;
/** Finds a command registered on the host or on any registered descendant. */
export declare function findUICommand(root: Element, id: string): UICommand | undefined;
export declare function listUICommands(root: Element): UICommand[];
/** Tells hosts that enabled/checked/value states may have changed. */
export declare function notifyUICommands(host: Element): void;
export declare function commandEnabled(command: UICommand | undefined): boolean;
