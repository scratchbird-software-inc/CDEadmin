import type { Json, Ref } from '@ddn/types';
import type { Viewer } from '@ddn/types/browser';
type Panel = (title: string, build: (body: HTMLElement) => (() => Promise<void>)) => HTMLElement;
type Commit = (ref: Ref, properties: Record<string, Json | undefined>) => Promise<void>;
/** Live appearance editor; every valid change uses the authorized source command service. */
export declare function openAppearance(viewer: Viewer, panel: Panel, commit: Commit): void;
export {};
