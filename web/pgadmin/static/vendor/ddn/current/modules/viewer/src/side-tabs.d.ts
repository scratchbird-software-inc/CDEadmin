export interface SideTab {
    readonly id: string;
    readonly label: string;
    readonly count?: number;
    readonly icon?: string;
}
/** Accessible vertical navigation shared by palettes, inspector sections and navigator filters. */
export declare function sideTabs(container: HTMLElement, label: string, tabs: readonly SideTab[], selected: string, onSelect: (id: string) => void): {
    element: HTMLDivElement;
    select: (id: string) => void;
    connect(panel: HTMLElement): void;
    label(panel: HTMLElement): void;
};
