// Generated from the adopted codex; run profiles/tools/generate.py.
import { catalogueFamily } from './data-surfaces-timeline.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily("surfaces-timeline", Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=surfaces-timeline.js.map