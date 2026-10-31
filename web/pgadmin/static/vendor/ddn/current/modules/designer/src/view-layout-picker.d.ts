import { type StandardDialog } from './dialogs.js';
type LayoutKind = 'dynamic' | 'monitor' | 'page' | 'presentation';
export interface LayoutChoice {
    id: string;
    label: string;
    detail: string;
    hint: string;
    kind: LayoutKind;
    width?: number;
    height?: number;
    unavailable?: boolean;
}
export declare const EXTENDED_VIEW_LAYOUTS: readonly LayoutChoice[];
export interface ViewLayoutDialogOptions {
    readonly selected?: string;
    readonly allowExtended?: boolean;
    readonly onContinue: (preset: string) => void;
    readonly onBack?: (preset: string) => void;
}
export declare function viewLayoutLabel(preset: string): string;
/** Surface choice is independent of the later diagram method and profile. */
export declare function viewLayoutDialog(host: HTMLElement, options: ViewLayoutDialogOptions): StandardDialog;
/** Dynamic remains implicit; a fixed layout stores only its versioned recipe. */
export declare function viewLayoutSource(preset: string, allowExtended?: boolean): string;
export {};
