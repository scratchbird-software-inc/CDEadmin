import gettext from 'sources/gettext';

// The caller owns the native stream. This pump owns only the file writer.
export async function saveFirebirdBlob({writer, reference, read, stopped, progress}) {
  let offset = 0;
  const checkStopped = () => {
    if (stopped()) throw new Error(gettext('BLOB save stopped.'));
  };
  try {
    while (true) {
      checkStopped();
      const part = await read(offset);
      checkStopped();
      if (part.blob_reference !== reference || part.offset !== offset ||
          part.encoding !== 'base64' || typeof part.complete !== 'boolean' ||
          typeof part.data !== 'string' || part.data.length > 87384 ||
          !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(part.data)) {
        throw new Error(gettext('Invalid BLOB download response.'));
      }
      const binary = atob(part.data);
      if (binary.length > 65536 || (!part.complete && binary.length === 0) ||
          !Number.isSafeInteger(part.next_offset) || part.next_offset !== offset + binary.length) {
        throw new Error(gettext('Invalid BLOB download offset or length.'));
      }
      await writer.write(Uint8Array.from(binary, value => value.charCodeAt(0)));
      offset = part.next_offset;
      progress(offset);
      checkStopped();
      if (part.complete) break;
    }
    await writer.close();
    return offset;
  } catch (error) {
    try {
      await writer.abort();
    } catch {
      throw new Error(gettext('BLOB save failed; file cleanup is unconfirmed. Inspect the destination file.'));
    }
    throw error;
  }
}
