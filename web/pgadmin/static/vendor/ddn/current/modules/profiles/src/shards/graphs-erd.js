// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-graphs-erd.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("graphs-erd", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=graphs-erd.js.map