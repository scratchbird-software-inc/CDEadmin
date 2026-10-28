import { installPresentationFamily } from './adapters.js';
import { chartProfileIds } from './data-catalogue.js';
import { createDataProjector } from './data-adapter.js';
import { drawChart } from './data-charts.js';
import { extrudeChart } from './data-isometric.js';
import { str } from './model.js';
export const projectCharts = createDataProjector(chartProfileIds, drawChart, (result, settings, scene) => { const profile = str(scene.view.record.profile); return extrudeChart(result, { ...settings, mark: settings.mark ?? (['chart.basic@1', 'chart.quality@1'].includes(profile) ? 'bar' : profile.slice(6).split('@')[0]) }, scene.extrusionDepths); });
export const chartsPresentation = Object.freeze({ id: 'charts', version: '1.0.0', language: 'ddn-next-1', profiles: chartProfileIds, kind: 'data', data: projectCharts });
export function installChartsPresentation() { installPresentationFamily(chartsPresentation); }
//# sourceMappingURL=family-charts.js.map