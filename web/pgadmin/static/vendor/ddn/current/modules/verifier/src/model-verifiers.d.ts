import type { SourceSet, VerifiedModel, VerifiedSources, Verifier, VerifyOptions } from '../../types/src/core.js';
import type { DecodeResult } from '../../language/src/index.js';
type ModelVerifier = (input: SourceSet, options: VerifyOptions) => Promise<VerifiedSources>;
/** How verifySourcesWithModel runs on `verifier`. */
export declare function registerModelVerifier(verifier: Verifier, run: ModelVerifier): void;
export declare function modelVerifier(verifier: Verifier): ModelVerifier | undefined;
/** The full decode result, usable with the language package's patching functions. */
export declare function verifiedModel(decoded: DecodeResult): VerifiedModel;
export {};
