import { catalogueFamily } from '../generated-family-graphs.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily('graphs', Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=graphs.js.map