// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-graphs-process.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("graphs-process", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=graphs-process.js.map