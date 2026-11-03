// Generated from the adopted codex; run profiles/tools/generate.py.
import { nativeCatalogue } from './generated-native-data.js';
import { createCatalogue } from './catalogue-store.js';
import { catalogueFamilies } from './generated-families.js';
import { catalogueShards } from './generated-shards.js';
const catalogue = createCatalogue(nativeCatalogue, { ...catalogueFamilies, ...catalogueShards });
export const compiledCodex = catalogue.compiledCodex;
export const installCatalogueFamily = catalogue.installCatalogueFamily;
export const installedCatalogueFamilies = catalogue.installedCatalogueFamilies;
export const installNativeCatalogue = catalogue.installCore;
//# sourceMappingURL=generated-native.js.map