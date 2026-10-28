import type { Json, Ref } from '@ddn/types';
import type { Viewer } from '@ddn/types/browser';
type Panel = (title: string, build: (body: HTMLElement) => (() => Promise<void>)) => HTMLElement;
type Commit = (target: Ref, properties: Record<string, Json | undefined>) => Promise<void>;
/** A typed settings form. Only changed values reach the authorized source service. */
export declare function openProperties(viewer: Viewer, panel: Panel, commit: Commit): void;
export {};
