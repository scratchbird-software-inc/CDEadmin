import type { Diagnostic, ModelSnapshot, RuntimeOptions, VerificationReport, Verifier, VerifyOptions } from '../../types/src/core.js';
/** Internal worker bridge: retain decoder diagnostics without decoding a second time. */
export declare function verifyDecoded(verifier: Verifier, input: ModelSnapshot, options: VerifyOptions, diagnostics: readonly Diagnostic[]): Promise<VerificationReport>;
/** Staged verification is headless; source decoding and presentation remain separate. */
export declare function createVerifier(runtimeOptions: RuntimeOptions): Verifier;
