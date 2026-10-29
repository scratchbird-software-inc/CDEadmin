import type { Json, Ref } from '../../types/src/core.js';
export type RecordValue = Record<string, Json>;
export interface Document extends RecordValue {
}
export interface BundleFile {
    location: string;
    document: Document;
}
export interface Bundle {
    version: 'ddn-next-1';
    entry: string;
    files: BundleFile[];
}
export type RecordKind = 'workarea' | 'definition' | 'view' | 'placement' | 'appearance' | 'data' | 'source' | 'asset' | 'template' | 'publication' | 'note';
export interface RecordEntry {
    file: string;
    kind: RecordKind;
    record: RecordValue;
    ref: Ref;
}
export declare const isRecord: (value: unknown) => value is RecordValue;
export declare const asRecord: (value: unknown) => RecordValue;
export declare const asArray: (value: unknown) => Json[];
export declare const asString: (value: unknown, fallback?: string) => string;
export declare const recordRef: (file: string, record: RecordValue) => Ref;
export declare function normalizedFiles(value: unknown): BundleFile[];
/** Canonical identity only: selecting or fetching a location remains the host's responsibility. */
export declare function normalizeLocation(value: string, fromFile?: string): string;
export declare function listRecords(bundle: unknown): RecordEntry[];
export declare function resolveReference(bundle: unknown, fromFile: string, reference: unknown): RecordEntry | undefined;
export declare function findRecord(bundle: unknown, ref: Ref): RecordValue | undefined;
export declare function getPath(value: unknown, path: string): Json | undefined;
export declare function safePath(path: string): string[];
export declare function setPath(record: RecordValue, path: string, value: Json | undefined): void;
export declare function canonicalJson(value: unknown): string;
