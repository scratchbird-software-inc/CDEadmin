import type { DataChange, Json, Ref } from '@ddn/types';
import type { RecordValue } from '../../model/src/index.js';
import type { AccountingContext } from '../../execution/src/index.js';
export interface ProviderOverlay {
    ref: Ref;
    revisionKey: string;
    revision: string;
    columns: RecordValue[];
    rows: Json[][];
}
/** Applies to a private candidate only; callers publish the entire candidate after verification. */
export declare function applyProviderOverlays(normalized: Json, overlays: ReadonlyMap<string, ProviderOverlay>): void;
export declare function stageProviderChanges(normalized: Json, prior: ReadonlyMap<string, ProviderOverlay>, dataRevisions: Readonly<Record<string, string>>, changes: readonly DataChange[], context: AccountingContext): Promise<{
    overlays: Map<string, ProviderOverlay>;
    revisions: Record<string, string>;
}>;
