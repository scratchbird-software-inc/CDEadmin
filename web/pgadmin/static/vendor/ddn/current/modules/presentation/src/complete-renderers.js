/** Complete convenience assembly; optional hosts import individual family installers. */
import '../../profiles/src/index.js';
import { installGraphsPresentation } from './family-graphs.js';
import { installChartsPresentation } from './family-charts.js';
import { installGeographyPresentation } from './family-geography.js';
import { installSurfacesPresentation } from './family-surfaces.js';
installGraphsPresentation();
installChartsPresentation();
installGeographyPresentation();
installSurfacesPresentation();
//# sourceMappingURL=complete-renderers.js.map