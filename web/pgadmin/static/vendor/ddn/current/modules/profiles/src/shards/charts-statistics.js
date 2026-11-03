// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-charts-statistics.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("charts-statistics", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=charts-statistics.js.map