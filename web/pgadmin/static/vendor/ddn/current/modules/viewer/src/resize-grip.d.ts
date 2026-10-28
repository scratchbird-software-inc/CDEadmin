export interface ResizeSize {
    readonly width: number;
    readonly height: number;
}
interface ResizeGripOptions {
    readonly label: string;
    readonly size: () => ResizeSize;
    readonly resize: (width: number, height: number) => void;
    readonly start?: () => void;
    readonly end?: () => void;
}
/** A visible pointer/touch and keyboard grip; the owner supplies its geometry rules. */
export declare function resizeGrip(container: HTMLElement, options: ResizeGripOptions): {
    button: HTMLButtonElement;
    dispose(): void;
};
export {};
