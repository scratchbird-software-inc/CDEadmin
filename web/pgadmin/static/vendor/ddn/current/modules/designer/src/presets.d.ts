import type { Json } from '@ddn/types';
export type PresetTarget = 'workarea' | 'element' | 'view';
export interface AppearancePreset {
    id: string;
    name: string;
    scope: 'user' | 'company';
    target: PresetTarget;
    profile?: string;
    properties: Record<string, Json>;
}
export interface PresetPack {
    format: 'ddn-appearance-presets';
    version: 1;
    presets: AppearancePreset[];
}
export declare const PRESET_PATHS: readonly ["background.color", "background.texture", "text.color", "border.color", "opacity", "style.paper", "style.font", "style.font_size", "style.look", "shadow", "decorations"];
/** Portable appearance data. Company is provenance, never an authorization grant. */
export declare function parsePresetPack(text: string): PresetPack;
export declare function serializePresetPack(presets: readonly AppearancePreset[]): string;
export declare function standardPresets(target: PresetTarget): AppearancePreset[];
export declare function mergePresetPacks(existing: readonly AppearancePreset[], incoming: readonly AppearancePreset[]): AppearancePreset[];
export declare function readLocalPresets(storage?: Pick<Storage, 'getItem'>): AppearancePreset[];
export declare function writeLocalPresets(storage: Pick<Storage, 'setItem'>, presets: readonly AppearancePreset[]): void;
