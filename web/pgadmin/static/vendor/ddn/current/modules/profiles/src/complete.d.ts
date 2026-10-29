import './generated.js';
import type { Pack, PackRegistrations } from '../../types/src/core.js';
export declare const completeRules: readonly import("@ddn/types").RuleDefinition[];
/** All adopted profiles with exact descriptors and executable semantic rules. */
export declare function createCompletePack(registrations?: PackRegistrations): Pack;
