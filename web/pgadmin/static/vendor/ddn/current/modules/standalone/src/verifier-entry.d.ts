import { createVerifier } from '../../verifier/src/index.js';
import type { RuntimeOptions } from '@ddn/types';
export declare const api: {
    createVerifier: typeof createVerifier;
    createNativeRuntimeOptions: () => RuntimeOptions;
};
