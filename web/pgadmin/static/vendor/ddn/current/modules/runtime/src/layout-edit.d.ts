import type { Ref, Runtime, SourcePatch } from '@ddn/types';
export declare function automaticLayoutAlgorithm(profile: string): string;
/** Plan one undoable, view-local edit. The caller commits through the normal
 * command service so lifecycle, source revisions and authority remain enforced.
 * An optional effective algorithm includes viewer-supplied CSS defaults. */
export declare function reflowViewPatches(runtime: Runtime, view: Ref, effectiveAlgorithm?: string): SourcePatch[];
