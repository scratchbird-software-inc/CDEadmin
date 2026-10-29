import type { Json, Ref } from '@ddn/types';
import { quoteText } from '../../language/src/index.js';
type RecordValue = Record<string, Json>;
/** One copied element: its authored definition (without identity) and where it sat in its view. */
export interface ClipItem {
    readonly record: RecordValue;
    readonly position?: {
        readonly x: number;
        readonly y: number;
    };
    /** The original definition, for Paste as reference while it still exists. */
    readonly source?: Ref;
}
export declare function clipRecord(record: Readonly<Record<string, unknown>>): RecordValue;
/** DDN text for the system clipboard; it pastes into the source panel, a text file, or another designer. */
export declare function clipboardText(items: readonly ClipItem[]): string;
/** Reads DDN element declarations copied as text (from another tab or a file). */
export declare function parseClipboardText(text: string): ClipItem[];
/** A name not yet used in the file: "Order", then "Order 2", "Order 3", … */
export declare function uniqueName(name: string, taken: ReadonlySet<string>): string;
/** The declarations to append to a view: names made unique, positions moved by the offset. */
export declare function pasteRecords(items: readonly ClipItem[], taken: Set<string>, offset: {
    x: number;
    y: number;
}): string;
/** RFC 4180 CSV: quoted fields, doubled quotes, CRLF or LF rows. The first row is the header. */
export declare function parseCsv(text: string): {
    columns: {
        id: string;
        label: string;
        type: 'text' | 'number';
    }[];
    rows: Json[][];
};
export { quoteText };
