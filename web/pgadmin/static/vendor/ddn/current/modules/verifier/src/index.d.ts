import type { Diagnostic, ModelSnapshot, RuntimeOptions, SourceSet, VerificationReport, Verifier, VerifyOptions } from '../../types/src/core.js';
import { createSourceSet } from '../../language/src/index.js';
export { createSourceSet };
/** Internal worker bridge: retain decoder diagnostics without decoding a second time. */
export declare function verifyDecoded(verifier: Verifier, input: ModelSnapshot, options: VerifyOptions, diagnostics: readonly Diagnostic[]): Promise<VerificationReport>;
/** Convenience helper to verify a DDN text string, file map, or SourceSet with sensible defaults. */
export declare function verifyText(verifier: Verifier, input: string | Readonly<Record<string, string>> | SourceSet, options?: Partial<VerifyOptions>): Promise<VerificationReport>;
/** Staged verification is headless; source decoding and presentation remain separate. */
export declare function createVerifier(runtimeOptions: RuntimeOptions): Verifier & {
    verifyText(input: string | Readonly<Record<string, string>> | SourceSet, options?: Partial<VerifyOptions> & {
        entry?: string;
    }): Promise<VerificationReport>;
};
