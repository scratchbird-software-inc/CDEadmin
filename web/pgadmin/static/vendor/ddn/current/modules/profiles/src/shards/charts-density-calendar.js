// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-charts-density-calendar.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("charts-density-calendar", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=charts-density-calendar.js.map