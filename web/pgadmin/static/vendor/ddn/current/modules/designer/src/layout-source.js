import { getViewSurfacePreset } from '../../profiles/src/view-surfaces.js';
/** Dynamic remains implicit; a fixed layout stores only its versioned recipe. */
export function viewLayoutSource(preset) {
    if (!getViewSurfacePreset(preset))
        throw Error('Choose an available view layout.');
    return preset === 'dynamic' ? '' : `    with\n        surface.preset ${preset}\n`;
}
//# sourceMappingURL=layout-source.js.map