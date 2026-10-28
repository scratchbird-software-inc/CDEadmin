import type { AuthorityProvider, CancelToken, CommandService, CommitResult, Pack, TaskOptions } from '@ddn/types';
import type { Runtime } from '@ddn/types';
/** Internal browser-edit grouping. It does not change the public command ABI. */
export interface CommandHistoryGroup {
    /** True only while this session still owns the current source revision. */
    readonly current: boolean;
    readonly changed: boolean;
    readonly signal: CancelToken;
    /** Capture commands started synchronously by this callback, not unrelated async work. */
    run<T>(action: () => T): T;
    commit(preparedId: string, task?: TaskOptions): Promise<CommitResult>;
    revert(): Promise<CommitResult>;
    close(): void;
}
export declare function createCommandHistoryGroup(service: CommandService): CommandHistoryGroup;
/** Capture before awaiting preparation; async continuations do not inherit this scope. */
export declare function currentCommandHistoryGroup(service: CommandService): CommandHistoryGroup | undefined;
export declare function createCommandService(runtime: Runtime, authority: AuthorityProvider, limits?: {
    maxCommands: number;
    maxBytes: number;
}): CommandService;
/** Descriptors disclose the native edit vocabulary; the runtime materializes its source-aware plans. */
export declare function createNativeCommandPack(): Pack;
export declare function createCompleteCommandPack(): Pack;
export declare function createModularCommandPack(): Pack;
