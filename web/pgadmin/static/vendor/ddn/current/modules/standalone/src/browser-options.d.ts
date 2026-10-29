import type { RuntimeOptions } from '@ddn/types';
/** Inline HTML supplies a trusted Blob worker; CSP-denied hosts use identical local handlers. */
export declare function withBrowserExecutor(options: RuntimeOptions): RuntimeOptions;
