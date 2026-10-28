import type { Diagnostic, Pack } from '../../types/src/core.js';
import { type IndexedRecord } from './core.js';
/** Trusted compiled family entry points install data before their executable rules. */
export declare function registerProfileFamily(id: string, profiles: readonly string[], evaluate: (view: IndexedRecord, records: readonly IndexedRecord[], review: boolean) => readonly Diagnostic[]): void;
export declare function loadedProfilePacks(): readonly Pack[];
