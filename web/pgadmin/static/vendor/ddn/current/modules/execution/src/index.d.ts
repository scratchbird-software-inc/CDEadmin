import type { ComputationContext, ComputeRequest, ComputeResult, Executor, TaskOptions, VersionSet } from '@ddn/types';
/** Portable, deterministic SHA-256; no browser, Node or asynchronous IO dependency. */
export declare function sha256(text: string): string;
export declare function canonical(value: unknown): string;
export declare const fingerprint: (value: unknown) => string;
export declare function clone<T>(value: T): T;
export declare function freeze<T>(value: T): T;
export declare class ComputationStopped extends Error {
    readonly outcome: 'cancelled' | 'budget-exceeded';
    constructor(outcome: 'cancelled' | 'budget-exceeded', message: string);
}
export interface AccountingContext extends ComputationContext {
    readonly stats: {
        elapsedMs: number;
        workUnits: number;
        memoryBytes: number;
    };
    accountMemory(bytes: number): void;
    check(): void;
}
export declare function createContext(versions: VersionSet, task?: TaskOptions): AccountingContext;
export type ComputeHandler = (request: ComputeRequest, context: AccountingContext) => Promise<ComputeResult>;
export declare function createExecutor(handlers: Partial<Record<ComputeRequest['kind'], ComputeHandler>>): Executor;
