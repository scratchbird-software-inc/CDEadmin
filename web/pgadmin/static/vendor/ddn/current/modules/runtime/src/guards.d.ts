import type { Diagnostic, ModelSnapshot, Ref } from '@ddn/types';
/** Only schema-declared references form dependencies; arbitrary JSON data never does. */
export declare function referenceGraph(normalized: unknown): Map<string, Set<string>>;
/** Source edits and provider updates cannot manufacture lifecycle transitions or attribution. */
export declare function checkLifecycleMutation(beforeNormalized: unknown, afterNormalized: unknown): Diagnostic[];
/** Protect accepted/reviewed definitions and every accepted scope that depends on them. */
export declare function affectedProtected(snapshot: ModelSnapshot, afterNormalized: unknown): Ref[];
