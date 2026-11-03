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
/** Stable read-only facade; deferred schema access fails explicitly until installed. */
export declare function createCatalogue(base: Record<string, unknown>, manifests: Readonly<Record<string, CatalogueFamilyManifest>>, expectedCoreHash?: string): {
    compiledCodex: Record<string, unknown>;
    installCatalogueFamily: (family: CatalogueFamily) => void;
    installedCatalogueFamilies: () => readonly string[];
    installCore: (value: Record<string, unknown>, hash?: string) => void;
};
