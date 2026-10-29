import type { Diagnostic, Json, Ref } from '../../types/src/core.js';
import { type IndexedRecord } from './core.js';
export interface ProjectionRow {
    values: Record<string, Json>;
    source: Ref;
}
/** Options admitted by the retained mark operations, before defaults are added. */
export declare function chartOptionErrors(profileId: string, authored: Readonly<Record<string, Json>>): string[];
export declare function projectionRows(view: IndexedRecord, records: readonly IndexedRecord[]): ProjectionRow[];
export declare function projectionDiagnostics(view: IndexedRecord, records: readonly IndexedRecord[], review: boolean): Diagnostic[];
