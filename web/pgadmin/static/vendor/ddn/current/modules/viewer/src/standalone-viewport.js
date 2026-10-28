/** A standalone document has no camera space outside its sole view. */
export function constrainStandaloneViewport(viewport, extent, view) {
    const width = Math.min(extent.width, viewport.bounds.width / viewport.zoom);
    const height = Math.min(extent.height, viewport.bounds.height / viewport.zoom);
    return {
        bounds: {
            x: Math.max(extent.x, Math.min(viewport.bounds.x, extent.x + extent.width - width)),
            y: Math.max(extent.y, Math.min(viewport.bounds.y, extent.y + extent.height - height)),
            width: width * viewport.zoom,
            height: height * viewport.zoom,
        },
        zoom: viewport.zoom,
        ...(view ? { activeView: view } : {}),
    };
}
/** Preserve fit-to-view while its content grows or shrinks; retain a deliberately zoomed camera. */
export function sameBounds(a, b) {
    return ['x', 'y', 'width', 'height'].every(key => Math.abs(a[key] - b[key]) < .001);
}
//# sourceMappingURL=standalone-viewport.js.map