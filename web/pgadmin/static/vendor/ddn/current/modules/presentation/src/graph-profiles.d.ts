import { type GraphProjectionResult, type GraphProjectionOptions } from './graph-common.js';
export type { GraphProjectionResult, GraphProjectionOptions } from './graph-common.js';
import type { ModelSnapshot } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type LocatedRecord } from './model.js';
export declare const graphProfileIds: readonly string[];
export declare function projectGraphProfile(snapshot: ModelSnapshot, view: LocatedRecord, entries: readonly ProjectedRecord[], options?: GraphProjectionOptions): GraphProjectionResult;
