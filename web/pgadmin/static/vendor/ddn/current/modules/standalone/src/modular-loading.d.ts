import type { Diagnostic, ModelSnapshot, RuntimeOptions, SourceSet, TaskOptions, VerificationReport, VerifyOptions, VersionSet } from '../../types/src/core.js';
export declare function requiredProfiles(input: SourceSet | ModelSnapshot | readonly string[], task?: TaskOptions): readonly string[];
export declare const scanUnits: (input: SourceSet | ModelSnapshot | readonly string[]) => number;
export declare function remainingTask(task: TaskOptions, started: number, units: number): TaskOptions;
/** Profile IDs are mapped through the installed distribution's trusted manifest. */
export declare function ensureProfileInput(input: SourceSet | ModelSnapshot | readonly string[], drawing: boolean, task?: TaskOptions): Promise<void>;
export declare function createModularRuntimeOptions(): RuntimeOptions;
export declare function createModularBrowserOptions(): RuntimeOptions;
export declare function installModularWorkerFactory(): void;
export declare class HostStopped extends Error {
    readonly reason: 'stale' | 'disposed';
    constructor(reason: 'stale' | 'disposed', message: string);
}
export declare function loadingDiagnostic(error: unknown, prefix?: string): Diagnostic;
export declare function verificationFailure(input: SourceSet | ModelSnapshot, task: VerifyOptions, versions: VersionSet, error: unknown, started: number): VerificationReport;
