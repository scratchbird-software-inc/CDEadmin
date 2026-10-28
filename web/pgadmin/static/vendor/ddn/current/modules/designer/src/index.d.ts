export { createStandardDialog, colourField } from './dialogs.js';
export { parsePresetPack, serializePresetPack } from './presets.js';
import type { Viewer, Designer, DesignerOptions } from '@ddn/types/browser';
export declare function createDesigner(viewer: Viewer, options: DesignerOptions): Designer;
