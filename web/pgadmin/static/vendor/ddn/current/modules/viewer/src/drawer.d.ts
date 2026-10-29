import { type Detached } from './popout.js';
export type DrawerMode = 'docked' | 'floating' | 'popout' | 'hidden';
export interface Drawer {
    readonly element: HTMLElement;
    readonly mode: DrawerMode;
    readonly detached: Detached | undefined;
    setMode(mode: DrawerMode): void;
    setHeader(header: HTMLElement): void;
    destroy(): void;
}
export interface DrawerOptions {
    readonly id: string;
    readonly title: string;
    readonly container: HTMLElement;
    readonly header: HTMLElement;
    readonly side?: 'left' | 'right';
    readonly hostClass?: string;
    readonly width?: number;
    readonly onMode?: (mode: DrawerMode) => void;
    readonly onHide?: () => void;
    readonly onBlocked?: () => void;
    readonly onKeydown?: (event: KeyboardEvent) => void;
    readonly closeLabel?: string;
}
export declare function drawerFor(container: HTMLElement | null | undefined, id: string): Drawer | undefined;
/** One owner for embedded drawers and host menus; detach keeps the same DOM and runtime. */
export declare function createDrawer(element: HTMLElement, options: DrawerOptions): Drawer;
