/** A minimal stored (uncompressed) ZIP writer for bundling a document with its assets offline. */
const table = (() => {
    const values = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++)
            c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        values[n] = c >>> 0;
    }
    return values;
})();
function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes)
        crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
}
export function zipFiles(entries, date = new Date()) {
    const encoder = new TextEncoder(), parts = [], central = [];
    const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
    const day = ((Math.max(1980, date.getFullYear()) - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    let offset = 0;
    const names = new Set();
    for (const entry of entries) {
        const name = entry.name.replace(/^\/+/, '').replace(/\\/g, '/');
        if (!name || name.split('/').includes('..') || names.has(name))
            throw Error('Invalid or duplicate bundle entry: ' + entry.name);
        names.add(name);
        const nameBytes = encoder.encode(name), crc = crc32(entry.bytes), size = entry.bytes.length;
        const local = new Uint8Array(30 + nameBytes.length), view = new DataView(local.buffer);
        view.setUint32(0, 0x04034b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 0x0800, true);
        view.setUint16(8, 0, true);
        view.setUint16(10, time, true);
        view.setUint16(12, day, true);
        view.setUint32(14, crc, true);
        view.setUint32(18, size, true);
        view.setUint32(22, size, true);
        view.setUint16(26, nameBytes.length, true);
        view.setUint16(28, 0, true);
        local.set(nameBytes, 30);
        const header = new Uint8Array(46 + nameBytes.length), cv = new DataView(header.buffer);
        cv.setUint32(0, 0x02014b50, true);
        cv.setUint16(4, 20, true);
        cv.setUint16(6, 20, true);
        cv.setUint16(8, 0x0800, true);
        cv.setUint16(10, 0, true);
        cv.setUint16(12, time, true);
        cv.setUint16(14, day, true);
        cv.setUint32(16, crc, true);
        cv.setUint32(20, size, true);
        cv.setUint32(24, size, true);
        cv.setUint16(28, nameBytes.length, true);
        cv.setUint32(42, offset, true);
        header.set(nameBytes, 46);
        parts.push(local, entry.bytes);
        central.push(header);
        offset += local.length + size;
    }
    const centralSize = central.reduce((sum, part) => sum + part.length, 0);
    const end = new Uint8Array(22), ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, entries.length, true);
    ev.setUint16(10, entries.length, true);
    ev.setUint32(12, centralSize, true);
    ev.setUint32(16, offset, true);
    return new Blob([...parts, ...central, end].map(part => part.slice().buffer), { type: 'application/zip' });
}
//# sourceMappingURL=zip.js.map