import type { Pack, PackRegistrations } from '../../types/src/core.js';
export declare const nativeRules: readonly import("@ddn/types").RuleDefinition[];
/** Exact native descriptors and executable rules; presentation adapters register separately. */
export declare function createNativePack(registrations?: PackRegistrations): Pack;
