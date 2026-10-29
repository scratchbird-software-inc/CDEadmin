export interface ZipEntry {
    readonly name: string;
    readonly bytes: Uint8Array;
}
export declare function zipFiles(entries: readonly ZipEntry[], date?: Date): Blob;
