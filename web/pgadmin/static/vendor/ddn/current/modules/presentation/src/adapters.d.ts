import type { Bounds, ModelSnapshot, Json, Ref } from '@ddn/types';
import type { LocatedRecord, DataRecord } from './model.js';
import type { ProjectedRecord } from './project-core.js';
import type { GraphProjectionOptions, GraphProjectionResult } from './graph-common.js';
import type { DataProfileProjection, DataProjectionOptions } from './data-common.js';
export type PresentationFamilyId = 'graphs' | 'charts' | 'geography' | 'surfaces';
export type GraphProjector = (snapshot: ModelSnapshot, view: LocatedRecord, entries: readonly ProjectedRecord[], options?: GraphProjectionOptions) => GraphProjectionResult;
export type DataProjector = (snapshot: ModelSnapshot, view: LocatedRecord, bounds: Bounds, effective: DataRecord, options?: DataProjectionOptions & {
    geography?: ReadonlyMap<string, unknown>;
}) => DataProfileProjection | undefined;
export type ProfileAnalyzer = (normalized: Json, target: Ref, values?: Record<string, Json>) => Json;
export interface PresentationFamily {
    readonly id: PresentationFamilyId;
    readonly version: '1.0.0';
    readonly language: 'ddn-next-1';
    readonly profiles: readonly string[];
    readonly kind: 'graph' | 'data';
    readonly graph?: GraphProjector;
    readonly data?: DataProjector;
    readonly analyze?: ProfileAnalyzer;
}
export declare const availableProjectionProfiles: ReadonlySet<string>;
/** Trusted local code registration. Assets are authenticated/version-selected by the host loader. */
export declare function installPresentationFamily(family: PresentationFamily): void;
export declare function installedPresentationFamilies(): readonly PresentationFamily[];
export declare const isGraphProfile: (profile: string) => boolean;
export declare const isDataProfile: (profile: string) => boolean;
export declare const graphProjector: (profile: string) => GraphProjector | undefined;
export declare const dataProjector: (profile: string) => DataProjector | undefined;
export declare function analyzePresentedProfile(normalized: Json, target: Ref, values?: Record<string, Json>): Json;
