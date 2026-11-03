// Generated from the adopted codex; run profiles/tools/generate.py.
import { nativeIndex, nativeSchemaHash } from './generated-native-index.js';
import { createCatalogue } from './catalogue-store.js';
import { catalogueFamilies } from './generated-families.js';
import { catalogueShards } from './generated-shards.js';
const catalogue = createCatalogue(nativeIndex, { ...catalogueFamilies, ...catalogueShards }, nativeSchemaHash);
export const compiledCodex = catalogue.compiledCodex;
export const installCatalogueFamily = catalogue.installCatalogueFamily;
export const installedCatalogueFamilies = catalogue.installedCatalogueFamilies;
export const installNativeCatalogue = catalogue.installCore;
//# sourceMappingURL=generated-native-light.js.map