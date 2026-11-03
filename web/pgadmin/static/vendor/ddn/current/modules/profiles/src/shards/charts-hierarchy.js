// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-charts-hierarchy.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("charts-hierarchy", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=charts-hierarchy.js.map