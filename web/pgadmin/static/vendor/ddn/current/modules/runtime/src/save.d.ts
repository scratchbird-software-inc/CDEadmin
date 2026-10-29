import type { Runtime, SourceSet, TaskOptions } from '@ddn/types';
/** Materialize explicitly requested data snapshots into save artifacts, never the live model. */
export declare function sourcesForSave(runtime: Runtime, task?: TaskOptions): Promise<SourceSet | undefined>;
