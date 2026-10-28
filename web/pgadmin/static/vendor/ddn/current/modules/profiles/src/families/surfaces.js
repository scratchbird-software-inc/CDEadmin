import { catalogueFamily } from '../generated-family-surfaces.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily('surfaces', Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=surfaces.js.map