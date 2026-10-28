import type { Json, Executor, RuntimeOptions, SourceSet, ModelSnapshot, VerifyOptions } from '../../types/src/core.js';
import { type DecodeResult } from '../../language/src/index.js';
/** Internal payload contract shared by worker and cooperative executors. */
export interface DecodePayload {
    sources: SourceSet;
    previous?: DecodeResult;
}
export interface DecodedPayload {
    decoded: DecodeResult;
    fingerprint: string;
}
export interface VerifyPayload {
    diagnostics?: readonly import('../../types/src/core.js').Diagnostic[];
    snapshot: ModelSnapshot;
    options: Pick<VerifyOptions, 'scope' | 'purpose' | 'level' | 'measurement'>;
}
/** Byte copies stay with their source owner; compute messages contain decoded text only. */
export declare function decodePayload(sources: SourceSet, previous?: DecodeResult): Json;
/** Both execution modes invoke these exact handlers; host-supplied packs stay trusted code. */
export declare function createComputeExecutor(options: RuntimeOptions): Executor;
