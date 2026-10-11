export const BLOB_EDIT_LIMIT = 1024 * 1024;

export function blobBytes(text, kind) {
  if (kind === 'text') return new TextEncoder().encode(text);
  const raw = atob(text);
  if (btoa(raw) !== text) throw new Error('Binary data must be canonical Base64.');
  return Uint8Array.from(raw, char => char.charCodeAt(0));
}

export function blobImport(bytes, kind) {
  if (bytes.byteLength > BLOB_EDIT_LIMIT) throw new Error('File exceeds the 1 MiB editor limit. Use chunked transfer.');
  if (kind === 'text') return new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes);
  let raw = '';
  for (let start = 0; start < bytes.length; start += 8192) raw += String.fromCharCode(...bytes.subarray(start, start + 8192));
  return btoa(raw);
}

export function blobDraft(original, draft, kind, endings, changed) {
  if (draft.isNull) return {...draft};
  let text = draft.text;
  if (kind === 'text') {
    if (endings === 'preserve') {
      if (changed && original.includes('\r')) throw new Error('Choose LF or CRLF before editing text with CR line endings.');
      if (!changed) text = original;
    } else {
      text = text.replace(/\r\n|\r|\n/g, '\n');
      if (endings === 'crlf') text = text.replace(/\n/g, '\r\n');
    }
  }
  if (blobBytes(text, kind).length > BLOB_EDIT_LIMIT) throw new Error('Value exceeds the 1 MiB editor limit. Use chunked transfer.');
  return {...draft, text};
}
