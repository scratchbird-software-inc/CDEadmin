import type { Json, ModelSnapshot, Ref } from '@ddn/types';
export type DataRecord = Record<string, unknown>;
export interface LocatedRecord {
    readonly file: string;
    readonly record: DataRecord;
    readonly owner: string;
    readonly ref: Ref;
}
export declare const object: (value: unknown) => DataRecord;
export declare const array: (value: unknown) => unknown[];
export declare const str: (value: unknown, fallback?: string) => string;
export declare const num: (value: unknown, fallback?: number) => number;
export declare function pathValue(value: unknown, path: string): unknown;
export declare function refKey(ref: Ref): string;
export declare function records(snapshot: ModelSnapshot): LocatedRecord[];
export declare function resolveRecord(all: readonly LocatedRecord[], reference: unknown, declaringFile: string): LocatedRecord | undefined;
export declare function findRecord(snapshot: ModelSnapshot, ref: Ref): LocatedRecord | undefined;
export declare function titleOf(record: DataRecord): string;
export declare function tableData(snapshot: ModelSnapshot, item: LocatedRecord): {
    columns: DataRecord[];
    rows: unknown[][];
};
export declare function asJson(value: unknown): Json;
