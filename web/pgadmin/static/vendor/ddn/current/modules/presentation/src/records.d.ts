import type { Diagnostic, ModelSnapshot, Ref } from '@ddn/types';
import { type DataRecord, type LocatedRecord } from './model.js';
export interface RecordTable {
    columns: DataRecord[];
    rows: unknown[][];
    targets: (Ref | undefined)[];
    diagnostics: Diagnostic[];
}
/** Field-key table projection. References stay qualified; missing cells stay distinct from null. */
export declare function recordTableData(snapshot: ModelSnapshot, view: LocatedRecord): RecordTable;
