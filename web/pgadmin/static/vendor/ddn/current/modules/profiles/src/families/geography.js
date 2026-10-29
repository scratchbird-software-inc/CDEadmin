import { catalogueFamily } from '../generated-family-geography.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily('geography', Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=geography.js.map