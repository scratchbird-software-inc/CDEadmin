/** Trusted catalogue data has the same version boundary as executable packs. */
export interface CatalogueFamilyManifest {
    readonly id: string;
    readonly version: string;
    readonly contract: string;
    readonly codexHash: string;
    readonly hash: string;
    readonly profiles: readonly string[];
}
export interface CatalogueFamily {
    readonly id: string;
    readonly version: string;
    readonly contract: string;
    readonly codexHash: string;
    readonly hash: string;
    readonly profiles: Readonly<Record<string, unknown>>;
}
/** A stable codex object with immutable snapshots of installed descriptors.
 * Schema instructions and indexes never change when a family is installed. */
export declare function createCatalogue(base: Record<string, unknown>, manifests: Readonly<Record<string, CatalogueFamilyManifest>>): {
    compiledCodex: Record<string, unknown>;
    installCatalogueFamily: (family: CatalogueFamily) => void;
    installedCatalogueFamilies: () => readonly string[];
};
