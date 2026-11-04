import type { Diagnostic, ModelSnapshot, RuntimeOptions, SourceSet, VerificationReport, VerifiedSources, Verifier, VerifyOptions } from '../../types/src/core.js';
import { type DecodeResult } from '../../language/src/index.js';
export type { VerifiedModel, VerifiedSources } from '../../types/src/core.js';
/** Verify sources and return the decoded model that was verified, so a host does
 *  not decode the same sources again. `model` is absent when decoding did not
 *  complete (an interrupted, cancelled or failed verification). */
export declare function verifySourcesWithModel(verifier: Verifier, input: SourceSet, options: VerifyOptions): Promise<VerifiedSources>;
/** verifySources for a caller that has already decoded the same sources.
 *  `decoded` is reused only when it is the unmodified result of a completed
 *  decodeSources call, without a previous result, over exactly the sources
 *  verification captures; otherwise the sources are decoded again. */
export declare function verifyDecodedSources(verifier: Verifier, input: SourceSet, decoded: DecodeResult, options: VerifyOptions): Promise<VerificationReport>;
/** Internal worker bridge: retain decoder diagnostics without decoding a second time. */
export declare function verifyDecoded(verifier: Verifier, input: ModelSnapshot, options: VerifyOptions, diagnostics: readonly Diagnostic[]): Promise<VerificationReport>;
/** Staged verification is headless; source decoding and presentation remain separate. */
export declare function createVerifier(runtimeOptions: RuntimeOptions): Verifier;
