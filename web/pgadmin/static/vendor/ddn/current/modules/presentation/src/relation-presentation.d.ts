import type { ProjectedRecord } from './project-core.js';
import { type DataRecord, type LocatedRecord } from './model.js';
export interface RelationPresentation {
    readonly allowed: boolean;
    readonly visible: boolean;
    readonly mode: 'text' | 'numbers' | 'tokens';
    /** Membership, independent from a globally hidden legend. */
    readonly inLegend: boolean;
    readonly number: string;
}
export declare function relationLegendVisible(view: DataRecord): boolean;
/** Shared by designer controls and every graph renderer. Absence is inherited,
 * rather than a stored value that overrides a profile's presentation rules. */
export declare function relationPresentation(entry: ProjectedRecord, view?: DataRecord): RelationPresentation;
export declare function relationCaption(entry: ProjectedRecord, semantic: string, view?: DataRecord): string;
/** Assign stable keys before label/legend filtering or specialized projections
 * create repeated occurrences. Different physical files never share identity. */
export declare function prepareRelationPresentation(entries: readonly ProjectedRecord[], all: readonly LocatedRecord[], view: DataRecord): ProjectedRecord[];
