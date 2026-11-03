// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-graphs-uml.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("graphs-uml", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=graphs-uml.js.map