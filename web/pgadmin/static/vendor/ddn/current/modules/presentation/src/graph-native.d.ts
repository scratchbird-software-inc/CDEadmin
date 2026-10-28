import type { ModelSnapshot } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type LocatedRecord } from './model.js';
import { type GraphProjectionResult, type GraphProjectionOptions } from './graph-common.js';
/** Native DDN uses the common geometry engine without importing foreign methods. */
export declare function projectNativeGraph(snapshot: ModelSnapshot, view: LocatedRecord, entries: readonly ProjectedRecord[], options?: GraphProjectionOptions, fallback?: (snapshot: ModelSnapshot, view: LocatedRecord, entries: readonly ProjectedRecord[], options: GraphProjectionOptions) => GraphProjectionResult, supportsFallback?: (profile: string) => boolean): GraphProjectionResult;
