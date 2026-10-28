import { analyzeProfile } from '../../profiles/src/index.js';
import { createVerifier } from '../../verifier/src/index.js';
import type { RuntimeOptions } from '@ddn/types';
export declare const api: {
    analyzeProfile: typeof analyzeProfile;
    createVerifier: typeof createVerifier;
    createCompleteRuntimeOptions: () => RuntimeOptions;
};
