import type { Json, Ref } from '@ddn/types';
import { type SchemaNode } from '../../profiles/src/schema-core.js';
export interface FieldEditor {
    read(): Json;
}
export interface ReferenceChoice {
    ref: Ref;
    label: string;
}
export declare function schemaNode(id: number | undefined): SchemaNode;
export declare function childSchema(id: number | undefined, field: string): number | undefined;
/** Schema-driven controls keep omission distinct from an authored empty value. */
export declare function createFieldEditor(parent: HTMLElement, id: number | undefined, value: Json | undefined, refs: readonly ReferenceChoice[], label: string, depth?: number, forcedType?: string): FieldEditor;
