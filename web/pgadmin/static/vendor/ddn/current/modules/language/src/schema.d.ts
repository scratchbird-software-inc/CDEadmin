import type { LexicalShape } from '../../profiles/src/schema-core.js';
export type Shape = LexicalShape;
export declare const shapes: Readonly<Record<string, Shape>>;
export declare const roleTypes: Record<string, {
    category: string;
    schema: string;
    core: string;
}>;
export declare const coreTypes: Record<string, {
    category: string;
    schema: string;
    core: string;
}>;
export declare const profiles: Record<string, {
    id: string;
    method: string;
    projection: string;
    primary_palette: string[];
    relation_roles: string[];
}>;
