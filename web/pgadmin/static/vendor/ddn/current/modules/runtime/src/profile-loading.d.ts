import type { ModelSnapshot, Runtime, SourceSet, TaskOptions } from '../../types/src/core.js';
export interface ProfileLoadingHost {
    readonly profiles: readonly {
        id: string;
        method: string;
    }[];
    ensure(input: SourceSet | ModelSnapshot | readonly string[], options?: TaskOptions): Promise<void>;
}
/** Distribution-host hook; DDN source cannot supply code or a loading URL. */
export declare function attachProfileLoadingHost(runtime: Runtime, host: ProfileLoadingHost): void;
export declare function profileLoadingHost(runtime: Runtime): ProfileLoadingHost | undefined;
export declare function prepareRuntimeProfiles(runtime: Runtime, input: SourceSet | ModelSnapshot | readonly string[], options?: TaskOptions): Promise<void>;
