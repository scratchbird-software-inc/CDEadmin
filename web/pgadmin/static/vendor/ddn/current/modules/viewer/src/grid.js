import { records, object, num } from '../../presentation/src/native.js';
/** The workarea's authored grid step, or the standard 16-unit grid when none is set. */
export function gridStep(snapshot) {
    const workarea = snapshot ? records(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile) : undefined;
    const grid = workarea?.record.grid;
    const value = typeof grid === 'number' ? grid : num(object(grid).size ?? object(grid).step ?? object(grid).spacing, 16);
    return Number.isFinite(value) && value >= 2 && value <= 1000 ? value : 16;
}
/** Session view settings a host sets on an ancestor of the viewer. */
export function viewSetting(element, name) {
    return element.closest(`[data-ddn-${name}]`)?.getAttribute(`data-ddn-${name}`) ?? undefined;
}
//# sourceMappingURL=grid.js.map