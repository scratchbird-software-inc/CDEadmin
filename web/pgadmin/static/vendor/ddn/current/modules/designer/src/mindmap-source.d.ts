import type { Json, Ref, Runtime, SourcePatch, SourceSet } from '@ddn/types';
import { type DecodeResult } from '../../language/src/index.js';
/** A local source transaction. Generated recipe content is made explicit only
 * inside its own block, using the existing dialect and preserving identities. */
export declare function mindmapSource(runtime: Runtime, view: Ref): {
    readonly source: SourceSet;
    readonly decoded: DecodeResult;
    record: (ref: Ref) => import("../../model/src/index.js").RecordEntry;
    unique: (stem: string, file?: string) => string;
    reference: (ref: Ref) => string;
    append: (file: string, text: string, parent?: Ref) => void;
    set: (ref: Ref, path: string, value: Json | undefined) => void;
    apply: (patches: readonly SourcePatch[]) => void;
    materialize: () => void;
    patches: () => {
        file: string;
        base: string;
        start: number;
        end: number;
        text: string;
    }[];
};
