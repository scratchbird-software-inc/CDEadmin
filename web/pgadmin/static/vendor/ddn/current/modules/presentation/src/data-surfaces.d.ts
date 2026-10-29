import type { Bounds } from '@ddn/types';
import { DataScene } from './data-common.js';
export declare function drawMatrix(scene: DataScene): void;
export declare function drawPanels(scene: DataScene): void;
export declare function intersectClip(a: Bounds, b: Bounds): Bounds;
export declare function civilTime(instant: number, zone: string): number;
export declare function timelineMoment(value: unknown, zone: string): {
    instant: number;
    civil: number;
    dateOnly: boolean;
};
export declare function businessDays(start: number, end: number, weekdays: readonly number[], holidays?: readonly string[]): number;
export declare function businessCalendarPosition(start: number, end: number, weekdays: readonly number[], holidays?: readonly string[]): (time: number) => number;
export declare function drawTimeline(scene: DataScene): void;
export declare function drawDecision(scene: DataScene): void;
