import type { Bounds, Diagnostic } from '@ddn/types';
import type { ProjectedRecord } from './project-core.js';
import { type LocatedRecord, type DataRecord } from './model.js';
/** Endpoint ordering is a presentation property. It never rewrites the semantic
 * parent direction or adds junctions where several branches leave a topic. */
export declare function mindmapEdges(edges: readonly ProjectedRecord[], nodes: readonly ProjectedRecord[], all: readonly LocatedRecord[], frame: Bounds, viewProperties: DataRecord | undefined, diagnostics: Diagnostic[], unavailable: string[]): ProjectedRecord[];
