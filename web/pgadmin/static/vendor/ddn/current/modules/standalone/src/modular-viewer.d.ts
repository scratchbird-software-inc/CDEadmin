import type { Viewer, ViewerOptions } from '../../types/src/browser.js';
import { getViewerHandle } from '../../viewer/src/native.js';
export { getViewerHandle };
export declare function createViewer(element: HTMLElement, options?: ViewerOptions): Viewer;
