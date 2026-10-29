import type { Diagnostic, Json, ProfileDescriptor, Ref } from '../../types/src/core.js';
import { codex } from './schema-core.js';
export declare const contractVersion = "ddn-next-1";
export declare const standardCommandIds: readonly string[];
export declare const completeProfileIds: readonly string[];
export declare const nativeProfileIds: readonly string[];
export declare function freezeProfileData<T>(v: T): T;
type CatalogueProfile = (typeof codex.profiles)[string];
/** External context reuses a profile contract without duplicating its catalogue data. */
export declare function getProfile(id: string): CatalogueProfile | undefined;
export declare function knownProfile(id: string): {
    id: string;
    method: string;
    projection: string;
} | undefined;
export declare function roleDescriptor(role: string, category?: string): import("./schema-core.js").RoleDescriptor | undefined;
export declare function coreDescriptor(id: string): {
    payload: number;
    complete: number;
    render: Record<string, Json>;
} | undefined;
export declare function coreTypeDescriptor(name: string, category?: string): {
    category: string;
    schema: number;
    core: string;
} | undefined;
export declare function profileDescriptor(id: string): ProfileDescriptor | undefined;
export interface IndexedRecord {
    file: string;
    owner: string;
    record: Record<string, Json>;
    ref: Ref;
    collection: string;
    index: number;
    path?: string;
}
export interface FileDocument {
    location: string;
    document: Record<string, Json>;
}
export declare function bundleFiles(normalized: Json): FileDocument[];
export declare function indexRecords(normalized: Json): IndexedRecord[];
export declare function resolveRecord(records: readonly IndexedRecord[], file: string, reference: Json | Ref | undefined): IndexedRecord | undefined;
/** Membership ownership is distinct from arbitrary inbound references. */
export declare function enclosingDefinitions(records: readonly IndexedRecord[], target: IndexedRecord): IndexedRecord[];
export declare function normalizedReference(value: Json | undefined): value is Record<string, Json>;
export declare function safeLocation(from: string, target: string): string | undefined;
export declare function nativeProfileDiagnostics(normalized: Json, view: IndexedRecord, records: readonly IndexedRecord[], review?: boolean): Diagnostic[];
export {};
