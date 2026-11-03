import { type StandardDialog } from './dialogs.js';
export interface ViewLayoutDialogOptions {
    readonly selected?: string;
    readonly onContinue: (preset: string) => void;
    readonly onBack?: (preset: string) => void;
}
/** Surface choice is independent of the later diagram method and profile. */
export declare function viewLayoutDialog(host: HTMLElement, options: ViewLayoutDialogOptions): StandardDialog;
export { viewLayoutSource } from './layout-source.js';
