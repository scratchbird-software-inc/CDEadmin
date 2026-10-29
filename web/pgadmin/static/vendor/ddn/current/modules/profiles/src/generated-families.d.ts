import type { CatalogueFamilyManifest } from './catalogue-store.js';
export declare const catalogueFamilies: Readonly<Record<string, CatalogueFamilyManifest>>;
export declare function profileCatalogueFamily(profile: string): string | undefined;
