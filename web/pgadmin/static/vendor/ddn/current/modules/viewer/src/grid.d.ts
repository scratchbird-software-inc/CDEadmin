import type { ModelSnapshot } from '@ddn/types';
/** The workarea's authored grid step, or the standard 16-unit grid when none is set. */
export declare function gridStep(snapshot: ModelSnapshot | undefined): number;
/** Session view settings a host sets on an ancestor of the viewer. */
export declare function viewSetting(element: Element, name: 'grid' | 'snap' | 'lod' | 'wheel'): string | undefined;
