import type { DataProjector } from './adapters.js';
import { DataScene, type DataProfileProjection } from './data-common.js';
import { type DataRecord } from './model.js';
/** Shared data-scene setup has no dependency on optional drawing algorithms. */
export declare function createDataProjector(profiles: readonly string[], draw: (scene: DataScene, geography?: ReadonlyMap<string, unknown>) => void, finish?: (result: DataProfileProjection, settings: DataRecord, scene: DataScene) => DataProfileProjection): DataProjector;
