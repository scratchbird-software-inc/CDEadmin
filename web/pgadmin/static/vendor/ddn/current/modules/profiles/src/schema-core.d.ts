import type { Json } from '../../types/src/core.js';
export interface SchemaNode {
    ref?: number;
    type?: string | string[];
    enum?: Json[];
    const?: Json;
    properties?: Record<string, number>;
    required?: string[];
    additionalProperties?: boolean | number;
    items?: number;
    minItems?: number;
    maxItems?: number;
    uniqueItems?: boolean;
    minProperties?: number;
    maxProperties?: number;
    minLength?: number;
    maxLength?: number;
    minimum?: number;
    maximum?: number;
    exclusiveMinimum?: number;
    exclusiveMaximum?: number;
    pattern?: string;
    format?: string;
    allOf?: number[];
    anyOf?: number[];
    oneOf?: number[];
    not?: number;
    if?: number;
    then?: number;
    else?: number;
}
export interface PropertyDefinition {
    owner: string;
    path: string;
    schema: number;
    default: {
        kind: string;
        value?: Json;
        rule?: string;
    };
    css: boolean;
    settable: boolean;
    defaultable: boolean;
    cssName?: string;
}
export interface RoleDescriptor {
    role: string;
    category: string;
    core: string;
    schema: number;
    render: Record<string, Json>;
}
export interface EndpointContract {
    role: string;
    source_roles: string[];
    target_roles: string[];
    member_endpoints: boolean;
    self_allowed: boolean;
    canonical_pattern: string;
    canonical_direction: string;
}
export interface NativeProfile {
    id: string;
    method: string;
    projection: string;
    primary_palette: string[];
    context_roles: string[];
    relation_roles: string[];
    relation_endpoint_contracts: EndpointContract[];
    defaults: Record<string, {
        kind: string;
        value?: Json;
        rule?: string;
        authored_default?: Json;
    }>;
    standard_overrides: Record<string, Json>;
    inherits: string | null;
    projection_schema: string;
    scope: string;
    exclusions: string[];
    rules: string[];
    bounded_analysis: string;
    metadata_editor_fields: string[];
    designer_commands: string[];
}
interface Codex {
    nodes: (SchemaNode | boolean)[];
    roots: Record<string, number>;
    properties: PropertyDefinition[];
    roles: Record<string, RoleDescriptor>;
    profiles: Record<string, NativeProfile>;
    knownProfiles: Record<string, {
        id: string;
        method: string;
        projection: string;
    }>;
    core: Record<string, {
        payload: number;
        complete: number;
        render: Record<string, Json>;
    }>;
    coreTypes: Record<string, {
        category: string;
        schema: number;
        core: string;
    }>;
    nativeProfiles: string[];
    cssMap: Record<string, {
        path: string;
        bindings: {
            owner: string;
            property: string;
        }[];
    }>;
    version: string;
    sourceHashes: Record<string, string>;
}
export declare const codex: Codex;
export interface SchemaIssue {
    path: string;
    keyword: string;
    message: string;
}
export interface SchemaOptions {
    checkpoint?: (units: number) => void;
    maxIssues?: number;
    reference?: (value: Record<string, Json>, path: string) => void;
}
export declare function isRecord(value: unknown): value is Record<string, Json>;
export declare function stableStringify(value: unknown): string;
/** Interprets deduplicated build-time validation instructions; never evaluates source code. */
export declare function validateSchema(schema: string | number, value: unknown, options?: SchemaOptions): SchemaIssue[];
export declare function getPath(value: unknown, path: string): Json | undefined;
export declare function setPath(value: Record<string, Json>, path: string, next: Json): void;
/** Lexical shape access shares the verifier instructions; it does not insert defaults. */
export interface LexicalShape {
    $ref?: string;
    type?: string | readonly string[];
    properties?: Readonly<Record<string, LexicalShape>>;
    items?: LexicalShape;
    additionalProperties?: LexicalShape | boolean;
    anyOf?: readonly LexicalShape[];
    oneOf?: readonly LexicalShape[];
}
export declare function schemaShape(schema: string | number): LexicalShape | undefined;
export declare const lexicalShapes: Readonly<Record<string, LexicalShape>>;
/** Exact schema shape for descriptor-driven editors; numeric references remain immutable codex indexes. */
export declare function getSchema(schema: string | number): SchemaNode | boolean | undefined;
export {};
