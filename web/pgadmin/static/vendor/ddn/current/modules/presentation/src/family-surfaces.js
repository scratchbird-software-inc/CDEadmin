import { installPresentationFamily } from './adapters.js';
import { surfaceProfileIds } from './data-catalogue.js';
import { createDataProjector } from './data-adapter.js';
import { drawMatrix, drawPanels, drawTimeline, drawDecision } from './data-surfaces.js';
import { str } from './model.js';
import { analyzeProfile } from '../../profiles/src/analysis-profile.js';
export const projectSurfaces = createDataProjector(surfaceProfileIds, scene => { const profile = str(scene.view.record.profile); if (profile.startsWith('matrix.'))
    drawMatrix(scene);
else if (profile.startsWith('panels.') || profile.startsWith('canvas.'))
    drawPanels(scene);
else if (profile.startsWith('timeline.'))
    drawTimeline(scene);
else
    drawDecision(scene); });
export const surfacesPresentation = Object.freeze({ id: 'surfaces', version: '1.0.0', language: 'ddn-next-1', profiles: surfaceProfileIds, kind: 'data', data: projectSurfaces, analyze: analyzeProfile });
export function installSurfacesPresentation() { installPresentationFamily(surfacesPresentation); }
//# sourceMappingURL=family-surfaces.js.map