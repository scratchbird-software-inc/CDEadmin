import type { SourceSet } from '../../types/src/core.js';
export interface DraftAsset {
    id: string;
    mime: string;
    base64: string;
}
export interface DocumentDraft extends SourceSet {
    version: 1;
    savedAt: string;
    assets: readonly DraftAsset[];
}
export declare const DRAFT_KEY = "ddn.designer.draft.v1";
export declare function encodeDraftAsset(id: string, mime: string, bytes: Uint8Array): DraftAsset;
export declare function restoreDraftAssets(draft: DocumentDraft): Map<string, File>;
export declare function readDocumentDraft(text: string | null): DocumentDraft | undefined;
