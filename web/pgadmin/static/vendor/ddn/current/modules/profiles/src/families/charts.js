import { catalogueFamily } from '../generated-family-charts.js';
import { installCatalogueFamily } from '../generated-native.js';
import { registerProfileFamily } from '../family-packs.js';
import { completeProfileDiagnostics } from '../semantic.js';
installCatalogueFamily(catalogueFamily);
registerProfileFamily('charts', Object.keys(catalogueFamily.profiles), completeProfileDiagnostics);
//# sourceMappingURL=charts.js.map