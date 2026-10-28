import { DataScene } from './data-common.js';
import { str, object, pathValue, num } from './model.js';
/** Shared data-scene setup has no dependency on optional drawing algorithms. */
export function createDataProjector(profiles, draw, finish) {
    return (snapshot, view, bounds, effective, options = {}) => {
        const profile = str(view.record.profile);
        if (!profiles.includes(profile))
            return;
        const settings = { ...object(pathValue(effective, 'projection.options')), ...object(pathValue(view.record, 'projection.options')) };
        const allocated = { ...bounds, width: num(settings.width, bounds.width), height: num(settings.height, bounds.height) };
        const scene = new DataScene(snapshot, view, allocated, effective, options);
        draw(scene, options.geography);
        const result = scene.finish();
        return finish ? finish(result, settings, scene) : result;
    };
}
//# sourceMappingURL=data-adapter.js.map