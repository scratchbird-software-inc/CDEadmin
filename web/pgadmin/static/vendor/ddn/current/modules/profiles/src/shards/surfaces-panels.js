// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-surfaces-panels.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("surfaces-panels", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=surfaces-panels.js.map