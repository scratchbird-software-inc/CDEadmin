import type { Bounds } from '@ddn/types';
import type { ProjectedRecord } from './project.js';
/** Isometric graph is a presentation of the existing flat layout. Identities,
 * routes and authored coordinates stay unchanged; depth is purely visual. */
export declare function isometricGraph(entries: readonly ProjectedRecord[], frame: Bounds, defaultDepth: number): ProjectedRecord[];
