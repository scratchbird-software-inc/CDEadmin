import type { Coverage, Diagnostic, Json, Ref, SourceFile, SourcePatch, SourceSet, TaskOptions } from '../../types/src/core.js';
import type { Bundle, RecordValue } from '../../model/src/index.js';
export type { Bundle, Document, RecordValue } from '../../model/src/index.js';
export interface SyntaxNode {
    file: string;
    kind: string;
    start: number;
    end: number;
    headerEnd: number;
    bodyStart: number;
    indent: number;
    raw: string;
    children: SyntaxNode[];
    ref?: Ref;
    owner?: Ref;
    path?: string;
    nameStart?: number;
    nameEnd?: number;
    valueStart?: number;
    valueEnd?: number;
    titleStart?: number;
    titleEnd?: number;
    implicit?: boolean;
    generated?: boolean;
    identityKey?: string;
}
export interface ReferenceSite {
    file: string;
    start: number;
    end: number;
    reference: RecordValue;
    target?: Ref;
    kind: 'reference' | 'member';
    spelling?: 'name' | 'id' | 'cell';
    scope?: Ref;
    boundCell?: boolean;
}
export interface SourceDocument {
    file: SourceFile;
    nodes: SyntaxNode[];
    newline: '\n' | '\r\n';
    bom: boolean;
}
export interface DecodeOptions extends TaskOptions {
    previous?: DecodeResult;
}
export interface DecodeResult {
    syntaxValid: boolean;
    normalized: Bundle;
    documents: SourceDocument[];
    diagnostics: Diagnostic[];
    coverage: Coverage;
    references: ReferenceSite[];
}
export declare function splitDelimited(text: string, delimiter: string): string[];
export declare function decodeText(raw: string): string;
export declare function quoteText(text: string): string;
export declare function parseTableHeader(text: string): RecordValue[];
export declare function parseTableRow(text: string, columns: readonly RecordValue[]): Json[];
export declare function decodeSources(input: SourceSet, options?: DecodeOptions): DecodeResult;
export declare function allNodes(result: DecodeResult): SyntaxNode[];
export declare function findNode(result: DecodeResult, target: Ref): SyntaxNode | undefined;
export declare function applySourcePatches(input: SourceSet, patches: readonly SourcePatch[]): SourceSet;
export declare function serializeProperties(properties: RecordValue, indent?: string, newline?: string): string;
export declare function patchProperty(result: DecodeResult, target: Ref, path: string, value: Json | undefined): SourcePatch[];
export declare function deleteDeclaration(result: DecodeResult, target: Ref): SourcePatch[];
export declare function renameDeclaration(result: DecodeResult, target: Ref, name: string): SourcePatch[];
export declare function appendDeclaration(result: DecodeResult, file: string, text: string, parent?: Ref): SourcePatch[];
export declare function encodeDefinition(record: RecordValue): string;
export declare function sourceText(result: DecodeResult, target: Ref): string | undefined;
/** Named datasets use the same typed property notation as other declarations. */
export declare function replaceRecordData(result: DecodeResult, target: Ref, columns: readonly RecordValue[], rows: readonly (readonly Json[])[]): SourcePatch[];
/** Replace only authored table input, retaining any original free-form draft. */
export declare function replaceDataBody(result: DecodeResult, target: Ref, data: {
    columns: readonly RecordValue[];
    rows: readonly (readonly Json[])[];
}): SourcePatch[];
export declare function replaceDraftBody(result: DecodeResult, target: Ref, text: string, format?: 'text' | 'fields' | 'table'): SourcePatch[];
/** Edit a raw note body without replacing its header, stable identity or siblings. */
export declare function replaceNoteBody(result: DecodeResult, target: Ref, text: string): SourcePatch[];
