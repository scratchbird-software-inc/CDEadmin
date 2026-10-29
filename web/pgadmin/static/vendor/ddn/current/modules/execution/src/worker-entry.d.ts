import type { Executor, RuntimeOptions } from '../../types/src/core.js';
export declare const WORKER_CHANNEL = "ddn.compute.v1";
export interface ComputeMessagePort {
    postMessage(message: unknown): void;
    addEventListener(type: 'message', listener: (event: {
        data: unknown;
    }) => void): void;
    removeEventListener(type: 'message', listener: (event: {
        data: unknown;
    }) => void): void;
}
/** Explicit installation keeps imports inert in browsers, workers and headless hosts. */
export declare function installWorkerServer(port: ComputeMessagePort, executor: Executor): () => void;
export declare function bootComputeWorker(options: RuntimeOptions, port?: ComputeMessagePort): () => void;
