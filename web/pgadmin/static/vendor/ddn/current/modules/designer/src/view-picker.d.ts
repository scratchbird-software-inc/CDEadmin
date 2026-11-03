export { profileDisplayName, diagramHeader } from './view-labels.js';
export interface ViewTypePicker {
    readonly element: HTMLElement;
    readonly value: string;
    onChange(listener: (value: string) => void): void;
}
/** Browse lightweight previews; selecting a type does not load its renderer pack. */
export declare function viewTypePicker(body: HTMLElement, profiles: readonly {
    id: string;
    method: string;
}[], label?: string, selected?: string): ViewTypePicker;
/** A new mind map includes its central topic; other defaults remain implicit. */
