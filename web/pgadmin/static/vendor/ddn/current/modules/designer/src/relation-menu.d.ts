import { type ProjectedRecord } from '../../presentation/src/native.js';
export type ContextMenuItem = readonly [
    string,
    () => void,
    {
        readonly name: string;
        readonly checked: boolean;
        readonly disabled: boolean;
        readonly title: string;
    }?
];
/** Presentation switches affect only the selected occurrence in this view. */
export declare function relationMenuItems(entry: ProjectedRecord, viewProperties: ProjectedRecord['effective'], editable: boolean, change: (path: string, value: boolean | string) => void): ContextMenuItem[];
