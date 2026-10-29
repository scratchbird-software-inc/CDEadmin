/** Complete data convenience entry. Families themselves have independent imports. */
import { str } from './model.js';
import { projectCharts } from './family-charts.js';
import { projectGeography } from './family-geography.js';
import { projectSurfaces } from './family-surfaces.js';
export { dataProfileIds } from './data-catalogue.js';
export const projectDataProfile = (snapshot, view, bounds, effective, options = {}) => {
    const profile = str(view.record.profile), project = profile.startsWith('chart.') ? projectCharts : profile.startsWith('geo.') ? projectGeography : projectSurfaces;
    return project(snapshot, view, bounds, effective, options);
};
//# sourceMappingURL=data-profiles.js.map