import { DataScene } from './data-common.js';
export type Coordinate = [
    number,
    number
];
export declare function projectCoordinate(longitude: number, latitude: number, method: string): Coordinate | undefined;
/** Split a geographic ring at the antimeridian before screen projection. */
export declare function splitAntimeridian(ring: readonly Coordinate[]): Coordinate[][];
export declare function drawGeo(scene: DataScene, supplied?: ReadonlyMap<string, unknown>): void;
