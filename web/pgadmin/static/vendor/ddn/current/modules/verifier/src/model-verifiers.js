const modelVerifiers = new WeakMap();
/** How verifySourcesWithModel runs on `verifier`. */
export function registerModelVerifier(verifier, run) { modelVerifiers.set(verifier, run); }
export function modelVerifier(verifier) { return modelVerifiers.get(verifier); }
/** The full decode result, usable with the language package's patching functions. */
export function verifiedModel(decoded) {
    return Object.freeze({ ...decoded });
}
//# sourceMappingURL=model-verifiers.js.map