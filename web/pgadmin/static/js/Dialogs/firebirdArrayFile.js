import gettext from 'sources/gettext';

// One bounded native slice and one file write at a time; no SQL replay.
export async function saveFirebirdArray({writer, descriptor, read, stopped, progress}) {
  let offset = 0, bytes = 0;
  const encoder = new TextEncoder();
  const checkStopped = () => {
    if (stopped()) throw new Error(gettext('ARRAY save stopped.'));
  };
  const write = async record => {
    checkStopped();
    const data = encoder.encode(JSON.stringify(record) + '\n');
    if (data.byteLength > 1048576) throw new Error(gettext('ARRAY file record exceeds the byte limit.'));
    await writer.write(data);
    bytes += data.byteLength;
    checkStopped();
  };
  try {
    const {bounds, element_count: total, array_reference: reference} = descriptor;
    if (typeof reference !== 'string' || !reference || !Array.isArray(bounds) || bounds.length < 1 || bounds.length > 16 ||
      bounds.some(pair => !Array.isArray(pair) || pair.length !== 2 ||
        !pair.every(value => Number.isSafeInteger(value) && value >= -2147483648 && value <= 2147483647) || pair[0] > pair[1]) ||
      !Number.isSafeInteger(total) || total < 1 || total >= 2147483648 ||
      !['native_element_type', 'scale', 'subtype'].every(key => Number.isSafeInteger(descriptor[key])) ||
      !(descriptor.charset_id === null || Number.isSafeInteger(descriptor.charset_id)) ||
      bounds.reduce((count, [low, high]) => count * (high - low + 1), 1) !== total) {
      throw new Error(gettext('Invalid ARRAY file descriptor.'));
    }
    await write({format: 'cdeadmin.firebird-array.v1', bounds, element_count: total,
      native_element_type: descriptor.native_element_type, scale: descriptor.scale,
      subtype: descriptor.subtype, charset_id: descriptor.charset_id});
    while (offset < total) {
      checkStopped();
      const part = await read(offset);
      checkStopped();
      let remainder = offset;
      const coordinates = bounds.map(() => 0);
      for (let index = bounds.length - 1; index >= 0; index--) {
        const size = bounds[index][1] - bounds[index][0] + 1;
        coordinates[index] = bounds[index][0] + remainder % size;
        remainder = Math.floor(remainder / size);
      }
      if (part.array_reference !== reference || part.offset !== offset ||
        !Array.isArray(part.values) || part.values.length < 1 || part.values.length > 256 ||
        part.next_offset !== offset + part.values.length || part.next_offset > total ||
        part.values.length > bounds.at(-1)[1] - coordinates.at(-1) + 1 ||
        part.complete !== (part.next_offset === total) ||
        !Array.isArray(part.coordinates) || part.coordinates.length !== coordinates.length ||
        coordinates.some((value, index) => value !== part.coordinates[index])) {
        throw new Error(gettext('Invalid ARRAY download response.'));
      }
      await write({offset, coordinates, values: part.values});
      offset = part.next_offset;
      progress({elements: offset, bytes});
    }
    await write({complete: true, element_count: total});
    await writer.close();
    return {elements: offset, bytes};
  } catch (error) {
    try {
      await writer.abort();
    } catch {
      throw new Error(gettext('ARRAY save failed; file cleanup is unconfirmed. Inspect the destination file.'));
    }
    throw error;
  }
}
