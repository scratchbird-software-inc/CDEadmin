import type { Bounds } from '@ddn/types';
import { type DataRecord } from './model.js';
/** Shared default proportions for canvas symbols and palette previews. */
export declare function graphNodeDimensions(role: string, profile: string, original: Bounds, record?: DataRecord, fixedSize?: boolean): Bounds;
