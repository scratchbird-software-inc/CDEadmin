import type { Diagnostic, Json } from '../../types/src/core.js';
import { type IndexedRecord } from './core.js';
import { type DecisionDomain, type DecisionRule } from './analysis.js';
interface Link {
    item: IndexedRecord;
    from: IndexedRecord;
    to: IndexedRecord;
    ends: Record<string, Json>[];
}
export interface ProfileSelection {
    nodes: IndexedRecord[];
    edges: IndexedRecord[];
    links: Link[];
    selected: Map<string, IndexedRecord>;
    resolve: (ref: Json | undefined, owner?: IndexedRecord) => IndexedRecord | undefined;
}
export declare function profileSelection(view: IndexedRecord, records: readonly IndexedRecord[]): ProfileSelection;
export declare function completeProfileDiagnostics(view: IndexedRecord, records: readonly IndexedRecord[], review?: boolean): Diagnostic[];
export declare function decisionDomains(view: IndexedRecord, records: readonly IndexedRecord[]): DecisionDomain[];
export declare function decisionRules(view: IndexedRecord, records: readonly IndexedRecord[]): DecisionRule[];
export declare function decisionOutputErrors(view: IndexedRecord, records: readonly IndexedRecord[], rules: readonly DecisionRule[]): string[];
export {};
