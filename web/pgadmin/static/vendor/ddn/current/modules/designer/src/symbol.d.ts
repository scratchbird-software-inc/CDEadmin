import type { Json, Ref } from '@ddn/types';
import type { Viewer } from '@ddn/types/browser';
type Panel = (title: string, build: (body: HTMLElement) => (() => Promise<void>)) => HTMLElement;
type Commit = (target: Ref, properties: Record<string, Json | undefined>) => Promise<void>;
/** Live symbol presentation uses the same authorized transaction as other appearance editors. */
export declare function openSymbol(viewer: Viewer, panel: Panel, commit: Commit): void;
export {};
