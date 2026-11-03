import type { CatalogueFamilyManifest } from './catalogue-store.js';
export declare const catalogueShards: Readonly<Record<string, CatalogueFamilyManifest & {
    readonly parent: string;
}>>;
export declare function profileCatalogueShard(profile: string): string | undefined;
