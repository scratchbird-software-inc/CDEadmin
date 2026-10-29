export const VIEW_SURFACE_PRESETS = Object.freeze([
    { id: 'dynamic', label: 'Dynamic', description: 'The view grows and shrinks with its diagram content.', width: null, height: null, scale: 1 },
    { id: 'tv-hd', label: 'HD', description: '1280 × 720 pixels · 16:9 dashboard for an HD display.', width: 1280, height: 720, scale: 2 / 3 },
    { id: 'tv-fhd', label: 'Full HD', description: '1920 × 1080 pixels · 16:9 dashboard for a Full HD display.', width: 1920, height: 1080, scale: 1 },
    { id: 'tv-2k', label: '2K', description: '2048 × 1080 pixels · the 2K format, distinct from 2560 × 1440 QHD.', width: 2048, height: 1080, scale: 1 },
    { id: 'tv-qhd', label: 'QHD', description: '2560 × 1440 pixels · 16:9 dashboard for a QHD display.', width: 2560, height: 1440, scale: 4 / 3 },
    { id: 'tv-4k', label: '4K UHD', description: '3840 × 2160 pixels · 16:9 dashboard for a 4K UHD display.', width: 3840, height: 2160, scale: 2 },
    { id: 'tv-8k', label: '8K UHD', description: '7680 × 4320 pixels · 16:9 dashboard for an 8K UHD display.', width: 7680, height: 4320, scale: 4 },
].map(preset => Object.freeze(preset)));
export function getViewSurfacePreset(id) {
    return VIEW_SURFACE_PRESETS.find(preset => preset.id === id);
}
//# sourceMappingURL=view-surfaces.js.map