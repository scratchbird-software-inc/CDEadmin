import type { Bounds } from '@ddn/types';
import { DataScene, type Datum } from './data-common.js';
interface Tree {
    key: string;
    name: string;
    children: Tree[];
    value: number;
    records: Datum[];
    depth: number;
    slot: number;
    radius: number;
    x: number;
    y: number;
}
export declare function hierarchy(records: readonly Datum[]): Tree;
export declare function drawHierarchy(scene: DataScene, mark: string, data: Datum[]): void;
export declare function forcePositions(names: readonly string[], links: readonly {
    source: string;
    target: string;
    value: number;
}[], width: number, height: number): Map<string, [
    number,
    number
]>;
export declare function drawLinks(scene: DataScene, mark: string, data: Datum[]): void;
/** Radial tidy hierarchy; endpoints retain their declared hierarchy depth. */
export declare function radialHierarchyPositions(names: readonly string[], bounds: Bounds): Map<string, [
    number,
    number
]>;
export {};
