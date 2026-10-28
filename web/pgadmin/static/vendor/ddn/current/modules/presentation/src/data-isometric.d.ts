import type { DataProfileProjection } from './data-common.js';
import { type DataRecord } from './model.js';
/** Retained chart depth treatment. Top faces keep their quantitative geometry;
 * oblique side faces carry no additional data values or selectable identities. */
export declare function extrudeChart(result: DataProfileProjection, settings: DataRecord, depths?: ReadonlyMap<string, number>): DataProfileProjection;
