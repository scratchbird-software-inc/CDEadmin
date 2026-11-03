// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-geography-outline.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("geography-outline", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=geography-outline.js.map