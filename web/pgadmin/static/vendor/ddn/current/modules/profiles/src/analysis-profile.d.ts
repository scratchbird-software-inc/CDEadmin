import type { Json, Ref } from '../../types/src/core.js';
import { type IndexedRecord } from './core.js';
export declare function flatTraceAnalysis(view: IndexedRecord, records: readonly IndexedRecord[]): Json;
/** Read-only bounded calculations for inspector output, with no action execution. */
export declare function analyzeProfile(normalized: Json, target: Ref, values?: Record<string, Json>): Json;
