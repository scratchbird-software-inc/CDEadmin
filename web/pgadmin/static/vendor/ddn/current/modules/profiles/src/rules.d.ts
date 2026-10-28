import type { Diagnostic, RuleDefinition } from '../../types/src/core.js';
import { type IndexedRecord } from './core.js';
export declare function rulesFor(ids: readonly string[], additional?: (view: IndexedRecord, records: readonly IndexedRecord[], review: boolean) => readonly Diagnostic[]): readonly RuleDefinition[];
