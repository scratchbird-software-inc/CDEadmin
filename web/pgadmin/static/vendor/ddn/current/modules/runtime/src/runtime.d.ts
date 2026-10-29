import type { Diagnostic, ModelSnapshot, OpenResult, Runtime, RuntimeEvent, RuntimeOptions, SourceSet, TaskOptions } from '@ddn/types';
import type { DecodeResult } from '../../language/src/index.js';
export { STANDARD_VERSIONS } from './versions.js';
export interface CommitBoundary {
    check(): Promise<readonly Diagnostic[]>;
    published(result: OpenResult): void;
}
export interface RuntimeState {
    options: RuntimeOptions;
    source?: SourceSet;
    decoded?: DecodeResult;
    current?: ModelSnapshot;
    diagnostics: readonly Diagnostic[];
    disposed: boolean;
    generation: number;
    counter: number;
    emit(event: RuntimeEvent): void;
    materialize(decoded: DecodeResult): DecodeResult;
    commitSources(source: SourceSet, options: TaskOptions, expectedFingerprint: string, boundary: CommitBoundary): Promise<OpenResult & {
        committed: boolean;
    }>;
}
export declare function runtimeState(runtime: Runtime): RuntimeState;
export declare function copySources(input: SourceSet): SourceSet;
export declare function createRuntime(inputOptions: RuntimeOptions): Runtime;
