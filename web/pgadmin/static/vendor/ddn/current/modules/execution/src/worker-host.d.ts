import type { Executor } from '../../types/src/core.js';
export interface WorkerExecutorOptions {
    createWorker: () => Worker;
    fallback: Executor;
}
/** One lazy worker per executor. The caller controls creation; this module never fetches code. */
export declare function createWorkerExecutor(options: WorkerExecutorOptions): Executor;
